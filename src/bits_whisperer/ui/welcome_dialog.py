"""Welcome dialog shown on first launch when no licence or trial is active.

Presents five options:
1. Start a 7-day free trial (collects name + email, registers device)
2. Register with an existing licence key
3. BITS member email verification (free access for @bitsusers.org)
4. Enter a beta invitation code
5. Exit the application

Accessibility: every control has ``SetName()``, keyboard reachable,
``wx.TAB_TRAVERSAL`` on all panels, screen-reader compatible labels.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import wx

from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    label_control,
    set_accessible_name,
)
from bits_whisperer.utils.constants import APP_NAME, APP_VERSION

if TYPE_CHECKING:
    from bits_whisperer.core.beta_service import BetaService
    from bits_whisperer.core.member_verification import MemberVerificationService
    from bits_whisperer.core.registration_service import BITS_RegistrationService

logger = logging.getLogger(__name__)

# Dialog return codes
WELCOME_TRIAL = wx.ID_YES
WELCOME_REGISTER = wx.ID_APPLY
WELCOME_MEMBER = wx.ID_MORE
WELCOME_BETA = wx.ID_FORWARD
WELCOME_EXIT = wx.ID_EXIT

# Simple email validation pattern
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class WelcomeDialog(wx.Dialog):
    """Welcome / activation dialog shown before the main window.

    After ``ShowModal()`` the caller should inspect ``GetReturnCode()``:
    - ``WELCOME_TRIAL``    -- trial started; name/email stored in service
    - ``WELCOME_REGISTER`` -- key entered and stored; caller should verify
    - ``WELCOME_MEMBER``   -- BITS member email verified; app should launch
    - ``WELCOME_BETA``     -- beta invitation verified; app should launch
    - ``WELCOME_EXIT``     -- user chose to quit
    """

    def __init__(
        self,
        parent: wx.Window | None,
        registration_service: BITS_RegistrationService,
        beta_service: BetaService | None = None,
        member_service: MemberVerificationService | None = None,
        activation_mode: str = "beta",
    ) -> None:
        super().__init__(
            parent,
            title=f"Welcome to {APP_NAME}",
            style=wx.DEFAULT_DIALOG_STYLE | wx.TAB_TRAVERSAL,
        )
        self._reg = registration_service  # BITS_RegistrationService
        self._beta = beta_service
        self._member = member_service
        self._activation_mode = activation_mode
        set_accessible_name(self, f"Welcome to {APP_NAME}")

        self._build_ui()
        self.Fit()
        self.SetMinSize((500, 440))
        self.Centre()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(
            panel,
            label=f"Welcome to {APP_NAME} v{APP_VERSION}",
        )
        font = header.GetFont()
        font.SetPointSize(font.GetPointSize() + 4)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header.SetFont(font)
        set_accessible_name(header, f"Welcome to {APP_NAME} version {APP_VERSION}")
        sizer.Add(header, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 15)

        intro = wx.StaticText(
            panel,
            label=(
                "Thank you for choosing BITS Whisperer!\n\n"
                "To get started, please choose one of the options below.\n"
                "You can start a free trial, register, verify your BITS\n"
                "membership, join the beta programme, or exit."
            ),
        )
        set_accessible_name(intro, "Introduction")
        sizer.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        # ---  Card-style notebook for Trial / Register  --- #
        notebook = wx.Notebook(panel, style=wx.NB_TOP)
        set_accessible_name(notebook, "Activation options")

        # -- Trial page -- #
        trial_page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        trial_sizer = wx.BoxSizer(wx.VERTICAL)

        trial_info = wx.StaticText(
            trial_page,
            label=(
                "Start a free 7-day trial. No payment required.\n"
                "Please provide your name and email address so we can\n"
                "register your device."
            ),
        )
        set_accessible_name(trial_info, "Trial information")
        trial_sizer.Add(trial_info, 0, wx.ALL, 10)

        # Name
        name_label = wx.StaticText(trial_page, label="&Full Name:")
        set_accessible_name(name_label, "Full Name label")
        trial_sizer.Add(name_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._trial_name = wx.TextCtrl(trial_page)
        set_accessible_name(self._trial_name, "Full Name")
        label_control(name_label, self._trial_name)
        trial_sizer.Add(self._trial_name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Email
        email_label = wx.StaticText(trial_page, label="&Email Address:")
        set_accessible_name(email_label, "Email Address label")
        trial_sizer.Add(email_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._trial_email = wx.TextCtrl(trial_page)
        set_accessible_name(self._trial_email, "Email Address")
        label_control(email_label, self._trial_email)
        trial_sizer.Add(self._trial_email, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Device ID (read-only) with Copy button
        hw_label = wx.StaticText(trial_page, label="Device &ID:")
        set_accessible_name(hw_label, "Device ID label")
        trial_sizer.Add(hw_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        hw_row = wx.BoxSizer(wx.HORIZONTAL)
        self._hw_token = wx.TextCtrl(
            trial_page,
            value=self._reg.get_device_id(),
            style=wx.TE_READONLY,
        )
        set_accessible_name(self._hw_token, "Device ID, read only")
        label_control(hw_label, self._hw_token)
        hw_row.Add(self._hw_token, 1, wx.RIGHT, 5)
        btn_copy_hw = wx.Button(trial_page, label="&Copy")
        set_accessible_name(btn_copy_hw, "Copy device ID to clipboard")
        btn_copy_hw.Bind(
            wx.EVT_BUTTON,
            lambda _e: self._copy_to_clipboard(self._reg.get_device_id()),
        )
        hw_row.Add(btn_copy_hw, 0)
        trial_sizer.Add(hw_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Start trial button
        self._btn_start_trial = wx.Button(trial_page, label="&Start 7-Day Trial")
        set_accessible_name(self._btn_start_trial, "Start 7-Day Trial")
        trial_sizer.Add(self._btn_start_trial, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)
        self._btn_start_trial.Bind(wx.EVT_BUTTON, self._on_start_trial)

        trial_page.SetSizer(trial_sizer)
        notebook.AddPage(trial_page, "Free Trial")

        # -- Register page -- #
        reg_page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        reg_sizer = wx.BoxSizer(wx.VERTICAL)

        reg_info = wx.StaticText(
            reg_page,
            label=(
                "If you already have a registration key, enter it below.\n"
                "Your key contains your name and licence type which will\n"
                "be verified cryptographically."
            ),
        )
        set_accessible_name(reg_info, "Registration information")
        reg_sizer.Add(reg_info, 0, wx.ALL, 10)

        key_label = wx.StaticText(reg_page, label="Registration &Key:")
        set_accessible_name(key_label, "Registration Key label")
        reg_sizer.Add(key_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._reg_key = wx.TextCtrl(reg_page, style=wx.TE_PASSWORD)
        set_accessible_name(self._reg_key, "Registration Key")
        label_control(key_label, self._reg_key)
        reg_sizer.Add(self._reg_key, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Device ID on register page too (with Copy button)
        hw_label2 = wx.StaticText(reg_page, label="Device &ID:")
        set_accessible_name(hw_label2, "Device ID label")
        reg_sizer.Add(hw_label2, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        hw_row2 = wx.BoxSizer(wx.HORIZONTAL)
        hw_token2 = wx.TextCtrl(
            reg_page,
            value=self._reg.get_device_id(),
            style=wx.TE_READONLY,
        )
        set_accessible_name(hw_token2, "Device ID, read only")
        label_control(hw_label2, hw_token2)
        hw_row2.Add(hw_token2, 1, wx.RIGHT, 5)
        btn_copy_hw2 = wx.Button(reg_page, label="C&opy")
        set_accessible_name(btn_copy_hw2, "Copy device ID to clipboard")
        btn_copy_hw2.Bind(
            wx.EVT_BUTTON,
            lambda _e: self._copy_to_clipboard(self._reg.get_device_id()),
        )
        hw_row2.Add(btn_copy_hw2, 0)
        reg_sizer.Add(hw_row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self._btn_register = wx.Button(reg_page, label="&Register")
        set_accessible_name(self._btn_register, "Register with Key")
        reg_sizer.Add(self._btn_register, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)
        self._btn_register.Bind(wx.EVT_BUTTON, self._on_register)

        reg_page.SetSizer(reg_sizer)
        notebook.AddPage(reg_page, "Register")

        # -- BITS Member page -- #
        member_page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        member_sizer = wx.BoxSizer(wx.VERTICAL)

        member_info = wx.StaticText(
            member_page,
            label=(
                "BITS members with a @bitsusers.org email address\n"
                "receive free access. Enter your email below and we\n"
                "will send you a one-time verification code."
            ),
        )
        set_accessible_name(member_info, "BITS member verification information")
        member_sizer.Add(member_info, 0, wx.ALL, 10)

        member_email_label = wx.StaticText(member_page, label="&Email Address:")
        set_accessible_name(member_email_label, "Email Address label")
        member_sizer.Add(member_email_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._member_email = wx.TextCtrl(member_page)
        set_accessible_name(self._member_email, "BITS member email address")
        label_control(member_email_label, self._member_email)
        member_sizer.Add(self._member_email, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self._btn_send_code = wx.Button(member_page, label="&Send Verification Code")
        set_accessible_name(self._btn_send_code, "Send verification code to your email")
        member_sizer.Add(self._btn_send_code, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        self._btn_send_code.Bind(wx.EVT_BUTTON, self._on_send_member_code)

        # OTP entry (initially hidden)
        otp_label = wx.StaticText(member_page, label="Verification &Code:")
        set_accessible_name(otp_label, "Verification Code label")
        member_sizer.Add(otp_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._member_otp = wx.TextCtrl(member_page)
        set_accessible_name(self._member_otp, "6-digit verification code")
        label_control(otp_label, self._member_otp)
        member_sizer.Add(self._member_otp, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self._btn_verify_member = wx.Button(member_page, label="&Verify Code")
        set_accessible_name(self._btn_verify_member, "Verify the code sent to your email")
        member_sizer.Add(self._btn_verify_member, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        self._btn_verify_member.Bind(wx.EVT_BUTTON, self._on_verify_member_code)

        # Start with OTP fields disabled until email is sent
        self._member_otp.Disable()
        self._btn_verify_member.Disable()

        member_page.SetSizer(member_sizer)
        notebook.AddPage(member_page, "BITS Member")

        # -- Beta Tester page -- #
        beta_page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        beta_sizer = wx.BoxSizer(wx.VERTICAL)

        beta_info = wx.StaticText(
            beta_page,
            label=(
                "If you have a beta invitation code, enter it below\n"
                "to join the BITS Whisperer beta programme and gain\n"
                "access to all features."
            ),
        )
        set_accessible_name(beta_info, "Beta programme information")
        beta_sizer.Add(beta_info, 0, wx.ALL, 10)

        beta_code_label = wx.StaticText(beta_page, label="&Invitation Code:")
        set_accessible_name(beta_code_label, "Invitation Code label")
        beta_sizer.Add(beta_code_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._beta_code = wx.TextCtrl(beta_page)
        set_accessible_name(self._beta_code, "Invitation Code")
        label_control(beta_code_label, self._beta_code)
        beta_sizer.Add(self._beta_code, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self._btn_verify_beta = wx.Button(beta_page, label="&Verify Invitation")
        set_accessible_name(self._btn_verify_beta, "Verify Invitation Code")
        beta_sizer.Add(self._btn_verify_beta, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)
        self._btn_verify_beta.Bind(wx.EVT_BUTTON, self._on_verify_beta)

        beta_page.SetSizer(beta_sizer)
        notebook.AddPage(beta_page, "Beta Tester")

        # Store notebook + page references for activation_mode gating
        self._notebook = notebook
        self._trial_page_idx = 0  # "Free Trial"
        self._reg_page_idx = 1  # "Register"
        self._member_page_idx = 2  # "BITS Member"
        self._beta_page_idx = 3  # "Beta Tester"

        # Gate tabs by admin-controlled activation_mode
        if self._activation_mode == "beta":
            # Beta mode: hide Trial, Register, BITS Member — only Beta Tester
            # Remove in reverse index order to keep indices stable
            notebook.RemovePage(self._member_page_idx)
            notebook.RemovePage(self._reg_page_idx)
            notebook.RemovePage(self._trial_page_idx)
            member_page.Hide()
            reg_page.Hide()
            trial_page.Hide()
        elif self._activation_mode == "closed":
            # Closed mode: hide all tabs — only the exit button is available
            for idx in range(notebook.GetPageCount() - 1, -1, -1):
                notebook.GetPage(idx).Hide()
                notebook.RemovePage(idx)

        sizer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        # -- Exit button -- #
        btn_exit = wx.Button(panel, wx.ID_EXIT, label="E&xit")
        set_accessible_name(btn_exit, "Exit application")
        btn_exit.Bind(wx.EVT_BUTTON, self._on_exit)
        sizer.Add(btn_exit, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        panel.SetSizer(sizer)

        # Close event → same as exit
        self.Bind(wx.EVT_CLOSE, self._on_exit)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy *text* to the system clipboard and announce."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            accessible_message_box(
                "Device ID copied to clipboard.",
                "Copied",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_start_trial(self, _event: wx.CommandEvent) -> None:
        name = self._trial_name.GetValue().strip()
        email = self._trial_email.GetValue().strip()

        if not name:
            accessible_message_box(
                "Please enter your full name.",
                "Name Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._trial_name.SetFocus()
            return

        if not email or not _EMAIL_RE.match(email):
            accessible_message_box(
                "Please enter a valid email address.",
                "Email Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._trial_email.SetFocus()
            return

        ok = self._reg.start_trial(name, email)
        if ok:
            accessible_message_box(
                f"Welcome, {name}!\n\n"
                "Your 7-day trial has been activated.\n"
                "Enjoy all features of BITS Whisperer.",
                "Trial Started",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.EndModal(WELCOME_TRIAL)
        else:
            accessible_message_box(
                "A trial has already been used on this device.\n"
                "Please register with a licence key to continue.",
                "Trial Unavailable",
                wx.OK | wx.ICON_WARNING,
                self,
            )

    def _on_register(self, _event: wx.CommandEvent) -> None:
        key = self._reg_key.GetValue().strip()
        if not key:
            accessible_message_box(
                "Please enter your registration key.",
                "Key Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._reg_key.SetFocus()
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
            self._reg_key.SetFocus()
            return

        # Store the key and trigger verification
        self._reg._key_store.store_key("registration_key", key)
        verified = self._reg.verify_key(force=True)

        if verified:
            name = self._reg.get_registered_name()
            greeting = f"Welcome, {name}!" if name else "Registration successful!"
            status = self._reg.get_status_message()
            accessible_message_box(
                f"{greeting}\n\n{status}\n\nYour licence has been activated on this device.",
                "Registration Successful",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.EndModal(WELCOME_REGISTER)
        else:
            # Clear the invalid key
            self._reg._key_store.delete_key("registration_key")
            accessible_message_box(
                "The registration key could not be verified.\n\n"
                "Please check that you entered it correctly,\n"
                "that you have an internet connection, and that\n"
                "the 3-device limit has not been reached.",
                "Verification Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_exit(self, _event: wx.Event) -> None:
        self.EndModal(WELCOME_EXIT)

    def _on_verify_beta(self, _event: wx.CommandEvent) -> None:
        code = self._beta_code.GetValue().strip()
        if not code:
            accessible_message_box(
                "Please enter your beta invitation code.",
                "Code Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._beta_code.SetFocus()
            return

        if self._beta is None:
            accessible_message_box(
                "Beta verification is not available at this time.\n"
                "Please start a free trial or register instead.",
                "Beta Unavailable",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        verified = self._beta.verify_invitation(code)
        if verified:
            # Also enable beta mode in the service
            self._beta.set_beta_enabled(enabled=True)
            accessible_message_box(
                "Welcome to the BITS Whisperer beta programme!\n\n"
                "Your invitation code has been verified.\n"
                "All features are now unlocked.",
                "Beta Activated",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.EndModal(WELCOME_BETA)
        else:
            accessible_message_box(
                "The invitation code could not be verified.\n\n"
                "Please check that you entered it correctly\n"
                "and that you have an internet connection.",
                "Verification Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_send_member_code(self, _event: wx.CommandEvent) -> None:
        """Send a verification code to the entered BITS member email."""
        email = self._member_email.GetValue().strip()

        if not email or not _EMAIL_RE.match(email):
            accessible_message_box(
                "Please enter a valid email address.",
                "Email Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._member_email.SetFocus()
            return

        if self._member is None:
            accessible_message_box(
                "Member verification is not available at this time.\n"
                "Please use another activation method.",
                "Unavailable",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        if not self._member.is_member_email(email):
            accessible_message_box(
                "This email address is not a BITS member address.\n\n"
                "BITS member emails end with @bitsusers.org.\n"
                "If you are not a BITS member, please use the\n"
                "Free Trial or Register tab instead.",
                "Not a BITS Member Email",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._member_email.SetFocus()
            return

        try:
            otp = self._member.request_verification(email)
        except ValueError as exc:
            accessible_message_box(
                str(exc),
                "Verification Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        # Relay the OTP to the backend for email delivery
        sent = self._member.send_otp_to_backend(email, otp)
        if not sent:
            logger.warning("OTP relay failed for %s***", email[:3])

        # Enable the OTP entry fields
        self._member_otp.Enable()
        self._btn_verify_member.Enable()
        self._member_otp.SetFocus()
        self._btn_send_code.Disable()

        accessible_message_box(
            "A verification code has been sent to your email.\n\n"
            "Please check your inbox (and spam folder) and enter\n"
            "the 6-digit code below.",
            "Code Sent",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_verify_member_code(self, _event: wx.CommandEvent) -> None:
        """Verify the OTP entered by the user."""
        email = self._member_email.GetValue().strip()
        otp = self._member_otp.GetValue().strip()

        if not otp:
            accessible_message_box(
                "Please enter the 6-digit verification code.",
                "Code Required",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._member_otp.SetFocus()
            return

        if self._member is None:
            return

        verified = self._member.verify_otp(email, otp)
        if verified:
            accessible_message_box(
                "Your BITS membership has been verified!\n\n"
                "Welcome — you now have full access to\n"
                "BITS Whisperer.",
                "Member Verified",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.EndModal(WELCOME_MEMBER)
        else:
            accessible_message_box(
                "The verification code is invalid or has expired.\n\n"
                "Please check the code and try again, or request\n"
                "a new code.",
                "Verification Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            # Re-enable send button so user can request a new code
            self._btn_send_code.Enable()
            self._member_otp.SetValue("")
            self._member_otp.SetFocus()
