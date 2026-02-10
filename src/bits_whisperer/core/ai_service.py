"""AI service for transcript translation and summarization.

Supports multiple LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude Sonnet, Claude Haiku)
- Azure OpenAI (configurable deployment)
- Google Gemini (Gemini 2.0 Flash, Gemini 2.5 Pro)
- GitHub Copilot (via Copilot SDK — GPT-4o, Claude, etc.)
- Ollama (local models from Hugging Face / Ollama library — Llama, Mistral, Gemma, etc.)

Each provider is accessed through a unified interface that handles
prompt construction, API calls, and response parsing.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with optional streaming.

        Default implementation flattens the conversation into a single
        prompt and delegates to :meth:`generate`.  Subclasses should
        override this to use native multi-turn + streaming APIs.

        Args:
            messages: Conversation history as ``[{"role": ..., "content": ...}]``.
            system_message: Optional system prompt (e.g. transcript context).
            max_tokens: Maximum response tokens.
            temperature: Sampling temperature.
            on_delta: Called with each text chunk during streaming.

        Returns:
            AIResponse with the complete generated text.
        """
        parts: list[str] = []
        if system_message:
            parts.append(f"System: {system_message}")
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            parts.append(f"{role}: {msg.get('content', '')}")
        prompt = "\n\n".join(parts)
        response = self.generate(prompt, max_tokens=max_tokens, temperature=temperature)
        if on_delta and response.text:
            on_delta(response.text)
        return response


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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with native OpenAI streaming."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            api_messages: list[dict[str, str]] = []
            if system_message:
                api_messages.append({"role": "system", "content": system_message})
            else:
                api_messages.append(
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that processes transcripts.",
                    }
                )
            api_messages.extend(messages)

            if on_delta:
                stream = client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,  # type: ignore[arg-type]
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                full_text = ""
                for chunk in stream:  # type: ignore[union-attr]
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        full_text += delta
                        on_delta(delta)
                return AIResponse(text=full_text, provider="openai", model=self._model)
            else:
                return self.generate(
                    messages[-1]["content"] if messages else "",
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        except ImportError:
            return AIResponse(
                text="",
                provider="openai",
                model=self._model,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("OpenAI chat_stream failed")
            return AIResponse(text="", provider="openai", model=self._model, error=str(exc))


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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with native Anthropic streaming."""
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=self._api_key)
            api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": api_messages,
            }
            if system_message:
                kwargs["system"] = system_message

            if on_delta:
                full_text = ""
                with client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        full_text += text
                        on_delta(text)
                return AIResponse(text=full_text, provider="anthropic", model=self._model)
            else:
                response = client.messages.create(**kwargs)
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
            logger.exception("Anthropic chat_stream failed")
            return AIResponse(text="", provider="anthropic", model=self._model, error=str(exc))


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
                messages=[  # type: ignore[arg-type]
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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with native Azure OpenAI streaming."""
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=self._api_key,
                api_version="2024-06-01",
                azure_endpoint=self._endpoint,
            )
            api_messages: list[dict[str, str]] = []
            if system_message:
                api_messages.append({"role": "system", "content": system_message})
            else:
                api_messages.append(
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that processes transcripts.",
                    }
                )
            api_messages.extend(messages)

            if on_delta:
                stream = client.chat.completions.create(
                    model=self._deployment,
                    messages=api_messages,  # type: ignore[arg-type]
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                full_text = ""
                for chunk in stream:  # type: ignore[union-attr]
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        full_text += delta
                        on_delta(delta)
                return AIResponse(
                    text=full_text,
                    provider="azure_openai",
                    model=self._deployment,
                )
            else:
                return self.generate(
                    messages[-1]["content"] if messages else "",
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        except ImportError:
            return AIResponse(
                text="",
                provider="azure_openai",
                model=self._deployment,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("Azure OpenAI chat_stream failed")
            return AIResponse(
                text="",
                provider="azure_openai",
                model=self._deployment,
                error=str(exc),
            )


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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with native Gemini streaming."""
        try:
            from google import genai

            client = genai.Client(api_key=self._api_key)
            # Build Gemini-format contents
            contents: list[dict[str, Any]] = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            config: dict[str, Any] = {
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
            if system_message:
                config["system_instruction"] = system_message
            else:
                config["system_instruction"] = (
                    "You are a helpful assistant that processes transcripts."
                )

            if on_delta:
                full_text = ""
                for chunk in client.models.generate_content_stream(
                    model=self._model,
                    contents=contents,  # type: ignore[arg-type]
                    config=config,  # type: ignore[arg-type]
                ):
                    text = chunk.text or ""
                    if text:
                        full_text += text
                        on_delta(text)
                return AIResponse(text=full_text, provider="gemini", model=self._model)
            else:
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,  # type: ignore[arg-type]
                    config=config,  # type: ignore[arg-type]
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
            logger.exception("Gemini chat_stream failed")
            return AIResponse(text="", provider="gemini", model=self._model, error=str(exc))


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

            from copilot import CopilotClient

            logger.info(
                "Copilot generate: model=%s, prompt_len=%d",
                self._model,
                len(prompt),
            )

            async def _run() -> AIResponse:
                client_kwargs: dict[str, Any] = {"auto_start": True}
                if self._github_token:
                    client_kwargs["github_token"] = self._github_token
                    logger.debug("Copilot generate: using provided GitHub token")
                elif not self._github_token:
                    client_kwargs["use_logged_in_user"] = True
                    logger.debug("Copilot generate: using logged-in CLI user")

                log_kwargs = {k: ("***" if "token" in k else v) for k, v in client_kwargs.items()}
                logger.debug("CopilotClient kwargs: %s", log_kwargs)

                client = CopilotClient(client_kwargs)  # type: ignore[arg-type]
                logger.debug("Starting CopilotClient for generation...")
                await client.start()
                logger.debug("CopilotClient started")
                try:
                    session = await client.create_session(
                        {
                            "model": self._model,
                            "system_message": (  # type: ignore[typeddict-item]
                                "You are a helpful assistant that processes transcripts."
                            ),
                        }
                    )
                    logger.debug("Session created, sending prompt...")
                    response = await session.send_and_wait({"prompt": prompt})
                    result_text = ""
                    if response and hasattr(response, "data"):
                        result_text = getattr(response.data, "content", "") or ""
                    logger.info(
                        "Copilot generation complete: response_len=%d",
                        len(result_text),
                    )
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
            logger.error("Copilot generate failed: github-copilot-sdk not installed")
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
            logger.exception("Copilot generation failed: %s", exc)
            return AIResponse(
                text="",
                provider="copilot",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Copilot connection by starting a test session."""
        logger.info(
            "Validating Copilot connection: has_token=%s, cli_path=%s",
            bool(api_key),
            self._cli_path or "(auto-detect)",
        )
        try:
            import asyncio

            from copilot import CopilotClient

            async def _test() -> bool:
                client_kwargs: dict[str, Any] = {"auto_start": True}
                if api_key:
                    client_kwargs["github_token"] = api_key
                    logger.debug("Validation: using provided token")
                else:
                    client_kwargs["use_logged_in_user"] = True
                    logger.debug("Validation: using logged-in CLI user")
                if self._cli_path:
                    client_kwargs["cli_path"] = self._cli_path

                logger.debug("Creating CopilotClient for validation...")
                client = CopilotClient(client_kwargs)  # type: ignore[arg-type]
                logger.debug("Starting CopilotClient...")
                await client.start()
                logger.debug("CopilotClient started, creating test session...")
                try:
                    session = await client.create_session({"model": "gpt-4o"})
                    logger.debug("Test session created successfully")
                    await session.destroy()
                    logger.info("Copilot validation PASSED")
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

        except ImportError as exc:
            logger.error("Copilot validation failed: SDK not importable: %s", exc)
            return False
        except Exception as exc:
            logger.error(
                "Copilot validation FAILED: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return False


# ---------------------------------------------------------------------------
# Ollama provider (local models via OpenAI-compatible API)
# ---------------------------------------------------------------------------


class OllamaAIProvider(AIProvider):
    """AI provider using Ollama for local LLM inference.

    Ollama serves models locally and exposes an OpenAI-compatible API
    at ``/v1/chat/completions``. Models can be pulled from the Ollama
    library or from Hugging Face GGUF repositories.

    No API key is required — models run entirely on-device.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        endpoint: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._endpoint = endpoint.rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AIResponse:
        """Generate text using Ollama's OpenAI-compatible chat API."""
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=f"{self._endpoint}/v1",
                api_key="ollama",  # Ollama ignores the key but openai lib requires it
            )
            response = client.chat.completions.create(
                model=self._model,
                messages=[  # type: ignore[arg-type]
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
                provider="ollama",
                model=self._model,
                tokens_used=tokens,
            )
        except ImportError:
            return AIResponse(
                text="",
                provider="ollama",
                model=self._model,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("Ollama generation failed")
            return AIResponse(
                text="",
                provider="ollama",
                model=self._model,
                error=str(exc),
            )

    def validate_key(self, api_key: str) -> bool:
        """Validate Ollama connectivity by listing local models."""
        try:
            import urllib.error
            import urllib.request

            url = f"{self._endpoint}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return bool(resp.status == 200)
        except Exception:
            return False

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIResponse:
        """Multi-turn chat with native Ollama streaming via OpenAI-compat API."""
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=f"{self._endpoint}/v1",
                api_key="ollama",
            )
            api_messages: list[dict[str, str]] = []
            if system_message:
                api_messages.append({"role": "system", "content": system_message})
            else:
                api_messages.append(
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that processes transcripts.",
                    }
                )
            api_messages.extend(messages)

            if on_delta:
                stream = client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,  # type: ignore[arg-type]
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                full_text = ""
                for chunk in stream:  # type: ignore[union-attr]
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        full_text += delta
                        on_delta(delta)
                return AIResponse(text=full_text, provider="ollama", model=self._model)
            else:
                return self.generate(
                    messages[-1]["content"] if messages else "",
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        except ImportError:
            return AIResponse(
                text="",
                provider="ollama",
                model=self._model,
                error="OpenAI SDK not installed. Install with: pip install openai",
            )
        except Exception as exc:
            logger.exception("Ollama chat_stream failed")
            return AIResponse(text="", provider="ollama", model=self._model, error=str(exc))

    def list_models(self) -> list[str]:
        """List models available in the local Ollama instance.

        Returns:
            List of model name strings, or empty list on error.
        """
        try:
            import json
            import urllib.request

            url = f"{self._endpoint}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def pull_model(self, model_name: str) -> bool:
        """Pull a model into Ollama (from Ollama library or Hugging Face).

        For Hugging Face models, use the format ``hf.co/user/repo``.

        Args:
            model_name: Model identifier to pull.

        Returns:
            True if the pull request was accepted.
        """
        try:
            import json
            import urllib.request

            url = f"{self._endpoint}/api/pull"
            payload = json.dumps({"model": model_name, "stream": False}).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                return bool(resp.status == 200)
        except Exception as exc:
            logger.warning("Ollama model pull failed for %s: %s", model_name, exc)
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

        elif provider_id == "ollama":
            model = self._settings.ollama_custom_model or self._settings.ollama_model
            endpoint = self._settings.ollama_endpoint or "http://localhost:11434"
            return OllamaAIProvider(model=model, endpoint=endpoint)

        return None

    def is_configured(self) -> bool:
        """Check whether the AI service has a valid provider configured.

        Returns:
            True if a provider can be created.
        """
        return self._get_provider() is not None

    def get_provider(self) -> AIProvider | None:
        """Return the configured provider instance, if available."""
        return self._get_provider()

    def _get_model_id(self) -> str:
        """Return the model ID for the currently selected provider.

        Returns:
            Model identifier string.
        """
        pid = self._settings.selected_provider
        model_map = {
            "openai": lambda: self._settings.openai_model,
            "anthropic": lambda: self._settings.anthropic_model,
            "azure_openai": lambda: self._settings.azure_openai_deployment or "",
            "gemini": lambda: self._settings.gemini_model,
            "copilot": lambda: self._settings.copilot_model,
            "ollama": lambda: (self._settings.ollama_custom_model or self._settings.ollama_model),
        }
        getter = model_map.get(pid)
        return getter() if getter else ""

    def get_model_id(self) -> str:
        """Return the model ID for the currently selected provider."""
        return self._get_model_id()

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

        # Ollama is available if the local server is reachable
        try:
            endpoint = self._settings.ollama_endpoint or "http://localhost:11434"
            provider = OllamaAIProvider(endpoint=endpoint)
            if provider.validate_key(""):
                available.append({"id": "ollama", "name": "Ollama (Local)"})
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

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        transcript_context: str = "",
        on_delta: Callable[[str], None] | None = None,
        on_complete: Callable[[AIResponse], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Multi-turn chat with streaming, running on a background thread.

        Sends the full conversation history to the configured provider,
        injects transcript context as a system message, and delivers
        streaming text via callbacks.

        Args:
            messages: Conversation history ``[{"role": ..., "content": ...}]``.
            transcript_context: Full transcript text for context injection.
            on_delta: Called with each streamed text chunk.
            on_complete: Called with the final ``AIResponse`` on success.
            on_error: Called with an error string on failure.
        """

        def _run() -> None:
            try:
                provider = self._get_provider()
                if not provider:
                    if on_error:
                        on_error(
                            "No AI provider configured. "
                            "Go to Tools \u2192 AI Provider Settings to add an API key."
                        )
                    return

                # Build system message with transcript context
                system_msg = (
                    "You are a helpful, knowledgeable assistant for analyzing "
                    "audio transcripts. Answer questions clearly and concisely. "
                    "When referencing the transcript, cite relevant quotes."
                )

                # Use context window manager for model-aware fitting
                from bits_whisperer.core.context_manager import create_context_manager

                pid = self._settings.selected_provider
                model = self._get_model_id()
                ctx_mgr = create_context_manager(self._settings)
                prepared = ctx_mgr.prepare_chat_context(
                    model=model,
                    provider=pid,
                    system_prompt=system_msg,
                    transcript=transcript_context,
                    conversation_history=messages,
                    response_reserve=self._settings.max_tokens,
                )

                if prepared.fitted_transcript:
                    system_msg += (
                        "\n\n--- TRANSCRIPT CONTEXT ---\n"
                        + prepared.fitted_transcript
                        + "\n--- END TRANSCRIPT ---"
                    )

                chat_messages = prepared.trimmed_history or messages

                response = provider.chat_stream(
                    chat_messages,
                    system_message=system_msg,
                    max_tokens=self._settings.max_tokens,
                    temperature=self._settings.temperature,
                    on_delta=on_delta,
                )

                if response.error:
                    if on_error:
                        on_error(response.error)
                elif on_complete:
                    on_complete(response)
            except Exception as exc:
                logger.exception("AIService.chat() failed")
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=_run, daemon=True, name="ai-chat").start()

    def get_provider_display_name(self) -> str:
        """Return a human-readable name for the configured provider.

        Returns:
            Display string like ``"OpenAI (gpt-4o-mini)"``.
        """
        pid = self._settings.selected_provider
        model = ""
        if pid == "openai":
            model = self._settings.openai_model
        elif pid == "anthropic":
            model = self._settings.anthropic_model
        elif pid == "azure_openai":
            model = self._settings.azure_openai_deployment or "Azure"
        elif pid == "gemini":
            model = self._settings.gemini_model
        elif pid == "copilot":
            model = self._settings.copilot_model
        elif pid == "ollama":
            model = self._settings.ollama_custom_model or self._settings.ollama_model

        names = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "azure_openai": "Azure OpenAI",
            "gemini": "Gemini",
            "copilot": "Copilot",
            "ollama": "Ollama",
        }
        name = names.get(pid, pid)
        return f"{name} ({model})" if model else name
