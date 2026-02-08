"""Local Whisper transcription via faster-whisper."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)
from bits_whisperer.utils.constants import MODELS_DIR, WHISPER_MODELS

logger = logging.getLogger(__name__)


class LocalWhisperProvider(TranscriptionProvider):
    """On-device transcription using faster-whisper (CTranslate2)."""

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for local Whisper inference."""
        return ProviderCapabilities(
            name="Local Whisper",
            provider_type="local",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=True,
            max_file_size_mb=500,
            supported_languages=["auto"],
            rate_per_minute_usd=0.0,
            free_tier_description="Free forever — runs on your computer.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Local provider doesn't need API keys — always valid."""
        return True

    def estimate_cost(self, duration_seconds: float) -> float:
        """Local inference is free."""
        return 0.0

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "base",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using faster-whisper locally.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            language: Language code or 'auto' for detection.
            model: Whisper model ID (e.g. 'tiny', 'base', 'small').
            include_timestamps: Whether to include segment timestamps.
            include_diarization: Ignored for local Whisper.
            api_key: Ignored for local provider.
            progress_callback: Optional progress callback (0–100).

        Returns:
            TranscriptionResult with segments and full text.
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            from bits_whisperer.core.sdk_installer import is_frozen

            if is_frozen():
                raise RuntimeError(
                    "The faster-whisper engine is not installed.\n\n"
                    "Go to Settings, then Providers, then Local Whisper and click "
                    "'Install SDK' to download it automatically."
                ) from None
            raise RuntimeError(
                "faster-whisper is not installed. " "Install it with: pip install faster-whisper"
            ) from None

        # Determine compute type based on hardware probe
        device = "cpu"
        compute_type = "int8"
        try:
            from bits_whisperer.utils.platform_utils import detect_gpu

            has_cuda, _gpu_name, _vram = detect_gpu()
            if has_cuda:
                device = "cuda"
                compute_type = "float16"
        except Exception:
            pass

        logger.info(
            "Starting local transcription: model=%s, device=%s, file=%s",
            model,
            device,
            Path(audio_path).name,
        )

        if progress_callback:
            progress_callback(5.0)

        # Look up repo_id for the model
        model_path = model
        for m in WHISPER_MODELS:
            if m.id == model:
                model_path = m.repo_id or model
                break

        whisper_model = WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
            download_root=str(MODELS_DIR),
        )

        if progress_callback:
            progress_callback(15.0)

        lang = None if language == "auto" else language

        segments_iter, info = whisper_model.transcribe(
            audio_path,
            language=lang,
            beam_size=5,
            word_timestamps=include_timestamps,
            vad_filter=True,
        )

        detected_language = info.language
        duration = info.duration

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []
        processed_duration = 0.0

        for seg in segments_iter:
            # Normalize avg_logprob (negative, e.g. -0.3) to [0, 1] confidence
            raw_logprob = seg.avg_logprob if hasattr(seg, "avg_logprob") else 0.0
            conf = max(0.0, min(1.0, 1.0 + raw_logprob)) if raw_logprob else 0.0
            segments.append(
                TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=conf,
                )
            )
            full_text_parts.append(seg.text.strip())
            processed_duration = seg.end

            if progress_callback and duration > 0:
                pct = 15.0 + (processed_duration / duration) * 80.0
                progress_callback(min(95.0, pct))

        if progress_callback:
            progress_callback(100.0)

        result = TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="local_whisper",
            model=model,
            language=detected_language or language,
            duration_seconds=duration,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )

        logger.info(
            "Local transcription complete: %d segments, %.1fs, language=%s",
            len(segments),
            duration,
            detected_language,
        )
        return result
