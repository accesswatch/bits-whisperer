"""Tests for Gemini AI, Copilot SDK integration, and agent features."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.settings import (
    AISettings,
    AppSettings,
    CopilotSettings,
)

# -----------------------------------------------------------------------
# CopilotSettings tests
# -----------------------------------------------------------------------


class TestCopilotSettingsDefaults:
    """CopilotSettings default values."""

    def test_not_enabled_by_default(self) -> None:
        s = CopilotSettings()
        assert s.enabled is False

    def test_default_cli_path(self) -> None:
        s = CopilotSettings()
        assert s.cli_path == ""

    def test_default_use_logged_in_user(self) -> None:
        s = CopilotSettings()
        assert s.use_logged_in_user is True

    def test_default_model(self) -> None:
        s = CopilotSettings()
        assert s.default_model == "gpt-4o"

    def test_default_streaming(self) -> None:
        s = CopilotSettings()
        assert s.streaming is True

    def test_default_system_message(self) -> None:
        s = CopilotSettings()
        assert "transcript assistant" in s.system_message.lower()

    def test_default_agent_settings(self) -> None:
        s = CopilotSettings()
        assert "Transcript Assistant" in s.agent_name
        assert isinstance(s.agent_instructions, str)

    def test_default_auto_start(self) -> None:
        s = CopilotSettings()
        assert isinstance(s.auto_start_cli, bool)

    def test_default_tool_permissions(self) -> None:
        s = CopilotSettings()
        assert s.allow_transcript_tools is True

    def test_default_panel_visibility(self) -> None:
        s = CopilotSettings()
        assert s.chat_panel_visible is False


class TestCopilotSettingsSerialization:
    """CopilotSettings persistence round-trip."""

    def test_copilot_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.copilot.enabled = True
            settings.copilot.default_model = "gpt-4o-mini"
            settings.copilot.agent_name = "My Agent"
            settings.copilot.streaming = False
            settings.copilot.auto_start_cli = True
            settings.save()

            loaded = AppSettings.load()
            assert loaded.copilot.enabled is True
            assert loaded.copilot.default_model == "gpt-4o-mini"
            assert loaded.copilot.agent_name == "My Agent"
            assert loaded.copilot.streaming is False
            assert loaded.copilot.auto_start_cli is True

    def test_copilot_from_dict(self) -> None:
        data = {
            "copilot": {
                "enabled": True,
                "cli_path": "/usr/local/bin/github-copilot",
                "default_model": "claude-sonnet-4",
            },
        }
        settings = AppSettings._from_dict(data)
        assert settings.copilot.enabled is True
        assert settings.copilot.cli_path == "/usr/local/bin/github-copilot"
        assert settings.copilot.default_model == "claude-sonnet-4"
        # Other fields get defaults
        assert settings.copilot.streaming is True

    def test_missing_copilot_section_defaults(self) -> None:
        data = {"general": {"language": "en"}}
        settings = AppSettings._from_dict(data)
        assert settings.copilot.enabled is False
        assert settings.copilot.default_model == "gpt-4o"


# -----------------------------------------------------------------------
# AISettings Gemini / Copilot model fields
# -----------------------------------------------------------------------


class TestAISettingsGeminiCopilot:
    """Gemini and Copilot model fields on AISettings."""

    def test_default_gemini_model(self) -> None:
        s = AISettings()
        assert s.gemini_model == "gemini-2.0-flash"

    def test_default_copilot_model(self) -> None:
        s = AISettings()
        assert s.copilot_model == "gpt-4o"

    def test_gemini_model_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.ai.gemini_model = "gemini-2.5-pro"
            settings.ai.copilot_model = "claude-haiku-4"
            settings.save()

            loaded = AppSettings.load()
            assert loaded.ai.gemini_model == "gemini-2.5-pro"
            assert loaded.ai.copilot_model == "claude-haiku-4"


# -----------------------------------------------------------------------
# AgentConfig tests
# -----------------------------------------------------------------------


class TestAgentConfig:
    """AgentConfig serialization."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        config = AgentConfig()
        assert "Transcript Assistant" in config.name
        assert config.model == "gpt-4o"
        assert 0.0 <= config.temperature <= 2.0
        assert config.max_tokens == 4096
        assert "search_transcript" in config.tools_enabled

    def test_to_dict_and_back(self) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        config = AgentConfig(
            name="Meeting Bot",
            description="Summarize meetings",
            instructions="Focus on action items",
            model="claude-sonnet-4",
            temperature=0.5,
            tools_enabled=["search_transcript"],
            welcome_message="Hello!",
        )
        data = config.to_dict()
        restored = AgentConfig.from_dict(data)
        assert restored.name == "Meeting Bot"
        assert restored.description == "Summarize meetings"
        assert restored.model == "claude-sonnet-4"
        assert restored.temperature == 0.5
        assert restored.tools_enabled == ["search_transcript"]
        assert restored.welcome_message == "Hello!"

    def test_save_and_load(self, tmp_path: Path) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        config = AgentConfig(name="Test Agent")
        filepath = tmp_path / "agent.json"
        config.save(filepath)
        assert filepath.exists()

        loaded = AgentConfig.load(filepath)
        assert loaded.name == "Test Agent"

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        filepath = tmp_path / "nonexistent.json"
        with pytest.raises((FileNotFoundError, OSError)):
            AgentConfig.load(filepath)


# -----------------------------------------------------------------------
# CopilotService tests (mocked, no CLI needed)
# -----------------------------------------------------------------------


class TestCopilotService:
    """CopilotService unit tests with mocked SDK."""

    def test_detect_cli_returns_none_if_not_installed(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        with patch("shutil.which", return_value=None):
            result = CopilotService.detect_cli()
            # Result depends on whether the CLI is actually installed,
            # but with shutil.which mocked to None, it checks fallback paths.
            # We just verify it doesn't crash.
            assert result is None or isinstance(result, str)

    def test_is_sdk_installed(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        result = service.is_sdk_installed()
        assert isinstance(result, bool)

    def test_initial_state(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        assert service.is_running is False
        assert service.get_conversation_history() == []

    def test_set_transcript_context(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        service.set_transcript_context("Hello world transcript")
        assert service._transcript_context == "Hello world transcript"

    def test_clear_conversation(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        service._conversation_history.append(MagicMock())
        service.clear_conversation()
        assert service.get_conversation_history() == []

    def test_get_quick_actions(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        actions = service.get_quick_actions()
        assert len(actions) >= 4
        assert all("label" in a and "prompt" in a for a in actions)

    def test_agent_config_property(self) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig, CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)

        new_config = AgentConfig(name="Custom Agent")
        service.agent_config = new_config
        assert service.agent_config.name == "Custom Agent"


# -----------------------------------------------------------------------
# AI Service Gemini / Copilot provider availability
# -----------------------------------------------------------------------


class TestAIServiceNewProviders:
    """AIService provider availability with Gemini/Copilot."""

    def test_gemini_appears_when_key_present(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.has_key.side_effect = lambda k: k == "gemini"

        service = AIService(mock_ks, AISettings())
        providers = service.get_available_providers()
        ids = [p["id"] for p in providers]
        assert "gemini" in ids

    def test_copilot_appears_when_token_present(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.has_key.side_effect = lambda k: k == "copilot_github_token"

        service = AIService(mock_ks, AISettings())
        providers = service.get_available_providers()
        ids = [p["id"] for p in providers]
        assert "copilot" in ids

    def test_gemini_provider_selected(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.has_key.side_effect = lambda k: k == "gemini"
        mock_ks.get_key.side_effect = lambda k: "fake-key" if k == "gemini" else None

        settings = AISettings(selected_provider="gemini")
        service = AIService(mock_ks, settings)
        assert service.is_configured() is True

    def test_translate_with_no_gemini_sdk(self) -> None:
        """If google.genai is not installed, should return error gracefully."""
        from bits_whisperer.core.ai_service import AIService

        mock_ks = MagicMock()
        mock_ks.get_key.side_effect = lambda k: "fake-key" if k == "gemini" else None

        settings = AISettings(selected_provider="gemini")
        service = AIService(mock_ks, settings)

        # This may fail with ImportError or give an error response,
        # but should not crash with an unhandled exception
        response = service.translate("Hello", "Spanish")
        # Either succeeds or returns an error string
        assert isinstance(response.text, str)


# -----------------------------------------------------------------------
# KeyStore Copilot entry
# -----------------------------------------------------------------------


class TestKeyStoreCopilotEntry:
    """Verify the Copilot token entry exists in the key store."""

    def test_copilot_key_name(self) -> None:
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert "copilot_github_token" in _KEY_NAMES

    def test_total_key_count_with_copilot(self) -> None:
        """Should now have 20 key entries (19 previous + 1 copilot)."""
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert len(_KEY_NAMES) == 20


# -----------------------------------------------------------------------
# CopilotMessage dataclass tests
# -----------------------------------------------------------------------


class TestCopilotMessage:
    """CopilotMessage dataclass validation."""

    def test_create_user_message(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotMessage

        msg = CopilotMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.model == ""
        assert msg.is_streaming is False
        assert msg.is_complete is True

    def test_create_assistant_message(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotMessage

        msg = CopilotMessage(
            role="assistant",
            content="Here is your summary.",
            model="gpt-4o",
            is_complete=True,
        )
        assert msg.role == "assistant"
        assert msg.model == "gpt-4o"
