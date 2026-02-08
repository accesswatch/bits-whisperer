"""Accessibility helpers for WXPython controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    pass


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


def announce_status(frame: wx.Frame, message: str, field: int = 0) -> None:
    """Update the status bar text — picked up by screen readers.

    Args:
        frame: The frame containing the status bar.
        message: Text to display and announce.
        field: Status bar field index (default 0).
    """
    status_bar = frame.GetStatusBar()
    if status_bar:
        status_bar.SetStatusText(message, field)


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
