"""MAI-Transcribe-1 transcription provider (Azure LLM Speech API)."""

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

# MAI-Transcribe-1 supported languages (BCP-47 codes)
_SUPPORTED_LANGUAGES: list[str] = [
    "auto",
    "ar",
    "cs",
    "da",
    "de",
    "en",
    "es",
    "fi",
    "fr",
    "hi",
    "hu",
    "id",
    "it",
    "ja",
    "ko",
    "nb",
    "nl",
    "pl",
    "pt",
    "ro",
    "ru",
    "sv",
    "th",
    "tr",
    "vi",
    "zh",
]


class MAITranscribeProvider(TranscriptionProvider):
    """Cloud transcription via Microsoft MAI-Transcribe-1 (LLM Speech API).

    MAI-Transcribe-1 is a speech recognition model from the Microsoft AI
    Superintelligence team that provides best-in-class accuracy across
    25 languages with excellent noise robustness. It uses the same Azure
    Speech resource key as ``AzureSpeechProvider`` but routes through the
    LLM Speech REST API with ``model=mai-transcribe-1``.

    Pricing: $0.006 per minute ($0.36/hour).

    Limitations (public preview):
        - Diarization is NOT supported.
        - Maximum file size 300 MB.
        - WAV, MP3, and FLAC formats only.
    """

    RATE_PER_MINUTE: float = 0.006  # USD ($0.36/hour)
    _API_VERSION: str = "2025-10-15"

    def __init__(self, region: str = "eastus") -> None:
        self._region = region

    def get_capabilities(self) -> ProviderCapabilities:
        """Return MAI-Transcribe-1 capabilities."""
        return ProviderCapabilities(
            name="MAI-Transcribe-1",
            provider_type="cloud",
            supports_streaming=False,
            supports_timestamps=True,
            supports_diarization=False,
            supports_language_detection=True,
            max_file_size_mb=300,
            supported_languages=list(_SUPPORTED_LANGUAGES),
            rate_per_minute_usd=self.RATE_PER_MINUTE,
            free_tier_description="No free tier. $0.006/min ($0.36/hour).",
        )

    def validate_api_key(self, api_key: str) -> bool:
        """Validate Azure Speech key via a lightweight REST probe.

        Sends a tiny silent WAV to the LLM Speech API endpoint. A 401/403
        indicates an invalid key; any other response means the key is
        accepted.

        Args:
            api_key: Azure Speech subscription key.

        Returns:
            True if the key is valid.
        """
        if not api_key:
            return False
        try:
            import httpx

            url = (
                f"https://{self._region}.api.cognitive.microsoft.com"
                f"/speechtotext/transcriptions:transcribe"
                f"?api-version={self._API_VERSION}"
            )
            # Build a minimal silent WAV (1 second, 16 kHz mono)
            audio_data = _build_silent_wav(frames=16000)
            definition = '{"enhancedMode":{"enabled":true,"model":"mai-transcribe-1"}}'
            response = httpx.post(
                url,
                headers={"Ocp-Apim-Subscription-Key": api_key},
                files={"audio": ("silence.wav", audio_data, "audio/wav")},
                data={"definition": definition},
                timeout=15.0,
            )
            # 401/403 = bad key; anything else means the key itself is fine
            return response.status_code not in (401, 403)
        except Exception:
            logger.debug("MAI-Transcribe-1 key validation failed", exc_info=True)
            return False

    def estimate_cost(self, duration_seconds: float) -> float:
        """Estimate transcription cost.

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
        """Transcribe audio via MAI-Transcribe-1 LLM Speech API.

        Args:
            audio_path: Path to audio file (WAV, MP3, or FLAC).
            language: BCP-47 language code or ``'auto'``.
            model: Ignored (always ``mai-transcribe-1``).
            include_timestamps: Include word/segment timestamps.
            include_diarization: Not supported — ignored with a warning.
            api_key: Azure Speech subscription key.
            progress_callback: Optional progress callback.

        Returns:
            TranscriptionResult with the transcribed text.

        Raises:
            RuntimeError: On missing API key, network errors, or API failures.
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed. pip install httpx") from None

        if not api_key:
            raise RuntimeError("Azure Speech subscription key is required.")

        if include_diarization:
            logger.warning(
                "MAI-Transcribe-1 does not support diarization. "
                "Proceeding without speaker identification."
            )

        if progress_callback:
            progress_callback(5.0)

        audio = Path(audio_path)
        if not audio.exists():
            raise RuntimeError(f"Audio file not found: {audio_path}")

        logger.info("Starting MAI-Transcribe-1 transcription: %s", audio.name)

        # Build the request definition
        definition: dict[str, object] = {
            "enhancedMode": {
                "enabled": True,
                "model": "mai-transcribe-1",
            },
        }
        if language and language != "auto":
            definition["locales"] = [language]

        if progress_callback:
            progress_callback(10.0)

        url = (
            f"https://{self._region}.api.cognitive.microsoft.com"
            f"/speechtotext/transcriptions:transcribe"
            f"?api-version={self._API_VERSION}"
        )

        import json

        with audio.open("rb") as f:
            content_type = _mime_for_extension(audio.suffix)
            response = httpx.post(
                url,
                headers={"Ocp-Apim-Subscription-Key": api_key},
                files={"audio": (audio.name, f, content_type)},
                data={"definition": json.dumps(definition)},
                timeout=600.0,  # 10-minute timeout for large files
            )

        if progress_callback:
            progress_callback(80.0)

        if response.status_code != 200:
            raise RuntimeError(
                f"MAI-Transcribe-1 API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()

        # Parse response into segments
        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        for phrase in data.get("phrases", []):
            text = phrase.get("text", "").strip()
            if not text:
                continue
            offset_ticks = phrase.get("offsetMilliseconds", 0)
            duration_ticks = phrase.get("durationMilliseconds", 0)
            start_s = offset_ticks / 1000.0
            end_s = start_s + (duration_ticks / 1000.0)
            segments.append(
                TranscriptSegment(
                    start=start_s,
                    end=end_s,
                    text=text,
                )
            )
            full_text_parts.append(text)

        # Fallback: if no phrases key, try combinedPhrases or text
        if not full_text_parts:
            combined = data.get("combinedPhrases", [])
            for cp in combined:
                text = cp.get("text", "").strip()
                if text:
                    full_text_parts.append(text)

        if not full_text_parts:
            text = data.get("text", "").strip()
            if text:
                full_text_parts.append(text)

        if progress_callback:
            progress_callback(100.0)

        duration = segments[-1].end if segments else 0.0
        detected_lang = data.get("language", language)

        return TranscriptionResult(
            job_id="",
            audio_file=audio.name,
            provider="mai_transcribe",
            model="mai-transcribe-1",
            language=detected_lang if detected_lang else language,
            duration_seconds=duration,
            segments=segments,
            full_text=" ".join(full_text_parts),
            created_at=datetime.now().isoformat(),
        )


def _build_silent_wav(frames: int = 16000) -> bytes:
    """Build a minimal silent WAV file in memory.

    Args:
        frames: Number of 16-bit mono samples (16000 = 1 second at 16 kHz).

    Returns:
        Complete WAV file as bytes.
    """
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<" + "h" * frames, *([0] * frames)))
    return buf.getvalue()


def _mime_for_extension(ext: str) -> str:
    """Map audio file extension to MIME type.

    Args:
        ext: File extension including dot (e.g. ``'.wav'``).

    Returns:
        MIME type string.
    """
    mime_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
    }
    return mime_map.get(ext.lower(), "application/octet-stream")
