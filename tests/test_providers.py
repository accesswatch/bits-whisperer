"""Tests for provider base classes and capabilities."""

from __future__ import annotations

from bits_whisperer.providers.base import ProviderCapabilities
from bits_whisperer.providers.parakeet_provider import ParakeetProvider
from bits_whisperer.providers.vosk_provider import VoskProvider


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


class TestVoskProvider:
    """VoskProvider capabilities and local-provider contract."""

    def test_capabilities_name(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.name == "Vosk"

    def test_capabilities_type_local(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps_supported(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_diarization(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_supported_languages(self) -> None:
        provider = VoskProvider()
        caps = provider.get_capabilities()
        assert "en-us" in caps.supported_languages
        assert len(caps.supported_languages) >= 9

    def test_validate_api_key_always_true(self) -> None:
        provider = VoskProvider()
        assert provider.validate_api_key("") is True
        assert provider.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self) -> None:
        provider = VoskProvider()
        assert provider.estimate_cost(60.0) == 0.0
        assert provider.estimate_cost(3600.0) == 0.0


class TestParakeetProvider:
    """ParakeetProvider capabilities and local-provider contract."""

    def test_capabilities_name(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.name == "Parakeet"

    def test_capabilities_type_local(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.provider_type == "local"

    def test_capabilities_free(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.rate_per_minute_usd == 0.0

    def test_capabilities_timestamps_supported(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.supports_timestamps is True

    def test_capabilities_no_diarization(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.supports_diarization is False

    def test_capabilities_no_language_detection(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.supports_language_detection is False

    def test_capabilities_english_only(self) -> None:
        provider = ParakeetProvider()
        caps = provider.get_capabilities()
        assert caps.supported_languages == ["en"]

    def test_validate_api_key_always_true(self) -> None:
        provider = ParakeetProvider()
        assert provider.validate_api_key("") is True
        assert provider.validate_api_key("anything") is True

    def test_estimate_cost_always_zero(self) -> None:
        provider = ParakeetProvider()
        assert provider.estimate_cost(60.0) == 0.0
        assert provider.estimate_cost(3600.0) == 0.0
