"""Google Cloud Speech-to-Text transcription provider."""

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


class GoogleSpeechProvider(TranscriptionProvider):
    """Cloud transcription via Google Cloud Speech-to-Text."""

    RATE_PER_MINUTE: float = 0.024  # USD (standard model)

    def __init__(self) -> None:
        """Initialize Google Speech provider with default settings."""
        self._model: str = "default"
        self._max_speaker_count: int = 6

    def configure(self, settings: dict[str, Any]) -> None:
        """Configure Google Speech-specific settings.

        Args:
            settings: Dict with keys: model, max_speaker_count.
        """
        self._model = settings.get("model", self._model)
        self._max_speaker_count = settings.get("max_speaker_count", self._max_speaker_count)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Google Cloud Speech capabilities."""
        return ProviderCapabilities(
            name="Google Cloud Speech",
            provider_type="cloud",
            supports_streaming=True,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=480,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="60 minutes/month free. Then ~$0.024/min.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Google credentials with a live API call.

        Loads the service account JSON and makes a lightweight
        ``ListOperations`` call to confirm the credentials are accepted
        by Google's servers.

        Args:
            api_key: Path to service account JSON file.

        Returns:
            True if credentials are accepted by Google Cloud.
        """
        try:
            from google.oauth2 import service_account

            # Service account JSON file
            if Path(api_key).exists():
                creds = service_account.Credentials.from_service_account_file(api_key)
            else:
                return False

            # Make a real API call to verify the credentials against Google
            from google.cloud import speech

            client = speech.SpeechClient(credentials=creds)
            # list_operations is a lightweight call that validates auth
            # without consuming any recognition quota.
            client.transport.operations_client.list_operations(name="", page_size=1)
            return True
        except Exception:
            logger.debug("Google Cloud Speech validation failed", exc_info=True)
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost at ~$0.024 per minute.

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
        model: str = "default",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Google Cloud Speech-to-Text.

        Args:
            audio_path: Path to audio file.
            language: Language code (e.g. 'en-US') or 'auto'.
            model: Google model variant.
            include_timestamps: Include word/segment timestamps.
            include_diarization: Enable speaker diarization.
            api_key: Path to service account JSON or set via env.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult.
        """
        try:
            from google.cloud import speech
        except ImportError:
            raise RuntimeError(
                "google-cloud-speech not installed. pip install google-cloud-speech"
            ) from None

        if progress_callback:
            progress_callback(10.0)

        logger.info("Starting Google Speech transcription: %s", Path(audio_path).name)

        # Build credentials without mutating os.environ (thread-safe)
        if api_key and Path(api_key).exists():
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(api_key)
            client = speech.SpeechClient(credentials=credentials)
        elif api_key:
            # Treat as an API key string — not a file path
            raise RuntimeError(
                "Google Cloud Speech requires a service account JSON file path. "
                "Provide the full path to your credentials file."
            )
        else:
            raise RuntimeError(
                "Google Cloud Speech API credentials are required. "
                "Provide a path to your service account JSON file."
            )

        with open(audio_path, "rb") as f:
            content = f.read()

        audio = speech.RecognitionAudio(content=content)
        lang_code = "en-US" if language == "auto" else language

        config_kwargs: dict = {
            "encoding": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "sample_rate_hertz": 16000,
            "language_code": lang_code,
            "enable_word_time_offsets": include_timestamps,
            "enable_automatic_punctuation": True,
        }
        if include_diarization:
            diarization_config = speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=2,
                max_speaker_count=self._max_speaker_count,
            )
            config_kwargs["diarization_config"] = diarization_config

        config = speech.RecognitionConfig(**config_kwargs)

        if progress_callback:
            progress_callback(30.0)

        # Use long_running_recognize for files > 1 minute
        operation = client.long_running_recognize(config=config, audio=audio)

        if progress_callback:
            progress_callback(50.0)

        response = operation.result(timeout=600)

        if progress_callback:
            progress_callback(85.0)

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        for result in response.results:
            alt = result.alternatives[0] if result.alternatives else None
            if alt:
                text = alt.transcript.strip()
                full_text_parts.append(text)

                start_time = 0.0
                end_time = 0.0
                if alt.words:
                    start_time = (
                        alt.words[0].start_time.total_seconds() if alt.words[0].start_time else 0.0
                    )
                    end_time = (
                        alt.words[-1].end_time.total_seconds() if alt.words[-1].end_time else 0.0
                    )

                segments.append(
                    TranscriptSegment(
                        start=start_time,
                        end=end_time,
                        text=text,
                        confidence=alt.confidence,
                    )
                )

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="google_speech",
            model=model or self._model,
            language=lang_code,
            duration_seconds=0.0,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )
