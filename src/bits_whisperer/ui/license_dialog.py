"""Licence management dialog — register, purchase, or revoke a licence.

Accessible from Help → Licence (Ctrl+Shift+L).  Shows current
licence status, registered name, licence type, installation count,
and provides actions to:

1. Register a new key
2. Purchase a licence (opens browser)
3. Revoke this device (frees a device slot)

Accessibility: ``SetName()`` on all controls, keyboard navigation,
``wx.TAB_TRAVERSAL``, screen-reader friendly labels and announcements.
"""

from __future__ import annotations

import logging
import webbrowser
from typing import TYPE_CHECKING

import wx

from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    label_control,
    set_accessible_name,
)
from bits_whisperer.utils.constants import APP_NAME

if TYPE_CHECKING:
    from bits_whisperer.core.registration_service import BITS_RegistrationService

logger = logging.getLogger(__name__)

# Purchase URL — update when storefront is live
_PURCHASE_URL = "https://github.com/BITSWhisperer/bits-whisperer#registration"


class LicenseDialog(wx.Dialog):
    """Licence status and management dialog."""

    def __init__(
        self,
        parent: wx.Window | None,
        registration_service: BITS_RegistrationService,
    ) -> None:
        super().__init__(
            parent,
            title=f"{APP_NAME} — Licence",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL,
        )
        self._reg = registration_service
        set_accessible_name(self, f"{APP_NAME} Licence Management")

        self._build_ui()
        self.Fit()
        self.SetMinSize((480, 520))
        self.Centre()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Status group ---- #
        status_box = wx.StaticBox(panel, label="Licence Status")
        set_accessible_name(status_box, "Licence Status")
        status_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        grid.AddGrowableCol(1, 1)

        # Status
        lbl_status = wx.StaticText(panel, label="Status:")
        set_accessible_name(lbl_status, "Status label")
        grid.Add(lbl_status, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        self._status_value = wx.StaticText(panel, label=self._reg.get_status_message())
        set_accessible_name(self._status_value, "Licence status")
        grid.Add(self._status_value, 1, wx.EXPAND)

        # Registered name
        lbl_name = wx.StaticText(panel, label="Name:")
        set_accessible_name(lbl_name, "Registered name label")
        grid.Add(lbl_name, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        name = self._reg.get_registered_name() or "—"
        self._name_value = wx.StaticText(panel, label=name)
        set_accessible_name(self._name_value, f"Registered name: {name}")
        grid.Add(self._name_value, 1, wx.EXPAND)

        # Email
        lbl_email = wx.StaticText(panel, label="Email:")
        set_accessible_name(lbl_email, "Registered email label")
        grid.Add(lbl_email, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        email = self._reg.get_registered_email() or "—"
        self._email_value = wx.StaticText(panel, label=email)
        set_accessible_name(self._email_value, f"Email: {email}")
        grid.Add(self._email_value, 1, wx.EXPAND)

        # Licence type
        lbl_type = wx.StaticText(panel, label="Type:")
        set_accessible_name(lbl_type, "Licence type label")
        grid.Add(lbl_type, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        type_text = self._licence_type_text()
        self._type_value = wx.StaticText(panel, label=type_text)
        set_accessible_name(self._type_value, f"Licence type: {type_text}")
        grid.Add(self._type_value, 1, wx.EXPAND)

        # Device ID with Copy button
        lbl_device = wx.StaticText(panel, label="Device ID:")
        set_accessible_name(lbl_device, "Device ID label")
        grid.Add(lbl_device, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        device_id = self._reg.get_device_id()
        device_row = wx.BoxSizer(wx.HORIZONTAL)
        self._device_value = wx.StaticText(panel, label=device_id)
        set_accessible_name(self._device_value, f"Device ID: {device_id}")
        device_row.Add(self._device_value, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        btn_copy_device = wx.Button(panel, label="Cop&y", size=(60, -1))
        set_accessible_name(btn_copy_device, "Copy Device ID to clipboard")
        btn_copy_device.Bind(
            wx.EVT_BUTTON,
            lambda _e: self._copy_to_clipboard(device_id),
        )
        device_row.Add(btn_copy_device, 0)
        grid.Add(device_row, 1, wx.EXPAND)

        # Installation count
        lbl_installs = wx.StaticText(panel, label="Installations:")
        set_accessible_name(lbl_installs, "Installation count label")
        grid.Add(lbl_installs, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        count = self._reg.get_install_count()
        installs_text = f"{count} of 3 device slots used"
        self._installs_value = wx.StaticText(panel, label=installs_text)
        set_accessible_name(self._installs_value, f"Installations: {installs_text}")
        grid.Add(self._installs_value, 1, wx.EXPAND)

        # Trial info (if applicable)
        if self._reg.is_trial_active():
            lbl_trial = wx.StaticText(panel, label="Trial:")
            set_accessible_name(lbl_trial, "Trial status label")
            grid.Add(lbl_trial, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
            days = self._reg.get_trial_days_remaining()
            trial_text = f"{days} day{'s' if days != 1 else ''} remaining"
            self._trial_value = wx.StaticText(panel, label=trial_text)
            set_accessible_name(self._trial_value, f"Trial: {trial_text}")
            grid.Add(self._trial_value, 1, wx.EXPAND)

        # Last verified display (for registered users)
        last_verified = self._reg.get_last_verified_display()
        if last_verified:
            lbl_verified = wx.StaticText(panel, label="Verified:")
            set_accessible_name(lbl_verified, "Last verification label")
            grid.Add(lbl_verified, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
            self._verified_value = wx.StaticText(panel, label=last_verified)
            set_accessible_name(self._verified_value, f"Last verified: {last_verified}")
            grid.Add(self._verified_value, 1, wx.EXPAND)

        status_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 10)

        # Trial expiry warning banner
        if self._reg.is_trial_expiring_soon():
            days_left = self._reg.get_trial_days_remaining()
            warn_text = (
                f"Your trial expires in {days_left} day"
                f"{'s' if days_left != 1 else ''}. "
                "Register now to keep using BITS Whisperer."
            )
            self._warn_banner = wx.StaticText(panel, label=warn_text)
            self._warn_banner.SetForegroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
            )
            self._warn_banner.SetBackgroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            )
            set_accessible_name(self._warn_banner, warn_text)
            status_sizer.Add(self._warn_banner, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        main_sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # ---- Actions group ---- #
        action_box = wx.StaticBox(panel, label="Actions")
        set_accessible_name(action_box, "Licence Actions")
        action_sizer = wx.StaticBoxSizer(action_box, wx.VERTICAL)

        # Register key
        reg_sizer = wx.BoxSizer(wx.HORIZONTAL)
        key_label = wx.StaticText(panel, label="Registration &Key:")
        set_accessible_name(key_label, "Registration Key label")
        reg_sizer.Add(key_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._key_input = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        set_accessible_name(self._key_input, "Registration Key")
        label_control(key_label, self._key_input)
        reg_sizer.Add(self._key_input, 1, wx.RIGHT, 5)
        self._btn_register = wx.Button(panel, label="&Register")
        set_accessible_name(self._btn_register, "Register with Key")
        reg_sizer.Add(self._btn_register)
        action_sizer.Add(reg_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Buttons row
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_purchase = wx.Button(panel, label="&Purchase Licence…")
        set_accessible_name(self._btn_purchase, "Purchase a licence — opens browser")
        btn_sizer.Add(self._btn_purchase, 0, wx.RIGHT, 8)

        self._btn_revoke = wx.Button(panel, label="Re&voke This Device")
        set_accessible_name(
            self._btn_revoke,
            "Revoke licence from this device to free a device slot",
        )
        btn_sizer.Add(self._btn_revoke, 0, wx.RIGHT, 8)

        # Only enable revoke if a key is stored
        has_key = self._reg._key_store.has_key("registration_key")
        self._btn_revoke.Enable(has_key)

        action_sizer.Add(btn_sizer, 0, wx.ALL, 8)
        main_sizer.Add(action_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ---- Close button ---- #
        btn_close = wx.Button(panel, wx.ID_CLOSE, label="&Close")
        set_accessible_name(btn_close, "Close")
        main_sizer.Add(btn_close, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)

        # ---- Bindings ---- #
        self._btn_register.Bind(wx.EVT_BUTTON, self._on_register)
        self._btn_purchase.Bind(wx.EVT_BUTTON, self._on_purchase)
        self._btn_revoke.Bind(wx.EVT_BUTTON, self._on_revoke)
        btn_close.Bind(wx.EVT_BUTTON, self._on_close)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _licence_type_text(self) -> str:
        """Map status code to human-readable licence type."""
        code = self._reg._key_store.get_key("registration_status")
        if self._reg.is_trial_active():
            return "7-Day Trial"
        mapping = {
            "L": "Lifetime",
            "A": "Annual Subscription",
            "C": "Contributor",
            "T": "Alpha Tester",
        }
        return mapping.get(code, "Unregistered") if code else "Unregistered"

    def _refresh_status(self) -> None:
        """Refresh all status labels after a state change."""
        self._status_value.SetLabel(self._reg.get_status_message())
        self._name_value.SetLabel(self._reg.get_registered_name() or "—")
        self._email_value.SetLabel(self._reg.get_registered_email() or "—")
        self._type_value.SetLabel(self._licence_type_text())
        count = self._reg.get_install_count()
        self._installs_value.SetLabel(f"{count} of 3 device slots used")
        has_key = self._reg._key_store.has_key("registration_key")
        self._btn_revoke.Enable(has_key)
        self.Layout()

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy *text* to the system clipboard and announce."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            accessible_message_box(
                "Copied to clipboard.",
                "Copied",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_register(self, _event: wx.CommandEvent) -> None:
        key = self._key_input.GetValue().strip()
        if not key:
            accessible_message_box(
                "Please enter your registration key.",
                "Key Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._key_input.SetFocus()
            return

        # Validate key format before contacting the server
        if not self._reg.is_valid_key_format(key):
            accessible_message_box(
                "The registration key format is invalid.\n\n"
                "Keys are at least 32 characters long and contain\n"
                "only letters, digits, and base64 characters (+/=_-).",
                "Invalid Key Format",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._key_input.SetFocus()
            return

        self._reg._key_store.store_key("registration_key", key)
        verified = self._reg.verify_key(force=True)

        if verified:
            name = self._reg.get_registered_name()
            greeting = f"Welcome, {name}!" if name else "Registration successful!"
            accessible_message_box(
                f"{greeting}\n\nYour licence has been activated on this device.",
                "Registration Successful",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self._refresh_status()
        else:
            self._reg._key_store.delete_key("registration_key")
            accessible_message_box(
                "The registration key could not be verified.\n\n"
                "Please check that you entered it correctly, that you\n"
                "have an internet connection, and that the 3-device\n"
                "limit has not been reached.",
                "Verification Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_purchase(self, _event: wx.CommandEvent) -> None:
        webbrowser.open(_PURCHASE_URL)

    def _on_revoke(self, _event: wx.CommandEvent) -> None:
        result = accessible_message_box(
            "Are you sure you want to revoke the licence from this device?\n\n"
            "This will free one of your 3 device slots so you can\n"
            "register a different machine. You will need to re-enter\n"
            "your registration key to use this device again.\n\n"
            "This action cannot be undone.",
            "Confirm Revocation",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if result == wx.YES:
            self._reg.revoke_device()
            accessible_message_box(
                "The licence has been revoked from this device.\n"
                "The device slot will be freed after the next\n"
                "backend sync (within 24 hours).",
                "Device Revoked",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self._refresh_status()

    def _on_close(self, _event: wx.Event) -> None:
        self.EndModal(wx.ID_CLOSE)
