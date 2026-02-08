"""Tests for AI service, live transcription, and plugin system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from bits_whisperer.core.settings import (
    AISettings,
    AppSettings,
    LiveTranscriptionSettings,
    PluginSettings,
)

# -----------------------------------------------------------------------
# AISettings tests
# -----------------------------------------------------------------------


class TestAISettingsDefaults:
    """AISettings default values."""

    def test_default_provider(self) -> None:
        s = AISettings()
        assert s.selected_provider == "openai"

    def test_default_openai_model(self) -> None:
        s = AISettings()
        assert s.openai_model == "gpt-4o-mini"

    def test_default_anthropic_model(self) -> None:
        s = AISettings()
        assert "claude" in s.anthropic_model.lower()

    def test_default_temperature(self) -> None:
        s = AISettings()
        assert s.temperature == 0.3

    def test_default_max_tokens(self) -> None:
        s = AISettings()
        assert s.max_tokens == 4096

    def test_default_translation_language(self) -> None:
        s = AISettings()
        assert s.translation_target_language == "en"

    def test_default_summarization_style(self) -> None:
        s = AISettings()
        assert s.summarization_style == "concise"


class TestAISettingsSerialization:
    """AISettings persistence round-trip."""

    def test_ai_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.ai.selected_provider = "anthropic"
            settings.ai.openai_model = "gpt-4o"
            settings.ai.temperature = 0.7
            settings.ai.translation_target_language = "Spanish"
            settings.ai.summarization_style = "bullet_points"
            settings.save()

            loaded = AppSettings.load()
            assert loaded.ai.selected_provider == "anthropic"
            assert loaded.ai.openai_model == "gpt-4o"
            assert loaded.ai.temperature == 0.7
            assert loaded.ai.translation_target_language == "Spanish"
            assert loaded.ai.summarization_style == "bullet_points"

    def test_ai_settings_from_dict(self) -> None:
        data = {
            "ai": {
                "selected_provider": "azure_openai",
                "max_tokens": 8192,
            },
        }
        settings = AppSettings._from_dict(data)
        assert settings.ai.selected_provider == "azure_openai"
        assert settings.ai.max_tokens == 8192
        # Other fields get defaults
        assert settings.ai.temperature == 0.3

    def test_missing_ai_section_defaults(self) -> None:
        data = {"general": {"language": "en"}}
        settings = AppSettings._from_dict(data)
        assert settings.ai.selected_provider == "openai"


# -----------------------------------------------------------------------
# LiveTranscriptionSettings tests
# -----------------------------------------------------------------------


class TestLiveTranscriptionSettingsDefaults:
    """LiveTranscriptionSettings default values."""

    def test_not_enabled_by_default(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.enabled is False

    def test_default_model(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.model == "base"

    def test_default_language(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.language == "auto"

    def test_default_sample_rate(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.sample_rate == 16000

    def test_default_chunk_duration(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.chunk_duration_seconds == 3.0

    def test_default_silence_threshold(self) -> None:
        s = LiveTranscriptionSettings()
        assert s.silence_threshold_seconds == 0.8


class TestLiveTranscriptionSettingsSerialization:
    """LiveTranscriptionSettings persistence."""

    def test_live_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.live_transcription.model = "small"
            settings.live_transcription.language = "en"
            settings.live_transcription.chunk_duration_seconds = 5.0
            settings.save()

            loaded = AppSettings.load()
            assert loaded.live_transcription.model == "small"
            assert loaded.live_transcription.language == "en"
            assert loaded.live_transcription.chunk_duration_seconds == 5.0


# -----------------------------------------------------------------------
# PluginSettings tests
# -----------------------------------------------------------------------


class TestPluginSettingsDefaults:
    """PluginSettings default values."""

    def test_enabled_by_default(self) -> None:
        s = PluginSettings()
        assert s.enabled is True

    def test_empty_plugin_directory(self) -> None:
        s = PluginSettings()
        assert s.plugin_directory == ""

    def test_no_disabled_plugins(self) -> None:
        s = PluginSettings()
        assert s.disabled_plugins == []

    def test_auto_update_off(self) -> None:
        s = PluginSettings()
        assert s.auto_update is False


class TestPluginSettingsSerialization:
    """PluginSettings persistence."""

    def test_plugin_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.plugins.enabled = False
            settings.plugins.disabled_plugins = ["my_plugin"]
            settings.save()

            loaded = AppSettings.load()
            assert loaded.plugins.enabled is False
            assert loaded.plugins.disabled_plugins == ["my_plugin"]


# -----------------------------------------------------------------------
# AI Service tests
# -----------------------------------------------------------------------


class TestAIService:
    """AIService unit tests."""

    def test_not_configured_without_keys(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        mock_ks.has_key.return_value = False

        service = AIService(mock_ks, AISettings())
        assert service.is_configured() is False

    def test_get_available_providers_empty(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.has_key.return_value = False

        with patch("shutil.which", return_value=None):
            service = AIService(mock_ks, AISettings())
            assert service.get_available_providers() == []

    def test_get_available_providers_with_openai(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.has_key.side_effect = lambda k: k == "openai"

        with patch("shutil.which", return_value=None):
            service = AIService(mock_ks, AISettings())
            providers = service.get_available_providers()
            assert len(providers) == 1
            assert providers[0]["id"] == "openai"

    def test_translate_without_provider_returns_error(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None

        service = AIService(mock_ks, AISettings())
        response = service.translate("Hello world", "Spanish")
        assert response.error != ""
        assert response.text == ""

    def test_summarize_without_provider_returns_error(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None

        service = AIService(mock_ks, AISettings())
        response = service.summarize("This is a test transcript.")
        assert response.error != ""
        assert response.text == ""

    def test_ai_response_dataclass(self) -> None:
        from bits_whisperer.core.ai_service import AIResponse

        r = AIResponse(text="Hello", provider="openai", model="gpt-4o")
        assert r.text == "Hello"
        assert r.tokens_used == 0
        assert r.error == ""


# -----------------------------------------------------------------------
# Plugin Manager tests
# -----------------------------------------------------------------------


class TestPluginManager:
    """PluginManager unit tests."""

    def test_discover_empty_directory(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        plugins = mgr.discover()
        assert plugins == []

    def test_discover_finds_plugin(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        # Create a simple plugin file
        plugin_file = tmp_path / "my_provider.py"
        plugin_file.write_text(
            'PLUGIN_NAME = "My Provider"\n'
            'PLUGIN_VERSION = "2.0.0"\n'
            "def register(manager):\n"
            "    pass\n",
            encoding="utf-8",
        )

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        plugins = mgr.discover()
        assert len(plugins) == 1
        assert plugins[0].name == "My Provider"
        assert plugins[0].version == "2.0.0"

    def test_discover_skips_files_without_register(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        # File without register function
        (tmp_path / "not_a_plugin.py").write_text("# Just a helper\nx = 1\n", encoding="utf-8")

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        plugins = mgr.discover()
        assert len(plugins) == 0

    def test_discover_disabled_returns_empty(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        settings = PluginSettings(enabled=False, plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        plugins = mgr.discover()
        assert plugins == []

    def test_load_plugin_calls_register(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            'PLUGIN_NAME = "Test Plugin"\n'
            "_registered = False\n"
            "def register(manager):\n"
            "    global _registered\n"
            "    _registered = True\n",
            encoding="utf-8",
        )

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        mgr.discover()
        loaded = mgr.load_all()
        assert loaded == 1
        assert mgr.list_plugins()[0].is_loaded is True

    def test_disable_enable_plugin(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        plugin_file = tmp_path / "toggle_plugin.py"
        plugin_file.write_text("def register(manager):\n    pass\n", encoding="utf-8")

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        mgr.discover()

        mgr.disable_plugin("toggle_plugin")
        assert mgr.list_plugins()[0].is_enabled is False
        assert "toggle_plugin" in settings.disabled_plugins

        mgr.enable_plugin("toggle_plugin")
        assert mgr.list_plugins()[0].is_enabled is True
        assert "toggle_plugin" not in settings.disabled_plugins

    def test_get_plugin_dir(self, tmp_path: Path) -> None:
        from bits_whisperer.core.plugin_manager import PluginManager

        settings = PluginSettings(plugin_directory=str(tmp_path))
        mock_pm = MagicMock()
        mgr = PluginManager(settings, mock_pm)
        assert mgr.get_plugin_dir() == tmp_path


# -----------------------------------------------------------------------
# LiveTranscriptionService tests
# -----------------------------------------------------------------------


class TestLiveTranscriptionService:
    """LiveTranscriptionService unit tests (no audio hardware required)."""

    def test_initial_state(self) -> None:
        from bits_whisperer.core.live_transcription import LiveTranscriptionService

        service = LiveTranscriptionService(LiveTranscriptionSettings())
        assert service.is_running is False
        assert service.is_paused is False
        assert service.get_full_transcript() == ""

    def test_state_tracking(self) -> None:
        from bits_whisperer.core.live_transcription import LiveTranscriptionState

        state = LiveTranscriptionState()
        assert state.total_segments == 0
        assert state.full_transcript == []
        assert state.current_text == ""

    def test_list_devices_returns_list(self) -> None:
        from bits_whisperer.core.live_transcription import LiveTranscriptionService

        # May be empty if no sounddevice installed, but should not crash
        result = LiveTranscriptionService.list_input_devices()
        assert isinstance(result, list)


# -----------------------------------------------------------------------
# KeyStore AI entries tests
# -----------------------------------------------------------------------


class TestKeyStoreAIEntries:
    """Verify AI provider entries exist in the key store."""

    def test_anthropic_key_name(self) -> None:
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert "anthropic" in _KEY_NAMES

    def test_azure_openai_key_name(self) -> None:
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert "azure_openai" in _KEY_NAMES

    def test_azure_openai_endpoint_key_name(self) -> None:
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert "azure_openai_endpoint" in _KEY_NAMES

    def test_azure_openai_deployment_key_name(self) -> None:
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert "azure_openai_deployment" in _KEY_NAMES

    def test_total_key_count(self) -> None:
        """Should now have 20 key entries (15 original + 4 AI + 1 Copilot)."""
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert len(_KEY_NAMES) == 20
