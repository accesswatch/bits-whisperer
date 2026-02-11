"""Accessibility helpers for WXPython controls."""

from __future__ import annotations

import logging

import wx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screen reader direct-speech via accessible_output2
# ---------------------------------------------------------------------------
_screen_reader_output = None


def _get_screen_reader():
    """Lazily initialise the accessible_output2 Auto output.

    Returns ``None`` when the library is unavailable so every call-site
    can fall back gracefully to status-bar announcements.
    """
    global _screen_reader_output
    if _screen_reader_output is not None:
        return _screen_reader_output
    try:
        from accessible_output2.outputs.auto import Auto

        _screen_reader_output = Auto()
    except Exception:
        logger.debug("accessible_output2 not available — screen reader speech disabled")
        _screen_reader_output = False  # sentinel: tried and failed
    return _screen_reader_output if _screen_reader_output else None


def speak(message: str, interrupt: bool = True) -> None:
    """Speak a message directly to the active screen reader.

    Uses *accessible_output2* to route speech to NVDA, JAWS, Narrator,
    or any other running screen reader. Falls back silently when no
    screen reader is detected.

    Args:
        message: Text to announce.
        interrupt: If ``True`` (default), interrupt any current speech.
    """
    sr = _get_screen_reader()
    if sr:
        try:
            sr.speak(message, interrupt=interrupt)
        except Exception:
            logger.debug("Screen reader speak failed for: %s", message)


def announce_to_screen_reader(message: str, interrupt: bool = True) -> None:
    """Announce a message to the screen reader (convenience alias).

    This is the primary function to call for alerts, errors, warnings,
    and important status changes that the user must hear.

    Args:
        message: Text to announce.
        interrupt: If ``True`` (default), interrupt any current speech.
    """
    speak(message, interrupt=interrupt)


def set_accessible_name(ctrl: wx.Window, name: str) -> None:
    """Set the accessible name on a WXPython control.

    Args:
        ctrl: The wx control to label.
        name: The accessible name string for screen readers.
    """
    ctrl.SetName(name)


def set_accessible_help(ctrl: wx.Window, text: str) -> None:
    """Set help text that screen readers can announce.

    Args:
        ctrl: The wx control.
        text: Descriptive help text.
    """
    ctrl.SetHelpText(text)


def label_control(label: wx.StaticText, ctrl: wx.Window) -> None:
    """Associate a static text label with a control for screen readers.

    Args:
        label: The wx.StaticText serving as the visible label.
        ctrl: The control that the label describes.
    """
    ctrl.SetName(label.GetLabel())


def announce_status(
    frame: wx.Frame,
    message: str,
    field: int = 0,
    *,
    speak_to_reader: bool = False,
) -> None:
    """Update the status bar text — picked up by screen readers.

    Args:
        frame: The frame containing the status bar.
        message: Text to display and announce.
        field: Status bar field index (default 0).
        speak_to_reader: If ``True``, also force-speak through
            accessible_output2 for critical messages.
    """
    status_bar = frame.GetStatusBar()
    if status_bar:
        status_bar.SetStatusText(message, field)
    if speak_to_reader:
        speak(message)


def safe_call_after(func, *args, **kwargs) -> None:
    """Thread-safe wrapper to schedule a callable on the main UI thread.

    Args:
        func: Callable to invoke on the main thread.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.
    """
    wx.CallAfter(func, *args, **kwargs)


def create_accelerator_entry(flags: int, keycode: int, cmd_id: int) -> wx.AcceleratorEntry:
    """Create an accelerator table entry.

    Args:
        flags: Modifier flags (wx.ACCEL_CTRL, wx.ACCEL_SHIFT, etc.).
        keycode: Key code (e.g. ord('O')).
        cmd_id: Menu item / command ID to trigger.

    Returns:
        A wx.AcceleratorEntry instance.
    """
    return wx.AcceleratorEntry(flags, keycode, cmd_id)


def make_panel_accessible(panel: wx.Panel) -> None:
    """Apply standard accessibility settings to a panel.

    Args:
        panel: The wx.Panel to configure.
    """
    panel.SetWindowStyleFlag(panel.GetWindowStyleFlag() | wx.TAB_TRAVERSAL)


def accessible_message_box(
    message: str,
    caption: str,
    style: int = wx.OK | wx.ICON_INFORMATION,
    parent: wx.Window | None = None,
) -> int:
    """Show a ``wx.MessageBox`` and simultaneously announce the message
    to the active screen reader via *accessible_output2*.

    This ensures that error, warning, and informational dialogs are
    always audible to screen reader users, even if the dialog itself
    doesn't trigger a proper alert event.

    Args:
        message: The dialog body text.
        caption: The dialog title / caption.
        style: wx dialog style flags (``wx.OK``, ``wx.ICON_ERROR``, etc.).
        parent: Parent window (may be ``None``).

    Returns:
        The button ID pressed by the user (e.g. ``wx.OK``, ``wx.YES``).
    """
    # Determine severity prefix for the screen reader announcement
    if style & wx.ICON_ERROR:
        prefix = "Error"
    elif style & wx.ICON_WARNING:
        prefix = "Warning"
    else:
        prefix = "Alert"

    # Announce to screen reader
    speak(f"{prefix}: {caption}. {message}")

    return int(wx.MessageBox(message, caption, style, parent))
