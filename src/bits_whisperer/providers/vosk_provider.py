"""Vosk offline transcription provider (Kaldi-based).

Vosk is a lightweight, open-source speech recognition toolkit that runs
entirely on-device. It supports 20+ languages with small models (40-50 MB)
that work on low-end hardware, and larger models (1-2 GB) for higher accuracy.

Models are downloaded automatically from https://alphacephei.com/vosk/models
on first use and cached locally.
"""

from __future__ import annotations

import json
import logging
import wave
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)
from bits_whisperer.utils.constants import (
    VOSK_MODEL_URL_BASE,
    VOSK_MODELS,
    VOSK_MODELS_DIR,
    get_vosk_model_by_id,
)

logger = logging.getLogger(__name__)


def _download_vosk_model(download_name: str, target_dir: Path) -> Path:
    """Download and extract a Vosk model if not already cached.

    Args:
        download_name: The model directory name (e.g. 'vosk-model-small-en-us-0.15').
        target_dir: Parent directory to extract into.

    Returns:
        Path to the extracted model directory.

    Raises:
        RuntimeError: If download or extraction fails.
    """
    model_path = target_dir / download_name
    if model_path.exists() and (model_path / "conf").exists():
        logger.debug("Vosk model already cached: %s", model_path)
        return model_path

    url = f"{VOSK_MODEL_URL_BASE}/{download_name}.zip"
    zip_path = target_dir / f"{download_name}.zip"

    logger.info("Downloading Vosk model: %s", url)
    try:
        req = Request(url, headers={"User-Agent": "BITS-Whisperer/1.1"})
        with urlopen(req, timeout=300) as resp, open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as exc:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to download Vosk model '{download_name}'. "
            f"Check your internet connection and try again.\n\n"
            f"Error: {exc}"
        ) from exc

    logger.info("Extracting Vosk model: %s", zip_path.name)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
    except Exception as exc:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to extract Vosk model '{download_name}'.\n\n" f"Error: {exc}"
        ) from exc
    finally:
        zip_path.unlink(missing_ok=True)

    if not model_path.exists():
        raise RuntimeError(
            f"Vosk model extracted but directory '{download_name}' not found. "
            f"The archive may have a different structure."
        )

    logger.info("Vosk model ready: %s", model_path)
    return model_path


class VoskProvider(TranscriptionProvider):
    """On-device transcription using Vosk (Kaldi-based).

    Vosk provides lightweight, CPU-friendly speech recognition with
    support for 20+ languages. Models range from 30 MB (small) to
    1.8 GB (large, high-accuracy).
    """

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for Vosk inference."""
        return ProviderCapabilities(
            name="Vosk",
            provider_type="local",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=False,
            max_file_size_mb=500,
            supported_languages=[m.language for m in VOSK_MODELS],
            rate_per_minute_usd=0.0,
            free_tier_description=(
                "Free forever. Lightweight offline recognition "
                "using Kaldi. Works on low-end hardware."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Local provider doesn't need API keys -- always valid."""
        return True

    def estimate_cost(self, duration_seconds: float) -> float:
        """Local inference is free."""
        return 0.0

    def transcribe(
        self,
        audio_path: str,
        language: str = "en-us",
        model: str = "vosk-small-en",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using Vosk locally.

        Args:
            audio_path: Path to the audio file (WAV 16kHz mono preferred).
            language: Language code (used to select model if model not set).
            model: Vosk model ID (e.g. 'vosk-small-en').
            include_timestamps: Whether to include word timestamps.
            include_diarization: Ignored for Vosk.
            api_key: Ignored for local provider.
            progress_callback: Optional progress callback (0-100).

        Returns:
            TranscriptionResult with segments and full text.
        """
        try:
            import vosk
        except ImportError:
            from bits_whisperer.core.sdk_installer import is_frozen

            if is_frozen():
                raise RuntimeError(
                    "The Vosk speech engine is not installed.\n\n"
                    "Go to Settings, then Providers, then Vosk and click "
                    "'Install SDK' to download it automatically."
                ) from None
            raise RuntimeError(
                "vosk is not installed. " "Install it with: pip install vosk"
            ) from None

        # Resolve model info
        model_info = get_vosk_model_by_id(model)
        if model_info is None:
            # Fall back to first model matching the language
            for m in VOSK_MODELS:
                if m.language == language:
                    model_info = m
                    break
        if model_info is None:
            # Default to English small
            model_info = VOSK_MODELS[0]

        logger.info(
            "Starting Vosk transcription: model=%s, language=%s, file=%s",
            model_info.id,
            model_info.language,
            Path(audio_path).name,
        )

        if progress_callback:
            progress_callback(2.0)

        # Download model if needed
        model_path = _download_vosk_model(model_info.download_name, VOSK_MODELS_DIR)

        if progress_callback:
            progress_callback(10.0)

        # Suppress Vosk's default logging
        vosk.SetLogLevel(-1)

        vosk_model = vosk.Model(str(model_path))

        if progress_callback:
            progress_callback(15.0)

        # Open the WAV file (must be 16kHz mono PCM from transcoder)
        try:
            wf = wave.open(audio_path, "rb")  # noqa: SIM115
        except Exception as exc:
            raise RuntimeError(
                f"Failed to open audio file for Vosk: {Path(audio_path).name}\n\n"
                f"Vosk requires WAV format (16kHz, mono, 16-bit PCM). "
                f"Ensure the file was transcoded correctly.\n\n"
                f"Error: {exc}"
            ) from exc

        try:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            duration = n_frames / sample_rate if sample_rate > 0 else 0.0

            rec = vosk.KaldiRecognizer(vosk_model, sample_rate)
            rec.SetWords(include_timestamps)

            segments: list[TranscriptSegment] = []
            full_text_parts: list[str] = []
            frames_read = 0
            chunk_size = 4000  # frames per read

            while True:
                data = wf.readframes(chunk_size)
                if len(data) == 0:
                    break

                frames_read += chunk_size

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        full_text_parts.append(text)
                        # Extract word-level timestamps if available
                        words = result.get("result", [])
                        if words and include_timestamps:
                            seg_start = words[0].get("start", 0.0)
                            seg_end = words[-1].get("end", 0.0)
                            avg_conf = (
                                sum(w.get("conf", 0.0) for w in words) / len(words)
                                if words
                                else 0.0
                            )
                            segments.append(
                                TranscriptSegment(
                                    start=seg_start,
                                    end=seg_end,
                                    text=text,
                                    confidence=avg_conf,
                                )
                            )
                        else:
                            segments.append(
                                TranscriptSegment(
                                    start=0.0,
                                    end=0.0,
                                    text=text,
                                    confidence=0.0,
                                )
                            )

                if progress_callback and duration > 0:
                    elapsed = frames_read / sample_rate
                    pct = 15.0 + (elapsed / duration) * 80.0
                    progress_callback(min(95.0, pct))

            # Process final result
            final = json.loads(rec.FinalResult())
            final_text = final.get("text", "").strip()
            if final_text:
                full_text_parts.append(final_text)
                words = final.get("result", [])
                if words and include_timestamps:
                    seg_start = words[0].get("start", 0.0)
                    seg_end = words[-1].get("end", 0.0)
                    avg_conf = sum(w.get("conf", 0.0) for w in words) / len(words) if words else 0.0
                    segments.append(
                        TranscriptSegment(
                            start=seg_start,
                            end=seg_end,
                            text=final_text,
                            confidence=avg_conf,
                        )
                    )
                else:
                    segments.append(
                        TranscriptSegment(
                            start=0.0,
                            end=0.0,
                            text=final_text,
                            confidence=0.0,
                        )
                    )
        finally:
            wf.close()

        if progress_callback:
            progress_callback(100.0)

        result = TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="vosk",
            model=model_info.id,
            language=model_info.language,
            duration_seconds=duration,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )

        logger.info(
            "Vosk transcription complete: %d segments, %.1fs, model=%s",
            len(segments),
            duration,
            model_info.id,
        )
        return result
