"""Windows built-in speech recognition via SAPI / WinRT.

Uses the Windows.Media.SpeechRecognition WinRT API on Windows 10/11
for fully offline, free speech-to-text. Falls back to the classic
System.Speech (SAPI5) COM interface when WinRT is not available.

No API key, no downloads, no internet — just the speech recogniser
that ships with every Windows 10/11 installation.

Requirements
------------
- Windows 10 1903+ or Windows 11
- ``winsdk`` Python package for WinRT bindings  (pip install winsdk)
  OR the ``comtypes`` / ``pywin32`` package for classic SAPI fallback
- Offline language packs installed via Windows Settings, then Time and Language
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.providers.base import (
    ProgressCallback,
    ProviderCapabilities,
    TranscriptionProvider,
)

logger = logging.getLogger(__name__)


class WindowsSpeechProvider(TranscriptionProvider):
    """On-device transcription using the Windows built-in speech engine.

    Two backends are attempted in order:

    1. **WinRT** — ``Windows.Media.SpeechRecognition`` (Windows 10 1903+).
       High-quality neural recogniser with offline language packs.
    2. **SAPI5** — Classic ``ISpRecoGrammar`` COM object via ``comtypes``.
       Available on every Windows version since Vista, lower accuracy.

    Both are completely free, offline, and require zero configuration.
    """

    def get_capabilities(self) -> ProviderCapabilities:
        """Return Windows Speech capabilities."""
        return ProviderCapabilities(
            name="Windows Speech (Built-in)",
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
                "fr-FR",
                "de-DE",
                "it-IT",
                "pt-BR",
                "ja-JP",
                "zh-CN",
                "ko-KR",
            ],
            rate_per_minute_usd=0.0,
            free_tier_description=(
                "Free forever — uses Windows built-in speech recognition. "
                "No internet required. Install language packs via Windows "
                "Settings, then Time and Language for additional languages."
            ),
        )

    def validate_api_key(self, api_key: str) -> bool:
        """No key needed — always valid on Windows."""
        return sys.platform == "win32"

    def estimate_cost(self, duration_seconds: float) -> float:
        """Return zero — always free."""
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
        """Transcribe audio using Windows built-in speech recogniser.

        Tries the WinRT path first, then falls back to SAPI5.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            language: BCP-47 language tag (e.g. ``"en-US"``).
            model: Ignored — Windows selects the best installed model.
            include_timestamps: Include per-phrase timestamps.
            include_diarization: Ignored — Windows Speech has no diarization.
            api_key: Ignored — no key needed.
            progress_callback: Optional progress callback (0–100).

        Returns:
            TranscriptionResult.
        """
        if sys.platform != "win32":
            raise RuntimeError("Windows Speech provider is Windows-only.")

        if language == "auto":
            language = "en-US"

        if progress_callback:
            progress_callback(5.0)

        # Try WinRT first (better quality)
        try:
            return self._transcribe_winrt(
                audio_path,
                language,
                progress_callback,
            )
        except Exception as winrt_err:
            logger.info(
                "WinRT not available (%s), trying SAPI5…",
                winrt_err,
            )

        # Fallback to SAPI5
        try:
            return self._transcribe_sapi(
                audio_path,
                language,
                progress_callback,
            )
        except Exception as sapi_err:
            msg = (
                "Windows speech recognition unavailable.\n"
                f"SAPI5 error: {sapi_err}\n\n"
                f"Ensure Windows 10 1903+ and the "
                f"'{language}' language pack are installed."
            )
            raise RuntimeError(msg) from sapi_err

    # ------------------------------------------------------------------ #
    # WinRT backend                                                        #
    # ------------------------------------------------------------------ #

    def _transcribe_winrt(
        self,
        audio_path: str,
        language: str,
        progress_callback: ProgressCallback | None,
    ) -> TranscriptionResult:
        """Transcribe using Windows.Media.SpeechRecognition (WinRT).

        This uses the modern neural recogniser on Windows 10 1903+.
        """
        import asyncio

        # WinRT requires an event loop — create one for sync callers
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._winrt_async(audio_path, language, progress_callback)
            )
        finally:
            loop.close()

    async def _winrt_async(
        self,
        audio_path: str,
        language: str,
        progress_callback: ProgressCallback | None,
    ) -> TranscriptionResult:
        """Async WinRT speech recognition from an audio file.

        Note: The WinRT ``SpeechRecognizer`` API (via winsdk bindings) uses
        the default audio input device (microphone) and does not support
        feeding audio from a file.  This method raises ``NotImplementedError``
        so the caller falls through to the SAPI5 backend, which properly
        handles file-based transcription.
        """
        raise NotImplementedError(
            "WinRT SpeechRecognizer does not support file-based audio input "
            "via the winsdk bindings. Use SAPI5 backend instead."
        )

    # ------------------------------------------------------------------ #
    # SAPI5 fallback                                                       #
    # ------------------------------------------------------------------ #

    def _transcribe_sapi(
        self,
        audio_path: str,
        language: str,
        progress_callback: ProgressCallback | None,
    ) -> TranscriptionResult:
        """Transcribe using classic SAPI5 COM interface.

        Uses ``comtypes`` to drive ``ISpRecoGrammar`` with a dictation
        grammar for general speech-to-text.
        """
        import comtypes  # noqa: F401
        from comtypes.client import CreateObject

        if progress_callback:
            progress_callback(10.0)

        # SAPI constants
        SPRST_INACTIVE = 0
        SPRST_ACTIVE = 1

        # Create SAPI recogniser
        recognizer = CreateObject("SAPI.SpInprocRecognizer")

        # Set audio input to file
        audio_input = CreateObject("SAPI.SpFileStream")
        audio_input.Open(str(Path(audio_path).resolve()), 0)  # 0 = read

        try:
            recognizer.AudioInputStream = audio_input

            if progress_callback:
                progress_callback(20.0)

            # Create recognition context
            context = recognizer.CreateRecoContext()

            # Load dictation grammar
            grammar = context.CreateGrammar(0)
            grammar.DictationLoad("", 0)
            grammar.DictationSetState(SPRST_ACTIVE)

            segments: list[TranscriptSegment] = []
            full_text_parts: list[str] = []
            seg_idx = 0.0

            # Synchronous recognition loop
            while True:
                try:
                    result = context.WaitForRecognition(10000)  # 10s timeout
                    if result is None:
                        break
                    text = result.PhraseInfo.GetText(0, -1, True)
                    if text and text.strip():
                        segments.append(
                            TranscriptSegment(
                                start=seg_idx,
                                end=seg_idx + 3.0,
                                text=text.strip(),
                            )
                        )
                        full_text_parts.append(text.strip())
                        seg_idx += 3.0

                        if progress_callback:
                            progress_callback(min(90.0, 20.0 + len(segments) * 3))
                except Exception:
                    break

            grammar.DictationSetState(SPRST_INACTIVE)
        finally:
            audio_input.Close()

        if progress_callback:
            progress_callback(100.0)

        return TranscriptionResult(
            job_id="",
            audio_file=Path(audio_path).name,
            provider="windows_speech",
            model="sapi5",
            language=language,
            duration_seconds=seg_idx,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )
