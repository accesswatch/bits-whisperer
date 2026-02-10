"""GitHub Copilot setup and authentication dialog.

Guides users through a streamlined setup:
1. Sign in with GitHub (browser OAuth or Personal Access Token)
2. Choose subscription tier and model
3. Prerequisites auto-detected and auto-managed

Designed for a "magical" experience — the user clicks Sign In
and everything else happens automatically.
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from typing import TYPE_CHECKING

import wx
import wx.adv

from bits_whisperer.core.github_oauth import (
    DeviceFlowCancelledError,
    DeviceFlowDeniedError,
    DeviceFlowError,
    DeviceFlowExpiredError,
    GitHubDeviceFlow,
)
from bits_whisperer.core.sdk_installer import (
    install_sdk,
    is_sdk_available,
)
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    announce_to_screen_reader,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import (
    COPILOT_TIERS,
    GITHUB_OAUTH_CLIENT_ID,
    format_price_per_1k,
    get_copilot_models_for_tier,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device Flow progress dialog
# ---------------------------------------------------------------------------


class DeviceFlowDialog(wx.Dialog):
    """Modal dialog that guides the user through GitHub OAuth Device Flow.

    Shows the user code, opens the browser, and polls for authorization
    in a background thread.  Closes automatically on success.
    """

    def __init__(self, parent: wx.Window, client_id: str) -> None:
        super().__init__(
            parent,
            title="Sign in with GitHub",
            size=(460, 340),
            style=wx.DEFAULT_DIALOG_STYLE,
        )
        set_accessible_name(self, "Sign in with GitHub via browser")
        self.Centre()

        self._client_id = client_id
        self._cancel_event = threading.Event()
        self._token: str | None = None

        self._build_ui()

        # Start the device flow immediately
        threading.Thread(target=self._run_flow, daemon=True, name="device-flow").start()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        intro = wx.StaticText(
            self,
            label=(
                "To sign in, enter the code below at GitHub.\n"
                "Your browser will open automatically."
            ),
        )
        intro.Wrap(420)
        set_accessible_name(intro, "Sign in instructions")
        sizer.Add(intro, 0, wx.ALL, 12)

        # User code (large, prominent)
        self._code_label = wx.StaticText(self, label="Loading...")
        code_font = self._code_label.GetFont()
        code_font.SetPointSize(code_font.GetPointSize() + 10)
        code_font.SetWeight(wx.FONTWEIGHT_BOLD)
        code_font.SetFamily(wx.FONTFAMILY_TELETYPE)
        self._code_label.SetFont(code_font)
        set_accessible_name(self._code_label, "Your authorization code")
        sizer.Add(self._code_label, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        # Buttons row
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._copy_btn = wx.Button(self, label="&Copy Code")
        set_accessible_name(self._copy_btn, "Copy authorization code to clipboard")
        self._copy_btn.Bind(wx.EVT_BUTTON, self._on_copy_code)
        self._copy_btn.Disable()
        btn_row.Add(self._copy_btn, 0, wx.RIGHT, 8)

        self._open_btn = wx.Button(self, label="Open &Browser")
        set_accessible_name(self._open_btn, "Open GitHub authorization page in browser")
        self._open_btn.Bind(wx.EVT_BUTTON, self._on_open_browser)
        self._open_btn.Disable()
        btn_row.Add(self._open_btn, 0)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        # Status text
        self._status_text = wx.StaticText(self, label="Requesting authorization code...")
        self._status_text.Wrap(420)
        set_accessible_name(self._status_text, "Authorization status")
        sizer.Add(self._status_text, 0, wx.ALL | wx.EXPAND, 12)

        # Progress gauge (indeterminate)
        self._gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        self._gauge.Pulse()
        set_accessible_name(self._gauge, "Authorization progress")
        sizer.Add(self._gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Cancel button
        cancel_btn = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        set_accessible_name(cancel_btn, "Cancel sign in")
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        sizer.Add(cancel_btn, 0, wx.ALIGN_CENTER | wx.ALL, 12)

        self.SetSizer(sizer)
        self.Bind(wx.EVT_CLOSE, self._on_cancel)

    # ------------------------------------------------------------------ #
    # Flow execution (background thread)                                   #
    # ------------------------------------------------------------------ #

    def _run_flow(self) -> None:
        """Run the full device flow in a background thread."""
        try:
            flow = GitHubDeviceFlow(
                client_id=self._client_id,
            )

            # Step 1: Get device code
            info = flow.request_device_code()

            # Update UI with the code
            def _show_code() -> None:
                self._code_label.SetLabel(info.user_code)
                set_accessible_name(
                    self._code_label,
                    f"Your authorization code is {info.user_code}",
                )
                self._status_text.SetLabel(
                    f"Go to {info.verification_uri} and enter the code above.\n"
                    "Waiting for authorization..."
                )
                self._copy_btn.Enable()
                self._open_btn.Enable()
                announce_to_screen_reader(
                    f"Your authorization code is {info.user_code}. "
                    "Your browser will open. Enter this code to sign in."
                )
                self.Layout()

            safe_call_after(_show_code)

            # Auto-open browser
            self._verification_uri = info.verification_uri
            try:
                webbrowser.open(info.verification_uri)
                logger.info("Opened browser to %s", info.verification_uri)
            except Exception as exc:
                logger.warning("Failed to open browser: %s", exc)

            # Step 3: Poll for token
            def _status_update(msg: str) -> None:
                safe_call_after(self._status_text.SetLabel, msg)
                safe_call_after(self._gauge.Pulse)

            token = flow.poll_for_token(
                info,
                on_status=_status_update,
                cancel_event=self._cancel_event,
            )

            # Success!
            self._token = token
            logger.info("Device flow completed — token obtained")

            def _success() -> None:
                self._gauge.SetValue(100)
                self._status_text.SetLabel("Authorized! Closing...")
                announce_to_screen_reader("GitHub authorization successful. Signed in.")
                # Auto-close after a short delay so the user sees the message
                wx.CallLater(1200, self.EndModal, wx.ID_OK)

            safe_call_after(_success)

        except DeviceFlowCancelledError:
            logger.info("Device flow cancelled by user")
            safe_call_after(self.EndModal, wx.ID_CANCEL)

        except DeviceFlowDeniedError as exc:
            logger.warning("Device flow denied: %s", exc)

            def _denied(e=exc) -> None:
                self._gauge.SetValue(0)
                self._status_text.SetLabel(str(e))
                announce_to_screen_reader(str(e))

            safe_call_after(_denied)

        except DeviceFlowExpiredError as exc:
            logger.warning("Device flow expired: %s", exc)

            def _expired(e=exc) -> None:
                self._gauge.SetValue(0)
                self._status_text.SetLabel(f"{e}\nClose this dialog and try again.")
                announce_to_screen_reader(str(e))

            safe_call_after(_expired)

        except DeviceFlowError as exc:
            logger.error("Device flow error: %s", exc)

            def _error(e=exc) -> None:
                self._gauge.SetValue(0)
                self._status_text.SetLabel(f"Error: {e}")
                announce_to_screen_reader(f"Error: {e}")

            safe_call_after(_error)

        except Exception as exc:
            logger.exception("Unexpected error in device flow: %s", exc)

            def _unexpected(e=exc) -> None:
                self._gauge.SetValue(0)
                self._status_text.SetLabel(f"Unexpected error: {e}")
                announce_to_screen_reader(f"Unexpected error: {e}")

            safe_call_after(_unexpected)

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_copy_code(self, _event: wx.CommandEvent) -> None:
        """Copy the user code to the clipboard."""
        code = self._code_label.GetLabel()
        if code and code != "Loading..." and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(code))
            wx.TheClipboard.Close()
            announce_to_screen_reader(f"Copied code {code} to clipboard")
            logger.debug("Copied user code to clipboard")

    def _on_open_browser(self, _event: wx.CommandEvent) -> None:
        """Open the verification URI in the default browser."""
        uri = getattr(self, "_verification_uri", "https://github.com/login/device")
        try:
            webbrowser.open(uri)
            logger.info("Opened browser to %s", uri)
        except Exception as exc:
            logger.warning("Failed to open browser: %s", exc)

    def _on_cancel(self, _event: wx.CommandEvent | wx.CloseEvent) -> None:
        """Cancel the device flow."""
        self._cancel_event.set()
        # Don't EndModal here — the background thread will do it
        # after it sees the cancel event
        logger.debug("Cancel requested for device flow")

    # ------------------------------------------------------------------ #
    # Public result                                                        #
    # ------------------------------------------------------------------ #

    def get_token(self) -> str | None:
        """Return the access token if authorization succeeded."""
        return self._token


# ---------------------------------------------------------------------------
# Status indicators
# ---------------------------------------------------------------------------

_CHECK = "\u2714"  # ✔
_CROSS = "\u2718"  # ✘
_WAIT = "\u23f3"  # ⏳


class CopilotSetupDialog(wx.Dialog):
    """Streamlined GitHub Copilot setup wizard.

    Designed for a "magical" one-click experience:
    - If a built-in OAuth Client ID is configured, browser sign-in
      is the primary action (one click, zero fields to fill).
    - Otherwise, Personal Access Token is primary with a direct
      link to create one on GitHub.
    - SDK installation is automatic and invisible.
    - Connection testing happens automatically after sign-in.
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        super().__init__(
            parent,
            title="GitHub Copilot Setup",
            size=(620, 540),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "GitHub Copilot setup wizard")
        self.SetMinSize((500, 420))
        self.Centre()

        self._main_frame = main_frame
        self._key_store = main_frame.key_store
        self._settings = AppSettings.load()
        self._auth_method = self._settings.copilot.auth_method
        self._has_oauth_client_id = bool(self._get_oauth_client_id())

        self._build_ui()
        self._auto_detect()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        root = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(self, label="GitHub Copilot Integration")
        font = header.GetFont()
        font.SetPointSize(font.GetPointSize() + 4)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header.SetFont(font)
        set_accessible_name(header, "GitHub Copilot Integration")
        root.Add(header, 0, wx.ALL, 12)

        intro = wx.StaticText(
            self,
            label=(
                "GitHub Copilot provides AI-powered transcript analysis using "
                "models like GPT-4o and Claude. Sign in with your GitHub "
                "account to get started."
            ),
        )
        intro.Wrap(560)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Scrolled content
        self._scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self._scroll.SetScrollRate(0, 20)
        make_panel_accessible(self._scroll)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        self._build_auth_section(self._scroll, scroll_sizer)
        self._build_model_section(self._scroll, scroll_sizer)
        self._build_status_section(self._scroll, scroll_sizer)

        self._scroll.SetSizer(scroll_sizer)
        root.Add(self._scroll, 1, wx.EXPAND | wx.ALL, 4)

        # Buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 4)
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _build_auth_section(self, scroll: wx.ScrolledWindow, sizer: wx.BoxSizer) -> None:
        """Build the authentication section.

        Layout depends on whether a built-in OAuth Client ID is available:
        - With Client ID: "Sign In with GitHub" is primary (one click)
        - Without: Personal Access Token is primary (paste a token)
        """
        auth_box = wx.StaticBox(scroll, label="Sign In")
        set_accessible_name(auth_box, "Sign in with GitHub")
        auth_sizer = wx.StaticBoxSizer(auth_box, wx.VERTICAL)

        if self._has_oauth_client_id:
            # ── PRIMARY: Browser sign-in (one click, zero fields) ──
            self._sign_in_btn = wx.Button(scroll, label="&Sign In with GitHub...")
            btn_font = self._sign_in_btn.GetFont()
            btn_font.SetPointSize(btn_font.GetPointSize() + 1)
            self._sign_in_btn.SetFont(btn_font)
            set_accessible_name(
                self._sign_in_btn,
                "Sign in with GitHub. Opens your browser for authentication.",
            )
            set_accessible_help(
                self._sign_in_btn,
                "Opens your browser where you'll enter a short code. "
                "No passwords are entered in this application.",
            )
            self._sign_in_btn.Bind(wx.EVT_BUTTON, self._on_browser_sign_in)
            auth_sizer.Add(self._sign_in_btn, 0, wx.ALL, 8)

            # Auth status
            self._auth_status = wx.StaticText(scroll, label="Checking sign-in status...")
            set_accessible_name(self._auth_status, "Authentication status")
            auth_sizer.Add(self._auth_status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

            # Separator
            auth_sizer.Add(wx.StaticLine(scroll), 0, wx.EXPAND | wx.ALL, 6)

            # SECONDARY: Personal Access Token
            pat_intro = wx.StaticText(scroll, label="Or use a Personal Access Token instead:")
            auth_sizer.Add(pat_intro, 0, wx.LEFT | wx.TOP, 8)
        else:
            # ── PRIMARY: Personal Access Token (no OAuth App registered) ──
            self._sign_in_btn = None  # No browser sign-in available

            pat_guide = wx.StaticText(
                scroll,
                label=(
                    "To connect, create a free Personal Access Token on GitHub "
                    "and paste it below:"
                ),
            )
            pat_guide.Wrap(520)
            auth_sizer.Add(pat_guide, 0, wx.ALL, 8)

            # Step-by-step mini guide
            steps = wx.StaticText(
                scroll,
                label=(
                    "1. Click the link below to open GitHub\n"
                    '2. Click "Generate token" (keep defaults)\n'
                    "3. Copy the token and paste it here"
                ),
            )
            steps.Wrap(520)
            auth_sizer.Add(steps, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

            # Create token link (opens with correct scopes pre-filled)
            create_link = wx.adv.HyperlinkCtrl(
                scroll,
                label="Create a Personal Access Token on GitHub",
                url=(
                    "https://github.com/settings/tokens/new"
                    "?scopes=copilot"
                    "&description=BITS+Whisperer+Copilot"
                ),
            )
            set_accessible_name(
                create_link,
                "Open GitHub to create a Personal Access Token " "with Copilot access",
            )
            auth_sizer.Add(create_link, 0, wx.LEFT | wx.BOTTOM, 8)

            # Auth status
            self._auth_status = wx.StaticText(scroll, label="Checking sign-in status...")
            set_accessible_name(self._auth_status, "Authentication status")
            auth_sizer.Add(self._auth_status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Token input row (present in both modes)
        pat_row = wx.BoxSizer(wx.HORIZONTAL)
        pat_label = wx.StaticText(scroll, label="GitHub &Token:")
        self._pat_input = wx.TextCtrl(scroll, style=wx.TE_PASSWORD, size=(350, -1))
        set_accessible_name(self._pat_input, "GitHub Personal Access Token")
        set_accessible_help(
            self._pat_input,
            "Paste your GitHub Personal Access Token here",
        )
        label_control(pat_label, self._pat_input)

        existing_token = self._key_store.get_key("copilot_github_token")
        if existing_token:
            self._pat_input.SetValue(existing_token)

        pat_row.Add(pat_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        pat_row.Add(self._pat_input, 1)
        auth_sizer.Add(pat_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

        # Save & verify button for PAT
        self._save_token_btn = wx.Button(scroll, label="Save && &Verify Token")
        set_accessible_name(self._save_token_btn, "Save and verify the token")
        set_accessible_help(
            self._save_token_btn,
            "Saves the token securely and verifies it works with GitHub",
        )
        self._save_token_btn.Bind(wx.EVT_BUTTON, self._on_save_verify_token)
        auth_sizer.Add(self._save_token_btn, 0, wx.ALL, 8)

        if self._has_oauth_client_id:
            # Also show the create-token link for OAuth mode
            pat_link = wx.adv.HyperlinkCtrl(
                scroll,
                label="Create a GitHub PAT",
                url=(
                    "https://github.com/settings/tokens/new"
                    "?scopes=copilot"
                    "&description=BITS+Whisperer+Copilot"
                ),
            )
            set_accessible_name(pat_link, "Open GitHub PAT creation page")
            auth_sizer.Add(pat_link, 0, wx.LEFT | wx.BOTTOM, 8)

        sizer.Add(auth_sizer, 0, wx.EXPAND | wx.ALL, 6)

    def _build_model_section(self, scroll: wx.ScrolledWindow, sizer: wx.BoxSizer) -> None:
        """Build the subscription tier and model selection section."""
        model_box = wx.StaticBox(scroll, label="Subscription && Model")
        set_accessible_name(model_box, "Subscription tier and model selection")
        model_sizer = wx.StaticBoxSizer(model_box, wx.VERTICAL)

        # Tier selector
        tier_row = wx.BoxSizer(wx.HORIZONTAL)
        tier_label = wx.StaticText(scroll, label="&Tier:")
        tier_choices = [f"{v['name']} — {v['price']}" for v in COPILOT_TIERS.values()]
        self._tier_choice = wx.Choice(scroll, choices=tier_choices)
        set_accessible_name(self._tier_choice, "Select your Copilot subscription tier")
        set_accessible_help(
            self._tier_choice,
            "Choose your GitHub Copilot plan. Higher tiers unlock more models.",
        )
        label_control(tier_label, self._tier_choice)

        current_tier = self._settings.copilot.subscription_tier
        tier_keys = list(COPILOT_TIERS.keys())
        tier_idx = tier_keys.index(current_tier) if current_tier in tier_keys else 1
        self._tier_choice.SetSelection(tier_idx)

        tier_row.Add(tier_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        tier_row.Add(self._tier_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        model_sizer.Add(tier_row, 0, wx.EXPAND | wx.ALL, 4)

        self._tier_desc = wx.StaticText(scroll, label="")
        set_accessible_name(self._tier_desc, "Tier description")
        model_sizer.Add(self._tier_desc, 0, wx.LEFT | wx.BOTTOM, 8)

        # Model selector
        model_row = wx.BoxSizer(wx.HORIZONTAL)
        model_label = wx.StaticText(scroll, label="&Model:")
        self._model_choice = wx.Choice(scroll)
        set_accessible_name(self._model_choice, "Select default Copilot model")
        set_accessible_help(
            self._model_choice,
            "The AI model to use for Copilot chat sessions",
        )
        label_control(model_label, self._model_choice)

        model_row.Add(model_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        model_row.Add(self._model_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        model_sizer.Add(model_row, 0, wx.EXPAND | wx.ALL, 4)

        # Pricing info
        self._copilot_pricing_label = wx.StaticText(scroll, label="")
        set_accessible_name(self._copilot_pricing_label, "Model pricing")
        model_sizer.Add(self._copilot_pricing_label, 0, wx.LEFT | wx.BOTTOM, 8)

        # Populate models and bind events
        self._update_tier_models()
        self._tier_choice.Bind(wx.EVT_CHOICE, self._on_tier_changed)
        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)

        sizer.Add(model_sizer, 0, wx.EXPAND | wx.ALL, 6)

    def _build_status_section(self, scroll: wx.ScrolledWindow, sizer: wx.BoxSizer) -> None:
        """Build the read-only status summary at the bottom.

        Shows at a glance whether everything is ready.
        """
        status_box = wx.StaticBox(scroll, label="Status")
        set_accessible_name(status_box, "Copilot readiness status")
        status_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)

        # SDK status line
        self._sdk_status = wx.StaticText(scroll, label=f"{_WAIT}  Copilot SDK: Checking...")
        set_accessible_name(self._sdk_status, "SDK status")
        status_sizer.Add(self._sdk_status, 0, wx.ALL, 4)

        # Auth status line (mirrors the auth section status)
        self._status_auth = wx.StaticText(scroll, label=f"{_WAIT}  Authentication: Checking...")
        set_accessible_name(self._status_auth, "Authentication status summary")
        status_sizer.Add(self._status_auth, 0, wx.ALL, 4)

        # Connection status line
        self._status_connection = wx.StaticText(
            scroll, label=f"{_WAIT}  Connection: Not tested yet"
        )
        set_accessible_name(self._status_connection, "Connection status")
        status_sizer.Add(self._status_connection, 0, wx.ALL, 4)

        sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 6)

    # ------------------------------------------------------------------ #
    # Auto-detection                                                       #
    # ------------------------------------------------------------------ #

    def _auto_detect(self) -> None:
        """Auto-detect SDK and auth state in background.

        Called on dialog open and after install/auth operations.
        Updates all status labels automatically.
        """
        logger.info("Auto-detecting Copilot prerequisites and auth state...")

        def _check() -> None:
            sdk_available = is_sdk_available("copilot_sdk")

            # Check existing token
            token = self._key_store.get_key("copilot_github_token")
            user_info = None
            if token:
                user_info = GitHubDeviceFlow.validate_token(token)

            logger.info(
                "Auto-detect: sdk=%s, has_token=%s, user=%s",
                sdk_available,
                bool(token),
                user_info.get("login") if user_info else None,
            )

            def _update() -> None:
                # ── SDK status ──
                if sdk_available:
                    self._sdk_status.SetLabel(f"{_CHECK}  Copilot SDK: Ready")
                else:
                    self._sdk_status.SetLabel(
                        f"{_CROSS}  Copilot SDK: Not installed " "(will install automatically)"
                    )

                # ── Auth status ──
                if user_info:
                    name = user_info.get("name") or user_info.get("login", "unknown")
                    self._auth_status.SetLabel(f"Signed in as {name}")
                    self._status_auth.SetLabel(f"{_CHECK}  Authentication: Signed in as {name}")
                    if self._sign_in_btn:
                        self._sign_in_btn.SetLabel("&Sign In Again / Switch Account...")
                    announce_to_screen_reader(f"Signed in as {name}")
                elif token:
                    self._auth_status.SetLabel("Token saved (could not verify — may be offline)")
                    self._status_auth.SetLabel(f"{_CHECK}  Authentication: Token saved")
                else:
                    self._auth_status.SetLabel("Not signed in yet")
                    self._status_auth.SetLabel(f"{_CROSS}  Authentication: Not signed in")

                # ── Connection status ──
                if user_info and sdk_available:
                    self._status_connection.SetLabel(f"{_CHECK}  Connection: Ready")
                elif user_info or token:
                    if not sdk_available:
                        self._status_connection.SetLabel(
                            f"{_WAIT}  Connection: SDK will install on first use"
                        )
                    else:
                        self._status_connection.SetLabel(f"{_WAIT}  Connection: Not verified")
                else:
                    self._status_connection.SetLabel(f"{_CROSS}  Connection: Sign in first")

                self._scroll.FitInside()
                self.Layout()

            safe_call_after(_update)

        threading.Thread(target=_check, daemon=True, name="copilot-detect").start()

    # ------------------------------------------------------------------ #
    # OAuth helpers                                                        #
    # ------------------------------------------------------------------ #

    def _get_oauth_client_id(self) -> str:
        """Get the OAuth client ID from constant or settings."""
        if GITHUB_OAUTH_CLIENT_ID:
            return GITHUB_OAUTH_CLIENT_ID
        if self._settings.copilot.oauth_client_id:
            return self._settings.copilot.oauth_client_id
        return ""

    def _on_browser_sign_in(self, _event: wx.CommandEvent) -> None:
        """Start the GitHub OAuth Device Flow via browser.

        Only available when a built-in OAuth Client ID is configured.
        """
        client_id = self._get_oauth_client_id()
        if not client_id:
            # This shouldn't happen if _has_oauth_client_id was checked
            logger.error("Browser sign-in attempted without client ID")
            return

        logger.info("Starting browser sign-in via OAuth Device Flow")
        self._sign_in_btn.Disable()
        self._auth_status.SetLabel("Starting sign-in...")

        # Auto-install SDK in background if needed (non-blocking)
        self._ensure_sdk_installed()

        dlg = DeviceFlowDialog(self, client_id)
        result = dlg.ShowModal()

        if result == wx.ID_OK:
            token = dlg.get_token()
            if token:
                self._store_token_and_update(token, method="browser_oauth")
                logger.info("Browser sign-in completed — token stored")
        else:
            self._auth_status.SetLabel("Sign-in cancelled")
            announce_to_screen_reader("Sign-in cancelled")
            logger.info("Browser sign-in cancelled or failed")

        dlg.Destroy()
        if self._sign_in_btn:
            self._sign_in_btn.Enable()

    def _on_save_verify_token(self, _event: wx.CommandEvent) -> None:
        """Save and verify the PAT entered by the user."""
        pat = self._pat_input.GetValue().strip()
        if not pat:
            accessible_message_box(
                "Please paste your GitHub Personal Access Token first.",
                "Token Required",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self._pat_input.SetFocus()
            return

        self._save_token_btn.Disable()
        self._save_token_btn.SetLabel("Verifying...")
        self._auth_status.SetLabel("Verifying token...")
        announce_to_screen_reader("Verifying your GitHub token, please wait")

        def _verify() -> None:
            user_info = GitHubDeviceFlow.validate_token(pat)

            def _done() -> None:
                if user_info:
                    self._store_token_and_update(pat, method="pat")
                    announce_to_screen_reader(
                        f"Token verified! Signed in as "
                        f"{user_info.get('name') or user_info.get('login')}"
                    )
                else:
                    self._auth_status.SetLabel(
                        "Could not verify token — check it's correct " "and has Copilot scope"
                    )
                    self._status_auth.SetLabel(f"{_CROSS}  Authentication: Token invalid")
                    announce_to_screen_reader(
                        "Token could not be verified. "
                        "Make sure it's correct and has Copilot scope."
                    )
                self._save_token_btn.SetLabel("Save && &Verify Token")
                self._save_token_btn.Enable()
                self._scroll.FitInside()
                self.Layout()

            safe_call_after(_done)

        threading.Thread(target=_verify, daemon=True, name="verify-token").start()

    def _store_token_and_update(self, token: str, method: str = "pat") -> None:
        """Store a verified token and update all UI elements.

        Args:
            token: The access token to store.
            method: Auth method ("browser_oauth" or "pat").
        """
        # Store securely
        self._key_store.store_key("copilot_github_token", token)
        self._pat_input.SetValue(token)
        self._auth_method = method

        # Validate to get user info
        user_info = GitHubDeviceFlow.validate_token(token)
        if user_info:
            name = user_info.get("name") or user_info.get("login", "")
            self._auth_status.SetLabel(f"Signed in as {name}")
            self._status_auth.SetLabel(f"{_CHECK}  Authentication: Signed in as {name}")
            if self._sign_in_btn:
                self._sign_in_btn.SetLabel("&Sign In Again / Switch Account...")
        else:
            self._auth_status.SetLabel("Signed in (token stored)")
            self._status_auth.SetLabel(f"{_CHECK}  Authentication: Token saved")

        # Update connection status
        sdk_available = is_sdk_available("copilot_sdk")
        if sdk_available:
            self._status_connection.SetLabel(f"{_CHECK}  Connection: Ready")
        else:
            self._status_connection.SetLabel(f"{_WAIT}  Connection: SDK will install on first use")

        # Auto-install SDK in background if needed
        self._ensure_sdk_installed()

        self._scroll.FitInside()
        self.Layout()

    # ------------------------------------------------------------------ #
    # Automatic SDK installation                                           #
    # ------------------------------------------------------------------ #

    def _ensure_sdk_installed(self) -> None:
        """Install the SDK in the background if not already available.

        This is called automatically — the user never needs to click
        an "Install SDK" button.
        """
        if is_sdk_available("copilot_sdk"):
            return

        logger.info("SDK not installed — starting automatic installation")
        self._sdk_status.SetLabel(f"{_WAIT}  Copilot SDK: Installing automatically...")
        announce_status(self._main_frame, "Installing GitHub Copilot SDK...")

        def _install() -> None:
            try:
                success, error = install_sdk("copilot_sdk")

                def _done() -> None:
                    if success:
                        sdk_ok = is_sdk_available("copilot_sdk")
                        if sdk_ok:
                            self._sdk_status.SetLabel(f"{_CHECK}  Copilot SDK: Ready")
                            announce_status(self._main_frame, "Copilot SDK installed")
                            announce_to_screen_reader("Copilot SDK installed successfully")
                            # Update connection status
                            token = self._key_store.get_key("copilot_github_token")
                            if token:
                                self._status_connection.SetLabel(f"{_CHECK}  Connection: Ready")
                            logger.info("SDK auto-installed and verified")
                        else:
                            self._sdk_status.SetLabel(
                                f"{_WAIT}  Copilot SDK: Installed — " "restart app to activate"
                            )
                            announce_to_screen_reader(
                                "SDK installed. Restart the application " "to use it."
                            )
                            logger.warning(
                                "SDK install OK but import fails. " "Python exe: %s",
                                sys.executable,
                            )
                    else:
                        self._sdk_status.SetLabel(
                            f"{_CROSS}  Copilot SDK: Install failed — "
                            f"{error[:200] if error else 'unknown error'}"
                        )
                        announce_to_screen_reader("Copilot SDK installation failed")
                        logger.error("SDK install failed: %s", error)

                    self._scroll.FitInside()
                    self.Layout()

                safe_call_after(_done)
            except Exception as exc:
                logger.exception("SDK auto-install failed: %s", exc)

                def _err(e: Exception = exc) -> None:
                    self._sdk_status.SetLabel(f"{_CROSS}  Copilot SDK: Error — {e}")
                    self._scroll.FitInside()
                    self.Layout()

                safe_call_after(_err)

        threading.Thread(target=_install, daemon=True, name="sdk-auto-install").start()

    # ------------------------------------------------------------------ #
    # Save & close                                                         #
    # ------------------------------------------------------------------ #

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save settings and close."""
        # Save token if entered
        pat = self._pat_input.GetValue().strip()
        if pat:
            self._key_store.store_key("copilot_github_token", pat)
            self._settings.copilot.auth_method = self._auth_method
            self._settings.copilot.use_logged_in_user = False
        else:
            self._settings.copilot.auth_method = "cli_login"
            self._settings.copilot.use_logged_in_user = True

        # Save model selection
        model_idx = self._model_choice.GetSelection()
        if model_idx >= 0:
            model = self._model_choice.GetString(model_idx)
            self._settings.copilot.default_model = model
            self._settings.ai.copilot_model = model

        # Save subscription tier
        tier_idx = self._tier_choice.GetSelection()
        if tier_idx >= 0:
            tier_keys = list(COPILOT_TIERS.keys())
            self._settings.copilot.subscription_tier = tier_keys[tier_idx]

        # Enable Copilot
        self._settings.copilot.enabled = True
        self._settings.save()

        announce_status(self._main_frame, "Copilot setup saved")
        self.EndModal(wx.ID_OK)

    # ------------------------------------------------------------------ #
    # Tier / model helpers                                                 #
    # ------------------------------------------------------------------ #

    def _update_tier_models(self) -> None:
        """Populate model list based on current tier selection."""
        sel = self._tier_choice.GetSelection()
        if sel < 0:
            return

        tier_keys = list(COPILOT_TIERS.keys())
        tier = tier_keys[sel]
        tier_info = COPILOT_TIERS[tier]
        self._tier_desc.SetLabel(tier_info["description"])

        available = get_copilot_models_for_tier(tier)
        self._model_choice.Clear()
        for m in available:
            self._model_choice.Append(m.id)

        current_model = self._settings.copilot.default_model
        idx = self._model_choice.FindString(current_model)
        self._model_choice.SetSelection(idx if idx != wx.NOT_FOUND else 0)
        self._update_pricing()

    def _update_pricing(self) -> None:
        """Update pricing label for the currently selected model."""
        sel = self._model_choice.GetSelection()
        if sel < 0:
            return

        model_id = self._model_choice.GetString(sel)
        from bits_whisperer.utils.constants import get_ai_model_by_id

        model_info = get_ai_model_by_id(model_id, "copilot")
        if model_info:
            in_price = format_price_per_1k(model_info.input_price_per_1m)
            out_price = format_price_per_1k(model_info.output_price_per_1m)
            ctx = f"{model_info.context_window:,} tokens"
            premium = "  (Premium)" if model_info.is_premium else ""
            self._copilot_pricing_label.SetLabel(
                f"Input: {in_price}  |  Output: {out_price}" f"  |  Context: {ctx}{premium}"
            )
        else:
            self._copilot_pricing_label.SetLabel("")

    def _on_tier_changed(self, _event: wx.CommandEvent) -> None:
        """Handle tier selection change."""
        self._update_tier_models()

    def _on_model_changed(self, _event: wx.CommandEvent) -> None:
        """Handle model selection change."""
        self._update_pricing()
