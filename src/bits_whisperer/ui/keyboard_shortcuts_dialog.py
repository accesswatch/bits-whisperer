"""Keyboard Shortcuts Reference dialog.

Displays a categorised, searchable table of all keyboard shortcuts.
Accessible via Help > Keyboard Shortcuts (Ctrl+Shift+K).

Accessibility
-------------
* Modal ``wx.Dialog`` with full tab traversal.
* ``SearchCtrl`` for filtering shortcuts by name or key.
* ``wx.ListCtrl`` report with Name / Shortcut / Category columns.
* All controls have ``SetName()`` and ``SetHelpText()``.
"""

from __future__ import annotations

import wx

from bits_whisperer.utils.accessibility import (
    announce_to_screen_reader,
    label_control,
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)

_SHORTCUTS: list[tuple[str, str, str]] = [
    # File
    ("Add File to Transcribe", "Ctrl+O", "File"),
    ("Add Folder", "Ctrl+Shift+O", "File"),
    ("Export Transcript", "Ctrl+E", "File"),
    ("Exit", "Alt+F4", "File"),
    # Queue
    ("Start Transcription", "F5", "Queue"),
    ("Pause / Resume", "Ctrl+P", "Queue"),
    ("Cancel Selected", "Del", "Queue"),
    ("Audio Preview Selected", "Ctrl+Alt+P", "Queue"),
    ("Rename Selected", "F2", "Queue"),
    ("Retry All Failed", "Ctrl+Shift+R", "Queue"),
    ("Retry Selected", "Ctrl+R", "Queue"),
    ("Copy Path", "Ctrl+C", "Queue"),
    ("Open File Location", "Ctrl+L", "Queue"),
    # Transcript
    ("Find in Transcript", "Ctrl+F", "Transcript"),
    ("Find Next", "F3", "Transcript"),
    ("Find Previous", "Shift+F3", "Transcript"),
    ("Increase Font Size", "Ctrl++", "Transcript"),
    ("Decrease Font Size", "Ctrl+-", "Transcript"),
    ("Reset Font Size", "Ctrl+0", "Transcript"),
    # AI
    ("Translate Transcript", "Ctrl+T", "AI"),
    ("Summarize Transcript", "Ctrl+Shift+S", "AI"),
    ("Toggle Chat Panel", "Ctrl+Shift+C", "AI"),
    # Tools
    ("Settings", "Ctrl+,", "Tools"),
    ("Manage Models", "Ctrl+M", "Tools"),
    ("Audio Preview", "Ctrl+Shift+P", "Tools"),
    ("Live Transcription", "Ctrl+Alt+L", "Tools"),
    ("Watch Folder Toggle", "Ctrl+W", "Tools"),
    # View / Navigation
    ("Advanced Mode", "Ctrl+Shift+A", "Navigation"),
    ("Next Tab", "Ctrl+Tab", "Navigation"),
    ("Previous Tab", "Ctrl+Shift+Tab", "Navigation"),
    ("Next Pane", "F6", "Navigation"),
    ("Previous Pane", "Shift+F6", "Navigation"),
    # Help
    ("Keyboard Shortcuts", "Ctrl+Shift+K", "Help"),
    ("About", "F1", "Help"),
]


class KeyboardShortcutsDialog(wx.Dialog):
    """Modal reference dialog listing all application keyboard shortcuts.

    Args:
        parent: Parent window.
    """

    def __init__(self, parent: wx.Window | None) -> None:
        super().__init__(
            parent,
            title="Keyboard Shortcuts — BITS Whisperer",
            size=(560, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, "Keyboard shortcuts reference")
        self.SetMinSize((420, 350))
        self.Centre()

        self._all_shortcuts = list(_SHORTCUTS)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        make_panel_accessible(panel, "Keyboard shortcuts")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Search / filter
        filter_label = wx.StaticText(panel, label="&Filter:")
        set_accessible_name(filter_label, "Filter label")
        sizer.Add(filter_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self._search = wx.SearchCtrl(panel, size=(250, -1))
        self._search.SetDescriptiveText("Type to filter shortcuts…")
        set_accessible_name(self._search, "Filter shortcuts")
        set_accessible_help(
            self._search,
            "Type text to filter the shortcuts list by name, key, or category.",
        )
        label_control(filter_label, self._search)
        sizer.Add(self._search, 0, wx.ALL | wx.EXPAND, 10)

        # List
        self._list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES)
        set_accessible_name(self._list, "Shortcuts list")
        set_accessible_help(
            self._list,
            "Table of keyboard shortcuts with columns: Action, Shortcut, Category.",
        )
        self._list.InsertColumn(0, "Action", width=220)
        self._list.InsertColumn(1, "Shortcut", width=140)
        self._list.InsertColumn(2, "Category", width=120)
        sizer.Add(self._list, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        # Close button
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        panel.SetSizer(sizer)

        # Bindings
        self._search.Bind(wx.EVT_TEXT, self._on_filter)
        self.Bind(wx.EVT_BUTTON, self._on_close, id=wx.ID_OK)

    # ------------------------------------------------------------------ #
    # Data                                                                 #
    # ------------------------------------------------------------------ #

    def _populate(self, filter_text: str = "") -> None:
        """Fill the list, optionally filtering by *filter_text*."""
        self._list.DeleteAllItems()
        needle = filter_text.lower()
        shown = 0
        for label, key, cat in self._all_shortcuts:
            if needle and needle not in f"{label} {key} {cat}".lower():
                continue
            idx = self._list.InsertItem(self._list.GetItemCount(), label)
            self._list.SetItem(idx, 1, key)
            self._list.SetItem(idx, 2, cat)
            shown += 1
        if filter_text:
            announce_to_screen_reader(f"{shown} shortcuts match filter")

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_filter(self, event: wx.CommandEvent) -> None:
        self._populate(self._search.GetValue())

    def _on_close(self, _event: wx.CommandEvent) -> None:
        self.EndModal(wx.ID_OK)
