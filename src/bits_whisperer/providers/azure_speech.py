"""Azure Speech Services transcription provider."""

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

logger = logging.getLogger(__name__)


class AzureSpeechProvider(TranscriptionProvider):
    """Cloud transcription via Azure Cognitive Services Speech."""

    RATE_PER_MINUTE: float = 0.017  # USD (standard)

    def __init__(self, region: str = "eastus") -> None:
        self._region = region

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Azure Speech capabilities."""
        return ProviderCapabilities(
            name="Azure Speech Services",
            provider_type="cloud",
            supports_streaming=True,
            supports_timestamps=True,
            supports_diarization=True,
            supports_language_detection=True,
            max_file_size_mb=200,
            supported_languages=["auto"],
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="5 hours/month free. Then ~$0.017/min.",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Azure subscription key with a real API call.

        Creates a short silent audio buffer and sends a recognition request.
        An auth failure raises an error; a "no match" result confirms the key
        is accepted.

        Args:
            api_key: Azure Speech subscription key.

        Returns:
            True if valid.
        """
        try:
            import azure.cognitiveservices.speech as speechsdk

            config = speechsdk.SpeechConfig(subscription=api_key, region=self._region)
            # Send a tiny silent WAV to verify the key is accepted
            import io
            import struct
            import wave

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
            audio_stream = speechsdk.audio.PushAudioInputStream()
            audio_stream.write(buf.getvalue()[44:])  # skip WAV header
            audio_stream.close()
            audio_cfg = speechsdk.audio.AudioConfig(stream=audio_stream)
            recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio_cfg)
            result = recognizer.recognize_once()
            # NoMatch is fine — it means the key worked but audio was silent
            if result.reason in (
                speechsdk.ResultReason.RecognizedSpeech,
                speechsdk.ResultReason.NoMatch,
            ):
                return True
            # Cancelled usually means auth failure
            if result.reason == speechsdk.ResultReason.Canceled:
                details = speechsdk.CancellationDetails(result)
                if details.reason == speechsdk.CancellationReason.Error:
                    logger.debug("Azure key validation failed: %s", details.error_details)
                    return False
            return True
        except Exception:
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate cost.

        Args:
            duration_seconds: Audio length in seconds.

        Returns:
            Estimated cost in USD.
        """
        return (duration_seconds / 60.0) * self.RATE_PER_MINUTE

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        model: str = "",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio via Azure Speech Services.

        When ``include_diarization`` is True, uses the conversation
        transcriber to identify speakers (Speaker 1, Speaker 2, etc.).
        Otherwise uses standard continuous recognition.

        Args:
            audio_path: Path to audio file.
            language: Language code or 'auto'.
            model: Ignored for Azure (uses default model).
            include_timestamps: Include timestamps.
            include_diarization: Enable speaker diarization.
            api_key: Azure subscription key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult.
        """
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise RuntimeError(
                "azure-cognitiveservices-speech not installed. "
                "pip install azure-cognitiveservices-speech"
            ) from None

        if not api_key:
            raise RuntimeError("Azure Speech subscription key is required.")

        if progress_callback:
            progress_callback(10.0)

        logger.info("Starting Azure Speech transcription: %s", Path(audio_path).name)

        speech_config = speechsdk.SpeechConfig(subscription=api_key, region=self._region)

        if language and language != "auto":
            speech_config.speech_recognition_language = language
        else:
            speech_config.speech_recognition_language = "en-US"

        # Request word-level timing for better diarization alignment
        speech_config.request_word_level_timestamps()

        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)

        if progress_callback:
            progress_callback(20.0)

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []
        done = False
        cancel_error: str | None = None
        speaker_map: dict[str, str] = {}

        if include_diarization:
            # Use conversation transcriber for speaker identification
            conversation_config = speechsdk.SpeechConfig(
                subscription=api_key,
                region=self._region,
            )
            if language and language != "auto":
                conversation_config.speech_recognition_language = language
            else:
                conversation_config.speech_recognition_language = "en-US"
            conversation_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_DiarizeIntermediateResults,
                "true",
            )
            audio_cfg = speechsdk.audio.AudioConfig(filename=audio_path)
            transcriber = speechsdk.transcription.ConversationTranscriber(
                speech_config=conversation_config,
                audio_config=audio_cfg,
            )

            def on_transcribed(evt) -> None:
                result = evt.result
                if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    offset_s = result.offset / 10_000_000
                    duration_s = result.duration / 10_000_000
                    speaker_id = getattr(result, "speaker_id", "") or ""
                    if speaker_id and speaker_id not in speaker_map:
                        n = len(speaker_map) + 1
                        speaker_map[speaker_id] = f"Speaker {n}"
                    display_speaker = speaker_map.get(speaker_id, speaker_id)
                    segments.append(
                        TranscriptSegment(
                            start=offset_s,
                            end=offset_s + duration_s,
                            text=result.text.strip(),
                            speaker=display_speaker,
                        )
                    )
                    full_text_parts.append(result.text.strip())

            def on_session_stopped_ct(evt) -> None:
                nonlocal done
                done = True

            def on_canceled_ct(evt) -> None:
                nonlocal done, cancel_error
                cancellation = speechsdk.CancellationDetails(evt.result)
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    cancel_error = (
                        f"Azure Speech cancelled with error: " f"{cancellation.error_details}"
                    )
                    logger.error(cancel_error)
                done = True

            transcriber.transcribed.connect(on_transcribed)
            transcriber.session_stopped.connect(on_session_stopped_ct)
            transcriber.canceled.connect(on_canceled_ct)

            transcriber.start_transcribing_async().get()
        else:
            # Standard continuous recognition (no diarization)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config
            )

            def on_recognized(evt) -> None:
                result = evt.result
                if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    offset_s = result.offset / 10_000_000
                    duration_s = result.duration / 10_000_000
                    segments.append(
                        TranscriptSegment(
                            start=offset_s,
                            end=offset_s + duration_s,
                            text=result.text.strip(),
                        )
                    )
                    full_text_parts.append(result.text.strip())

            def on_session_stopped(evt) -> None:
                nonlocal done
                done = True

            def on_canceled(evt) -> None:
                nonlocal done, cancel_error
                cancellation = speechsdk.CancellationDetails(evt.result)
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    cancel_error = (
                        f"Azure Speech cancelled with error: " f"{cancellation.error_details}"
                    )
                    logger.error(cancel_error)
                else:
                    logger.info("Azure Speech cancelled: %s", cancellation.reason)
                done = True

            recognizer.recognized.connect(on_recognized)
            recognizer.session_stopped.connect(on_session_stopped)
            recognizer.canceled.connect(on_canceled)

            recognizer.start_continuous_recognition()

        import time

        _MAX_WAIT_SECS = 1800  # 30-minute safety timeout
        _elapsed = 0.0
        while not done:
            time.sleep(0.5)
            _elapsed += 0.5
            if progress_callback:
                progress_callback(min(90.0, 20.0 + len(segments) * 2))
            if _elapsed >= _MAX_WAIT_SECS:
                logger.error("Azure Speech recognition timed out after %ds", _MAX_WAIT_SECS)
                break

        if include_diarization:
            transcriber.stop_transcribing_async().get()
        else:
            recognizer.stop_continuous_recognition()

        if cancel_error:
            raise RuntimeError(cancel_error)

        if _elapsed >= _MAX_WAIT_SECS and not segments:
            raise RuntimeError(
                "Azure Speech recognition timed out with no results. "
                "Check your audio file and API key."
            )

        if progress_callback:
            progress_callback(100.0)

        duration = segments[-1].end if segments else 0.0

        result = TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="azure_speech",
            model="azure-default",
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )
        if speaker_map:
            result.speaker_map = {v: v for v in speaker_map.values()}
        return result
