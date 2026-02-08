"""Audio preprocessor for improving transcription accuracy.

Applies a chain of ffmpeg audio filters *before* transcoding to
clean up the signal for speech recognition. All processing is done
via ffmpeg subprocesses — no extra native libraries required.

Filter chain (configurable):
1. **High-pass filter** — removes low-frequency rumble (< 80 Hz).
2. **Low-pass filter** — removes ultrasonic noise (> 8 kHz by default,
   preserving the speech band).
3. **Noise gate** — silences sections below a threshold (reduces hiss).
4. **De-essing** — attenuates sibilance (3–10 kHz).
5. **Dynamic range compression** — evens out loudness differences.
6. **Loudnorm** — EBU R128 loudness normalisation (already in transcoder,
   but can be run beforehand for two-pass accuracy).
7. **Silence trimming** — removes leading/trailing silence.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PreprocessorSettings:
    """User-configurable audio preprocessing options."""

    enabled: bool = True

    # High-pass filter to remove rumble
    highpass_enabled: bool = True
    highpass_freq: int = 80  # Hz

    # Low-pass filter to remove high-frequency noise
    lowpass_enabled: bool = True
    lowpass_freq: int = 8000  # Hz

    # Noise gate
    noise_gate_enabled: bool = True
    noise_gate_threshold_db: float = -40.0  # dB below which audio is silenced

    # De-esser (band-specific compressor)
    deesser_enabled: bool = False
    deesser_freq: int = 5000  # centre frequency in Hz

    # Dynamic range compressor
    compressor_enabled: bool = True
    compressor_threshold_db: float = -20.0
    compressor_ratio: float = 4.0
    compressor_attack_ms: float = 5.0
    compressor_release_ms: float = 50.0

    # Loudnorm (EBU R128)
    loudnorm_enabled: bool = True
    loudnorm_target_i: float = -16.0
    loudnorm_target_tp: float = -3.0
    loudnorm_target_lra: float = 11.0

    # Silence trimming
    trim_silence_enabled: bool = True
    silence_threshold_db: float = -40.0
    silence_duration_s: float = 1.0  # min silence length to trim


class AudioPreprocessor:
    """Apply an ffmpeg filter chain to improve audio for transcription.

    Usage::

        preprocessor = AudioPreprocessor()
        cleaned = preprocessor.process("noisy_meeting.mp3")
        # cleaned is a temporary WAV path ready for the transcoder
    """

    def __init__(self, settings: PreprocessorSettings | None = None) -> None:
        """Initialise with optional settings."""
        self._settings = settings or PreprocessorSettings()
        self._ffmpeg = self._find_ffmpeg()

    @property
    def settings(self) -> PreprocessorSettings:
        """Current preprocessing settings."""
        return self._settings

    @settings.setter
    def settings(self, value: PreprocessorSettings) -> None:
        self._settings = value

    def is_available(self) -> bool:
        """Return True if ffmpeg is found on PATH."""
        return bool(self._ffmpeg)

    def process(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
    ) -> Path:
        """Apply the configured filter chain to *input_path*.

        Args:
            input_path: Source audio file.
            output_path: Destination. If ``None``, a temp file is created.

        Returns:
            Path to the preprocessed audio file.

        Raises:
            RuntimeError: If ffmpeg is unavailable or the command fails.
        """
        if not self._ffmpeg:
            raise RuntimeError("ffmpeg not found. Install ffmpeg and add it to your PATH.")

        s = self._settings
        if not s.enabled:
            return Path(input_path)

        input_path = Path(input_path)
        if output_path is None:
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            output_path = Path(tmp)
        else:
            output_path = Path(output_path)

        filters = self._build_filter_chain()
        if not filters:
            # Nothing to do — copy input as-is
            return Path(input_path)

        af_chain = ",".join(filters)

        cmd = [
            self._ffmpeg,
            "-i",
            str(input_path),
            "-vn",
            "-af",
            af_chain,
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            str(output_path),
        ]

        logger.info("Preprocessing audio: %s (filters: %s)", input_path.name, af_chain)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.error("Preprocessor ffmpeg stderr: %s", result.stderr)
                raise RuntimeError(
                    f"Audio preprocessing failed (exit {result.returncode}): "
                    f"{result.stderr[:500]}"
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio preprocessing timed out (10 minutes)") from None

        logger.info("Preprocessing complete: %s", output_path.name)
        return output_path

    # ------------------------------------------------------------------ #
    # Filter chain construction                                            #
    # ------------------------------------------------------------------ #

    def _build_filter_chain(self) -> list[str]:
        """Build the ffmpeg ``-af`` filter list from current settings."""
        s = self._settings
        filters: list[str] = []

        if s.highpass_enabled:
            filters.append(f"highpass=f={s.highpass_freq}")

        if s.lowpass_enabled:
            filters.append(f"lowpass=f={s.lowpass_freq}")

        if s.noise_gate_enabled:
            # agate: threshold in dB, ratio high = hard gate
            filters.append(
                f"agate=threshold={s.noise_gate_threshold_db}dB" f":ratio=10:attack=5:release=50"
            )

        if s.deesser_enabled:
            # Band-split approach: isolate sibilant band, compress, remix
            filters.append(f"equalizer=f={s.deesser_freq}:t=q:w=2:g=-6")

        if s.compressor_enabled:
            filters.append(
                f"acompressor="
                f"threshold={s.compressor_threshold_db}dB:"
                f"ratio={s.compressor_ratio}:"
                f"attack={s.compressor_attack_ms}:"
                f"release={s.compressor_release_ms}"
            )

        if s.loudnorm_enabled:
            filters.append(
                f"loudnorm="
                f"I={s.loudnorm_target_i}:"
                f"TP={s.loudnorm_target_tp}:"
                f"LRA={s.loudnorm_target_lra}"
            )

        if s.trim_silence_enabled:
            # silenceremove: remove leading silence
            filters.append(
                f"silenceremove=start_periods=1:"
                f"start_duration=0.1:"
                f"start_threshold={s.silence_threshold_db}dB,"
                f"areverse,"
                f"silenceremove=start_periods=1:"
                f"start_duration=0.1:"
                f"start_threshold={s.silence_threshold_db}dB,"
                f"areverse"
            )

        return filters

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_ffmpeg() -> str:
        """Locate the ffmpeg executable."""
        path = shutil.which("ffmpeg")
        if path:
            return path
        for candidate in [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]:
            if Path(candidate).exists():
                return candidate
        return ""
