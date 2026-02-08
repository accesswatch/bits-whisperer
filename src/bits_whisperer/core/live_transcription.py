"""Live microphone transcription service using faster-whisper.

Captures audio from the microphone via ``sounddevice``, buffers it,
and feeds chunks to faster-whisper for real-time speech-to-text.
Runs in a background thread and pushes text updates to the UI via
a callback.

Architecture
------------
1. ``sounddevice.InputStream`` captures audio at 16 kHz mono.
2. Audio chunks are collected in a rolling buffer.
3. When silence (VAD) or a time threshold is reached, the buffer is
   sent to faster-whisper for transcription.
4. The resulting text is pushed to the UI callback.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bits_whisperer.core.settings import LiveTranscriptionSettings
from bits_whisperer.utils.constants import MODELS_DIR

logger = logging.getLogger(__name__)

# Type alias for the callback that receives new transcript text
LiveTextCallback = Callable[[str, bool], None]  # (text, is_final)


@dataclass
class LiveTranscriptionState:
    """Tracks the current state of live transcription."""

    is_running: bool = False
    is_paused: bool = False
    total_segments: int = 0
    total_duration_seconds: float = 0.0
    current_text: str = ""
    full_transcript: list[str] = field(default_factory=list)


class LiveTranscriptionService:
    """Real-time microphone transcription using faster-whisper.

    Usage::

        service = LiveTranscriptionService(settings)
        service.set_text_callback(my_callback)
        service.start()
        # ... user speaks ...
        service.stop()
        full_text = service.get_full_transcript()
    """

    def __init__(self, settings: LiveTranscriptionSettings) -> None:
        """Initialise the live transcription service.

        Args:
            settings: Live transcription configuration.
        """
        self._settings = settings
        self._state = LiveTranscriptionState()
        self._text_callback: LiveTextCallback | None = None
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._worker_thread: threading.Thread | None = None
        self._stream: Any = None  # sounddevice.InputStream
        self._whisper_model: Any = None  # WhisperModel (cached)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_text_callback(self, callback: LiveTextCallback) -> None:
        """Set the callback for receiving transcribed text.

        Args:
            callback: Function(text: str, is_final: bool). Called from
                a background thread — use wx.CallAfter for UI updates.
        """
        self._text_callback = callback

    def start(self) -> None:
        """Start capturing and transcribing from the microphone."""
        if self._state.is_running:
            return

        self._stop_event.clear()
        self._pause_event.set()
        self._state = LiveTranscriptionState(is_running=True)

        # Start the processing worker first
        self._worker_thread = threading.Thread(
            target=self._transcription_worker,
            daemon=True,
            name="live-transcription",
        )
        self._worker_thread.start()

        # Start audio capture
        self._start_audio_stream()
        logger.info("Live transcription started")

    def stop(self) -> None:
        """Stop capturing and transcribing."""
        if not self._state.is_running:
            return

        self._stop_event.set()
        self._pause_event.set()  # Unpause to let worker exit

        # Stop audio stream
        self._stop_audio_stream()

        # Wait for worker to finish
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)

        self._state.is_running = False
        logger.info("Live transcription stopped")

    def pause(self) -> None:
        """Pause live transcription (keeps stream open)."""
        self._pause_event.clear()
        self._state.is_paused = True

    def resume(self) -> None:
        """Resume live transcription after pause."""
        self._pause_event.set()
        self._state.is_paused = False

    @property
    def is_running(self) -> bool:
        """Whether live transcription is currently running."""
        return self._state.is_running

    @property
    def is_paused(self) -> bool:
        """Whether live transcription is paused."""
        return self._state.is_paused

    def get_state(self) -> LiveTranscriptionState:
        """Get the current transcription state."""
        return self._state

    def get_full_transcript(self) -> str:
        """Return the complete transcript so far.

        Returns:
            Full transcript text joined with newlines.
        """
        return "\n".join(self._state.full_transcript)

    @staticmethod
    def list_input_devices() -> list[dict[str, Any]]:
        """List available audio input devices.

        Returns:
            List of dicts with 'index', 'name', 'channels', 'sample_rate'.
        """
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            inputs: list[dict[str, Any]] = []
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    inputs.append(
                        {
                            "index": i,
                            "name": dev["name"],
                            "channels": dev["max_input_channels"],
                            "sample_rate": dev["default_samplerate"],
                        }
                    )
            return inputs
        except Exception as exc:
            logger.warning("Could not list audio devices: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Audio capture                                                        #
    # ------------------------------------------------------------------ #

    def _start_audio_stream(self) -> None:
        """Open a sounddevice InputStream for microphone capture."""
        try:
            import sounddevice as sd

            device = None
            if self._settings.input_device:
                # Try to find the device by name
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    if dev["max_input_channels"] > 0 and self._settings.input_device in dev["name"]:
                        device = i
                        break

            self._stream = sd.InputStream(
                samplerate=self._settings.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self._settings.sample_rate * self._settings.chunk_duration_seconds),
                device=device,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info(
                "Audio stream started (device=%s, rate=%d)",
                device or "default",
                self._settings.sample_rate,
            )
        except ImportError:
            logger.error("sounddevice not installed. Install with: pip install sounddevice")
            self._stop_event.set()
            self._state.is_running = False
        except Exception as exc:
            logger.error("Failed to start audio stream: %s", exc)
            self._stop_event.set()
            self._state.is_running = False

    def _stop_audio_stream(self) -> None:
        """Close the sounddevice InputStream."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("Error closing audio stream: %s", exc)
            self._stream = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """Called by sounddevice for each audio chunk.

        Puts audio data into the processing queue.
        """
        if status:
            logger.debug("Audio stream status: %s", status)
        if not self._stop_event.is_set() and self._pause_event.is_set():
            self._audio_queue.put(indata.copy())

    # ------------------------------------------------------------------ #
    # Transcription worker                                                 #
    # ------------------------------------------------------------------ #

    def _transcription_worker(self) -> None:
        """Background thread that processes audio chunks.

        Collects audio from the queue, checks for speech activity,
        and sends audio to faster-whisper when enough has accumulated.
        """
        try:
            self._load_whisper_model()
        except Exception as exc:
            logger.error("Failed to load Whisper model: %s", exc)
            if self._text_callback:
                self._text_callback(f"[Error loading model: {exc}]", True)
            self._state.is_running = False
            return

        audio_buffer: list[np.ndarray] = []
        buffer_duration = 0.0
        silence_duration = 0.0
        chunk_seconds = self._settings.chunk_duration_seconds
        silence_threshold = self._settings.silence_threshold_seconds

        while not self._stop_event.is_set():
            # Wait if paused
            self._pause_event.wait()

            try:
                chunk = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Check for speech activity (simple energy-based VAD)
            energy = float(np.sqrt(np.mean(chunk**2)))
            is_speech = energy > 0.01  # Threshold for speech detection

            if is_speech:
                audio_buffer.append(chunk)
                buffer_duration += chunk_seconds
                silence_duration = 0.0
            else:
                silence_duration += chunk_seconds
                if audio_buffer:
                    audio_buffer.append(chunk)
                    buffer_duration += chunk_seconds

            # Transcribe when we have enough audio + silence pause,
            # or when buffer exceeds a reasonable max
            should_transcribe = audio_buffer and (
                (silence_duration >= silence_threshold and buffer_duration >= 1.0)
                or buffer_duration >= 30.0  # Max buffer 30 seconds
            )

            if should_transcribe:
                audio_data = np.concatenate(audio_buffer, axis=0)
                audio_buffer.clear()
                buffer_duration = 0.0
                silence_duration = 0.0

                text = self._transcribe_chunk(audio_data)
                if text.strip():
                    with self._lock:
                        self._state.full_transcript.append(text.strip())
                        self._state.total_segments += 1
                        self._state.current_text = text.strip()
                    if self._text_callback:
                        self._text_callback(text.strip(), True)

        # Transcribe any remaining audio in buffer
        if audio_buffer:
            audio_data = np.concatenate(audio_buffer, axis=0)
            text = self._transcribe_chunk(audio_data)
            if text.strip():
                with self._lock:
                    self._state.full_transcript.append(text.strip())
                    self._state.total_segments += 1
                if self._text_callback:
                    self._text_callback(text.strip(), True)

    def _load_whisper_model(self) -> None:
        """Load the faster-whisper model (cached for reuse)."""
        if self._whisper_model is not None:
            return

        from faster_whisper import WhisperModel

        # Determine compute type based on hardware
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

        # Resolve model path
        model_path = self._settings.model
        from bits_whisperer.utils.constants import WHISPER_MODELS

        for m in WHISPER_MODELS:
            if m.id == self._settings.model:
                model_path = m.repo_id or self._settings.model
                break

        logger.info(
            "Loading Whisper model for live transcription: %s (device=%s)",
            model_path,
            device,
        )

        self._whisper_model = WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
            download_root=str(MODELS_DIR),
        )

    def _transcribe_chunk(self, audio_data: np.ndarray) -> str:
        """Transcribe a chunk of audio data.

        Args:
            audio_data: NumPy array of float32 audio samples.

        Returns:
            Transcribed text string.
        """
        if self._whisper_model is None:
            return ""

        try:
            # Flatten to 1-D float32
            audio = audio_data.flatten().astype(np.float32)

            # Skip very short chunks
            min_samples = self._settings.sample_rate  # 1 second minimum
            if len(audio) < min_samples:
                return ""

            lang = None if self._settings.language == "auto" else self._settings.language

            segments_iter, info = self._whisper_model.transcribe(
                audio,
                language=lang,
                beam_size=3,  # Smaller beam for speed
                vad_filter=self._settings.vad_filter,
                without_timestamps=True,
            )

            parts: list[str] = []
            for seg in segments_iter:
                text = seg.text.strip()
                if text:
                    parts.append(text)

            return " ".join(parts)

        except Exception as exc:
            logger.warning("Live transcription chunk failed: %s", exc)
            return ""
