"""Hardware capability detection for on-device model eligibility."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass, field
from typing import Final

from bits_whisperer.utils.constants import WHISPER_MODELS, WhisperModelInfo

logger = logging.getLogger(__name__)

# Threshold for "warn but allow" CPU-only inference on larger models
_CPU_WARN_THRESHOLD_GB: Final[int] = 8


@dataclass
class DeviceProfile:
    """Snapshot of the host machine's hardware capabilities."""

    cpu_name: str = ""
    cpu_cores_physical: int = 0
    cpu_cores_logical: int = 0
    has_avx: bool = False
    has_avx2: bool = False
    ram_gb: float = 0.0
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    has_cuda: bool = False
    os_name: str = ""
    os_version: str = ""
    eligible_models: list[str] = field(default_factory=list)
    warned_models: list[str] = field(default_factory=list)
    ineligible_models: list[str] = field(default_factory=list)


class DeviceProbe:
    """Detect hardware capabilities and determine model eligibility."""

    def __init__(self) -> None:
        self._profile: DeviceProfile | None = None

    def probe(self) -> DeviceProfile:
        """Run hardware detection and return a DeviceProfile.

        Returns:
            A populated DeviceProfile with eligible model lists.
        """
        profile = DeviceProfile()

        # OS
        profile.os_name = platform.system()
        profile.os_version = platform.version()

        # CPU + RAM — lazy-import psutil to keep startup lightweight
        import psutil

        profile.cpu_cores_physical = psutil.cpu_count(logical=False) or 1
        profile.cpu_cores_logical = psutil.cpu_count(logical=True) or 1
        profile.cpu_name = platform.processor() or "Unknown CPU"

        # RAM
        mem = psutil.virtual_memory()
        profile.ram_gb = round(mem.total / (1024**3), 1)

        # AVX detection (Windows)
        profile.has_avx = self._detect_avx()
        profile.has_avx2 = self._detect_avx2()

        # GPU / CUDA detection
        profile.has_cuda, profile.gpu_name, profile.gpu_vram_gb = self._detect_cuda()

        # Determine model eligibility
        self._evaluate_models(profile)

        self._profile = profile
        logger.info("Device probe complete: %s", profile)
        return profile

    @property
    def profile(self) -> DeviceProfile:
        """Return cached profile or run probe."""
        if self._profile is None:
            return self.probe()
        return self._profile

    def is_model_eligible(self, model_id: str) -> bool:
        """Check if a model can run on this hardware.

        Args:
            model_id: Whisper model identifier.

        Returns:
            True if the model can run (possibly with a warning).
        """
        p = self.profile
        return model_id in p.eligible_models or model_id in p.warned_models

    def get_eligibility_reason(self, model: WhisperModelInfo) -> str:
        """Return a plain-English explanation of why a model is or isn't eligible.

        Args:
            model: The WhisperModelInfo to evaluate.

        Returns:
            Human-readable eligibility string.
        """
        p = self.profile
        if model.id in p.eligible_models:
            return "Your computer can run this model."
        if model.id in p.warned_models:
            return (
                "Your computer can run this model, but it may be slow. "
                "Consider using a cloud service for faster results."
            )
        reasons = []
        if model.min_ram_gb > p.ram_gb:
            reasons.append(f"Needs {model.min_ram_gb} GB RAM (you have {p.ram_gb} GB)")
        if model.min_vram_gb > 0 and model.min_vram_gb > p.gpu_vram_gb:
            if not p.has_cuda:
                reasons.append(f"Needs a GPU with {model.min_vram_gb} GB video memory")
            else:
                reasons.append(
                    f"Needs {model.min_vram_gb} GB video memory "
                    f"(your GPU has {p.gpu_vram_gb} GB)"
                )
        if model.min_cpu_cores > p.cpu_cores_physical:
            reasons.append(
                f"Needs {model.min_cpu_cores} CPU cores " f"(you have {p.cpu_cores_physical})"
            )
        if not reasons:
            reasons.append("This model is too demanding for your hardware.")
        return (
            "This model can't run on your computer. "
            + " ".join(reasons)
            + " Try a smaller model or use a cloud service."
        )

    def get_recommended_model(self) -> str:
        """Pick the best model that runs well on this hardware.

        Returns:
            Model ID of the recommended model.
        """
        p = self.profile
        # Prefer the best eligible (non-warned) model
        best: str = "tiny"
        for m in WHISPER_MODELS:
            if m.id in p.eligible_models:
                best = m.id
        return best

    # -----------------------------------------------------------------------
    # Internal detection methods
    # -----------------------------------------------------------------------

    def _detect_avx(self) -> bool:
        """Detect AVX support (best-effort, cross-platform)."""
        from bits_whisperer.utils.platform_utils import detect_cpu_features

        return detect_cpu_features()["avx"]

    def _detect_avx2(self) -> bool:
        """Detect AVX2 support (best-effort, cross-platform)."""
        from bits_whisperer.utils.platform_utils import detect_cpu_features

        return detect_cpu_features()["avx2"]

    def _detect_cuda(self) -> tuple[bool, str, float]:
        """Detect CUDA GPU availability (cross-platform).

        Returns:
            (has_cuda, gpu_name, vram_gb)
        """
        from bits_whisperer.utils.platform_utils import detect_gpu

        return detect_gpu()

    def _evaluate_models(self, profile: DeviceProfile) -> None:
        """Classify each model as eligible, warned, or ineligible.

        Args:
            profile: The DeviceProfile to update with eligibility lists.
        """
        for model in WHISPER_MODELS:
            if self._model_fully_eligible(model, profile):
                profile.eligible_models.append(model.id)
            elif self._model_warn_eligible(model, profile):
                profile.warned_models.append(model.id)
            else:
                profile.ineligible_models.append(model.id)

    def _model_fully_eligible(self, model: WhisperModelInfo, profile: DeviceProfile) -> bool:
        """Check if hardware comfortably supports the model."""
        # GPU path
        if (
            profile.has_cuda
            and profile.gpu_vram_gb >= model.min_vram_gb
            and profile.ram_gb >= model.min_ram_gb
        ):
            return True

        # CPU path (only for models that don't require GPU: min_vram_gb == 0)
        return (
            model.min_vram_gb == 0
            and profile.cpu_cores_physical >= model.min_cpu_cores
            and profile.ram_gb >= model.min_ram_gb
        )

    def _model_warn_eligible(self, model: WhisperModelInfo, profile: DeviceProfile) -> bool:
        """Check if hardware can run the model but with degraded performance."""
        # CPU fallback for GPU-preferred models
        # Allow CPU inference for small/medium if enough RAM
        if (
            not profile.has_cuda
            and model.min_vram_gb > 0
            and model.min_ram_gb <= _CPU_WARN_THRESHOLD_GB
            and profile.ram_gb >= model.min_ram_gb
            and profile.cpu_cores_physical >= model.min_cpu_cores
        ):
            return True
        # GPU with less VRAM than ideal but meets minimum via quantization
        return (
            profile.has_cuda
            and profile.gpu_vram_gb > 0
            and profile.gpu_vram_gb >= model.min_vram_gb * 0.7
        )
