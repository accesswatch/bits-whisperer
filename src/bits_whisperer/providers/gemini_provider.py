"""Google Gemini multimodal transcription provider."""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import datetime
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)

# Lock to protect global genai.configure() calls (SDK limitation)
_gemini_lock = threading.Lock()


class GeminiProvider(TranscriptionProvider):
    """Cloud transcription via Google Gemini's native audio understanding.

    Gemini 2.0 Flash and Pro can directly process audio files and produce
    accurate transcripts. Gemini excels at understanding context, speaker
    intent, and produces well-punctuated output. Supports long-form audio
    via the Files API.
    """

    # Gemini 2.0 Flash: ~$0.10/M input tokens, audio ≈ 32 tokens/sec
    # ≈ 32 * 60 * 0.10 / 1_000_000 ≈ $0.000192/min
    RATE_PER_MINUTE: float = 0.0002

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="Google Gemini",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=2000,  # Files API supports large uploads
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description=(
                "Generous free tier via Google AI Studio. " "Pay-as-you-go via Vertex AI."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        try:
            import google.generativeai as genai

            with _gemini_lock:
                genai.configure(api_key=api_key)
                genai.list_models()
            return True
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "gemini-2.0-flash",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Google Gemini.

        Uses the generative AI Files API for upload and then prompts
        Gemini to produce a structured transcription.
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError(
                "google-generativeai package not installed. " "pip install google-generativeai"
            ) from None

        if not api_key:
            raise RuntimeError("Google Gemini API key is required.")

        # Acquire lock to protect global genai.configure() (SDK limitation)
        with _gemini_lock:
            genai.configure(api_key=api_key)

            if progress_callback:
                progress_callback(5.0)

            logger.info("Uploading audio to Gemini Files API: %s", Path(audio_path).name)
            audio_file = genai.upload_file(audio_path)

            if progress_callback:
                progress_callback(25.0)

            # Build prompt
            lang_hint = f" The audio is in {language}." if language != "auto" else ""
            ts_hint = (
                " Include timestamps [MM:SS] at the start of each segment."
                if include_timestamps
                else ""
            )
            diar_hint = " Identify and label different speakers." if include_diarization else ""

            prompt = (
                "Transcribe the following audio file accurately and completely. "
                "Output only the transcription text."
                + lang_hint
                + ts_hint
                + diar_hint
                + "\n\nFormat each segment on its own line. "
                "If timestamps are requested, use the format [MM:SS] at the beginning of each line."
            )

            model_obj = genai.GenerativeModel(model or "gemini-2.0-flash")

            if progress_callback:
                progress_callback(40.0)

            logger.info("Sending transcription request to Gemini (%s)", model)
            response = model_obj.generate_content([audio_file, prompt])

        if progress_callback:
            progress_callback(85.0)

        full_text = response.text.strip() if response.text else ""

        # Parse segments from timestamped output
        segments: list[TranscriptSegment] = []
        if include_timestamps and full_text:
            import re

            ts_pattern = re.compile(r"\[(\d{1,2}):(\d{2})\]\s*(.*)")
            lines = full_text.split("\n")
            for i, line in enumerate(lines):
                m = ts_pattern.match(line.strip())
                if m:
                    start = int(m.group(1)) * 60 + int(m.group(2))
                    text = m.group(3).strip()
                    # Estimate end from next segment
                    end = start + 30  # default
                    if i + 1 < len(lines):
                        m2 = ts_pattern.match(lines[i + 1].strip())
                        if m2:
                            end = int(m2.group(1)) * 60 + int(m2.group(2))

                    speaker = ""
                    if include_diarization:
                        sp_match = re.match(r"\[?(Speaker\s*\d+|[A-Z][a-z]+)\]?:\s*(.*)", text)
                        if sp_match:
                            speaker = sp_match.group(1)
                            text = sp_match.group(2)

                    segments.append(
                        TranscriptSegment(
                            start=float(start),
                            end=float(end),
                            text=text,
                            speaker=speaker,
                        )
                    )

        if progress_callback:
            progress_callback(100.0)

        # Clean delete of uploaded file (best-effort)
        with contextlib.suppress(Exception):
            audio_file.delete()

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="gemini",
            model=model or "gemini-2.0-flash",
            language=language,
            duration_seconds=0.0,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )
