"""Tests for SDK installer, wheel installer, and updater."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.sdk_installer import (
    _SDK_REGISTRY,
    SDKInfo,
    get_missing_sdks,
    get_provider_sdk_info,
    is_frozen,
    is_sdk_available,
)
from bits_whisperer.core.updater import UpdateInfo, Updater
from bits_whisperer.core.wheel_installer import (
    WheelInstaller,
    _EXCLUDED,
    _norm,
    _wheel_is_compatible,
    compatible_tags,
)

# ---------------------------------------------------------------------------
# SDK Installer — Registry
# ---------------------------------------------------------------------------


class TestSDKRegistry:
    """SDK registry completeness and structure."""

    def test_registry_has_all_providers(self) -> None:
        """All major providers should be in the registry."""
        expected = {
            "local_whisper",
            "openai_whisper",
            "google_speech",
            "azure_speech",
            "azure_embedded",
            "deepgram",
            "assemblyai",
            "aws_transcribe",
            "gemini",
            "groq_whisper",
            "rev_ai",
            "speechmatics",
            "elevenlabs",
            "auphonic",
            "windows_speech",
            "vosk",
            "parakeet",
        }
        for key in expected:
            assert key in _SDK_REGISTRY, f"Missing provider in SDK registry: {key}"

    def test_sdk_info_fields(self) -> None:
        info = _SDK_REGISTRY["openai_whisper"]
        assert isinstance(info, SDKInfo)
        assert info.provider_key == "openai_whisper"
        assert info.display_name != ""
        assert info.test_import == "openai"
        assert len(info.pip_packages) > 0

    def test_get_provider_sdk_info(self) -> None:
        info = get_provider_sdk_info("local_whisper")
        assert info is not None
        assert info.provider_key == "local_whisper"
        assert "faster-whisper" in info.pip_packages[0]

    def test_local_whisper_uses_pinned_faster_whisper_range(self) -> None:
        info = get_provider_sdk_info("local_whisper")
        assert info is not None
        assert info.pip_packages == ["faster-whisper>=1.2.1,<2"]

    def test_get_provider_sdk_info_unknown(self) -> None:
        assert get_provider_sdk_info("nonexistent_provider") is None

    def test_elevenlabs_no_extra_packages(self) -> None:
        """ElevenLabs uses httpx (core dep) — no extra packages needed."""
        info = get_provider_sdk_info("elevenlabs")
        assert info is not None
        assert info.pip_packages == []
        assert info.test_import == "httpx"

    def test_auphonic_no_extra_packages(self) -> None:
        """Auphonic uses httpx (core dep) — no extra packages needed."""
        info = get_provider_sdk_info("auphonic")
        assert info is not None
        assert info.pip_packages == []


class TestSDKAvailability:
    """SDK availability checks."""

    def test_unknown_provider_is_available(self) -> None:
        """Unknown providers default to available."""
        assert is_sdk_available("totally_fake_provider") is True

    def test_httpx_based_provider_available(self) -> None:
        """ElevenLabs/Auphonic use httpx which is always installed."""
        assert is_sdk_available("elevenlabs") is True
        assert is_sdk_available("auphonic") is True

    def test_is_frozen_returns_bool(self) -> None:
        # When running tests from source, should return False
        assert is_frozen() is False

    def test_get_missing_sdks_returns_list(self) -> None:
        result = get_missing_sdks()
        assert isinstance(result, list)
        # All items should be SDKInfo
        for item in result:
            assert isinstance(item, SDKInfo)


# ---------------------------------------------------------------------------
# Wheel Installer — Name normalisation
# ---------------------------------------------------------------------------


class TestWheelInstallerNorm:
    """Package name normalisation."""

    def test_lowercase(self) -> None:
        assert _norm("MyPackage") == "mypackage"

    def test_hyphens_to_underscores(self) -> None:
        assert _norm("my-package") == "my_package"

    def test_dots_to_underscores(self) -> None:
        assert _norm("my.package") == "my_package"

    def test_combined(self) -> None:
        assert _norm("My-Cool.Package") == "my_cool_package"


class TestWheelCompatibility:
    """Wheel compatibility detection."""

    def test_compatible_tags_returns_set(self) -> None:
        tags = compatible_tags()
        assert isinstance(tags, set)
        assert len(tags) > 0

    def test_pure_python_wheel_compatible(self) -> None:
        """Pure Python wheels (none-any) should be compatible."""
        assert _wheel_is_compatible("foo-1.0-py3-none-any.whl") is True

    def test_malformed_filename_not_compatible(self) -> None:
        """Wheel with too few parts is not compatible."""
        assert _wheel_is_compatible("foo-1.0.whl") is False

    def test_sdist_not_compatible(self) -> None:
        """Non-wheel files should not match."""
        assert _wheel_is_compatible("foo-1.0.tar.gz") is False


class TestWheelInstallerSatisfaction:
    """Package satisfaction checks."""

    def test_cpu_onnxruntime_not_excluded_for_local_whisper(self) -> None:
        assert "onnxruntime" not in _EXCLUDED
        assert "onnxruntime_gpu" in _EXCLUDED

    def test_bundled_packages_satisfied(self, tmp_path: Path) -> None:
        installer = WheelInstaller(tmp_path)
        # httpx is a bundled package
        assert installer._is_satisfied("httpx") is True

    def test_importable_package_satisfied(self, tmp_path: Path) -> None:
        installer = WheelInstaller(tmp_path)
        assert installer._is_satisfied("pytest") is True

    def test_nonexistent_package_not_satisfied(self, tmp_path: Path) -> None:
        installer = WheelInstaller(tmp_path)
        assert installer._is_satisfied("totally_fake_nonexistent_pkg_xyz") is False


# ---------------------------------------------------------------------------
# Updater
# ---------------------------------------------------------------------------


class TestUpdateInfo:
    """UpdateInfo dataclass."""

    def test_create(self) -> None:
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="1.1.0",
            tag_name="v1.1.0",
            release_name="Version 1.1.0",
            release_notes="Bug fixes",
            download_url="https://example.com/app.exe",
            download_size_mb=25.0,
            html_url="https://github.com/org/repo/releases/tag/v1.1.0",
            published_at="2024-01-15T00:00:00Z",
        )
        assert info.current_version == "1.0.0"
        assert info.latest_version == "1.1.0"
        assert info.download_size_mb == 25.0


class TestUpdater:
    """Updater version checking."""

    def _make_updater(self, version: str = "1.0.0") -> Updater:
        return Updater(
            repo_owner="test-org",
            repo_name="test-repo",
            current_version=version,
            asset_pattern=".exe",
        )

    def test_init(self) -> None:
        u = self._make_updater()
        assert u._current == "1.0.0"
        assert u._owner == "test-org"
        assert u._repo == "test-repo"

    def test_check_for_update_no_newer(self) -> None:
        """When latest == current, should return None."""
        u = self._make_updater("2.0.0")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "name": "v2.0.0",
            "body": "",
            "html_url": "https://example.com",
            "published_at": "2024-01-01",
            "assets": [],
        }
        with patch("httpx.get", return_value=mock_resp):
            result = u.check_for_update()
        assert result is None

    def test_check_for_update_newer_available(self) -> None:
        """When latest > current, should return UpdateInfo."""
        u = self._make_updater("1.0.0")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "name": "Version 2.0.0",
            "body": "New features",
            "html_url": "https://github.com/test/test/releases/tag/v2.0.0",
            "published_at": "2024-06-01",
            "assets": [
                {
                    "name": "app.exe",
                    "browser_download_url": "https://example.com/app.exe",
                    "size": 52428800,
                }
            ],
        }
        with patch("httpx.get", return_value=mock_resp):
            result = u.check_for_update()
        assert result is not None
        assert result.latest_version == "2.0.0"
        assert result.download_url == "https://example.com/app.exe"
        assert result.download_size_mb == pytest.approx(50.0, abs=0.1)

    def test_check_for_update_http_error(self) -> None:
        """HTTP errors should return None, not raise."""
        import httpx

        u = self._make_updater()
        with patch("httpx.get", side_effect=httpx.ConnectError("offline")):
            result = u.check_for_update()
        assert result is None

    def test_check_for_update_no_matching_asset(self) -> None:
        """If no asset matches pattern, fall back to html_url."""
        u = self._make_updater("1.0.0")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "name": "v2.0.0",
            "body": "",
            "html_url": "https://github.com/releases/v2.0.0",
            "published_at": "2024-06-01",
            "assets": [
                {
                    "name": "app.tar.gz",
                    "browser_download_url": "https://example.com/app.tar.gz",
                    "size": 1000000,
                }
            ],
        }
        with patch("httpx.get", return_value=mock_resp):
            result = u.check_for_update()
        assert result is not None
        assert result.download_url == "https://github.com/releases/v2.0.0"

    def test_download_update_no_info(self) -> None:
        """Should raise RuntimeError if no update info available."""
        u = self._make_updater()
        with pytest.raises(RuntimeError, match="No update info"):
            u.download_update()
