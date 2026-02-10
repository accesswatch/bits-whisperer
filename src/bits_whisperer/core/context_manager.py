"""Context window management for AI operations.

Provides model-aware token budgeting, transcript fitting, and
conversation history management.  Replaces the hardcoded ``[:50000]``
character truncation with intelligent, per-model strategies.

Strategies
----------
- **truncate** – keep the first *N* tokens (head truncation).
- **tail** – keep the last *N* tokens.
- **head_tail** – preserve beginning and end, elide the middle with a
  marker so the model sees both the start and finish of a transcript.
- **smart** – automatically choose the best strategy based on how
  much of the transcript fits: if it fits entirely, use it in full;
  if only small overflow, head-truncate; if severe overflow, use
  head + tail.

Token Estimation
----------------
Uses ``len(text) / chars_per_token`` as a fast heuristic (default 4
chars/token for English).  When ``tiktoken`` is available **and** the
model is an OpenAI model, precise BPE counting is used instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default characters-per-token ratio for heuristic estimation.
# English text averages ~4 chars per token across GPT / Claude / Gemini.
_DEFAULT_CHARS_PER_TOKEN: Final[float] = 4.0

# Fallback context window when the model is unknown.
_FALLBACK_CONTEXT_WINDOW: Final[int] = 16_000

# Minimum tokens to reserve so the model can produce a meaningful answer.
_MIN_RESPONSE_RESERVE: Final[int] = 512

# Marker inserted when the middle of a transcript is elided.
_ELISION_MARKER: Final[str] = (
    "\n\n[... middle of transcript omitted due to length — "
    "{omitted_tokens:,} tokens elided ...]\n\n"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBudget:
    """Token budget allocation for a single AI call.

    All values are in **tokens** (estimated or precise).
    """

    model_context_window: int
    """Total context window of the selected model."""

    system_prompt_tokens: int
    """Tokens consumed by the system prompt / instructions."""

    response_reserve_tokens: int
    """Tokens reserved for the model's response."""

    conversation_history_tokens: int
    """Tokens consumed by prior conversation turns."""

    transcript_budget_tokens: int
    """Tokens available for transcript context (the remainder)."""

    transcript_actual_tokens: int
    """Estimated tokens in the full, untruncated transcript."""

    transcript_fitted_tokens: int
    """Tokens in the transcript text after fitting to the budget."""

    strategy_used: str
    """Which fitting strategy was applied (none/truncate/tail/head_tail/smart)."""

    is_truncated: bool
    """Whether the transcript was truncated to fit."""

    @property
    def total_used_tokens(self) -> int:
        """Total tokens consumed (system + history + fitted transcript)."""
        return (
            self.system_prompt_tokens
            + self.conversation_history_tokens
            + self.transcript_fitted_tokens
        )

    @property
    def utilisation_pct(self) -> float:
        """Percentage of the context window used (0-100)."""
        if self.model_context_window <= 0:
            return 0.0
        effective = self.model_context_window - self.response_reserve_tokens
        if effective <= 0:
            return 100.0
        return min(100.0, (self.total_used_tokens / effective) * 100.0)

    @property
    def headroom_tokens(self) -> int:
        """Free tokens remaining after all allocations."""
        return max(
            0,
            self.model_context_window - self.response_reserve_tokens - self.total_used_tokens,
        )


@dataclass
class ContextWindowSettings:
    """User-configurable knobs for context management.

    These defaults work well for most workflows; power users can
    adjust them via the AI settings dialog.
    """

    strategy: str = "smart"
    """Fitting strategy: 'truncate', 'tail', 'head_tail', 'smart'."""

    transcript_budget_pct: float = 0.70
    """Fraction of *available* context to allocate to transcript (0.0–1.0)."""

    response_reserve_tokens: int = 4096
    """Tokens reserved for the model's response."""

    max_conversation_turns: int = 20
    """Maximum conversation turns to keep in history (0 = unlimited)."""

    head_tail_ratio: float = 0.6
    """In head_tail strategy, fraction of budget for the head portion."""

    chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN
    """Characters-per-token ratio for heuristic estimation."""


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def estimate_tokens(text: str, *, chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate the number of tokens in *text* using a character ratio.

    Args:
        text: Input text.
        chars_per_token: Average characters per token.

    Returns:
        Estimated token count (always >= 0).
    """
    if not text:
        return 0
    return max(1, int(len(text) / chars_per_token + 0.5))


def estimate_tokens_precise(text: str, model: str = "gpt-4o") -> int | None:
    """Attempt precise token counting via ``tiktoken``.

    Returns ``None`` if tiktoken is unavailable or the model is not
    recognised.

    Args:
        text: Input text.
        model: OpenAI model identifier.

    Returns:
        Exact token count, or None on failure.
    """
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return None


def count_tokens(
    text: str,
    *,
    model: str = "",
    provider: str = "",
    chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN,
) -> int:
    """Count (or estimate) the tokens in *text*.

    Tries ``tiktoken`` for OpenAI models first, then falls back to
    the heuristic estimator.

    Args:
        text: Input text.
        model: Model identifier for precise counting.
        provider: Provider identifier (e.g. 'openai').
        chars_per_token: Fallback chars-per-token ratio.

    Returns:
        Token count.
    """
    if provider in ("openai", "azure_openai") and model:
        precise = estimate_tokens_precise(text, model)
        if precise is not None:
            return precise
    return estimate_tokens(text, chars_per_token=chars_per_token)


# ---------------------------------------------------------------------------
# Model context window lookup
# ---------------------------------------------------------------------------


def get_model_context_window(model: str, provider: str = "") -> int:
    """Return the context window size (in tokens) for a model.

    Uses the model catalog in :mod:`constants`.  Returns a safe
    fallback when the model is unknown (e.g. custom Ollama models).

    Args:
        model: Model identifier.
        provider: Provider identifier.

    Returns:
        Context window in tokens.
    """
    try:
        from bits_whisperer.utils.constants import get_ai_model_by_id

        info = get_ai_model_by_id(model, provider)
        if info and info.context_window > 0:
            return info.context_window
    except Exception:
        pass

    # Heuristic fallbacks for models not in the catalog
    model_lower = model.lower() if model else ""
    if "gpt-4" in model_lower or "gpt4" in model_lower:
        return 128_000
    if "gpt-3.5" in model_lower:
        return 16_385
    if "claude" in model_lower:
        return 200_000
    if "gemini" in model_lower:
        return 1_048_576
    if "llama" in model_lower:
        return 128_000
    if "mistral" in model_lower:
        return 32_768

    return _FALLBACK_CONTEXT_WINDOW


def get_model_max_output(model: str, provider: str = "") -> int:
    """Return the max output tokens for a model.

    Args:
        model: Model identifier.
        provider: Provider identifier.

    Returns:
        Maximum output tokens.
    """
    try:
        from bits_whisperer.utils.constants import get_ai_model_by_id

        info = get_ai_model_by_id(model, provider)
        if info and info.max_output_tokens > 0:
            return info.max_output_tokens
    except Exception:
        pass
    return 4096


# ---------------------------------------------------------------------------
# Transcript fitting
# ---------------------------------------------------------------------------


def chars_for_tokens(tokens: int, chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN) -> int:
    """Convert a token count to an approximate character count.

    Args:
        tokens: Number of tokens.
        chars_per_token: Characters per token ratio.

    Returns:
        Approximate character count.
    """
    return max(0, int(tokens * chars_per_token))


def fit_transcript(
    text: str,
    budget_tokens: int,
    *,
    strategy: str = "smart",
    head_tail_ratio: float = 0.6,
    chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN,
    model: str = "",
    provider: str = "",
) -> tuple[str, str, int]:
    """Fit transcript text into a token budget.

    Args:
        text: Full transcript text.
        budget_tokens: Maximum tokens the transcript may occupy.
        strategy: 'truncate', 'tail', 'head_tail', or 'smart'.
        head_tail_ratio: For head_tail, fraction of budget for the head.
        chars_per_token: Chars-per-token for estimation.
        model: Model ID for precise counting.
        provider: Provider ID.

    Returns:
        Tuple of (fitted_text, strategy_used, fitted_token_count).
    """
    if not text or budget_tokens <= 0:
        return "", strategy if text else "none", 0

    actual_tokens = count_tokens(
        text, model=model, provider=provider, chars_per_token=chars_per_token
    )

    # Fits without truncation
    if actual_tokens <= budget_tokens:
        return text, "none", actual_tokens

    # Choose strategy
    effective_strategy = strategy
    if strategy == "smart":
        ratio = actual_tokens / budget_tokens if budget_tokens > 0 else float("inf")
        if ratio <= 1.3:
            # Only slightly over — just trim the end
            effective_strategy = "truncate"
        elif ratio <= 3.0:
            # Moderate overflow — head + tail preserves key info
            effective_strategy = "head_tail"
        else:
            # Severe overflow — head + tail is still best but user should know
            effective_strategy = "head_tail"

    max_chars = chars_for_tokens(budget_tokens, chars_per_token)

    if effective_strategy == "truncate":
        fitted = text[:max_chars]
        fitted_tokens = count_tokens(
            fitted, model=model, provider=provider, chars_per_token=chars_per_token
        )
        return fitted, "truncate", fitted_tokens

    elif effective_strategy == "tail":
        fitted = text[-max_chars:]
        fitted_tokens = count_tokens(
            fitted, model=model, provider=provider, chars_per_token=chars_per_token
        )
        return fitted, "tail", fitted_tokens

    elif effective_strategy == "head_tail":
        # Reserve a small amount for the elision marker
        marker_tokens = 30
        usable = budget_tokens - marker_tokens
        if usable <= 0:
            return text[:max_chars], "truncate", budget_tokens

        head_tokens = int(usable * head_tail_ratio)
        tail_tokens = usable - head_tokens

        head_chars = chars_for_tokens(head_tokens, chars_per_token)
        tail_chars = chars_for_tokens(tail_tokens, chars_per_token)

        head_text = text[:head_chars]
        tail_text = text[-tail_chars:] if tail_chars > 0 else ""

        omitted = actual_tokens - head_tokens - tail_tokens
        marker = _ELISION_MARKER.format(omitted_tokens=max(0, omitted))

        fitted = head_text + marker + tail_text
        fitted_tokens = count_tokens(
            fitted, model=model, provider=provider, chars_per_token=chars_per_token
        )
        return fitted, "head_tail", fitted_tokens

    # Fallback
    fitted = text[:max_chars]
    fitted_tokens = count_tokens(
        fitted, model=model, provider=provider, chars_per_token=chars_per_token
    )
    return fitted, "truncate", fitted_tokens


# ---------------------------------------------------------------------------
# Conversation history management
# ---------------------------------------------------------------------------


def trim_conversation_history(
    messages: list[dict[str, str]],
    max_turns: int = 20,
    max_tokens: int = 0,
    *,
    chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN,
    model: str = "",
    provider: str = "",
) -> list[dict[str, str]]:
    """Trim conversation history to fit within limits.

    Removes the **oldest** message pairs first, always preserving the
    most recent exchange.  A "turn" here is a single user or assistant
    message.

    Args:
        messages: Full conversation history.
        max_turns: Maximum number of messages to keep (0 = unlimited).
        max_tokens: Maximum total tokens for history (0 = unlimited).
        chars_per_token: For heuristic estimation.
        model: Model identifier for precise counting.
        provider: Provider identifier.

    Returns:
        Trimmed copy of the message list.
    """
    if not messages:
        return []

    result = list(messages)

    # Trim by turn count
    if max_turns > 0 and len(result) > max_turns:
        result = result[-max_turns:]

    # Trim by token budget
    if max_tokens > 0:
        while len(result) > 2:  # Keep at least the last exchange
            total = sum(
                count_tokens(
                    m.get("content", ""),
                    model=model,
                    provider=provider,
                    chars_per_token=chars_per_token,
                )
                for m in result
            )
            if total <= max_tokens:
                break
            result.pop(0)

    return result


# ---------------------------------------------------------------------------
# ContextWindowManager — main orchestrator
# ---------------------------------------------------------------------------


class ContextWindowManager:
    """Orchestrates context window budgeting for AI calls.

    Usage::

        mgr = ContextWindowManager(settings)
        budget = mgr.prepare_chat_context(
            model="gpt-4o",
            provider="openai",
            system_prompt="You are a helpful assistant.",
            transcript="...",
            conversation_history=[...],
        )
        # budget.fitted_transcript is the transcript to send
        # budget.trimmed_history is the conversation history to send
    """

    def __init__(self, settings: ContextWindowSettings | None = None) -> None:
        """Initialise with optional settings.

        Args:
            settings: Context window configuration.  Uses defaults if None.
        """
        self.settings = settings or ContextWindowSettings()

    def prepare_chat_context(
        self,
        *,
        model: str = "",
        provider: str = "",
        system_prompt: str = "",
        transcript: str = "",
        conversation_history: list[dict[str, str]] | None = None,
        response_reserve: int | None = None,
    ) -> PreparedContext:
        """Prepare all context components to fit within the model's window.

        Steps:
            1. Look up model context window.
            2. Estimate system prompt tokens.
            3. Reserve response tokens.
            4. Trim conversation history.
            5. Estimate remaining budget for transcript.
            6. Fit transcript to budget.

        Args:
            model: AI model identifier.
            provider: AI provider identifier.
            system_prompt: System prompt text.
            transcript: Full transcript text.
            conversation_history: Chat history messages.
            response_reserve: Override response token reservation.

        Returns:
            PreparedContext with fitted text and budget info.
        """
        cpt = self.settings.chars_per_token

        # 1. Model limits
        context_window = get_model_context_window(model, provider)
        max_output = get_model_max_output(model, provider)

        # 2. Response reserve
        reserve = response_reserve or self.settings.response_reserve_tokens
        reserve = max(reserve, _MIN_RESPONSE_RESERVE)
        # Don't reserve more than the model can output
        reserve = min(reserve, max_output)

        available = context_window - reserve
        if available <= 0:
            logger.warning(
                "Context window (%d) minus response reserve (%d) leaves no room",
                context_window,
                reserve,
            )
            return PreparedContext(
                fitted_transcript="",
                trimmed_history=[],
                budget=ContextBudget(
                    model_context_window=context_window,
                    system_prompt_tokens=0,
                    response_reserve_tokens=reserve,
                    conversation_history_tokens=0,
                    transcript_budget_tokens=0,
                    transcript_actual_tokens=estimate_tokens(transcript, chars_per_token=cpt),
                    transcript_fitted_tokens=0,
                    strategy_used="none",
                    is_truncated=bool(transcript),
                ),
            )

        # 3. System prompt
        sys_tokens = count_tokens(
            system_prompt, model=model, provider=provider, chars_per_token=cpt
        )
        available -= sys_tokens

        # 4. Conversation history
        history = list(conversation_history or [])
        if self.settings.max_conversation_turns > 0:
            history = trim_conversation_history(
                history,
                max_turns=self.settings.max_conversation_turns,
                chars_per_token=cpt,
                model=model,
                provider=provider,
            )

        history_tokens = sum(
            count_tokens(m.get("content", ""), model=model, provider=provider, chars_per_token=cpt)
            for m in history
        )

        # If history alone overflows, trim further
        max_history_tokens = int(available * (1.0 - self.settings.transcript_budget_pct))
        if history_tokens > max_history_tokens and max_history_tokens > 0:
            history = trim_conversation_history(
                history,
                max_turns=0,
                max_tokens=max_history_tokens,
                chars_per_token=cpt,
                model=model,
                provider=provider,
            )
            history_tokens = sum(
                count_tokens(
                    m.get("content", ""), model=model, provider=provider, chars_per_token=cpt
                )
                for m in history
            )

        available -= history_tokens

        # 5. Transcript budget
        transcript_budget = max(0, int(available * self.settings.transcript_budget_pct))
        # If there's no history, give all available space to transcript
        if not history:
            transcript_budget = max(0, available)

        # 6. Fit transcript
        transcript_actual_tokens = count_tokens(
            transcript, model=model, provider=provider, chars_per_token=cpt
        )

        fitted_text, strategy_used, fitted_tokens = fit_transcript(
            transcript,
            transcript_budget,
            strategy=self.settings.strategy,
            head_tail_ratio=self.settings.head_tail_ratio,
            chars_per_token=cpt,
            model=model,
            provider=provider,
        )

        budget = ContextBudget(
            model_context_window=context_window,
            system_prompt_tokens=sys_tokens,
            response_reserve_tokens=reserve,
            conversation_history_tokens=history_tokens,
            transcript_budget_tokens=transcript_budget,
            transcript_actual_tokens=transcript_actual_tokens,
            transcript_fitted_tokens=fitted_tokens,
            strategy_used=strategy_used,
            is_truncated=strategy_used != "none",
        )

        logger.info(
            "Context budget: window=%d, sys=%d, history=%d (%d msgs), "
            "transcript=%d/%d (budget=%d, strategy=%s), reserve=%d, "
            "utilisation=%.1f%%",
            context_window,
            sys_tokens,
            history_tokens,
            len(history),
            fitted_tokens,
            transcript_actual_tokens,
            transcript_budget,
            strategy_used,
            reserve,
            budget.utilisation_pct,
        )

        return PreparedContext(
            fitted_transcript=fitted_text,
            trimmed_history=history,
            budget=budget,
        )

    def prepare_action_context(
        self,
        *,
        model: str = "",
        provider: str = "",
        instructions: str = "",
        transcript: str = "",
        attachments_text: str = "",
        response_reserve: int | None = None,
    ) -> PreparedContext:
        """Prepare context for a one-shot AI action (no conversation history).

        Simpler than :meth:`prepare_chat_context` — allocates maximum
        space to the transcript since there is no chat history.

        Args:
            model: AI model identifier.
            provider: AI provider identifier.
            instructions: AI action instructions/prompt.
            transcript: Full transcript text.
            attachments_text: Pre-formatted text from attached documents.
            response_reserve: Override response token reservation.

        Returns:
            PreparedContext with fitted text and budget info.
        """
        cpt = self.settings.chars_per_token

        context_window = get_model_context_window(model, provider)
        max_output = get_model_max_output(model, provider)

        reserve = response_reserve or self.settings.response_reserve_tokens
        reserve = max(reserve, _MIN_RESPONSE_RESERVE)
        reserve = min(reserve, max_output)

        # Instructions token count (includes the framing text around transcript)
        framing_overhead = (
            "\n\n--- TRANSCRIPT ---\n\n--- END TRANSCRIPT ---\n\n"
            "Please process this transcript according to the instructions above."
        )
        # Account for attachment tokens in the fixed overhead
        attachment_tokens = 0
        if attachments_text:
            attachment_framing = (
                "\n\n--- ATTACHED DOCUMENTS ---\n"
                + attachments_text
                + "\n--- END ATTACHED DOCUMENTS ---\n"
            )
            attachment_tokens = count_tokens(
                attachment_framing,
                model=model,
                provider=provider,
                chars_per_token=cpt,
            )

        instructions_tokens = count_tokens(
            instructions + framing_overhead,
            model=model,
            provider=provider,
            chars_per_token=cpt,
        )

        fixed_tokens = instructions_tokens + attachment_tokens
        transcript_budget = max(0, context_window - reserve - fixed_tokens)

        transcript_actual_tokens = count_tokens(
            transcript, model=model, provider=provider, chars_per_token=cpt
        )

        fitted_text, strategy_used, fitted_tokens = fit_transcript(
            transcript,
            transcript_budget,
            strategy=self.settings.strategy,
            head_tail_ratio=self.settings.head_tail_ratio,
            chars_per_token=cpt,
            model=model,
            provider=provider,
        )

        budget = ContextBudget(
            model_context_window=context_window,
            system_prompt_tokens=fixed_tokens,
            response_reserve_tokens=reserve,
            conversation_history_tokens=0,
            transcript_budget_tokens=transcript_budget,
            transcript_actual_tokens=transcript_actual_tokens,
            transcript_fitted_tokens=fitted_tokens,
            strategy_used=strategy_used,
            is_truncated=strategy_used != "none",
        )

        logger.info(
            "Action context budget: window=%d, instructions=%d, "
            "attachments=%d, transcript=%d/%d (budget=%d, strategy=%s), "
            "reserve=%d, utilisation=%.1f%%",
            context_window,
            instructions_tokens,
            attachment_tokens,
            fitted_tokens,
            transcript_actual_tokens,
            transcript_budget,
            strategy_used,
            reserve,
            budget.utilisation_pct,
        )

        return PreparedContext(
            fitted_transcript=fitted_text,
            trimmed_history=[],
            budget=budget,
        )

    def format_budget_summary(self, budget: ContextBudget) -> str:
        """Format a human-readable budget summary for status display.

        Args:
            budget: The context budget to summarize.

        Returns:
            Short string like "Context: 45K/128K tokens (35%)"
        """

        def _fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.0f}K"
            return str(n)

        used = budget.total_used_tokens + budget.response_reserve_tokens
        window = budget.model_context_window
        pct = budget.utilisation_pct

        parts = [f"Context: {_fmt(used)}/{_fmt(window)} tokens ({pct:.0f}%)"]

        if budget.is_truncated:
            parts.append(f"transcript {budget.strategy_used}")

        return " \u2022 ".join(parts)


# ---------------------------------------------------------------------------
# Prepared context result
# ---------------------------------------------------------------------------


@dataclass
class PreparedContext:
    """Result of context preparation — ready to send to an AI provider."""

    fitted_transcript: str
    """Transcript text fitted to the available budget."""

    trimmed_history: list[dict[str, str]]
    """Conversation history after trimming."""

    budget: ContextBudget
    """Detailed budget breakdown."""


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def create_context_manager(
    ai_settings: object | None = None,
) -> ContextWindowManager:
    """Create a :class:`ContextWindowManager` from application settings.

    Reads context-related fields from ``AISettings`` if available,
    otherwise uses defaults.

    Args:
        ai_settings: An ``AISettings`` instance (or None for defaults).

    Returns:
        Configured ContextWindowManager.
    """
    ctx_settings = ContextWindowSettings()

    if ai_settings is not None:
        # Read context settings from AISettings if they exist
        ctx_settings.strategy = getattr(ai_settings, "context_strategy", "smart")
        ctx_settings.transcript_budget_pct = getattr(
            ai_settings, "context_transcript_budget_pct", 0.70
        )
        ctx_settings.response_reserve_tokens = getattr(
            ai_settings, "context_response_reserve_tokens", 4096
        )
        ctx_settings.max_conversation_turns = getattr(
            ai_settings, "context_max_conversation_turns", 20
        )

    return ContextWindowManager(ctx_settings)
