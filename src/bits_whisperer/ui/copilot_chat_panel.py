"""Interactive AI chat panel for transcript analysis.

Embeds a provider-agnostic AI chat interface alongside the transcript,
allowing users to ask questions about their transcripts, get
summaries, find topics, and more — with streaming responses from
any configured AI provider.

Supported providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude Sonnet, Claude Haiku)
- Azure OpenAI
- Google Gemini
- GitHub Copilot (GitHub account sign-in)
- Ollama (local models)

Features:
- Provider picker — switch AI providers on the fly
- Streaming response display with real-time text updates
- Multi-turn conversation with persistent history
- Quick action buttons for common operations
- Transcript context auto-injection
- Full keyboard navigation and screen reader support
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.settings import AppSettings
from bits_whisperer.ui.slash_commands import (
    SlashCommandRegistry,
    build_default_registry,
    parse_slash_command,
)
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
    ANTHROPIC_AI_MODELS,
    COPILOT_AI_MODELS,
    DEFAULT_SYSTEM_PROMPT,
    GEMINI_AI_MODELS,
    OPENAI_AI_MODELS,
    SYSTEM_PROMPT_PRESETS,
)

if TYPE_CHECKING:
    from bits_whisperer.core.copilot_service import CopilotMessage, CopilotService
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Provider display names for the picker
_PROVIDER_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "azure_openai": "Azure OpenAI",
    "gemini": "Google Gemini",
    "copilot": "GitHub Copilot",
    "ollama": "Ollama (Local)",
}


class CopilotChatPanel(wx.Panel):
    """Interactive chat panel for AI-powered transcript analysis.

    Provides a conversational interface where users can ask questions
    about their transcripts using any configured AI provider — OpenAI,
    Anthropic, Gemini, Ollama, Azure, or GitHub Copilot.  Supports
    streaming responses, quick actions, and multi-turn conversations.
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        """Initialise the chat panel.

        Args:
            parent: Parent window (typically the notebook).
            main_frame: Reference to the main application frame.
        """
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        set_accessible_name(self, "AI Transcript Assistant")
        make_panel_accessible(self)

        self._main_frame = main_frame
        self._settings = AppSettings.load()
        self._copilot_service: CopilotService | None = None
        self._is_streaming = False

        # Conversation state — shared across all providers
        self._conversation_history: list[dict[str, str]] = []
        self._transcript_context: str = ""
        self._available_providers: list[dict[str, str]] = []

        # Per-session model override (not persisted to settings)
        self._session_model: str = ""

        # Per-session system prompt override (not persisted to settings)
        self._session_system_prompt: str = DEFAULT_SYSTEM_PROMPT

        # Slash command registry
        self._slash_registry: SlashCommandRegistry = build_default_registry()
        self._autocomplete_popup: _SlashAutocompletePopup | None = None

        self._build_ui()
        self._refresh_providers()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the chat panel layout with provider picker."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Header bar ──────────────────────────────────────────────── #
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        header_label = wx.StaticText(self, label="AI Transcript Chat")
        font = header_label.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header_label.SetFont(font)
        set_accessible_name(header_label, "AI Transcript Chat panel")
        header_sizer.Add(header_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        header_sizer.AddStretchSpacer()

        # Status indicator
        self._status_label = wx.StaticText(self, label="Select a provider")
        self._status_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        set_accessible_name(self._status_label, "Provider status")
        header_sizer.Add(self._status_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Clear button
        self._clear_btn = wx.Button(self, label="Clea&r")
        set_accessible_name(self._clear_btn, "Clear conversation")
        self._clear_btn.Bind(wx.EVT_BUTTON, self._on_clear)
        header_sizer.Add(self._clear_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # ── Provider picker ─────────────────────────────────────────── #
        provider_sizer = wx.BoxSizer(wx.HORIZONTAL)

        provider_label = wx.StaticText(self, label="Pro&vider:")
        set_accessible_name(provider_label, "AI Provider")
        provider_sizer.Add(provider_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        self._provider_choice = wx.Choice(self)
        label_control(provider_label, self._provider_choice)
        set_accessible_name(self._provider_choice, "AI Provider")
        set_accessible_help(
            self._provider_choice,
            "Choose which AI provider to use for chat. "
            "Configure providers in Tools, AI Provider Settings.",
        )
        self._provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)
        provider_sizer.Add(self._provider_choice, 1, wx.LEFT | wx.RIGHT, 4)

        # Refresh providers button
        refresh_btn = wx.Button(self, label="Re&fresh")
        set_accessible_name(refresh_btn, "Refresh provider list")
        refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh_providers)
        provider_sizer.Add(refresh_btn, 0, wx.RIGHT, 4)

        # Open Manage Models button
        mm_btn = wx.Button(self, label="&Manage Models\u2026")
        set_accessible_name(mm_btn, "Manage AI and transcription models")
        set_accessible_help(
            mm_btn,
            "Open Manage Models to download or organize AI models",
        )
        mm_btn.Bind(wx.EVT_BUTTON, self._on_open_model_manager)
        provider_sizer.Add(mm_btn, 0, wx.RIGHT, 4)

        main_sizer.Add(provider_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        # ── Model picker ────────────────────────────────────────────── #
        model_sizer = wx.BoxSizer(wx.HORIZONTAL)

        model_label = wx.StaticText(self, label="&Model:")
        set_accessible_name(model_label, "AI model")
        model_sizer.Add(model_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        self._model_choice = wx.Choice(self)
        label_control(model_label, self._model_choice)
        set_accessible_name(self._model_choice, "AI model")
        set_accessible_help(
            self._model_choice,
            "Choose which model to use for this chat session. "
            "Models depend on the selected provider.",
        )
        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)
        model_sizer.Add(self._model_choice, 1, wx.LEFT | wx.RIGHT, 4)

        main_sizer.Add(model_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        # ── System prompt preset picker ──────────────────────────────── #
        prompt_sizer = wx.BoxSizer(wx.HORIZONTAL)

        prompt_label = wx.StaticText(self, label="&Persona:")
        set_accessible_name(prompt_label, "AI persona")
        prompt_sizer.Add(prompt_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        preset_names = [p.name for p in SYSTEM_PROMPT_PRESETS]
        self._prompt_choice = wx.Choice(self, choices=preset_names)
        label_control(prompt_label, self._prompt_choice)
        set_accessible_name(self._prompt_choice, "AI persona")
        set_accessible_help(
            self._prompt_choice,
            "Choose how the AI assistant behaves. "
            "General Assistant works for most tasks. "
            "Select Custom to write your own instructions.",
        )
        self._prompt_choice.SetSelection(0)
        self._prompt_choice.Bind(wx.EVT_CHOICE, self._on_prompt_preset_changed)
        prompt_sizer.Add(self._prompt_choice, 1, wx.LEFT | wx.RIGHT, 4)

        main_sizer.Add(prompt_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 4)

        # ── Chat display ────────────────────────────────────────────── #
        self._chat_display = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.TE_RICH2,
        )
        chat_font = wx.Font(
            11,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
        self._chat_display.SetFont(chat_font)
        set_accessible_name(self._chat_display, "Conversation history")
        set_accessible_help(
            self._chat_display,
            "Shows the conversation with the AI assistant. New messages appear at the bottom.",
        )
        main_sizer.Add(self._chat_display, 1, wx.EXPAND | wx.ALL, 4)

        # ── Quick actions ────────────────────────────────────────────── #
        action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        action_label = wx.StaticText(self, label="Quick:")
        set_accessible_name(action_label, "Quick actions")
        action_sizer.Add(action_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        quick_actions = [
            ("&Summarize", "Please provide a concise summary of this transcript."),
            ("&Key Points", "List the key points and action items as bullet points."),
            ("&Topics", "What are the main topics discussed in this transcript?"),
            ("S&peakers", "Identify and describe each speaker in this transcript."),
            ("&Action Items", "Extract all action items and follow-ups from this transcript."),
            ("&Translate", self._build_translate_prompt()),
        ]

        _quick_help = {
            "Summarize": "Generate a concise summary of the transcript",
            "Key Points": "Extract key points and action items as bullets",
            "Topics": "Identify main topics discussed in the transcript",
            "Speakers": "Identify and describe each speaker",
            "Action Items": "Extract action items and follow-ups",
            "Translate": "Translate the transcript to your chosen language",
        }
        for label, prompt in quick_actions:
            btn = wx.Button(self, label=label, size=(-1, -1))
            clean = label.replace("&", "")
            set_accessible_name(btn, f"Quick action: {clean}")
            help_text = _quick_help.get(clean, "")
            if help_text:
                set_accessible_help(btn, help_text)
            btn.Bind(
                wx.EVT_BUTTON,
                lambda e, p=prompt: self._send_quick_action(p),
            )
            action_sizer.Add(btn, 0, wx.LEFT, 4)

        main_sizer.Add(action_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # ── Input area ──────────────────────────────────────────────── #
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._input_text = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER | wx.TE_MULTILINE,
            size=(-1, 60),
        )
        set_accessible_name(self._input_text, "Message input")
        set_accessible_help(
            self._input_text,
            "Type your question about the transcript and press Enter or "
            "click Send. Press Shift+Enter for a new line. "
            "Type / to see available slash commands.",
        )
        self._input_text.Bind(wx.EVT_TEXT_ENTER, self._on_send)
        self._input_text.Bind(wx.EVT_KEY_DOWN, self._on_input_key)
        self._input_text.Bind(wx.EVT_TEXT, self._on_input_text_changed)
        self._chat_display.Bind(wx.EVT_CONTEXT_MENU, self._on_display_context_menu)
        self._input_text.Bind(wx.EVT_CONTEXT_MENU, self._on_input_context_menu)
        input_sizer.Add(self._input_text, 1, wx.EXPAND | wx.RIGHT, 4)

        self._send_btn = wx.Button(self, label="&Send")
        set_accessible_name(self._send_btn, "Send message")
        self._send_btn.Bind(wx.EVT_BUTTON, self._on_send)
        input_sizer.Add(self._send_btn, 0, wx.EXPAND)

        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        self.SetSizer(main_sizer)
        self._update_interaction_state()

    # ------------------------------------------------------------------ #
    # Provider management                                                  #
    # ------------------------------------------------------------------ #

    def _refresh_providers(self) -> None:
        """Populate the provider picker with available AI providers.

        Filters to only show providers that have at least one
        downloaded/available model or a configured API key.
        """
        self._settings = AppSettings.load()

        def _load() -> list[dict[str, str]]:
            from bits_whisperer.core.ai_service import AIService

            svc = AIService(self._main_frame.key_store, self._settings.ai)
            return svc.get_available_providers()

        def _populate(providers: list[dict[str, str]]) -> None:
            self._available_providers = providers
            self._provider_choice.Clear()

            if not providers:
                self._provider_choice.Append("No providers configured")
                self._provider_choice.SetSelection(0)
                self._model_choice.Clear()
                self._model_choice.Append("Set up an AI provider first")
                self._model_choice.SetSelection(0)
                self._status_label.SetLabel(
                    "No AI providers are ready yet — open Copilot Setup, AI Provider "
                    "Settings, or Manage Models"
                )
                announce_to_screen_reader(
                    "No AI providers are ready. Open Copilot Setup, AI Provider Settings, "
                    "or Manage Models."
                )
                self._chat_display.SetValue(
                    "AI Transcript Chat\n"
                    + "\u2501" * 36
                    + "\n\n"
                    + "No AI providers are ready yet.\n\n"
                    + "To get started:\n"
                    + "  •  Open AI > Copilot Setup to sign in with GitHub\n"
                    + "  •  Open Tools > AI Provider Settings to use another provider\n"
                    + "  \u2022  Open Manage Models to download local models\n\n"
                    + "Once a provider is ready, come back here and ask a question "
                    + "about your transcript.\n\n"
                )
                self._update_interaction_state()
                return

            current = self._settings.ai.selected_provider
            sel_idx = 0
            for i, p in enumerate(providers):
                self._provider_choice.Append(p["name"])
                if p["id"] == current:
                    sel_idx = i
            self._provider_choice.SetSelection(sel_idx)
            self._on_provider_changed(None)  # update status
            self._show_welcome()
            self._update_interaction_state()

        # Run in background to avoid blocking on Ollama connectivity check
        def _bg() -> None:
            providers = _load()
            safe_call_after(_populate, providers)

        threading.Thread(target=_bg, daemon=True, name="provider-scan").start()

    def _on_refresh_providers(self, _event: wx.CommandEvent) -> None:
        """Handle Refresh button click."""
        self._refresh_providers()
        announce_status(self._main_frame, "Refreshing provider list")

    def _on_provider_changed(self, _event: wx.CommandEvent | None) -> None:
        """Handle provider selection change."""
        pid = self._get_selected_provider_id()
        if not pid:
            return

        # Reset per-session model override when switching providers
        self._session_model = ""

        # Populate model list for the selected provider
        self._populate_models(pid)

        # Update status with provider + model info
        from bits_whisperer.core.ai_service import AIService

        svc = AIService(self._main_frame.key_store, self._settings.ai)
        display = svc.get_provider_display_name()
        if self._transcript_context:
            from bits_whisperer.core.context_manager import create_context_manager

            ctx_mgr = create_context_manager(self._settings.ai)
            model_id = svc._get_model_id()
            prepared = ctx_mgr.prepare_chat_context(
                model=model_id,
                provider=pid,
                system_prompt="",
                transcript=self._transcript_context,
            )
            budget_info = ctx_mgr.format_budget_summary(prepared.budget)
            ctx_hint = f" \u2022 {budget_info}"
        else:
            ctx_hint = ""
        self._status_label.SetLabel(f"Ready \u2014 {display}{ctx_hint}")
        announce_to_screen_reader(f"Provider set to {display}")

    def _populate_models(self, provider_id: str) -> None:
        """Populate the model dropdown for the given provider.

        For Ollama, queries the actual downloaded models from the server.
        For other providers, uses static model registries.

        Args:
            provider_id: Provider identifier.
        """
        _provider_models: dict[str, list] = {
            "openai": OPENAI_AI_MODELS,
            "anthropic": ANTHROPIC_AI_MODELS,
            "gemini": GEMINI_AI_MODELS,
            "copilot": COPILOT_AI_MODELS,
        }

        self._model_choice.Clear()

        if provider_id == "ollama":
            # Query actual downloaded models from Ollama server
            self._model_choice.Append("Loading\u2026")
            self._model_choice.SetSelection(0)

            def _fetch_ollama() -> list[str]:
                try:
                    from bits_whisperer.core.ai_service import AIService

                    svc = AIService(self._main_frame.key_store, self._settings.ai)
                    return svc.list_ollama_models()
                except Exception:
                    return []

            def _populate_ollama(model_ids: list[str]) -> None:
                self._model_choice.Clear()
                if not model_ids:
                    self._model_choice.Append("No models \u2014 choose Manage Models")
                    self._model_choice.SetSelection(0)
                    return
                default = self._settings.ai.default_chat_model or self._settings.ai.ollama_model
                sel_idx = 0
                for i, mid in enumerate(model_ids):
                    self._model_choice.Append(mid)
                    if mid == default:
                        sel_idx = i
                self._model_choice.SetSelection(sel_idx)
                self._session_model = self._model_choice.GetString(sel_idx)
                self._update_provider_status()

            def _bg() -> None:
                ids = _fetch_ollama()
                safe_call_after(_populate_ollama, ids)

            threading.Thread(target=_bg, daemon=True, name="ollama-models").start()
            return

        models = _provider_models.get(provider_id, [])
        if not models:
            self._model_choice.Append("Default")
            self._model_choice.SetSelection(0)
            self._update_provider_status()
            return

        # Get the currently persisted model for this provider
        current_model = ""
        ai = self._settings.ai
        if provider_id == "openai":
            current_model = ai.openai_model
        elif provider_id == "anthropic":
            current_model = ai.anthropic_model
        elif provider_id == "gemini":
            current_model = ai.gemini_model
        elif provider_id == "copilot":
            current_model = ai.copilot_model

        sel_idx = 0
        for i, m in enumerate(models):
            self._model_choice.Append(m.id)
            if m.id == current_model:
                sel_idx = i
        self._model_choice.SetSelection(sel_idx)
        self._session_model = self._model_choice.GetString(sel_idx)
        self._update_provider_status()

    def _on_model_changed(self, _event: wx.CommandEvent) -> None:
        """Handle model selection change in the chat panel.

        Stores the selection as a per-session override (not persisted).
        """
        idx = self._model_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        model_name = self._model_choice.GetString(idx)
        if model_name in ("Default", "Loading\u2026", "No models \u2014 choose Manage Models"):
            self._update_interaction_state()
            return
        self._session_model = model_name
        announce_to_screen_reader(f"Model set to {model_name}")
        self._update_interaction_state()

    def _on_prompt_preset_changed(self, _event: wx.CommandEvent) -> None:
        """Handle system prompt preset selection change.

        When "Custom" is selected, opens a text dialog so the user
        can type their own instructions.
        """
        idx = self._prompt_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        preset = SYSTEM_PROMPT_PRESETS[idx]

        if preset.id == "custom":
            dlg = wx.TextEntryDialog(
                self,
                "Enter your custom system prompt.\n\n"
                "This tells the AI how to behave when answering questions.",
                "Custom AI Persona",
                self._session_system_prompt,
                style=wx.OK | wx.CANCEL | wx.TE_MULTILINE,
            )
            dlg.SetSize((500, 300))
            set_accessible_name(dlg, "Custom AI persona instructions")
            if dlg.ShowModal() == wx.ID_OK:
                custom_text = dlg.GetValue().strip()
                if custom_text:
                    self._session_system_prompt = custom_text
                    announce_to_screen_reader("Custom persona set")
                else:
                    # User left it blank — revert to General
                    self._prompt_choice.SetSelection(0)
                    self._session_system_prompt = DEFAULT_SYSTEM_PROMPT
                    announce_to_screen_reader("Persona reset to General Assistant")
            else:
                # Cancelled — revert to previous selection
                self._prompt_choice.SetSelection(0)
            dlg.Destroy()
        else:
            self._session_system_prompt = preset.prompt
            announce_to_screen_reader(f"Persona set to {preset.name}")

    def _update_provider_status(self) -> None:
        """Update the status label with the current provider and model."""
        pid = self._get_selected_provider_id()
        if not pid or not self._available_providers:
            return

        from bits_whisperer.core.ai_service import AIService

        svc = AIService(self._main_frame.key_store, self._settings.ai)
        display = svc.get_provider_display_name()
        if self._transcript_context:
            from bits_whisperer.core.context_manager import create_context_manager

            ctx_mgr = create_context_manager(self._settings.ai)
            model_id = svc._get_model_id()
            prepared = ctx_mgr.prepare_chat_context(
                model=model_id,
                provider=pid,
                system_prompt="",
                transcript=self._transcript_context,
            )
            budget_info = ctx_mgr.format_budget_summary(prepared.budget)
            ctx_hint = f" \u2022 {budget_info}"
        else:
            ctx_hint = ""
        self._status_label.SetLabel(f"Ready \u2014 {display}{ctx_hint}")
        announce_to_screen_reader(f"Provider set to {display}")

    def _on_open_model_manager(self, _event: wx.CommandEvent) -> None:
        """Open the Manage Models dialog."""
        try:
            on_model_manager = getattr(self._main_frame, "_on_model_manager", None)
            if callable(on_model_manager):
                on_model_manager(None)
            else:
                raise AttributeError("Manage Models handler not available")
        except Exception:
            logger.exception("Failed to open Manage Models")
            announce_to_screen_reader("Could not open Manage Models")

    def _get_selected_provider_id(self) -> str:
        """Return the ID of the currently selected provider."""
        idx = self._provider_choice.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._available_providers):
            return self._settings.ai.selected_provider
        return self._available_providers[idx]["id"]

    def _get_selected_model_id(self) -> str:
        """Return the model ID from the chat model dropdown."""
        idx = self._model_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return ""
        return self._model_choice.GetString(idx)

    # ------------------------------------------------------------------ #
    # Service management (Copilot-specific)                                #
    # ------------------------------------------------------------------ #

    def connect(self, copilot_service: CopilotService) -> None:
        """Connect to a CopilotService instance for enhanced Copilot chat.

        When Copilot is the selected provider, the CopilotService gives
        access to transcript tools, custom agents, and richer streaming.

        Args:
            copilot_service: The Copilot service instance.
        """

        logger.info("Connecting chat panel to CopilotService")
        self._copilot_service = copilot_service

        # Listen for SDK lifecycle status changes
        copilot_service.add_status_listener(self._on_copilot_status)

        if copilot_service.is_running:
            logger.info("Chat panel connected (service already running)")
        else:
            logger.info("Chat panel: starting CopilotService...")

            def _start() -> None:
                success = copilot_service.start()
                logger.info("CopilotService.start() returned %s", success)

                def _update() -> None:
                    if success:
                        announce_to_screen_reader("Copilot connected")
                    else:
                        from bits_whisperer.core.sdk_installer import is_sdk_available

                        if not is_sdk_available("copilot_sdk"):
                            announce_to_screen_reader(
                                "Copilot is still being prepared. "
                                "It will finish automatically when needed."
                            )
                        else:
                            announce_to_screen_reader("Copilot connection failed. Check setup.")

                safe_call_after(_update)

            threading.Thread(target=_start, daemon=True).start()

    def _on_copilot_status(self, status: str, detail: str) -> None:
        """Handle SDK lifecycle status change notifications.

        Updates the status label so the user can see connection state.

        Args:
            status: Status key (starting, connected, disconnected, error).
            detail: Human-readable description.
        """

        def _update() -> None:
            if status == "connected":
                self._status_label.SetLabel("Ready \u2014 Copilot")
                announce_to_screen_reader(detail)
            elif status == "starting":
                self._status_label.SetLabel("Connecting\u2026")
            elif status == "error":
                self._status_label.SetLabel(f"Error \u2014 {detail}")
                announce_to_screen_reader(detail)
            elif status == "disconnected":
                self._status_label.SetLabel("Disconnected")

        safe_call_after(_update)

    def set_transcript_context(self, text: str) -> None:
        """Set the transcript text for context in conversations.

        Args:
            text: The full transcript text to use as context.
        """
        self._transcript_context = text
        if self._copilot_service:
            self._copilot_service.set_transcript_context(text)

        # Update status to show transcript and context budget info
        pid = self._get_selected_provider_id()
        if pid and self._available_providers:
            from bits_whisperer.core.ai_service import AIService

            svc = AIService(self._main_frame.key_store, self._settings.ai)
            display = svc.get_provider_display_name()
            if text:
                # Show context budget utilisation
                from bits_whisperer.core.context_manager import create_context_manager

                ctx_mgr = create_context_manager(self._settings.ai)
                model_id = svc._get_model_id()
                prepared = ctx_mgr.prepare_chat_context(
                    model=model_id,
                    provider=pid,
                    system_prompt="",
                    transcript=text,
                )
                budget_info = ctx_mgr.format_budget_summary(prepared.budget)
                self._status_label.SetLabel(f"Ready \u2014 {display} \u2022 {budget_info}")
                announce_to_screen_reader(f"Transcript loaded. {budget_info}")
            else:
                self._status_label.SetLabel(f"Ready \u2014 {display}")
                announce_to_screen_reader("Transcript context cleared")

    # ------------------------------------------------------------------ #
    # Welcome message                                                      #
    # ------------------------------------------------------------------ #

    def _show_welcome(self) -> None:
        """Display a provider-aware welcome message in the chat."""
        # Determine current provider name
        pid = self._get_selected_provider_id()
        provider_name = _PROVIDER_NAMES.get(pid, pid.title()) if pid else "None"

        # Use agent config welcome if Copilot + agent configured
        if (
            pid == "copilot"
            and self._copilot_service
            and self._copilot_service.agent_config.welcome_message
        ):
            welcome = self._copilot_service.agent_config.welcome_message
        else:
            welcome = (
                "AI Transcript Chat\n"
                "\u2501" * 36 + "\n\n"
                f"Provider:  {provider_name}\n\n"
                "I can help you analyze your transcripts:\n"
                "  \u2022  Summarize content and extract key points\n"
                "  \u2022  Find specific topics, quotes, or themes\n"
                "  \u2022  Identify speakers and their contributions\n"
                "  \u2022  Extract action items and decisions\n"
                "  \u2022  Translate sections to other languages\n"
                "  \u2022  Answer any question about your transcript\n\n"
                "Slash Commands (type / for autocomplete):\n"
                "  /summarize  /translate  /key-points  /action-items\n"
                "  /topics  /speakers  /search  /run  /export  /status\n"
                "  /help \u2014 show all commands\n\n"
                "Load a transcript, then ask me anything, use\n"
                "the quick action buttons, or type a /command.\n\n"
                "Tip: Switch providers using the dropdown above.\n"
                "     Configure keys in Tools \u2192 AI Provider Settings."
            )

        self._chat_display.SetValue(welcome + "\n\n")

    def _build_translate_prompt(self) -> str:
        """Build the quick translate prompt using the saved target language."""
        target_language = self._settings.ai.translation_target_language or "Spanish"
        return f"Translate this transcript to {target_language}, preserving speaker labels."

    def _update_interaction_state(self) -> None:
        """Enable or disable message controls based on readiness."""
        has_provider = bool(self._available_providers)
        model_name = self._get_selected_model_id() if has_provider else ""
        can_send = (
            has_provider
            and model_name
            not in {
                "Loading\u2026",
                "No models \u2014 choose Manage Models",
                "Set up an AI provider first",
            }
            and not self._is_streaming
        )
        self._send_btn.Enable(can_send)
        self._input_text.Enable(has_provider and not self._is_streaming)

    # ------------------------------------------------------------------ #
    # Message sending                                                      #
    # ------------------------------------------------------------------ #

    def _on_input_key(self, event: wx.KeyEvent) -> None:
        """Handle key events in the input field.

        Enter sends the message. Shift+Enter inserts a newline.
        Arrow keys navigate the autocomplete popup when visible.
        Escape dismisses the autocomplete popup.
        """
        keycode = event.GetKeyCode()

        # Forward navigation keys to the autocomplete popup
        if self._autocomplete_popup and self._autocomplete_popup.IsShown():
            if keycode == wx.WXK_DOWN:
                self._autocomplete_popup.select_next()
                return
            elif keycode == wx.WXK_UP:
                self._autocomplete_popup.select_prev()
                return
            elif keycode == wx.WXK_ESCAPE:
                self._autocomplete_popup.dismiss()
                return
            elif keycode == wx.WXK_TAB:
                self._autocomplete_popup.accept_selection()
                return
            elif keycode == wx.WXK_RETURN and not event.ShiftDown():
                # If popup is open and has selection, accept it
                if self._autocomplete_popup.has_selection():
                    self._autocomplete_popup.accept_selection()
                    return

        if keycode == wx.WXK_RETURN:
            if event.ShiftDown():
                event.Skip()  # Allow Shift+Enter to insert newline
            else:
                self._on_send(None)
                return
        event.Skip()

    def _on_input_text_changed(self, event: wx.CommandEvent) -> None:
        """Handle real-time text changes for slash command autocomplete.

        Shows a popup with matching commands when the user types ``/``.
        """
        event.Skip()
        text = self._input_text.GetValue()

        if not text.startswith("/"):
            self._dismiss_autocomplete()
            return

        # Extract the partial command (everything after / up to first space)
        parts = text[1:].split(None, 1)
        prefix = parts[0] if parts else ""

        # If there's already a space after the command name, dismiss
        if len(parts) > 1:
            self._dismiss_autocomplete()
            return

        # Find matching commands
        matches = self._slash_registry.match(prefix)
        if matches:
            self._show_autocomplete(matches)
        else:
            self._dismiss_autocomplete()

    def _show_autocomplete(self, commands: list) -> None:
        """Show the autocomplete popup with matching commands.

        Args:
            commands: List of SlashCommand objects to display.
        """
        if not self._autocomplete_popup:
            self._autocomplete_popup = _SlashAutocompletePopup(self, self._input_text)

        self._autocomplete_popup.update_commands(commands)
        self._autocomplete_popup.show_at_input()

    def _dismiss_autocomplete(self) -> None:
        """Hide and dismiss the autocomplete popup."""
        if self._autocomplete_popup and self._autocomplete_popup.IsShown():
            self._autocomplete_popup.dismiss()

    def _on_send(self, _event: wx.CommandEvent | None) -> None:
        """Send the user's message to the AI assistant.

        Intercepts slash commands (``/foo args``) and routes them
        to the command handler instead of sending to the AI provider.
        """
        self._dismiss_autocomplete()
        message = self._input_text.GetValue().strip()
        if not message:
            return

        if self._is_streaming:
            announce_status(
                self._main_frame,
                "Please wait for the current response to complete.",
            )
            return

        if not self._available_providers:
            announce_status(
                self._main_frame,
                "Set up an AI provider before sending a message.",
            )
            return

        # Intercept slash commands
        parsed = parse_slash_command(message)
        if parsed:
            cmd_name, cmd_args = parsed
            self._execute_slash_command(cmd_name, cmd_args)
            return

        self._send_message(message)

    def _execute_slash_command(self, name: str, args: str) -> None:
        """Look up and execute a slash command.

        Args:
            name: Command name (without leading ``/``).
            args: Arguments string after the command name.
        """
        cmd = self._slash_registry.get(name)
        if not cmd:
            # Suggest closest matches
            suggestions = self._slash_registry.match(name)
            self._input_text.SetValue("")
            if suggestions:
                suggestion_text = ", ".join(f"/{s.name}" for s in suggestions[:5])
                self._append_message(
                    "System",
                    f"Unknown command '/{name}'.\n"
                    f"Did you mean: {suggestion_text}\n"
                    f"Type /help to see all commands.",
                )
            else:
                self._append_message(
                    "System",
                    f"Unknown command '/{name}'.\nType /help to see all available commands.",
                )
            return

        # Check if command requires a transcript
        if cmd.requires_transcript and not self._transcript_context:
            self._input_text.SetValue("")
            self._append_message(
                "System",
                f"/{cmd.name} requires a loaded transcript.\n"
                "Transcribe a file first, then try again.",
            )
            return

        # Clear input and execute
        self._input_text.SetValue("")
        try:
            cmd.handler(self, args)
        except Exception as exc:
            logger.exception("Slash command '/%s' failed", name)
            self._append_message(
                "System",
                f"Command /{name} failed: {exc}",
            )

    def _send_quick_action(self, prompt: str) -> None:
        """Send a quick action prompt.

        Args:
            prompt: The pre-defined prompt to send.
        """
        if self._is_streaming:
            announce_status(
                self._main_frame,
                "Please wait for the current response to complete.",
            )
            return
        self._send_message(prompt)

    def _send_message(self, message: str) -> None:
        """Send a message to the selected AI provider with streaming.

        Routes to CopilotService when Copilot is selected and running,
        otherwise uses the unified AIService streaming chat.

        Args:
            message: The message to send.
        """
        # Display user message
        self._append_message("You", message)
        self._input_text.SetValue("")
        self._is_streaming = True
        self._update_interaction_state()

        # Track in conversation history
        self._conversation_history.append({"role": "user", "content": message})

        pid = self._get_selected_provider_id()

        # Enhanced path: Copilot SDK with tools + streaming
        if pid == "copilot" and self._copilot_service and self._copilot_service.is_running:
            logger.info("Sending via Copilot SDK (len=%d)", len(message))
            self._send_via_copilot(message)
        else:
            logger.info("Sending via AIService/%s (len=%d)", pid, len(message))
            self._send_via_ai_service(message)

    def _send_via_copilot(self, message: str) -> None:
        """Send via the Copilot SDK with streaming support.

        Args:
            message: The user's message.
        """

        self._append_header("Assistant")
        self._status_label.SetLabel("Thinking\u2026")
        announce_to_screen_reader("Thinking")

        def on_delta(delta: str) -> None:
            safe_call_after(self._append_streaming_text, delta)

        def on_complete(msg: CopilotMessage) -> None:
            logger.info(
                "Copilot response complete (len=%d, model=%s)",
                len(msg.content),
                msg.model,
            )
            self._conversation_history.append({"role": "assistant", "content": msg.content})

            def _done() -> None:
                self._append_text("\n\n")
                self._finalize_response()
                self._status_label.SetLabel(f"Ready \u2014 Copilot ({msg.model})")
                announce_status(self._main_frame, "Response complete")

            safe_call_after(_done)

        def on_error(error: str) -> None:
            logger.error("Copilot chat error: %s", error)

            def _err() -> None:
                self._append_text(f"\n[Error: {error}]\n\n")
                self._finalize_response()
                self._status_label.SetLabel("Error")
                announce_to_screen_reader(f"Chat error: {error}")

            safe_call_after(_err)

        service = self._copilot_service
        if service is None:
            self._append_text("\n[Copilot is not connected yet.]\n\n")
            self._finalize_response()
            return

        service.send_message(
            message,
            on_delta=on_delta,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _send_via_ai_service(self, message: str) -> None:
        """Send via the unified AIService with streaming for all providers.

        Uses the full conversation history so the model sees the
        complete multi-turn context.

        Args:
            message: The user's message.
        """
        from bits_whisperer.core.ai_service import AIService

        self._append_header("Assistant")
        self._status_label.SetLabel("Thinking\u2026")
        announce_to_screen_reader("Thinking")

        settings = AppSettings.load()
        settings.ai.selected_provider = self._get_selected_provider_id()

        # Use per-session model override (not persisted to disk)
        chat_model = self._session_model or self._get_selected_model_id()
        if chat_model and chat_model not in (
            "Default",
            "Loading\u2026",
            "No models \u2014 choose Manage Models",
        ):
            pid = settings.ai.selected_provider
            if pid == "openai":
                settings.ai.openai_model = chat_model
            elif pid == "anthropic":
                settings.ai.anthropic_model = chat_model
            elif pid == "gemini":
                settings.ai.gemini_model = chat_model
            elif pid == "copilot":
                settings.ai.copilot_model = chat_model
            elif pid == "ollama":
                settings.ai.ollama_model = chat_model

        ai_service = AIService(self._main_frame.key_store, settings.ai)

        if not ai_service.is_configured():
            self._append_text(
                "\n[No AI provider is ready yet. Open AI > Copilot Setup to sign in with "
                "GitHub, or open Tools > AI Provider Settings to use another provider.]\n\n"
            )
            self._finalize_response()
            return

        def on_delta(delta: str) -> None:
            safe_call_after(self._append_streaming_text, delta)

        def on_complete(response) -> None:
            self._conversation_history.append({"role": "assistant", "content": response.text})

            def _done() -> None:
                self._append_text("\n\n")
                self._finalize_response()
                display = f"{response.provider}/{response.model}"
                self._status_label.SetLabel(f"Ready \u2014 {display}")
                announce_status(self._main_frame, "Response complete")

            safe_call_after(_done)

        def on_error(error: str) -> None:
            logger.error("AI chat error: %s", error)

            def _err() -> None:
                self._append_text(f"\n[Error: {error}]\n\n")
                self._finalize_response()
                self._status_label.SetLabel("Error")
                announce_to_screen_reader(f"Chat error: {error}")

            safe_call_after(_err)

        ai_service.chat(
            self._conversation_history,
            transcript_context=self._transcript_context,
            system_prompt=self._session_system_prompt,
            on_delta=on_delta,
            on_complete=on_complete,
            on_error=on_error,
        )

    # ------------------------------------------------------------------ #
    # Display helpers                                                      #
    # ------------------------------------------------------------------ #

    def _append_message(self, sender: str, text: str) -> None:
        """Append a complete message to the chat display.

        Args:
            sender: The sender label (e.g. "You", "Assistant").
            text: The message text.
        """
        self._chat_display.AppendText(f"{sender}:\n{text}\n\n")
        self._scroll_to_bottom()

    def _append_header(self, sender: str) -> None:
        """Append a sender header for a streaming response.

        Args:
            sender: The sender label.
        """
        self._chat_display.AppendText(f"{sender}:\n")

    def _append_streaming_text(self, text: str) -> None:
        """Append streaming text to the chat display.

        Args:
            text: Text chunk to append.
        """
        self._chat_display.AppendText(text)
        self._scroll_to_bottom()

    def _append_text(self, text: str) -> None:
        """Append arbitrary text to the chat display.

        Args:
            text: Text to append.
        """
        self._chat_display.AppendText(text)
        self._scroll_to_bottom()

    def _finalize_response(self) -> None:
        """Finalize a streaming response — re-enable input."""
        self._is_streaming = False
        self._update_interaction_state()
        self._input_text.SetFocus()

    def _scroll_to_bottom(self) -> None:
        """Scroll the chat display to the bottom."""
        self._chat_display.ShowPosition(self._chat_display.GetLastPosition())

    # ------------------------------------------------------------------ #
    # Context menus                                                        #
    # ------------------------------------------------------------------ #

    def _on_display_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        """Right-click context menu for the chat display."""
        menu = wx.Menu()
        has_text = self._chat_display.GetValue() != ""
        has_selection = self._chat_display.GetStringSelection() != ""

        sel_item = menu.Append(wx.ID_ANY, "Select &All\tCtrl+A")
        self.Bind(wx.EVT_MENU, lambda e: self._chat_display.SelectAll(), sel_item)
        sel_item.Enable(has_text)

        copy_item = menu.Append(wx.ID_ANY, "&Copy\tCtrl+C")
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._copy_display_selection(),
            copy_item,
        )
        copy_item.Enable(has_selection)

        copy_all = menu.Append(wx.ID_ANY, "Copy A&ll")
        self.Bind(wx.EVT_MENU, lambda e: self._copy_all_display(), copy_all)
        copy_all.Enable(has_text)

        menu.AppendSeparator()

        clear_item = menu.Append(wx.ID_ANY, "C&lear Conversation")
        self.Bind(wx.EVT_MENU, self._on_clear, clear_item)
        clear_item.Enable(has_text)

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_input_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        """Right-click context menu for the message input."""
        menu = wx.Menu()
        has_text = self._input_text.GetValue() != ""
        has_selection = self._input_text.GetStringSelection() != ""

        cut_item = menu.Append(wx.ID_ANY, "Cu&t\tCtrl+X")
        self.Bind(wx.EVT_MENU, lambda e: self._input_text.Cut(), cut_item)
        cut_item.Enable(has_selection)

        copy_item = menu.Append(wx.ID_ANY, "&Copy\tCtrl+C")
        self.Bind(wx.EVT_MENU, lambda e: self._input_text.Copy(), copy_item)
        copy_item.Enable(has_selection)

        paste_item = menu.Append(wx.ID_ANY, "&Paste\tCtrl+V")
        self.Bind(wx.EVT_MENU, lambda e: self._input_text.Paste(), paste_item)

        menu.AppendSeparator()

        sel_item = menu.Append(wx.ID_ANY, "Select &All\tCtrl+A")
        self.Bind(wx.EVT_MENU, lambda e: self._input_text.SelectAll(), sel_item)
        sel_item.Enable(has_text)

        clear_item = menu.Append(wx.ID_ANY, "C&lear")
        self.Bind(wx.EVT_MENU, lambda e: self._input_text.SetValue(""), clear_item)
        clear_item.Enable(has_text)

        self.PopupMenu(menu)
        menu.Destroy()

    def _copy_display_selection(self) -> None:
        """Copy selected text from the chat display."""
        text = self._chat_display.GetStringSelection()
        if text and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            announce_status(self._main_frame, "Selection copied to clipboard")

    def _copy_all_display(self) -> None:
        """Copy all text from the chat display."""
        text = self._chat_display.GetValue()
        if text and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            announce_status(self._main_frame, "Conversation copied to clipboard")

    # ------------------------------------------------------------------ #
    # Clear / Reset                                                        #
    # ------------------------------------------------------------------ #

    def _on_clear(self, _event: wx.CommandEvent) -> None:
        """Clear the conversation history and reset the chat."""
        has_content = bool(self._conversation_history or self._chat_display.GetValue().strip())
        if has_content:
            result = accessible_message_box(
                "Clear the current conversation and start fresh?",
                "Clear Conversation",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                self,
            )
            if result != wx.YES:
                announce_status(self._main_frame, "Clear cancelled")
                return
        self._conversation_history.clear()
        if self._copilot_service:
            self._copilot_service.clear_conversation()
        self._chat_display.SetValue("")
        self._show_welcome()
        announce_status(self._main_frame, "Conversation cleared")


# ====================================================================== #
# Autocomplete popup for slash commands                                   #
# ====================================================================== #


class _SlashAutocompletePopup(wx.PopupTransientWindow):
    """A transient popup that shows matching slash commands.

    Appears just above the input field as the user types ``/`` followed
    by a partial command name.  The list updates as the user types and
    supports keyboard navigation (Up/Down) and selection (Tab/Enter).
    """

    _MAX_VISIBLE = 8  # Max items before scrolling

    def __init__(self, panel: CopilotChatPanel, anchor: wx.TextCtrl) -> None:
        """Initialise the autocomplete popup.

        Args:
            panel: The parent chat panel.
            anchor: The text control the popup is anchored to.
        """
        super().__init__(panel, style=wx.BORDER_SIMPLE)
        self._panel = panel
        self._anchor = anchor
        self._commands: list = []

        self._listbox = wx.ListBox(self, style=wx.LB_SINGLE | wx.LB_NEEDED_SB)
        set_accessible_name(self._listbox, "Slash command suggestions")
        self._listbox.Bind(wx.EVT_LISTBOX_DCLICK, self._on_double_click)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._listbox, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def update_commands(self, commands: list) -> None:
        """Refresh the list with the given matching commands.

        Args:
            commands: List of SlashCommand objects to display.
        """
        self._commands = commands
        self._listbox.Clear()
        for cmd in commands:
            hint = f"  {cmd.arg_hint}" if cmd.arg_hint else ""
            label = f"/{cmd.name}{hint} — {cmd.description}"
            self._listbox.Append(label)

        if self._listbox.GetCount() > 0:
            self._listbox.SetSelection(0)

        # Size the popup
        visible = min(len(commands), self._MAX_VISIBLE)
        item_height = self._listbox.GetCharHeight() + 4
        height = max(visible * item_height, item_height)
        width = max(self._anchor.GetSize().GetWidth(), 300)
        self.SetSize(width, height + 4)
        self._listbox.SetSize(width, height + 4)

    def show_at_input(self) -> None:
        """Position the popup just above the input field and show it."""
        pos = self._anchor.GetScreenPosition()
        popup_height = self.GetSize().GetHeight()
        # Place above the input
        x = pos.x
        y = pos.y - popup_height - 2
        if y < 0:
            # Fall back to below the input
            y = pos.y + self._anchor.GetSize().GetHeight() + 2
        self.SetPosition(wx.Point(x, y))
        self.Show()
        # Keep focus in the text control
        self._anchor.SetFocus()

    def select_next(self) -> None:
        """Move selection down in the list."""
        count = self._listbox.GetCount()
        if count == 0:
            return
        sel = self._listbox.GetSelection()
        if sel < count - 1:
            self._listbox.SetSelection(sel + 1)

    def select_prev(self) -> None:
        """Move selection up in the list."""
        count = self._listbox.GetCount()
        if count == 0:
            return
        sel = self._listbox.GetSelection()
        if sel > 0:
            self._listbox.SetSelection(sel - 1)

    def has_selection(self) -> bool:
        """Return whether an item is currently selected."""
        return self._listbox.GetSelection() != wx.NOT_FOUND

    def accept_selection(self) -> None:
        """Insert the selected command into the input field and dismiss."""
        sel = self._listbox.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._commands):
            self.dismiss()
            return
        cmd = self._commands[sel]
        # Insert "/<command> " into the text control
        text = f"/{cmd.name} "
        self._anchor.SetValue(text)
        self._anchor.SetInsertionPointEnd()
        self.dismiss()

    def dismiss(self) -> None:
        """Hide the popup."""
        self.Hide()

    def _on_double_click(self, _event: wx.CommandEvent) -> None:
        """Accept the double-clicked item."""
        self.accept_selection()
