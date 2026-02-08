"""Speechmatics provider — highest-accuracy multilingual transcription."""

from __future__ import annotations

import json
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


class SpeechmaticsProvider(TranscriptionProvider):
    """Enterprise-grade transcription via Speechmatics batch API.

    Speechmatics is renowned for industry-leading accuracy across 50+
    languages, with exceptional handling of accents, dialects, and
    domain-specific terminology.

    Pricing: ~$0.017/min (pay-as-you-go).
    """

    RATE_PER_MINUTE: float = 0.017

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="Speechmatics",
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
                "tr",
                "th",
                "vi",
                "id",
                "ms",
                "tl",
                "uk",
                "ro",
                "hu",
                "bg",
                "hr",
                "sk",
                "sl",
                "lt",
                "lv",
                "et",
                "ca",
                "gl",
                "eu",
                "cy",
            ],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description=(
                "Free trial credits available. Best-in-class multilingual accuracy "
                "with 50+ languages."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key by listing recent jobs."""
        try:
            import httpx

            resp = httpx.get(
                "https://asr.api.speechmatics.com/v2/jobs",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"limit": 1},
                timeout=15,
            )
            return resp.status_code == 200
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
        """Transcribe via Speechmatics batch API using httpx.

        We use the REST API directly for maximum compatibility rather than
        the Speechmatics Python SDK, which has complex async dependencies.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx package not installed. pip install httpx") from None

        if not api_key:
            raise RuntimeError("Speechmatics API key is required.")

        base_url = "https://asr.api.speechmatics.com/v2"
        headers = {"Authorization": f"Bearer {api_key}"}

        if progress_callback:
            progress_callback(5.0)

        logger.info(
            "Submitting to Speechmatics: %s (lang=%s, diarization=%s)",
            Path(audio_path).name,
            language,
            include_diarization,
        )

        # Build transcription config
        transcription_config: dict = {
            "language": language if language and language != "auto" else "en",
        }
        if language == "auto":
            transcription_config["language"] = "auto"

        config: dict = {
            "type": "transcription",
            "transcription_config": transcription_config,
        }

        if include_diarization:
            config["transcription_config"]["diarization"] = "speaker"

        # Submit job via multipart form
        with open(audio_path, "rb") as f:
            files = {
                "data_file": (Path(audio_path).name, f, "application/octet-stream"),
            }
            data = {
                "config": json.dumps(config),
            }

            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/jobs/",
                    headers=headers,
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                job_id = resp.json()["id"]

        if progress_callback:
            progress_callback(20.0)

        # Poll for completion
        poll_interval = 3.0
        max_polls = 600  # 30 min
        with httpx.Client(timeout=30) as client:
            for i in range(max_polls):
                resp = client.get(f"{base_url}/jobs/{job_id}", headers=headers)
                resp.raise_for_status()
                job_data = resp.json()["job"]

                status = job_data.get("status", "")
                if status == "done":
                    break
                elif status in ("rejected", "deleted"):
                    error = job_data.get("errors", [{}])
                    raise RuntimeError(f"Speechmatics job {status}: {error}")

                if progress_callback:
                    progress = min(20.0 + (i / max_polls) * 60.0, 80.0)
                    progress_callback(progress)

                time.sleep(poll_interval)
            else:
                raise RuntimeError("Speechmatics transcription timed out after 30 minutes.")

            if progress_callback:
                progress_callback(85.0)

            # Fetch transcript
            resp = client.get(
                f"{base_url}/jobs/{job_id}/transcript",
                headers=headers,
                params={"format": "json-v2"},
            )
            resp.raise_for_status()
            transcript_data = resp.json()

        if progress_callback:
            progress_callback(90.0)

        # Parse results
        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        results = transcript_data.get("results", [])
        current_segment_words: list[str] = []
        seg_start: float = 0.0
        seg_end: float = 0.0
        current_speaker: str | None = None

        for result in results:
            r_type = result.get("type", "")
            if r_type != "word":
                continue

            start_time = result.get("start_time", 0.0)
            end_time = result.get("end_time", 0.0)
            content = result.get("alternatives", [{}])[0].get("content", "")
            speaker = result.get("alternatives", [{}])[0].get("speaker", None)
            speaker_label = f"Speaker {speaker}" if speaker else None

            if not current_segment_words:
                seg_start = start_time
                current_speaker = speaker_label

            # Break on speaker change or after long pause (> 2s)
            should_break = False
            if (current_speaker != speaker_label and current_segment_words) or (
                current_segment_words and (start_time - seg_end) > 2.0
            ):
                should_break = True

            if should_break:
                text = " ".join(current_segment_words).strip()
                if text:
                    segments.append(
                        TranscriptSegment(
                            start=seg_start,
                            end=seg_end,
                            text=text,
                            speaker=current_speaker,
                        )
                    )
                    full_text_parts.append(text)
                current_segment_words = []
                seg_start = start_time
                current_speaker = speaker_label

            current_segment_words.append(content)
            seg_end = end_time

        # Flush remaining words
        if current_segment_words:
            text = " ".join(current_segment_words).strip()
            if text:
                segments.append(
                    TranscriptSegment(
                        start=seg_start,
                        end=seg_end,
                        text=text,
                        speaker=current_speaker,
                    )
                )
                full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        duration = segments[-1].end if segments else 0.0

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id=job_id,
            audio_file=Path(audio_path).name,
            provider="speechmatics",
            model="speechmatics_batch",
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
