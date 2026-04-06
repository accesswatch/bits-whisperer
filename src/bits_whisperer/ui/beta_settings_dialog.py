"""Beta programme settings dialog.

Allows users to:

1. Enter and verify a beta invitation code.
2. Toggle beta mode on/off (requires a valid code).
3. View beta status and leave the programme.

Accessibility
-------------
* ``wx.Dialog`` with ``SetTitle()`` and ``wx.TAB_TRAVERSAL``.
* All controls have ``SetName()``, mnemonics, and help text.
* Keyboard-reachable buttons and input field.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx

from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)

if TYPE_CHECKING:
    from bits_whisperer.core.beta_service import BetaService
    from bits_whisperer.core.settings import AppSettings

logger = logging.getLogger(__name__)


class BetaSettingsDialog(wx.Dialog):
    """Dialog for beta programme enrolment and management.

    Args:
        parent: Parent window.
        beta_service: The :class:`BetaService` instance.
        app_settings: The :class:`AppSettings` instance.
    """

    def __init__(
        self,
        parent: wx.Window,
        beta_service: BetaService,
        app_settings: AppSettings,
    ) -> None:
        super().__init__(
            parent,
            title="Beta Programme Settings",
            size=(500, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, "Beta Programme Settings")
        self.SetMinSize((420, 320))
        self.Centre()

        self._beta_service = beta_service
        self._app_settings = app_settings

        self._build_ui()
        self._update_status_display()

    def _build_ui(self) -> None:
        """Construct the dialog layout."""
        panel = wx.Panel(self)
        make_panel_accessible(panel, "Beta programme settings")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Description
        desc = wx.StaticText(
            panel,
            label=(
                "Join the BITS Whisperer beta programme to receive "
                "early access to new features before they are released "
                "publicly. An invitation code is required."
            ),
        )
        set_accessible_name(desc, "Beta programme description")
        desc.Wrap(460)
        sizer.Add(desc, flag=wx.ALL | wx.EXPAND, border=10)

        # Status display
        self._status_label = wx.StaticText(panel, label="Status: Not enrolled")
        set_accessible_name(self._status_label, "Beta programme status")
        sizer.Add(
            self._status_label,
            flag=wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )
        sizer.AddSpacer(10)

        # Invitation code entry
        code_label = wx.StaticText(panel, label="&Invitation Code:")
        set_accessible_name(code_label, "Invitation code label")
        sizer.Add(code_label, flag=wx.LEFT | wx.RIGHT, border=10)

        code_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._code_ctrl = wx.TextCtrl(panel, size=(280, -1))
        set_accessible_name(self._code_ctrl, "Invitation code entry")
        set_accessible_help(
            self._code_ctrl,
            "Enter your beta invitation code. Codes are case-insensitive.",
        )
        label_control(code_label, self._code_ctrl)
        code_sizer.Add(self._code_ctrl, proportion=1, flag=wx.RIGHT, border=5)

        self._verify_btn = wx.Button(panel, label="&Verify")
        set_accessible_name(self._verify_btn, "Verify invitation code")
        set_accessible_help(
            self._verify_btn,
            "Check the entered code against the server. Requires an internet connection.",
        )
        code_sizer.Add(self._verify_btn)
        sizer.Add(code_sizer, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=10)
        sizer.AddSpacer(10)

        # Beta mode checkbox
        self._beta_cb = wx.CheckBox(
            panel,
            label="&Enable Beta Testing Mode",
        )
        set_accessible_name(self._beta_cb, "Enable beta testing mode")
        set_accessible_help(
            self._beta_cb,
            "When checked, you will see beta-only features and receive "
            "early updates. Requires a verified invitation code.",
        )
        self._beta_cb.SetValue(self._app_settings.beta.enabled)
        sizer.Add(self._beta_cb, flag=wx.LEFT | wx.RIGHT, border=10)
        sizer.AddSpacer(5)

        # Show What's New checkbox
        self._whats_new_cb = wx.CheckBox(
            panel,
            label="Show &What's New dialog on startup",
        )
        set_accessible_name(
            self._whats_new_cb,
            "Show What's New dialog on startup",
        )
        set_accessible_help(
            self._whats_new_cb,
            "When checked, you will see a summary of new and changed "
            "features each time the application starts.",
        )
        self._whats_new_cb.SetValue(self._app_settings.beta.show_whats_new)
        sizer.Add(self._whats_new_cb, flag=wx.LEFT | wx.RIGHT, border=10)
        sizer.AddSpacer(10)

        # Alpha testing mode checkbox (internal testers only)
        self._alpha_cb = wx.CheckBox(
            panel,
            label="Enable &Alpha Testing Mode (no registration required)",
        )
        set_accessible_name(
            self._alpha_cb,
            "Enable alpha testing mode",
        )
        set_accessible_help(
            self._alpha_cb,
            "Alpha testing mode bypasses registration verification and "
            "enables all features. Intended for internal testing only. "
            "No invitation code is required.",
        )
        self._alpha_cb.SetValue(self._app_settings.beta.alpha_mode)
        sizer.Add(self._alpha_cb, flag=wx.LEFT | wx.RIGHT, border=10)
        sizer.AddSpacer(10)

        # Leave beta button
        self._leave_btn = wx.Button(panel, label="&Leave Beta Programme")
        set_accessible_name(self._leave_btn, "Leave beta programme")
        set_accessible_help(
            self._leave_btn,
            "Revoke your beta status and return to the general release "
            "channel. Your invitation code will be cleared.",
        )
        sizer.Add(self._leave_btn, flag=wx.LEFT | wx.RIGHT, border=10)
        sizer.AddSpacer(10)

        # Button row
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)

        panel.SetSizer(sizer)

        # Bindings
        self.Bind(wx.EVT_BUTTON, self._on_verify, self._verify_btn)
        self.Bind(wx.EVT_BUTTON, self._on_leave, self._leave_btn)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _update_status_display(self) -> None:
        """Update the status label and enable/disable controls."""
        if self._beta_service.is_invitation_verified:
            self._status_label.SetLabel("Status: Invitation verified ✓")
            self._code_ctrl.Disable()
            self._verify_btn.Disable()
            self._beta_cb.Enable()
            self._leave_btn.Enable()
        else:
            self._status_label.SetLabel("Status: Not enrolled")
            self._code_ctrl.Enable()
            self._verify_btn.Enable()
            self._beta_cb.Disable()
            self._leave_btn.Disable()

    def _on_verify(self, _event: wx.CommandEvent) -> None:
        """Handle the Verify button click — validates the code."""
        code = self._code_ctrl.GetValue().strip()
        if not code:
            accessible_message_box(
                "Please enter your beta invitation code.",
                "Code Required",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self._code_ctrl.SetFocus()
            return

        self._verify_btn.Disable()
        self._code_ctrl.Disable()
        self._verify_btn.SetLabel("Verifying…")

        def _verify() -> None:
            result = self._beta_service.verify_invitation(code)
            safe_call_after(self._on_verify_complete, result)

        threading.Thread(
            target=_verify,
            daemon=True,
            name="beta-verify",
        ).start()

    def _on_verify_complete(self, success: bool) -> None:
        """Handle verification result on the main thread."""
        self._verify_btn.SetLabel("&Verify")

        if success:
            self._beta_cb.SetValue(True)
            accessible_message_box(
                "Your invitation code has been verified! Beta testing mode is now available.",
                "Code Verified",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        else:
            accessible_message_box(
                "The invitation code was not recognised. "
                "Please check your code and try again.\n\n"
                "If you believe this is an error, contact "
                "support@bitswhisperer.com.",
                "Invalid Code",
                wx.OK | wx.ICON_WARNING,
                self,
            )

        self._update_status_display()

    def _on_leave(self, _event: wx.CommandEvent) -> None:
        """Handle Leave Beta Programme button."""
        result = accessible_message_box(
            "Are you sure you want to leave the beta programme?\n\n"
            "Your invitation code will be cleared and you will "
            "return to the general release channel.",
            "Leave Beta Programme",
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if result == wx.YES:
            self._beta_service.revoke_beta()
            self._beta_cb.SetValue(False)
            self._code_ctrl.SetValue("")
            self._update_status_display()

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save settings and close."""
        self._app_settings.beta.enabled = self._beta_cb.GetValue()
        self._app_settings.beta.show_whats_new = self._whats_new_cb.GetValue()
        self._app_settings.beta.alpha_mode = self._alpha_cb.GetValue()
        self._beta_service.set_beta_enabled(self._app_settings.beta.enabled)
        self._beta_service.set_alpha_mode(self._app_settings.beta.alpha_mode)
        self._app_settings.save()
        self.EndModal(wx.ID_OK)
