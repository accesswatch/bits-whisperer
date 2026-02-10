"""GitHub Copilot SDK integration service.

Wraps the ``github-copilot-sdk`` Python package to provide:
- Copilot CLI lifecycle management (auto-start, health checks)
- Session creation with configurable models and streaming
- Custom transcript analysis tools (search, speakers, segments)
- Async-to-wxPython bridge for streaming UI updates
- Agent configuration management

Architecture
------------
App → CopilotService → github-copilot-sdk → JSON-RPC → Copilot CLI
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bits_whisperer.core.settings import CopilotSettings
    from bits_whisperer.storage.key_store import KeyStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent configuration data model
# ---------------------------------------------------------------------------


@dataclass
class Attachment:
    """A file attached as supplementary context for AI actions.

    Attachments provide additional reference material that the AI can use
    alongside the transcript — e.g. meeting agendas, project specs, style guides.
    Each attachment can have optional per-attachment instructions.
    """

    file_path: str  # Absolute path to the attached file
    instructions: str = ""  # Per-attachment instructions (e.g. "Use this as a glossary")
    display_name: str = ""  # Friendly display name (defaults to filename if empty)

    @property
    def name(self) -> str:
        """Display name or filename."""
        return self.display_name or Path(self.file_path).name

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "file_path": self.file_path,
            "instructions": self.instructions,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attachment:
        """Deserialize from a dict."""
        return cls(
            file_path=data.get("file_path", ""),
            instructions=data.get("instructions", ""),
            display_name=data.get("display_name", ""),
        )


@dataclass
class AgentConfig:
    """Configuration for a custom Copilot agent.

    Used by the Agent Builder dialog to create a guided experience
    for users — they don't need to know Markdown or metadata syntax.
    """

    name: str = "BITS Transcript Assistant"
    description: str = "An AI assistant for analyzing audio transcripts"
    instructions: str = (
        "You are a helpful transcript assistant. You help users understand, "
        "analyze, and work with audio transcripts. You can summarize content, "
        "identify speakers, find specific topics, and answer questions about "
        "the transcript. Be concise, clear, and helpful."
    )
    model: str = "gpt-4o"
    tools_enabled: list[str] = field(
        default_factory=lambda: [
            "search_transcript",
            "get_speakers",
            "get_transcript_stats",
        ]
    )
    temperature: float = 0.3
    max_tokens: int = 4096
    welcome_message: str = (
        "Hello! I'm your transcript assistant. I can help you:\n"
        "• Summarize the transcript\n"
        "• Find specific topics or quotes\n"
        "• Identify speakers and their contributions\n"
        "• Answer questions about the content\n"
        "• Translate sections\n\n"
        "What would you like to know?"
    )
    attachments: list[Attachment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        d = asdict(self)
        # Serialize attachments explicitly for clarity
        d["attachments"] = [a.to_dict() for a in self.attachments]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """Deserialize from a dict, ignoring unknown keys."""
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid}
        # Deserialize attachments from list of dicts
        if "attachments" in filtered and isinstance(filtered["attachments"], list):
            filtered["attachments"] = [
                Attachment.from_dict(a) if isinstance(a, dict) else a
                for a in filtered["attachments"]
            ]
        return cls(**filtered)

    def save(self, path: Path) -> None:
        """Save configuration to a JSON file."""
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> AgentConfig:
        """Load configuration from a JSON file."""
        data = json.loads(path.read_text("utf-8"))
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Streaming callback types
# ---------------------------------------------------------------------------


@dataclass
class CopilotMessage:
    """A message in the Copilot chat conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    model: str = ""
    is_streaming: bool = False
    is_complete: bool = True


# ---------------------------------------------------------------------------
# Copilot Service
# ---------------------------------------------------------------------------


class CopilotService:
    """High-level service for GitHub Copilot SDK integration.

    Manages the Copilot CLI lifecycle, session creation, and
    provides a synchronous-friendly API for wxPython integration.

    Usage::

        service = CopilotService(key_store, settings)
        if service.is_available():
            service.start()
            service.send_message(
                "Summarize this transcript",
                transcript_text=text,
                on_delta=lambda delta: print(delta, end=""),
                on_complete=lambda msg: print("\\nDone:", msg.content),
            )
    """

    def __init__(
        self,
        key_store: KeyStore,
        settings: CopilotSettings,
    ) -> None:
        self._key_store = key_store
        self._settings = settings
        self._client: Any | None = None
        self._session: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._agent_config = AgentConfig()
        self._conversation_history: list[CopilotMessage] = []
        self._transcript_context: str = ""
        self._is_running = False

    # ------------------------------------------------------------------ #
    # Availability checks                                                  #
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """Check whether the Copilot SDK is available.

        The SDK bundles its own CLI binary, so no separate CLI
        installation is needed.

        Returns:
            True if the SDK is importable.
        """
        sdk_ok = self.is_sdk_installed()
        logger.debug(
            "Copilot availability check: sdk_installed=%s",
            sdk_ok,
        )
        return sdk_ok

    @staticmethod
    def is_sdk_installed() -> bool:
        """Check if the github-copilot-sdk package is installed.

        Invalidates import caches first to detect newly-installed packages.
        """
        import importlib

        importlib.invalidate_caches()
        try:
            import copilot

            logger.debug(
                "Copilot SDK is installed (module location: %s)",
                getattr(copilot, "__file__", "unknown"),
            )
            return True
        except ImportError as exc:
            logger.debug("Copilot SDK not importable: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Event loop management                                                #
    # ------------------------------------------------------------------ #

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create the background event loop for async operations."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                daemon=True,
                name="copilot-event-loop",
            )
            self._thread.start()
        return self._loop

    def _run_async(self, coro) -> Any:
        """Run an async coroutine on the background event loop.

        Args:
            coro: Coroutine to execute.

        Returns:
            Result of the coroutine.
        """
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120)

    # ------------------------------------------------------------------ #
    # Client lifecycle                                                     #
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """Start the Copilot client and create an initial session.

        Returns:
            True if the client started successfully.
        """
        if self._is_running:
            logger.debug("Copilot client already running, skipping start")
            return True

        try:
            from copilot import CopilotClient
        except ImportError:
            logger.error(
                "github-copilot-sdk not installed — cannot start Copilot. "
                "Install with: pip install github-copilot-sdk"
            )
            return False

        try:
            client_kwargs: dict[str, Any] = {
                "auto_start": self._settings.auto_start_cli,
            }

            # Auth — prefer stored token, fall back to logged-in user
            token = self._key_store.get_key("copilot_github_token")
            if token:
                client_kwargs["github_token"] = token
                auth_method = self._settings.auth_method
                logger.info(
                    "Copilot auth: using stored token (method=%s, prefix=%s...)",
                    auth_method,
                    token[:7] if len(token) > 7 else "***",
                )
            elif self._settings.use_logged_in_user:
                client_kwargs["use_logged_in_user"] = True
                logger.info("Copilot auth: using logged-in CLI user")
            else:
                logger.warning(
                    "Copilot auth: no token and use_logged_in_user=False — "
                    "authentication may fail"
                )

            # The SDK bundles its own CLI binary; only override if
            # the user has explicitly configured a custom path.
            if self._settings.cli_path:
                client_kwargs["cli_path"] = self._settings.cli_path
                logger.info("Copilot CLI path (custom): %s", self._settings.cli_path)

            # Log sanitised client kwargs (redact token)
            log_kwargs = {k: ("***" if "token" in k else v) for k, v in client_kwargs.items()}
            logger.info("Creating CopilotClient with options: %s", log_kwargs)

            self._client = CopilotClient(client_kwargs)
            logger.debug("CopilotClient created, calling start()...")
            self._run_async(self._client.start())
            self._is_running = True
            logger.info("Copilot client started successfully")
            return True

        except Exception as exc:
            logger.exception("Failed to start Copilot client: %s", exc)
            return False

    def stop(self) -> None:
        """Stop the Copilot client and clean up resources."""
        logger.debug("Stopping Copilot client...")
        if self._session:
            try:
                self._run_async(self._session.destroy())
                logger.debug("Copilot session destroyed")
            except Exception:
                logger.debug("Error destroying Copilot session (ignored)", exc_info=True)
            self._session = None

        if self._client and self._is_running:
            try:
                self._run_async(self._client.stop())
                logger.debug("Copilot client stopped via SDK")
            except Exception:
                logger.debug("Error stopping Copilot client (ignored)", exc_info=True)
            self._client = None
            self._is_running = False

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._loop.close()
            self._loop = None
            self._thread = None

        self._conversation_history.clear()
        logger.info("Copilot client stopped and resources cleaned up")

    @property
    def is_running(self) -> bool:
        """Whether the Copilot client is currently running."""
        return self._is_running

    # ------------------------------------------------------------------ #
    # Session management                                                   #
    # ------------------------------------------------------------------ #

    async def _create_session(self) -> Any:
        """Create a new Copilot session with configured options."""
        if not self._client:
            raise RuntimeError("Copilot client not started")

        session_kwargs: dict[str, Any] = {
            "model": self._settings.default_model,
            "streaming": self._settings.streaming,
        }

        # System message with transcript context
        system_msg = self._settings.system_message
        if self._agent_config.instructions:
            system_msg = self._agent_config.instructions
        if self._transcript_context:
            # Use context manager for model-aware fitting
            from bits_whisperer.core.context_manager import (
                ContextWindowManager,
                ContextWindowSettings,
            )

            ctx_settings = ContextWindowSettings()
            ctx_mgr = ContextWindowManager(ctx_settings)
            prepared = ctx_mgr.prepare_chat_context(
                model=self._settings.default_model,
                provider="copilot",
                system_prompt=system_msg,
                transcript=self._transcript_context,
                conversation_history=self._conversation_history,
            )
            if prepared.fitted_transcript:
                system_msg += (
                    "\n\n--- TRANSCRIPT CONTEXT ---\n"
                    + prepared.fitted_transcript
                    + "\n--- END TRANSCRIPT ---"
                )
            ctx_len = len(prepared.fitted_transcript)
            logger.debug("Transcript context attached to session (%d chars)", ctx_len)
        session_kwargs["system_message"] = system_msg

        # Add transcript tools if enabled
        if self._settings.allow_transcript_tools:
            tools = self._build_transcript_tools()
            if tools:
                session_kwargs["tools"] = tools
                logger.debug("Attached %d custom tools to session", len(tools))

        logger.info(
            "Creating Copilot session: model=%s, streaming=%s, system_msg_len=%d",
            session_kwargs["model"],
            session_kwargs["streaming"],
            len(system_msg),
        )
        try:
            session = await self._client.create_session(session_kwargs)
            logger.info("Copilot session created successfully")
            return session
        except Exception:
            logger.exception("Failed to create Copilot session")
            raise

    def _build_transcript_tools(self) -> list[Any] | None:
        """Build custom tools for transcript analysis.

        Returns:
            List of tool definitions, or None if tools are not available.
        """
        try:
            from copilot import define_tool
            from pydantic import BaseModel, Field

            transcript_text = self._transcript_context

            class SearchQuery(BaseModel):
                query: str = Field(description="Text or keyword to search for")

            @define_tool(
                name="search_transcript",
                description="Search the transcript for specific text, keywords, or topics",
            )
            def search_transcript(args: SearchQuery) -> str:
                if not transcript_text:
                    return "No transcript loaded."
                query_lower = args.query.lower()
                lines = transcript_text.split("\n")
                matches = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        matches.append(f"Line {i + 1}: {line.strip()}")
                if not matches:
                    return f"No matches found for '{args.query}'."
                return f"Found {len(matches)} match(es):\n" + "\n".join(matches[:20])

            class EmptyArgs(BaseModel):
                pass

            @define_tool(
                name="get_transcript_stats",
                description="Get statistics about the transcript (word count, line count, etc.)",
            )
            def get_transcript_stats(args: EmptyArgs) -> str:
                if not transcript_text:
                    return "No transcript loaded."
                lines = transcript_text.strip().split("\n")
                words = transcript_text.split()
                # Find unique speakers
                speakers = set()
                for line in lines:
                    if ":" in line:
                        speaker = line.split(":")[0].strip()
                        if len(speaker) < 50:  # Likely a speaker label
                            speakers.add(speaker)
                return (
                    f"Lines: {len(lines)}\n"
                    f"Words: {len(words)}\n"
                    f"Characters: {len(transcript_text)}\n"
                    f"Possible speakers: {', '.join(speakers) if speakers else 'Unknown'}"
                )

            return [search_transcript, get_transcript_stats]

        except ImportError:
            logger.debug("Pydantic not available — skipping tool definitions")
            return None

    # ------------------------------------------------------------------ #
    # Messaging                                                            #
    # ------------------------------------------------------------------ #

    def set_transcript_context(self, text: str) -> None:
        """Set the transcript text for context in conversations.

        Args:
            text: The full transcript text.
        """
        self._transcript_context = text
        # Reset session so context is refreshed
        if self._session:
            with contextlib.suppress(Exception):
                self._run_async(self._session.destroy())
            self._session = None

    def send_message(
        self,
        message: str,
        *,
        on_delta: Callable[[str], None] | None = None,
        on_complete: Callable[[CopilotMessage], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Send a message to Copilot and handle the response.

        Runs asynchronously on the background event loop. Callbacks
        are invoked from the background thread — use ``wx.CallAfter``
        in UI code.

        Args:
            message: The user's message text.
            on_delta: Called with each text chunk during streaming.
            on_complete: Called with the full response when done.
            on_error: Called with an error message if something fails.
        """
        logger.info("Sending Copilot message (len=%d)", len(message))
        self._conversation_history.append(CopilotMessage(role="user", content=message))

        def _do_send() -> None:
            try:
                result = self._run_async(self._async_send(message, on_delta=on_delta))
                self._conversation_history.append(result)
                logger.info(
                    "Copilot response received (len=%d, model=%s)",
                    len(result.content),
                    result.model,
                )
                if on_complete:
                    on_complete(result)
            except Exception as exc:
                logger.exception("Copilot send failed: %s", exc)
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=_do_send, daemon=True, name="copilot-send").start()

    async def _async_send(
        self,
        message: str,
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> CopilotMessage:
        """Send a message and collect the response asynchronously."""
        # Ensure we have a session
        if not self._session:
            logger.debug("No active session — creating a new one")
            self._session = await self._create_session()

        if self._settings.streaming and on_delta:
            # Streaming mode — collect deltas via event handler
            logger.debug("Sending message in streaming mode (len=%d)", len(message))
            full_text = ""
            error_msg = ""
            done_event = asyncio.Event()

            def _handle_event(event: Any) -> None:
                nonlocal full_text, error_msg
                event_type = getattr(event.type, "value", str(event.type))
                logger.debug("Copilot event: type=%s", event_type)
                if event_type == "assistant.message_delta":
                    # Streaming chunk — use delta_content per SDK docs
                    delta = getattr(event.data, "delta_content", "") or ""
                    if delta:
                        full_text += delta
                        on_delta(delta)
                elif event_type == "assistant.message":
                    # Final complete message
                    final = getattr(event.data, "content", "") or ""
                    logger.debug("Copilot final message received (len=%d)", len(final))
                    if not full_text and final:
                        # No streaming deltas were received — use the final message
                        full_text = final
                        on_delta(final)
                elif event_type == "session.idle":
                    logger.debug("Copilot session idle — response complete")
                    done_event.set()
                elif event_type in ("session.error", "error"):
                    error_msg = getattr(event.data, "message", "") or str(event.data)
                    logger.error("Copilot session error event: %s", error_msg)
                    done_event.set()
                else:
                    logger.debug(
                        "Copilot unhandled event type: %s (data=%s)",
                        event_type,
                        type(event.data).__name__,
                    )

            unsubscribe = self._session.on(_handle_event)
            try:
                await self._session.send({"prompt": message})
                await asyncio.wait_for(done_event.wait(), timeout=120)
            except TimeoutError:
                logger.error("Copilot streaming response timed out after 120s")
                if not full_text:
                    full_text = "[Response timed out after 120 seconds]"
            finally:
                unsubscribe()

            if error_msg and not full_text:
                full_text = f"[Error: {error_msg}]"

            return CopilotMessage(
                role="assistant",
                content=full_text,
                model=self._settings.default_model,
                is_complete=True,
            )
        else:
            # Non-streaming mode — use send_and_wait
            logger.debug("Sending message in non-streaming mode (len=%d)", len(message))
            response = await self._session.send_and_wait({"prompt": message})
            text = ""
            if response and hasattr(response, "data"):
                text = getattr(response.data, "content", "") or ""
            logger.debug("Non-streaming response received (len=%d)", len(text))
            return CopilotMessage(
                role="assistant",
                content=text,
                model=self._settings.default_model,
                is_complete=True,
            )

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text content from various response types."""
        if hasattr(response, "text"):
            return response.text or ""
        if hasattr(response, "content"):
            return response.content or ""
        if hasattr(response, "message"):
            msg = response.message
            if hasattr(msg, "content"):
                return msg.content or ""
        return str(response)

    # ------------------------------------------------------------------ #
    # Conversation management                                              #
    # ------------------------------------------------------------------ #

    def get_conversation_history(self) -> list[CopilotMessage]:
        """Get the current conversation history."""
        return list(self._conversation_history)

    def clear_conversation(self) -> None:
        """Clear the conversation history and reset the session."""
        self._conversation_history.clear()
        if self._session:
            with contextlib.suppress(Exception):
                self._run_async(self._session.destroy())
            self._session = None

    # ------------------------------------------------------------------ #
    # Agent configuration                                                  #
    # ------------------------------------------------------------------ #

    @property
    def agent_config(self) -> AgentConfig:
        """Get the current agent configuration."""
        return self._agent_config

    @agent_config.setter
    def agent_config(self, config: AgentConfig) -> None:
        """Set the agent configuration and reset the session."""
        self._agent_config = config
        # Reset session to pick up new instructions
        if self._session:
            with contextlib.suppress(Exception):
                self._run_async(self._session.destroy())
            self._session = None

    def load_agent_config(self, path: Path) -> AgentConfig:
        """Load agent configuration from a file.

        Args:
            path: Path to the JSON config file.

        Returns:
            The loaded AgentConfig.
        """
        self._agent_config = AgentConfig.load(path)
        return self._agent_config

    def save_agent_config(self, path: Path) -> None:
        """Save the current agent configuration to a file.

        Args:
            path: Path to save the JSON config file.
        """
        self._agent_config.save(path)

    # ------------------------------------------------------------------ #
    # Quick actions                                                        #
    # ------------------------------------------------------------------ #

    def get_quick_actions(self) -> list[dict[str, str]]:
        """Get available quick action prompts for the chat panel.

        Returns:
            List of dicts with 'label' and 'prompt' keys.
        """
        return [
            {
                "label": "Summarize",
                "prompt": "Please provide a concise summary of this transcript.",
            },
            {
                "label": "Key Points",
                "prompt": (
                    "List the key points, decisions, and action items "
                    "from this transcript as bullet points."
                ),
            },
            {
                "label": "Identify Speakers",
                "prompt": (
                    "Identify and describe each speaker in this transcript. "
                    "What are their main contributions to the conversation?"
                ),
            },
            {
                "label": "Find Topics",
                "prompt": (
                    "What are the main topics discussed in this transcript? "
                    "Organize them with brief descriptions."
                ),
            },
            {
                "label": "Action Items",
                "prompt": (
                    "Extract all action items, tasks, and follow-ups mentioned "
                    "in this transcript. Include who is responsible if mentioned."
                ),
            },
            {
                "label": "Translate",
                "prompt": (
                    "Translate this transcript to Spanish, preserving speaker "
                    "labels and formatting."
                ),
            },
        ]
