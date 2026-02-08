"""AssemblyAI transcription provider."""

from __future__ import annotations

import logging
import threading
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

# Lock to protect global aai.settings.api_key mutation (SDK limitation)
_assemblyai_lock = threading.Lock()


class AssemblyAIProvider(TranscriptionProvider):
    """Cloud transcription via the AssemblyAI API."""

    RATE_PER_MINUTE: float = 0.011  # USD

    def __init__(self) -> None:
        """Initialize AssemblyAI provider with default settings."""
        self._punctuate: bool = True
        self._format_text: bool = True
        self._auto_chapters: bool = False
        self._content_safety: bool = False
        self._sentiment_analysis: bool = False
        self._entity_detection: bool = False

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure AssemblyAI-specific settings.

        Args:
            settings: Dict with keys: punctuate, format_text, auto_chapters,
                content_safety, sentiment_analysis, entity_detection.
        """
        self._punctuate = settings.get("punctuate", self._punctuate)
        self._format_text = settings.get("format_text", self._format_text)
        self._auto_chapters = settings.get("auto_chapters", self._auto_chapters)
        self._content_safety = settings.get("content_safety", self._content_safety)
        self._sentiment_analysis = settings.get("sentiment_analysis", self._sentiment_analysis)
        self._entity_detection = settings.get("entity_detection", self._entity_detection)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return AssemblyAI capabilities."""
        return ProviderCapabilities(
            name="AssemblyAI",
            provider_type="cloud",
            supports_streaming=True,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=5000,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="Trial credits for new accounts.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate AssemblyAI API key by making a lightweight API call.

        Args:
            api_key: AssemblyAI API key.

        Returns:
            True if valid.
        """
        if not api_key or len(api_key) < 10:
            return False
        try:
            import requests

            resp = requests.get(
                "https://api.assemblyai.com/v2/transcript",
                headers={"Authorization": api_key},
                params={"limit": 1},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost at ~$0.011/min.

        Args:
            duration_seconds: Audio length.

        Returns:
            Estimated cost in USD.
        """
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "best",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via AssemblyAI.

        Args:
            audio_path: Path to audio file.
            language: Language code or 'auto'.
            model: Model variant.
            include_timestamps: Include timestamps.
            include_diarization: Enable diarization.
            api_key: AssemblyAI API key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult.
        """
        try:
            import assemblyai as aai
        except ImportError:
            raise RuntimeError("assemblyai not installed. pip install assemblyai") from None

        if not api_key:
            raise RuntimeError("AssemblyAI API key is required.")

        if progress_callback:
            progress_callback(10.0)

        logger.info("Starting AssemblyAI transcription: %s", Path(audio_path).name)

        config_kwargs: dict = {
            "punctuate": self._punctuate,
            "format_text": self._format_text,
            "auto_chapters": self._auto_chapters,
            "content_safety": self._content_safety,
            "sentiment_analysis": self._sentiment_analysis,
            "entity_detection": self._entity_detection,
        }
        if language and language != "auto":
            config_kwargs["language_code"] = language
        else:
            config_kwargs["language_detection"] = True

        if include_diarization:
            config_kwargs["speaker_labels"] = True

        config = aai.TranscriptionConfig(**config_kwargs)

        # Acquire lock to protect global aai.settings.api_key (SDK limitation)
        with _assemblyai_lock:
            aai.settings.api_key = api_key
            transcriber = aai.Transcriber(config=config)

            if progress_callback:
                progress_callback(25.0)

            transcript = transcriber.transcribe(audio_path)

        if progress_callback:
            progress_callback(85.0)

        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"AssemblyAI error: {transcript.error}")

        segments: list[TranscriptSegment] = []
        if transcript.utterances:
            for utt in transcript.utterances:
                segments.append(
                    TranscriptSegment(
                        start=utt.start / 1000.0,
                        end=utt.end / 1000.0,
                        text=utt.text.strip(),
                        confidence=utt.confidence,
                        speaker=utt.speaker or "",
                    )
                )
        elif transcript.words:
            # Group words into segments
            current_words: list[str] = []
            seg_start = transcript.words[0].start / 1000.0 if transcript.words else 0.0
            for word in transcript.words:
                current_words.append(word.text)
                if word.text.endswith((".", "!", "?")):
                    segments.append(
                        TranscriptSegment(
                            start=seg_start,
                            end=word.end / 1000.0,
                            text=" ".join(current_words),
                            confidence=word.confidence,
                        )
                    )
                    current_words = []
                    seg_start = word.end / 1000.0
            if current_words:
                segments.append(
                    TranscriptSegment(
                        start=seg_start,
                        end=transcript.words[-1].end / 1000.0,
                        text=" ".join(current_words),
                    )
                )

        if progress_callback:
            progress_callback(100.0)

        duration = transcript.audio_duration or 0.0

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="assemblyai",
            model=model,
            language=transcript.language_code or language,
            duration_seconds=duration,
            segments=segments,
            full_text=transcript.text or "",
            created_at=datetime.now().isoformat(),
        )
