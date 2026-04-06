"""Model manager — download, cache, and manage Whisper + Ollama models locally.

Supports multiple model providers:
- **Whisper**: faster-whisper models from HuggingFace Hub.
- **Ollama**: local LLM models pulled via Ollama daemon/CLI.
- **Vosk**: Kaldi-based offline speech models.
- **Parakeet**: NVIDIA NeMo ASR models.

The manager provides a unified interface for listing, downloading,
deleting, and querying models across all providers, plus hardware-
aware ranking via :class:`DeviceProbe`.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from bits_whisperer.utils.constants import MODELS_DIR, WHISPER_MODELS, WhisperModelInfo
from bits_whisperer.utils.platform_utils import get_free_disk_space_mb, has_sufficient_disk_space

if TYPE_CHECKING:
    from bits_whisperer.core.ollama_adapter import (
        CancelToken,
        OllamaHTTPAdapter,
        OllamaModelMetadata,
    )

logger = logging.getLogger(__name__)

DownloadCallback = Callable[[str, float], None]  # (model_id, progress 0–100)


# ---------------------------------------------------------------------------
# Unified model info wrapper
# ---------------------------------------------------------------------------


@dataclass
class UnifiedModelInfo:
    """Provider-agnostic model information for the Model Manager UI."""

    provider: str  # "whisper", "ollama", "vosk", "parakeet"
    model_id: str
    name: str
    description: str = ""
    status: str = "available"  # "available", "downloaded", "downloading", "error"
    size_gb: float = 0.0
    context_window: int = 0
    parameter_size: str = ""
    rank_score: float = 0.0
    disk_path: str = ""
    version: str = ""
    last_updated: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ProviderSummary:
    """Summary of a model provider for the treeview root nodes."""

    provider_id: str
    name: str
    description: str = ""
    downloaded_count: int = 0
    available_count: int = 0


class ModelManager:
    """Manage local model downloads and cache across all providers.

    Supports Whisper models (downloaded via faster-whisper from
    HuggingFace Hub) and Ollama models (pulled via the native HTTP
    adapter or CLI).  Provides a unified interface for listing,
    downloading/pulling, deleting, and querying models.

    Models are stored in the app data directory under ``models/``
    (Whisper) or managed by the Ollama daemon (Ollama).
    """

    def __init__(
        self,
        models_dir: Path = MODELS_DIR,
        ollama_adapter: OllamaHTTPAdapter | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._ollama: OllamaHTTPAdapter | None = ollama_adapter

    @property
    def models_dir(self) -> Path:
        """Return the directory where models are stored."""
        return self._models_dir

    def set_ollama_adapter(self, adapter: OllamaHTTPAdapter | None) -> None:
        """Attach or replace the Ollama adapter at runtime.

        Args:
            adapter: An ``OllamaHTTPAdapter`` instance, or ``None`` to detach.
        """
        self._ollama = adapter

    # ------------------------------------------------------------------
    # Provider summaries (for treeview root nodes)
    # ------------------------------------------------------------------

    def get_provider_summaries(self) -> list[ProviderSummary]:
        """Return a summary for each model provider.

        Returns:
            List of ProviderSummary objects in display order.
        """
        summaries: list[ProviderSummary] = []

        # Whisper
        whisper_dl = sum(1 for m in WHISPER_MODELS if self.is_downloaded(m.id))
        summaries.append(
            ProviderSummary(
                provider_id="whisper",
                name="Whisper (faster-whisper)",
                description="On-device transcription models from HuggingFace",
                downloaded_count=whisper_dl,
                available_count=len(WHISPER_MODELS),
            )
        )

        # Ollama
        try:
            ollama_models = self.list_ollama_models()
            summaries.append(
                ProviderSummary(
                    provider_id="ollama",
                    name="Ollama (Local LLM)",
                    description="AI chat models running locally via Ollama",
                    downloaded_count=len(ollama_models),
                    available_count=len(ollama_models),
                )
            )
        except Exception:
            summaries.append(
                ProviderSummary(
                    provider_id="ollama",
                    name="Ollama (Local LLM)",
                    description="Ollama daemon not reachable",
                    downloaded_count=0,
                    available_count=0,
                )
            )

        return summaries

    # ------------------------------------------------------------------
    # Unified model listing
    # ------------------------------------------------------------------

    def get_unified_models(self, provider: str = "") -> list[UnifiedModelInfo]:
        """Return models as ``UnifiedModelInfo`` for the treeview.

        Args:
            provider: Filter by provider ID (empty = all providers).

        Returns:
            List of UnifiedModelInfo objects.
        """
        result: list[UnifiedModelInfo] = []

        if not provider or provider == "whisper":
            for m in WHISPER_MODELS:
                downloaded = self.is_downloaded(m.id)
                result.append(
                    UnifiedModelInfo(
                        provider="whisper",
                        model_id=m.id,
                        name=m.name,
                        description=m.description,
                        status="downloaded" if downloaded else "available",
                        size_gb=round(m.disk_size_mb / 1024, 2),
                        parameter_size=f"{m.parameters_m}M",
                        extra={
                            "speed_stars": str(m.speed_stars),
                            "accuracy_stars": str(m.accuracy_stars),
                            "min_ram_gb": str(m.min_ram_gb),
                            "min_vram_gb": str(m.min_vram_gb),
                            "repo_id": m.repo_id,
                        },
                    )
                )

        if not provider or provider == "ollama":
            for m in self.list_ollama_models():
                result.append(
                    UnifiedModelInfo(
                        provider="ollama",
                        model_id=m.model_id,
                        name=m.name,
                        description=f"{m.family} {m.parameter_size}".strip(),
                        status="downloaded",
                        size_gb=m.size_gb,
                        parameter_size=m.parameter_size,
                        context_window=m.context_window,
                        version=m.digest[:12] if m.digest else "",
                        last_updated=m.modified_at,
                        extra={
                            "quantization": m.quantization,
                            "family": m.family,
                        },
                    )
                )

        return result

    # ------------------------------------------------------------------
    # Whisper queries
    # ------------------------------------------------------------------

    def list_available_models(self) -> list[WhisperModelInfo]:
        """Return the full list of known Whisper model variants."""
        return list(WHISPER_MODELS)

    def list_downloaded_models(self) -> list[WhisperModelInfo]:
        """Return models that are already downloaded locally.

        Returns:
            List of WhisperModelInfo for models present on disk.
        """
        downloaded = []
        for model in WHISPER_MODELS:
            if self.is_downloaded(model.id):
                downloaded.append(model)
        return downloaded

    def is_downloaded(self, model_id: str) -> bool:
        """Check whether a Whisper model is cached locally.

        Args:
            model_id: Whisper model identifier (e.g. 'small', 'large-v3').

        Returns:
            True if the model directory exists and appears valid.
        """
        model_dir = self._model_dir(model_id)
        if not model_dir.exists():
            return False
        # HuggingFace Hub cache stores files under snapshots/<hash>/
        snapshot = self._get_snapshot_dir(model_dir)
        if snapshot:
            return any(snapshot.glob("config.json")) or any(snapshot.glob("*.bin"))
        # Direct structure fallback (manual placement)
        return any(model_dir.glob("*.bin")) or any(model_dir.glob("config.json"))

    def get_model_path(self, model_id: str) -> Path | None:
        """Return the local path for a downloaded Whisper model.

        Args:
            model_id: Whisper model identifier.

        Returns:
            Path to the model snapshot directory, or None if not downloaded.
        """
        if not self.is_downloaded(model_id):
            return None
        model_dir = self._model_dir(model_id)
        snapshot = self._get_snapshot_dir(model_dir)
        return snapshot if snapshot else model_dir

    def get_disk_usage(self) -> dict[str, int]:
        """Return disk usage per downloaded Whisper model in bytes.

        Returns:
            Dict mapping model_id to size in bytes.
        """
        usage: dict[str, int] = {}
        for model in WHISPER_MODELS:
            model_dir = self._model_dir(model.id)
            if model_dir.exists():
                total = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
                usage[model.id] = total
        return usage

    def get_total_disk_usage_mb(self) -> float:
        """Return total disk space used by all Whisper models in megabytes."""
        total = sum(self.get_disk_usage().values())
        return round(total / (1024 * 1024), 1)

    def get_download_dir(self, model_id: str) -> Path:
        """Return the expected download directory for a Whisper model.

        This is useful for monitoring download progress by observing
        directory size growth.

        Args:
            model_id: Whisper model identifier.

        Returns:
            Path to the model's download directory (may not exist yet).
        """
        return self._model_dir(model_id)

    # ------------------------------------------------------------------
    # Ollama queries
    # ------------------------------------------------------------------

    def list_ollama_models(self) -> list[OllamaModelMetadata]:
        """List models available in the local Ollama instance.

        Returns:
            List of ``OllamaModelMetadata`` (empty if adapter is not set
            or Ollama is unreachable).
        """
        if not self._ollama:
            return []
        try:
            return self._ollama.list_models()
        except Exception:
            logger.debug("Failed to list Ollama models", exc_info=True)
            return []

    def is_ollama_model_downloaded(self, model_id: str) -> bool:
        """Check whether an Ollama model is pulled locally.

        Args:
            model_id: Model identifier (e.g. ``llama3.2``).

        Returns:
            True if the model is listed by the Ollama daemon.
        """
        return any(m.model_id == model_id for m in self.list_ollama_models())

    def get_ollama_model_names(self) -> list[str]:
        """Return just the model name strings for Ollama.

        Convenient for populating dropdown choices.

        Returns:
            List of model ID strings.
        """
        return [m.model_id for m in self.list_ollama_models()]

    # ------------------------------------------------------------------
    # Whisper download / delete
    # ------------------------------------------------------------------

    def download_model(
        self,
        model_id: str,
        progress_callback: DownloadCallback | None = None,
    ) -> Path:
        """Download a Whisper model from HuggingFace via faster-whisper.

        The faster-whisper library handles the actual download and caching
        via CTranslate2-converted models.

        Args:
            model_id: Whisper model identifier.
            progress_callback: Optional callback (model_id, progress %).

        Returns:
            Path to the downloaded model directory.

        Raises:
            ValueError: If model_id is unknown.
            RuntimeError: If download fails.
        """
        model_info = self._get_model_info(model_id)
        model_dir = self._model_dir(model_id)

        logger.info("Downloading model '%s' (%s)...", model_id, model_info.repo_id)

        # Pre-flight disk space check (require 10% headroom)
        required_mb = model_info.disk_size_mb * 1.1
        if not has_sufficient_disk_space(self._models_dir, required_mb):
            free = get_free_disk_space_mb(self._models_dir)
            raise RuntimeError(
                f"Not enough disk space to download {model_info.name}. "
                f"Need {model_info.disk_size_mb} MB, only {free:.0f} MB free."
            )

        if progress_callback:
            progress_callback(model_id, 0.0)

        try:
            # faster-whisper downloads and converts the model automatically
            # when you instantiate WhisperModel with the model size.
            # We trigger this by importing and creating a model instance.
            from faster_whisper import WhisperModel

            # This downloads the model if not cached
            _model = WhisperModel(
                model_info.repo_id or model_id,
                device="cpu",
                compute_type="int8",
                download_root=str(self._models_dir),
            )
            del _model  # Release memory — we just wanted the download

            if progress_callback:
                progress_callback(model_id, 100.0)

            logger.info("Model '%s' downloaded successfully.", model_id)
            return model_dir

        except ImportError:
            from bits_whisperer.core.sdk_installer import is_frozen

            if is_frozen():
                raise RuntimeError(
                    "The faster-whisper engine is not installed.\n\n"
                    "Go to Settings, then Providers, then Local Whisper and click "
                    "'Install SDK' to download it automatically."
                ) from None
            raise RuntimeError(
                "faster-whisper is not installed. Install it with: pip install faster-whisper"
            ) from None
        except Exception as exc:
            raise RuntimeError(f"Failed to download model '{model_id}': {exc}") from exc

    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded Whisper model from disk.

        Args:
            model_id: Whisper model identifier.

        Returns:
            True if deleted, False if not found.
        """
        model_dir = self._model_dir(model_id)
        if model_dir.exists():
            shutil.rmtree(model_dir, ignore_errors=True)
            logger.info("Deleted model '%s'.", model_id)
            return True
        return False

    # ------------------------------------------------------------------
    # Ollama pull / delete
    # ------------------------------------------------------------------

    def pull_ollama_model(
        self,
        model_id: str,
        progress_callback: DownloadCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> bool:
        """Pull (download) an Ollama model.

        Args:
            model_id: Model identifier (e.g. ``llama3.2``).
            progress_callback: Optional ``(model_id, progress %)`` callback.
            cancel_token: Optional cancellation token.

        Returns:
            True if the pull completed successfully.

        Raises:
            RuntimeError: If the Ollama adapter is not configured.
        """
        if not self._ollama:
            raise RuntimeError(
                "Ollama adapter not configured. Enable Ollama in AI Provider Settings."
            )

        def _pct_cb(pct: int) -> None:
            if progress_callback:
                progress_callback(model_id, float(pct))

        return self._ollama.pull_model(model_id, progress_cb=_pct_cb, cancel_token=cancel_token)

    def delete_ollama_model(self, model_id: str) -> bool:
        """Delete an Ollama model from the local daemon.

        Args:
            model_id: Model identifier to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        if not self._ollama:
            return False
        return self._ollama.delete_model(model_id)

    # ── Internal (Whisper) ──────────────────────────────────────────

    def _model_dir(self, model_id: str) -> Path:
        """Compute the local directory for a Whisper model.

        Uses HuggingFace Hub cache naming convention (``models--org--repo``).

        Args:
            model_id: Whisper model identifier.

        Returns:
            Path to model subdirectory.
        """
        info = self._get_model_info(model_id)
        dirname = f"models--{info.repo_id.replace('/', '--')}" if info.repo_id else model_id
        return self._models_dir / dirname

    def _get_snapshot_dir(self, model_dir: Path) -> Path | None:
        """Find the latest snapshot directory in a HuggingFace Hub cache.

        Args:
            model_dir: The top-level model cache directory.

        Returns:
            Path to the snapshot directory, or None if not found.
        """
        snapshots_dir = model_dir / "snapshots"
        if not snapshots_dir.exists():
            return None
        # Return the first (usually only) snapshot directory
        for child in sorted(snapshots_dir.iterdir(), reverse=True):
            if child.is_dir():
                return child
        return None

    def _get_model_info(self, model_id: str) -> WhisperModelInfo:
        """Look up Whisper model metadata.

        Args:
            model_id: Whisper model identifier.

        Returns:
            WhisperModelInfo instance.

        Raises:
            ValueError: If model_id is not recognized.
        """
        for m in WHISPER_MODELS:
            if m.id == model_id:
                return m
        raise ValueError(f"Unknown model: {model_id}")
