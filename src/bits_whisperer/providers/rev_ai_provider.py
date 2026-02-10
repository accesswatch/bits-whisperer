"""Rev.ai provider — highly accurate async transcription."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)


class RevAIProvider(TranscriptionProvider):
    """Highly accurate speech-to-text via Rev.ai async API.

    Rev.ai is a speech recognition company known for its human-level
    accuracy. They offer a robust async transcription API with speaker
    diarization, custom vocabularies, and multi-language support.

    Pricing: $0.02/min (with 300 min free trial).
    """

    RATE_PER_MINUTE: float = 0.02

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="Rev.ai",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=2000,
            supported_languages=[
                "en",
                "es",
                "fr",
                "de",
                "it",
                "pt",
                "nl",
                "ja",
                "ko",
                "zh",
                "ar",
                "hi",
                "ru",
                "sv",
                "da",
                "no",
                "fi",
                "pl",
                "cs",
            ],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="300 minutes free trial. $0.02/min after.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        try:
            from rev_ai import apiclient

            client = apiclient.RevAiAPIClient(api_key)
            account = client.get_account()
            return account is not None
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        model: str = "",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Rev.ai async API.

        Submits the file, polls for completion, then fetches the transcript.
        """
        try:
            from rev_ai import apiclient
        except ImportError:
            raise RuntimeError("rev_ai package not installed. pip install rev_ai") from None

        if not api_key:
            raise RuntimeError("Rev.ai API key is required.")

        client = apiclient.RevAiAPIClient(api_key)

        if progress_callback:
            progress_callback(5.0)

        logger.info(
            "Submitting to Rev.ai: %s (lang=%s, diarization=%s)",
            Path(audio_path).name,
            language,
            include_diarization,
        )

        # Submit the job
        submit_kwargs: dict = {
            "filename": audio_path,
        }
        if language and language != "auto":
            submit_kwargs["language"] = language
        else:
            submit_kwargs["language"] = "en"

        if include_diarization:
            submit_kwargs["speakers_count"] = None  # Auto-detect speakers

        job = client.submit_job_local_file(
            audio_path,
            **{k: v for k, v in submit_kwargs.items() if k != "filename"},
        )
        job_id = job.id

        if progress_callback:
            progress_callback(20.0)

        # Poll until complete
        poll_interval = 3.0
        max_polls = 600  # 30 min max wait
        for i in range(max_polls):
            details = client.get_job_details(job_id)
            status = details.status.name if hasattr(details.status, "name") else str(details.status)

            if status.lower() == "transcribed":
                break
            if status.lower() == "failed":
                failure = getattr(details, "failure", "Unknown error")
                raise RuntimeError(f"Rev.ai transcription failed: {failure}")

            if progress_callback:
                progress = min(20.0 + (i / max_polls) * 60.0, 80.0)
                progress_callback(progress)

            time.sleep(poll_interval)
        else:
            raise RuntimeError("Rev.ai transcription timed out after 30 minutes.")

        if progress_callback:
            progress_callback(85.0)

        # Fetch transcript
        transcript = client.get_transcript_object(job_id)

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        if hasattr(transcript, "monologues") and transcript.monologues:
            for monologue in transcript.monologues:
                speaker = getattr(monologue, "speaker", None)
                speaker_id = int(speaker) if speaker is not None else None

                # Combine elements into text for this monologue
                mono_text_parts: list[str] = []
                start_time: float | None = None
                end_time: float = 0.0

                for element in monologue.elements:
                    if element.type_ == "text":
                        mono_text_parts.append(element.value)
                        ts = getattr(element, "ts", None)
                        end_ts = getattr(element, "end_ts", None)
                        if ts is not None and start_time is None:
                            start_time = ts
                        if end_ts is not None:
                            end_time = end_ts
                    elif element.type_ == "punct":
                        mono_text_parts.append(element.value)

                text = "".join(mono_text_parts).strip()
                if text:
                    segments.append(
                        TranscriptSegment(
                            start=start_time or 0.0,
                            end=end_time,
                            text=text,
                            speaker=f"Speaker {speaker_id}" if speaker_id is not None else None,
                        )
                    )
                    full_text_parts.append(text)

        full_text = " ".join(full_text_parts)

        # Estimate duration from last segment
        duration = segments[-1].end if segments else 0.0

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id=job_id,
            audio_file=Path(audio_path).name,
            provider="rev_ai",
            model="rev_ai_default",
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
