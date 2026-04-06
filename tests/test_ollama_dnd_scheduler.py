"""Tests for Ollama HTTP adapter, DND monitor, scheduler, and related settings."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from bits_whisperer.core.settings import (
    AISettings,
    AppSettings,
    DNDSettings,
    SchedulerSettings,
)

# -----------------------------------------------------------------------
# DNDSettings tests
# -----------------------------------------------------------------------


class TestDNDSettingsDefaults:
    """DNDSettings default values."""

    def test_enabled_by_default(self) -> None:
        s = DNDSettings()
        assert s.enabled is True

    def test_poll_interval_default(self) -> None:
        s = DNDSettings()
        assert s.poll_interval_seconds == 5.0

    def test_pause_transcription_default(self) -> None:
        s = DNDSettings()
        assert s.pause_transcription is True

    def test_pause_live_transcription_default(self) -> None:
        s = DNDSettings()
        assert s.pause_live_transcription is True

    def test_show_alert_on_pause_default(self) -> None:
        s = DNDSettings()
        assert s.show_alert_on_pause is True

    def test_auto_resume_default(self) -> None:
        s = DNDSettings()
        assert s.auto_resume_on_dnd_off is True


class TestDNDSettingsCustom:
    """DNDSettings with custom values."""

    def test_disabled(self) -> None:
        s = DNDSettings(enabled=False)
        assert s.enabled is False

    def test_custom_interval(self) -> None:
        s = DNDSettings(poll_interval_seconds=10.0)
        assert s.poll_interval_seconds == 10.0

    def test_no_pause(self) -> None:
        s = DNDSettings(pause_transcription=False)
        assert s.pause_transcription is False


# -----------------------------------------------------------------------
# SchedulerSettings tests
# -----------------------------------------------------------------------


class TestSchedulerSettingsDefaults:
    """SchedulerSettings default values."""

    def test_enabled_by_default(self) -> None:
        s = SchedulerSettings()
        assert s.enabled is True

    def test_model_cache_prune_hours(self) -> None:
        s = SchedulerSettings()
        assert s.model_cache_prune_hours == 24.0

    def test_health_check_minutes(self) -> None:
        s = SchedulerSettings()
        assert s.health_check_minutes == 30.0

    def test_catalog_refresh_hours(self) -> None:
        s = SchedulerSettings()
        assert s.catalog_refresh_hours == 12.0


# -----------------------------------------------------------------------
# AISettings — Ollama fields
# -----------------------------------------------------------------------


class TestAISettingsOllamaFields:
    """AISettings Ollama-related field defaults."""

    def test_ollama_mode_default(self) -> None:
        s = AISettings()
        assert s.ollama_mode == "http"

    def test_ollama_cli_path_default(self) -> None:
        s = AISettings()
        assert s.ollama_cli_path == ""

    def test_ollama_cache_quota_default(self) -> None:
        s = AISettings()
        assert s.ollama_cache_quota_gib == 20.0

    def test_ollama_concurrent_pulls_default(self) -> None:
        s = AISettings()
        assert s.ollama_concurrent_pulls == 1

    def test_default_chat_model_default(self) -> None:
        s = AISettings()
        assert s.default_chat_model == ""

    def test_custom_values(self) -> None:
        s = AISettings(
            ollama_mode="cli",
            ollama_cli_path="/usr/local/bin/ollama",
            ollama_cache_quota_gib=50.0,
            ollama_concurrent_pulls=3,
            default_chat_model="llama3.2:8b",
        )
        assert s.ollama_mode == "cli"
        assert s.ollama_cli_path == "/usr/local/bin/ollama"
        assert s.ollama_cache_quota_gib == 50.0
        assert s.ollama_concurrent_pulls == 3
        assert s.default_chat_model == "llama3.2:8b"


# -----------------------------------------------------------------------
# Settings roundtrip with new fields
# -----------------------------------------------------------------------


class TestSettingsRoundtrip:
    """AppSettings persistence with DND, Scheduler, and Ollama fields."""

    def test_dnd_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.dnd.enabled = False
            settings.dnd.poll_interval_seconds = 15.0
            settings.dnd.pause_transcription = False
            settings.save()

            loaded = AppSettings.load()
            assert loaded.dnd.enabled is False
            assert loaded.dnd.poll_interval_seconds == 15.0
            assert loaded.dnd.pause_transcription is False

    def test_scheduler_settings_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.scheduler.enabled = False
            settings.scheduler.model_cache_prune_hours = 48.0
            settings.save()

            loaded = AppSettings.load()
            assert loaded.scheduler.enabled is False
            assert loaded.scheduler.model_cache_prune_hours == 48.0

    def test_ollama_fields_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            settings = AppSettings()
            settings.ai.ollama_mode = "cli"
            settings.ai.ollama_cli_path = "C:\\ollama\\ollama.exe"
            settings.ai.default_chat_model = "mistral:7b"
            settings.save()

            loaded = AppSettings.load()
            assert loaded.ai.ollama_mode == "cli"
            assert loaded.ai.ollama_cli_path == "C:\\ollama\\ollama.exe"
            assert loaded.ai.default_chat_model == "mistral:7b"


# -----------------------------------------------------------------------
# CancelToken tests
# -----------------------------------------------------------------------


class TestCancelToken:
    """CancelToken basic lifecycle."""

    def test_not_cancelled_initially(self) -> None:
        from bits_whisperer.core.ollama_adapter import CancelToken

        token = CancelToken()
        assert token.cancelled is False

    def test_cancel_sets_flag(self) -> None:
        from bits_whisperer.core.ollama_adapter import CancelToken

        token = CancelToken()
        token.cancel()
        assert token.cancelled is True

    def test_thread_safe_cancel(self) -> None:
        from bits_whisperer.core.ollama_adapter import CancelToken

        token = CancelToken()
        results: list[bool] = []

        def cancel_from_thread() -> None:
            token.cancel()
            results.append(token.cancelled)

        t = threading.Thread(target=cancel_from_thread)
        t.start()
        t.join()
        assert results == [True]
        assert token.cancelled is True


# -----------------------------------------------------------------------
# OllamaModelMetadata tests
# -----------------------------------------------------------------------


class TestOllamaModelMetadata:
    """OllamaModelMetadata dataclass."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaModelMetadata

        m = OllamaModelMetadata(model_id="llama3.2", name="llama3.2")
        assert m.name == "llama3.2"
        assert m.size_bytes == 0
        assert m.parameter_size == ""

    def test_post_init_size_gb(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaModelMetadata

        m = OllamaModelMetadata(model_id="test", name="test", size_bytes=5_000_000_000)
        assert m.size_gb > 0

    def test_custom_fields(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaModelMetadata

        m = OllamaModelMetadata(
            model_id="mistral:7b",
            name="mistral:7b",
            size_bytes=4_000_000_000,
            parameter_size="7B",
            family="mistral",
            quantization="Q4_K_M",
        )
        assert m.parameter_size == "7B"
        assert m.family == "mistral"
        assert m.quantization == "Q4_K_M"


# -----------------------------------------------------------------------
# OllamaHealthStatus tests
# -----------------------------------------------------------------------


class TestOllamaHealthStatus:
    """OllamaHealthStatus dataclass."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaHealthStatus

        h = OllamaHealthStatus()
        assert h.reachable is False
        assert h.version == ""
        assert h.error == ""


# -----------------------------------------------------------------------
# OllamaHTTPAdapter tests (mocked — no real server)
# -----------------------------------------------------------------------


class TestOllamaHTTPAdapterHealthCheck:
    """OllamaHTTPAdapter.health_check with mocked HTTP."""

    def test_health_check_success(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaHTTPAdapter

        adapter = OllamaHTTPAdapter(
            endpoint="http://localhost:11434",
            cli_fallback=False,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "0.5.0"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            status = adapter.health_check()

        assert status.reachable is True
        assert status.version == "0.5.0"

    def test_health_check_failure(self) -> None:
        import httpx

        from bits_whisperer.core.ollama_adapter import OllamaHTTPAdapter

        adapter = OllamaHTTPAdapter(
            endpoint="http://localhost:11434",
            cli_fallback=False,
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch("httpx.Client", return_value=mock_client):
            status = adapter.health_check()

        assert status.reachable is False
        assert "refused" in status.error


class TestOllamaHTTPAdapterListModels:
    """OllamaHTTPAdapter.list_models with mocked HTTP."""

    def test_list_models_success(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaHTTPAdapter

        adapter = OllamaHTTPAdapter(
            endpoint="http://localhost:11434",
            cli_fallback=False,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {
                    "name": "llama3.2:latest",
                    "size": 2_000_000_000,
                    "details": {
                        "parameter_size": "3B",
                        "family": "llama",
                        "quantization_level": "Q4_K_M",
                    },
                },
                {
                    "name": "mistral:7b",
                    "size": 4_000_000_000,
                    "details": {
                        "parameter_size": "7B",
                        "family": "mistral",
                    },
                },
            ]
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            models = adapter.list_models()

        assert len(models) == 2
        assert models[0].name == "llama3.2:latest"
        assert models[0].parameter_size == "3B"
        assert models[1].name == "mistral:7b"


class TestOllamaHTTPAdapterDeleteModel:
    """OllamaHTTPAdapter.delete_model with mocked HTTP."""

    def test_delete_model_success(self) -> None:
        from bits_whisperer.core.ollama_adapter import OllamaHTTPAdapter

        adapter = OllamaHTTPAdapter(
            endpoint="http://localhost:11434",
            cli_fallback=False,
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response

        with (
            patch("httpx.Client", return_value=mock_client),
            patch("filelock.FileLock", return_value=MagicMock()),
        ):
            result = adapter.delete_model("old-model")

        assert result is True

    def test_delete_model_not_found(self) -> None:
        import httpx

        from bits_whisperer.core.ollama_adapter import OllamaHTTPAdapter

        adapter = OllamaHTTPAdapter(
            endpoint="http://localhost:11434",
            cli_fallback=False,
        )
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response

        with (
            patch("httpx.Client", return_value=mock_client),
            patch("filelock.FileLock", return_value=MagicMock()),
        ):
            result = adapter.delete_model("nonexistent")

        assert result is False


# -----------------------------------------------------------------------
# DND monitor tests
# -----------------------------------------------------------------------


class TestDNDDetect:
    """detect_dnd() function with mocked platform layer."""

    def test_detect_dnd_returns_status(self) -> None:
        from bits_whisperer.core.dnd_monitor import DNDStatus, detect_dnd

        with (
            patch(
                "bits_whisperer.core.dnd_monitor._detect_dnd_windows",
                return_value=DNDStatus(active=True, mode="focus", source="winrt"),
            ),
            patch("bits_whisperer.core.dnd_monitor.platform") as mock_platform,
        ):
            mock_platform.system.return_value = "Windows"
            status = detect_dnd()
            assert isinstance(status, DNDStatus)


class TestDNDMonitorLifecycle:
    """DNDMonitor start/stop lifecycle."""

    def test_start_and_stop(self) -> None:
        from bits_whisperer.core.dnd_monitor import DNDMonitor

        callback = MagicMock()
        monitor = DNDMonitor(
            poll_interval=0.1,
            on_dnd_changed=callback,
        )
        with patch("bits_whisperer.core.dnd_monitor.detect_dnd") as mock_detect:
            mock_detect.return_value = MagicMock(active=False, mode="off")
            monitor.start()
            assert monitor._running is True
            monitor.stop()
            assert monitor._running is False

    def test_stop_without_start_is_safe(self) -> None:
        from bits_whisperer.core.dnd_monitor import DNDMonitor

        monitor = DNDMonitor(poll_interval=1.0)
        monitor.stop()  # Should not raise
        assert monitor._running is False


class TestDNDEvent:
    """DNDEvent dataclass."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.dnd_monitor import DNDEvent

        e = DNDEvent()
        assert e.previous_active is False
        assert e.current_active is False
        assert e.mode == ""

    def test_custom_values(self) -> None:
        from bits_whisperer.core.dnd_monitor import DNDEvent

        e = DNDEvent(
            previous_active=False,
            current_active=True,
            mode="focus",
        )
        assert e.current_active is True
        assert e.mode == "focus"


# -----------------------------------------------------------------------
# Scheduler service tests
# -----------------------------------------------------------------------


class TestScheduledJob:
    """ScheduledJob dataclass."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.scheduler_service import ScheduledJob

        job = ScheduledJob(
            job_id="test",
            name="Test Job",
            func=lambda: None,
            interval_seconds=60.0,
        )
        assert job.enabled is True
        assert job.job_id == "test"
        assert job.name == "Test Job"


class TestSchedulerServiceLifecycle:
    """SchedulerService start/stop with timer fallback."""

    def test_start_stop_timer_backend(self) -> None:
        from bits_whisperer.core.scheduler_service import (
            ScheduledJob,
            SchedulerService,
        )

        callback = MagicMock()
        svc = SchedulerService(settings=SchedulerSettings())
        svc.register_job(
            ScheduledJob(
                job_id="test_job",
                name="Test Job",
                func=callback,
                interval_seconds=9999,  # long enough to never fire in test
            )
        )

        # Force timer fallback by blocking APScheduler import
        with patch.dict("sys.modules", {"apscheduler": None}):
            svc.start()
            assert svc.is_running is True
            svc.stop()
            assert svc.is_running is False

    def test_disabled_settings_no_start(self) -> None:
        from bits_whisperer.core.scheduler_service import SchedulerService

        settings = SchedulerSettings(enabled=False)
        svc = SchedulerService(settings=settings)
        svc.start()
        assert svc.is_running is False

    def test_double_start_is_safe(self) -> None:
        from bits_whisperer.core.scheduler_service import SchedulerService

        svc = SchedulerService(settings=SchedulerSettings())
        with patch.dict("sys.modules", {"apscheduler": None}):
            svc.start()
            svc.start()  # Should not raise
            assert svc.is_running is True
            svc.stop()

    def test_stop_without_start_is_safe(self) -> None:
        from bits_whisperer.core.scheduler_service import SchedulerService

        svc = SchedulerService(settings=SchedulerSettings())
        svc.stop()  # Should not raise
        assert svc.is_running is False


# -----------------------------------------------------------------------
# UnifiedModelInfo tests (model_manager integration)
# -----------------------------------------------------------------------


class TestUnifiedModelInfo:
    """UnifiedModelInfo dataclass from model_manager."""

    def test_whisper_model_info(self) -> None:
        from bits_whisperer.core.model_manager import UnifiedModelInfo

        info = UnifiedModelInfo(
            provider="whisper",
            model_id="base",
            name="Base",
            status="downloaded",
        )
        assert info.provider == "whisper"
        assert info.status == "downloaded"
        assert info.parameter_size == ""

    def test_ollama_model_info(self) -> None:
        from bits_whisperer.core.model_manager import UnifiedModelInfo

        info = UnifiedModelInfo(
            provider="ollama",
            model_id="llama3.2:latest",
            name="Llama 3.2",
            status="downloaded",
            parameter_size="3B",
            size_gb=1.86,
        )
        assert info.provider == "ollama"
        assert info.parameter_size == "3B"
        assert info.size_gb == 1.86


# -----------------------------------------------------------------------
# Feature flag tests for new flags
# -----------------------------------------------------------------------


class TestNewFeatureFlags:
    """New feature flags exist in the config."""

    def test_ollama_native_flag_exists(self) -> None:
        import json

        config = json.loads(Path("feature_flags.json").read_text(encoding="utf-8"))
        flags = config.get("features", {})
        assert "ollama_native" in flags
        assert flags["ollama_native"]["enabled"] is True

    def test_dnd_monitor_flag_exists(self) -> None:
        import json

        config = json.loads(Path("feature_flags.json").read_text(encoding="utf-8"))
        flags = config.get("features", {})
        assert "dnd_monitor" in flags

    def test_scheduler_flag_exists(self) -> None:
        import json

        config = json.loads(Path("feature_flags.json").read_text(encoding="utf-8"))
        flags = config.get("features", {})
        assert "scheduler" in flags

    def test_model_manager_treeview_flag(self) -> None:
        import json

        config = json.loads(Path("feature_flags.json").read_text(encoding="utf-8"))
        flags = config.get("features", {})
        assert "model_manager_treeview" in flags
