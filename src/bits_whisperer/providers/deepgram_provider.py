"""Deepgram transcription provider."""

from __future__ import annotations

import contextlib
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


class DeepgramProvider(TranscriptionProvider):
    """Cloud transcription via the Deepgram API."""

    RATE_PER_MINUTE: float = 0.0125  # USD (Nova-2)

    def __init__(self) -> None:
        """Initialize Deepgram provider with default settings."""
        self._model: str = "nova-2"
        self._smart_format: bool = True
        self._punctuate: bool = True
        self._paragraphs: bool = True
        self._utterances: bool = False

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure Deepgram-specific settings.

        Args:
            settings: Dict with keys: model, smart_format, punctuate,
                paragraphs, utterances.
        """
        self._model = settings.get("model", self._model)
        self._smart_format = settings.get("smart_format", self._smart_format)
        self._punctuate = settings.get("punctuate", self._punctuate)
        self._paragraphs = settings.get("paragraphs", self._paragraphs)
        self._utterances = settings.get("utterances", self._utterances)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Deepgram capabilities."""
        return ProviderCapabilities(
            name="Deepgram",
            provider_type="cloud",
            supports_streaming=True,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=2000,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="$200 free credits for new accounts.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Deepgram API key by making a lightweight API call.

        Args:
            api_key: Deepgram API key.

        Returns:
            True if valid.
        """
        if not api_key:
            return False
        try:
            import requests

            resp = requests.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost at ~$0.0125/min for Nova-2.

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
        model: str = "nova-2",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via the Deepgram API.

        Args:
            audio_path: Path to audio file.
            language: Language code or 'auto'.
            model: Deepgram model (default nova-2).
            include_timestamps: Include timestamps.
            include_diarization: Enable diarization.
            api_key: Deepgram API key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult.
        """
        try:
            from deepgram import DeepgramClient, FileSource, PrerecordedOptions
        except ImportError:
            raise RuntimeError("deepgram-sdk not installed. pip install deepgram-sdk") from None

        if not api_key:
            raise RuntimeError("Deepgram API key is required.")

        if progress_callback:
            progress_callback(10.0)

        logger.info("Starting Deepgram transcription: %s", Path(audio_path).name)

        client = DeepgramClient(api_key)

        with open(audio_path, "rb") as f:
            buffer_data = f.read()

        payload: FileSource = {"buffer": buffer_data}

        options_dict: dict = {
            "model": model or self._model,
            "smart_format": self._smart_format,
            "punctuate": self._punctuate,
            "paragraphs": self._paragraphs,
            "utterances": self._utterances,
        }
        if language and language != "auto":
            options_dict["language"] = language
        else:
            options_dict["detect_language"] = True

        if include_diarization:
            options_dict["diarize"] = True

        options = PrerecordedOptions(**options_dict)

        if progress_callback:
            progress_callback(30.0)

        response = client.listen.rest.v("1").transcribe_file(  # type: ignore[attr-defined]
            payload, options
        )

        if progress_callback:
            progress_callback(85.0)

        segments: list[TranscriptSegment] = []
        full_text = ""

        try:
            result = response.results
            channels = result.channels if result else []
            if channels:
                alt = channels[0].alternatives[0] if channels[0].alternatives else None
                if alt:
                    full_text = alt.transcript or ""
                    if hasattr(alt, "words") and alt.words:
                        # Group words into segments by sentence/paragraph
                        current_segment_words: list = []
                        seg_start = alt.words[0].start if alt.words else 0.0
                        for word in alt.words:
                            current_segment_words.append(word.punctuated_word or word.word)
                            if (
                                hasattr(word, "punctuated_word")
                                and word.punctuated_word
                                and word.punctuated_word.endswith((".", "!", "?"))
                            ):
                                segments.append(
                                    TranscriptSegment(
                                        start=seg_start,
                                        end=word.end,
                                        text=" ".join(current_segment_words),
                                        confidence=word.confidence,
                                    )
                                )
                                current_segment_words = []
                                seg_start = word.end
                        # Remaining words
                        if current_segment_words:
                            segments.append(
                                TranscriptSegment(
                                    start=seg_start,
                                    end=alt.words[-1].end,
                                    text=" ".join(current_segment_words),
                                )
                            )
        except Exception as exc:
            logger.warning("Error parsing Deepgram response: %s", exc)
            full_text = str(response)

        if progress_callback:
            progress_callback(100.0)

        duration = 0.0
        with contextlib.suppress(Exception):
            duration = response.metadata.duration or 0.0

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="deepgram",
            model=model or self._model,
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
