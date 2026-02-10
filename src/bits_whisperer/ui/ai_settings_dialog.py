"""AI provider settings dialog for configuring translation/summarization.

Allows users to add API keys for OpenAI, Anthropic (Claude), Azure OpenAI,
Google Gemini (including Gemma), and GitHub Copilot.  Shows real-time pricing
and supports custom vocabulary, prompt templates, and multi-language
simultaneous translation.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    announce_to_screen_reader,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import (
    ANTHROPIC_AI_MODELS,
    BUILTIN_PROMPT_TEMPLATES,
    COPILOT_AI_MODELS,
    COPILOT_TIERS,
    GEMINI_AI_MODELS,
    OLLAMA_AI_MODELS,
    OPENAI_AI_MODELS,
    format_price_per_1k,
    get_ai_model_by_id,
    get_copilot_models_for_tier,
    get_templates_by_category,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


def _build_model_list(models_list):
    """Build a list of model ID strings from an AIModelInfo list."""
    return [m.id for m in models_list]


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
        "models": _build_model_list(OPENAI_AI_MODELS),
        "models_list": OPENAI_AI_MODELS,
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "description": "Anthropic's Claude models for high-quality translation and summarization.",
        "key_id": "anthropic",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "anthropic", "password": True},
        ],
        "models": _build_model_list(ANTHROPIC_AI_MODELS),
        "models_list": ANTHROPIC_AI_MODELS,
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
        "models_list": [],
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "description": (
            "Google's Gemini AI models and Gemma open-weight models for "
            "translation and summarization. Requires a Google AI Studio API key."
        ),
        "key_id": "gemini",
        "fields": [
            {"id": "api_key", "label": "API Key", "key_name": "gemini", "password": True},
        ],
        "models": _build_model_list(GEMINI_AI_MODELS),
        "models_list": GEMINI_AI_MODELS,
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
        "models": _build_model_list(COPILOT_AI_MODELS),
        "models_list": COPILOT_AI_MODELS,
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "description": (
            "Run AI models locally with Ollama. No API key or cloud account needed. "
            "Supports models from Hugging Face and the Ollama library. "
            "Requires Ollama to be installed and running (ollama.com)."
        ),
        "key_id": "ollama",
        "fields": [
            {
                "id": "endpoint",
                "label": "Ollama Endpoint",
                "key_name": "",
                "password": False,
                "default": "http://localhost:11434",
            },
            {
                "id": "custom_model",
                "label": "Custom Model (HuggingFace or Ollama)",
                "key_name": "",
                "password": False,
                "placeholder": "e.g. hf.co/user/model or custom-model:tag",
            },
        ],
        "models": _build_model_list(OLLAMA_AI_MODELS),
        "models_list": OLLAMA_AI_MODELS,
    },
]

# Available languages for translation
_LANGUAGES = [
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


class AISettingsDialog(wx.Dialog):
    """Dialog for configuring AI provider API keys and preferences.

    Allows users to:
    - Add/remove API keys for AI providers with real-time pricing
    - Select the default AI provider and model
    - Configure translation target language and multi-language translation
    - Configure summarization style and prompt templates
    - Manage custom vocabulary for domain-specific accuracy
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
            size=(650, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "AI Provider Settings")
        self.SetMinSize((520, 460))
        self.Centre()

        self._main_frame = main_frame
        self._settings = AppSettings.load()
        self._key_store = main_frame.key_store
        self._fields: dict[str, wx.TextCtrl] = {}
        self._pricing_labels: dict[str, wx.StaticText] = {}

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

        # -- Custom Vocabulary tab --
        vocab_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(vocab_panel)
        self._build_vocabulary_tab(vocab_panel)
        notebook.AddPage(vocab_panel, "Vocabulary")

        # -- Prompt Templates tab --
        templates_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(templates_panel)
        self._build_templates_tab(templates_panel)
        notebook.AddPage(templates_panel, "Templates")

        # -- Multi-Language tab --
        multi_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(multi_panel)
        self._build_multi_language_tab(multi_panel)
        notebook.AddPage(multi_panel, "Multi-Language")

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
                set_accessible_name(txt, f"{field_def['label']} for {provider['name']}")
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

                # Pricing info label (updated when model changes)
                pricing_label = wx.StaticText(parent, label="")
                set_accessible_name(pricing_label, f"{provider['name']} pricing")
                self._pricing_labels[provider["id"]] = pricing_label
                box_sizer.Add(pricing_label, 0, wx.LEFT | wx.BOTTOM, 10)

                # Bind model change to update pricing
                model_choice.Bind(
                    wx.EVT_CHOICE,
                    lambda evt, pid=provider["id"]: self._on_model_changed(pid),
                )

                # Copilot tier info
                if provider["id"] == "copilot":
                    tier_row = wx.BoxSizer(wx.HORIZONTAL)
                    tier_lbl = wx.StaticText(parent, label="Subscription:")
                    set_accessible_name(tier_lbl, "Copilot subscription tier")
                    tier_row.Add(tier_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

                    tier_choices = [f"{v['name']} — {v['price']}" for v in COPILOT_TIERS.values()]
                    self._copilot_tier_choice = wx.Choice(parent, choices=tier_choices)
                    set_accessible_name(
                        self._copilot_tier_choice,
                        "Select your Copilot subscription tier",
                    )
                    set_accessible_help(
                        self._copilot_tier_choice,
                        "Choose your GitHub Copilot plan to see available models",
                    )
                    tier_row.Add(self._copilot_tier_choice, 1, wx.ALIGN_CENTER_VERTICAL)
                    box_sizer.Add(tier_row, 0, wx.ALL | wx.EXPAND, 5)

                    tier_desc = wx.StaticText(parent, label="")
                    set_accessible_name(tier_desc, "Copilot tier description")
                    self._copilot_tier_desc = tier_desc
                    box_sizer.Add(tier_desc, 0, wx.LEFT | wx.BOTTOM, 10)

                    self._copilot_tier_choice.Bind(wx.EVT_CHOICE, self._on_copilot_tier_changed)

                # Ollama-specific controls
                if provider["id"] == "ollama":
                    ollama_btn_row = wx.BoxSizer(wx.HORIZONTAL)

                    test_btn = wx.Button(parent, label="Test Connection")
                    set_accessible_name(test_btn, "Test Ollama connection")
                    test_btn.Bind(wx.EVT_BUTTON, self._on_ollama_test)
                    ollama_btn_row.Add(test_btn, 0, wx.RIGHT, 8)

                    refresh_btn = wx.Button(parent, label="Refresh Models")
                    set_accessible_name(refresh_btn, "Refresh available Ollama models")
                    set_accessible_help(
                        refresh_btn,
                        "Query the Ollama server for locally installed models",
                    )
                    refresh_btn.Bind(wx.EVT_BUTTON, self._on_ollama_refresh)
                    ollama_btn_row.Add(refresh_btn, 0, wx.RIGHT, 8)

                    pull_btn = wx.Button(parent, label="Pull Model")
                    set_accessible_name(pull_btn, "Pull a model into Ollama")
                    set_accessible_help(
                        pull_btn,
                        "Download a model from the Ollama library or Hugging Face. "
                        "Enter a model name in the Custom Model field first, "
                        "e.g. hf.co/user/model for Hugging Face GGUF models.",
                    )
                    pull_btn.Bind(wx.EVT_BUTTON, self._on_ollama_pull)
                    ollama_btn_row.Add(pull_btn, 0)

                    box_sizer.Add(ollama_btn_row, 0, wx.ALL, 5)

                    # Status label for ollama operations
                    self._ollama_status = wx.StaticText(parent, label="")
                    set_accessible_name(self._ollama_status, "Ollama status")
                    box_sizer.Add(self._ollama_status, 0, wx.LEFT | wx.BOTTOM, 10)

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

        self._lang_choice = wx.Choice(parent, choices=_LANGUAGES)
        set_accessible_name(self._lang_choice, "Select translation target language")
        set_accessible_help(
            self._lang_choice,
            "The language to translate transcripts into",
        )
        self._lang_choice.SetSelection(0)
        lang_row.Add(self._lang_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        trans_sizer.Add(lang_row, 0, wx.ALL | wx.EXPAND, 8)

        # Active translation template
        tpl_row = wx.BoxSizer(wx.HORIZONTAL)
        tpl_label = wx.StaticText(parent, label="Translation &Style:")
        set_accessible_name(tpl_label, "Translation template style")
        tpl_row.Add(tpl_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        trans_templates = get_templates_by_category("translation")
        self._trans_tpl_names = [t.name for t in trans_templates]
        self._trans_tpl_ids = [t.id for t in trans_templates]
        self._trans_tpl_choice = wx.Choice(parent, choices=self._trans_tpl_names)
        set_accessible_name(self._trans_tpl_choice, "Select translation template")
        self._trans_tpl_choice.SetSelection(0)
        tpl_row.Add(self._trans_tpl_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        trans_sizer.Add(tpl_row, 0, wx.ALL | wx.EXPAND, 8)

        sizer.Add(trans_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Summarization settings
        summ_box = wx.StaticBox(parent, label="Summarization")
        set_accessible_name(summ_box, "Summarization settings")
        summ_sizer = wx.StaticBoxSizer(summ_box, wx.VERTICAL)

        style_row = wx.BoxSizer(wx.HORIZONTAL)
        style_label = wx.StaticText(parent, label="&Summary Style:")
        set_accessible_name(style_label, "Summary style")
        style_row.Add(style_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        styles = ["Concise (3-5 sentences)", "Detailed", "Bullet Points", "Meeting Minutes"]
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

        self._temp_spin = wx.SpinCtrlDouble(parent, min=0.0, max=2.0, inc=0.1, initial=0.3)
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

    def _build_vocabulary_tab(self, parent: wx.Panel) -> None:
        """Build the custom vocabulary tab.

        Args:
            parent: Parent panel.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "Add custom words, names, and technical terms to improve "
                "AI translation and summarization accuracy. One term per line."
            ),
        )
        intro.Wrap(560)
        set_accessible_name(intro, "Custom vocabulary instructions")
        sizer.Add(intro, 0, wx.ALL, 10)

        self._vocab_text = wx.TextCtrl(
            parent,
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
        )
        set_accessible_name(self._vocab_text, "Custom vocabulary terms, one per line")
        set_accessible_help(
            self._vocab_text,
            "Enter domain-specific terms, names, and jargon that the AI "
            "should preserve or use. These are sent as hints with each request.",
        )
        sizer.Add(self._vocab_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        hint = wx.StaticText(
            parent,
            label="Examples: BITS Whisperer, wxPython, WCAG 2.1, pyannote",
        )
        hint.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        sizer.Add(hint, 0, wx.ALL, 10)

        parent.SetSizer(sizer)

    def _build_templates_tab(self, parent: wx.Panel) -> None:
        """Build the prompt templates tab.

        Args:
            parent: Parent panel.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "View built-in prompt templates and set active templates "
                "for translation and summarization operations."
            ),
        )
        intro.Wrap(560)
        set_accessible_name(intro, "Prompt templates instructions")
        sizer.Add(intro, 0, wx.ALL, 10)

        # Built-in templates list
        tmpl_box = wx.StaticBox(parent, label="Built-in Templates")
        set_accessible_name(tmpl_box, "Built-in prompt templates")
        tmpl_sizer = wx.StaticBoxSizer(tmpl_box, wx.VERTICAL)

        items = [f"[{t.category}] {t.name} — {t.description}" for t in BUILTIN_PROMPT_TEMPLATES]
        self._template_list = wx.ListBox(parent, choices=items, size=(-1, 140))
        set_accessible_name(self._template_list, "Available prompt templates")
        tmpl_sizer.Add(self._template_list, 1, wx.EXPAND | wx.ALL, 4)

        # Preview
        self._template_preview = wx.TextCtrl(
            parent,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 80),
        )
        set_accessible_name(self._template_preview, "Template preview")
        tmpl_sizer.Add(self._template_preview, 0, wx.EXPAND | wx.ALL, 4)

        self._template_list.Bind(wx.EVT_LISTBOX, self._on_template_selected)

        sizer.Add(tmpl_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Active templates selection
        active_box = wx.StaticBox(parent, label="Active Templates")
        set_accessible_name(active_box, "Active template selection")
        active_sizer = wx.StaticBoxSizer(active_box, wx.VERTICAL)

        trans_row = wx.BoxSizer(wx.HORIZONTAL)
        trans_lbl = wx.StaticText(parent, label="Translation:")
        set_accessible_name(trans_lbl, "Active translation template")
        trans_row.Add(trans_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        trans_templates = get_templates_by_category("translation")
        self._active_trans_names = [t.name for t in trans_templates]
        self._active_trans_ids = [t.id for t in trans_templates]
        self._active_trans_choice = wx.Choice(parent, choices=self._active_trans_names)
        set_accessible_name(self._active_trans_choice, "Select active translation template")
        self._active_trans_choice.SetSelection(0)
        trans_row.Add(self._active_trans_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        active_sizer.Add(trans_row, 0, wx.EXPAND | wx.ALL, 4)

        summ_row = wx.BoxSizer(wx.HORIZONTAL)
        summ_lbl = wx.StaticText(parent, label="Summarization:")
        set_accessible_name(summ_lbl, "Active summarization template")
        summ_row.Add(summ_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        summ_templates = get_templates_by_category("summarization")
        self._active_summ_names = [t.name for t in summ_templates]
        self._active_summ_ids = [t.id for t in summ_templates]
        self._active_summ_choice = wx.Choice(parent, choices=self._active_summ_names)
        set_accessible_name(self._active_summ_choice, "Select active summarization template")
        self._active_summ_choice.SetSelection(0)
        summ_row.Add(self._active_summ_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        active_sizer.Add(summ_row, 0, wx.EXPAND | wx.ALL, 4)

        sizer.Add(active_sizer, 0, wx.EXPAND | wx.ALL, 10)

        parent.SetSizer(sizer)

    def _build_multi_language_tab(self, parent: wx.Panel) -> None:
        """Build the multi-language simultaneous translation tab.

        Args:
            parent: Parent panel.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "Select multiple target languages for simultaneous translation. "
                "When you translate a transcript, it will be translated to all "
                "selected languages at once."
            ),
        )
        intro.Wrap(560)
        set_accessible_name(intro, "Multi-language translation instructions")
        sizer.Add(intro, 0, wx.ALL, 10)

        lang_box = wx.StaticBox(parent, label="Target Languages")
        set_accessible_name(lang_box, "Multi-language target selection")
        lang_sizer = wx.StaticBoxSizer(lang_box, wx.VERTICAL)

        self._multi_lang_list = wx.CheckListBox(parent, choices=_LANGUAGES)
        set_accessible_name(
            self._multi_lang_list,
            "Select target languages for simultaneous translation",
        )
        set_accessible_help(
            self._multi_lang_list,
            "Check all languages you want to translate to at once. "
            "Use AI menu, then Translate Multi-Language to run.",
        )
        lang_sizer.Add(self._multi_lang_list, 1, wx.EXPAND | wx.ALL, 4)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(parent, label="Select &All")
        set_accessible_name(select_all_btn, "Select all languages")
        select_all_btn.Bind(
            wx.EVT_BUTTON,
            lambda e: [
                self._multi_lang_list.Check(i, True)
                for i in range(self._multi_lang_list.GetCount())
            ],
        )
        btn_row.Add(select_all_btn, 0, wx.RIGHT, 8)

        clear_btn = wx.Button(parent, label="&Clear All")
        set_accessible_name(clear_btn, "Clear all language selections")
        clear_btn.Bind(
            wx.EVT_BUTTON,
            lambda e: [
                self._multi_lang_list.Check(i, False)
                for i in range(self._multi_lang_list.GetCount())
            ],
        )
        btn_row.Add(clear_btn, 0)
        lang_sizer.Add(btn_row, 0, wx.ALL, 4)

        sizer.Add(lang_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        parent.SetSizer(sizer)

    # ------------------------------------------------------------------ #
    # Event handlers for pricing & templates                               #
    # ------------------------------------------------------------------ #

    def _on_model_changed(self, provider_id: str) -> None:
        """Update pricing display when a model is selected.

        Args:
            provider_id: Provider identifier.
        """
        model_field_id = f"{provider_id}_model"
        model_ctrl = self._fields.get(model_field_id)
        pricing_label = self._pricing_labels.get(provider_id)
        if not model_ctrl or not pricing_label or not isinstance(model_ctrl, wx.Choice):
            return

        sel = model_ctrl.GetSelection()
        if sel < 0:
            return

        model_id = model_ctrl.GetString(sel)
        model_info = get_ai_model_by_id(model_id, provider_id)
        if model_info:
            in_price = format_price_per_1k(model_info.input_price_per_1m)
            out_price = format_price_per_1k(model_info.output_price_per_1m)
            ctx = f"{model_info.context_window:,} tokens"
            tier_note = ""
            if model_info.copilot_tier:
                tier_note = f"  |  Tier: {model_info.copilot_tier.title()}"
                if model_info.is_premium:
                    tier_note += " (Premium)"
            pricing_label.SetLabel(
                f"Input: {in_price}  |  Output: {out_price}  |  " f"Context: {ctx}{tier_note}"
            )
        else:
            pricing_label.SetLabel("")

        pricing_label.GetParent().Layout()

    def _on_copilot_tier_changed(self, _event: wx.CommandEvent) -> None:
        """Update Copilot model list based on selected tier."""
        sel = self._copilot_tier_choice.GetSelection()
        if sel < 0:
            return

        tier_keys = list(COPILOT_TIERS.keys())
        tier = tier_keys[sel]
        tier_info = COPILOT_TIERS[tier]
        self._copilot_tier_desc.SetLabel(tier_info["description"])

        # Update model choices for copilot to match tier
        available = get_copilot_models_for_tier(tier)
        model_ctrl = self._fields.get("copilot_model")
        if model_ctrl and isinstance(model_ctrl, wx.Choice):
            model_ctrl.Clear()
            for m in available:
                model_ctrl.Append(m.id)
            if available:
                model_ctrl.SetSelection(0)
                self._on_model_changed("copilot")

        # Save tier to settings
        self._settings.copilot.subscription_tier = tier
        self._copilot_tier_desc.GetParent().Layout()

    def _on_template_selected(self, _event: wx.CommandEvent) -> None:
        """Show preview of selected template."""
        sel = self._template_list.GetSelection()
        if sel < 0 or sel >= len(BUILTIN_PROMPT_TEMPLATES):
            return
        tmpl = BUILTIN_PROMPT_TEMPLATES[sel]
        self._template_preview.SetValue(tmpl.template)

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
                key_name = field_def.get("key_name", "")
                if not key_name:
                    continue  # Ollama fields loaded separately
                field_id = f"{provider['id']}_{field_def['id']}"
                txt = self._fields.get(field_id)
                if txt and isinstance(txt, wx.TextCtrl):
                    key = self._key_store.get_key(key_name)
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
                elif provider["id"] == "ollama":
                    model_name = ai.ollama_model
                else:
                    continue
                idx = model_ctrl.FindString(model_name)
                if idx != wx.NOT_FOUND:
                    model_ctrl.SetSelection(idx)
                # Show initial pricing
                self._on_model_changed(provider["id"])

        # Copilot subscription tier
        tier = self._settings.copilot.subscription_tier
        tier_keys = list(COPILOT_TIERS.keys())
        if tier in tier_keys:
            tier_idx = tier_keys.index(tier)
            self._copilot_tier_choice.SetSelection(tier_idx)
            self._copilot_tier_desc.SetLabel(COPILOT_TIERS[tier]["description"])

        # Translation target language
        idx = self._lang_choice.FindString(ai.translation_target_language)
        if idx != wx.NOT_FOUND:
            self._lang_choice.SetSelection(idx)

        # Translation template in preferences tab
        if ai.active_translation_template in self._trans_tpl_ids:
            tpl_idx = self._trans_tpl_ids.index(ai.active_translation_template)
            self._trans_tpl_choice.SetSelection(tpl_idx)

        # Summary style
        style_map = {"concise": 0, "detailed": 1, "bullet_points": 2, "meeting": 3}
        self._style_choice.SetSelection(style_map.get(ai.summarization_style, 0))

        # Advanced
        self._temp_spin.SetValue(ai.temperature)
        self._tokens_spin.SetValue(ai.max_tokens)

        # Custom vocabulary
        if ai.custom_vocabulary:
            self._vocab_text.SetValue("\n".join(ai.custom_vocabulary))

        # Active templates (in Templates tab)
        if ai.active_translation_template in self._active_trans_ids:
            self._active_trans_choice.SetSelection(
                self._active_trans_ids.index(ai.active_translation_template)
            )
        if ai.active_summarization_template in self._active_summ_ids:
            self._active_summ_choice.SetSelection(
                self._active_summ_ids.index(ai.active_summarization_template)
            )

        # Multi-language targets
        for lang in ai.multi_target_languages:
            idx = self._multi_lang_list.FindString(lang)
            if idx != wx.NOT_FOUND:
                self._multi_lang_list.Check(idx, True)

        # Ollama endpoint and custom model (stored in settings, not key store)
        endpoint_field = self._fields.get("ollama_endpoint")
        if endpoint_field and isinstance(endpoint_field, wx.TextCtrl):
            endpoint_field.SetValue(ai.ollama_endpoint or "http://localhost:11434")
        custom_model_field = self._fields.get("ollama_custom_model")
        if custom_model_field and isinstance(custom_model_field, wx.TextCtrl):
            custom_model_field.SetValue(ai.ollama_custom_model or "")

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
                key_name = field_def.get("key_name", "")
                if not key_name:
                    continue  # Ollama fields are saved separately
                field_id = f"{provider['id']}_{field_def['id']}"
                txt = self._fields.get(field_id)
                if txt and isinstance(txt, wx.TextCtrl):
                    val = txt.GetValue().strip()
                    if val:
                        self._key_store.store_key(key_name, val)
                    else:
                        self._key_store.delete_key(key_name)

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
                    elif provider["id"] == "ollama":
                        ai.ollama_model = model_name

        # Translation
        lang_idx = self._lang_choice.GetSelection()
        if lang_idx >= 0:
            ai.translation_target_language = self._lang_choice.GetString(lang_idx)

        # Translation template from preferences tab
        trans_tpl_idx = self._trans_tpl_choice.GetSelection()
        if trans_tpl_idx >= 0 and trans_tpl_idx < len(self._trans_tpl_ids):
            ai.active_translation_template = self._trans_tpl_ids[trans_tpl_idx]

        # Summary style
        style_idx = self._style_choice.GetSelection()
        style_map = {0: "concise", 1: "detailed", 2: "bullet_points", 3: "meeting"}
        ai.summarization_style = style_map.get(style_idx, "concise")

        # Advanced
        ai.temperature = self._temp_spin.GetValue()
        ai.max_tokens = self._tokens_spin.GetValue()

        # Copilot subscription tier
        tier_idx = self._copilot_tier_choice.GetSelection()
        if tier_idx >= 0:
            tier_keys = list(COPILOT_TIERS.keys())
            self._settings.copilot.subscription_tier = tier_keys[tier_idx]

        # Custom vocabulary
        vocab_raw = self._vocab_text.GetValue().strip()
        if vocab_raw:
            ai.custom_vocabulary = [w.strip() for w in vocab_raw.split("\n") if w.strip()]
        else:
            ai.custom_vocabulary = []

        # Active templates (from Templates tab)
        active_trans_idx = self._active_trans_choice.GetSelection()
        if active_trans_idx >= 0 and active_trans_idx < len(self._active_trans_ids):
            ai.active_translation_template = self._active_trans_ids[active_trans_idx]
        active_summ_idx = self._active_summ_choice.GetSelection()
        if active_summ_idx >= 0 and active_summ_idx < len(self._active_summ_ids):
            ai.active_summarization_template = self._active_summ_ids[active_summ_idx]

        # Multi-language targets
        selected_langs = []
        for i in range(self._multi_lang_list.GetCount()):
            if self._multi_lang_list.IsChecked(i):
                selected_langs.append(self._multi_lang_list.GetString(i))
        ai.multi_target_languages = selected_langs

        # Ollama settings (stored in settings, not key store)
        endpoint_field = self._fields.get("ollama_endpoint")
        if endpoint_field and isinstance(endpoint_field, wx.TextCtrl):
            val = endpoint_field.GetValue().strip()
            ai.ollama_endpoint = val or "http://localhost:11434"
        custom_model_field = self._fields.get("ollama_custom_model")
        if custom_model_field and isinstance(custom_model_field, wx.TextCtrl):
            ai.ollama_custom_model = custom_model_field.GetValue().strip()

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
            accessible_message_box(
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

                    provider = CopilotAIProvider(
                        github_token=api_key,
                    )
                    valid = provider.validate_key(api_key)
            except Exception as exc:
                logger.warning("API key validation failed: %s", exc)

            def _show_result() -> None:
                if valid:
                    accessible_message_box(
                        f"{provider_id.title()} API key is valid!",
                        "Key Valid",
                        wx.OK | wx.ICON_INFORMATION,
                        self,
                    )
                    announce_status(self._main_frame, f"{provider_id} key validated")
                else:
                    accessible_message_box(
                        f"Could not validate {provider_id} API key.\n"
                        "Check that the key is correct and the service is reachable.",
                        "Validation Failed",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )

            safe_call_after(_show_result)

        threading.Thread(target=_validate, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Ollama-specific handlers                                             #
    # ------------------------------------------------------------------ #

    def _get_ollama_endpoint(self) -> str:
        """Read the current Ollama endpoint from the dialog field."""
        endpoint_field = self._fields.get("ollama_endpoint")
        if endpoint_field and isinstance(endpoint_field, wx.TextCtrl):
            return endpoint_field.GetValue().strip() or "http://localhost:11434"
        return "http://localhost:11434"

    def _on_ollama_test(self, _event: wx.CommandEvent) -> None:
        """Test connectivity to the Ollama server."""
        endpoint = self._get_ollama_endpoint()
        self._ollama_status.SetLabel("Testing connection...")
        announce_status(self._main_frame, "Testing Ollama connection...")

        def _test() -> None:
            from bits_whisperer.core.ai_service import OllamaAIProvider

            provider = OllamaAIProvider(endpoint=endpoint)
            reachable = provider.validate_key("")

            def _show() -> None:
                if reachable:
                    models = provider.list_models()
                    count = len(models)
                    self._ollama_status.SetLabel(
                        f"Connected — {count} model{'s' if count != 1 else ''} available"
                    )
                    accessible_message_box(
                        f"Ollama is reachable at {endpoint}.\n"
                        f"{count} model{'s' if count != 1 else ''} installed locally.",
                        "Connection Successful",
                        wx.OK | wx.ICON_INFORMATION,
                        self,
                    )
                    announce_status(self._main_frame, "Ollama connection successful")
                else:
                    self._ollama_status.SetLabel("Connection failed")
                    accessible_message_box(
                        f"Could not connect to Ollama at {endpoint}.\n\n"
                        "Make sure Ollama is installed and running.\n"
                        "Download from: https://ollama.com",
                        "Connection Failed",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )

            safe_call_after(_show)

        threading.Thread(target=_test, daemon=True).start()

    def _on_ollama_refresh(self, _event: wx.CommandEvent) -> None:
        """Refresh the Ollama model list from the local server."""
        endpoint = self._get_ollama_endpoint()
        self._ollama_status.SetLabel("Fetching models...")
        announce_status(self._main_frame, "Fetching Ollama models...")

        def _fetch() -> None:
            from bits_whisperer.core.ai_service import OllamaAIProvider

            provider = OllamaAIProvider(endpoint=endpoint)
            models = provider.list_models()

            def _update() -> None:
                model_ctrl = self._fields.get("ollama_model")
                if not model_ctrl or not isinstance(model_ctrl, wx.Choice):
                    return

                if not models:
                    self._ollama_status.SetLabel("No models found — pull a model first")
                    announce_to_screen_reader(
                        "No models found on Ollama server. " "Use Pull Model to download one."
                    )
                    return

                # Remember current selection
                current = model_ctrl.GetStringSelection()
                model_ctrl.Clear()
                for m in models:
                    model_ctrl.Append(m)

                # Restore selection or select first
                idx = model_ctrl.FindString(current)
                if idx != wx.NOT_FOUND:
                    model_ctrl.SetSelection(idx)
                elif model_ctrl.GetCount() > 0:
                    model_ctrl.SetSelection(0)

                count = len(models)
                self._ollama_status.SetLabel(f"{count} model{'s' if count != 1 else ''} available")
                announce_status(
                    self._main_frame,
                    f"Found {count} Ollama model{'s' if count != 1 else ''}",
                )

            safe_call_after(_update)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_ollama_pull(self, _event: wx.CommandEvent) -> None:
        """Pull a model into Ollama from the library or Hugging Face."""
        custom_field = self._fields.get("ollama_custom_model")
        model_name = ""
        if custom_field and isinstance(custom_field, wx.TextCtrl):
            model_name = custom_field.GetValue().strip()

        if not model_name:
            accessible_message_box(
                "Enter a model name in the 'Custom Model' field first.\n\n"
                "Examples:\n"
                "  • llama3.2 (from Ollama library)\n"
                "  • hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF (from Hugging Face)\n"
                "  • mistral:7b-instruct",
                "No Model Specified",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        endpoint = self._get_ollama_endpoint()
        self._ollama_status.SetLabel(f"Pulling {model_name}... (this may take a while)")
        announce_status(
            self._main_frame,
            f"Pulling model {model_name}. This may take several minutes.",
        )

        def _pull() -> None:
            from bits_whisperer.core.ai_service import OllamaAIProvider

            provider = OllamaAIProvider(endpoint=endpoint)
            success = provider.pull_model(model_name)

            def _show() -> None:
                if success:
                    self._ollama_status.SetLabel(f"Successfully pulled {model_name}")
                    accessible_message_box(
                        f"Model '{model_name}' has been pulled successfully.\n"
                        "Click 'Refresh Models' to update the model list.",
                        "Model Pulled",
                        wx.OK | wx.ICON_INFORMATION,
                        self,
                    )
                    announce_status(self._main_frame, f"Model {model_name} pulled successfully")
                else:
                    self._ollama_status.SetLabel("Pull failed")
                    accessible_message_box(
                        f"Failed to pull model '{model_name}'.\n\n"
                        "Check that:\n"
                        "  • Ollama is running\n"
                        "  • The model name is correct\n"
                        "  • You have enough disk space",
                        "Pull Failed",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )

            safe_call_after(_show)

        threading.Thread(target=_pull, daemon=True).start()
