"""AI provider settings dialog for configuring translation/summarization.

Allows users to add API keys for OpenAI, Anthropic (Claude), and
Azure OpenAI, and configure default preferences for AI features.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    announce_status,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# AI provider definitions
_AI_PROVIDERS = [
    {
        "id": "openai",
        "name": "OpenAI (GPT-4o)",
        "description": "OpenAI's GPT-4o and GPT-4o-mini models for translation and summarization.",
        "key_id": "openai",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "openai", "password": True},
        ],
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "description": "Anthropic's Claude models for high-quality translation and summarization.",
        "key_id": "anthropic",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "anthropic", "password": True},
        ],
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
            "claude-3-5-sonnet-20241022",
        ],
    },
    {
        "id": "azure_openai",
        "name": "Azure OpenAI (Copilot)",
        "description": (
            "Microsoft Azure OpenAI Service. Use your Azure OpenAI deployment "
            "for enterprise-grade AI features. Compatible with Copilot infrastructure."
        ),
        "key_id": "azure_openai",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "azure_openai", "password": True},
            {
                "id": "endpoint",
                "label": "Endpoint URL",
                "key_name": "azure_openai_endpoint",
                "password": False,
            },
            {
                "id": "deployment",
                "label": "Deployment Name",
                "key_name": "azure_openai_deployment",
                "password": False,
            },
        ],
        "models": [],
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "description": (
            "Google's Gemini AI models for high-quality translation and "
            "summarization. Requires a Google AI Studio API key."
        ),
        "key_id": "gemini",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "gemini", "password": True},
        ],
        "models": ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"],
    },
    {
        "id": "copilot",
        "name": "GitHub Copilot",
        "description": (
            "GitHub Copilot-powered AI via the Copilot CLI. Requires a GitHub "
            "account with Copilot access. Use AI > Copilot Setup for installation."
        ),
        "key_id": "copilot",
        "fields": [
            {
                "id": "api_key",
                "label": "GitHub Token (PAT)",
                "key_name": "copilot_github_token",
                "password": True,
            },
        ],
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-sonnet-4", "claude-haiku-4"],
    },
]


class AISettingsDialog(wx.Dialog):
    """Dialog for configuring AI provider API keys and preferences.

    Allows users to:
    - Add/remove API keys for AI providers
    - Select the default AI provider
    - Configure translation target language
    - Configure summarization style
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        """Initialise the AI settings dialog.

        Args:
            parent: Parent window.
            main_frame: Reference to the main frame.
        """
        super().__init__(
            parent,
            title="AI Provider Settings",
            size=(600, 550),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "AI Provider Settings")
        self.SetMinSize((480, 420))
        self.Centre()

        self._main_frame = main_frame
        self._settings = AppSettings.load()
        self._key_store = main_frame.key_store
        self._fields: dict[str, wx.TextCtrl] = {}

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        root = wx.BoxSizer(wx.VERTICAL)

        notebook = wx.Notebook(self)
        set_accessible_name(notebook, "AI settings tabs")

        # -- Providers tab --
        providers_panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        providers_panel.SetScrollRate(0, 20)
        make_panel_accessible(providers_panel)
        self._build_providers_tab(providers_panel)
        notebook.AddPage(providers_panel, "Providers")

        # -- Preferences tab --
        prefs_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(prefs_panel)
        self._build_preferences_tab(prefs_panel)
        notebook.AddPage(prefs_panel, "Preferences")

        root.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)

        # -- Buttons --
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 4)
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)

        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _build_providers_tab(self, parent: wx.ScrolledWindow) -> None:
        """Build the providers configuration tab.

        Args:
            parent: Parent scrolled window.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        instructions = wx.StaticText(
            parent,
            label=(
                "Configure API keys for AI providers used for translation "
                "and summarization. At least one provider must be configured "
                "to use AI features."
            ),
        )
        instructions.Wrap(520)
        set_accessible_name(instructions, "Instructions")
        sizer.Add(instructions, 0, wx.ALL, 10)

        # Default provider selector
        provider_row = wx.BoxSizer(wx.HORIZONTAL)
        provider_label = wx.StaticText(parent, label="&Default Provider:")
        set_accessible_name(provider_label, "Default AI provider")
        provider_row.Add(provider_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        provider_names = [p["name"] for p in _AI_PROVIDERS]
        self._provider_choice = wx.Choice(parent, choices=provider_names)
        set_accessible_name(self._provider_choice, "Select default AI provider")
        provider_row.Add(self._provider_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(provider_row, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        sizer.AddSpacer(10)

        # Provider fields
        for provider in _AI_PROVIDERS:
            box = wx.StaticBox(parent, label=provider["name"])
            set_accessible_name(box, provider["name"])
            box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

            desc = wx.StaticText(parent, label=provider["description"])
            desc.Wrap(480)
            box_sizer.Add(desc, 0, wx.ALL, 5)

            grid = wx.FlexGridSizer(cols=3, vgap=6, hgap=8)
            grid.AddGrowableCol(1, 1)

            for field_def in provider["fields"]:
                lbl = wx.StaticText(parent, label=f"{field_def['label']}:")
                set_accessible_name(lbl, field_def["label"])
                grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)

                style = wx.TE_PASSWORD if field_def.get("password") else 0
                txt = wx.TextCtrl(parent, style=style, size=(250, -1))
                field_id = f"{provider['id']}_{field_def['id']}"
                set_accessible_name(
                    txt, f"{field_def['label']} for {provider['name']}"
                )
                grid.Add(txt, 1, wx.EXPAND)
                self._fields[field_id] = txt

                # Validate button for API keys
                if field_def.get("password"):
                    validate_btn = wx.Button(parent, label="Validate")
                    set_accessible_name(
                        validate_btn,
                        f"Validate {provider['name']} API key",
                    )
                    validate_btn.Bind(
                        wx.EVT_BUTTON,
                        lambda evt, pid=provider["id"]: self._on_validate(pid),
                    )
                    grid.Add(validate_btn, 0)
                else:
                    grid.AddSpacer(0)

            box_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 5)

            # Model selector for providers with model choices
            if provider.get("models"):
                model_row = wx.BoxSizer(wx.HORIZONTAL)
                model_lbl = wx.StaticText(parent, label="Model:")
                set_accessible_name(model_lbl, f"{provider['name']} model")
                model_row.Add(model_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

                model_choice = wx.Choice(parent, choices=provider["models"])
                model_field_id = f"{provider['id']}_model"
                set_accessible_name(model_choice, f"Select {provider['name']} model")
                model_row.Add(model_choice, 1, wx.ALIGN_CENTER_VERTICAL)
                self._fields[model_field_id] = model_choice  # type: ignore[assignment]
                box_sizer.Add(model_row, 0, wx.ALL | wx.EXPAND, 5)

            sizer.Add(box_sizer, 0, wx.ALL | wx.EXPAND, 5)

        parent.SetSizer(sizer)

    def _build_preferences_tab(self, parent: wx.Panel) -> None:
        """Build the AI preferences tab.

        Args:
            parent: Parent panel.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Translation settings
        trans_box = wx.StaticBox(parent, label="Translation")
        set_accessible_name(trans_box, "Translation settings")
        trans_sizer = wx.StaticBoxSizer(trans_box, wx.VERTICAL)

        lang_row = wx.BoxSizer(wx.HORIZONTAL)
        lang_label = wx.StaticText(parent, label="&Target Language:")
        set_accessible_name(lang_label, "Translation target language")
        lang_row.Add(lang_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        languages = [
            "English",
            "Spanish",
            "French",
            "German",
            "Italian",
            "Portuguese",
            "Chinese",
            "Japanese",
            "Korean",
            "Russian",
            "Arabic",
            "Hindi",
            "Dutch",
            "Swedish",
            "Polish",
        ]
        self._lang_choice = wx.Choice(parent, choices=languages)
        set_accessible_name(self._lang_choice, "Select translation target language")
        set_accessible_help(
            self._lang_choice,
            "The language to translate transcripts into",
        )
        self._lang_choice.SetSelection(0)
        lang_row.Add(self._lang_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        trans_sizer.Add(lang_row, 0, wx.ALL | wx.EXPAND, 8)

        sizer.Add(trans_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Summarization settings
        summ_box = wx.StaticBox(parent, label="Summarization")
        set_accessible_name(summ_box, "Summarization settings")
        summ_sizer = wx.StaticBoxSizer(summ_box, wx.VERTICAL)

        style_row = wx.BoxSizer(wx.HORIZONTAL)
        style_label = wx.StaticText(parent, label="&Summary Style:")
        set_accessible_name(style_label, "Summary style")
        style_row.Add(style_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        styles = ["Concise (3-5 sentences)", "Detailed", "Bullet Points"]
        self._style_choice = wx.Choice(parent, choices=styles)
        set_accessible_name(self._style_choice, "Select summarization style")
        self._style_choice.SetSelection(0)
        style_row.Add(self._style_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        summ_sizer.Add(style_row, 0, wx.ALL | wx.EXPAND, 8)

        sizer.Add(summ_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Advanced AI settings
        adv_box = wx.StaticBox(parent, label="Advanced")
        set_accessible_name(adv_box, "Advanced AI settings")
        adv_sizer = wx.StaticBoxSizer(adv_box, wx.VERTICAL)

        temp_row = wx.BoxSizer(wx.HORIZONTAL)
        temp_label = wx.StaticText(parent, label="&Temperature:")
        set_accessible_name(temp_label, "AI temperature")
        temp_row.Add(temp_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._temp_spin = wx.SpinCtrlDouble(
            parent, min=0.0, max=2.0, inc=0.1, initial=0.3
        )
        set_accessible_name(self._temp_spin, "AI temperature value")
        set_accessible_help(
            self._temp_spin,
            "Lower values produce more predictable output, higher values more creative",
        )
        temp_row.Add(self._temp_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(temp_row, 0, wx.ALL | wx.EXPAND, 8)

        tokens_row = wx.BoxSizer(wx.HORIZONTAL)
        tokens_label = wx.StaticText(parent, label="&Max Tokens:")
        set_accessible_name(tokens_label, "Maximum tokens")
        tokens_row.Add(tokens_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._tokens_spin = wx.SpinCtrl(parent, min=256, max=16384, initial=4096)
        set_accessible_name(self._tokens_spin, "Maximum response tokens")
        tokens_row.Add(self._tokens_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(tokens_row, 0, wx.ALL | wx.EXPAND, 8)

        sizer.Add(adv_sizer, 0, wx.ALL | wx.EXPAND, 10)

        parent.SetSizer(sizer)

    # ------------------------------------------------------------------ #
    # Load / Save                                                          #
    # ------------------------------------------------------------------ #

    def _load_values(self) -> None:
        """Load current values from settings and key store."""
        ai = self._settings.ai

        # Default provider
        for i, p in enumerate(_AI_PROVIDERS):
            if p["id"] == ai.selected_provider:
                self._provider_choice.SetSelection(i)
                break

        # API keys from key store
        for provider in _AI_PROVIDERS:
            for field_def in provider["fields"]:
                field_id = f"{provider['id']}_{field_def['id']}"
                txt = self._fields.get(field_id)
                if txt and isinstance(txt, wx.TextCtrl):
                    key = self._key_store.get_key(field_def["key_name"])
                    if key:
                        txt.SetValue(key)

            # Model selection
            model_field_id = f"{provider['id']}_model"
            model_ctrl = self._fields.get(model_field_id)
            if model_ctrl and isinstance(model_ctrl, wx.Choice):
                if provider["id"] == "openai":
                    model_name = ai.openai_model
                elif provider["id"] == "anthropic":
                    model_name = ai.anthropic_model
                elif provider["id"] == "gemini":
                    model_name = ai.gemini_model
                elif provider["id"] == "copilot":
                    model_name = ai.copilot_model
                else:
                    continue
                idx = model_ctrl.FindString(model_name)
                if idx != wx.NOT_FOUND:
                    model_ctrl.SetSelection(idx)

        # Translation target language
        idx = self._lang_choice.FindString(ai.translation_target_language)
        if idx != wx.NOT_FOUND:
            self._lang_choice.SetSelection(idx)

        # Summary style
        style_map = {"concise": 0, "detailed": 1, "bullet_points": 2}
        self._style_choice.SetSelection(style_map.get(ai.summarization_style, 0))

        # Advanced
        self._temp_spin.SetValue(ai.temperature)
        self._tokens_spin.SetValue(ai.max_tokens)

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save settings and close."""
        ai = self._settings.ai

        # Save default provider
        idx = self._provider_choice.GetSelection()
        if idx >= 0:
            ai.selected_provider = _AI_PROVIDERS[idx]["id"]

        # Save API keys
        for provider in _AI_PROVIDERS:
            for field_def in provider["fields"]:
                field_id = f"{provider['id']}_{field_def['id']}"
                txt = self._fields.get(field_id)
                if txt and isinstance(txt, wx.TextCtrl):
                    val = txt.GetValue().strip()
                    if val:
                        self._key_store.store_key(field_def["key_name"], val)
                    else:
                        self._key_store.delete_key(field_def["key_name"])

            # Model selection
            model_field_id = f"{provider['id']}_model"
            model_ctrl = self._fields.get(model_field_id)
            if model_ctrl and isinstance(model_ctrl, wx.Choice):
                sel = model_ctrl.GetSelection()
                if sel >= 0:
                    model_name = model_ctrl.GetString(sel)
                    if provider["id"] == "openai":
                        ai.openai_model = model_name
                    elif provider["id"] == "anthropic":
                        ai.anthropic_model = model_name
                    elif provider["id"] == "gemini":
                        ai.gemini_model = model_name
                    elif provider["id"] == "copilot":
                        ai.copilot_model = model_name

        # Translation
        lang_idx = self._lang_choice.GetSelection()
        if lang_idx >= 0:
            ai.translation_target_language = self._lang_choice.GetString(lang_idx)

        # Summary style
        style_idx = self._style_choice.GetSelection()
        style_map = {0: "concise", 1: "detailed", 2: "bullet_points"}
        ai.summarization_style = style_map.get(style_idx, "concise")

        # Advanced
        ai.temperature = self._temp_spin.GetValue()
        ai.max_tokens = self._tokens_spin.GetValue()

        # Persist
        self._settings.save()
        announce_status(self._main_frame, "AI settings saved")

        self.EndModal(wx.ID_OK)

    def _on_validate(self, provider_id: str) -> None:
        """Validate an AI provider's API key in a background thread.

        Args:
            provider_id: Provider identifier.
        """
        # Get the API key from the field
        api_key_field = self._fields.get(f"{provider_id}_api_key")
        if not api_key_field:
            return
        api_key = api_key_field.GetValue().strip()
        if not api_key:
            wx.MessageBox(
                "Please enter an API key first.",
                "No API Key",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        announce_status(self._main_frame, f"Validating {provider_id} API key...")

        def _validate() -> None:
            from bits_whisperer.core.ai_service import (
                AnthropicAIProvider,
                AzureOpenAIProvider,
                OpenAIAIProvider,
            )

            valid = False
            try:
                if provider_id == "openai":
                    provider = OpenAIAIProvider(api_key)
                    valid = provider.validate_key(api_key)
                elif provider_id == "anthropic":
                    provider = AnthropicAIProvider(api_key)
                    valid = provider.validate_key(api_key)
                elif provider_id == "azure_openai":
                    endpoint_field = self._fields.get("azure_openai_endpoint")
                    deploy_field = self._fields.get("azure_openai_deployment")
                    endpoint = endpoint_field.GetValue().strip() if endpoint_field else ""
                    deployment = deploy_field.GetValue().strip() if deploy_field else ""
                    if endpoint and deployment:
                        provider = AzureOpenAIProvider(api_key, endpoint, deployment)
                        valid = provider.validate_key(api_key)
                elif provider_id == "gemini":
                    from bits_whisperer.core.ai_service import GeminiAIProvider

                    provider = GeminiAIProvider(api_key)
                    valid = provider.validate_key(api_key)
                elif provider_id == "copilot":
                    from bits_whisperer.core.ai_service import CopilotAIProvider

                    provider = CopilotAIProvider(api_key)
                    valid = provider.validate_key(api_key)
            except Exception as exc:
                logger.warning("API key validation failed: %s", exc)

            def _show_result() -> None:
                if valid:
                    wx.MessageBox(
                        f"{provider_id.title()} API key is valid!",
                        "Key Valid",
                        wx.OK | wx.ICON_INFORMATION,
                        self,
                    )
                    announce_status(self._main_frame, f"{provider_id} key validated")
                else:
                    wx.MessageBox(
                        f"Could not validate {provider_id} API key.\n"
                        "Check that the key is correct and the service is reachable.",
                        "Validation Failed",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )

            safe_call_after(_show_result)

        threading.Thread(target=_validate, daemon=True).start()
