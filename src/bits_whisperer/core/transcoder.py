"""Audio transcoding via ffmpeg — normalize audio for transcription."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from bits_whisperer.utils.constants import (
    TRANSCODE_CHANNELS,
    TRANSCODE_SAMPLE_RATE,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], None]  # 0.0 – 100.0


class TranscoderError(Exception):
    """Raised when transcoding fails."""


class Transcoder:
    """Transcode audio files to a Whisper-friendly format using ffmpeg."""

    def __init__(self) -> None:
        self._ffmpeg_path: str = self._find_ffmpeg()

    def is_available(self) -> bool:
        """Check whether ffmpeg is installed and accessible."""
        return bool(self._ffmpeg_path)

    def get_duration(self, file_path: str | Path) -> float:
        """Get the duration of an audio file in seconds.

        Args:
            file_path: Path to the audio file.

        Returns:
            Duration in seconds.

        Raises:
            TranscoderError: If ffprobe fails.
        """
        try:
            result = subprocess.run(
                [
                    self._ffmpeg_path.replace("ffmpeg", "ffprobe"),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return float(result.stdout.strip())
        except Exception as exc:
            raise TranscoderError(f"Failed to get duration: {exc}") from exc

    def transcode(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        sample_rate: int = TRANSCODE_SAMPLE_RATE,
        channels: int = TRANSCODE_CHANNELS,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        """Transcode an audio file to PCM16 WAV for Whisper.

        Args:
            input_path: Source audio file.
            output_path: Destination path. If None, creates a temp file.
            sample_rate: Target sample rate (default 16000).
            channels: Target channel count (default 1 = mono).
            progress_callback: Optional callback receiving progress 0–100.

        Returns:
            Path to the transcoded WAV file.

        Raises:
            TranscoderError: On ffmpeg failure.
        """
        input_path = Path(input_path)
        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".wav"))
        else:
            output_path = Path(output_path)

        if not input_path.exists():
            raise TranscoderError(f"Input file not found: {input_path}")

        cmd = [
            self._ffmpeg_path,
            "-i",
            str(input_path),
            "-vn",  # no video
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-af",
            "loudnorm=I=-16:TP=-3:LRA=11",  # normalize audio levels
            "-y",  # overwrite
            "-progress",
            "pipe:1",
            str(output_path),
        ]

        logger.info("Transcoding: %s to %s", input_path.name, output_path.name)

        try:
            duration = self.get_duration(input_path)
        except TranscoderError:
            duration = 0.0

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if process.stdout and duration > 0 and progress_callback:
                for line in process.stdout:
                    if line.startswith("out_time_us="):
                        try:
                            time_us = int(line.split("=")[1].strip())
                            pct = min(100.0, (time_us / 1_000_000) / duration * 100)
                            progress_callback(pct)
                        except (ValueError, ZeroDivisionError):
                            pass

            process.wait(timeout=600)

            if process.returncode != 0:
                stderr = process.stderr.read() if process.stderr else ""
                raise TranscoderError(f"ffmpeg exited with code {process.returncode}: {stderr}")

        except subprocess.TimeoutExpired:
            process.kill()
            raise TranscoderError("Transcoding timed out (10 minutes)") from None
        except FileNotFoundError:
            raise TranscoderError(
                "ffmpeg not found. Please install ffmpeg and ensure it is on your PATH."
            ) from None

        if progress_callback:
            progress_callback(100.0)

        logger.info("Transcoding complete: %s", output_path.name)
        return output_path

    def _find_ffmpeg(self) -> str:
        """Locate the ffmpeg executable.

        Returns:
            Path to ffmpeg, or empty string if not found.
        """
        path = shutil.which("ffmpeg")
        if path:
            return path
        # Check common Windows locations
        for candidate in [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]:
            if Path(candidate).exists():
                return candidate
        logger.warning("ffmpeg not found on PATH")
        return ""
