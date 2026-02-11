"""Groq Whisper provider — ultra-fast cloud Whisper inference."""

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


class GroqWhisperProvider(TranscriptionProvider):
    """Ultra-fast cloud transcription via Groq's Whisper Large V3 Turbo.

    Groq runs Whisper on custom LPU hardware, delivering transcription
    at ~188x real-time speed — a 1-hour file completes in ~19 seconds.
    Currently supports whisper-large-v3 and whisper-large-v3-turbo.

    Pricing: Free tier available. Production: ~$0.0028/min.
    """

    RATE_PER_MINUTE: float = 0.0028

    def __init__(self) -> None:
        """Initialize Groq Whisper provider with default settings."""
        self._model: str = "whisper-large-v3-turbo"

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure Groq Whisper-specific settings.

        Args:
            settings: Dict with keys: model.
        """
        self._model = settings.get("model", self._model)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="Groq Whisper (Ultra-Fast)",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=True,
            max_file_size_mb=25,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description=(
                "Free tier with rate limits. Fastest Whisper API available — "
                "188x real-time speed on Groq LPU hardware."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        try:
            from groq import Groq

            client = Groq(api_key=api_key)
            client.models.list()
            return True
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "whisper-large-v3-turbo",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Groq's Whisper API.

        Uses the OpenAI-compatible endpoint on Groq infrastructure.
        """
        try:
            from groq import Groq
        except ImportError:
            raise RuntimeError("groq package not installed. pip install groq") from None

        if not api_key:
            raise RuntimeError("Groq API key is required.")

        client = Groq(api_key=api_key)

        if progress_callback:
            progress_callback(10.0)

        logger.info(
            "Starting Groq Whisper transcription: %s (model: %s)",
            Path(audio_path).name,
            model,
        )

        kwargs: dict = {
            "model": model or self._model,
            "response_format": "verbose_json" if include_timestamps else "json",
        }
        if language and language != "auto":
            kwargs["language"] = language

        if progress_callback:
            progress_callback(30.0)

        with open(audio_path, "rb") as audio_file:
            kwargs["file"] = audio_file
            response = client.audio.transcriptions.create(**kwargs)

        if progress_callback:
            progress_callback(85.0)

        segments: list[TranscriptSegment] = []
        if hasattr(response, "segments") and response.segments:  # type: ignore[attr-defined]
            for seg in response.segments:  # type: ignore[attr-defined]
                start = (
                    seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0)
                )
                end = seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0)
                text = (
                    seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")
                ).strip()
                segments.append(TranscriptSegment(start=start, end=end, text=text))

        full_text = response.text if hasattr(response, "text") else str(response)
        duration = getattr(response, "duration", 0.0) or 0.0

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="groq_whisper",
            model=model or self._model,
            language=getattr(response, "language", language) or language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
