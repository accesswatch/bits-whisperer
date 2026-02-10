"""Tests for slash command system in the AI chat panel.

Covers:
- SlashCommand dataclass
- SlashCommandRegistry (register, get, match, categories)
- parse_slash_command() parser
- build_default_registry() completeness
- Individual command handler logic (using mock panel)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bits_whisperer.ui.slash_commands import (
    SlashCommand,
    SlashCommandRegistry,
    build_default_registry,
    parse_slash_command,
)

# -----------------------------------------------------------------------
# parse_slash_command
# -----------------------------------------------------------------------


class TestParseSlashCommand:
    """Test the slash command parser."""

    def test_simple_command(self) -> None:
        result = parse_slash_command("/help")
        assert result == ("help", "")

    def test_command_with_args(self) -> None:
        result = parse_slash_command("/translate Spanish")
        assert result == ("translate", "Spanish")

    def test_command_with_multi_word_args(self) -> None:
        result = parse_slash_command("/search budget discussion")
        assert result == ("search", "budget discussion")

    def test_command_case_insensitive(self) -> None:
        result = parse_slash_command("/HELP")
        assert result == ("help", "")

    def test_command_mixed_case(self) -> None:
        result = parse_slash_command("/Summarize detailed")
        assert result == ("summarize", "detailed")

    def test_not_a_command(self) -> None:
        result = parse_slash_command("hello world")
        assert result is None

    def test_empty_string(self) -> None:
        result = parse_slash_command("")
        assert result is None

    def test_just_slash(self) -> None:
        result = parse_slash_command("/")
        assert result is None

    def test_whitespace_before_slash(self) -> None:
        result = parse_slash_command("  /help")
        assert result == ("help", "")

    def test_trailing_whitespace(self) -> None:
        result = parse_slash_command("/clear  ")
        assert result == ("clear", "")

    def test_args_with_extra_spaces(self) -> None:
        result = parse_slash_command("/export   txt")
        assert result == ("export", "txt")

    def test_multiline_args(self) -> None:
        result = parse_slash_command("/ask What happened?\nAny decisions?")
        assert result is not None
        assert result[0] == "ask"
        assert "What happened?" in result[1]

    def test_hyphenated_command(self) -> None:
        result = parse_slash_command("/key-points")
        assert result == ("key-points", "")

    def test_command_with_numbers(self) -> None:
        result = parse_slash_command("/test123")
        assert result == ("test123", "")


# -----------------------------------------------------------------------
# SlashCommand dataclass
# -----------------------------------------------------------------------


class TestSlashCommandDataclass:
    """Test the SlashCommand dataclass."""

    def test_basic_creation(self) -> None:
        cmd = SlashCommand(
            name="test",
            description="A test command",
            category="Test",
            handler=lambda p, a: None,
        )
        assert cmd.name == "test"
        assert cmd.description == "A test command"
        assert cmd.category == "Test"

    def test_defaults(self) -> None:
        cmd = SlashCommand(
            name="test",
            description="desc",
            category="Cat",
            handler=lambda p, a: None,
        )
        assert cmd.aliases == []
        assert cmd.arg_hint == ""
        assert cmd.requires_transcript is False

    def test_with_aliases(self) -> None:
        cmd = SlashCommand(
            name="test",
            description="desc",
            category="Cat",
            handler=lambda p, a: None,
            aliases=["t", "tst"],
        )
        assert cmd.aliases == ["t", "tst"]

    def test_with_arg_hint(self) -> None:
        cmd = SlashCommand(
            name="export",
            description="Export transcript",
            category="App",
            handler=lambda p, a: None,
            arg_hint="[format]",
        )
        assert cmd.arg_hint == "[format]"

    def test_requires_transcript(self) -> None:
        cmd = SlashCommand(
            name="summarize",
            description="Summarize",
            category="AI",
            handler=lambda p, a: None,
            requires_transcript=True,
        )
        assert cmd.requires_transcript is True


# -----------------------------------------------------------------------
# SlashCommandRegistry
# -----------------------------------------------------------------------


class TestSlashCommandRegistry:
    """Test the command registry."""

    def _make_cmd(self, name: str, **kwargs) -> SlashCommand:
        defaults = {
            "description": f"Test {name}",
            "category": "Test",
            "handler": lambda p, a: None,
        }
        defaults.update(kwargs)
        return SlashCommand(name=name, **defaults)

    def test_register_and_get(self) -> None:
        reg = SlashCommandRegistry()
        cmd = self._make_cmd("foo")
        reg.register(cmd)
        assert reg.get("foo") is cmd

    def test_get_nonexistent(self) -> None:
        reg = SlashCommandRegistry()
        assert reg.get("nope") is None

    def test_get_by_alias(self) -> None:
        reg = SlashCommandRegistry()
        cmd = self._make_cmd("summarize", aliases=["sum", "summary"])
        reg.register(cmd)
        assert reg.get("sum") is cmd
        assert reg.get("summary") is cmd
        assert reg.get("summarize") is cmd

    def test_all_commands_sorted(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("z-cmd", category="B"))
        reg.register(self._make_cmd("a-cmd", category="A"))
        reg.register(self._make_cmd("m-cmd", category="A"))
        cmds = reg.all_commands()
        assert [c.name for c in cmds] == ["a-cmd", "m-cmd", "z-cmd"]

    def test_match_prefix(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("start"))
        reg.register(self._make_cmd("status"))
        reg.register(self._make_cmd("stop"))
        matches = reg.match("sta")
        names = [c.name for c in matches]
        assert "start" in names
        assert "status" in names
        assert "stop" not in names

    def test_match_empty_prefix(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("help"))
        reg.register(self._make_cmd("clear"))
        matches = reg.match("")
        assert len(matches) == 2

    def test_match_alias_prefix(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("summarize", aliases=["sum"]))
        matches = reg.match("sum")
        assert len(matches) == 1
        assert matches[0].name == "summarize"

    def test_match_substring(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("clear-queue"))
        matches = reg.match("queue")
        assert len(matches) == 1
        assert matches[0].name == "clear-queue"

    def test_match_no_duplicates(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("summarize", aliases=["sum"]))
        # "sum" matches both the alias and the name substring
        matches = reg.match("sum")
        assert len(matches) == 1

    def test_categories(self) -> None:
        reg = SlashCommandRegistry()
        reg.register(self._make_cmd("a", category="AI"))
        reg.register(self._make_cmd("b", category="App"))
        reg.register(self._make_cmd("c", category="AI"))
        assert reg.categories() == ["AI", "App"]


# -----------------------------------------------------------------------
# build_default_registry
# -----------------------------------------------------------------------


class TestBuildDefaultRegistry:
    """Test the default registry builder."""

    def test_registry_has_commands(self) -> None:
        reg = build_default_registry()
        assert len(reg.all_commands()) >= 24

    def test_ai_category_commands(self) -> None:
        reg = build_default_registry()
        ai_cmds = [c for c in reg.all_commands() if c.category == "AI"]
        ai_names = {c.name for c in ai_cmds}
        expected = {
            "summarize",
            "translate",
            "key-points",
            "action-items",
            "topics",
            "speakers",
            "search",
            "ask",
            "run",
            "copy",
        }
        assert expected.issubset(ai_names)

    def test_app_category_commands(self) -> None:
        reg = build_default_registry()
        app_cmds = [c for c in reg.all_commands() if c.category == "App"]
        app_names = {c.name for c in app_cmds}
        expected = {
            "help",
            "clear",
            "status",
            "provider",
            "export",
            "open",
            "start",
            "cancel",
            "settings",
            "live",
            "models",
            "agent",
            "history",
            "pause",
            "retry",
            "open-folder",
            "clear-queue",
        }
        assert expected.issubset(app_names)

    def test_all_commands_have_handlers(self) -> None:
        reg = build_default_registry()
        for cmd in reg.all_commands():
            assert callable(cmd.handler), f"/{cmd.name} has no handler"

    def test_all_commands_have_descriptions(self) -> None:
        reg = build_default_registry()
        for cmd in reg.all_commands():
            assert cmd.description, f"/{cmd.name} has no description"

    def test_categories_list(self) -> None:
        reg = build_default_registry()
        cats = reg.categories()
        assert "AI" in cats
        assert "App" in cats

    def test_alias_resolution(self) -> None:
        reg = build_default_registry()
        assert reg.get("sum") is reg.get("summarize")
        assert reg.get("tr") is reg.get("translate")
        assert reg.get("kp") is reg.get("key-points")
        assert reg.get("?") is reg.get("help")
        assert reg.get("go") is reg.get("start")
        assert reg.get("stop") is reg.get("cancel")
        assert reg.get("mic") is reg.get("live")

    def test_transcript_requiring_commands(self) -> None:
        """Commands that need a transcript have requires_transcript=True."""
        reg = build_default_registry()
        must_have_transcript = {
            "summarize",
            "translate",
            "key-points",
            "action-items",
            "topics",
            "speakers",
            "search",
            "export",
        }
        for name in must_have_transcript:
            cmd = reg.get(name)
            assert cmd is not None, f"/{name} not registered"
            assert cmd.requires_transcript, f"/{name} should require transcript"

    def test_non_transcript_commands(self) -> None:
        """Commands that don't need a transcript."""
        reg = build_default_registry()
        no_transcript = {"help", "clear", "status", "open", "start", "settings"}
        for name in no_transcript:
            cmd = reg.get(name)
            assert cmd is not None, f"/{name} not registered"
            assert not cmd.requires_transcript, f"/{name} should NOT require transcript"


# -----------------------------------------------------------------------
# Command handler unit tests (mock panel)
# -----------------------------------------------------------------------


class TestCommandHandlers:
    """Test individual command handlers with a mocked panel."""

    @staticmethod
    def _make_panel() -> MagicMock:
        """Create a mock CopilotChatPanel."""
        panel = MagicMock()
        panel._transcript_context = "Meeting transcript content here."
        panel._conversation_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ]
        panel._slash_registry = build_default_registry()
        panel._get_selected_provider_id.return_value = "openai"
        panel._available_providers = [
            {"id": "openai", "name": "OpenAI"},
            {"id": "anthropic", "name": "Anthropic (Claude)"},
        ]
        panel._main_frame = MagicMock()
        panel._input_text = MagicMock()
        panel._is_streaming = False
        panel._send_btn = MagicMock()
        return panel

    def test_help_shows_all_commands(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("help")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "summarize" in msg.lower()
        assert "help" in msg.lower()

    def test_clear_calls_on_clear(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("clear")
        cmd.handler(panel, "")
        panel._on_clear.assert_called_once_with(None)

    def test_summarize_sends_message(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("summarize")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()
        msg = panel._send_message.call_args[0][0]
        assert "summary" in msg.lower() or "summarize" in msg.lower()

    def test_summarize_detailed(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("summarize")
        cmd.handler(panel, "detailed")
        panel._send_message.assert_called_once()
        msg = panel._send_message.call_args[0][0]
        assert "detailed" in msg.lower()

    def test_summarize_invalid_style(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("summarize")
        cmd.handler(panel, "bogus")
        # Should show error about invalid style AND still send with default
        calls = panel._append_message.call_args_list
        assert any("Unknown" in str(c) or "style" in str(c) for c in calls)

    def test_translate_default_language(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("translate")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()

    def test_translate_specific_language(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("translate")
        cmd.handler(panel, "French")
        msg = panel._send_message.call_args[0][0]
        assert "French" in msg

    def test_key_points(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("key-points")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()

    def test_action_items(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("action-items")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()

    def test_topics(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("topics")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()

    def test_speakers(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("speakers")
        cmd.handler(panel, "")
        panel._send_message.assert_called_once()

    def test_search_no_query(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("search")
        cmd.handler(panel, "")
        # Should show usage, not send message
        panel._append_message.assert_called_once()
        panel._send_message.assert_not_called()

    def test_search_with_query(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("search")
        cmd.handler(panel, "budget discussion")
        panel._send_message.assert_called_once()
        msg = panel._send_message.call_args[0][0]
        assert "budget discussion" in msg

    def test_ask_no_question(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("ask")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        panel._send_message.assert_not_called()

    def test_ask_with_question(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("ask")
        cmd.handler(panel, "What were the decisions?")
        panel._send_message.assert_called_once_with("What were the decisions?")

    def test_copy_last_response(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("copy")
        cmd.handler(panel, "")
        panel._main_frame._copy_text.assert_called_once_with("Hi! How can I help?")

    def test_copy_no_response(self) -> None:
        panel = self._make_panel()
        panel._conversation_history = []
        reg = build_default_registry()
        cmd = reg.get("copy")
        cmd.handler(panel, "")
        # Should show "no response" message
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "No AI response" in msg

    def test_history_shows_stats(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("history")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "2 total" in msg
        assert "You" in msg

    def test_status_shows_info(self) -> None:
        panel = self._make_panel()
        panel._main_frame.queue_panel.get_pending_jobs.return_value = []
        panel._main_frame.queue_panel._jobs = {}
        reg = build_default_registry()
        cmd = reg.get("status")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "Status" in msg

    def test_provider_show_current(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("provider")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "Current provider" in msg

    def test_provider_switch(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("provider")
        cmd.handler(panel, "anthropic")
        panel._provider_choice.SetSelection.assert_called()
        panel._on_provider_changed.assert_called()

    def test_provider_switch_not_found(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("provider")
        cmd.handler(panel, "nonexistent")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "not found" in msg.lower()

    def test_run_no_args_lists_presets(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("run")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "Meeting Minutes" in msg
        assert "Action Items" in msg

    def test_run_no_transcript(self) -> None:
        panel = self._make_panel()
        panel._transcript_context = ""
        reg = build_default_registry()
        cmd = reg.get("run")
        cmd.handler(panel, "Meeting Minutes")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "No transcript" in msg

    def test_export_invalid_format(self) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("export")
        cmd.handler(panel, "pdf")
        panel._append_message.assert_called_once()
        msg = panel._append_message.call_args[0][1]
        assert "Unknown" in msg or "pdf" in msg

    def test_export_no_transcript(self) -> None:
        panel = self._make_panel()
        panel._main_frame.transcript_panel._current_job = None
        reg = build_default_registry()
        cmd = reg.get("export")
        cmd.handler(panel, "txt")
        panel._append_message.assert_called()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_open_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("open")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_start_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("start")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_cancel_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("cancel")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_settings_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("settings")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_live_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("live")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_models_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("models")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_agent_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("agent")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_retry_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("retry")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_pause_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("pause")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_clear_queue_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("clear-queue")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()

    @patch("bits_whisperer.utils.accessibility.safe_call_after")
    def test_open_folder_calls_main_frame(self, mock_safe) -> None:
        panel = self._make_panel()
        reg = build_default_registry()
        cmd = reg.get("open-folder")
        cmd.handler(panel, "")
        panel._append_message.assert_called_once()
        mock_safe.assert_called_once()


# -----------------------------------------------------------------------
# Integration: command execution flow
# -----------------------------------------------------------------------


class TestSlashCommandExecution:
    """Test the full command execution flow (parse → registry → handler)."""

    def test_end_to_end_help(self) -> None:
        """Parse '/help' and execute through the registry."""
        reg = build_default_registry()
        parsed = parse_slash_command("/help")
        assert parsed is not None
        name, args = parsed
        cmd = reg.get(name)
        assert cmd is not None
        assert cmd.name == "help"

    def test_end_to_end_alias(self) -> None:
        """Parse '/sum' (alias) and resolve to 'summarize'."""
        reg = build_default_registry()
        parsed = parse_slash_command("/sum detailed")
        assert parsed is not None
        name, args = parsed
        cmd = reg.get(name)
        assert cmd is not None
        assert cmd.name == "summarize"
        assert args == "detailed"

    def test_unknown_command(self) -> None:
        """Unknown command returns None from registry."""
        reg = build_default_registry()
        parsed = parse_slash_command("/xyz123")
        assert parsed is not None
        cmd = reg.get(parsed[0])
        assert cmd is None

    def test_autocomplete_partial(self) -> None:
        """Typing '/su' matches summarize and status."""
        reg = build_default_registry()
        matches = reg.match("su")
        names = {c.name for c in matches}
        assert "summarize" in names

    def test_autocomplete_ex(self) -> None:
        """Typing '/ex' matches export."""
        reg = build_default_registry()
        matches = reg.match("ex")
        names = {c.name for c in matches}
        assert "export" in names

    def test_all_ai_commands_require_transcript(self) -> None:
        """AI analysis commands should require a transcript."""
        reg = build_default_registry()
        analysis_cmds = {
            "summarize",
            "translate",
            "key-points",
            "action-items",
            "topics",
            "speakers",
            "search",
        }
        for name in analysis_cmds:
            cmd = reg.get(name)
            assert cmd.requires_transcript, f"/{name} should require transcript"

    def test_question_mark_alias(self) -> None:
        """'?' is a valid alias for 'help'."""
        reg = build_default_registry()
        cmd = reg.get("?")
        assert cmd is not None
        assert cmd.name == "help"
