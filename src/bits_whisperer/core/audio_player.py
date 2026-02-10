"""Cross-platform audio playback with pitch-preserving speed control."""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, float], None]
StateCallback = Callable[[str], None]


class AudioPlayerError(Exception):
    """Raised when audio playback fails."""


class AudioPlayer:
    """Simple ffmpeg-backed audio player with pitch-preserving speed.

    This player uses ffmpeg to decode audio to raw PCM and streams it
    to the default output device via sounddevice.
    """

    def __init__(
        self,
        sample_rate: int | None = None,
        channels: int = 2,
    ) -> None:
        """Initialise the audio player with optional output settings."""
        self._ffmpeg = self._find_ffmpeg()
        self._sample_rate = sample_rate or self._get_default_sample_rate()
        self._channels = channels
        self._file_path: Path | None = None
        self._duration: float = 0.0
        self._selection_start: float = 0.0
        self._selection_end: float | None = None
        self._position: float = 0.0
        self._speed: float = 1.0
        self._progress_cb: ProgressCallback | None = None
        self._state_cb: StateCallback | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._stop_event = threading.Event()

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Register a progress callback.

        Args:
            callback: Called with (position_seconds, duration_seconds).
        """
        self._progress_cb = callback

    def set_state_callback(self, callback: StateCallback | None) -> None:
        """Register a state callback.

        Args:
            callback: Called with a state string
                (playing, paused, stopped, finished).
        """
        self._state_cb = callback

    def load(
        self,
        file_path: str | Path,
        *,
        selection_start: float | None = None,
        selection_end: float | None = None,
    ) -> None:
        """Load a new audio file and optional selection range.

        Args:
            file_path: Path to the audio file.
            selection_start: Optional start time (seconds).
            selection_end: Optional end time (seconds).
        """
        path = Path(file_path)
        if not path.exists():
            raise AudioPlayerError(f"Audio file not found: {path}")

        self._file_path = path
        self._duration = self._probe_duration(path)

        start = max(0.0, selection_start or 0.0)
        end = selection_end if selection_end and selection_end > 0 else None
        if end is not None and end <= start:
            end = None

        self._selection_start = start
        self._selection_end = end
        self._position = start

    def set_clip_range(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        """Update the current selection range.

        Args:
            start_seconds: Start time in seconds.
            end_seconds: End time in seconds.
        """
        start = max(0.0, start_seconds or 0.0)
        end = end_seconds if end_seconds and end_seconds > 0 else None
        if end is not None and end <= start:
            end = None

        with self._lock:
            self._selection_start = start
            self._selection_end = end
            self._position = min(
                max(self._position, start),
                end or self._duration,
            )

    def set_speed(self, speed: float) -> None:
        """Set playback speed (pitch-preserving).

        Args:
            speed: Playback speed multiplier.
        """
        speed = max(0.25, min(speed, 8.0))
        restart = self.is_playing
        with self._lock:
            self._speed = speed
        if restart:
            self._restart_at_current_position()

    def seek(self, position_seconds: float) -> None:
        """Seek to a specific position within the file.

        Args:
            position_seconds: Target position in seconds.
        """
        with self._lock:
            pos = max(self._selection_start, position_seconds)
            if self._selection_end is not None:
                pos = min(pos, self._selection_end)
            self._position = pos
        if self.is_playing:
            self._restart_at_current_position()

    @property
    def duration(self) -> float:
        """Total duration of the loaded audio file in seconds."""
        return self._duration

    @property
    def position(self) -> float:
        """Current playback position in seconds (source time)."""
        with self._lock:
            return self._position

    @property
    def speed(self) -> float:
        """Current playback speed multiplier."""
        with self._lock:
            return self._speed

    @property
    def is_playing(self) -> bool:
        """Return True if playback is active."""
        return self._thread is not None and self._thread.is_alive()

    def play(self) -> None:
        """Start playback from the current position."""
        if not self._file_path:
            raise AudioPlayerError("No audio file loaded")
        if not self._ffmpeg:
            raise AudioPlayerError("ffmpeg not found. Install ffmpeg and add it to PATH.")
        if importlib.util.find_spec("sounddevice") is None:
            raise AudioPlayerError(
                "sounddevice is not installed. " "Install the audio playback dependency."
            )
        if self.is_playing:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._playback_loop,
            daemon=True,
        )
        self._thread.start()
        self._fire_state("playing")

    def pause(self) -> None:
        """Pause playback, keeping the current position."""
        if not self.is_playing:
            return
        self._stop_playback(reset_position=False)
        self._fire_state("paused")

    def stop(self) -> None:
        """Stop playback and reset position to the selection start."""
        if self.is_playing:
            self._stop_playback(reset_position=True)
        else:
            with self._lock:
                self._position = self._selection_start
        self._fire_state("stopped")

    def close(self) -> None:
        """Stop playback and release resources."""
        self._stop_playback(reset_position=False)

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _restart_at_current_position(self) -> None:
        with self._lock:
            pos = self._position
        self._stop_playback(reset_position=False)
        with self._lock:
            self._position = pos
        self.play()

    def _stop_playback(self, *, reset_position: bool) -> None:
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            with contextlib.suppress(Exception):
                self._process.kill()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        self._process = None
        if reset_position:
            with self._lock:
                self._position = self._selection_start

    def _playback_loop(self) -> None:
        import sounddevice as sd

        if not self._file_path:
            return

        with self._lock:
            start_pos = self._position
            speed = self._speed
            sel_end = self._selection_end

        cmd = self._build_ffmpeg_cmd(
            self._file_path,
            start_pos,
            sel_end,
            speed,
        )

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except Exception as exc:
            logger.error("Failed to start ffmpeg: %s", exc)
            self._fire_state("stopped")
            return

        bytes_per_frame = self._channels * 2
        chunk_frames = int(self._sample_rate * 0.05)
        chunk_bytes = chunk_frames * bytes_per_frame

        last_update = time.monotonic()

        try:
            with sd.RawOutputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
            ) as stream:
                while not self._stop_event.is_set():
                    if not self._process or not self._process.stdout:
                        break
                    data = self._process.stdout.read(chunk_bytes)
                    if not data:
                        break

                    stream.write(data)
                    frames = len(data) // bytes_per_frame

                    with self._lock:
                        self._position += (frames / self._sample_rate) * speed
                        if sel_end is not None:
                            self._position = min(self._position, sel_end)

                    now = time.monotonic()
                    if self._progress_cb and now - last_update >= 0.1:
                        self._progress_cb(self.position, self._duration)
                        last_update = now
        except Exception as exc:
            logger.debug("Playback loop error: %s", exc)
        finally:
            if self._process and self._process.poll() is None:
                with contextlib.suppress(Exception):
                    self._process.kill()
            self._process = None

        if not self._stop_event.is_set():
            self._fire_state("finished")

    def _build_ffmpeg_cmd(
        self,
        file_path: Path,
        start_seconds: float,
        end_seconds: float | None,
        speed: float,
    ) -> list[str]:
        cmd = [
            self._ffmpeg,
            "-loglevel",
            "error",
            "-ss",
            f"{start_seconds}",
            "-i",
            str(file_path),
        ]
        if end_seconds is not None and end_seconds > 0:
            cmd.extend(["-to", f"{end_seconds}"])

        atempo = self._build_atempo_chain(speed)
        if atempo:
            cmd.extend(["-filter:a", atempo])

        cmd.extend(
            [
                "-vn",
                "-ac",
                str(self._channels),
                "-ar",
                str(self._sample_rate),
                "-f",
                "s16le",
                "pipe:1",
            ]
        )
        return cmd

    @staticmethod
    def _build_atempo_chain(speed: float) -> str:
        if abs(speed - 1.0) < 0.001:
            return ""

        factors: list[float] = []
        remaining = speed

        while remaining > 2.0:
            factors.append(2.0)
            remaining /= 2.0

        while remaining < 0.5:
            factors.append(0.5)
            remaining /= 0.5

        if abs(remaining - 1.0) > 0.001:
            factors.append(remaining)

        return ",".join(f"atempo={f:.3f}" for f in factors)

    def _probe_duration(self, file_path: Path) -> float:
        if not self._ffmpeg:
            return 0.0

        ffprobe = self._ffmpeg.replace("ffmpeg", "ffprobe")
        if not Path(ffprobe).exists():
            ffprobe = shutil.which("ffprobe") or ""

        if not ffprobe:
            return 0.0

        try:
            result = subprocess.run(
                [
                    ffprobe,
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
                timeout=15,
                check=False,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def _find_ffmpeg() -> str:
        path = shutil.which("ffmpeg")
        if path:
            return path
        for candidate in [
            r"C:\\ffmpeg\\bin\\ffmpeg.exe",
            r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        ]:
            if Path(candidate).exists():
                return candidate
        return ""

    @staticmethod
    def _get_default_sample_rate() -> int:
        try:
            import sounddevice as sd

            dev = sd.query_devices(None, "output")
            sr = int(dev.get("default_samplerate", 0))
            if sr > 0:
                return sr
        except Exception:
            pass
        return 48000

    def _fire_state(self, state: str) -> None:
        if self._state_cb:
            self._state_cb(state)
