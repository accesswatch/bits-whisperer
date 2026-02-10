"""System tray icon with progress, notifications, and background support.

Provides a ``wx.adv.TaskBarIcon`` that shows transcription progress,
delivers balloon/toast notifications on job completion, and lets the
user hide/restore the main window while processing continues in the
background.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import wx
import wx.adv

from bits_whisperer.utils.constants import APP_NAME

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Tray context-menu IDs
ID_TRAY_SHOW = wx.NewIdRef()
ID_TRAY_HIDE = wx.NewIdRef()
ID_TRAY_PAUSE = wx.NewIdRef()
ID_TRAY_RESUME = wx.NewIdRef()
ID_TRAY_QUIT = wx.NewIdRef()


def _make_tray_icon() -> wx.Icon:
    """Create a small 16x16 icon for the system tray.

    Generates a simple programmatic icon so we don't depend on
    an external .ico file. In a production build this would be
    replaced with a proper branded icon resource.
    """
    bmp = wx.Bitmap(16, 16)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(40, 120, 200)))
    dc.Clear()
    dc.SetTextForeground(wx.WHITE)
    font = wx.Font(
        9,
        wx.FONTFAMILY_SWISS,
        wx.FONTSTYLE_NORMAL,
        wx.FONTWEIGHT_BOLD,
    )
    dc.SetFont(font)
    dc.DrawText("B", 3, 0)
    dc.SelectObject(wx.NullBitmap)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon


class TrayIcon(wx.adv.TaskBarIcon):
    """System-tray icon for BITS Whisperer.

    Capabilities
    ------------
    - Tooltip shows current progress summary (idle / X of Y transcribing)
    - Left-click toggles window visibility
    - Right-click context menu: Show / Hide / Pause / Resume / Quit
    - Balloon notifications on job completion or errors
    - Stays alive when the main window is hidden so background processing
      continues uninterrupted
    """

    def __init__(self, main_frame: MainFrame) -> None:
        """Initialise the tray icon and bind events."""
        super().__init__(wx.adv.TBI_DOCK)
        self._main_frame = main_frame
        self._icon = _make_tray_icon()
        self._is_processing = False
        self._progress_text = "Idle"

        self.SetIcon(self._icon, f"{APP_NAME} — Idle")

        # --- Event bindings ---
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self._on_left_click)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self._on_left_click)

    # ------------------------------------------------------------------ #
    # Tooltip / progress updates (called from main thread)                 #
    # ------------------------------------------------------------------ #

    def update_progress(
        self,
        completed: int,
        total: int,
        active: int,
        current_file: str = "",
    ) -> None:
        """Update the tray tooltip with live progress.

        Args:
            completed: Number of finished jobs.
            total: Total jobs in the batch.
            active: Currently processing count.
            current_file: Name of the file being transcribed.
        """
        if total == 0:
            self._progress_text = "Idle"
            self._is_processing = False
        else:
            pct = int(completed / total * 100) if total else 0
            status = (
                f"Transcribing {completed}/{total} ({pct}%)"
                if active > 0
                else f"Complete — {completed}/{total}"
            )
            if current_file:
                status += f"\n{current_file}"
            self._progress_text = status
            self._is_processing = active > 0

        self.SetIcon(self._icon, f"{APP_NAME} — {self._progress_text}")

    def set_idle(self) -> None:
        """Reset to idle state."""
        self._progress_text = "Idle"
        self._is_processing = False
        self.SetIcon(self._icon, f"{APP_NAME} — Idle")

    # ------------------------------------------------------------------ #
    # Notifications                                                        #
    # ------------------------------------------------------------------ #

    @property
    def _notifications_enabled(self) -> bool:
        """Check if balloon notifications are enabled in settings."""
        try:
            return self._main_frame.app_settings.general.show_notifications
        except Exception:
            return True  # Default to enabled if settings unavailable

    def notify_job_complete(self, file_name: str) -> None:
        """Show a balloon notification when a job finishes.

        Args:
            file_name: Name of the completed audio file.
        """
        if not self._notifications_enabled:
            return
        try:
            self.ShowBalloon(
                title=f"{APP_NAME} — Transcription Complete",
                text=f"Finished: {file_name}",
                msec=4000,
                flags=wx.ICON_INFORMATION,
            )
        except Exception:
            logger.debug("Balloon notification not supported on this platform")

    def notify_batch_complete(self, total: int, failed: int = 0) -> None:
        """Show a balloon notification when a batch finishes.

        Args:
            total: Total jobs processed.
            failed: Number of failed jobs.
        """
        if not self._notifications_enabled:
            return
        if failed:
            text = f"Batch complete: {total - failed} succeeded, {failed} failed"
        else:
            text = f"All {total} files transcribed successfully!"
        try:
            self.ShowBalloon(
                title=f"{APP_NAME} — Batch Complete",
                text=text,
                msec=5000,
                flags=wx.ICON_INFORMATION if failed == 0 else wx.ICON_WARNING,
            )
        except Exception:
            logger.debug("Balloon notification not supported on this platform")

    def notify_error(self, file_name: str, error: str) -> None:
        """Show a balloon notification on job failure.

        Args:
            file_name: Name of the failed audio file.
            error: Short error description.
        """
        if not self._notifications_enabled:
            return
        try:
            self.ShowBalloon(
                title=f"{APP_NAME} — Error",
                text=f"{file_name}: {error[:200]}",
                msec=6000,
                flags=wx.ICON_ERROR,
            )
        except Exception:
            logger.debug("Balloon notification not supported on this platform")

    # ------------------------------------------------------------------ #
    # Window visibility                                                    #
    # ------------------------------------------------------------------ #

    def show_main_window(self) -> None:
        """Show and raise the main window."""
        frame = self._main_frame
        if frame.IsIconized():
            frame.Iconize(False)
        frame.Show(True)
        frame.Raise()
        frame.SetFocus()

    def hide_main_window(self) -> None:
        """Hide the main window (minimize to tray)."""
        self._main_frame.Show(False)

    def toggle_main_window(self) -> None:
        """Toggle main window visibility."""
        if self._main_frame.IsShown():
            self.hide_main_window()
        else:
            self.show_main_window()

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_left_click(self, _event: wx.CommandEvent) -> None:
        """Left-click on the tray icon toggles window visibility."""
        self.toggle_main_window()

    def CreatePopupMenu(self) -> wx.Menu:
        """Build the right-click context menu for the tray icon.

        Returns:
            wx.Menu with Show/Hide, Pause/Resume, and Quit items.
        """
        menu = wx.Menu()

        if self._main_frame.IsShown():
            menu.Append(ID_TRAY_HIDE, "&Hide Window")
        else:
            menu.Append(ID_TRAY_SHOW, "&Show Window")

        menu.AppendSeparator()

        svc = self._main_frame.transcription_service
        if svc.is_running:
            if svc.is_paused:
                menu.Append(ID_TRAY_RESUME, "&Resume Transcription")
            else:
                menu.Append(ID_TRAY_PAUSE, "&Pause Transcription")
        menu.AppendSeparator()

        # Progress summary
        menu.Append(wx.ID_ANY, self._progress_text).Enable(False)
        menu.AppendSeparator()

        menu.Append(ID_TRAY_QUIT, "&Quit BITS Whisperer")

        # --- Bindings ---
        self.Bind(wx.EVT_MENU, self._on_show_hide, id=ID_TRAY_SHOW)
        self.Bind(wx.EVT_MENU, self._on_show_hide, id=ID_TRAY_HIDE)
        self.Bind(wx.EVT_MENU, self._on_pause_resume, id=ID_TRAY_PAUSE)
        self.Bind(wx.EVT_MENU, self._on_pause_resume, id=ID_TRAY_RESUME)
        self.Bind(wx.EVT_MENU, self._on_quit, id=ID_TRAY_QUIT)

        return menu

    def _on_show_hide(self, _event: wx.CommandEvent) -> None:
        self.toggle_main_window()

    def _on_pause_resume(self, _event: wx.CommandEvent) -> None:
        svc = self._main_frame.transcription_service
        if svc.is_paused:
            svc.resume()
        else:
            svc.pause()

    def _on_quit(self, _event: wx.CommandEvent) -> None:
        """Quit the application completely — bypass minimize-to-tray."""
        self._main_frame._request_exit()

    # ------------------------------------------------------------------ #
    # Cleanup                                                              #
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """Remove the tray icon before shutdown."""
        self.RemoveIcon()
        self.Destroy()
