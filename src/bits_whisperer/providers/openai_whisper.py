"""OpenAI Whisper API transcription provider."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)


class OpenAIWhisperProvider(TranscriptionProvider):
    """Cloud transcription via the OpenAI Whisper API."""

    RATE_PER_MINUTE: float = 0.006  # USD

    def __init__(self) -> None:
        """Initialize OpenAI Whisper provider with default settings."""
        self._model: str = "whisper-1"
        self._temperature: float = 0.0

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure OpenAI Whisper-specific settings.

        Args:
            settings: Dict with keys: model, temperature.
        """
        self._model = settings.get("model", self._model)
        self._temperature = settings.get("temperature", self._temperature)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return OpenAI Whisper API capabilities."""
        return ProviderCapabilities(
            name="OpenAI Whisper",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=True,
            max_file_size_mb=25,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="New-user credits may apply. Paid per minute.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key with a lightweight models list call.

        Args:
            api_key: OpenAI API key to test.

        Returns:
            True if the key works.
        """
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            client.models.list()
            return True
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost at $0.006 per minute.

        Args:
            duration_seconds: Audio length in seconds.

        Returns:
            Estimated cost in USD.
        """
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "whisper-1",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via the OpenAI API.

        Args:
            audio_path: Path to audio file.
            language: Language code or 'auto'.
            model: Model name (default whisper-1).
            include_timestamps: Request verbose output with timestamps.
            include_diarization: Ignored (not supported by OpenAI).
            api_key: OpenAI API key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult with segments and full text.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. pip install openai") from None

        if not api_key:
            raise RuntimeError("OpenAI API key is required.")

        client = OpenAI(api_key=api_key)

        if progress_callback:
            progress_callback(10.0)

        logger.info("Starting OpenAI transcription: %s", Path(audio_path).name)

        response_format = "verbose_json" if include_timestamps else "json"
        kwargs: dict = {
            "model": model or self._model,
            "response_format": response_format,
            "temperature": self._temperature,
        }
        if language and language != "auto":
            kwargs["language"] = language

        if progress_callback:
            progress_callback(30.0)

        with open(audio_path, "rb") as audio_file:
            kwargs["file"] = audio_file
            response = client.audio.transcriptions.create(**kwargs)

        if progress_callback:
            progress_callback(80.0)

        segments: list[TranscriptSegment] = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                segments.append(
                    TranscriptSegment(
                        start=(
                            seg.get("start", 0.0)
                            if isinstance(seg, dict)
                            else getattr(seg, "start", 0.0)
                        ),
                        end=(
                            seg.get("end", 0.0)
                            if isinstance(seg, dict)
                            else getattr(seg, "end", 0.0)
                        ),
                        text=(
                            seg.get("text", "")
                            if isinstance(seg, dict)
                            else getattr(seg, "text", "")
                        ).strip(),
                    )
                )

        full_text = response.text if hasattr(response, "text") else str(response)
        duration = getattr(response, "duration", 0.0) or 0.0

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="openai_whisper",
            model=model or self._model,
            language=getattr(response, "language", language) or language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
