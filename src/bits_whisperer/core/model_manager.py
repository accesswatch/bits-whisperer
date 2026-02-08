"""Model manager — download, cache, and manage Whisper models locally."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from bits_whisperer.utils.constants import MODELS_DIR, WHISPER_MODELS, WhisperModelInfo
from bits_whisperer.utils.platform_utils import get_free_disk_space_mb, has_sufficient_disk_space

logger = logging.getLogger(__name__)

DownloadCallback = Callable[[str, float], None]  # (model_id, progress 0–100)


class ModelManager:
    """Manage local Whisper model downloads and cache.

    Models are stored in the app data directory under ``models/``.
    Each model gets its own subdirectory matching its repo_id basename.
    """

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        self._models_dir = models_dir
        self._models_dir.mkdir(parents=True, exist_ok=True)

    @property
    def models_dir(self) -> Path:
        """Return the directory where models are stored."""
        return self._models_dir

    # ------------------------------------------------------------------
    # Queries
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
        """Check whether a model is cached locally.

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
        """Return the local path for a downloaded model.

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
        """Return disk usage per downloaded model in bytes.

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
        """Return total disk space used by all models in megabytes."""
        total = sum(self.get_disk_usage().values())
        return round(total / (1024 * 1024), 1)

    def get_download_dir(self, model_id: str) -> Path:
        """Return the expected download directory for a model.

        This is useful for monitoring download progress by observing
        directory size growth.

        Args:
            model_id: Whisper model identifier.

        Returns:
            Path to the model's download directory (may not exist yet).
        """
        return self._model_dir(model_id)

    # ------------------------------------------------------------------
    # Download / Delete
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
                "faster-whisper is not installed. " "Install it with: pip install faster-whisper"
            ) from None
        except Exception as exc:
            raise RuntimeError(f"Failed to download model '{model_id}': {exc}") from exc

    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model from disk.

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
    # Internal
    # ------------------------------------------------------------------

    def _model_dir(self, model_id: str) -> Path:
        """Compute the local directory for a model.

        Uses HuggingFace Hub cache naming convention (``models--org--repo``).

        Args:
            model_id: Whisper model identifier.

        Returns:
            Path to model subdirectory.
        """
        info = self._get_model_info(model_id)
        if info.repo_id:
            dirname = f"models--{info.repo_id.replace('/', '--')}"
        else:
            dirname = model_id
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
        """Look up model metadata.

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
