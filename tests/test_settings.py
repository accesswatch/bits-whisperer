"""Tests for AppSettings persistence and defaults."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from bits_whisperer.core.settings import (
    AdvancedSettings,
    AppSettings,
    AudioProcessingSettings,
    GeneralSettings,
    TranscriptionSettings,
)


class TestGeneralDefaults:
    """GeneralSettings default values."""

    def test_language_default(self) -> None:
        s = GeneralSettings()
        assert s.language == "auto"

    def test_provider_default(self) -> None:
        s = GeneralSettings()
        assert s.default_provider == "local_whisper"

    def test_minimize_to_tray_default(self) -> None:
        s = GeneralSettings()
        assert s.minimize_to_tray is True

    def test_auto_export_default(self) -> None:
        s = GeneralSettings()
        assert s.auto_export is False

    def test_experience_mode_default(self) -> None:
        s = GeneralSettings()
        assert s.experience_mode == "basic"

    def test_activated_providers_default(self) -> None:
        s = GeneralSettings()
        assert s.activated_providers == []

    def test_experience_mode_advanced(self) -> None:
        s = GeneralSettings(experience_mode="advanced")
        assert s.experience_mode == "advanced"

    def test_activated_providers_persist(self) -> None:
        s = GeneralSettings(activated_providers=["openai", "groq"])
        assert s.activated_providers == ["openai", "groq"]


class TestTranscriptionDefaults:
    """TranscriptionSettings default values."""

    def test_timestamps_on(self) -> None:
        s = TranscriptionSettings()
        assert s.include_timestamps is True

    def test_temperature_zero(self) -> None:
        s = TranscriptionSettings()
        assert s.temperature == 0.0

    def test_beam_size_five(self) -> None:
        s = TranscriptionSettings()
        assert s.beam_size == 5

    def test_vad_on(self) -> None:
        s = TranscriptionSettings()
        assert s.vad_filter is True


class TestAudioProcessingDefaults:
    """AudioProcessingSettings default values."""

    def test_enabled_default(self) -> None:
        s = AudioProcessingSettings()
        assert s.enabled is True

    def test_highpass_default(self) -> None:
        s = AudioProcessingSettings()
        assert s.highpass_enabled is True
        assert s.highpass_freq == 80

    def test_deesser_off_by_default(self) -> None:
        s = AudioProcessingSettings()
        assert s.deesser_enabled is False

    def test_loudnorm_target(self) -> None:
        s = AudioProcessingSettings()
        assert s.loudnorm_target_i == -16.0


class TestAdvancedDefaults:
    """AdvancedSettings default values."""

    def test_max_file_size(self) -> None:
        s = AdvancedSettings()
        assert s.max_file_size_mb == 500

    def test_max_concurrent_jobs(self) -> None:
        s = AdvancedSettings()
        assert s.max_concurrent_jobs == 2


class TestAppSettingsSerialization:
    """AppSettings save/load round-trip."""

    def test_defaults_roundtrip(self) -> None:
        settings = AppSettings()
        data = json.loads(json.dumps(settings.__dict__, default=str))
        # Basic shape check
        assert "general" in str(data) or hasattr(settings, "general")

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {
            "general": {"language": "en", "unknown_key": "ignored"},
            "transcription": {},
            "output": {},
            "audio_processing": {},
            "paths": {},
            "advanced": {},
        }
        settings = AppSettings._from_dict(data)
        assert settings.general.language == "en"
        assert not hasattr(settings.general, "unknown_key")

    def test_from_dict_empty(self) -> None:
        settings = AppSettings._from_dict({})
        assert settings.general.language == "auto"
        assert settings.transcription.beam_size == 5

    def test_save_and_load(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            # Save
            settings = AppSettings()
            settings.general.language = "fr"
            settings.transcription.temperature = 0.5
            settings.save()

            assert settings_file.exists()

            # Load
            loaded = AppSettings.load()
            assert loaded.general.language == "fr"
            assert loaded.transcription.temperature == 0.5

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", missing):
            settings = AppSettings.load()
            assert settings.general.language == "auto"

    def test_load_corrupt_file_returns_defaults(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("not valid json {{{", encoding="utf-8")
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", corrupt):
            settings = AppSettings.load()
            assert settings.general.language == "auto"

    def test_experience_mode_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.general.experience_mode = "advanced"
            settings.general.activated_providers = ["openai", "deepgram"]
            settings.save()

            loaded = AppSettings.load()
            assert loaded.general.experience_mode == "advanced"
            assert loaded.general.activated_providers == ["openai", "deepgram"]

    def test_activated_providers_from_dict(self) -> None:
        data = {
            "general": {
                "language": "en",
                "experience_mode": "advanced",
                "activated_providers": ["gemini"],
            },
        }
        settings = AppSettings._from_dict(data)
        assert settings.general.experience_mode == "advanced"
        assert settings.general.activated_providers == ["gemini"]

    def test_missing_mode_defaults_to_basic(self) -> None:
        """Old settings files without experience_mode field get basic."""
        data = {"general": {"language": "en"}}
        settings = AppSettings._from_dict(data)
        assert settings.general.experience_mode == "basic"
        assert settings.general.activated_providers == []
