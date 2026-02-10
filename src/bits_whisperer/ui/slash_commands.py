"""Slash command system for the AI chat panel.

Provides an extensible registry of ``/commands`` that users can type
in the chat input to perform app actions, AI operations, and
configuration changes — all without leaving the chat interface.

Commands are categorised into groups:

- **AI**: Transcript analysis via the configured AI provider
  (summarize, translate, key-points, action-items, topics, speakers)
- **App**: Application actions (export, open, start, cancel, status,
  clear-queue, settings, provider, help)
- **Templates**: Run saved AI action templates on the current transcript

Each command has a name, description, optional aliases, optional
argument hint, and a handler function.  The registry supports fuzzy
matching for autocomplete and can resolve partial command names.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from bits_whisperer.ui.copilot_chat_panel import CopilotChatPanel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SlashCommand:
    """Definition of a single slash command.

    Attributes:
        name: Command name without the leading ``/`` (e.g. ``"summarize"``).
        description: One-line help text shown in autocomplete.
        category: Grouping label (``"AI"``, ``"App"``, ``"Templates"``).
        handler: Callable that executes the command.  Receives
            ``(panel, args_str)`` where *panel* is the chat panel and
            *args_str* is the remainder of the input after the command.
        aliases: Alternative names for the command.
        arg_hint: Placeholder shown after the command (e.g. ``"[language]"``).
        requires_transcript: If True, the command needs a loaded transcript.
    """

    name: str
    description: str
    category: str
    handler: Callable[[CopilotChatPanel, str], None]
    aliases: list[str] = field(default_factory=list)
    arg_hint: str = ""
    requires_transcript: bool = False


class SlashCommandRegistry:
    """Registry of available slash commands with matching support."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._alias_map: dict[str, str] = {}

    def register(self, command: SlashCommand) -> None:
        """Register a slash command.

        Args:
            command: The command definition.
        """
        self._commands[command.name] = command
        for alias in command.aliases:
            self._alias_map[alias] = command.name

    def get(self, name: str) -> SlashCommand | None:
        """Look up a command by name or alias.

        Args:
            name: Command name (without leading ``/``).

        Returns:
            The command, or None if not found.
        """
        canonical = self._alias_map.get(name, name)
        return self._commands.get(canonical)

    def all_commands(self) -> list[SlashCommand]:
        """Return all registered commands sorted by category then name."""
        return sorted(
            self._commands.values(),
            key=lambda c: (c.category, c.name),
        )

    def match(self, prefix: str) -> list[SlashCommand]:
        """Return commands whose name or alias starts with *prefix*.

        Args:
            prefix: Partial command name (without ``/``).

        Returns:
            Matching commands, sorted by relevance.
        """
        prefix_lower = prefix.lower()
        results: list[SlashCommand] = []
        seen: set[str] = set()

        # Exact name prefix matches first
        for cmd in self._commands.values():
            if cmd.name.startswith(prefix_lower) and cmd.name not in seen:
                results.append(cmd)
                seen.add(cmd.name)

        # Alias prefix matches
        for alias, canonical in self._alias_map.items():
            if alias.startswith(prefix_lower) and canonical not in seen:
                cmd = self._commands.get(canonical)
                if cmd:
                    results.append(cmd)
                    seen.add(canonical)

        # Fuzzy: substring matches (lower priority)
        for cmd in self._commands.values():
            if cmd.name not in seen and prefix_lower in cmd.name:
                results.append(cmd)
                seen.add(cmd.name)

        return results

    def categories(self) -> list[str]:
        """Return sorted unique category names."""
        return sorted({c.category for c in self._commands.values()})


# ---------------------------------------------------------------------------
# Parse helper
# ---------------------------------------------------------------------------


def parse_slash_command(text: str) -> tuple[str, str] | None:
    """Parse a slash command from user input.

    Args:
        text: The raw input text (e.g. ``"/translate Spanish"``).

    Returns:
        Tuple of ``(command_name, args_string)`` if the text starts
        with ``/``, otherwise None.
    """
    text = text.strip()
    if not text.startswith("/"):
        return None
    # Split on first whitespace
    match = re.match(r"/(\S+)\s*(.*)", text, re.DOTALL)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).strip()


# ---------------------------------------------------------------------------
# Built-in command handlers
# ---------------------------------------------------------------------------


def _cmd_help(panel: CopilotChatPanel, args: str) -> None:
    """Show all available slash commands."""
    registry = panel._slash_registry
    lines = ["Available Slash Commands", "\u2501" * 36, ""]

    for category in registry.categories():
        lines.append(f"\u2550\u2550 {category} \u2550" * 3)
        cmds = [c for c in registry.all_commands() if c.category == category]
        for cmd in cmds:
            arg_part = f" {cmd.arg_hint}" if cmd.arg_hint else ""
            alias_part = ""
            if cmd.aliases:
                alias_part = f"  (aliases: {', '.join('/' + a for a in cmd.aliases)})"
            lines.append(f"  /{cmd.name}{arg_part}")
            lines.append(f"    {cmd.description}{alias_part}")
        lines.append("")

    lines.append("Tip: Type / and start typing to see suggestions.")
    panel._append_message("System", "\n".join(lines))


def _cmd_clear(panel: CopilotChatPanel, args: str) -> None:
    """Clear the conversation history."""
    panel._on_clear(None)


def _cmd_summarize(panel: CopilotChatPanel, args: str) -> None:
    """Summarize the transcript with an optional style argument."""
    style = args.strip().lower() if args.strip() else ""
    valid_styles = {"concise", "detailed", "bullets", "bullet_points"}

    if style and style not in valid_styles:
        panel._append_message(
            "System",
            f"Unknown summary style '{style}'.\n"
            f"Valid styles: concise, detailed, bullets\n"
            f"Using default style.",
        )
        style = ""

    # Map shorthand
    if style == "bullets":
        style = "bullet_points"

    if style:
        from bits_whisperer.core.ai_service import _SUMMARIZE_STYLES

        template = _SUMMARIZE_STYLES.get(style)
        if template and panel._transcript_context:
            from bits_whisperer.core.context_manager import create_context_manager
            from bits_whisperer.core.settings import AppSettings

            settings = AppSettings.load()
            ctx_mgr = create_context_manager(settings.ai)
            prepared = ctx_mgr.prepare_action_context(
                model=getattr(settings.ai, f"{settings.ai.selected_provider}_model", ""),
                provider=settings.ai.selected_provider,
                instructions=template.split("{text}")[0] if "{text}" in template else "",
                transcript=panel._transcript_context,
            )
            prompt = template.format(text=prepared.fitted_transcript)
            panel._send_message(prompt)
            return

    # Default: send as a natural language request to the AI
    prompt = "Please provide a concise summary of this transcript."
    if style == "detailed":
        prompt = (
            "Provide a detailed summary of this transcript including "
            "main topics, key points from each speaker, decisions, and action items."
        )
    elif style == "bullet_points":
        prompt = (
            "Summarize this transcript as a bulleted list. Each bullet "
            "should capture one key point, decision, or action item."
        )
    panel._send_message(prompt)


def _cmd_translate(panel: CopilotChatPanel, args: str) -> None:
    """Translate the transcript to a target language."""
    language = args.strip() if args.strip() else ""

    if not language:
        # Use the configured default
        from bits_whisperer.core.settings import AppSettings

        settings = AppSettings.load()
        language = settings.ai.translation_target_language or "Spanish"

    prompt = (
        f"Translate this transcript to {language}. "
        "Preserve speaker labels, timestamps, and formatting exactly as they appear. "
        "Only translate the spoken content."
    )
    panel._send_message(prompt)


def _cmd_key_points(panel: CopilotChatPanel, args: str) -> None:
    """Extract key points from the transcript."""
    panel._send_message(
        "List the key points and action items from this transcript as bullet points."
    )


def _cmd_action_items(panel: CopilotChatPanel, args: str) -> None:
    """Extract action items and follow-ups."""
    panel._send_message(
        "Extract all action items, tasks, and follow-ups from this transcript. "
        "For each item, note who is responsible and any deadlines mentioned."
    )


def _cmd_topics(panel: CopilotChatPanel, args: str) -> None:
    """Identify main topics discussed."""
    panel._send_message(
        "What are the main topics discussed in this transcript? "
        "List each topic with a brief description."
    )


def _cmd_speakers(panel: CopilotChatPanel, args: str) -> None:
    """Identify and describe speakers."""
    panel._send_message(
        "Identify and describe each speaker in this transcript. "
        "Note their role, key contributions, and speaking style."
    )


def _cmd_search(panel: CopilotChatPanel, args: str) -> None:
    """Search the transcript for specific content."""
    query = args.strip()
    if not query:
        panel._append_message(
            "System",
            "Usage: /search <query>\nExample: /search budget discussion",
        )
        return
    panel._send_message(
        f"Search this transcript for content related to: {query}\n"
        "Quote the relevant sections and provide context."
    )


def _cmd_ask(panel: CopilotChatPanel, args: str) -> None:
    """Ask a freeform question about the transcript."""
    question = args.strip()
    if not question:
        panel._append_message(
            "System",
            "Usage: /ask <question>\nExample: /ask What decisions were made?",
        )
        return
    panel._send_message(question)


def _cmd_export(panel: CopilotChatPanel, args: str) -> None:
    """Export the current transcript to a file."""
    from bits_whisperer.utils.accessibility import announce_status, safe_call_after
    from bits_whisperer.utils.constants import EXPORT_FORMATS

    fmt = args.strip().lower() if args.strip() else ""

    if fmt and fmt not in EXPORT_FORMATS:
        valid = ", ".join(EXPORT_FORMATS.keys())
        panel._append_message(
            "System",
            f"Unknown export format '{fmt}'.\nValid formats: {valid}",
        )
        return

    mf = panel._main_frame

    if not mf.transcript_panel._current_job or not mf.transcript_panel._current_job.result:
        panel._append_message(
            "System",
            "No transcript loaded. Transcribe a file first.",
        )
        return

    if fmt:
        # Direct export with the specified format
        from bits_whisperer.export.base import get_exporter

        exporter = get_exporter(fmt)
        if exporter:
            from pathlib import Path

            from bits_whisperer.core.settings import AppSettings

            settings = AppSettings.load()
            stem = Path(mf.transcript_panel._current_job.file_path).stem
            out_dir = settings.output.output_directory
            out_path = str(Path(out_dir) / f"{stem}.{fmt}")
            try:
                exporter.export(mf.transcript_panel._current_job.result, out_path)
                panel._append_message(
                    "System",
                    f"Transcript exported to: {out_path}",
                )
                announce_status(mf, f"Exported as {fmt}: {out_path}")
            except Exception as exc:
                panel._append_message("System", f"Export failed: {exc}")
        else:
            panel._append_message("System", f"No exporter found for format '{fmt}'.")
    else:
        # Open the export dialog
        def _show() -> None:
            mf.transcript_panel.export_transcript()

        safe_call_after(_show)
        panel._append_message("System", "Opening export dialog...")


def _cmd_open(panel: CopilotChatPanel, args: str) -> None:
    """Open the file picker to add audio files."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_add_files(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening file picker...")


def _cmd_open_folder(panel: CopilotChatPanel, args: str) -> None:
    """Open the folder picker to add a folder of audio files."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_add_folder(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening folder picker...")


def _cmd_start(panel: CopilotChatPanel, args: str) -> None:
    """Start transcription of pending jobs."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _do() -> None:
        panel._main_frame._on_start(None)

    safe_call_after(_do)
    panel._append_message("System", "Starting transcription...")


def _cmd_cancel(panel: CopilotChatPanel, args: str) -> None:
    """Cancel the current transcription job."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _do() -> None:
        panel._main_frame._on_cancel(None)

    safe_call_after(_do)
    panel._append_message("System", "Cancelling current job...")


def _cmd_pause(panel: CopilotChatPanel, args: str) -> None:
    """Toggle pause/resume on transcription."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _do() -> None:
        panel._main_frame._on_pause(None)

    safe_call_after(_do)
    panel._append_message("System", "Toggling transcription pause/resume...")


def _cmd_clear_queue(panel: CopilotChatPanel, args: str) -> None:
    """Clear all jobs from the queue."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _do() -> None:
        panel._main_frame._on_clear_queue(None)

    safe_call_after(_do)
    panel._append_message("System", "Queue cleared.")


def _cmd_status(panel: CopilotChatPanel, args: str) -> None:
    """Show current queue and transcription status."""
    mf = panel._main_frame
    try:
        pending = mf.queue_panel.get_pending_jobs()
        total_jobs = len(mf.queue_panel._jobs)
        pending_count = len(pending)
        completed = sum(1 for j in mf.queue_panel._jobs.values() if j.status == "COMPLETED")
        failed = sum(1 for j in mf.queue_panel._jobs.values() if j.status == "FAILED")
        active = total_jobs - pending_count - completed - failed

        # Provider info
        from bits_whisperer.core.ai_service import AIService
        from bits_whisperer.core.settings import AppSettings

        settings = AppSettings.load()
        ai_svc = AIService(mf.key_store, settings.ai)
        provider_display = ai_svc.get_provider_display_name()
        has_transcript = bool(panel._transcript_context)

        lines = [
            "Status",
            "\u2501" * 20,
            f"Queue:      {total_jobs} total",
            f"  Pending:  {pending_count}",
            f"  Active:   {active}",
            f"  Done:     {completed}",
            f"  Failed:   {failed}",
            "",
            f"AI Provider: {provider_display}",
            f"Transcript:  {'Loaded' if has_transcript else 'None'}",
        ]
        panel._append_message("System", "\n".join(lines))
    except Exception as exc:
        panel._append_message("System", f"Could not fetch status: {exc}")


def _cmd_provider(panel: CopilotChatPanel, args: str) -> None:
    """Switch AI provider or show current one."""
    target = args.strip().lower() if args.strip() else ""

    if not target:
        # Show current
        from bits_whisperer.ui.copilot_chat_panel import _PROVIDER_NAMES

        pid = panel._get_selected_provider_id()
        name = _PROVIDER_NAMES.get(pid, pid)
        available = [f"  {p['name']} ({p['id']})" for p in panel._available_providers]
        lines = [
            f"Current provider: {name}",
            "",
            "Available providers:",
        ] + (available if available else ["  (none configured)"])
        lines.append("")
        lines.append("Usage: /provider <id>")
        lines.append("Example: /provider openai")
        panel._append_message("System", "\n".join(lines))
        return

    # Try to match by ID or partial name
    matched_idx = -1
    for i, p in enumerate(panel._available_providers):
        if p["id"] == target or p["name"].lower().startswith(target):
            matched_idx = i
            break

    if matched_idx < 0:
        panel._append_message(
            "System",
            f"Provider '{target}' not found. Use /provider to see available options.",
        )
        return

    panel._provider_choice.SetSelection(matched_idx)
    panel._on_provider_changed(None)
    name = panel._available_providers[matched_idx]["name"]
    panel._append_message("System", f"Switched to {name}.")


def _cmd_settings(panel: CopilotChatPanel, args: str) -> None:
    """Open the AI provider settings dialog."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_ai_settings(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening AI settings...")


def _cmd_live(panel: CopilotChatPanel, args: str) -> None:
    """Open the live microphone transcription dialog."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_live_transcription(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening live transcription...")


def _cmd_models(panel: CopilotChatPanel, args: str) -> None:
    """Open the model manager dialog."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_models(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening model manager...")


def _cmd_run(panel: CopilotChatPanel, args: str) -> None:
    """Run an AI action template on the current transcript.

    Supports built-in presets and saved templates (AgentConfig).
    """
    template_name = args.strip()
    if not template_name:
        # List available templates
        from bits_whisperer.core.transcription_service import TranscriptionService

        presets = list(TranscriptionService._BUILTIN_PRESETS.keys())

        # Check for saved templates

        from bits_whisperer.utils.constants import DATA_DIR

        agents_dir = DATA_DIR / "agents"
        saved: list[str] = []
        if agents_dir.is_dir():
            for f in sorted(agents_dir.glob("*.json")):
                saved.append(f.stem)

        lines = [
            "Available AI Action Templates",
            "\u2501" * 36,
            "",
            "Built-in presets:",
        ]
        for p in presets:
            lines.append(f"  \u2022 {p}")

        if saved:
            lines.append("")
            lines.append("Saved templates:")
            for s in saved:
                lines.append(f"  \u2605 {s}")

        lines.append("")
        lines.append("Usage: /run <template name>")
        lines.append("Example: /run Meeting Minutes")
        panel._append_message("System", "\n".join(lines))
        return

    if not panel._transcript_context:
        panel._append_message(
            "System",
            "No transcript loaded. Transcribe a file first, then try /run again.",
        )
        return

    # Resolve template instructions
    from bits_whisperer.core.transcription_service import TranscriptionService

    # Check built-in presets (case-insensitive match)
    preset_map = {k.lower(): k for k in TranscriptionService._BUILTIN_PRESETS}
    resolved_name = preset_map.get(template_name.lower())

    instructions = ""
    if resolved_name:
        instructions = TranscriptionService._BUILTIN_PRESETS[resolved_name]
    else:
        # Try saved template file

        from bits_whisperer.utils.constants import DATA_DIR

        template_path = DATA_DIR / "agents" / f"{template_name}.json"
        if template_path.is_file():
            try:
                from bits_whisperer.core.copilot_service import AgentConfig

                config = AgentConfig.load(template_path)
                instructions = config.instructions
                resolved_name = config.name or template_name
            except Exception as exc:
                panel._append_message(
                    "System",
                    f"Failed to load template '{template_name}': {exc}",
                )
                return
        else:
            panel._append_message(
                "System",
                f"Template '{template_name}' not found. Use /run to see available templates.",
            )
            return

    # Build prompt with model-aware context fitting
    from bits_whisperer.core.context_manager import create_context_manager
    from bits_whisperer.core.settings import AppSettings

    settings = AppSettings.load()
    ctx_mgr = create_context_manager(settings.ai)
    prepared = ctx_mgr.prepare_action_context(
        model=getattr(settings.ai, f"{settings.ai.selected_provider}_model", ""),
        provider=settings.ai.selected_provider,
        instructions=instructions,
        transcript=panel._transcript_context,
    )
    prompt = (
        f"{instructions}\n\n"
        f"--- TRANSCRIPT ---\n"
        f"{prepared.fitted_transcript}\n"
        f"--- END TRANSCRIPT ---\n\n"
        f"Please process this transcript according to the instructions above."
    )
    panel._append_message("You", f"/run {resolved_name or template_name}")
    panel._input_text.SetValue("")
    panel._is_streaming = True
    panel._send_btn.Disable()
    panel._conversation_history.append({"role": "user", "content": prompt})
    panel._send_via_ai_service(prompt)


def _cmd_copy(panel: CopilotChatPanel, args: str) -> None:
    """Copy the last AI response to the clipboard."""
    # Find the last assistant message
    for msg in reversed(panel._conversation_history):
        if msg["role"] == "assistant":
            panel._main_frame._copy_text(msg["content"])
            panel._append_message("System", "Last response copied to clipboard.")
            return
    panel._append_message("System", "No AI response to copy.")


def _cmd_history(panel: CopilotChatPanel, args: str) -> None:
    """Show conversation statistics."""
    total = len(panel._conversation_history)
    user_msgs = sum(1 for m in panel._conversation_history if m["role"] == "user")
    asst_msgs = sum(1 for m in panel._conversation_history if m["role"] == "assistant")
    total_chars = sum(len(m["content"]) for m in panel._conversation_history)

    lines = [
        "Conversation History",
        "\u2501" * 24,
        f"Messages:  {total} total",
        f"  You:     {user_msgs}",
        f"  AI:      {asst_msgs}",
        f"Characters: {total_chars:,}",
    ]
    panel._append_message("System", "\n".join(lines))


def _cmd_retry(panel: CopilotChatPanel, args: str) -> None:
    """Retry all failed jobs in the queue."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _do() -> None:
        panel._main_frame._on_retry_failed(None)

    safe_call_after(_do)
    panel._append_message("System", "Retrying failed jobs...")


def _cmd_agent(panel: CopilotChatPanel, args: str) -> None:
    """Open the AI Action Builder dialog."""
    from bits_whisperer.utils.accessibility import safe_call_after

    def _show() -> None:
        panel._main_frame._on_agent_builder(None)

    safe_call_after(_show)
    panel._append_message("System", "Opening AI Action Builder...")


def _cmd_context(panel: CopilotChatPanel, args: str) -> None:
    """Show context window budget and transcript fit information."""
    from bits_whisperer.core.ai_service import AIService
    from bits_whisperer.core.context_manager import (
        count_tokens,
        create_context_manager,
        get_model_context_window,
    )
    from bits_whisperer.core.settings import AppSettings

    settings = AppSettings.load()
    ai_svc = AIService(panel._main_frame.key_store, settings.ai)
    model_id = ai_svc._get_model_id()
    provider_id = settings.ai.selected_provider

    ctx_mgr = create_context_manager(settings.ai)
    context_window = get_model_context_window(model_id, provider_id)

    def _fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    lines = [
        "Context Window Budget",
        "\u2501" * 24,
        f"Provider:        {ai_svc.get_provider_display_name()}",
        f"Model:           {model_id}",
        f"Context Window:  {_fmt(context_window)} tokens",
        f"Strategy:        {settings.ai.context_strategy}",
        f"Response Reserve: {_fmt(settings.ai.context_response_reserve_tokens)} tokens",
        f"Transcript %:    {settings.ai.context_transcript_budget_pct * 100:.0f}%",
        f"Max Chat Turns:  {settings.ai.context_max_conversation_turns}",
    ]

    if panel._transcript_context:
        transcript_tokens = count_tokens(
            panel._transcript_context,
            model=model_id,
            provider=provider_id,
        )
        lines.append("")
        lines.append("Transcript")
        lines.append("\u2501" * 24)
        lines.append(f"Characters: {len(panel._transcript_context):,}")
        lines.append(f"Est. Tokens: {_fmt(transcript_tokens)}")

        prepared = ctx_mgr.prepare_chat_context(
            model=model_id,
            provider=provider_id,
            system_prompt="",
            transcript=panel._transcript_context,
            conversation_history=panel._conversation_history,
        )
        b = prepared.budget
        lines.append(f"Fitted Tokens: {_fmt(b.transcript_fitted_tokens)}")
        lines.append(f"Truncated:   {'Yes (' + b.strategy_used + ')' if b.is_truncated else 'No'}")
        lines.append(f"Utilisation: {b.utilisation_pct:.1f}%")
        lines.append(f"Headroom:    {_fmt(b.headroom_tokens)} tokens")
    else:
        lines.append("")
        lines.append("No transcript loaded.")

    history_tokens = count_tokens(
        " ".join(m.get("content", "") for m in panel._conversation_history),
        model=model_id,
        provider=provider_id,
    )
    lines.append("")
    lines.append(
        f"Chat History: {len(panel._conversation_history)} messages ({_fmt(history_tokens)} tokens)"
    )

    panel._append_message("System", "\n".join(lines))


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------


def build_default_registry() -> SlashCommandRegistry:
    """Create and populate the default slash command registry.

    Returns:
        A fully-populated SlashCommandRegistry with all built-in commands.
    """
    reg = SlashCommandRegistry()

    # -- AI commands --
    reg.register(
        SlashCommand(
            name="summarize",
            description="Summarize the transcript (styles: concise, detailed, bullets)",
            category="AI",
            handler=_cmd_summarize,
            aliases=["sum", "summary"],
            arg_hint="[style]",
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="translate",
            description="Translate the transcript to a target language",
            category="AI",
            handler=_cmd_translate,
            aliases=["trans", "tr"],
            arg_hint="[language]",
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="key-points",
            description="Extract key points and takeaways",
            category="AI",
            handler=_cmd_key_points,
            aliases=["kp", "keypoints"],
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="action-items",
            description="Extract action items, tasks, and follow-ups",
            category="AI",
            handler=_cmd_action_items,
            aliases=["ai", "actions", "todos"],
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="topics",
            description="Identify the main topics discussed",
            category="AI",
            handler=_cmd_topics,
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="speakers",
            description="Identify and describe each speaker",
            category="AI",
            handler=_cmd_speakers,
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="search",
            description="Search the transcript for specific content",
            category="AI",
            handler=_cmd_search,
            arg_hint="<query>",
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="ask",
            description="Ask a freeform question about the transcript",
            category="AI",
            handler=_cmd_ask,
            arg_hint="<question>",
        )
    )
    reg.register(
        SlashCommand(
            name="run",
            description="Run an AI action template on the transcript",
            category="AI",
            handler=_cmd_run,
            arg_hint="[template name]",
        )
    )
    reg.register(
        SlashCommand(
            name="copy",
            description="Copy the last AI response to the clipboard",
            category="AI",
            handler=_cmd_copy,
        )
    )

    # -- App commands --
    reg.register(
        SlashCommand(
            name="help",
            description="Show all available slash commands",
            category="App",
            handler=_cmd_help,
            aliases=["?", "commands"],
        )
    )
    reg.register(
        SlashCommand(
            name="clear",
            description="Clear the conversation history",
            category="App",
            handler=_cmd_clear,
        )
    )
    reg.register(
        SlashCommand(
            name="status",
            description="Show queue status and current provider info",
            category="App",
            handler=_cmd_status,
        )
    )
    reg.register(
        SlashCommand(
            name="provider",
            description="Switch AI provider or show current one",
            category="App",
            handler=_cmd_provider,
            arg_hint="[provider_id]",
        )
    )
    reg.register(
        SlashCommand(
            name="export",
            description="Export the transcript (formats: txt, md, html, docx, srt, vtt, json)",
            category="App",
            handler=_cmd_export,
            arg_hint="[format]",
            requires_transcript=True,
        )
    )
    reg.register(
        SlashCommand(
            name="open",
            description="Open file picker to add audio files",
            category="App",
            handler=_cmd_open,
            aliases=["add"],
        )
    )
    reg.register(
        SlashCommand(
            name="open-folder",
            description="Open folder picker to add a folder of audio files",
            category="App",
            handler=_cmd_open_folder,
            aliases=["folder", "add-folder"],
        )
    )
    reg.register(
        SlashCommand(
            name="start",
            description="Start transcription of pending jobs",
            category="App",
            handler=_cmd_start,
            aliases=["go", "transcribe"],
        )
    )
    reg.register(
        SlashCommand(
            name="pause",
            description="Pause or resume transcription",
            category="App",
            handler=_cmd_pause,
            aliases=["resume"],
        )
    )
    reg.register(
        SlashCommand(
            name="cancel",
            description="Cancel the current transcription job",
            category="App",
            handler=_cmd_cancel,
            aliases=["stop"],
        )
    )
    reg.register(
        SlashCommand(
            name="clear-queue",
            description="Remove all jobs from the queue",
            category="App",
            handler=_cmd_clear_queue,
        )
    )
    reg.register(
        SlashCommand(
            name="retry",
            description="Retry all failed jobs in the queue",
            category="App",
            handler=_cmd_retry,
        )
    )
    reg.register(
        SlashCommand(
            name="settings",
            description="Open the AI provider settings dialog",
            category="App",
            handler=_cmd_settings,
            aliases=["config", "prefs"],
        )
    )
    reg.register(
        SlashCommand(
            name="live",
            description="Open live microphone transcription",
            category="App",
            handler=_cmd_live,
            aliases=["mic", "microphone"],
        )
    )
    reg.register(
        SlashCommand(
            name="models",
            description="Open the Whisper model manager",
            category="App",
            handler=_cmd_models,
        )
    )
    reg.register(
        SlashCommand(
            name="agent",
            description="Open the AI Action Builder to create/edit templates",
            category="App",
            handler=_cmd_agent,
            aliases=["builder", "action-builder"],
        )
    )
    reg.register(
        SlashCommand(
            name="history",
            description="Show conversation statistics",
            category="App",
            handler=_cmd_history,
        )
    )
    reg.register(
        SlashCommand(
            name="context",
            description="Show context window budget and transcript fit info",
            category="App",
            handler=_cmd_context,
            aliases=["ctx", "budget"],
        )
    )

    return reg
