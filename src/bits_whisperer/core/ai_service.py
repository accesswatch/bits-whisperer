"""AI service for transcript translation and summarization.

Supports multiple LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude Sonnet, Claude Haiku)
- Azure OpenAI (configurable deployment)
- Google Gemini (Gemini 2.0 Flash, Gemini 2.5 Pro)
- GitHub Copilot (via Copilot SDK — GPT-4o, Claude, etc.)

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
# Google Gemini provider
# ---------------------------------------------------------------------------


class GeminiAIProvider(AIProvider):
    """AI provider using Google Gemini models."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._api_key = api_key
        self._model = model

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using Google Gemini API."""
        try:
            from google import genai

            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                    "system_instruction": (
                        "You are a helpful assistant that processes transcripts."
                    ),
                },
            )
            text = response.text or ""
            tokens = 0
            if response.usage_metadata:
                tokens = (response.usage_metadata.prompt_token_count or 0) + (
                    response.usage_metadata.candidates_token_count or 0
                )
            return AIResponse(
                text=text,
                provider="gemini",
                model=self._model,
                tokens_used=tokens,
            )
        except ImportError:
            return AIResponse(
                text="",
                provider="gemini",
                model=self._model,
                error="Google GenAI SDK not installed. Install with: pip install google-genai",
            )
        except Exception as exc:
            logger.exception("Gemini generation failed")
            return AIResponse(
                text="",
                provider="gemini",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Gemini API key with a minimal generation call."""
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            client.models.generate_content(
                model="gemini-2.0-flash",
                contents="hi",
                config={"max_output_tokens": 5},
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# GitHub Copilot provider (via Copilot SDK)
# ---------------------------------------------------------------------------


class CopilotAIProvider(AIProvider):
    """AI provider using GitHub Copilot SDK for LLM access.

    Requires the GitHub Copilot CLI to be installed and authenticated.
    Uses the ``github-copilot-sdk`` Python package for communication.
    """

    def __init__(
        self,
        github_token: str = "",
        model: str = "gpt-4o",
        cli_path: str = "",
    ) -> None:
        self._github_token = github_token
        self._model = model
        self._cli_path = cli_path

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using GitHub Copilot SDK."""
        try:
            import asyncio

            from github_copilot import CopilotClient

            async def _run() -> AIResponse:
                client_kwargs: dict[str, Any] = {"auto_start": True}
                if self._github_token:
                    client_kwargs["github_token"] = self._github_token
                elif not self._github_token:
                    client_kwargs["use_logged_in_user"] = True
                if self._cli_path:
                    client_kwargs["cli_path"] = self._cli_path

                client = CopilotClient(**client_kwargs)
                await client.start()
                try:
                    session = await client.create_session(
                        model=self._model,
                        system_message=("You are a helpful assistant that processes transcripts."),
                    )
                    result_text = ""
                    response = await session.send(prompt)
                    if hasattr(response, "text"):
                        result_text = response.text or ""
                    elif hasattr(response, "content"):
                        result_text = response.content or ""
                    else:
                        result_text = str(response)
                    await session.destroy()
                    return AIResponse(
                        text=result_text,
                        provider="copilot",
                        model=self._model,
                    )
                finally:
                    await client.stop()

            # Run the async function — create a new event loop if needed
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We're inside an existing event loop — use a thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    return future.result(timeout=120)
            else:
                return asyncio.run(_run())

        except ImportError:
            return AIResponse(
                text="",
                provider="copilot",
                model=self._model,
                error=(
                    "GitHub Copilot SDK not installed. "
                    "Install with: pip install github-copilot-sdk"
                ),
            )
        except Exception as exc:
            logger.exception("Copilot generation failed")
            return AIResponse(
                text="",
                provider="copilot",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Copilot connection by starting a test session."""
        try:
            import asyncio

            from github_copilot import CopilotClient

            async def _test() -> bool:
                client_kwargs: dict[str, Any] = {"auto_start": True}
                if api_key:
                    client_kwargs["github_token"] = api_key
                else:
                    client_kwargs["use_logged_in_user"] = True
                client = CopilotClient(**client_kwargs)
                await client.start()
                try:
                    session = await client.create_session(model="gpt-4o")
                    await session.destroy()
                    return True
                finally:
                    await client.stop()

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _test())
                    return future.result(timeout=30)
            else:
                return asyncio.run(_test())
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

        elif provider_id == "gemini":
            api_key = self._key_store.get_key("gemini")
            if not api_key:
                return None
            return GeminiAIProvider(api_key, self._settings.gemini_model)

        elif provider_id == "copilot":
            token = self._key_store.get_key("copilot_github_token") or ""
            return CopilotAIProvider(
                github_token=token,
                model=self._settings.copilot_model,
            )

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
        if self._key_store.has_key("gemini"):
            available.append({"id": "gemini", "name": "Google Gemini"})
        # Copilot is available if token is set or CLI is authenticated
        if self._key_store.has_key("copilot_github_token"):
            available.append({"id": "copilot", "name": "GitHub Copilot"})
        else:
            # Check if Copilot CLI is installed and might be logged in
            try:
                import shutil

                if shutil.which("copilot"):
                    available.append({"id": "copilot", "name": "GitHub Copilot"})
            except Exception:
                pass
        return available

    def translate(
        self,
        text: str,
        target_language: str = "",
        *,
        template_id: str = "",
        custom_vocabulary: list[str] | None = None,
    ) -> AIResponse:
        """Translate transcript text to the target language.

        Args:
            text: The transcript text to translate.
            target_language: Target language (e.g. 'Spanish', 'French').
                Falls back to settings default.
            template_id: Optional prompt template ID to use.
            custom_vocabulary: Optional vocabulary hints for specialised terms.

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

        # Resolve prompt template
        prompt_text: str = ""
        if template_id:
            from bits_whisperer.utils.constants import get_prompt_template_by_id

            tpl = get_prompt_template_by_id(template_id)
            if tpl:
                prompt_text = tpl.template.format(language=lang, text=text)
        if not prompt_text:
            # Use active template from settings, or fall back to default
            active = self._settings.active_translation_template
            if active and active != "translate_standard":
                from bits_whisperer.utils.constants import get_prompt_template_by_id

                tpl = get_prompt_template_by_id(active)
                if tpl:
                    prompt_text = tpl.template.format(language=lang, text=text)
            if not prompt_text:
                prompt_text = _TRANSLATE_PROMPT.format(target_language=lang, text=text)

        # Prepend custom vocabulary hints
        vocab = custom_vocabulary or self._settings.custom_vocabulary
        if vocab:
            vocab_str = ", ".join(vocab)
            prompt_text = (
                f"Important vocabulary/terms to preserve or use correctly: "
                f"{vocab_str}\n\n{prompt_text}"
            )

        return provider.generate(
            prompt_text,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )

    def translate_multi(
        self,
        text: str,
        target_languages: list[str] | None = None,
        *,
        template_id: str = "",
        custom_vocabulary: list[str] | None = None,
    ) -> dict[str, AIResponse]:
        """Translate transcript text to multiple target languages.

        Args:
            text: The transcript text to translate.
            target_languages: List of target languages. Falls back to
                settings.multi_target_languages.
            template_id: Optional prompt template ID to use.
            custom_vocabulary: Optional vocabulary hints.

        Returns:
            Dict mapping language name to AIResponse.
        """
        languages = target_languages or self._settings.multi_target_languages
        if not languages:
            return {}

        results: dict[str, AIResponse] = {}
        for lang in languages:
            results[lang] = self.translate(
                text,
                target_language=lang,
                template_id=template_id,
                custom_vocabulary=custom_vocabulary,
            )
        return results

    def summarize(
        self,
        text: str,
        style: str = "",
        *,
        template_id: str = "",
        custom_vocabulary: list[str] | None = None,
    ) -> AIResponse:
        """Summarize transcript text.

        Args:
            text: The transcript text to summarize.
            style: Summary style ('concise', 'detailed', 'bullet_points').
                Falls back to settings default.
            template_id: Optional prompt template ID to use.
            custom_vocabulary: Optional vocabulary hints.

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

        # Resolve prompt template
        prompt_text: str = ""
        if template_id:
            from bits_whisperer.utils.constants import get_prompt_template_by_id

            tpl = get_prompt_template_by_id(template_id)
            if tpl:
                prompt_text = tpl.template.format(text=text)
        if not prompt_text:
            active = self._settings.active_summarization_template
            if active and active != "summary_concise":
                from bits_whisperer.utils.constants import get_prompt_template_by_id

                tpl = get_prompt_template_by_id(active)
                if tpl:
                    prompt_text = tpl.template.format(text=text)
            if not prompt_text:
                chosen_style = style or self._settings.summarization_style
                template = _SUMMARIZE_STYLES.get(chosen_style, _SUMMARIZE_CONCISE)
                prompt_text = template.format(text=text)

        # Prepend custom vocabulary hints
        vocab = custom_vocabulary or self._settings.custom_vocabulary
        if vocab:
            vocab_str = ", ".join(vocab)
            prompt_text = (
                f"Important vocabulary/terms to use correctly: " f"{vocab_str}\n\n{prompt_text}"
            )

        return provider.generate(
            prompt_text,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )
