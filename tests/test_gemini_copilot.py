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

    def test_is_available_depends_on_sdk(self) -> None:
        from bits_whisperer.core.copilot_service import CopilotService

        mock_ks = MagicMock()
        mock_ks.get_key.return_value = None
        settings = CopilotSettings()
        service = CopilotService(mock_ks, settings)
        # is_available should return a bool and depend on SDK presence
        result = service.is_available()
        assert isinstance(result, bool)

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
        """Should now have 22 key entries (15 original + 4 AI + 1 Copilot + 2 registration)."""
        from bits_whisperer.storage.key_store import _KEY_NAMES

        assert len(_KEY_NAMES) == 22


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


# -----------------------------------------------------------------------
# GitHub OAuth Device Flow tests
# -----------------------------------------------------------------------


class TestDeviceCodeInfo:
    """DeviceCodeInfo frozen dataclass."""

    def test_fields(self) -> None:
        from bits_whisperer.core.github_oauth import DeviceCodeInfo

        info = DeviceCodeInfo(
            device_code="dc_abc",
            user_code="ABCD-1234",
            verification_uri="https://github.com/login/device",
            expires_in=900,
            interval=5,
        )
        assert info.device_code == "dc_abc"
        assert info.user_code == "ABCD-1234"
        assert info.verification_uri == "https://github.com/login/device"
        assert info.expires_in == 900
        assert info.interval == 5

    def test_frozen(self) -> None:
        from bits_whisperer.core.github_oauth import DeviceCodeInfo

        info = DeviceCodeInfo("dc", "UC", "https://example.com", 900, 5)
        with pytest.raises(AttributeError):
            info.user_code = "CHANGED"  # type: ignore[misc]


class TestDeviceFlowErrors:
    """Device flow exception hierarchy."""

    def test_error_hierarchy(self) -> None:
        from bits_whisperer.core.github_oauth import (
            DeviceFlowCancelledError,
            DeviceFlowDeniedError,
            DeviceFlowDisabledError,
            DeviceFlowError,
            DeviceFlowExpiredError,
        )

        assert issubclass(DeviceFlowExpiredError, DeviceFlowError)
        assert issubclass(DeviceFlowDeniedError, DeviceFlowError)
        assert issubclass(DeviceFlowCancelledError, DeviceFlowError)
        assert issubclass(DeviceFlowDisabledError, DeviceFlowError)

    def test_error_messages(self) -> None:
        from bits_whisperer.core.github_oauth import DeviceFlowDeniedError

        err = DeviceFlowDeniedError("User denied")
        assert str(err) == "User denied"


class TestGitHubDeviceFlow:
    """GitHubDeviceFlow unit tests with mocked HTTP."""

    def test_init_requires_client_id(self) -> None:
        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        with pytest.raises(ValueError, match="client_id"):
            GitHubDeviceFlow(client_id="")

    def test_init_default_scopes(self) -> None:
        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        flow = GitHubDeviceFlow(client_id="test_id")
        assert flow._scopes == ["copilot"]

    def test_init_custom_scopes(self) -> None:
        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        flow = GitHubDeviceFlow(client_id="test_id", scopes=["read:user", "copilot"])
        assert flow._scopes == ["read:user", "copilot"]

    def test_request_device_code_success(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        response_data = json.dumps(
            {
                "device_code": "dc_test123",
                "user_code": "WDJB-MJHT",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            }
        ).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        flow = GitHubDeviceFlow(client_id="test_client_id")
        with patch("urllib.request.urlopen", return_value=mock_response):
            info = flow.request_device_code()

        assert info.device_code == "dc_test123"
        assert info.user_code == "WDJB-MJHT"
        assert info.verification_uri == "https://github.com/login/device"
        assert info.expires_in == 900
        assert info.interval == 5

    def test_request_device_code_github_error(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import DeviceFlowError, GitHubDeviceFlow

        response_data = json.dumps(
            {
                "error": "incorrect_client_credentials",
                "error_description": "The client_id is not valid.",
            }
        ).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        flow = GitHubDeviceFlow(client_id="bad_client_id")
        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            pytest.raises(DeviceFlowError, match="incorrect_client_credentials"),
        ):
            flow.request_device_code()

    def test_request_device_code_network_error(self) -> None:
        from bits_whisperer.core.github_oauth import DeviceFlowError, GitHubDeviceFlow

        flow = GitHubDeviceFlow(client_id="test_id")
        with (
            patch("urllib.request.urlopen", side_effect=OSError("Connection refused")),
            pytest.raises(DeviceFlowError, match="Connection refused"),
        ):
            flow.request_device_code()

    def test_poll_for_token_success(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import DeviceCodeInfo, GitHubDeviceFlow

        info = DeviceCodeInfo("dc_test", "UC-TEST", "https://github.com/login/device", 900, 0)

        # First call: pending, second call: success
        responses = [
            json.dumps({"error": "authorization_pending"}).encode(),
            json.dumps({"access_token": "gho_test_token_12345", "scope": "copilot"}).encode(),
        ]
        call_count = [0]

        def mock_urlopen(req, timeout=None):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.read.return_value = responses[idx]
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        statuses: list[str] = []
        flow = GitHubDeviceFlow(client_id="test_id")
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            token = flow.poll_for_token(info, on_status=statuses.append)

        assert token == "gho_test_token_12345"
        assert len(statuses) >= 1

    def test_poll_for_token_cancelled(self) -> None:
        import threading

        from bits_whisperer.core.github_oauth import (
            DeviceCodeInfo,
            DeviceFlowCancelledError,
            GitHubDeviceFlow,
        )

        info = DeviceCodeInfo("dc_test", "UC", "https://example.com", 900, 0)
        cancel = threading.Event()
        cancel.set()  # Already cancelled

        flow = GitHubDeviceFlow(client_id="test_id")
        with pytest.raises(DeviceFlowCancelledError):
            flow.poll_for_token(info, cancel_event=cancel)

    def test_poll_for_token_denied(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import (
            DeviceCodeInfo,
            DeviceFlowDeniedError,
            GitHubDeviceFlow,
        )

        info = DeviceCodeInfo("dc_test", "UC", "https://example.com", 900, 0)
        response_data = json.dumps({"error": "access_denied"}).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        flow = GitHubDeviceFlow(client_id="test_id")
        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            pytest.raises(DeviceFlowDeniedError, match="denied"),
        ):
            flow.poll_for_token(info)

    def test_poll_for_token_expired(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import (
            DeviceCodeInfo,
            DeviceFlowExpiredError,
            GitHubDeviceFlow,
        )

        info = DeviceCodeInfo("dc_test", "UC", "https://example.com", 900, 0)
        response_data = json.dumps({"error": "expired_token"}).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        flow = GitHubDeviceFlow(client_id="test_id")
        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            pytest.raises(DeviceFlowExpiredError, match="expired"),
        ):
            flow.poll_for_token(info)

    def test_poll_for_token_slow_down(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import DeviceCodeInfo, GitHubDeviceFlow

        info = DeviceCodeInfo("dc_test", "UC", "https://example.com", 900, 0)

        # First: slow_down, second: success
        responses = [
            json.dumps({"error": "slow_down"}).encode(),
            json.dumps({"access_token": "gho_after_slow_down"}).encode(),
        ]
        call_count = [0]

        def mock_urlopen(req, timeout=None):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.read.return_value = responses[idx]
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        flow = GitHubDeviceFlow(client_id="test_id")
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            token = flow.poll_for_token(info)

        assert token == "gho_after_slow_down"

    def test_poll_for_token_device_flow_disabled(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import (
            DeviceCodeInfo,
            DeviceFlowDisabledError,
            GitHubDeviceFlow,
        )

        info = DeviceCodeInfo("dc_test", "UC", "https://example.com", 900, 0)
        response_data = json.dumps(
            {
                "error": "device_flow_disabled",
                "error_description": "Device flow is disabled for this OAuth App.",
            }
        ).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        flow = GitHubDeviceFlow(client_id="test_id")
        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            pytest.raises(DeviceFlowDisabledError, match="disabled"),
        ):
            flow.poll_for_token(info)

    def test_validate_token_success(self) -> None:
        import json

        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        user_data = json.dumps({"login": "testuser", "id": 12345}).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = user_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = GitHubDeviceFlow.validate_token("gho_test_token")

        assert result is not None
        assert result["login"] == "testuser"

    def test_validate_token_invalid(self) -> None:
        from bits_whisperer.core.github_oauth import GitHubDeviceFlow

        with patch("urllib.request.urlopen", side_effect=OSError("401 Unauthorized")):
            result = GitHubDeviceFlow.validate_token("invalid_token")

        assert result is None


# -----------------------------------------------------------------------
# CopilotSettings OAuth fields
# -----------------------------------------------------------------------


class TestCopilotSettingsOAuth:
    """New OAuth-related CopilotSettings fields."""

    def test_default_auth_method(self) -> None:
        s = CopilotSettings()
        assert s.auth_method == "cli_login"

    def test_default_oauth_client_id(self) -> None:
        s = CopilotSettings()
        assert s.oauth_client_id == ""

    def test_auth_method_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.copilot.auth_method = "browser_oauth"
            settings.copilot.oauth_client_id = "Iv1.test12345"
            settings.save()

            loaded = AppSettings.load()
            assert loaded.copilot.auth_method == "browser_oauth"
            assert loaded.copilot.oauth_client_id == "Iv1.test12345"

    def test_auth_method_from_dict(self) -> None:
        data = {
            "copilot": {
                "enabled": True,
                "auth_method": "pat",
                "oauth_client_id": "Iv1.abc",
            },
        }
        settings = AppSettings._from_dict(data)
        assert settings.copilot.auth_method == "pat"
        assert settings.copilot.oauth_client_id == "Iv1.abc"

    def test_missing_auth_method_defaults(self) -> None:
        """Old settings without auth_method should get default."""
        data = {
            "copilot": {
                "enabled": True,
                "cli_path": "/some/path",
            },
        }
        settings = AppSettings._from_dict(data)
        assert settings.copilot.auth_method == "cli_login"
        assert settings.copilot.oauth_client_id == ""


# -----------------------------------------------------------------------
# Constants — GITHUB_OAUTH_CLIENT_ID
# -----------------------------------------------------------------------


class TestOAuthConstants:
    """Verify the OAuth client ID constant exists."""

    def test_constant_exists(self) -> None:
        from bits_whisperer.utils.constants import GITHUB_OAUTH_CLIENT_ID

        assert isinstance(GITHUB_OAUTH_CLIENT_ID, str)
