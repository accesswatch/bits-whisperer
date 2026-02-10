"""Tests for the remote feature flag service."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.feature_flags import (
    FeatureFlag,
    FeatureFlagConfig,
    FeatureFlagService,
)

# ---------------------------------------------------------------------------
# FeatureFlag dataclass
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    """Tests for the FeatureFlag dataclass."""

    def test_default_values(self):
        flag = FeatureFlag(name="test")
        assert flag.name == "test"
        assert flag.enabled is True
        assert flag.min_version == "0.0.0"
        assert flag.label == ""
        assert flag.description == ""

    def test_custom_values(self):
        flag = FeatureFlag(
            name="live",
            enabled=False,
            min_version="2.0.0",
            label="Live Transcription",
            description="Real-time mic",
        )
        assert flag.name == "live"
        assert flag.enabled is False
        assert flag.min_version == "2.0.0"
        assert flag.label == "Live Transcription"
        assert flag.description == "Real-time mic"

    def test_frozen(self):
        flag = FeatureFlag(name="test")
        with pytest.raises(AttributeError):
            flag.enabled = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FeatureFlagConfig
# ---------------------------------------------------------------------------


class TestFeatureFlagConfig:
    """Tests for FeatureFlagConfig serialisation."""

    def test_to_dict_and_from_dict_roundtrip(self):
        config = FeatureFlagConfig(
            version=1,
            description="Test config",
            features={
                "alpha": FeatureFlag(
                    name="alpha",
                    enabled=True,
                    min_version="1.0.0",
                    label="Alpha",
                    description="Alpha feature",
                ),
                "beta": FeatureFlag(
                    name="beta",
                    enabled=False,
                    min_version="2.0.0",
                    label="Beta",
                    description="Beta feature",
                ),
            },
            fetched_at=1234567890.0,
        )

        data = config.to_dict()
        restored = FeatureFlagConfig.from_dict(data)

        assert restored.version == 1
        assert restored.description == "Test config"
        assert len(restored.features) == 2
        assert restored.features["alpha"].enabled is True
        assert restored.features["beta"].enabled is False
        assert restored.features["beta"].min_version == "2.0.0"
        assert restored.fetched_at == 1234567890.0

    def test_from_dict_unknown_keys_ignored(self):
        data = {
            "version": 1,
            "features": {
                "test": {
                    "enabled": True,
                    "min_version": "1.0.0",
                    "label": "Test",
                    "future_field": "should be ignored",
                },
            },
        }
        config = FeatureFlagConfig.from_dict(data)
        assert "test" in config.features
        assert config.features["test"].enabled is True

    def test_from_dict_empty(self):
        config = FeatureFlagConfig.from_dict({})
        assert config.version == 1
        assert len(config.features) == 0
        assert config.fetched_at == 0.0

    def test_from_dict_non_dict_feature_entries_skipped(self):
        data = {
            "features": {
                "valid": {"enabled": True},
                "invalid": "not a dict",
            },
        }
        config = FeatureFlagConfig.from_dict(data)
        assert "valid" in config.features
        assert "invalid" not in config.features


# ---------------------------------------------------------------------------
# FeatureFlagService — core logic
# ---------------------------------------------------------------------------


class TestFeatureFlagServiceCore:
    """Tests for FeatureFlagService without network calls."""

    def _make_service(self, **kwargs) -> FeatureFlagService:
        """Create a service with a non-existent cache path."""
        defaults = {
            "remote_url": "https://example.com/flags.json",
            "cache_path": Path("/nonexistent/cache.json"),
            "app_version": "1.0.0",
        }
        defaults.update(kwargs)
        return FeatureFlagService(**defaults)

    def test_unknown_feature_enabled_by_default(self):
        service = self._make_service()
        assert service.is_enabled("nonexistent_feature") is True

    def test_disabled_feature_returns_false(self):
        service = self._make_service()
        service._config = FeatureFlagConfig(
            features={
                "disabled_one": FeatureFlag(name="disabled_one", enabled=False),
            },
        )
        service._loaded = True
        assert service.is_enabled("disabled_one") is False

    def test_enabled_feature_returns_true(self):
        service = self._make_service()
        service._config = FeatureFlagConfig(
            features={
                "enabled_one": FeatureFlag(name="enabled_one", enabled=True),
            },
        )
        service._loaded = True
        assert service.is_enabled("enabled_one") is True

    def test_version_gate_too_new(self):
        service = self._make_service(app_version="1.0.0")
        service._config = FeatureFlagConfig(
            features={
                "future": FeatureFlag(
                    name="future",
                    enabled=True,
                    min_version="2.0.0",
                ),
            },
        )
        service._loaded = True
        assert service.is_enabled("future") is False

    def test_version_gate_satisfied(self):
        service = self._make_service(app_version="2.5.0")
        service._config = FeatureFlagConfig(
            features={
                "old": FeatureFlag(
                    name="old",
                    enabled=True,
                    min_version="1.0.0",
                ),
            },
        )
        service._loaded = True
        assert service.is_enabled("old") is True

    def test_version_gate_exact_match(self):
        service = self._make_service(app_version="1.5.0")
        service._config = FeatureFlagConfig(
            features={
                "exact": FeatureFlag(
                    name="exact",
                    enabled=True,
                    min_version="1.5.0",
                ),
            },
        )
        service._loaded = True
        assert service.is_enabled("exact") is True

    def test_local_override_force_enable(self):
        service = self._make_service(
            local_overrides={"disabled_one": True},
        )
        service._config = FeatureFlagConfig(
            features={
                "disabled_one": FeatureFlag(name="disabled_one", enabled=False),
            },
        )
        service._loaded = True
        # Override wins over remote config
        assert service.is_enabled("disabled_one") is True

    def test_local_override_force_disable(self):
        service = self._make_service(
            local_overrides={"enabled_one": False},
        )
        service._config = FeatureFlagConfig(
            features={
                "enabled_one": FeatureFlag(name="enabled_one", enabled=True),
            },
        )
        service._loaded = True
        assert service.is_enabled("enabled_one") is False

    def test_set_and_clear_override(self):
        service = self._make_service()
        service._config = FeatureFlagConfig(
            features={
                "test": FeatureFlag(name="test", enabled=True),
            },
        )
        service._loaded = True

        # Initially enabled
        assert service.is_enabled("test") is True

        # Override to disable
        service.set_override("test", False)
        assert service.is_enabled("test") is False

        # Clear override — reverts to remote config
        service.clear_override("test")
        assert service.is_enabled("test") is True

    def test_get_overrides(self):
        service = self._make_service(
            local_overrides={"a": True, "b": False},
        )
        overrides = service.get_overrides()
        assert overrides == {"a": True, "b": False}

    def test_get_flag_existing(self):
        service = self._make_service()
        flag = FeatureFlag(name="test", label="Test Feature")
        service._config = FeatureFlagConfig(features={"test": flag})
        service._loaded = True

        result = service.get_flag("test")
        assert result is not None
        assert result.label == "Test Feature"

    def test_get_flag_missing(self):
        service = self._make_service()
        assert service.get_flag("nonexistent") is None

    def test_get_all_flags(self):
        service = self._make_service()
        service._config = FeatureFlagConfig(
            features={
                "a": FeatureFlag(name="a"),
                "b": FeatureFlag(name="b"),
            },
        )
        service._loaded = True
        flags = service.get_all_flags()
        assert len(flags) == 2
        assert "a" in flags
        assert "b" in flags

    def test_properties(self):
        service = self._make_service()
        assert service.remote_url == "https://example.com/flags.json"
        assert service.is_loaded is False
        assert service.last_fetched == 0.0


# ---------------------------------------------------------------------------
# FeatureFlagService — cache persistence
# ---------------------------------------------------------------------------


class TestFeatureFlagServiceCache:
    """Tests for cache load/save."""

    def test_save_and_load_cache(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        service = FeatureFlagService(
            remote_url="https://example.com/flags.json",
            cache_path=cache_file,
            app_version="1.0.0",
        )

        # Inject a config and save it
        service._config = FeatureFlagConfig(
            version=1,
            features={
                "test": FeatureFlag(
                    name="test",
                    enabled=True,
                    label="Test",
                ),
            },
            fetched_at=time.time(),
        )
        service._save_cache()

        assert cache_file.exists()

        # Create a new service that should load from cache
        service2 = FeatureFlagService(
            remote_url="https://example.com/flags.json",
            cache_path=cache_file,
            app_version="1.0.0",
        )

        assert service2.is_loaded is True
        assert service2.is_enabled("test") is True

    def test_corrupt_cache_falls_back_to_defaults(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not valid json {{{", encoding="utf-8")

        service = FeatureFlagService(
            remote_url="https://example.com/flags.json",
            cache_path=cache_file,
            app_version="1.0.0",
        )

        # Should not crash; is_loaded stays False, everything enabled by default
        assert service.is_loaded is False
        assert service.is_enabled("anything") is True

    def test_missing_cache_is_fine(self, tmp_path):
        cache_file = tmp_path / "nonexistent" / "cache.json"

        service = FeatureFlagService(
            remote_url="https://example.com/flags.json",
            cache_path=cache_file,
            app_version="1.0.0",
        )
        assert service.is_loaded is False


# ---------------------------------------------------------------------------
# FeatureFlagService — remote fetch (mocked)
# ---------------------------------------------------------------------------


class TestFeatureFlagServiceFetch:
    """Tests for remote fetching with mocked httpx."""

    @pytest.fixture
    def sample_remote_json(self):
        return {
            "version": 1,
            "description": "Test flags",
            "features": {
                "live_transcription": {
                    "enabled": True,
                    "min_version": "1.0.0",
                    "label": "Live Transcription",
                    "description": "Mic transcription",
                },
                "beta_feature": {
                    "enabled": False,
                    "min_version": "1.0.0",
                    "label": "Beta",
                    "description": "Not ready",
                },
                "future_feature": {
                    "enabled": True,
                    "min_version": "99.0.0",
                    "label": "Future",
                    "description": "Needs v99",
                },
            },
        }

    def test_successful_fetch(self, tmp_path, sample_remote_json):
        cache_file = tmp_path / "cache.json"

        mock_response = MagicMock()
        mock_response.json.return_value = sample_remote_json
        mock_response.raise_for_status = MagicMock()

        with patch("bits_whisperer.core.feature_flags.httpx.get", return_value=mock_response):
            service = FeatureFlagService(
                remote_url="https://example.com/flags.json",
                cache_path=cache_file,
                app_version="1.0.0",
            )
            result = service.refresh(force=True)

        assert result is True
        assert service.is_loaded is True
        assert service.is_enabled("live_transcription") is True
        assert service.is_enabled("beta_feature") is False
        assert service.is_enabled("future_feature") is False  # version gate
        assert cache_file.exists()

    def test_fetch_network_failure_uses_cache(self, tmp_path, sample_remote_json):
        cache_file = tmp_path / "cache.json"

        # Pre-populate cache
        config = FeatureFlagConfig.from_dict(sample_remote_json)
        config.fetched_at = time.time()
        cache_file.write_text(
            json.dumps(config.to_dict(), indent=2),
            encoding="utf-8",
        )

        import httpx as httpx_mod

        with patch(
            "bits_whisperer.core.feature_flags.httpx.get",
            side_effect=httpx_mod.ConnectError("Network down"),
        ):
            service = FeatureFlagService(
                remote_url="https://example.com/flags.json",
                cache_path=cache_file,
                app_version="1.0.0",
            )
            result = service.refresh(force=True)

        assert result is False
        # Should still work from cache
        assert service.is_loaded is True
        assert service.is_enabled("live_transcription") is True
        assert service.is_enabled("beta_feature") is False

    def test_fetch_invalid_json(self, tmp_path):
        cache_file = tmp_path / "cache.json"

        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_response.raise_for_status = MagicMock()

        with patch("bits_whisperer.core.feature_flags.httpx.get", return_value=mock_response):
            service = FeatureFlagService(
                remote_url="https://example.com/flags.json",
                cache_path=cache_file,
                app_version="1.0.0",
            )
            result = service.refresh(force=True)

        assert result is False

    def test_ttl_skips_fresh_cache(self, tmp_path, sample_remote_json):
        cache_file = tmp_path / "cache.json"

        # Pre-populate cache with recent timestamp
        config = FeatureFlagConfig.from_dict(sample_remote_json)
        config.fetched_at = time.time()  # Fresh
        cache_file.write_text(
            json.dumps(config.to_dict(), indent=2),
            encoding="utf-8",
        )

        with patch("bits_whisperer.core.feature_flags.httpx.get") as mock_get:
            service = FeatureFlagService(
                remote_url="https://example.com/flags.json",
                cache_path=cache_file,
                ttl_hours=24.0,
                app_version="1.0.0",
            )
            result = service.refresh(force=False)

        assert result is True
        mock_get.assert_not_called()  # Should skip fetch

    def test_ttl_triggers_fetch_for_stale_cache(self, tmp_path, sample_remote_json):
        cache_file = tmp_path / "cache.json"

        # Pre-populate cache with old timestamp
        config = FeatureFlagConfig.from_dict(sample_remote_json)
        config.fetched_at = time.time() - 100_000  # Way past TTL
        cache_file.write_text(
            json.dumps(config.to_dict(), indent=2),
            encoding="utf-8",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = sample_remote_json
        mock_response.raise_for_status = MagicMock()

        with patch("bits_whisperer.core.feature_flags.httpx.get", return_value=mock_response):
            service = FeatureFlagService(
                remote_url="https://example.com/flags.json",
                cache_path=cache_file,
                ttl_hours=24.0,
                app_version="1.0.0",
            )
            result = service.refresh(force=False)

        assert result is True


# ---------------------------------------------------------------------------
# FeatureFlagConfig from actual feature_flags.json
# ---------------------------------------------------------------------------


class TestFeatureFlagsJsonFile:
    """Validate the actual feature_flags.json file in the repo."""

    @pytest.fixture
    def flags_file(self):
        path = Path(__file__).parent.parent / "feature_flags.json"
        if not path.exists():
            pytest.skip("feature_flags.json not found in repo root")
        return path

    def test_valid_json(self, flags_file):
        data = json.loads(flags_file.read_text("utf-8"))
        assert "version" in data
        assert "features" in data

    def test_all_features_have_required_keys(self, flags_file):
        data = json.loads(flags_file.read_text("utf-8"))
        for name, entry in data["features"].items():
            assert "enabled" in entry, f"Feature '{name}' missing 'enabled'"
            assert "min_version" in entry, f"Feature '{name}' missing 'min_version'"
            assert "label" in entry, f"Feature '{name}' missing 'label'"
            assert "description" in entry, f"Feature '{name}' missing 'description'"

    def test_parses_into_config(self, flags_file):
        data = json.loads(flags_file.read_text("utf-8"))
        config = FeatureFlagConfig.from_dict(data)
        assert len(config.features) >= 10  # We defined 12 features


# ---------------------------------------------------------------------------
# Settings integration
# ---------------------------------------------------------------------------


class TestFeatureFlagSettings:
    """Tests for FeatureFlagSettings in AppSettings."""

    def test_settings_has_feature_flags(self):
        from bits_whisperer.core.settings import AppSettings

        settings = AppSettings()
        assert hasattr(settings, "feature_flags")
        assert settings.feature_flags.enabled is True
        assert settings.feature_flags.remote_url == ""
        assert settings.feature_flags.refresh_hours == 24.0
        assert settings.feature_flags.local_overrides == {}

    def test_roundtrip_serialization(self):
        from bits_whisperer.core.settings import AppSettings, FeatureFlagSettings

        settings = AppSettings()
        settings.feature_flags = FeatureFlagSettings(
            enabled=False,
            remote_url="https://custom.example.com/flags.json",
            refresh_hours=12.0,
            local_overrides={"test": True, "beta": False},
        )

        # Serialize and deserialize
        from dataclasses import asdict

        data = asdict(settings)
        restored = AppSettings._from_dict(data)

        assert restored.feature_flags.enabled is False
        assert restored.feature_flags.remote_url == "https://custom.example.com/flags.json"
        assert restored.feature_flags.refresh_hours == 12.0
        assert restored.feature_flags.local_overrides == {"test": True, "beta": False}

    def test_from_dict_missing_feature_flags_uses_defaults(self):
        from bits_whisperer.core.settings import AppSettings

        # Old settings file without feature_flags section
        data = {"general": {"language": "en"}}
        settings = AppSettings._from_dict(data)
        assert settings.feature_flags.enabled is True
        assert settings.feature_flags.local_overrides == {}
