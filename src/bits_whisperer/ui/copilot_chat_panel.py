"""Interactive Copilot chat panel for transcript analysis.

Embeds an AI-powered chat interface alongside the transcript,
allowing users to ask questions about their transcripts, get
summaries, find topics, and more — all with streaming responses.

Features:
- Streaming response display with real-time text updates
- Multi-turn conversation with persistent context
- Quick action buttons for common operations
- Transcript context auto-injection
- Full keyboard navigation and screen reader support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.copilot_service import CopilotMessage, CopilotService
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


class CopilotChatPanel(wx.Panel):
    """Interactive chat panel for AI-powered transcript analysis.

    Provides a conversational interface where users can ask questions
    about their transcripts using GitHub Copilot or other AI providers.
    Supports streaming responses, quick actions, and multi-turn
    conversations.
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        """Initialise the chat panel.

        Args:
            parent: Parent window (typically the main frame or splitter).
            main_frame: Reference to the main application frame.
        """
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        set_accessible_name(self, "AI Transcript Assistant")
        make_panel_accessible(self)

        self._main_frame = main_frame
        self._settings = AppSettings.load()
        self._copilot_service: CopilotService | None = None
        self._is_streaming = False

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the chat panel layout."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header bar
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        header_label = wx.StaticText(self, label="AI Transcript Assistant")
        font = header_label.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header_label.SetFont(font)
        set_accessible_name(header_label, "AI Transcript Assistant panel")
        header_sizer.Add(header_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        # Status indicator
        self._status_label = wx.StaticText(self, label="Not connected")
        self._status_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        set_accessible_name(self._status_label, "Connection status")
        header_sizer.Add(self._status_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Clear button
        clear_btn = wx.Button(self, label="Clea&r")
        set_accessible_name(clear_btn, "Clear conversation")
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear)
        header_sizer.Add(clear_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 4)
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND)

        # Chat display area
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
            "Shows the conversation with the AI assistant. " "New messages appear at the bottom.",
        )
        main_sizer.Add(self._chat_display, 1, wx.EXPAND | wx.ALL, 4)

        # Quick actions bar
        action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        action_label = wx.StaticText(self, label="Quick:")
        set_accessible_name(action_label, "Quick actions")
        action_sizer.Add(action_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        quick_actions = [
            ("&Summarize", "Please provide a concise summary of this transcript."),
            ("&Key Points", "List the key points and action items as bullet points."),
            ("&Topics", "What are the main topics discussed in this transcript?"),
            ("S&peakers", "Identify and describe each speaker in this transcript."),
        ]

        for label, prompt in quick_actions:
            btn = wx.Button(self, label=label, size=(-1, -1))
            set_accessible_name(btn, f"Quick action: {label.replace('&', '')}")
            btn.Bind(
                wx.EVT_BUTTON,
                lambda e, p=prompt: self._send_quick_action(p),
            )
            action_sizer.Add(btn, 0, wx.LEFT, 4)

        main_sizer.Add(action_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Input area
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
            "click Send. Press Shift+Enter for a new line.",
        )
        self._input_text.Bind(wx.EVT_TEXT_ENTER, self._on_send)
        self._input_text.Bind(wx.EVT_KEY_DOWN, self._on_input_key)
        input_sizer.Add(self._input_text, 1, wx.EXPAND | wx.RIGHT, 4)

        self._send_btn = wx.Button(self, label="&Send")
        set_accessible_name(self._send_btn, "Send message")
        self._send_btn.Bind(wx.EVT_BUTTON, self._on_send)
        input_sizer.Add(self._send_btn, 0, wx.EXPAND)

        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        self.SetSizer(main_sizer)

        # Show welcome message
        self._show_welcome()

    # ------------------------------------------------------------------ #
    # Service management                                                   #
    # ------------------------------------------------------------------ #

    def connect(self, copilot_service: CopilotService) -> None:
        """Connect to a CopilotService instance.

        Args:
            copilot_service: The service to use for AI interactions.
        """
        self._copilot_service = copilot_service
        if copilot_service.is_running:
            self._status_label.SetLabel("Connected")
        else:
            self._status_label.SetLabel("Starting...")
            # Try to start
            import threading

            def _start() -> None:
                success = copilot_service.start()
                safe_call_after(
                    self._status_label.SetLabel,
                    "Connected" if success else "Connection failed",
                )

            threading.Thread(target=_start, daemon=True).start()

    def set_transcript_context(self, text: str) -> None:
        """Set the transcript text for context.

        Args:
            text: The full transcript text to use as context.
        """
        if self._copilot_service:
            self._copilot_service.set_transcript_context(text)
            self._status_label.SetLabel("Connected (transcript loaded)")

    # ------------------------------------------------------------------ #
    # Welcome message                                                      #
    # ------------------------------------------------------------------ #

    def _show_welcome(self) -> None:
        """Display the welcome message in the chat."""
        welcome = (
            "Welcome to the AI Transcript Assistant!\n\n"
            "I can help you analyze your transcripts:\n"
            "  \u2022  Summarize content\n"
            "  \u2022  Find specific topics or quotes\n"
            "  \u2022  Identify speakers\n"
            "  \u2022  Extract action items\n"
            "  \u2022  Translate sections\n\n"
            "Load a transcript and ask me anything, or use the quick "
            "action buttons above the input box.\n\n"
            "Tip: Use the AI menu to configure your preferred AI provider."
        )

        # Use agent config welcome if available
        if self._copilot_service and self._copilot_service.agent_config.welcome_message:
            welcome = self._copilot_service.agent_config.welcome_message

        self._chat_display.SetValue(welcome + "\n\n")

    # ------------------------------------------------------------------ #
    # Message sending                                                      #
    # ------------------------------------------------------------------ #

    def _on_input_key(self, event: wx.KeyEvent) -> None:
        """Handle key events in the input field.

        Enter sends the message. Shift+Enter inserts a newline.
        """
        if event.GetKeyCode() == wx.WXK_RETURN:
            if event.ShiftDown():
                event.Skip()  # Allow Shift+Enter to insert newline
            else:
                self._on_send(None)
                return
        event.Skip()

    def _on_send(self, _event: wx.CommandEvent | None) -> None:
        """Send the user's message to the AI assistant."""
        message = self._input_text.GetValue().strip()
        if not message:
            return

        if self._is_streaming:
            announce_status(
                self._main_frame,
                "Please wait for the current response to complete.",
            )
            return

        self._send_message(message)

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
        """Send a message to the AI service and display the response.

        Args:
            message: The message to send.
        """
        # Display user message
        self._append_message("You", message)
        self._input_text.SetValue("")
        self._is_streaming = True
        self._send_btn.Disable()

        # Check if we have a copilot service
        if self._copilot_service and self._copilot_service.is_running:
            self._send_via_copilot(message)
        else:
            # Fall back to the standard AI service
            self._send_via_ai_service(message)

    def _send_via_copilot(self, message: str) -> None:
        """Send via the Copilot SDK with streaming support.

        Args:
            message: The user's message.
        """
        self._append_header("Assistant")
        self._status_label.SetLabel("Thinking...")

        def on_delta(delta: str) -> None:
            """Handle streaming text chunks."""
            safe_call_after(self._append_streaming_text, delta)

        def on_complete(msg: CopilotMessage) -> None:
            """Handle completed response."""

            def _done() -> None:
                self._finalize_response()
                self._status_label.SetLabel("Connected")
                announce_status(self._main_frame, "Assistant response complete")

            safe_call_after(_done)

        def on_error(error: str) -> None:
            """Handle errors."""

            def _err() -> None:
                self._append_text(f"\n[Error: {error}]\n\n")
                self._finalize_response()
                self._status_label.SetLabel("Error")

            safe_call_after(_err)

        self._copilot_service.send_message(
            message,
            on_delta=on_delta,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _send_via_ai_service(self, message: str) -> None:
        """Fall back to the standard AIService for response.

        Args:
            message: The user's message.
        """
        import threading

        from bits_whisperer.core.ai_service import AIService

        self._append_header("Assistant")
        self._status_label.SetLabel("Processing...")

        def _do_send() -> None:
            try:
                settings = AppSettings.load()
                ai_service = AIService(self._main_frame.key_store, settings.ai)

                if not ai_service.is_configured():
                    safe_call_after(
                        self._append_text,
                        (
                            "\n[No AI provider configured. Go to Tools > "
                            "AI Provider Settings to add an API key.]\n\n"
                        ),
                    )
                    safe_call_after(self._finalize_response)
                    return

                # Build a prompt with transcript context
                prompt = message
                if self._copilot_service and self._copilot_service._transcript_context:
                    transcript = self._copilot_service._transcript_context[:50000]
                    prompt = (
                        f"Given this transcript:\n\n{transcript}\n\n" f"User question: {message}"
                    )

                # Use the AI service for generation
                response = ai_service.summarize(prompt, style="detailed")

                def _show() -> None:
                    if response.error:
                        self._append_text(f"\n[Error: {response.error}]\n\n")
                    else:
                        self._append_streaming_text(response.text)
                        self._append_text("\n\n")
                    self._finalize_response()
                    self._status_label.SetLabel(f"Ready ({response.provider}/{response.model})")

                safe_call_after(_show)

            except Exception as exc:
                safe_call_after(self._append_text, f"\n[Error: {exc}]\n\n")
                safe_call_after(self._finalize_response)

        threading.Thread(target=_do_send, daemon=True).start()

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
        self._send_btn.Enable()
        self._input_text.SetFocus()

    def _scroll_to_bottom(self) -> None:
        """Scroll the chat display to the bottom."""
        self._chat_display.ShowPosition(self._chat_display.GetLastPosition())

    # ------------------------------------------------------------------ #
    # Clear / Reset                                                        #
    # ------------------------------------------------------------------ #

    def _on_clear(self, _event: wx.CommandEvent) -> None:
        """Clear the conversation history."""
        if self._copilot_service:
            self._copilot_service.clear_conversation()
        self._chat_display.SetValue("")
        self._show_welcome()
        announce_status(self._main_frame, "Conversation cleared")
