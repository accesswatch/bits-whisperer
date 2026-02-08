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
import shutil
import subprocess
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """Deserialize from a dict, ignoring unknown keys."""
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})

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
    # CLI detection                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_cli() -> str | None:
        """Detect the Copilot CLI installation path.

        Returns:
            Path to the copilot CLI binary, or None if not found.
        """
        # Check custom path first, then PATH
        cli = shutil.which("copilot")
        if cli:
            return cli
        # Common locations on Windows
        for candidate in [
            Path.home() / "AppData" / "Local" / "Programs" / "copilot" / "copilot.exe",
            Path("C:/Program Files/GitHub Copilot CLI/copilot.exe"),
        ]:
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def get_cli_version(cli_path: str | None = None) -> str | None:
        """Get the Copilot CLI version string.

        Args:
            cli_path: Path to the copilot binary. Auto-detected if None.

        Returns:
            Version string, or None if CLI is not available.
        """
        path = cli_path or CopilotService.detect_cli()
        if not path:
            return None
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        """Check whether the Copilot SDK and CLI are available.

        Returns:
            True if the SDK is importable and the CLI is detected.
        """
        try:
            import github_copilot  # noqa: F401

            return self.detect_cli() is not None
        except ImportError:
            return False

    def is_sdk_installed(self) -> bool:
        """Check if the github-copilot-sdk package is installed."""
        try:
            import github_copilot  # noqa: F401

            return True
        except ImportError:
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
            return True

        try:
            from github_copilot import CopilotClient

            client_kwargs: dict[str, Any] = {
                "auto_start": self._settings.auto_start_cli,
            }

            # Auth — prefer stored token, fall back to logged-in user
            token = self._key_store.get_key("copilot_github_token")
            if token:
                client_kwargs["github_token"] = token
            elif self._settings.use_logged_in_user:
                client_kwargs["use_logged_in_user"] = True

            cli_path = self._settings.cli_path or self.detect_cli()
            if cli_path:
                client_kwargs["cli_path"] = cli_path

            self._client = CopilotClient(**client_kwargs)
            self._run_async(self._client.start())
            self._is_running = True
            logger.info("Copilot client started")
            return True

        except ImportError:
            logger.error("github-copilot-sdk not installed")
            return False
        except Exception as exc:
            logger.exception("Failed to start Copilot client: %s", exc)
            return False

    def stop(self) -> None:
        """Stop the Copilot client and clean up resources."""
        if self._session:
            with contextlib.suppress(Exception):
                self._run_async(self._session.destroy())
            self._session = None

        if self._client and self._is_running:
            with contextlib.suppress(Exception):
                self._run_async(self._client.stop())
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
        logger.info("Copilot client stopped")

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
            system_msg += (
                "\n\n--- TRANSCRIPT CONTEXT ---\n"
                + self._transcript_context[:50000]  # Limit context size
                + "\n--- END TRANSCRIPT ---"
            )
        session_kwargs["system_message"] = system_msg

        # Add transcript tools if enabled
        if self._settings.allow_transcript_tools:
            tools = self._build_transcript_tools()
            if tools:
                session_kwargs["tools"] = tools

        session = await self._client.create_session(**session_kwargs)
        return session

    def _build_transcript_tools(self) -> list[Any] | None:
        """Build custom tools for transcript analysis.

        Returns:
            List of tool definitions, or None if tools are not available.
        """
        try:
            from github_copilot import define_tool
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
        self._conversation_history.append(CopilotMessage(role="user", content=message))

        def _do_send() -> None:
            try:
                result = self._run_async(self._async_send(message, on_delta=on_delta))
                self._conversation_history.append(result)
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
            self._session = await self._create_session()

        if self._settings.streaming and on_delta:
            # Streaming mode — collect deltas
            full_text = ""
            response = await self._session.send(message)

            # Handle different response types from the SDK
            if hasattr(response, "__aiter__"):
                async for event in response:
                    if hasattr(event, "type"):
                        if event.type == "assistant.message_delta":
                            delta = getattr(event, "delta", "") or getattr(event, "text", "")
                            if delta:
                                full_text += delta
                                on_delta(delta)
                        elif event.type == "assistant.message":
                            text = getattr(event, "text", "") or getattr(event, "content", "")
                            if text and not full_text:
                                full_text = text
                    elif isinstance(event, str):
                        full_text += event
                        on_delta(event)
            else:
                # Non-iterable response — extract text
                full_text = self._extract_text(response)
                if on_delta:
                    on_delta(full_text)

            return CopilotMessage(
                role="assistant",
                content=full_text,
                model=self._settings.default_model,
                is_complete=True,
            )
        else:
            # Non-streaming mode
            response = await self._session.send(message)
            text = self._extract_text(response)
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
