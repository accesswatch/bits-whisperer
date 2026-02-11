"""Azure Embedded (offline) speech recognition provider.

Uses the Azure Speech SDK's **embedded speech** feature to run Microsoft's
neural speech-to-text models entirely on-device — no internet connection
and no API key required after the model is downloaded.

This is distinct from the cloud ``AzureSpeechProvider`` which sends audio
to Azure servers. Embedded models are downloaded once (~200 MB per language)
and then run locally with near-cloud-quality accuracy.

Requirements
------------
- ``azure-cognitiveservices-speech >= 1.32.0`` (embedded support)
- Windows 10/11, x64
- Downloaded embedded model files (managed via the Model Manager dialog)

See: https://learn.microsoft.com/azure/ai-services/
    speech-service/embedded-speech
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
from bits_whisperer.utils.constants import DATA_DIR

logger = logging.getLogger(__name__)

# Default path for embedded speech models
EMBEDDED_MODELS_DIR = DATA_DIR / "azure_embedded_models"


class AzureEmbeddedSpeechProvider(TranscriptionProvider):
    """Offline transcription using Azure Speech SDK embedded models.

    Runs Microsoft's neural speech-to-text engine entirely on-device.
    Models must be downloaded first, but after that no internet or API
    key is needed.
    """

    def __init__(self, models_dir: str | Path | None = None) -> None:
        """Initialise with an optional custom models directory."""
        self._models_dir = Path(models_dir or EMBEDDED_MODELS_DIR)
        self._models_dir.mkdir(parents=True, exist_ok=True)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Azure Embedded Speech capabilities."""
        return ProviderCapabilities(
            name="Microsoft Embedded Speech (Offline)",
            provider_type="local",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=False,
            max_file_size_mb=500,
            supported_languages=[
                "en-US",
                "en-GB",
                "es-ES",
                "es-MX",
                "fr-FR",
                "de-DE",
                "it-IT",
                "pt-BR",
                "ja-JP",
                "zh-CN",
                "ko-KR",
                "ar-SA",
                "hi-IN",
                "ru-RU",
            ],
            rate_per_minute_usd=0.0,
            free_tier_description=(
                "Free — runs Microsoft's neural speech "
                "model on your computer. Download language "
                "models (~200 MB each) once, then "
                "transcribe offline with no API key."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        """No key needed for embedded speech."""
        return True

    def estimate_cost(self, duration_seconds: float) -> float:
        """Return zero — embedded models are free."""
        return 0.0

    def transcribe(
        self,
        audio_path: str,
        language: str = "en-US",
        model: str = "",
        include_timestamps: bool = True,
        include_diarization: bool = False,
        api_key: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using Azure embedded speech models.

        Args:
            audio_path: Path to audio file.
            language: BCP-47 language tag (e.g. ``"en-US"``).
            model: Specific model name, or auto-detect from language.
            include_timestamps: Include per-phrase timestamps.
            include_diarization: Ignored for embedded models.
            api_key: Ignored — no key needed.
            progress_callback: Optional progress callback (0–100).

        Returns:
            TranscriptionResult.
        """
        try:
            import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError(
                "azure-cognitiveservices-speech not installed. "
                "pip install azure-cognitiveservices-speech"
            ) from None

        if language == "auto":
            language = "en-US"

        if progress_callback:
            progress_callback(5.0)

        # Find the embedded model for the requested language
        model_path = self._find_model(language, model)

        logger.info(
            "Azure embedded: lang=%s model=%s file=%s",
            language,
            model_path,
            Path(audio_path).name,
        )

        # Configure embedded speech
        speech_config = speechsdk.EmbeddedSpeechConfig(  # type: ignore[attr-defined]
            path=str(model_path)
        )
        speech_config.speech_recognition_language = language

        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        if progress_callback:
            progress_callback(15.0)

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []
        done = False

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
                if progress_callback:
                    progress_callback(min(90.0, 15.0 + len(segments) * 2))

        def on_session_stopped(evt) -> None:
            nonlocal done
            done = True

        cancel_error: str | None = None

        def on_canceled(evt) -> None:
            nonlocal done, cancel_error
            if evt.result.reason == speechsdk.ResultReason.Canceled:
                cancellation = speechsdk.CancellationDetails(evt.result)
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    cancel_error = f"Embedded recognition error: " f"{cancellation.error_details}"
                    logger.error(cancel_error)
                else:
                    logger.warning(
                        "Recognition cancelled: %s",
                        cancellation.reason,
                    )
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
            if _elapsed >= _MAX_WAIT_SECS:
                logger.error("Embedded recognition timed out after %ds", _MAX_WAIT_SECS)
                break

        recognizer.stop_continuous_recognition()

        if cancel_error:
            raise RuntimeError(cancel_error)

        if _elapsed >= _MAX_WAIT_SECS and not segments:
            raise RuntimeError(
                "Azure Embedded recognition timed out with no results. "
                "Check your audio file and installed models."
            )

        if progress_callback:
            progress_callback(100.0)

        duration = segments[-1].end if segments else 0.0

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="azure_embedded",
            model=f"embedded-{language}",
            language=language,
            duration_seconds=duration,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )

    # ------------------------------------------------------------------ #
    # Model management                                                     #
    # ------------------------------------------------------------------ #

    def _find_model(self, language: str, model_hint: str = "") -> Path:
        """Locate the embedded model directory for a language.

        Args:
            language: BCP-47 tag like ``"en-US"``.
            model_hint: Optional specific model directory name.

        Returns:
            Path to the model directory.

        Raises:
            RuntimeError: If no model is found.
        """
        if model_hint:
            candidate = self._models_dir / model_hint
            if candidate.is_dir():
                return candidate

        # Search for a model matching the language
        for sub in sorted(self._models_dir.iterdir()):
            lang_norm = language.lower().replace("-", "")
            if sub.is_dir() and lang_norm in sub.name.lower().replace("-", ""):
                return sub

        raise RuntimeError(
            f"No embedded speech model found for '{language}'.\n\n"
            f"Download via Tools, then Manage Models, "
            f"or place them in:\n"
            f"{self._models_dir}"
        )

    def list_downloaded_languages(self) -> list[str]:
        """Return language codes for downloaded embedded models."""
        langs: list[str] = []
        if not self._models_dir.exists():
            return langs
        for sub in sorted(self._models_dir.iterdir()):
            if sub.is_dir():
                # Convention: directory names contain the language tag
                name = sub.name.lower()
                for tag in [
                    "en-us",
                    "en-gb",
                    "es-es",
                    "es-mx",
                    "fr-fr",
                    "de-de",
                    "it-it",
                    "pt-br",
                    "ja-jp",
                    "zh-cn",
                    "ko-kr",
                    "ar-sa",
                    "hi-in",
                    "ru-ru",
                ]:
                    if tag.replace("-", "") in name.replace("-", ""):
                        langs.append(tag)
                        break
        return langs

    def get_models_dir(self) -> Path:
        """Return the path where embedded models are stored."""
        return self._models_dir
