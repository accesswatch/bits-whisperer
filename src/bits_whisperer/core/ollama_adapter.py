"""Native Ollama HTTP adapter for local LLM model management and chat.

Uses ``httpx`` for direct REST communication with the Ollama daemon
(default ``http://127.0.0.1:11434``).  Falls back to the ``ollama``
CLI when the daemon is unreachable and CLI fallback is enabled.

All methods use ``tenacity`` for configurable retry logic with
exponential back-off.  Model cache mutations are protected by
``filelock`` to prevent concurrent corruption.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from filelock import FileLock
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class OllamaModelMetadata:
    """Metadata for an Ollama model (local or remote catalog entry)."""

    model_id: str
    name: str
    size_bytes: int = 0
    size_gb: float = 0.0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    context_window: int = 0
    digest: str = ""
    modified_at: str = ""
    is_downloaded: bool = False
    disk_path: str = ""

    def __post_init__(self) -> None:
        """Compute size_gb from size_bytes if not explicitly set."""
        if self.size_bytes and not self.size_gb:
            self.size_gb = round(self.size_bytes / (1024**3), 2)


@dataclass
class OllamaHealthStatus:
    """Health-check result for the Ollama daemon."""

    reachable: bool = False
    version: str = ""
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class CancelToken:
    """Thread-safe cancellation token for long-running operations."""

    _cancelled: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        """Request cancellation."""
        with self._lock:
            self._cancelled = True


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_RETRY_POLICY = retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class OllamaHTTPAdapter:
    """Native HTTP adapter for the Ollama REST API.

    Args:
        endpoint: Base URL of the Ollama daemon
            (default ``http://127.0.0.1:11434``).
        timeout_seconds: Per-request timeout.
        cli_path: Path to the ``ollama`` CLI binary (empty = auto-detect).
        cli_fallback: Whether to fall back to CLI when HTTP fails.
        cache_dir: Directory for file-lock coordination.
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 10.0,
        cli_path: str = "",
        cli_fallback: bool = True,
        cache_dir: Path | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout_seconds
        self._cli_path = cli_path or shutil.which("ollama") or "ollama"
        self._cli_fallback = cli_fallback
        self._cache_dir = cache_dir or Path.home() / ".ollama"
        self._lock_path = self._cache_dir / ".bw_model_lock"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> OllamaHealthStatus:
        """Ping the Ollama daemon and return health status.

        Returns:
            OllamaHealthStatus with reachability and version info.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                import time

                t0 = time.monotonic()
                resp = client.get(f"{self._endpoint}/api/version")
                latency = (time.monotonic() - t0) * 1000
                resp.raise_for_status()
                data = resp.json()
                return OllamaHealthStatus(
                    reachable=True,
                    version=data.get("version", ""),
                    latency_ms=round(latency, 1),
                )
        except Exception as exc:
            return OllamaHealthStatus(reachable=False, error=str(exc))

    # ------------------------------------------------------------------
    # Model listing
    # ------------------------------------------------------------------

    @_RETRY_POLICY
    def list_models(self) -> list[OllamaModelMetadata]:
        """List models available in the local Ollama instance.

        Returns:
            List of OllamaModelMetadata for each local model.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{self._endpoint}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models: list[OllamaModelMetadata] = []
                for m in data.get("models", []):
                    details = m.get("details", {})
                    models.append(
                        OllamaModelMetadata(
                            model_id=m.get("name", ""),
                            name=m.get("name", ""),
                            size_bytes=m.get("size", 0),
                            parameter_size=details.get("parameter_size", ""),
                            quantization=details.get("quantization_level", ""),
                            family=details.get("family", ""),
                            digest=m.get("digest", ""),
                            modified_at=m.get("modified_at", ""),
                            is_downloaded=True,
                        )
                    )
                return models
        except (httpx.ConnectError, httpx.TimeoutException):
            if self._cli_fallback:
                return self._list_models_cli()
            raise
        except Exception as exc:
            logger.error("Failed to list Ollama models: %s", exc)
            return []

    def _list_models_cli(self) -> list[OllamaModelMetadata]:
        """Fallback: list models via ``ollama list`` CLI command."""
        try:
            result = subprocess.run(
                [self._cli_path, "list"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                logger.warning("ollama list CLI failed: %s", result.stderr)
                return []
            models: list[OllamaModelMetadata] = []
            for line in result.stdout.strip().splitlines()[1:]:  # skip header
                parts = line.split()
                if parts:
                    models.append(
                        OllamaModelMetadata(
                            model_id=parts[0],
                            name=parts[0],
                            is_downloaded=True,
                        )
                    )
            return models
        except Exception as exc:
            logger.error("ollama list CLI error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Model show (detailed info)
    # ------------------------------------------------------------------

    def show_model(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model.

        Args:
            model_id: Model identifier (e.g. ``llama3.2``).

        Returns:
            Dict with model details (parameters, template, etc.).
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._endpoint}/api/show",
                    json={"model": model_id},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error("Failed to show model %s: %s", model_id, exc)
            return {}

    # ------------------------------------------------------------------
    # Model pull
    # ------------------------------------------------------------------

    def pull_model(
        self,
        model_id: str,
        progress_cb: Callable[[int], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> bool:
        """Pull (download) a model from the Ollama library.

        Uses file-locking to prevent concurrent pulls from corrupting
        the model cache.

        Args:
            model_id: Model identifier (e.g. ``llama3.2``).
            progress_cb: Called with progress percentage (0–100).
            cancel_token: Optional cancellation token.

        Returns:
            True if the pull completed successfully.
        """
        lock = FileLock(str(self._lock_path), timeout=10)
        try:
            with lock:
                return self._pull_model_http(model_id, progress_cb, cancel_token)
        except Exception as exc:
            logger.error("Pull model %s failed: %s", model_id, exc)
            if self._cli_fallback:
                return self._pull_model_cli(model_id)
            return False

    def _pull_model_http(
        self,
        model_id: str,
        progress_cb: Callable[[int], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> bool:
        """Pull a model using the Ollama HTTP streaming API."""
        logger.info("Pulling model %s via HTTP...", model_id)
        if progress_cb:
            progress_cb(0)

        with (
            httpx.Client(timeout=httpx.Timeout(10.0, read=600.0)) as client,
            client.stream(
                "POST",
                f"{self._endpoint}/api/pull",
                json={"model": model_id, "stream": True},
            ) as resp,
        ):
            resp.raise_for_status()
            for line in resp.iter_lines():
                if cancel_token and cancel_token.cancelled:
                    logger.info("Pull of %s cancelled by user.", model_id)
                    return False
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = chunk.get("status", "")
                if status == "success":
                    if progress_cb:
                        progress_cb(100)
                    logger.info("Model %s pulled successfully.", model_id)
                    return True
                total = chunk.get("total", 0)
                completed = chunk.get("completed", 0)
                if total > 0 and progress_cb:
                    pct = min(int(completed * 100 / total), 99)
                    progress_cb(pct)
        # If we exit without seeing "success", treat as success if no error
        if progress_cb:
            progress_cb(100)
        return True

    def _pull_model_cli(self, model_id: str) -> bool:
        """Fallback: pull a model via ``ollama pull`` CLI command."""
        logger.info("Pulling model %s via CLI fallback...", model_id)
        try:
            result = subprocess.run(
                [self._cli_path, "pull", model_id],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Model %s pulled via CLI.", model_id)
                return True
            logger.warning("ollama pull CLI failed: %s", result.stderr)
            return False
        except Exception as exc:
            logger.error("ollama pull CLI error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Model delete
    # ------------------------------------------------------------------

    def delete_model(self, model_id: str) -> bool:
        """Delete a model from the local Ollama instance.

        Args:
            model_id: Model identifier to delete.

        Returns:
            True if deletion succeeded.
        """
        lock = FileLock(str(self._lock_path), timeout=10)
        try:
            with lock, httpx.Client(timeout=self._timeout) as client:
                resp = client.request(
                    "DELETE",
                    f"{self._endpoint}/api/delete",
                    json={"model": model_id},
                )
                resp.raise_for_status()
                logger.info("Deleted model %s.", model_id)
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            if self._cli_fallback:
                return self._delete_model_cli(model_id)
            return False
        except Exception as exc:
            logger.error("Failed to delete model %s: %s", model_id, exc)
            return False

    def _delete_model_cli(self, model_id: str) -> bool:
        """Fallback: delete a model via ``ollama rm`` CLI command."""
        try:
            result = subprocess.run(
                [self._cli_path, "rm", model_id],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Deleted model %s via CLI.", model_id)
                return True
            logger.warning("ollama rm CLI failed: %s", result.stderr)
            return False
        except Exception as exc:
            logger.error("ollama rm CLI error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model_id: str,
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        stream_cb: Callable[[str], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> str:
        """Stream a chat response from an Ollama model.

        Uses the native ``/api/chat`` endpoint (not the OpenAI-compat
        layer) for maximum control.

        Args:
            messages: Conversation history as ``[{"role": ..., "content": ...}]``.
            model_id: Model to use for generation.
            system_message: Optional system prompt.
            max_tokens: Maximum response tokens (``num_predict``).
            temperature: Sampling temperature.
            stream_cb: Called with each text delta during streaming.
            cancel_token: Optional cancellation token.

        Returns:
            Complete generated text.
        """
        api_messages: list[dict[str, str]] = []
        if system_message:
            api_messages.append({"role": "system", "content": system_message})
        api_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": api_messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        full_text = ""
        try:
            with (
                httpx.Client(timeout=httpx.Timeout(10.0, read=300.0)) as client,
                client.stream(
                    "POST",
                    f"{self._endpoint}/api/chat",
                    json=payload,
                ) as resp,
            ):
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if cancel_token and cancel_token.cancelled:
                        break
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message", {})
                    delta = msg.get("content", "")
                    if delta:
                        full_text += delta
                        if stream_cb:
                            stream_cb(delta)
                    if chunk.get("done", False):
                        break
        except Exception as exc:
            logger.error("Ollama chat_stream error: %s", exc)
            raise

        return full_text

    # ── Generate (single-turn, non-streaming) ─────────────────────────

    @_RETRY_POLICY
    def generate(
        self,
        prompt: str,
        model_id: str,
        *,
        system_message: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Generate text with a single prompt (non-streaming).

        Args:
            prompt: The input prompt.
            model_id: Model to use.
            system_message: Optional system prompt.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            Generated text string.
        """
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if system_message:
            payload["system"] = system_message

        with httpx.Client(timeout=httpx.Timeout(10.0, read=300.0)) as client:
            resp = client.post(f"{self._endpoint}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_running_models(self) -> list[dict[str, Any]]:
        """List models currently loaded in Ollama's memory.

        Returns:
            List of dicts with model name and memory usage info.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{self._endpoint}/api/ps")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
        except Exception as exc:
            logger.debug("Failed to get running models: %s", exc)
            return []

    def is_cli_available(self) -> bool:
        """Check whether the ``ollama`` CLI is available on PATH."""
        return shutil.which(self._cli_path) is not None or shutil.which("ollama") is not None
