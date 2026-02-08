"""Base protocol for transcription provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bits_whisperer.core.job import TranscriptionResult

ProgressCallback = Callable[[float], None]  # 0.0 -- 100.0


@dataclass(frozen=True)
class ProviderCapabilities:
    """Describes what a provider can do."""

    name: str
    provider_type: str  # "cloud" or "local"
    supports_streaming: bool = False
    supports_timestamps: bool = True
    supports_diarization: bool = False
    supports_language_detection: bool = True
    max_file_size_mb: int = 500
    supported_languages: list[str] = field(default_factory=lambda: ["auto"])
    rate_per_minute_usd: float = 0.0  # 0 = free
    free_tier_description: str = ""


class TranscriptionProvider(ABC):
    """Abstract base for all transcription provider adapters.

    Each cloud or local provider implements this interface. The
    ProviderManager selects and invokes the appropriate adapter
    for each transcription job.
    """

    def configure(self, settings: dict[str, Any]) -> None:  # noqa: B027
        """Apply provider-specific settings before transcription.

        Called by the TranscriptionService before ``transcribe()`` to
        inject per-provider defaults chosen by the user (e.g. Auphonic
        loudness target, Deepgram model variant, diarization settings).

        Subclasses override this to accept their specific options.
        The default implementation is a no-op.

        Args:
            settings: Dict of provider-specific key-value settings.
        """

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return the provider's capabilities and pricing.

        Returns:
            ProviderCapabilities describing what this provider supports.
        """
        ...

    @abstractmethod
    def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key with a lightweight dry-run call.

        Args:
            api_key: The API key to test.

        Returns:
            True if the key is valid and working.
        """
        ...

    @abstractmethod
    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate the cost to transcribe audio of the given duration.

        Args:
            duration_seconds: Length of the audio in seconds.

        Returns:
            Estimated cost in USD. 0.0 for free providers.
        """
        ...

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            language: Language code or 'auto' for detection.
            model: Model identifier (provider-specific).
            include_timestamps: Whether to include segment timestamps.
            include_diarization: Whether to identify speakers.
            api_key: API key for cloud providers.
            progress_callback: Optional progress callback (0–100).

        Returns:
            TranscriptionResult with segments and full text.

        Raises:
            RuntimeError: On transcription failure.
        """
        ...
