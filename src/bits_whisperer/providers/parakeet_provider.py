"""NVIDIA Parakeet on-device transcription provider (NeMo-based).

Parakeet is NVIDIA's family of high-accuracy ASR models built on the
NeMo framework. Models are English-only and run entirely on-device
using either CPU or CUDA GPU.

Available models:
- parakeet-ctc-0.6b  — 600M params, CTC decoder (fast, simple)
- parakeet-tdt-0.6b  — 600M params, TDT decoder (better timestamps)
- parakeet-ctc-1.1b  — 1.1B params, CTC decoder (high accuracy)
- parakeet-tdt-1.1b  — 1.1B params, TDT decoder (best accuracy + timestamps)

Models are downloaded automatically from HuggingFace on first use
via the NeMo ``from_pretrained`` API and cached locally.
"""

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
from bits_whisperer.utils.constants import (
    PARAKEET_MODELS,
    get_parakeet_model_by_id,
)

logger = logging.getLogger(__name__)


class ParakeetProvider(TranscriptionProvider):
    """On-device transcription using NVIDIA Parakeet (NeMo).

    Parakeet models deliver state-of-the-art English ASR accuracy.
    The 0.6B models run well on modern CPUs; the 1.1B models benefit
    from a CUDA GPU.
    """

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for Parakeet inference."""
        return ProviderCapabilities(
            name="Parakeet",
            provider_type="local",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=False,
            max_file_size_mb=500,
            supported_languages=["en"],
            rate_per_minute_usd=0.0,
            free_tier_description=(
                "Free forever. NVIDIA's high-accuracy English ASR "
                "running on your computer via NeMo."
            ),
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
        language: str = "en",
        model: str = "parakeet-ctc-0.6b",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using NVIDIA Parakeet locally.

        Args:
            audio_path: Path to the audio file (WAV 16kHz mono preferred).
            language: Language code (only 'en' supported).
            model: Parakeet model ID (e.g. 'parakeet-ctc-0.6b').
            include_timestamps: Whether to include segment timestamps.
            include_diarization: Ignored for Parakeet.
            api_key: Ignored for local provider.
            progress_callback: Optional progress callback (0-100).

        Returns:
            TranscriptionResult with segments and full text.
        """
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError:
            from bits_whisperer.core.sdk_installer import is_frozen

            if is_frozen():
                raise RuntimeError(
                    "The NVIDIA NeMo ASR engine is not installed.\n\n"
                    "Go to Settings, then Providers, then Parakeet and click "
                    "'Install SDK' to download it automatically."
                ) from None
            raise RuntimeError(
                "nemo_toolkit[asr] is not installed. "
                "Install it with: pip install nemo_toolkit[asr]"
            ) from None

        # Resolve model info
        model_info = get_parakeet_model_by_id(model)
        if model_info is None:
            # Default to the smallest CTC model
            model_info = PARAKEET_MODELS[0]

        logger.info(
            "Starting Parakeet transcription: model=%s, file=%s",
            model_info.id,
            Path(audio_path).name,
        )

        if progress_callback:
            progress_callback(2.0)

        # Load the model — NeMo downloads from HuggingFace on first use
        # and caches to the local NeMo cache directory.
        try:
            if model_info.decoder_type == "ctc":
                asr_model = nemo_asr.models.EncDecCTCModelBPE.from_pretrained(
                    model_name=model_info.hf_repo_id
                )
            else:
                # TDT models use the RNNT/TDT model class
                asr_model = nemo_asr.models.EncDecRNNTBPEModel.from_pretrained(
                    model_name=model_info.hf_repo_id
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Parakeet model '{model_info.id}'.\n\n"
                f"The model will be downloaded from HuggingFace on first use "
                f"(~{model_info.disk_size_mb} MB).\n\n"
                f"Error: {exc}"
            ) from exc

        if progress_callback:
            progress_callback(20.0)

        # Transcribe the audio file
        try:
            if include_timestamps and model_info.decoder_type == "ctc":
                # CTC models support word-level timestamps via transcribe()
                output = asr_model.transcribe(
                    [audio_path],
                    timestamps=True,
                    batch_size=1,
                )
            elif include_timestamps and model_info.decoder_type == "tdt":
                output = asr_model.transcribe(
                    [audio_path],
                    timestamps=True,
                    batch_size=1,
                )
            else:
                output = asr_model.transcribe(
                    [audio_path],
                    batch_size=1,
                )
        except Exception as exc:
            raise RuntimeError(
                f"Parakeet transcription failed for '{Path(audio_path).name}'.\n\n" f"Error: {exc}"
            ) from exc

        if progress_callback:
            progress_callback(80.0)

        # Parse output — NeMo returns a list of Hypothesis objects or strings
        segments: list[TranscriptSegment] = []
        full_text = ""

        if isinstance(output, list) and len(output) > 0:
            result_item = output[0]

            # NeMo can return either a string or a Hypothesis object
            if isinstance(result_item, str):
                full_text = result_item.strip()
            elif hasattr(result_item, "text"):
                full_text = result_item.text.strip()
            else:
                full_text = str(result_item).strip()

            # Extract timestamp information if available
            if include_timestamps and hasattr(result_item, "timestep"):
                timestep = result_item.timestep
                if hasattr(timestep, "segments") and timestep.segments:
                    for seg in timestep.segments:
                        seg_start = getattr(seg, "start", 0.0)
                        seg_end = getattr(seg, "end", 0.0)
                        seg_text = getattr(seg, "text", "").strip()
                        seg_conf = getattr(seg, "confidence", 0.0)
                        if seg_text:
                            segments.append(
                                TranscriptSegment(
                                    start=seg_start,
                                    end=seg_end,
                                    text=seg_text,
                                    confidence=seg_conf,
                                )
                            )
                elif hasattr(timestep, "words") and timestep.words:
                    # Build segments from word-level timestamps
                    segments.extend(self._words_to_segments(timestep.words))

        # If no segments were extracted, create a single segment
        if not segments and full_text:
            segments.append(
                TranscriptSegment(
                    start=0.0,
                    end=0.0,
                    text=full_text,
                    confidence=0.0,
                )
            )

        # Estimate duration from audio file
        duration = self._get_audio_duration(audio_path)

        if progress_callback:
            progress_callback(100.0)

        result = TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="parakeet",
            model=model_info.id,
            language="en",
            duration_seconds=duration,
            segments=segments,
            full_text=full_text,
            created_at=datetime.now().isoformat(),
        )

        logger.info(
            "Parakeet transcription complete: %d segments, %.1fs, model=%s",
            len(segments),
            duration,
            model_info.id,
        )
        return result

    @staticmethod
    def _words_to_segments(
        words: list,
        max_words_per_segment: int = 25,
    ) -> list[TranscriptSegment]:
        """Group word-level timestamps into sentence-like segments.

        Args:
            words: List of word objects with start, end, text attributes.
            max_words_per_segment: Maximum words before forcing a segment break.

        Returns:
            List of TranscriptSegment grouped by natural breaks.
        """
        segments: list[TranscriptSegment] = []
        current_words: list = []

        for word in words:
            current_words.append(word)
            text = getattr(word, "text", getattr(word, "word", ""))

            # Break on sentence-ending punctuation or max words
            if (
                text.rstrip().endswith((".", "!", "?", "…"))
                or len(current_words) >= max_words_per_segment
            ):
                seg_text = " ".join(
                    getattr(w, "text", getattr(w, "word", "")) for w in current_words
                ).strip()
                if seg_text:
                    seg_start = getattr(current_words[0], "start", 0.0)
                    seg_end = getattr(current_words[-1], "end", 0.0)
                    avg_conf = 0.0
                    confs = [
                        getattr(w, "confidence", getattr(w, "score", 0.0)) for w in current_words
                    ]
                    if confs:
                        avg_conf = sum(c for c in confs if c) / max(len(confs), 1)
                    segments.append(
                        TranscriptSegment(
                            start=seg_start,
                            end=seg_end,
                            text=seg_text,
                            confidence=avg_conf,
                        )
                    )
                current_words = []

        # Flush remaining words
        if current_words:
            seg_text = " ".join(
                getattr(w, "text", getattr(w, "word", "")) for w in current_words
            ).strip()
            if seg_text:
                seg_start = getattr(current_words[0], "start", 0.0)
                seg_end = getattr(current_words[-1], "end", 0.0)
                segments.append(
                    TranscriptSegment(
                        start=seg_start,
                        end=seg_end,
                        text=seg_text,
                        confidence=0.0,
                    )
                )

        return segments

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """Get the duration of an audio file in seconds.

        Tries the ``wave`` module first (for WAV files), then falls
        back to 0.0 if the format is unsupported.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Duration in seconds, or 0.0 if unknown.
        """
        try:
            import wave

            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except Exception:
            pass
        return 0.0
