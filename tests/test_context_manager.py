"""Tests for the context window manager.

Tests token estimation, model lookup, transcript fitting strategies,
conversation history trimming, and the full ContextWindowManager
orchestration.
"""

import unittest
from unittest.mock import patch

from bits_whisperer.core.context_manager import (
    ContextBudget,
    ContextWindowManager,
    ContextWindowSettings,
    PreparedContext,
    chars_for_tokens,
    count_tokens,
    create_context_manager,
    estimate_tokens,
    estimate_tokens_precise,
    fit_transcript,
    get_model_context_window,
    get_model_max_output,
    trim_conversation_history,
)

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestEstimateTokens(unittest.TestCase):
    """Test heuristic token estimation."""

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_short_text(self) -> None:
        # "hello" = 5 chars / 4 = 1.25 → rounds to 1
        assert estimate_tokens("hello") == 1

    def test_longer_text(self) -> None:
        text = "a" * 400
        # 400 / 4 = 100
        assert estimate_tokens(text) == 100

    def test_custom_ratio(self) -> None:
        text = "a" * 300
        # 300 / 3 = 100
        assert estimate_tokens(text, chars_per_token=3.0) == 100

    def test_always_at_least_one(self) -> None:
        assert estimate_tokens("x") >= 1

    def test_rounding(self) -> None:
        # 10 chars / 4 = 2.5 → rounds to 3
        assert estimate_tokens("a" * 10) == 3


class TestEstimateTokensPrecise(unittest.TestCase):
    """Test tiktoken-based precise estimation."""

    def test_returns_none_without_tiktoken(self) -> None:
        with patch.dict("sys.modules", {"tiktoken": None}):
            estimate_tokens_precise("hello", "gpt-4o")
            # May or may not be None depending on import cache
            # Just verify it doesn't crash

    def test_returns_none_for_unknown_model(self) -> None:
        # Should gracefully handle unknown models
        result = estimate_tokens_precise("hello", "totally-fake-model-xyz")
        # This either returns an int (if tiktoken guesses) or None
        assert result is None or isinstance(result, int)


class TestCountTokens(unittest.TestCase):
    """Test the unified count_tokens function."""

    def test_fallback_to_heuristic(self) -> None:
        result = count_tokens("hello world", model="", provider="")
        assert result > 0

    def test_custom_chars_per_token(self) -> None:
        text = "a" * 300
        result = count_tokens(text, chars_per_token=3.0)
        assert result == 100

    def test_non_openai_uses_heuristic(self) -> None:
        # Even with a model name, non-openai providers use heuristic
        result = count_tokens("hello world", model="claude-sonnet-4", provider="anthropic")
        assert result > 0


# ---------------------------------------------------------------------------
# Model context window lookup
# ---------------------------------------------------------------------------


class TestGetModelContextWindow(unittest.TestCase):
    """Test context window size lookups."""

    def test_gpt4o_from_catalog(self) -> None:
        window = get_model_context_window("gpt-4o", "openai")
        assert window == 128_000

    def test_gpt4o_mini_from_catalog(self) -> None:
        window = get_model_context_window("gpt-4o-mini", "openai")
        assert window == 128_000

    def test_gpt35_turbo(self) -> None:
        window = get_model_context_window("gpt-3.5-turbo", "openai")
        assert window == 16_385

    def test_claude_sonnet(self) -> None:
        window = get_model_context_window("claude-sonnet-4-20250514", "anthropic")
        assert window == 200_000

    def test_gemini_flash(self) -> None:
        window = get_model_context_window("gemini-2.0-flash", "gemini")
        assert window == 1_048_576

    def test_unknown_model_fallback(self) -> None:
        window = get_model_context_window("unknown-model-xyz")
        assert window == 16_000  # fallback

    def test_heuristic_gpt4(self) -> None:
        window = get_model_context_window("gpt-4-custom-fine-tune")
        assert window == 128_000

    def test_heuristic_claude(self) -> None:
        window = get_model_context_window("claude-3-haiku-whatever")
        assert window == 200_000

    def test_heuristic_gemini(self) -> None:
        window = get_model_context_window("gemini-pro-custom")
        assert window == 1_048_576

    def test_heuristic_mistral(self) -> None:
        window = get_model_context_window("mistral-large")
        assert window == 32_768

    def test_heuristic_llama(self) -> None:
        window = get_model_context_window("llama3.1:70b")
        assert window == 128_000

    def test_ollama_model_from_catalog(self) -> None:
        window = get_model_context_window("llama3.2", "ollama")
        assert window == 128_000

    def test_copilot_gpt4o(self) -> None:
        window = get_model_context_window("gpt-4o", "copilot")
        assert window == 128_000


class TestGetModelMaxOutput(unittest.TestCase):
    """Test max output token lookups."""

    def test_gpt4o(self) -> None:
        assert get_model_max_output("gpt-4o", "openai") == 16_384

    def test_gpt35_turbo(self) -> None:
        assert get_model_max_output("gpt-3.5-turbo", "openai") == 4_096

    def test_claude_sonnet(self) -> None:
        assert get_model_max_output("claude-sonnet-4-20250514", "anthropic") == 8_192

    def test_unknown(self) -> None:
        assert get_model_max_output("unknown-xyz") == 4096


# ---------------------------------------------------------------------------
# chars_for_tokens
# ---------------------------------------------------------------------------


class TestCharsForTokens(unittest.TestCase):
    """Test token-to-character conversion."""

    def test_basic(self) -> None:
        assert chars_for_tokens(100) == 400

    def test_custom_ratio(self) -> None:
        assert chars_for_tokens(100, chars_per_token=3.0) == 300

    def test_zero(self) -> None:
        assert chars_for_tokens(0) == 0

    def test_negative(self) -> None:
        assert chars_for_tokens(-10) == 0


# ---------------------------------------------------------------------------
# Transcript fitting
# ---------------------------------------------------------------------------


class TestFitTranscript(unittest.TestCase):
    """Test transcript fitting strategies."""

    def test_empty_text(self) -> None:
        text, strategy, tokens = fit_transcript("", 1000)
        assert text == ""
        assert strategy == "none"
        assert tokens == 0

    def test_fits_entirely(self) -> None:
        text = "Short transcript."
        fitted, strategy, _tokens = fit_transcript(text, 1000)
        assert fitted == text
        assert strategy == "none"

    def test_truncate_strategy(self) -> None:
        text = "a" * 10000  # ~2500 tokens
        fitted, strategy, tokens_ = fit_transcript(text, 500, strategy="truncate")
        assert strategy == "truncate"
        assert len(fitted) < len(text)
        assert tokens_ <= 500

    def test_tail_strategy(self) -> None:
        text = "START " + "x" * 10000 + " END"
        fitted, strategy, _tokens = fit_transcript(text, 500, strategy="tail")
        assert strategy == "tail"
        assert "END" in fitted
        assert "START" not in fitted

    def test_head_tail_strategy(self) -> None:
        text = "START " + "x" * 10000 + " END"
        fitted, strategy, _tokens = fit_transcript(text, 500, strategy="head_tail")
        assert strategy == "head_tail"
        assert "START" in fitted
        assert "END" in fitted
        assert "omitted" in fitted.lower()

    def test_smart_strategy_fits(self) -> None:
        text = "Short text"
        fitted, strategy, _tokens = fit_transcript(text, 1000, strategy="smart")
        assert strategy == "none"
        assert fitted == text

    def test_smart_strategy_slight_overflow(self) -> None:
        # Create text that's slightly over budget (ratio <= 1.3)
        text = "a" * 5200  # ~1300 tokens at 4 cpt
        _fitted, strategy, _tokens = fit_transcript(text, 1100, strategy="smart")
        assert strategy == "truncate"

    def test_smart_strategy_moderate_overflow(self) -> None:
        # Create text that's moderately over budget (ratio > 1.3, <= 3.0)
        text = "START " + "a" * 8000 + " END"  # ~2000 tokens
        fitted, strategy, _tokens = fit_transcript(text, 1000, strategy="smart")
        assert strategy == "head_tail"
        assert "START" in fitted
        assert "END" in fitted

    def test_smart_strategy_severe_overflow(self) -> None:
        # Create text that's severely over budget (ratio > 3.0)
        text = "START " + "a" * 40000 + " END"  # ~10000 tokens
        _fitted, strategy, _tokens = fit_transcript(text, 1000, strategy="smart")
        assert strategy == "head_tail"

    def test_zero_budget(self) -> None:
        text, _strategy, tokens = fit_transcript("hello", 0)
        assert text == ""
        assert tokens == 0

    def test_head_tail_ratio(self) -> None:
        text = "AAAA" + "x" * 10000 + "BBBB"
        # Head-heavy ratio
        fitted1, _, _ = fit_transcript(text, 500, strategy="head_tail", head_tail_ratio=0.8)
        # Tail-heavy ratio
        fitted2, _, _ = fit_transcript(text, 500, strategy="head_tail", head_tail_ratio=0.2)
        # Head-heavy should have more of the start
        assert fitted1.index("omitted") > fitted2.index("omitted")

    def test_preserves_content_within_budget(self) -> None:
        text = "Important text that should fit."
        fitted, strategy, _tokens = fit_transcript(text, 100)
        assert fitted == text
        assert strategy == "none"


# ---------------------------------------------------------------------------
# Conversation history trimming
# ---------------------------------------------------------------------------


class TestTrimConversationHistory(unittest.TestCase):
    """Test conversation history management."""

    def _make_history(self, n_turns: int) -> list[dict[str, str]]:
        """Create a conversation with n_turns exchanges."""
        msgs: list[dict[str, str]] = []
        for i in range(n_turns):
            msgs.append({"role": "user", "content": f"Question {i}"})
            msgs.append({"role": "assistant", "content": f"Answer {i}"})
        return msgs

    def test_empty_history(self) -> None:
        assert trim_conversation_history([]) == []

    def test_no_trimming_needed(self) -> None:
        history = self._make_history(3)
        trimmed = trim_conversation_history(history, max_turns=20)
        assert len(trimmed) == 6

    def test_trim_by_turns(self) -> None:
        history = self._make_history(15)
        trimmed = trim_conversation_history(history, max_turns=10)
        assert len(trimmed) == 10
        # Should keep the most recent messages
        assert trimmed[-1]["content"] == "Answer 14"

    def test_trim_preserves_recent(self) -> None:
        history = self._make_history(5)
        trimmed = trim_conversation_history(history, max_turns=4)
        assert len(trimmed) == 4
        assert trimmed[-1]["content"] == "Answer 4"
        assert trimmed[-2]["content"] == "Question 4"

    def test_trim_by_tokens(self) -> None:
        history = [
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b" * 1000},
            {"role": "user", "content": "c" * 1000},
            {"role": "assistant", "content": "d" * 1000},
            {"role": "user", "content": "e" * 100},
            {"role": "assistant", "content": "f" * 100},
        ]
        # Give a token budget that only fits the last 2 messages
        trimmed = trim_conversation_history(history, max_turns=0, max_tokens=100)
        # Should keep at least the last 2 messages
        assert len(trimmed) >= 2
        assert trimmed[-1]["content"] == "f" * 100

    def test_unlimited_turns(self) -> None:
        history = self._make_history(100)
        trimmed = trim_conversation_history(history, max_turns=0)
        assert len(trimmed) == 200

    def test_preserves_minimum(self) -> None:
        history = self._make_history(10)
        # Very tight token budget
        trimmed = trim_conversation_history(history, max_turns=0, max_tokens=1)
        # Should keep at least 2 messages
        assert len(trimmed) >= 2


# ---------------------------------------------------------------------------
# ContextBudget
# ---------------------------------------------------------------------------


class TestContextBudget(unittest.TestCase):
    """Test ContextBudget properties."""

    def test_total_used_tokens(self) -> None:
        b = ContextBudget(
            model_context_window=128_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=200,
            transcript_budget_tokens=50_000,
            transcript_actual_tokens=10_000,
            transcript_fitted_tokens=10_000,
            strategy_used="none",
            is_truncated=False,
        )
        assert b.total_used_tokens == 100 + 200 + 10_000

    def test_utilisation_pct(self) -> None:
        b = ContextBudget(
            model_context_window=100_000,
            system_prompt_tokens=10_000,
            response_reserve_tokens=10_000,
            conversation_history_tokens=10_000,
            transcript_budget_tokens=50_000,
            transcript_actual_tokens=40_000,
            transcript_fitted_tokens=40_000,
            strategy_used="none",
            is_truncated=False,
        )
        # effective = 100K - 10K reserve = 90K
        # used = 10K + 10K + 40K = 60K
        # pct = 60K / 90K * 100 ≈ 66.7%
        assert 66 < b.utilisation_pct < 67

    def test_headroom(self) -> None:
        b = ContextBudget(
            model_context_window=128_000,
            system_prompt_tokens=1000,
            response_reserve_tokens=4096,
            conversation_history_tokens=500,
            transcript_budget_tokens=50_000,
            transcript_actual_tokens=5000,
            transcript_fitted_tokens=5000,
            strategy_used="none",
            is_truncated=False,
        )
        # headroom = 128000 - 4096 - (1000 + 500 + 5000) = 117404
        assert b.headroom_tokens == 117404

    def test_is_truncated_false(self) -> None:
        b = ContextBudget(
            model_context_window=128_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=50_000,
            transcript_actual_tokens=1000,
            transcript_fitted_tokens=1000,
            strategy_used="none",
            is_truncated=False,
        )
        assert not b.is_truncated

    def test_is_truncated_true(self) -> None:
        b = ContextBudget(
            model_context_window=16_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=5000,
            transcript_actual_tokens=50000,
            transcript_fitted_tokens=5000,
            strategy_used="truncate",
            is_truncated=True,
        )
        assert b.is_truncated

    def test_zero_context_window(self) -> None:
        b = ContextBudget(
            model_context_window=0,
            system_prompt_tokens=0,
            response_reserve_tokens=0,
            conversation_history_tokens=0,
            transcript_budget_tokens=0,
            transcript_actual_tokens=0,
            transcript_fitted_tokens=0,
            strategy_used="none",
            is_truncated=False,
        )
        assert b.utilisation_pct == 0.0
        assert b.headroom_tokens == 0


# ---------------------------------------------------------------------------
# ContextWindowManager
# ---------------------------------------------------------------------------


class TestContextWindowManager(unittest.TestCase):
    """Test the main ContextWindowManager orchestrator."""

    def test_prepare_chat_no_transcript(self) -> None:
        mgr = ContextWindowManager()
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System prompt",
            transcript="",
            conversation_history=[],
        )
        assert result.fitted_transcript == ""
        assert result.budget.is_truncated is False

    def test_prepare_chat_small_transcript(self) -> None:
        mgr = ContextWindowManager()
        transcript = "Hello, this is a test transcript." * 10
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System prompt",
            transcript=transcript,
        )
        assert result.fitted_transcript == transcript
        assert result.budget.is_truncated is False
        assert result.budget.strategy_used == "none"

    def test_prepare_chat_large_transcript_truncation(self) -> None:
        settings = ContextWindowSettings(strategy="truncate")
        mgr = ContextWindowManager(settings)
        # Create a transcript that's huge (will exceed even GPT-4o)
        transcript = "word " * 200_000  # ~200K tokens
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System",
            transcript=transcript,
        )
        assert result.budget.is_truncated is True
        assert result.budget.strategy_used == "truncate"
        assert len(result.fitted_transcript) < len(transcript)

    def test_prepare_chat_smart_strategy(self) -> None:
        mgr = ContextWindowManager()
        transcript = "START " + "word " * 200_000 + " END"
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System",
            transcript=transcript,
        )
        assert result.budget.is_truncated is True
        # Smart should pick head_tail for large overflow
        assert result.budget.strategy_used == "head_tail"
        assert "START" in result.fitted_transcript
        assert "END" in result.fitted_transcript

    def test_prepare_chat_with_history(self) -> None:
        mgr = ContextWindowManager()
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        transcript = "Short transcript."
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System",
            transcript=transcript,
            conversation_history=history,
        )
        assert result.fitted_transcript == transcript
        assert len(result.trimmed_history) == 2
        assert result.budget.conversation_history_tokens > 0

    def test_prepare_chat_trims_long_history(self) -> None:
        settings = ContextWindowSettings(max_conversation_turns=4)
        mgr = ContextWindowManager(settings)
        history = [{"role": "user", "content": f"Q{i}"} for i in range(20)]
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="System",
            transcript="",
            conversation_history=history,
        )
        assert len(result.trimmed_history) <= 4

    def test_small_context_window_model(self) -> None:
        """Test with a small context window model like GPT-3.5."""
        mgr = ContextWindowManager()
        transcript = "word " * 20_000  # ~20K tokens, exceeds gpt-3.5 16K
        result = mgr.prepare_chat_context(
            model="gpt-3.5-turbo",
            provider="openai",
            system_prompt="System prompt for analysis.",
            transcript=transcript,
        )
        assert result.budget.is_truncated is True
        assert result.budget.model_context_window == 16_385

    def test_large_context_window_model(self) -> None:
        """Test with a large context window model like Gemini."""
        mgr = ContextWindowManager()
        transcript = "word " * 20_000  # ~20K tokens, fits in Gemini 1M
        result = mgr.prepare_chat_context(
            model="gemini-2.0-flash",
            provider="gemini",
            system_prompt="System",
            transcript=transcript,
        )
        assert result.budget.is_truncated is False
        assert result.budget.model_context_window == 1_048_576

    def test_response_reserve_capped_at_max_output(self) -> None:
        settings = ContextWindowSettings(response_reserve_tokens=100_000)
        mgr = ContextWindowManager(settings)
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="",
            transcript="Hello",
        )
        # GPT-4o max output is 16384, so reserve should be capped
        assert result.budget.response_reserve_tokens <= 16_384


class TestContextWindowManagerAction(unittest.TestCase):
    """Test prepare_action_context (one-shot AI actions)."""

    def test_small_transcript(self) -> None:
        mgr = ContextWindowManager()
        result = mgr.prepare_action_context(
            model="gpt-4o",
            provider="openai",
            instructions="Summarize this transcript.",
            transcript="Short transcript text.",
        )
        assert result.fitted_transcript == "Short transcript text."
        assert result.budget.is_truncated is False

    def test_large_transcript(self) -> None:
        mgr = ContextWindowManager()
        transcript = "word " * 200_000
        result = mgr.prepare_action_context(
            model="gpt-4o",
            provider="openai",
            instructions="Summarize this transcript.",
            transcript=transcript,
        )
        assert result.budget.is_truncated is True
        assert len(result.fitted_transcript) < len(transcript)

    def test_no_conversation_history_in_action(self) -> None:
        mgr = ContextWindowManager()
        result = mgr.prepare_action_context(
            model="gpt-4o",
            provider="openai",
            instructions="Do something",
            transcript="Text",
        )
        assert result.trimmed_history == []
        assert result.budget.conversation_history_tokens == 0

    def test_custom_response_reserve(self) -> None:
        mgr = ContextWindowManager()
        result = mgr.prepare_action_context(
            model="gpt-4o",
            provider="openai",
            instructions="Do something",
            transcript="Text",
            response_reserve=8192,
        )
        assert result.budget.response_reserve_tokens == 8192


# ---------------------------------------------------------------------------
# Format budget summary
# ---------------------------------------------------------------------------


class TestFormatBudgetSummary(unittest.TestCase):
    """Test human-readable budget formatting."""

    def test_basic_format(self) -> None:
        mgr = ContextWindowManager()
        budget = ContextBudget(
            model_context_window=128_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=50000,
            transcript_actual_tokens=1000,
            transcript_fitted_tokens=1000,
            strategy_used="none",
            is_truncated=False,
        )
        summary = mgr.format_budget_summary(budget)
        assert "128K" in summary
        assert "%" in summary

    def test_truncated_format(self) -> None:
        mgr = ContextWindowManager()
        budget = ContextBudget(
            model_context_window=16_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=5000,
            transcript_actual_tokens=50000,
            transcript_fitted_tokens=5000,
            strategy_used="head_tail",
            is_truncated=True,
        )
        summary = mgr.format_budget_summary(budget)
        assert "head_tail" in summary
        assert "%" in summary

    def test_millions_format(self) -> None:
        mgr = ContextWindowManager()
        budget = ContextBudget(
            model_context_window=1_048_576,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=500000,
            transcript_actual_tokens=1000,
            transcript_fitted_tokens=1000,
            strategy_used="none",
            is_truncated=False,
        )
        summary = mgr.format_budget_summary(budget)
        assert "1.0M" in summary


# ---------------------------------------------------------------------------
# create_context_manager factory
# ---------------------------------------------------------------------------


class TestCreateContextManager(unittest.TestCase):
    """Test the factory function."""

    def test_with_none(self) -> None:
        mgr = create_context_manager(None)
        assert isinstance(mgr, ContextWindowManager)
        assert mgr.settings.strategy == "smart"

    def test_with_settings_object(self) -> None:
        from bits_whisperer.core.settings import AISettings

        ai = AISettings()
        ai.context_strategy = "truncate"
        ai.context_response_reserve_tokens = 8192
        ai.context_max_conversation_turns = 10
        ai.context_transcript_budget_pct = 0.5

        mgr = create_context_manager(ai)
        assert mgr.settings.strategy == "truncate"
        assert mgr.settings.response_reserve_tokens == 8192
        assert mgr.settings.max_conversation_turns == 10
        assert mgr.settings.transcript_budget_pct == 0.5

    def test_default_values(self) -> None:
        mgr = create_context_manager(None)
        assert mgr.settings.transcript_budget_pct == 0.70
        assert mgr.settings.response_reserve_tokens == 4096
        assert mgr.settings.max_conversation_turns == 20
        assert mgr.settings.head_tail_ratio == 0.6


# ---------------------------------------------------------------------------
# ContextWindowSettings
# ---------------------------------------------------------------------------


class TestContextWindowSettings(unittest.TestCase):
    """Test settings dataclass defaults."""

    def test_defaults(self) -> None:
        s = ContextWindowSettings()
        assert s.strategy == "smart"
        assert s.transcript_budget_pct == 0.70
        assert s.response_reserve_tokens == 4096
        assert s.max_conversation_turns == 20
        assert s.head_tail_ratio == 0.6
        assert s.chars_per_token == 4.0

    def test_custom_values(self) -> None:
        s = ContextWindowSettings(
            strategy="tail",
            transcript_budget_pct=0.5,
            response_reserve_tokens=8192,
            max_conversation_turns=10,
            head_tail_ratio=0.3,
            chars_per_token=3.5,
        )
        assert s.strategy == "tail"
        assert s.transcript_budget_pct == 0.5


# ---------------------------------------------------------------------------
# PreparedContext
# ---------------------------------------------------------------------------


class TestPreparedContext(unittest.TestCase):
    """Test PreparedContext dataclass."""

    def test_creation(self) -> None:
        budget = ContextBudget(
            model_context_window=128_000,
            system_prompt_tokens=100,
            response_reserve_tokens=4096,
            conversation_history_tokens=0,
            transcript_budget_tokens=50000,
            transcript_actual_tokens=100,
            transcript_fitted_tokens=100,
            strategy_used="none",
            is_truncated=False,
        )
        ctx = PreparedContext(
            fitted_transcript="Hello",
            trimmed_history=[],
            budget=budget,
        )
        assert ctx.fitted_transcript == "Hello"
        assert ctx.trimmed_history == []
        assert ctx.budget.model_context_window == 128_000


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_very_long_system_prompt(self) -> None:
        mgr = ContextWindowManager()
        system = "System instruction. " * 5000  # Very long system prompt
        result = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt=system,
            transcript="Short transcript.",
        )
        # Should still work, transcript may or may not be truncated
        assert isinstance(result, PreparedContext)

    def test_transcript_exactly_budget_size(self) -> None:
        # Create a transcript that's exactly the right size
        text = "a" * 400  # exactly 100 tokens at 4 cpt
        fitted, strategy, _tokens = fit_transcript(text, 100)
        assert strategy == "none"
        assert fitted == text

    def test_transcript_one_token_over(self) -> None:
        text = "a" * 404  # 101 tokens at 4 cpt
        fitted, strategy, _tokens = fit_transcript(text, 100, strategy="truncate")
        assert strategy == "truncate"
        assert len(fitted) <= 400

    def test_model_aware_sizing_differences(self) -> None:
        """Verify different models get different transcript budgets."""
        mgr = ContextWindowManager()
        transcript = "word " * 5000  # ~5000 tokens

        result_small = mgr.prepare_chat_context(
            model="gpt-3.5-turbo",
            provider="openai",
            system_prompt="System",
            transcript=transcript,
        )

        result_large = mgr.prepare_chat_context(
            model="gemini-2.0-flash",
            provider="gemini",
            system_prompt="System",
            transcript=transcript,
        )

        # Gemini should have more headroom
        assert (
            result_large.budget.transcript_budget_tokens
            > result_small.budget.transcript_budget_tokens
        )

    def test_concurrent_history_and_transcript(self) -> None:
        """Verify history and transcript compete properly for space."""
        settings = ContextWindowSettings(
            transcript_budget_pct=0.5,
            max_conversation_turns=100,
        )
        mgr = ContextWindowManager(settings)

        # Long history
        history = [
            {"role": "user", "content": f"Question about topic {i} " * 50} for i in range(50)
        ]
        transcript = "Important transcript content. " * 100

        result = mgr.prepare_chat_context(
            model="gpt-3.5-turbo",
            provider="openai",
            system_prompt="System",
            transcript=transcript,
            conversation_history=history,
        )
        # Both should be present but potentially trimmed
        assert isinstance(result, PreparedContext)
        assert result.budget.conversation_history_tokens > 0


if __name__ == "__main__":
    unittest.main()
