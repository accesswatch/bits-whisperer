"""AI service for transcript translation and summarization.

Supports multiple LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude Sonnet, Claude Haiku)
- Azure OpenAI (configurable deployment)

Each provider is accessed through a unified interface that handles
prompt construction, API calls, and response parsing.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bits_whisperer.core.settings import AISettings
    from bits_whisperer.storage.key_store import KeyStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AIResponse:
    """Response from an AI provider."""

    text: str
    provider: str
    model: str
    tokens_used: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_TRANSLATE_PROMPT = (
    "Translate the following transcript to {target_language}. "
    "Preserve speaker labels, timestamps, and formatting exactly as they appear. "
    "Only translate the spoken content.\n\n"
    "Transcript:\n{text}"
)

_SUMMARIZE_CONCISE = (
    "Summarize the following transcript in a concise paragraph (3-5 sentences). "
    "Capture the main topics, key decisions, and action items.\n\n"
    "Transcript:\n{text}"
)

_SUMMARIZE_DETAILED = (
    "Provide a detailed summary of the following transcript. "
    "Include main topics discussed, key points from each speaker, "
    "decisions made, and any action items or follow-ups mentioned.\n\n"
    "Transcript:\n{text}"
)

_SUMMARIZE_BULLETS = (
    "Summarize the following transcript as a bulleted list. "
    "Each bullet should capture one key point, decision, or action item. "
    "Group related points together with sub-bullets if appropriate.\n\n"
    "Transcript:\n{text}"
)

_SUMMARIZE_STYLES = {
    "concise": _SUMMARIZE_CONCISE,
    "detailed": _SUMMARIZE_DETAILED,
    "bullet_points": _SUMMARIZE_BULLETS,
}


# ---------------------------------------------------------------------------
# Provider ABCs
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """Abstract base for AI text generation providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text from a prompt.

        Args:
            prompt: The input prompt.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            AIResponse with generated text.
        """
        ...

    @abstractmethod
    def validate_key(self, api_key: str) -> bool:
        """Validate an API key with a lightweight test call.

        Args:
            api_key: The API key to test.

        Returns:
            True if the key is valid.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIAIProvider(AIProvider):
    """AI provider using OpenAI's GPT models."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self._model = model

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using OpenAI Chat Completions API."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that processes transcripts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return AIResponse(
                text=text,
                provider="openai",
                model=self._model,
                tokens_used=tokens,
            )
        except ImportError:
            return AIResponse(
                text="",
                provider="openai",
                model=self._model,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("OpenAI generation failed")
            return AIResponse(
                text="",
                provider="openai",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate OpenAI API key with a models list call."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            client.models.list()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicAIProvider(AIProvider):
    """AI provider using Anthropic's Claude models."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using Anthropic Messages API."""
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text if response.content else ""
            tokens_in = response.usage.input_tokens if response.usage else 0
            tokens_out = response.usage.output_tokens if response.usage else 0
            return AIResponse(
                text=text,
                provider="anthropic",
                model=self._model,
                tokens_used=tokens_in + tokens_out,
            )
        except ImportError:
            return AIResponse(
                text="",
                provider="anthropic",
                model=self._model,
                error="Anthropic SDK not installed. Install with: pip install anthropic",
            )
        except Exception as exc:
            logger.exception("Anthropic generation failed")
            return AIResponse(
                text="",
                provider="anthropic",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Anthropic API key with a minimal message call."""
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Azure OpenAI provider
# ---------------------------------------------------------------------------


class AzureOpenAIProvider(AIProvider):
    """AI provider using Azure OpenAI Service (Copilot-compatible)."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._deployment = deployment

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using Azure OpenAI Chat Completions API."""
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=self._api_key,
                api_version="2024-06-01",
                azure_endpoint=self._endpoint,
            )
            response = client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that processes transcripts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return AIResponse(
                text=text,
                provider="azure_openai",
                model=self._deployment,
                tokens_used=tokens,
            )
        except ImportError:
            return AIResponse(
                text="",
                provider="azure_openai",
                model=self._deployment,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("Azure OpenAI generation failed")
            return AIResponse(
                text="",
                provider="azure_openai",
                model=self._deployment,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Azure OpenAI key with a test call."""
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=api_key,
                api_version="2024-06-01",
                azure_endpoint=self._endpoint,
            )
            client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# AI Service — main entry point
# ---------------------------------------------------------------------------


class AIService:
    """Unified AI service for transcript translation and summarization.

    Reads configuration from AppSettings and uses the appropriate
    provider based on user preferences.
    """

    def __init__(self, key_store: KeyStore, settings: AISettings) -> None:
        """Initialise the AI service.

        Args:
            key_store: Key store for retrieving API keys.
            settings: AI configuration settings.
        """
        self._key_store = key_store
        self._settings = settings

    def _get_provider(self) -> AIProvider | None:
        """Create the configured AI provider instance.

        Returns:
            AIProvider instance, or None if not configured.
        """
        provider_id = self._settings.selected_provider

        if provider_id == "openai":
            api_key = self._key_store.get_key("openai")
            if not api_key:
                return None
            return OpenAIAIProvider(api_key, self._settings.openai_model)

        elif provider_id == "anthropic":
            api_key = self._key_store.get_key("anthropic")
            if not api_key:
                return None
            return AnthropicAIProvider(api_key, self._settings.anthropic_model)

        elif provider_id == "azure_openai":
            api_key = self._key_store.get_key("azure_openai")
            endpoint = (
                self._key_store.get_key("azure_openai_endpoint")
                or self._settings.azure_openai_endpoint
            )
            deployment = (
                self._key_store.get_key("azure_openai_deployment")
                or self._settings.azure_openai_deployment
            )
            if not api_key or not endpoint or not deployment:
                return None
            return AzureOpenAIProvider(api_key, endpoint, deployment)

        return None

    def is_configured(self) -> bool:
        """Check whether the AI service has a valid provider configured.

        Returns:
            True if a provider can be created.
        """
        return self._get_provider() is not None

    def get_available_providers(self) -> list[dict[str, str]]:
        """List AI providers that have API keys configured.

        Returns:
            List of dicts with 'id' and 'name' keys.
        """
        available: list[dict[str, str]] = []
        if self._key_store.has_key("openai"):
            available.append({"id": "openai", "name": "OpenAI (GPT-4o)"})
        if self._key_store.has_key("anthropic"):
            available.append({"id": "anthropic", "name": "Anthropic (Claude)"})
        if self._key_store.has_key("azure_openai"):
            available.append({"id": "azure_openai", "name": "Azure OpenAI (Copilot)"})
        return available

    def translate(
        self,
        text: str,
        target_language: str = "",
    ) -> AIResponse:
        """Translate transcript text to the target language.

        Args:
            text: The transcript text to translate.
            target_language: Target language (e.g. 'Spanish', 'French').
                Falls back to settings default.

        Returns:
            AIResponse with translated text.
        """
        provider = self._get_provider()
        if not provider:
            return AIResponse(
                text="",
                provider="",
                model="",
                error="No AI provider configured. Add an API key in Settings.",
            )

        lang = target_language or self._settings.translation_target_language
        prompt = _TRANSLATE_PROMPT.format(target_language=lang, text=text)

        return provider.generate(
            prompt,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )

    def summarize(
        self,
        text: str,
        style: str = "",
    ) -> AIResponse:
        """Summarize transcript text.

        Args:
            text: The transcript text to summarize.
            style: Summary style ('concise', 'detailed', 'bullet_points').
                Falls back to settings default.

        Returns:
            AIResponse with summary text.
        """
        provider = self._get_provider()
        if not provider:
            return AIResponse(
                text="",
                provider="",
                model="",
                error="No AI provider configured. Add an API key in Settings.",
            )

        chosen_style = style or self._settings.summarization_style
        template = _SUMMARIZE_STYLES.get(chosen_style, _SUMMARIZE_CONCISE)
        prompt = template.format(text=text)

        return provider.generate(
            prompt,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )
