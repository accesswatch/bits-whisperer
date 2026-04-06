"""Tests for provider base classes, capabilities, and all 18 provider adapters."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from bits_whisperer.providers.assemblyai_provider import AssemblyAIProvider
from bits_whisperer.providers.auphonic_provider import AuphonicProvider
from bits_whisperer.providers.aws_transcribe import AWSTranscribeProvider
from bits_whisperer.providers.azure_embedded import AzureEmbeddedSpeechProvider
from bits_whisperer.providers.azure_speech import AzureSpeechProvider
from bits_whisperer.providers.base import ProviderCapabilities
from bits_whisperer.providers.deepgram_provider import DeepgramProvider
from bits_whisperer.providers.elevenlabs_provider import ElevenLabsProvider
from bits_whisperer.providers.gemini_provider import GeminiProvider
from bits_whisperer.providers.google_speech import GoogleSpeechProvider
from bits_whisperer.providers.groq_whisper import GroqWhisperProvider
from bits_whisperer.providers.local_whisper import LocalWhisperProvider
from bits_whisperer.providers.mai_transcribe_provider import MAITranscribeProvider
from bits_whisperer.providers.openai_whisper import OpenAIWhisperProvider
from bits_whisperer.providers.parakeet_provider import ParakeetProvider
from bits_whisperer.providers.rev_ai_provider import RevAIProvider
from bits_whisperer.providers.speechmatics_provider import SpeechmaticsProvider
from bits_whisperer.providers.vosk_provider import VoskProvider
from bits_whisperer.providers.windows_speech import WindowsSpeechProvider

# ---------------------------------------------------------------------------
# Helper: assert cost formula  (duration_seconds / 60) * rate
# ---------------------------------------------------------------------------


def _assert_cost(provider: object, rate: float) -> None:
    """Verify estimate_cost follows the standard per-minute formula."""
    est = provider.estimate_cost  # type: ignore[attr-defined]
    assert est(0.0) == 0.0
    assert math.isclose(est(60.0), rate, rel_tol=1e-9)
    assert math.isclose(est(120.0), rate * 2, rel_tol=1e-9)
    assert math.isclose(est(30.0), rate / 2, rel_tol=1e-9)


# ===================================================================
# ProviderCapabilities dataclass
# ===================================================================


class TestProviderCapabilities:
    """ProviderCapabilities dataclass validation."""

    def test_minimal_capabilities(self) -> None:
        caps = ProviderCapabilities(name="Test Provider", provider_type="local")
        assert caps.name == "Test Provider"
        assert caps.provider_type == "local"

    def test_defaults(self) -> None:
        caps = ProviderCapabilities(name="Test", provider_type="cloud")
        assert caps.supports_streaming is False
        assert caps.supports_timestamps is True
        assert caps.supports_diarization is False
        assert caps.rate_per_minute_usd == 0.0
        assert caps.max_file_size_mb == 500

    def test_frozen(self) -> None:
        caps = ProviderCapabilities(name="Test", provider_type="local")
        try:
            caps.name = "changed"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass


# ===================================================================
# LOCAL PROVIDERS (free, no API key required)
# ===================================================================


class TestLocalWhisperProvider:
    """LocalWhisperProvider — on-device faster-whisper."""

    def test_capabilities_name(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.name == "Local Whisper"

    def test_capabilities_type_local(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_streaming(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_language_detection(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = LocalWhisperProvider().get_capabilities()
        assert caps.max_file_size_mb == 500

    def test_validate_api_key_always_true(self) -> None:
        p = LocalWhisperProvider()
        assert p.validate_api_key("") is True
        assert p.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self) -> None:
        p = LocalWhisperProvider()
        assert p.estimate_cost(60.0) == 0.0
        assert p.estimate_cost(3600.0) == 0.0


class TestVoskProvider:
    """VoskProvider — on-device Kaldi-based recognition."""

    def test_capabilities_name(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.name == "Vosk"

    def test_capabilities_type_local(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps_supported(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_diarization(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_supported_languages(self) -> None:
        caps = VoskProvider().get_capabilities()
        assert "en-us" in caps.supported_languages
        assert len(caps.supported_languages) >= 9

    def test_validate_api_key_always_true(self) -> None:
        p = VoskProvider()
        assert p.validate_api_key("") is True
        assert p.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self) -> None:
        p = VoskProvider()
        assert p.estimate_cost(60.0) == 0.0
        assert p.estimate_cost(3600.0) == 0.0


class TestParakeetProvider:
    """ParakeetProvider — NVIDIA NeMo ASR, English only."""

    def test_capabilities_name(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.name == "Parakeet"

    def test_capabilities_type_local(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps_supported(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_diarization(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_english_only(self) -> None:
        caps = ParakeetProvider().get_capabilities()
        assert caps.supported_languages == ["en"]

    def test_validate_api_key_always_true(self) -> None:
        p = ParakeetProvider()
        assert p.validate_api_key("") is True
        assert p.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self) -> None:
        p = ParakeetProvider()
        assert p.estimate_cost(60.0) == 0.0
        assert p.estimate_cost(3600.0) == 0.0


class TestWindowsSpeechProvider:
    """WindowsSpeechProvider — Windows built-in SAPI5/WinRT."""

    def test_capabilities_name(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.name == "Windows Speech (Built-in)"

    def test_capabilities_type_local(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_streaming(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_supported_languages(self) -> None:
        caps = WindowsSpeechProvider().get_capabilities()
        assert "en-US" in caps.supported_languages
        assert len(caps.supported_languages) >= 5

    def test_validate_api_key_platform_check(self) -> None:
        p = WindowsSpeechProvider()
        assert p.validate_api_key("ignored") == (sys.platform == "win32")

    def test_estimate_cost_always_zero(self) -> None:
        p = WindowsSpeechProvider()
        assert p.estimate_cost(60.0) == 0.0
        assert p.estimate_cost(3600.0) == 0.0


class TestAzureEmbeddedSpeechProvider:
    """AzureEmbeddedSpeechProvider — offline Microsoft neural models."""

    def test_capabilities_name(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.name == "Microsoft Embedded Speech (Offline)"

    def test_capabilities_type_local(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_diarization(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_supported_languages(self, tmp_path: Path) -> None:
        caps = AzureEmbeddedSpeechProvider(models_dir=tmp_path).get_capabilities()
        assert "en-US" in caps.supported_languages
        assert len(caps.supported_languages) >= 10

    def test_validate_api_key_always_true(self, tmp_path: Path) -> None:
        p = AzureEmbeddedSpeechProvider(models_dir=tmp_path)
        assert p.validate_api_key("") is True
        assert p.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self, tmp_path: Path) -> None:
        p = AzureEmbeddedSpeechProvider(models_dir=tmp_path)
        assert p.estimate_cost(60.0) == 0.0
        assert p.estimate_cost(3600.0) == 0.0


# ===================================================================
# CLOUD PROVIDERS (paid, API key validated via network)
# ===================================================================


class TestOpenAIWhisperProvider:
    """OpenAIWhisperProvider — cloud Whisper API."""

    def test_capabilities_name(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.name == "OpenAI Whisper"

    def test_capabilities_type_cloud(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_language_detection(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.max_file_size_mb == 25

    def test_capabilities_rate(self) -> None:
        caps = OpenAIWhisperProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.006

    def test_estimate_cost(self) -> None:
        _assert_cost(OpenAIWhisperProvider(), 0.006)


class TestGoogleSpeechProvider:
    """GoogleSpeechProvider — Google Cloud Speech-to-Text."""

    def test_capabilities_name(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.name == "Google Cloud Speech"

    def test_capabilities_type_cloud(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_streaming(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.supports_streaming is True

    def test_capabilities_diarization(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.max_file_size_mb == 480

    def test_capabilities_rate(self) -> None:
        caps = GoogleSpeechProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.024

    def test_estimate_cost(self) -> None:
        _assert_cost(GoogleSpeechProvider(), 0.024)


class TestGeminiProvider:
    """GeminiProvider — Google Gemini multimodal transcription."""

    def test_capabilities_name(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.name == "Google Gemini"

    def test_capabilities_type_cloud(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_diarization(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = GeminiProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0002

    def test_estimate_cost(self) -> None:
        _assert_cost(GeminiProvider(), 0.0002)


class TestAzureSpeechProvider:
    """AzureSpeechProvider — Microsoft Azure Speech Services."""

    def test_capabilities_name(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.name == "Azure Speech Services"

    def test_capabilities_type_cloud(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_streaming(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.supports_streaming is True

    def test_capabilities_diarization(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.max_file_size_mb == 200

    def test_capabilities_rate(self) -> None:
        caps = AzureSpeechProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.017

    def test_estimate_cost(self) -> None:
        _assert_cost(AzureSpeechProvider(), 0.017)


class TestAWSTranscribeProvider:
    """AWSTranscribeProvider — Amazon Transcribe."""

    def test_capabilities_name(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.name == "Amazon Transcribe"

    def test_capabilities_type_cloud(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_streaming(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.supports_streaming is True

    def test_capabilities_diarization(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.024

    def test_capabilities_supported_languages(self) -> None:
        caps = AWSTranscribeProvider().get_capabilities()
        assert "auto" in caps.supported_languages
        assert "en" in caps.supported_languages
        assert len(caps.supported_languages) >= 5

    def test_estimate_cost(self) -> None:
        _assert_cost(AWSTranscribeProvider(), 0.024)


class TestDeepgramProvider:
    """DeepgramProvider — Deepgram Nova-3."""

    def test_capabilities_name(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.name == "Deepgram"

    def test_capabilities_type_cloud(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_streaming(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.supports_streaming is True

    def test_capabilities_diarization(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = DeepgramProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0125

    def test_estimate_cost(self) -> None:
        _assert_cost(DeepgramProvider(), 0.0125)


class TestAssemblyAIProvider:
    """AssemblyAIProvider — AssemblyAI."""

    def test_capabilities_name(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.name == "AssemblyAI"

    def test_capabilities_type_cloud(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_streaming(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.supports_streaming is True

    def test_capabilities_diarization(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.max_file_size_mb == 5000

    def test_capabilities_rate(self) -> None:
        caps = AssemblyAIProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.011

    def test_estimate_cost(self) -> None:
        _assert_cost(AssemblyAIProvider(), 0.011)


class TestGroqWhisperProvider:
    """GroqWhisperProvider — Groq LPU ultra-fast Whisper."""

    def test_capabilities_name(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.name == "Groq Whisper (Ultra-Fast)"

    def test_capabilities_type_cloud(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_language_detection(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.max_file_size_mb == 25

    def test_capabilities_rate(self) -> None:
        caps = GroqWhisperProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.0028

    def test_estimate_cost(self) -> None:
        _assert_cost(GroqWhisperProvider(), 0.0028)


class TestRevAIProvider:
    """RevAIProvider — Rev.ai transcription."""

    def test_capabilities_name(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.name == "Rev.ai"

    def test_capabilities_type_cloud(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_diarization(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.02

    def test_capabilities_supported_languages(self) -> None:
        caps = RevAIProvider().get_capabilities()
        assert "en" in caps.supported_languages
        assert len(caps.supported_languages) >= 10

    def test_estimate_cost(self) -> None:
        _assert_cost(RevAIProvider(), 0.02)


class TestSpeechmaticsProvider:
    """SpeechmaticsProvider — Speechmatics batch transcription."""

    def test_capabilities_name(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.name == "Speechmatics"

    def test_capabilities_type_cloud(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_diarization(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.017

    def test_capabilities_supported_languages(self) -> None:
        caps = SpeechmaticsProvider().get_capabilities()
        assert "en" in caps.supported_languages
        assert len(caps.supported_languages) >= 30

    def test_estimate_cost(self) -> None:
        _assert_cost(SpeechmaticsProvider(), 0.017)


class TestElevenLabsProvider:
    """ElevenLabsProvider — ElevenLabs Scribe."""

    def test_capabilities_name(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.name == "ElevenLabs Scribe"

    def test_capabilities_type_cloud(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_diarization(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.supports_diarization is True

    def test_capabilities_language_detection(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.max_file_size_mb == 2000

    def test_capabilities_rate(self) -> None:
        caps = ElevenLabsProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.005

    def test_estimate_cost(self) -> None:
        _assert_cost(ElevenLabsProvider(), 0.005)


class TestAuphonicProvider:
    """AuphonicProvider — Auphonic post-production + transcription."""

    def test_capabilities_name(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.name == "Auphonic"

    def test_capabilities_type_cloud(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_language_detection(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.max_file_size_mb == 500

    def test_capabilities_rate(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.01

    def test_capabilities_supported_languages(self) -> None:
        caps = AuphonicProvider().get_capabilities()
        assert "auto" in caps.supported_languages
        assert "en" in caps.supported_languages
        assert len(caps.supported_languages) >= 5

    def test_estimate_cost(self) -> None:
        _assert_cost(AuphonicProvider(), 0.01)


class TestMAITranscribeProvider:
    """MAITranscribeProvider — Microsoft MAI-Transcribe-1 (LLM Speech API)."""

    def test_capabilities_name(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.name == "MAI-Transcribe-1"

    def test_capabilities_type_cloud(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.provider_type == "cloud"

    def test_capabilities_no_streaming(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.supports_streaming is False

    def test_capabilities_no_diarization(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_language_detection(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.supports_language_detection is True

    def test_capabilities_max_file_size(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.max_file_size_mb == 300

    def test_capabilities_rate(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert caps.rate_per_minute_usd == 0.006

    def test_capabilities_supported_languages(self) -> None:
        caps = MAITranscribeProvider().get_capabilities()
        assert "auto" in caps.supported_languages
        assert "en" in caps.supported_languages
        assert len(caps.supported_languages) == 26

    def test_estimate_cost(self) -> None:
        _assert_cost(MAITranscribeProvider(), 0.006)

    def test_validate_api_key_empty_returns_false(self) -> None:
        p = MAITranscribeProvider()
        assert p.validate_api_key("") is False

    def test_transcribe_missing_key_raises(self) -> None:
        p = MAITranscribeProvider()
        with pytest.raises(RuntimeError, match="subscription key is required"):
            p.transcribe("test.wav", api_key="")

    def test_transcribe_missing_file_raises(self, tmp_path: Path) -> None:
        p = MAITranscribeProvider()
        missing = str(tmp_path / "nonexistent.wav")
        with pytest.raises(RuntimeError, match="Audio file not found"):
            p.transcribe(missing, api_key="test-key")


# ===================================================================
# Cross-provider consistency checks
# ===================================================================


class TestAllProvidersContract:
    """Verify every provider satisfies the TranscriptionProvider ABC contract."""

    @pytest.fixture
    def all_providers(self, tmp_path: Path) -> list:
        """Instantiate all 18 providers."""
        return [
            LocalWhisperProvider(),
            OpenAIWhisperProvider(),
            GoogleSpeechProvider(),
            GeminiProvider(),
            AzureSpeechProvider(),
            AzureEmbeddedSpeechProvider(models_dir=tmp_path),
            AWSTranscribeProvider(),
            DeepgramProvider(),
            AssemblyAIProvider(),
            GroqWhisperProvider(),
            RevAIProvider(),
            SpeechmaticsProvider(),
            ElevenLabsProvider(),
            WindowsSpeechProvider(),
            VoskProvider(),
            ParakeetProvider(),
            AuphonicProvider(),
            MAITranscribeProvider(),
        ]

    def test_all_have_capabilities(self, all_providers: list) -> None:
        for p in all_providers:
            caps = p.get_capabilities()
            assert isinstance(caps, ProviderCapabilities), f"{type(p).__name__}"
            assert caps.name, f"{type(p).__name__} missing name"
            assert caps.provider_type in ("local", "cloud"), f"{type(p).__name__}"

    def test_all_estimate_cost_non_negative(self, all_providers: list) -> None:
        for p in all_providers:
            cost = p.estimate_cost(300.0)
            assert cost >= 0.0, f"{type(p).__name__} returned negative cost"

    def test_all_local_providers_are_free(self, all_providers: list) -> None:
        for p in all_providers:
            caps = p.get_capabilities()
            if caps.provider_type == "local":
                assert caps.rate_per_minute_usd == 0.0, f"{caps.name} not free"
                assert p.estimate_cost(600.0) == 0.0, f"{caps.name} cost != 0"

    def test_all_cloud_providers_have_rate(self, all_providers: list) -> None:
        for p in all_providers:
            caps = p.get_capabilities()
            if caps.provider_type == "cloud":
                assert caps.rate_per_minute_usd > 0.0, f"{caps.name} missing rate"

    def test_provider_count_is_eighteen(self, all_providers: list) -> None:
        assert len(all_providers) == 18
