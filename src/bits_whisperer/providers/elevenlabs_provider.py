"""ElevenLabs Scribe transcription provider.

ElevenLabs Scribe (speech-to-text) is one of the most accurate cloud
transcription APIs available, rivalling or exceeding Whisper Large V3
across many benchmarks. It supports 99+ languages, speaker
diarization, timestamps, and handles audio up to 2 GB.

Pricing: ~$0.005 per minute — one of the cheapest high-accuracy options.
"""

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


class ElevenLabsProvider(TranscriptionProvider):
    """Cloud transcription via ElevenLabs Scribe (speech-to-text).

    ElevenLabs Scribe delivers state-of-the-art accuracy across 99+
    languages with built-in speaker diarization. It handles files up
    to 2 GB and returns word-level timestamps.

    See: https://elevenlabs.io/speech-to-text
    """

    RATE_PER_MINUTE: float = 0.005  # USD

    def __init__(self) -> None:
        """Initialize ElevenLabs provider with default settings."""
        self._timestamps_granularity: str = "segment"

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure ElevenLabs-specific settings.

        Args:
            settings: Dict with keys: timestamps_granularity.
        """
        self._timestamps_granularity = settings.get(
            "timestamps_granularity", self._timestamps_granularity
        )

    def get_capabilities(self) -> ProviderCapabilities:
        """Return ElevenLabs Scribe capabilities."""
        return ProviderCapabilities(
            name="ElevenLabs Scribe",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=2000,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description=(
                "Free tier with limited minutes. "
                "One of the most accurate and affordable cloud providers."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key with a lightweight models list call.

        Args:
            api_key: ElevenLabs API key to validate.

        Returns:
            True if the key is valid.
        """
        try:
            import httpx

            resp = httpx.get(
                "https://api.elevenlabs.io/v1/models",
                headers={"xi-api-key": api_key},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost at $0.005 per minute.

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
        model: str = "scribe_v1",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via the ElevenLabs speech-to-text API.

        Args:
            audio_path: Path to audio file.
            language: ISO 639-1 language code or 'auto'.
            model: Model name (default scribe_v1).
            include_timestamps: Include word/segment timestamps.
            include_diarization: Include speaker labels.
            api_key: ElevenLabs API key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult with segments and full text.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx package not installed. " "pip install httpx") from None

        if not api_key:
            raise RuntimeError("ElevenLabs API key is required.")

        if progress_callback:
            progress_callback(5.0)

        logger.info(
            "Starting ElevenLabs Scribe transcription: %s",
            Path(audio_path).name,
        )

        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": api_key}

        # Build multipart form data
        file_path = Path(audio_path)
        data: dict[str, str] = {
            "model_id": model or "scribe_v1",
        }
        if language and language != "auto":
            data["language_code"] = language
        if include_diarization:
            data["diarize"] = "true"
        if include_timestamps:
            data["timestamps_granularity"] = self._timestamps_granularity

        if progress_callback:
            progress_callback(15.0)

        with open(audio_path, "rb") as f:
            files = {"file": (file_path.name, f, "audio/mpeg")}
            with httpx.Client(timeout=600) as client:
                response = client.post(
                    url,
                    headers=headers,
                    data=data,
                    files=files,
                )

        if progress_callback:
            progress_callback(80.0)

        if response.status_code != 200:
            raise RuntimeError(
                f"ElevenLabs API error ({response.status_code}): " f"{response.text[:500]}"
            )

        result_data = response.json()

        full_text = result_data.get("text", "")

        # Parse segments/words
        segments: list[TranscriptSegment] = []
        words = result_data.get("words", [])

        if words:
            # Group words into sentence-like segments
            current_words: list[str] = []
            current_start = 0.0
            current_end = 0.0
            current_speaker = ""

            for word_info in words:
                word_text = word_info.get("text", "")
                word_start = word_info.get("start", 0.0)
                word_end = word_info.get("end", 0.0)
                speaker = word_info.get("speaker_id", "")

                if not current_words:
                    current_start = word_start
                    current_speaker = speaker

                current_words.append(word_text)
                current_end = word_end

                # Segment break on sentence punctuation or speaker change
                is_sentence_end = word_text.rstrip().endswith((".", "!", "?"))
                speaker_changed = speaker and speaker != current_speaker

                if is_sentence_end or speaker_changed or len(current_words) >= 40:
                    segment_text = " ".join(current_words).strip()
                    # Clean up spacing before punctuation
                    for punct in (".", ",", "!", "?", ";", ":"):
                        segment_text = segment_text.replace(f" {punct}", punct)

                    segments.append(
                        TranscriptSegment(
                            start=current_start,
                            end=current_end,
                            text=segment_text,
                            speaker=(current_speaker if include_diarization else ""),
                            confidence=word_info.get("confidence", 0.0),
                        )
                    )
                    current_words = []
                    if speaker_changed:
                        current_speaker = speaker

            # Flush remaining words
            if current_words:
                segment_text = " ".join(current_words).strip()
                for punct in (".", ",", "!", "?", ";", ":"):
                    segment_text = segment_text.replace(f" {punct}", punct)
                segments.append(
                    TranscriptSegment(
                        start=current_start,
                        end=current_end,
                        text=segment_text,
                        speaker=current_speaker if include_diarization else "",
                    )
                )

        if progress_callback:
            progress_callback(100.0)

        detected_lang = result_data.get("language_code", language) or language
        duration = segments[-1].end if segments else 0.0

        return TranscriptionResult(
            job_id="",
            audio_file=file_path.name,
            provider="elevenlabs",
            model=model or "scribe_v1",
            language=detected_lang,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
