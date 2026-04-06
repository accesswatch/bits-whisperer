"""What's New dialog shown on startup when features change.

Displays a summary of new, enabled, or disabled features along
with optional Markdown release notes fetched from the repository.
Changes are grouped by category: System, Features, and Providers.
Works for both general users, beta testers, and alpha testers.

Accessibility
-------------
* ``wx.Dialog`` with ``SetTitle()`` and ``wx.TAB_TRAVERSAL``.
* All controls have ``SetName()`` and are keyboard-reachable.
* The release notes area is a read-only ``wx.TextCtrl`` with
  multiline scrolling.
* OK button is the default and closes the dialog.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import wx
import wx.adv

from bits_whisperer.utils.accessibility import (
    label_control,
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import APP_VERSION

if TYPE_CHECKING:
    from bits_whisperer.core.beta_service import FeatureChange

logger = logging.getLogger(__name__)


class WhatsNewDialog(wx.Dialog):
    """Modal dialog displaying What's New information on startup.

    Shows a list of feature changes (added, enabled, disabled,
    version update) grouped by category and optional per-feature
    release notes.

    Args:
        parent: Parent window.
        changes: List of :class:`FeatureChange` items to display.
        is_beta: Whether the user is a beta tester.
        is_alpha: Whether the user is an alpha tester.
        release_notes_by_feature: Dict of feature_name -> Markdown
            release notes content.
    """

    def __init__(
        self,
        parent: wx.Window | None,
        changes: list[FeatureChange],
        *,
        is_beta: bool = False,
        is_alpha: bool = False,
        release_notes_by_feature: dict[str, str] | None = None,
    ) -> None:
        title = f"What's New in BITS Whisperer v{APP_VERSION}"
        if is_alpha:
            title += " (Alpha)"
        elif is_beta:
            title += " (Beta)"

        super().__init__(
            parent,
            title=title,
            size=(650, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, title)
        self.SetMinSize((500, 400))
        self.Centre()

        self._changes = changes
        self._is_beta = is_beta
        self._is_alpha = is_alpha
        self._release_notes = release_notes_by_feature or {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the dialog layout."""
        panel = wx.Panel(self)
        make_panel_accessible(panel, "What's New content")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with version
        if self._is_alpha:
            header_text = (
                f"Welcome back, alpha tester! BITS Whisperer v{APP_VERSION} - here's what changed:"
            )
        elif self._is_beta:
            header_text = (
                f"Welcome back, beta tester! BITS Whisperer v{APP_VERSION} - here's what changed:"
            )
        else:
            header_text = (
                f"Here's what's new in BITS Whisperer v{APP_VERSION} "
                "since you last used the application:"
            )

        header = wx.StaticText(panel, label=header_text)
        set_accessible_name(header, "What's New introduction")
        sizer.Add(header, flag=wx.ALL | wx.EXPAND, border=10)

        # Changes list rendered as categorised formatted text
        changes_text = self._format_changes()
        changes_label = wx.StaticText(panel, label="&Changes:")
        set_accessible_name(changes_label, "Changes label")
        sizer.Add(changes_label, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)

        self._changes_ctrl = wx.TextCtrl(
            panel,
            value=changes_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
        )
        set_accessible_name(self._changes_ctrl, "Feature changes list")
        set_accessible_help(
            self._changes_ctrl,
            "Read-only list of features that have been added, enabled, "
            "or disabled since your last session, grouped by category.",
        )
        label_control(changes_label, self._changes_ctrl)
        sizer.Add(
            self._changes_ctrl,
            proportion=1,
            flag=wx.ALL | wx.EXPAND,
            border=10,
        )

        # Release notes section (only if any notes are available)
        if self._release_notes:
            notes_label = wx.StaticText(panel, label="&Release Notes:")
            set_accessible_name(notes_label, "Release notes label")
            sizer.Add(
                notes_label,
                flag=wx.LEFT | wx.RIGHT | wx.TOP,
                border=10,
            )

            combined_notes = self._format_release_notes()
            self._notes_ctrl = wx.TextCtrl(
                panel,
                value=combined_notes,
                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
            )
            set_accessible_name(self._notes_ctrl, "Release notes content")
            set_accessible_help(
                self._notes_ctrl,
                "Detailed release notes for changed features.",
            )
            label_control(notes_label, self._notes_ctrl)
            sizer.Add(
                self._notes_ctrl,
                proportion=1,
                flag=wx.ALL | wx.EXPAND,
                border=10,
            )

        # Don't show again checkbox
        self._dont_show_cb = wx.CheckBox(
            panel,
            label="&Don't show this dialog on startup",
        )
        set_accessible_name(
            self._dont_show_cb,
            "Don't show this dialog on startup",
        )
        set_accessible_help(
            self._dont_show_cb,
            "Check to suppress the What's New dialog on future launches. "
            "You can re-enable it in Settings.",
        )
        sizer.Add(self._dont_show_cb, flag=wx.LEFT | wx.RIGHT, border=10)

        # View Full Changelog link
        self._changelog_link = wx.adv.HyperlinkCtrl(
            panel,
            label="View Full Changelog",
            url="https://github.com/accesswatch/bits-whisperer/blob/main/docs/CHANGELOG.md",
        )
        set_accessible_name(self._changelog_link, "View full changelog on GitHub")
        set_accessible_help(
            self._changelog_link,
            "Opens the complete changelog in your web browser.",
        )
        sizer.Add(self._changelog_link, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)

        # Button row
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK)
        sizer.Add(btn_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)

        panel.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    @property
    def suppress_future(self) -> bool:
        """Whether the user checked 'Don't show again'."""
        return self._dont_show_cb.GetValue()

    def _format_changes(self) -> str:
        """Format the change list as categorised human-readable text."""
        # Group changes by category
        system_changes: list[FeatureChange] = []
        feature_changes: list[FeatureChange] = []
        provider_changes: list[FeatureChange] = []

        for change in self._changes:
            category = getattr(change, "change_category", "feature")
            if category == "system":
                system_changes.append(change)
            elif category == "provider":
                provider_changes.append(change)
            else:
                feature_changes.append(change)

        lines: list[str] = []

        if system_changes:
            lines.append("=== System ===")
            for change in system_changes:
                icon = _change_icon(change.change_type)
                lines.append(f"  {icon} {change.label}")
                if change.description:
                    lines.append(f"      {change.description}")
                lines.append("")

        if feature_changes:
            lines.append("=== Features ===")
            for change in feature_changes:
                icon = _change_icon(change.change_type)
                lines.append(f"  {icon} {change.label}")
                if change.description:
                    lines.append(f"      {change.description}")
                lines.append("")

        if provider_changes:
            lines.append("=== Transcription Providers ===")
            for change in provider_changes:
                icon = _change_icon(change.change_type)
                lines.append(f"  {icon} {change.label}")
                if change.description:
                    lines.append(f"      {change.description}")
                lines.append("")

        return "\n".join(lines).strip()

    def _format_release_notes(self) -> str:
        """Combine release notes from all changed features."""
        parts: list[str] = []
        for change in self._changes:
            notes = self._release_notes.get(change.feature_name, "")
            if notes:
                parts.append(f"--- {change.label} ---\n\n{notes}")
        return "\n\n".join(parts).strip()

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Handle OK button."""
        self.EndModal(wx.ID_OK)


def _change_icon(change_type: str) -> str:
    """Return a text icon for a change type."""
    return {
        "added": "[NEW]",
        "enabled": "[ON]",
        "disabled": "[OFF]",
        "version_update": "[UPDATE]",
    }.get(change_type, "[*]")
