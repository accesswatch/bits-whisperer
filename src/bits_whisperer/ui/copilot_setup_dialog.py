"""GitHub Copilot setup and authentication dialog.

Guides users through:
1. Detecting or installing the Copilot CLI
2. Authenticating with GitHub (login or PAT)
3. Testing the connection
4. Installing the Python SDK if needed
"""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import TYPE_CHECKING

import wx
import wx.adv

from bits_whisperer.core.copilot_service import CopilotService
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    announce_status,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import (
    COPILOT_TIERS,
    format_price_per_1k,
    get_copilot_models_for_tier,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


class CopilotSetupDialog(wx.Dialog):
    """Dialog for setting up GitHub Copilot integration.

    Walks the user through CLI installation, authentication,
    and connection verification in a friendly, guided manner.
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        super().__init__(
            parent,
            title="GitHub Copilot Setup",
            size=(620, 580),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "GitHub Copilot setup wizard")
        self.SetMinSize((500, 460))
        self.Centre()

        self._main_frame = main_frame
        self._key_store = main_frame.key_store
        self._settings = AppSettings.load()

        self._build_ui()
        self._check_status()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
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

        intro_text = (
            "GitHub Copilot provides AI-powered transcript analysis using "
            "models like GPT-4o and Claude. You can ask questions about your "
            "transcripts, get summaries, find topics, and more — all powered "
            "by GitHub's AI infrastructure."
        )
        intro = wx.StaticText(self, label=intro_text)
        intro.Wrap(560)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Scrolled content
        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 20)
        make_panel_accessible(scroll)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        # Step 1: CLI Status
        cli_box = wx.StaticBox(scroll, label="Step 1: Copilot CLI")
        set_accessible_name(cli_box, "Copilot CLI status")
        cli_sizer = wx.StaticBoxSizer(cli_box, wx.VERTICAL)

        self._cli_status = wx.TextCtrl(
            scroll,
            value="Checking...",
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        self._cli_status.SetBackgroundColour(scroll.GetBackgroundColour())
        set_accessible_name(self._cli_status, "CLI installation status")
        cli_sizer.Add(self._cli_status, 0, wx.EXPAND | wx.ALL, 4)

        cli_btn_row = wx.BoxSizer(wx.HORIZONTAL)

        self._install_winget_btn = wx.Button(scroll, label="Install via &WinGet")
        set_accessible_name(
            self._install_winget_btn, "Install Copilot CLI via Windows Package Manager"
        )
        set_accessible_help(
            self._install_winget_btn,
            "Runs: winget install GitHub.Copilot",
        )
        self._install_winget_btn.Bind(wx.EVT_BUTTON, self._on_install_winget)
        cli_btn_row.Add(self._install_winget_btn, 0, wx.RIGHT, 8)

        self._install_npm_btn = wx.Button(scroll, label="Install via &npm")
        set_accessible_name(self._install_npm_btn, "Install Copilot CLI via npm")
        set_accessible_help(
            self._install_npm_btn,
            "Runs: npm install -g @github/copilot",
        )
        self._install_npm_btn.Bind(wx.EVT_BUTTON, self._on_install_npm)
        cli_btn_row.Add(self._install_npm_btn, 0, wx.RIGHT, 8)

        self._recheck_btn = wx.Button(scroll, label="&Recheck")
        set_accessible_name(self._recheck_btn, "Recheck CLI installation")
        self._recheck_btn.Bind(wx.EVT_BUTTON, self._on_recheck)
        cli_btn_row.Add(self._recheck_btn, 0)

        cli_sizer.Add(cli_btn_row, 0, wx.ALL, 4)
        scroll_sizer.Add(cli_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Step 2: SDK Status
        sdk_box = wx.StaticBox(scroll, label="Step 2: Python SDK")
        set_accessible_name(sdk_box, "Python SDK status")
        sdk_sizer = wx.StaticBoxSizer(sdk_box, wx.VERTICAL)

        self._sdk_status = wx.TextCtrl(
            scroll,
            value="Checking...",
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        self._sdk_status.SetBackgroundColour(scroll.GetBackgroundColour())
        set_accessible_name(self._sdk_status, "SDK installation status")
        sdk_sizer.Add(self._sdk_status, 0, wx.EXPAND | wx.ALL, 4)

        self._install_sdk_btn = wx.Button(scroll, label="Install &SDK")
        set_accessible_name(self._install_sdk_btn, "Install GitHub Copilot Python SDK")
        set_accessible_help(
            self._install_sdk_btn,
            "Runs: pip install github-copilot-sdk",
        )
        self._install_sdk_btn.Bind(wx.EVT_BUTTON, self._on_install_sdk)
        sdk_sizer.Add(self._install_sdk_btn, 0, wx.ALL, 4)

        scroll_sizer.Add(sdk_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Step 3: Authentication
        auth_box = wx.StaticBox(scroll, label="Step 3: Authentication")
        set_accessible_name(auth_box, "Authentication configuration")
        auth_sizer = wx.StaticBoxSizer(auth_box, wx.VERTICAL)

        auth_intro = wx.StaticText(
            scroll,
            label=(
                "Choose how to authenticate with GitHub Copilot. "
                "You can use the CLI's built-in login, or provide a "
                "Personal Access Token (PAT) with 'Copilot Requests' permission."
            ),
        )
        auth_intro.Wrap(520)
        auth_sizer.Add(auth_intro, 0, wx.ALL, 4)

        # Auth method selection
        self._auth_login = wx.RadioButton(
            scroll,
            label="Use CLI &login (recommended)",
            style=wx.RB_GROUP,
        )
        set_accessible_name(self._auth_login, "Use CLI login for authentication")
        set_accessible_help(
            self._auth_login,
            "Use the Copilot CLI's built-in login command to authenticate with GitHub",
        )
        auth_sizer.Add(self._auth_login, 0, wx.ALL, 4)

        self._auth_pat = wx.RadioButton(
            scroll,
            label="Use &Personal Access Token (PAT)",
        )
        set_accessible_name(self._auth_pat, "Use Personal Access Token")
        auth_sizer.Add(self._auth_pat, 0, wx.ALL, 4)

        # PAT input
        pat_row = wx.BoxSizer(wx.HORIZONTAL)
        pat_label = wx.StaticText(scroll, label="GitHub &Token:")
        self._pat_input = wx.TextCtrl(scroll, style=wx.TE_PASSWORD, size=(350, -1))
        set_accessible_name(self._pat_input, "GitHub Personal Access Token")
        set_accessible_help(
            self._pat_input,
            "Enter a GitHub PAT with Copilot Requests permission. "
            "Create one at github.com/settings/tokens",
        )
        label_control(pat_label, self._pat_input)

        # Pre-fill from key store
        existing_token = self._key_store.get_key("copilot_github_token")
        if existing_token:
            self._pat_input.SetValue(existing_token)
            self._auth_pat.SetValue(True)

        pat_row.Add(pat_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        pat_row.Add(self._pat_input, 1)
        auth_sizer.Add(pat_row, 0, wx.EXPAND | wx.ALL, 4)

        pat_link = wx.adv.HyperlinkCtrl(
            scroll,
            label="Create a GitHub PAT",
            url="https://github.com/settings/tokens/new?scopes=copilot",
        )
        set_accessible_name(pat_link, "Open GitHub PAT creation page")
        auth_sizer.Add(pat_link, 0, wx.LEFT | wx.BOTTOM, 4)

        scroll_sizer.Add(auth_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Step 4: Test Connection
        test_box = wx.StaticBox(scroll, label="Step 4: Test Connection")
        set_accessible_name(test_box, "Connection test")
        test_sizer = wx.StaticBoxSizer(test_box, wx.VERTICAL)

        self._test_status = wx.TextCtrl(
            scroll,
            value="Not tested yet.",
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        self._test_status.SetBackgroundColour(scroll.GetBackgroundColour())
        set_accessible_name(self._test_status, "Connection test result")
        test_sizer.Add(self._test_status, 0, wx.EXPAND | wx.ALL, 4)

        self._test_btn = wx.Button(scroll, label="&Test Connection")
        set_accessible_name(self._test_btn, "Test Copilot connection")
        self._test_btn.Bind(wx.EVT_BUTTON, self._on_test_connection)
        test_sizer.Add(self._test_btn, 0, wx.ALL, 4)

        scroll_sizer.Add(test_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Model selection (tier-based)
        model_box = wx.StaticBox(scroll, label="Subscription & Model")
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

        # Pre-select current tier
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

        # Model selector (populated by tier)
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

        # Populate initial models based on tier
        self._update_tier_models()

        # Bind changes
        self._tier_choice.Bind(wx.EVT_CHOICE, self._on_tier_changed)
        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)

        scroll_sizer.Add(model_sizer, 0, wx.EXPAND | wx.ALL, 6)

        scroll.SetSizer(scroll_sizer)
        root.Add(scroll, 1, wx.EXPAND | wx.ALL, 4)

        # Buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 4)
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    # ------------------------------------------------------------------ #
    # Status checking                                                      #
    # ------------------------------------------------------------------ #

    def _check_status(self) -> None:
        """Check CLI and SDK installation status."""

        def _check() -> None:
            cli_path = CopilotService.detect_cli()
            cli_version = CopilotService.get_cli_version(cli_path) if cli_path else None
            sdk_available = False
            try:
                import github_copilot  # noqa: F401

                sdk_available = True
            except ImportError:
                pass

            def _update() -> None:
                if cli_path and cli_version:
                    self._cli_status.SetValue(f"Installed: {cli_path}\nVersion: {cli_version}")
                    self._install_winget_btn.Disable()
                    self._install_npm_btn.Disable()
                elif cli_path:
                    self._cli_status.SetValue(f"Found: {cli_path} (version unknown)")
                    self._install_winget_btn.Disable()
                    self._install_npm_btn.Disable()
                else:
                    self._cli_status.SetValue(
                        "Not installed. Install using one of the buttons below."
                    )

                if sdk_available:
                    self._sdk_status.SetValue("Installed and ready.")
                    self._install_sdk_btn.Disable()
                else:
                    self._sdk_status.SetValue("Not installed. Click Install SDK to set it up.")

            safe_call_after(_update)

        threading.Thread(target=_check, daemon=True).start()

    def _on_recheck(self, _event: wx.CommandEvent) -> None:
        """Re-check CLI status."""
        self._cli_status.SetValue("Rechecking...")
        self._install_winget_btn.Enable()
        self._install_npm_btn.Enable()
        self._install_sdk_btn.Enable()
        self._check_status()

    # ------------------------------------------------------------------ #
    # Installation handlers                                                #
    # ------------------------------------------------------------------ #

    def _on_install_winget(self, _event: wx.CommandEvent) -> None:
        """Install Copilot CLI via WinGet."""
        self._install_winget_btn.Disable()
        announce_status(self._main_frame, "Installing Copilot CLI via WinGet...")

        def _install() -> None:
            try:
                result = subprocess.run(
                    ["winget", "install", "GitHub.Copilot", "--accept-source-agreements"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                success = result.returncode == 0

                def _done() -> None:
                    if success:
                        self._cli_status.SetValue("Installation complete. Click Recheck.")
                        announce_status(self._main_frame, "Copilot CLI installed successfully")
                    else:
                        self._cli_status.SetValue(f"Installation failed: {result.stderr[:200]}")
                        self._install_winget_btn.Enable()

                safe_call_after(_done)
            except FileNotFoundError:
                safe_call_after(
                    lambda: self._cli_status.SetValue(
                        "WinGet not found. Try npm or install from github.com/apps/copilot"
                    )
                )
                safe_call_after(self._install_winget_btn.Enable)
            except Exception as exc:
                safe_call_after(lambda e=exc: self._cli_status.SetValue(f"Error: {e}"))
                safe_call_after(self._install_winget_btn.Enable)

        threading.Thread(target=_install, daemon=True).start()

    def _on_install_npm(self, _event: wx.CommandEvent) -> None:
        """Install Copilot CLI via npm."""
        self._install_npm_btn.Disable()
        announce_status(self._main_frame, "Installing Copilot CLI via npm...")

        def _install() -> None:
            try:
                result = subprocess.run(
                    ["npm", "install", "-g", "@github/copilot"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                success = result.returncode == 0

                def _done() -> None:
                    if success:
                        self._cli_status.SetValue("Installation complete. Click Recheck.")
                        announce_status(self._main_frame, "Copilot CLI installed via npm")
                    else:
                        self._cli_status.SetValue(f"Installation failed: {result.stderr[:200]}")
                        self._install_npm_btn.Enable()

                safe_call_after(_done)
            except FileNotFoundError:
                safe_call_after(
                    lambda: self._cli_status.SetValue(
                        "npm not found. Install Node.js first from nodejs.org"
                    )
                )
                safe_call_after(self._install_npm_btn.Enable)
            except Exception as exc:
                safe_call_after(lambda e=exc: self._cli_status.SetValue(f"Error: {e}"))
                safe_call_after(self._install_npm_btn.Enable)

        threading.Thread(target=_install, daemon=True).start()

    def _on_install_sdk(self, _event: wx.CommandEvent) -> None:
        """Install the Python SDK via pip."""
        self._install_sdk_btn.Disable()
        announce_status(self._main_frame, "Installing GitHub Copilot Python SDK...")

        def _install() -> None:
            try:
                result = subprocess.run(
                    ["pip", "install", "github-copilot-sdk"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                success = result.returncode == 0

                def _done() -> None:
                    if success:
                        self._sdk_status.SetValue("SDK installed successfully.")
                        self._install_sdk_btn.Disable()
                        announce_status(self._main_frame, "Copilot SDK installed")
                    else:
                        self._sdk_status.SetValue(f"Failed: {result.stderr[:200]}")
                        self._install_sdk_btn.Enable()

                safe_call_after(_done)
            except Exception as exc:
                safe_call_after(lambda e=exc: self._sdk_status.SetValue(f"Error: {e}"))
                safe_call_after(self._install_sdk_btn.Enable)

        threading.Thread(target=_install, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Connection test                                                      #
    # ------------------------------------------------------------------ #

    def _on_test_connection(self, _event: wx.CommandEvent) -> None:
        """Test the Copilot connection."""
        self._test_btn.Disable()
        self._test_status.SetValue("Testing connection...")
        announce_status(self._main_frame, "Testing Copilot connection...")

        # Save PAT if provided
        pat = self._pat_input.GetValue().strip()
        if pat and self._auth_pat.GetValue():
            self._key_store.store_key("copilot_github_token", pat)

        def _test() -> None:
            try:
                from bits_whisperer.core.ai_service import CopilotAIProvider

                provider = CopilotAIProvider(
                    github_token=pat if self._auth_pat.GetValue() else "",
                )
                valid = provider.validate_key(pat)

                def _done() -> None:
                    if valid:
                        self._test_status.SetValue(
                            "Connection successful! Copilot is ready to use."
                        )
                        announce_status(self._main_frame, "Copilot connection verified")
                    else:
                        self._test_status.SetValue(
                            "Connection failed. Check that the CLI is installed "
                            "and you are authenticated."
                        )
                    self._test_btn.Enable()

                safe_call_after(_done)

            except ImportError:
                safe_call_after(
                    lambda: self._test_status.SetValue(
                        "SDK not installed. Install it first (Step 2)."
                    )
                )
                safe_call_after(self._test_btn.Enable)
            except Exception as exc:
                safe_call_after(lambda e=exc: self._test_status.SetValue(f"Error: {e}"))
                safe_call_after(self._test_btn.Enable)

        threading.Thread(target=_test, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Save & close                                                         #
    # ------------------------------------------------------------------ #

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save settings and close."""
        # Save PAT if provided
        pat = self._pat_input.GetValue().strip()
        if pat and self._auth_pat.GetValue():
            self._key_store.store_key("copilot_github_token", pat)
        elif not self._auth_pat.GetValue():
            # Using CLI login — clear stored PAT
            pass

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
        self._settings.copilot.use_logged_in_user = self._auth_login.GetValue()
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

        # Select current model if available, otherwise first
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
                f"Input: {in_price}  |  Output: {out_price}  |  Context: {ctx}{premium}"
            )
        else:
            self._copilot_pricing_label.SetLabel("")

    def _on_tier_changed(self, _event: wx.CommandEvent) -> None:
        """Handle tier selection change."""
        self._update_tier_models()

    def _on_model_changed(self, _event: wx.CommandEvent) -> None:
        """Handle model selection change."""
        self._update_pricing()
