"""Startup dependency checker — ensures required external tools are available.

Checks for and automatically installs missing external dependencies on
Windows (primarily ffmpeg). Uses ``winget`` when available, with a
fallback manual-download prompt for older Windows versions.

This module is invoked during application startup, before the main frame
is created, to give users a smooth first-run experience.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_to_screen_reader,
)

logger = logging.getLogger(__name__)


def is_ffmpeg_available() -> bool:
    """Check whether ffmpeg is reachable on PATH or at common locations.

    Returns:
        True if ffmpeg can be executed.
    """
    if shutil.which("ffmpeg"):
        return True
    # Common Windows install locations
    for candidate in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]:
        if Path(candidate).exists():
            return True
    return False


def _has_winget() -> bool:
    """Return True if ``winget`` is available."""
    try:
        result = subprocess.run(
            ["winget", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode == 0
    except Exception:
        return False


def install_ffmpeg_winget(progress_callback=None) -> bool:
    """Install ffmpeg via ``winget`` (Windows Package Manager).

    Args:
        progress_callback: Optional callable receiving status strings.

    Returns:
        True if installation succeeded.
    """
    try:
        if progress_callback:
            progress_callback("Installing ffmpeg via Windows Package Manager…")
        logger.info("Installing ffmpeg via winget")
        result = subprocess.run(
            [
                "winget",
                "install",
                "Gyan.FFmpeg",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent",
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            logger.info("ffmpeg installed successfully via winget")
            # Refresh PATH so we can find it immediately
            _refresh_path()
            return True
        else:
            logger.warning("winget install failed (exit %d): %s", result.returncode, result.stderr)
            return False
    except subprocess.TimeoutExpired:
        logger.error("winget install timed out")
        return False
    except Exception as exc:
        logger.error("winget install error: %s", exc)
        return False


def _refresh_path() -> None:
    """Reload PATH from the Windows registry so newly installed tools are found."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        # User PATH
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            user_path, _ = winreg.QueryValueEx(key, "PATH")

        # System PATH
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            sys_path, _ = winreg.QueryValueEx(key, "Path")

        combined = f"{sys_path};{user_path}"
        os.environ["PATH"] = combined
        logger.debug("PATH refreshed from registry")
    except Exception:
        logger.debug("Could not refresh PATH from registry")


def check_and_install_dependencies(parent_window=None) -> dict[str, bool]:
    """Check all external dependencies and attempt to install missing ones.

    Shows a wx dialog to inform the user and request permission before
    installing anything.

    Args:
        parent_window: Optional wx parent window for dialogs.

    Returns:
        Dict mapping dependency name to availability status (True = OK).
    """
    results: dict[str, bool] = {}

    # ---- ffmpeg ----
    if is_ffmpeg_available():
        results["ffmpeg"] = True
        logger.info("ffmpeg: found")
    else:
        logger.info("ffmpeg: NOT found — attempting install")
        results["ffmpeg"] = _handle_ffmpeg_install(parent_window)

    return results


def _handle_ffmpeg_install(parent_window) -> bool:
    """Guide the user through ffmpeg installation.

    Tries winget first (automatic), then falls back to directing the
    user to download manually.

    Args:
        parent_window: wx parent window for dialogs.

    Returns:
        True if ffmpeg is available after this function.
    """
    import wx

    # Ask permission first
    msg = (
        "BITS Whisperer requires ffmpeg to process audio files.\n\n"
        "ffmpeg is a free, open-source audio tool used by almost every "
        "media application. Without it, audio preprocessing and format "
        "conversion will not work.\n\n"
    )

    if sys.platform == "win32" and _has_winget():
        msg += (
            "We can install ffmpeg automatically using the Windows Package "
            "Manager (winget). This will take about a minute.\n\n"
            "Would you like to install ffmpeg now?"
        )
        dlg = wx.MessageDialog(
            parent_window,
            msg,
            "Install Required Dependency",
            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
        )
        announce_to_screen_reader("ffmpeg is required for audio conversion. Install it now?")
        answer = dlg.ShowModal()
        dlg.Destroy()

        if answer == wx.ID_YES:
            return _install_with_progress(parent_window)
        else:
            # User declined — show manual instructions
            _show_manual_instructions(parent_window)
            return is_ffmpeg_available()
    else:
        _show_manual_instructions(parent_window)
        return is_ffmpeg_available()


def _install_with_progress(parent_window) -> bool:
    """Show a progress dialog while installing ffmpeg via winget.

    Args:
        parent_window: wx parent window.

    Returns:
        True if installed successfully.
    """
    import wx

    progress = wx.ProgressDialog(
        "Installing ffmpeg",
        "Installing ffmpeg via Windows Package Manager…\n" "This may take a minute. Please wait.",
        maximum=100,
        parent=parent_window,
        style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT,
    )
    progress.Pulse()

    import threading

    result_holder: list[bool] = [False]

    def _do_install() -> None:
        result_holder[0] = install_ffmpeg_winget()
        wx.CallAfter(progress.Destroy)

    t = threading.Thread(target=_do_install, daemon=True)
    t.start()

    # Keep the dialog alive while the install runs
    while t.is_alive():
        wx.MilliSleep(200)
        cont, _ = progress.Pulse("Installing ffmpeg… Please wait.")
        if not cont:
            # User pressed Cancel — we can't really cancel winget, but
            # we can stop waiting
            break
        wx.GetApp().Yield()

    t.join(timeout=5)

    if not progress.WasCancelled():
        with contextlib.suppress(Exception):
            progress.Destroy()

    success = result_holder[0]

    # Double-check availability after PATH refresh
    if not success:
        success = is_ffmpeg_available()

    if success:
        accessible_message_box(
            "ffmpeg has been installed successfully!\n\n"
            "Audio processing is now fully available.",
            "Installation Complete",
            wx.OK | wx.ICON_INFORMATION,
            parent_window,
        )
    else:
        accessible_message_box(
            "Automatic installation did not complete successfully.\n\n"
            "You can install ffmpeg manually — see the instructions "
            "in the next dialog.",
            "Installation Issue",
            wx.OK | wx.ICON_WARNING,
            parent_window,
        )
        _show_manual_instructions(parent_window)
        success = is_ffmpeg_available()

    return success


def _show_manual_instructions(parent_window) -> None:
    """Show manual ffmpeg installation instructions.

    Args:
        parent_window: wx parent window.
    """
    import wx

    msg = (
        "To install ffmpeg manually:\n\n"
        "Option 1 — Windows Package Manager (recommended):\n"
        "  Open a Command Prompt or PowerShell and run:\n"
        "  winget install Gyan.FFmpeg\n\n"
        "Option 2 — Direct download:\n"
        "  1. Visit https://www.gyan.dev/ffmpeg/builds/\n"
        '  2. Download "ffmpeg-release-essentials.zip"\n'
        "  3. Extract to C:\\ffmpeg\\\n"
        "  4. Add C:\\ffmpeg\\bin to your system PATH\n\n"
        "Option 3 — Chocolatey:\n"
        "  choco install ffmpeg\n\n"
        "After installing, restart BITS Whisperer."
    )

    dlg = wx.MessageDialog(
        parent_window,
        msg,
        "How to Install ffmpeg",
        wx.OK | wx.ICON_INFORMATION,
    )
    dlg.ShowModal()
    dlg.Destroy()
