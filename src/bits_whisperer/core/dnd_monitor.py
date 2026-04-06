"""Do Not Disturb / Focus Assist detection and transcription pausing.

Monitors the system-wide DND / Focus Assist state on Windows and macOS.
When DND is detected, transcription jobs are paused with an accessible
alert.  Users can resume manually or automatically when DND turns off.

Windows: Uses WinRT ``QuietHoursSettings`` (Focus Assist) API via
``winsdk`` or falls back to registry polling.
macOS: Checks ``NSDoNotDisturbEnabled`` via ``defaults read``.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DNDStatus:
    """Current Do Not Disturb / Focus Assist status."""

    active: bool = False
    mode: str = ""  # "off", "priority_only", "alarms_only", "focus", "unknown"
    source: str = ""  # "winrt", "registry", "macos_defaults", "unsupported"
    error: str = ""


@dataclass
class DNDEvent:
    """Event emitted when DND state changes."""

    previous_active: bool = False
    current_active: bool = False
    mode: str = ""


# ---------------------------------------------------------------------------
# Platform detectors
# ---------------------------------------------------------------------------


def _detect_dnd_windows() -> DNDStatus:
    """Detect Focus Assist / DND on Windows via WinRT or registry.

    Returns:
        DNDStatus with current state.
    """
    # Try WinRT first (Windows 10 1709+)
    try:
        from winsdk.windows.ui.notifications import NotificationSetting
        from winsdk.windows.ui.notifications.management import (
            UserNotificationListener,
        )

        listener = UserNotificationListener.current
        setting = listener.get_notification_setting()

        # NotificationSetting enum:
        # 0 = Enabled (notifications allowed — DND off)
        # 1 = DisabledForApplication
        # 2 = DisabledForUser
        # 3 = DisabledByGroupPolicy
        # 4 = DisabledByManifest
        if setting == NotificationSetting.ENABLED:
            return DNDStatus(active=False, mode="off", source="winrt")
        return DNDStatus(
            active=True,
            mode="focus",
            source="winrt",
        )
    except Exception:
        pass

    # Fallback: registry polling for Focus Assist profile
    try:
        import winreg

        key_path = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion"
            r"\CloudStore\Store\DefaultAccount\Current"
            r"\default$windows.data.notifications.quiethourssettings"
            r"\windows.data.notifications.quiethourssettings"
        )
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
            data, _ = winreg.QueryValueEx(key, "Data")
            winreg.CloseKey(key)
            # The registry blob's byte at offset 18 indicates the mode:
            # 0 = off, 1 = priority only, 2 = alarms only
            if isinstance(data, bytes) and len(data) > 18:
                mode_byte = data[18]
                if mode_byte == 0:
                    return DNDStatus(active=False, mode="off", source="registry")
                mode_name = {1: "priority_only", 2: "alarms_only"}.get(mode_byte, "focus")
                return DNDStatus(active=True, mode=mode_name, source="registry")
        except FileNotFoundError:
            pass
        except Exception:
            pass

        return DNDStatus(active=False, mode="off", source="registry")
    except Exception as exc:
        return DNDStatus(active=False, mode="unknown", source="registry", error=str(exc))


def _detect_dnd_macos() -> DNDStatus:
    """Detect Do Not Disturb on macOS via ``defaults read``.

    Returns:
        DNDStatus with current state.
    """
    try:
        # macOS Monterey+ uses Focus modes
        result = subprocess.run(
            [
                "defaults",
                "read",
                "com.apple.controlcenter",
                "NSDoNotDisturbEnabled",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            active = value == "1"
            return DNDStatus(
                active=active,
                mode="focus" if active else "off",
                source="macos_defaults",
            )

        # Fallback for older macOS (pre-Monterey)
        result2 = subprocess.run(
            [
                "defaults",
                "-currentHost",
                "read",
                "com.apple.notificationcenterui",
                "doNotDisturb",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result2.returncode == 0:
            active = result2.stdout.strip() == "1"
            return DNDStatus(
                active=active,
                mode="focus" if active else "off",
                source="macos_defaults",
            )

        return DNDStatus(active=False, mode="off", source="macos_defaults")
    except Exception as exc:
        return DNDStatus(active=False, mode="unknown", source="macos_defaults", error=str(exc))


def detect_dnd() -> DNDStatus:
    """Detect system-wide DND / Focus Assist status.

    Returns:
        DNDStatus for the current platform.
    """
    system = platform.system()
    if system == "Windows":
        return _detect_dnd_windows()
    elif system == "Darwin":
        return _detect_dnd_macos()
    return DNDStatus(active=False, mode="unsupported", source="unsupported")


# ---------------------------------------------------------------------------
# Monitor service
# ---------------------------------------------------------------------------


@dataclass
class DNDMonitor:
    """Background monitor that polls DND status and emits change events.

    Typical usage::

        monitor = DNDMonitor(
            poll_interval=5.0,
            on_dnd_changed=my_callback,
        )
        monitor.start()
        # ... later ...
        monitor.stop()

    Args:
        poll_interval: Seconds between status polls.
        on_dnd_changed: Callback receiving ``DNDEvent`` on state changes.
    """

    poll_interval: float = 5.0
    on_dnd_changed: Callable[[DNDEvent], None] | None = None
    _running: bool = field(default=False, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _last_active: bool = field(default=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def start(self) -> None:
        """Start polling DND status in a background thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="dnd-monitor",
        )
        self._thread.start()
        logger.info("DND monitor started (interval=%.1fs).", self.poll_interval)

    def stop(self) -> None:
        """Stop the background polling thread."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.poll_interval + 1)
        self._thread = None
        logger.info("DND monitor stopped.")

    @property
    def is_dnd_active(self) -> bool:
        """Return the last-known DND state."""
        return self._last_active

    def get_status(self) -> DNDStatus:
        """Poll and return the current DND status immediately."""
        return detect_dnd()

    def _poll_loop(self) -> None:
        """Background loop that polls DND and fires change events."""
        # Initial read
        status = detect_dnd()
        self._last_active = status.active

        while not self._stop_event.is_set():
            self._stop_event.wait(self.poll_interval)
            if not self._running:
                break
            try:
                status = detect_dnd()
                if status.active != self._last_active:
                    event = DNDEvent(
                        previous_active=self._last_active,
                        current_active=status.active,
                        mode=status.mode,
                    )
                    self._last_active = status.active
                    logger.info(
                        "DND state changed: %s → %s (mode=%s)",
                        event.previous_active,
                        event.current_active,
                        event.mode,
                    )
                    if self.on_dnd_changed:
                        self.on_dnd_changed(event)
            except Exception:
                logger.debug("DND poll error", exc_info=True)
