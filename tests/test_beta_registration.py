"""Tests for beta programme, What's New change detection, and registration.

Covers:
- BetaService: invitation verification, hash_code, is_beta_tester,
  revoke_beta, release notes fetching, cache fallback
- WhatsNewState / FeatureChange: dataclass serialisation
- detect_changes: version bump, beta toggle, per-feature add/enable/disable
- snapshot_current_state: state persistence
- FeatureFlagService.is_enabled_for_beta: beta_enabled vs enabled routing
- BITS_RegistrationService: device ID, verify_key, offline fallback,
  rate limiting, integrity check, status messages, clear_registration
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.beta_service import (
    _BETA_KEYSTORE_KEY,
    BetaService,
    FeatureChange,
    WhatsNewState,
)
from bits_whisperer.core.feature_flags import (
    FeatureFlag,
    FeatureFlagService,
)

# registration_service requires `requests` which may not be installed
_has_requests = True
try:
    from bits_whisperer.core.registration_service import (
        BITS_RegistrationService,
    )
except ModuleNotFoundError:
    _has_requests = False

_skip_no_requests = pytest.mark.skipif(
    not _has_requests,
    reason="requests library not installed",
)


# ===================================================================== #
# FeatureChange dataclass                                                #
# ===================================================================== #


class TestFeatureChange:
    """FeatureChange dataclass basics."""

    def test_required_fields(self) -> None:
        fc = FeatureChange(
            feature_name="live",
            label="Live",
            description="Real-time",
            change_type="added",
        )
        assert fc.feature_name == "live"
        assert fc.label == "Live"
        assert fc.description == "Real-time"
        assert fc.change_type == "added"

    def test_defaults(self) -> None:
        fc = FeatureChange(
            feature_name="x",
            label="X",
            description="Desc",
            change_type="enabled",
        )
        assert fc.release_notes == ""
        assert fc.added_in_version == ""

    def test_frozen(self) -> None:
        fc = FeatureChange(
            feature_name="x",
            label="X",
            description="Desc",
            change_type="added",
        )
        with pytest.raises(AttributeError):
            fc.feature_name = "y"  # type: ignore[misc]


# ===================================================================== #
# WhatsNewState dataclass                                                #
# ===================================================================== #


class TestWhatsNewState:
    """WhatsNewState serialisation and defaults."""

    def test_defaults(self) -> None:
        state = WhatsNewState()
        assert state.last_seen_version == ""
        assert state.seen_flags == {}
        assert state.last_checked == 0.0
        assert state.beta_mode is False

    def test_to_dict(self) -> None:
        state = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": True},
            last_checked=100.0,
            beta_mode=True,
        )
        d = state.to_dict()
        assert d["last_seen_version"] == "1.0.0"
        assert d["seen_flags"] == {"live": True}
        assert d["last_checked"] == 100.0
        assert d["beta_mode"] is True

    def test_from_dict(self) -> None:
        d = {
            "last_seen_version": "2.0.0",
            "seen_flags": {"ai": False},
            "last_checked": 50.0,
            "beta_mode": False,
        }
        state = WhatsNewState.from_dict(d)
        assert state.last_seen_version == "2.0.0"
        assert state.seen_flags == {"ai": False}
        assert state.last_checked == 50.0

    def test_from_dict_empty(self) -> None:
        state = WhatsNewState.from_dict({})
        assert state.last_seen_version == ""
        assert state.seen_flags == {}

    def test_roundtrip(self) -> None:
        original = WhatsNewState(
            last_seen_version="3.0.0",
            seen_flags={"a": True, "b": False},
            last_checked=999.0,
            beta_mode=True,
        )
        rebuilt = WhatsNewState.from_dict(original.to_dict())
        assert rebuilt.last_seen_version == original.last_seen_version
        assert rebuilt.seen_flags == original.seen_flags
        assert rebuilt.beta_mode == original.beta_mode


# ===================================================================== #
# BetaService — hash_code                                               #
# ===================================================================== #


class TestBetaServiceHashCode:
    """BetaService.hash_code normalisation and hashing."""

    def test_basic_hash(self) -> None:
        h = BetaService.hash_code("BETA-1234")
        expected = hashlib.sha256(b"BETA-1234").hexdigest()
        assert h == expected

    def test_strips_whitespace(self) -> None:
        assert BetaService.hash_code("  BETA-1234  ") == BetaService.hash_code("BETA-1234")

    def test_case_insensitive(self) -> None:
        assert BetaService.hash_code("beta-abcd") == BetaService.hash_code("BETA-ABCD")

    def test_different_codes_differ(self) -> None:
        assert BetaService.hash_code("AAA") != BetaService.hash_code("BBB")


# ===================================================================== #
# BetaService — is_beta_tester property                                  #
# ===================================================================== #


class TestBetaServiceIsBetaTester:
    """is_beta_tester requires both invitation AND settings toggle."""

    def _make_service(
        self,
        *,
        verified: bool = False,
        enabled_in_settings: bool = False,
    ) -> BetaService:
        ks = MagicMock()
        ks.get_key.return_value = "somehash" if verified else None
        ks.has_key.return_value = verified
        return BetaService(
            key_store=ks,
            beta_enabled_in_settings=enabled_in_settings,
        )

    def test_not_verified_not_enabled(self) -> None:
        svc = self._make_service(verified=False, enabled_in_settings=False)
        assert svc.is_beta_tester is False

    def test_verified_but_not_enabled(self) -> None:
        svc = self._make_service(verified=True, enabled_in_settings=False)
        assert svc.is_beta_tester is False

    def test_not_verified_but_enabled(self) -> None:
        svc = self._make_service(verified=False, enabled_in_settings=True)
        assert svc.is_beta_tester is False

    def test_verified_and_enabled(self) -> None:
        svc = self._make_service(verified=True, enabled_in_settings=True)
        assert svc.is_beta_tester is True

    def test_set_beta_enabled(self) -> None:
        svc = self._make_service(verified=True, enabled_in_settings=False)
        assert svc.is_beta_tester is False
        svc.set_beta_enabled(True)
        assert svc.is_beta_tester is True

    def test_is_invitation_verified(self) -> None:
        svc = self._make_service(verified=True, enabled_in_settings=False)
        assert svc.is_invitation_verified is True


# ===================================================================== #
# BetaService — verify_invitation                                        #
# ===================================================================== #


class TestBetaServiceVerifyInvitation:
    """verify_invitation: remote fetch, hash match, keystore persistence."""

    def _make_service(self) -> tuple[BetaService, MagicMock]:
        ks = MagicMock()
        ks.get_key.return_value = None
        svc = BetaService(key_store=ks, beta_enabled_in_settings=True)
        return svc, ks

    def test_empty_code_rejected(self) -> None:
        svc, _ = self._make_service()
        assert svc.verify_invitation("") is False
        assert svc.verify_invitation("   ") is False

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_valid_code_accepted(self, mock_get: MagicMock) -> None:
        code = "BETA-VALID"
        expected_hash = BetaService.hash_code(code)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"codes": [expected_hash]},
            raise_for_status=MagicMock(),
        )
        svc, ks = self._make_service()
        assert svc.verify_invitation(code) is True
        assert svc.is_invitation_verified is True
        ks.store_key.assert_called_once_with(_BETA_KEYSTORE_KEY, expected_hash)

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_invalid_code_rejected(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"codes": ["deadbeef"]},
            raise_for_status=MagicMock(),
        )
        svc, ks = self._make_service()
        assert svc.verify_invitation("WRONG-CODE") is False
        assert svc.is_invitation_verified is False
        ks.store_key.assert_not_called()

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_network_failure_uses_cache(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("offline")
        svc, _ = self._make_service()
        # No cache file → returns empty set → code not found
        assert svc.verify_invitation("ANY-CODE") is False


# ===================================================================== #
# BetaService — revoke_beta                                              #
# ===================================================================== #


class TestBetaServiceRevoke:
    """revoke_beta clears invitation, settings toggle, and keystore."""

    def test_revoke_clears_state(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = "somehash"
        svc = BetaService(key_store=ks, beta_enabled_in_settings=True)
        assert svc.is_beta_tester is True

        svc.revoke_beta()

        assert svc.is_beta_tester is False
        assert svc.is_invitation_verified is False
        ks.delete_key.assert_called_once_with(_BETA_KEYSTORE_KEY)


# ===================================================================== #
# BetaService — release notes                                           #
# ===================================================================== #


class TestBetaServiceReleaseNotes:
    """Release notes URL resolution and fetching."""

    def test_resolve_bitswhisperer_uri(self) -> None:
        url = BetaService.resolve_release_notes_url("bitswhisperer://release-notes/watch_folder")
        assert "watch_folder.md" in url
        assert url.startswith("https://")

    def test_resolve_plain_url_unchanged(self) -> None:
        url = "https://example.com/notes.md"
        assert BetaService.resolve_release_notes_url(url) == url

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_fetch_release_notes_success(self, mock_get: MagicMock, tmp_path: Path) -> None:
        mock_get.return_value = MagicMock(
            status_code=200,
            text="# Watch Folder\nNew feature!",
            raise_for_status=MagicMock(),
        )
        svc = BetaService()
        with patch(
            "bits_whisperer.core.beta_service._RELEASE_NOTES_CACHE_DIR",
            tmp_path,
        ):
            content = svc.fetch_release_notes("watch_folder")
        assert "Watch Folder" in content

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_fetch_release_notes_fallback_to_cache(
        self,
        mock_get: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_get.side_effect = Exception("offline")
        cache_file = tmp_path / "my_feature.md"
        cache_file.write_text("# Cached notes", encoding="utf-8")
        svc = BetaService()
        with patch(
            "bits_whisperer.core.beta_service._RELEASE_NOTES_CACHE_DIR",
            tmp_path,
        ):
            content = svc.fetch_release_notes("my_feature")
        assert content == "# Cached notes"

    @patch("bits_whisperer.core.beta_service.httpx.get")
    def test_fetch_release_notes_no_cache(
        self,
        mock_get: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_get.side_effect = Exception("offline")
        svc = BetaService()
        with patch(
            "bits_whisperer.core.beta_service._RELEASE_NOTES_CACHE_DIR",
            tmp_path,
        ):
            assert svc.fetch_release_notes("missing_feature") == ""


# ===================================================================== #
# BetaService — What's New state persistence                             #
# ===================================================================== #


class TestBetaServiceWhatsNewState:
    """What's New state save/load lifecycle."""

    def test_load_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        svc = BetaService()
        with patch(
            "bits_whisperer.core.beta_service._WHATS_NEW_STATE",
            tmp_path / "nonexistent.json",
        ):
            state = svc.load_whats_new_state()
        assert state.last_seen_version == ""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        state_file = tmp_path / "whats_new.json"
        svc = BetaService()
        original = WhatsNewState(
            last_seen_version="1.5.0",
            seen_flags={"live": True, "ai": False},
            beta_mode=True,
        )
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            BetaService.save_whats_new_state(original)
            loaded = svc.load_whats_new_state()
        assert loaded.last_seen_version == "1.5.0"
        assert loaded.seen_flags == {"live": True, "ai": False}
        assert loaded.beta_mode is True

    def test_load_corrupt_json_returns_defaults(self, tmp_path: Path) -> None:
        state_file = tmp_path / "whats_new.json"
        state_file.write_text("NOT JSON!!!", encoding="utf-8")
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            state = svc.load_whats_new_state()
        assert state.last_seen_version == ""


# ===================================================================== #
# BetaService — detect_changes                                           #
# ===================================================================== #


class TestBetaServiceDetectChanges:
    """detect_changes: version bump, beta toggle, per-feature changes."""

    def _make_flag(
        self,
        name: str,
        *,
        enabled: bool = True,
        beta_enabled: bool | None = None,
    ) -> FeatureFlag:
        return FeatureFlag(
            name=name,
            enabled=enabled,
            beta_enabled=beta_enabled,
            label=name.replace("_", " ").title(),
            description=f"Description of {name}",
        )

    def test_no_changes_on_first_launch(self, tmp_path: Path) -> None:
        svc = BetaService()
        # First launch — state file doesn't exist
        with patch(
            "bits_whisperer.core.beta_service._WHATS_NEW_STATE",
            tmp_path / "state.json",
        ):
            flags = {"live": self._make_flag("live")}
            changes = svc.detect_changes(flags, is_beta=False)
        # No prior state → shouldn't show "added" for every feature
        assert len(changes) == 0

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "2.0.0")
    def test_version_bump_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(last_seen_version="1.0.0", seen_flags={"live": True})
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {"live": self._make_flag("live")},
                is_beta=False,
            )
        version_changes = [c for c in changes if c.change_type == "version_update"]
        assert len(version_changes) == 1
        assert "2.0.0" in version_changes[0].label

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_beta_mode_enabled_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": True},
            beta_mode=False,
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {"live": self._make_flag("live")},
                is_beta=True,
            )
        beta_changes = [c for c in changes if c.feature_name == "__beta_mode__"]
        assert len(beta_changes) == 1
        assert beta_changes[0].change_type == "enabled"

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_beta_mode_disabled_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": True},
            beta_mode=True,
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {"live": self._make_flag("live")},
                is_beta=False,
            )
        beta_changes = [c for c in changes if c.feature_name == "__beta_mode__"]
        assert len(beta_changes) == 1
        assert beta_changes[0].change_type == "disabled"

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_new_feature_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": True},
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {
                    "live": self._make_flag("live"),
                    "new_feature": self._make_flag("new_feature"),
                },
                is_beta=False,
            )
        added = [c for c in changes if c.change_type == "added"]
        assert len(added) == 1
        assert added[0].feature_name == "new_feature"

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_feature_enabled_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": False},
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {"live": self._make_flag("live", enabled=True)},
                is_beta=False,
            )
        enabled = [c for c in changes if c.change_type == "enabled"]
        assert len(enabled) == 1
        assert enabled[0].feature_name == "live"

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_feature_disabled_detected(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": True},
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {"live": self._make_flag("live", enabled=False)},
                is_beta=False,
            )
        disabled = [c for c in changes if c.change_type == "disabled"]
        assert len(disabled) == 1
        assert disabled[0].feature_name == "live"

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.0.0")
    def test_beta_flag_routing(self, tmp_path: Path) -> None:
        """In beta mode, detect_changes uses beta_enabled instead of enabled."""
        state_file = tmp_path / "state.json"
        prior = WhatsNewState(
            last_seen_version="1.0.0",
            seen_flags={"live": False},
            beta_mode=True,
        )
        state_file.write_text(
            json.dumps(prior.to_dict()),
            encoding="utf-8",
        )
        svc = BetaService()
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            changes = svc.detect_changes(
                {
                    "live": self._make_flag(
                        "live",
                        enabled=False,
                        beta_enabled=True,
                    ),
                },
                is_beta=True,
            )
        # beta_enabled=True and previously False → "enabled" change
        enabled = [c for c in changes if c.change_type == "enabled"]
        assert len(enabled) == 1


# ===================================================================== #
# BetaService — snapshot_current_state                                   #
# ===================================================================== #


class TestBetaServiceSnapshot:
    """snapshot_current_state persists flag state for future comparison."""

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "1.2.0")
    def test_snapshot_creates_state_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        svc = BetaService()
        flag = FeatureFlag(name="live", enabled=True)
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            svc.snapshot_current_state({"live": flag}, is_beta=False)
            loaded = svc.load_whats_new_state()
        assert loaded.last_seen_version == "1.2.0"
        assert loaded.seen_flags == {"live": True}
        assert loaded.beta_mode is False

    @patch("bits_whisperer.core.beta_service.APP_VERSION", "2.0.0")
    def test_snapshot_beta_mode(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        svc = BetaService()
        flag = FeatureFlag(name="live", enabled=False, beta_enabled=True)
        with patch("bits_whisperer.core.beta_service._WHATS_NEW_STATE", state_file):
            svc.snapshot_current_state({"live": flag}, is_beta=True)
            loaded = svc.load_whats_new_state()
        assert loaded.beta_mode is True
        # In beta mode, snapshot records beta_enabled (True), not enabled (False)
        assert loaded.seen_flags == {"live": True}


# ===================================================================== #
# FeatureFlagService.is_enabled_for_beta                                 #
# ===================================================================== #


class TestIsEnabledForBeta:
    """is_enabled_for_beta: beta_enabled routing & fallbacks."""

    def _make_service(self, features: dict[str, FeatureFlag]) -> FeatureFlagService:
        svc = FeatureFlagService(app_version="1.0.0")
        for name, flag in features.items():
            svc._config.features[name] = flag
        return svc

    def test_beta_enabled_true_overrides_disabled(self) -> None:
        """Feature disabled for general users but enabled for beta."""
        svc = self._make_service(
            {
                "new_feature": FeatureFlag(
                    name="new_feature",
                    enabled=False,
                    beta_enabled=True,
                ),
            }
        )
        assert svc.is_enabled("new_feature") is False
        assert svc.is_enabled_for_beta("new_feature") is True

    def test_beta_enabled_false_overrides_enabled(self) -> None:
        """Feature enabled for general users but disabled for beta."""
        svc = self._make_service(
            {
                "old_feature": FeatureFlag(
                    name="old_feature",
                    enabled=True,
                    beta_enabled=False,
                ),
            }
        )
        assert svc.is_enabled("old_feature") is True
        assert svc.is_enabled_for_beta("old_feature") is False

    def test_beta_enabled_none_falls_back_to_enabled(self) -> None:
        """When beta_enabled is None, fallback to enabled."""
        svc = self._make_service(
            {
                "feature_a": FeatureFlag(
                    name="feature_a",
                    enabled=True,
                    beta_enabled=None,
                ),
            }
        )
        assert svc.is_enabled_for_beta("feature_a") is True

    def test_beta_enabled_none_disabled_falls_back(self) -> None:
        svc = self._make_service(
            {
                "feature_b": FeatureFlag(
                    name="feature_b",
                    enabled=False,
                    beta_enabled=None,
                ),
            }
        )
        assert svc.is_enabled_for_beta("feature_b") is False

    def test_unknown_feature_enabled_by_default(self) -> None:
        svc = self._make_service({})
        assert svc.is_enabled_for_beta("nonexistent") is True

    def test_local_override_wins_over_beta(self) -> None:
        svc = self._make_service(
            {
                "gated": FeatureFlag(
                    name="gated",
                    enabled=False,
                    beta_enabled=False,
                ),
            }
        )
        svc.set_override("gated", True)
        assert svc.is_enabled_for_beta("gated") is True

    def test_version_gate_blocks_beta(self) -> None:
        svc = self._make_service(
            {
                "future": FeatureFlag(
                    name="future",
                    enabled=True,
                    beta_enabled=True,
                    min_version="99.0.0",
                ),
            }
        )
        assert svc.is_enabled_for_beta("future") is False


# ===================================================================== #
# BITS_RegistrationService — device ID                                   #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceDeviceId:
    """Device ID generation is deterministic and non-empty."""

    def test_device_id_not_empty(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        did = svc.get_device_id()
        assert isinstance(did, str)
        assert len(did) == 24

    def test_device_id_deterministic(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_device_id() == svc.get_device_id()


# ===================================================================== #
# BITS_RegistrationService — status messages                             #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceStatus:
    """get_status_message returns human-readable registration status."""

    def _make_service(self, status: str | None) -> BITS_RegistrationService:
        ks = MagicMock()
        ks.get_key.side_effect = lambda key: status if key == "registration_status" else None
        ks.has_key.side_effect = lambda key: (
            status is not None if key == "registration_key" else False
        )
        return BITS_RegistrationService(ks)

    def test_lifetime_member(self) -> None:
        svc = self._make_service("L")
        assert "Lifetime" in svc.get_status_message()

    def test_active_member(self) -> None:
        svc = self._make_service("A")
        assert "Active" in svc.get_status_message()

    def test_contributor(self) -> None:
        svc = self._make_service("C")
        assert "Contributor" in svc.get_status_message()

    def test_unregistered(self) -> None:
        svc = self._make_service(None)
        assert "Unregistered" in svc.get_status_message()


# ===================================================================== #
# BITS_RegistrationService — verify_key                                  #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceVerifyKey:
    """verify_key: online verification, caching, and offline fallback."""

    def _make_service(self) -> tuple[BITS_RegistrationService, MagicMock]:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        return svc, ks

    def test_no_key_returns_false(self) -> None:
        svc, ks = self._make_service()
        ks.get_key.return_value = None
        assert svc.verify_key() is False

    @patch("bits_whisperer.core.registration_service._LAST_VERIFICATION_TIME", 0)
    def test_rate_limiting_uses_cache(self) -> None:
        svc, ks = self._make_service()
        ks.get_key.side_effect = lambda key: "test_key" if key == "registration_key" else None
        ks.has_key.return_value = True
        # First call sets the timestamp
        with patch.object(svc, "_get_secure_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_session.return_value.get.return_value = mock_resp
            svc.verify_key(force=True)

        # Second call within interval should be rate-limited
        result = svc.verify_key(force=False)
        # Rate-limited → returns cached status (has_key for registration_status)
        assert isinstance(result, bool)

    @patch("bits_whisperer.core.registration_service._LAST_VERIFICATION_TIME", 0)
    def test_no_key_clears_status(self) -> None:
        svc, ks = self._make_service()
        ks.get_key.return_value = None
        svc.verify_key()
        ks.delete_key.assert_called_with("registration_status")


# ===================================================================== #
# BITS_RegistrationService — offline fallback                            #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceFallback:
    """_fallback_to_cache: 7-day grace period for offline access."""

    def test_no_cached_time_returns_false(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc._fallback_to_cache() is False

    def test_recent_cache_returns_status(self) -> None:
        from datetime import datetime

        ks = MagicMock()
        ks.get_key.side_effect = lambda key: (
            datetime.now().isoformat() if key == "registration_verified_at" else None
        )
        ks.has_key.return_value = True
        svc = BITS_RegistrationService(ks)
        assert svc._fallback_to_cache() is True

    def test_old_cache_returns_false(self) -> None:
        from datetime import datetime, timedelta

        old_time = (datetime.now() - timedelta(days=31)).isoformat()
        ks = MagicMock()
        ks.get_key.side_effect = lambda key: old_time if key == "registration_verified_at" else None
        ks.has_key.return_value = True
        svc = BITS_RegistrationService(ks)
        assert svc._fallback_to_cache() is False

    def test_within_grace_period_succeeds(self) -> None:
        from datetime import datetime, timedelta

        recent_time = (datetime.now() - timedelta(days=29)).isoformat()
        ks = MagicMock()
        ks.get_key.side_effect = lambda key: (
            recent_time if key == "registration_verified_at" else None
        )
        ks.has_key.return_value = True
        svc = BITS_RegistrationService(ks)
        assert svc._fallback_to_cache() is True


# ===================================================================== #
# BITS_RegistrationService — clear_registration                          #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceClear:
    """clear_registration removes all registration data."""

    def test_clears_all_keys(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        svc.clear_registration()
        # Should attempt to delete all registration keys incl. trial_hmac
        deleted = [call.args[0] for call in ks.delete_key.call_args_list]
        assert "registration_key" in deleted
        assert "registration_status" in deleted
        assert "registration_verified_at" in deleted
        assert "trial_hmac" in deleted


# ===================================================================== #
# BITS_RegistrationService — integrity check                             #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationServiceIntegrity:
    """_perform_integrity_check skips when hash is None (dev mode)."""

    def test_integrity_check_skipped_in_dev(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        # Should not raise — _EXPECTED_MODULE_HASH is None
        svc = BITS_RegistrationService(ks)
        assert svc is not None


# ===================================================================== #
# Trial / activation helpers                                             #
# ===================================================================== #


@_skip_no_requests
class TestTrialActiveAndDaysRemaining:
    """is_trial_active and get_trial_days_remaining compute from datetime.now."""

    def test_trial_active_within_window(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=3)).isoformat()
        svc = BITS_RegistrationService(ks)
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.is_trial_active() is True
        assert svc.get_trial_days_remaining() == 4

    def test_trial_expired(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=8)).isoformat()
        ks.get_key.side_effect = lambda k: start if k == "trial_start_date" else None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.is_trial_active() is False
        assert svc.get_trial_days_remaining() == 0

    def test_no_trial_started(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.is_trial_active() is False
        assert svc.get_trial_days_remaining() == 0


@_skip_no_requests
class TestNeedsActivation:
    """needs_activation returns True only when no key and no active trial."""

    def test_needs_activation_no_key_no_trial(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is True

    def test_no_activation_with_key(self) -> None:
        ks = MagicMock()

        def _get(k: str) -> str | None:
            if k == "registration_key":
                return "some-key"
            return None

        ks.get_key.side_effect = _get
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is False

    def test_no_activation_during_trial(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=2)).isoformat()

        # Trials only bypass activation in "live" mode
        ff = MagicMock()
        ff.get_licensing_config.return_value = MagicMock(activation_mode="live")

        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.needs_activation() is False

    def test_needs_activation_after_trial_expires(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=10)).isoformat()

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is True

    def test_beta_invitation_bypass(self) -> None:
        """Beta testers with a verified invitation hash bypass activation."""
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.side_effect = lambda k: k == "beta_invitation_hash"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is False

    def test_alpha_tester_bypass(self) -> None:
        ks = MagicMock()

        def _get(k: str) -> str | None:
            if k == "registration_status":
                return "T"
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is False

    def test_beta_mode_blocks_trial(self) -> None:
        """In beta mode, an active trial does NOT bypass activation."""
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=2)).isoformat()
        # Default mode is "beta" (no feature_flag_service)
        svc = BITS_RegistrationService(ks)
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.needs_activation() is True

    def test_beta_mode_blocks_member_hash(self) -> None:
        """In beta mode, a verified member email does NOT bypass."""
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.side_effect = lambda k: k == "member_email_hash"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_activation() is True

    def test_live_mode_allows_member_hash(self) -> None:
        """In live mode, a verified BITS member bypasses activation."""
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.side_effect = lambda k: k == "member_email_hash"

        ff = MagicMock()
        ff.get_licensing_config.return_value = MagicMock(activation_mode="live")

        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.needs_activation() is False

    def test_closed_mode_blocks_all(self) -> None:
        """In closed mode, even a registration key does not bypass."""
        ks = MagicMock()
        ks.get_key.return_value = "some-key"
        ks.has_key.return_value = True  # has registration_key

        ff = MagicMock()
        ff.get_licensing_config.return_value = MagicMock(activation_mode="closed")

        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.needs_activation() is True

    def test_activation_mode_property_defaults_beta(self) -> None:
        """Without feature flags, activation_mode defaults to 'beta'."""
        ks = MagicMock()
        svc = BITS_RegistrationService(ks)
        assert svc.activation_mode == "beta"

    def test_activation_mode_property_reads_remote(self) -> None:
        """activation_mode reads from the remote LicensingConfig."""
        ks = MagicMock()
        ff = MagicMock()
        ff.get_licensing_config.return_value = MagicMock(activation_mode="live")
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.activation_mode == "live"


# ===================================================================== #
# HMAC tamper protection                                                 #
# ===================================================================== #


@_skip_no_requests
class TestTrialHmacProtection:
    """HMAC-SHA256 protects trial start date from tampering."""

    def test_authentic_trial_passes_hmac(self) -> None:
        """start_trial stores a valid HMAC and is_trial_active accepts it."""
        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks)
        svc.start_trial("Test User", "user@example.com")
        assert svc.is_trial_active() is True
        assert svc.get_trial_days_remaining() == 7

    def test_tampered_date_fails_hmac(self) -> None:
        """Changing trial_start_date after HMAC is set → trial invalid."""
        from datetime import datetime, timedelta

        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks)
        svc.start_trial("Test User", "user@example.com")
        # Tamper: reset the date to extend the trial
        tampered = (datetime.now() - timedelta(days=1)).isoformat()
        stored["trial_start_date"] = tampered
        assert svc.is_trial_active() is False
        assert svc.get_trial_days_remaining() == 0

    def test_missing_hmac_fails(self) -> None:
        """Trial with a start date but no HMAC is treated as tampered."""
        from datetime import datetime

        ks = MagicMock()
        stored: dict[str, str] = {"trial_start_date": datetime.now().isoformat()}
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks)
        assert svc.is_trial_active() is False

    def test_no_trial_is_authentic(self) -> None:
        """No trial date at all counts as 'authentic' (nothing to tamper)."""
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc._is_trial_date_authentic() is True


# ===================================================================== #
# Key format validation                                                  #
# ===================================================================== #


@_skip_no_requests
class TestKeyFormatValidation:
    """is_valid_key_format: regex-based structural check."""

    def test_valid_base64_key(self) -> None:
        key = "A" * 32
        assert BITS_RegistrationService.is_valid_key_format(key) is True

    def test_valid_key_with_base64_chars(self) -> None:
        key = "AbCdEfGhIjKlMnOpQrStUvWxYz012345+/=_-"
        assert BITS_RegistrationService.is_valid_key_format(key) is True

    def test_too_short(self) -> None:
        assert BITS_RegistrationService.is_valid_key_format("ABC") is False

    def test_empty(self) -> None:
        assert BITS_RegistrationService.is_valid_key_format("") is False

    def test_spaces_invalid(self) -> None:
        assert BITS_RegistrationService.is_valid_key_format("A" * 16 + " " + "B" * 16) is False

    def test_special_chars_invalid(self) -> None:
        assert BITS_RegistrationService.is_valid_key_format("!" * 32) is False


# ===================================================================== #
# Periodic re-verification                                               #
# ===================================================================== #


@_skip_no_requests
class TestNeedsReverification:
    """needs_reverification: 24-hour interval check."""

    def test_no_key_no_reverification(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.needs_reverification() is False

    def test_never_verified_needs_reverification(self) -> None:
        ks = MagicMock()
        ks.get_key.side_effect = lambda k: "key123" if k == "registration_key" else None
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_reverification() is True

    def test_recently_verified_no_reverification(self) -> None:
        from datetime import datetime

        ks = MagicMock()

        def _get(k: str) -> str | None:
            if k == "registration_key":
                return "key123"
            if k == "registration_verified_at":
                return datetime.now().isoformat()
            return None

        ks.get_key.side_effect = _get
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_reverification() is False

    def test_stale_verification_needs_reverification(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()

        def _get(k: str) -> str | None:
            if k == "registration_key":
                return "key123"
            if k == "registration_verified_at":
                return old_time
            return None

        ks.get_key.side_effect = _get
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks)
        assert svc.needs_reverification() is True


# ===================================================================== #
# Trial expiry warning                                                   #
# ===================================================================== #


@_skip_no_requests
class TestTrialExpiringSoon:
    """is_trial_expiring_soon: warns when ≤ 2 days remaining."""

    def test_not_expiring_5_days_left(self) -> None:
        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks)
        svc.start_trial("User", "u@e.com")
        # Just started → 7 days left, not expiring soon
        assert svc.is_trial_expiring_soon() is False

    def test_expiring_1_day_left(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        start = (datetime.now() - timedelta(days=6)).isoformat()
        svc = BITS_RegistrationService(ks)
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.is_trial_expiring_soon() is True

    def test_not_expiring_when_no_trial(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.is_trial_expiring_soon() is False


# ===================================================================== #
# Last verified display                                                  #
# ===================================================================== #


@_skip_no_requests
class TestLastVerifiedDisplay:
    """get_last_verified_display: human-readable time-ago strings."""

    def test_never_verified(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "Never"

    def test_just_now(self) -> None:
        from datetime import datetime

        ks = MagicMock()
        ks.get_key.side_effect = lambda k: (
            datetime.now().isoformat() if k == "registration_verified_at" else None
        )
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "Just now"

    def test_hours_ago(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        t = (datetime.now() - timedelta(hours=3)).isoformat()
        ks.get_key.side_effect = lambda k: t if k == "registration_verified_at" else None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "3 hours ago"

    def test_yesterday(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        t = (datetime.now() - timedelta(days=1)).isoformat()
        ks.get_key.side_effect = lambda k: t if k == "registration_verified_at" else None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "Yesterday"

    def test_days_ago(self) -> None:
        from datetime import datetime, timedelta

        ks = MagicMock()
        t = (datetime.now() - timedelta(days=5)).isoformat()
        ks.get_key.side_effect = lambda k: t if k == "registration_verified_at" else None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "5 days ago"

    def test_corrupt_timestamp(self) -> None:
        ks = MagicMock()
        ks.get_key.side_effect = lambda k: "not-a-date" if k == "registration_verified_at" else None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_last_verified_display() == "Unknown"


# ===================================================================== #
# Remote licensing configuration                                        #
# ===================================================================== #


@_skip_no_requests
class TestRemoteLicensingConfig:
    """Licence parameters are remotely adjustable via feature flags."""

    def _make_ff_service(
        self,
        *,
        trial_days: int = 7,
        offline_grace_days: int = 30,
        reverify_hours: int = 24,
        trial_warning_days: int = 2,
    ) -> MagicMock:
        """Build a mock FeatureFlagService with a LicensingConfig."""
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(
            trial_days=trial_days,
            offline_grace_days=offline_grace_days,
            reverify_hours=reverify_hours,
            trial_warning_days=trial_warning_days,
        )
        return ff

    def test_default_trial_days_without_ff(self) -> None:
        """Without FeatureFlagService, compile-time defaults apply."""
        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks)
        svc.start_trial("User", "u@test.com")
        assert svc.get_trial_days_remaining() == 7

    def test_extended_trial_via_remote_config(self) -> None:
        """Admin extends trial to 14 days via feature_flags.json."""

        ff = self._make_ff_service(trial_days=14)
        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        svc.start_trial("User", "u@test.com")
        assert svc.get_trial_days_remaining() == 14
        assert svc.is_trial_active() is True

    def test_shortened_trial_via_remote_config(self) -> None:
        """Admin shortens trial to 3 days — day-4 user is expired."""
        from datetime import datetime, timedelta

        ff = self._make_ff_service(trial_days=3)
        ks = MagicMock()
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        start = (datetime.now() - timedelta(days=4)).isoformat()
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.is_trial_active() is False

    def test_extended_offline_grace_via_remote(self) -> None:
        """Admin extends offline grace to 60 days — 45-day cache OK."""
        from datetime import datetime, timedelta

        ff = self._make_ff_service(offline_grace_days=60)
        ks = MagicMock()
        old_time = (datetime.now() - timedelta(days=45)).isoformat()
        ks.get_key.side_effect = lambda key: old_time if key == "registration_verified_at" else None
        ks.has_key.return_value = True
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc._fallback_to_cache() is True

    def test_shortened_offline_grace_via_remote(self) -> None:
        """Admin shortens grace to 10 days — 15-day cache expired."""
        from datetime import datetime, timedelta

        ff = self._make_ff_service(offline_grace_days=10)
        ks = MagicMock()
        old_time = (datetime.now() - timedelta(days=15)).isoformat()
        ks.get_key.side_effect = lambda key: old_time if key == "registration_verified_at" else None
        ks.has_key.return_value = True
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc._fallback_to_cache() is False

    def test_reverify_interval_remote(self) -> None:
        """Admin sets re-verification to 12 hours — 13h stale."""
        from datetime import datetime, timedelta

        ff = self._make_ff_service(reverify_hours=12)
        ks = MagicMock()
        old_time = (datetime.now() - timedelta(hours=13)).isoformat()

        def _get(k: str) -> str | None:
            if k == "registration_key":
                return "key123"
            if k == "registration_verified_at":
                return old_time
            return None

        ks.get_key.side_effect = _get
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.needs_reverification() is True

    def test_trial_warning_days_remote(self) -> None:
        """Admin sets warning threshold to 3 days — 3 days left triggers."""
        from datetime import datetime, timedelta

        ff = self._make_ff_service(trial_days=7, trial_warning_days=3)
        ks = MagicMock()
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        start = (datetime.now() - timedelta(days=4)).isoformat()
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        # 3 days remaining, warning threshold is 3 → should warn
        assert svc.is_trial_expiring_soon() is True


# ===================================================================== #
# LicensingConfig dataclass                                             #
# ===================================================================== #


class TestLicensingConfig:
    """LicensingConfig parsing and defaults."""

    def test_defaults(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        lc = LicensingConfig()
        assert lc.activation_mode == "beta"
        assert lc.trial_days == 7
        assert lc.offline_grace_days == 30
        assert lc.reverify_hours == 24
        assert lc.trial_warning_days == 2


# ===================================================================== #
# MemberVerificationService                                              #
# ===================================================================== #


class TestMemberVerificationService:
    """OTP-based BITS member email verification."""

    def test_is_member_email_valid(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        assert MemberVerificationService.is_member_email("user@bitsusers.org") is True
        assert MemberVerificationService.is_member_email("USER@BITSUSERS.ORG") is True

    def test_is_member_email_invalid(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        assert MemberVerificationService.is_member_email("user@gmail.com") is False
        assert MemberVerificationService.is_member_email("not-an-email") is False
        assert MemberVerificationService.is_member_email("") is False

    def test_request_verification_rejects_non_member(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        ks = MagicMock()
        svc = MemberVerificationService(ks)
        with pytest.raises(ValueError, match=r"bitsusers\.org"):
            svc.request_verification("user@gmail.com")

    def test_request_and_verify_otp(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.has_key.side_effect = lambda k: k in stored

        svc = MemberVerificationService(ks)
        otp = svc.request_verification("user@bitsusers.org")
        assert len(otp) == 6
        assert otp.isdigit()

        # Correct OTP succeeds
        assert svc.verify_otp("user@bitsusers.org", otp) is True
        assert "member_email_hash" in stored

    def test_verify_wrong_otp(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        ks = MagicMock()
        svc = MemberVerificationService(ks)
        svc.request_verification("user@bitsusers.org")
        assert svc.verify_otp("user@bitsusers.org", "000000") is False

    def test_verify_no_pending(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        ks = MagicMock()
        svc = MemberVerificationService(ks)
        assert svc.verify_otp("user@bitsusers.org", "123456") is False

    def test_is_already_verified(self) -> None:
        from bits_whisperer.core.member_verification import MemberVerificationService

        ks = MagicMock()
        ks.has_key.return_value = True
        svc = MemberVerificationService(ks)
        assert svc.is_already_verified() is True

    def test_custom_values(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        lc = LicensingConfig(
            trial_days=14,
            offline_grace_days=60,
            reverify_hours=12,
            trial_warning_days=3,
        )
        assert lc.trial_days == 14
        assert lc.offline_grace_days == 60
        assert lc.reverify_hours == 12
        assert lc.trial_warning_days == 3

    def test_from_feature_flag_config(self) -> None:
        from bits_whisperer.core.feature_flags import FeatureFlagConfig

        data = {
            "version": 2,
            "features": {},
            "licensing": {
                "trial_days": 21,
                "offline_grace_days": 90,
                "reverify_hours": 48,
                "trial_warning_days": 5,
            },
        }
        config = FeatureFlagConfig.from_dict(data)
        assert config.licensing.trial_days == 21
        assert config.licensing.offline_grace_days == 90
        assert config.licensing.reverify_hours == 48
        assert config.licensing.trial_warning_days == 5

    def test_missing_licensing_section_uses_defaults(self) -> None:
        from bits_whisperer.core.feature_flags import FeatureFlagConfig

        data = {"version": 2, "features": {}}
        config = FeatureFlagConfig.from_dict(data)
        assert config.licensing.trial_days == 7
        assert config.licensing.offline_grace_days == 30

    def test_roundtrip_serialization(self) -> None:
        from bits_whisperer.core.feature_flags import (
            FeatureFlagConfig,
            LicensingConfig,
        )

        original = FeatureFlagConfig(
            licensing=LicensingConfig(trial_days=10, offline_grace_days=45),
        )
        rebuilt = FeatureFlagConfig.from_dict(original.to_dict())
        assert rebuilt.licensing.trial_days == 10
        assert rebuilt.licensing.offline_grace_days == 45

    def test_get_licensing_config_from_service(self) -> None:
        from bits_whisperer.core.feature_flags import (
            FeatureFlagConfig,
            FeatureFlagService,
            LicensingConfig,
        )

        svc = FeatureFlagService(app_version="1.0.0")
        svc._config = FeatureFlagConfig(
            licensing=LicensingConfig(trial_days=30),
        )
        lc = svc.get_licensing_config()
        assert lc.trial_days == 30

    def test_expanded_fields_defaults(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        lc = LicensingConfig()
        assert lc.max_devices == 3
        assert lc.admin_message == ""
        assert lc.purchase_url == ""
        assert lc.trial_extension_days == 0
        assert lc.grace_mode_enabled is False
        assert lc.grace_mode_days == 7
        assert lc.tier_names["L"] == "Lifetime Member"
        assert lc.tier_names["T"] == "Alpha Tester"

    def test_expanded_fields_roundtrip(self) -> None:
        from bits_whisperer.core.feature_flags import (
            FeatureFlagConfig,
            LicensingConfig,
        )

        original = FeatureFlagConfig(
            licensing=LicensingConfig(
                max_devices=5,
                admin_message="Maintenance tonight",
                purchase_url="https://example.com/buy",
                trial_extension_days=3,
                grace_mode_enabled=True,
                grace_mode_days=14,
                tier_names={"L": "Patron", "A": "Member", "C": "Donor", "T": "Tester"},
            ),
        )
        rebuilt = FeatureFlagConfig.from_dict(original.to_dict())
        assert rebuilt.licensing.max_devices == 5
        assert rebuilt.licensing.admin_message == "Maintenance tonight"
        assert rebuilt.licensing.purchase_url == "https://example.com/buy"
        assert rebuilt.licensing.trial_extension_days == 3
        assert rebuilt.licensing.grace_mode_enabled is True
        assert rebuilt.licensing.grace_mode_days == 14
        assert rebuilt.licensing.tier_names["L"] == "Patron"

    def test_tier_names_from_dict_bad_data(self) -> None:
        from bits_whisperer.core.feature_flags import FeatureFlagConfig

        data = {
            "version": 2,
            "features": {},
            "licensing": {"tier_names": {"L": 123, "A": None}},
        }
        config = FeatureFlagConfig.from_dict(data)
        # Bad values should fall back to defaults
        assert config.licensing.tier_names["L"] == "Lifetime Member"


# ===================================================================== #
# Registration service — new configurable fields                         #
# ===================================================================== #


@_skip_no_requests
class TestRegistrationConfigurableDeviceLimit:
    """Device limit is read from LicensingConfig instead of hardcoded 3."""

    def _make_ff(self, max_devices: int = 3) -> MagicMock:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(max_devices=max_devices)
        return ff

    def test_default_max_devices(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc._max_devices == 3

    def test_remote_max_devices(self) -> None:
        ff = self._make_ff(max_devices=5)
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc._max_devices == 5


@_skip_no_requests
class TestRegistrationGraceMode:
    """Grace mode: read-only period after trial/licence expiry."""

    def _make_ff(
        self,
        grace_mode_enabled: bool = True,
        grace_mode_days: int = 7,
        trial_days: int = 7,
    ) -> MagicMock:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(
            grace_mode_enabled=grace_mode_enabled,
            grace_mode_days=grace_mode_days,
            trial_days=trial_days,
        )
        return ff

    def test_grace_mode_disabled_returns_false(self) -> None:
        ff = self._make_ff(grace_mode_enabled=False)
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.is_in_grace_mode() is False

    def test_grace_mode_within_window(self) -> None:
        from datetime import datetime, timedelta

        ff = self._make_ff(grace_mode_enabled=True, grace_mode_days=7, trial_days=7)
        ks = MagicMock()
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        # Trial expired 2 days ago (day 9 of 7-day trial)
        start = (datetime.now() - timedelta(days=9)).isoformat()
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.is_in_grace_mode() is True
        assert svc.get_grace_days_remaining() == 5

    def test_grace_mode_past_window(self) -> None:
        from datetime import datetime, timedelta

        ff = self._make_ff(grace_mode_enabled=True, grace_mode_days=7, trial_days=7)
        ks = MagicMock()
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        # Trial expired 10 days ago (day 17 of 7-day trial + 7 grace)
        start = (datetime.now() - timedelta(days=17)).isoformat()
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        assert svc.is_in_grace_mode() is False

    def test_grace_mode_status_message(self) -> None:
        from datetime import datetime, timedelta

        ff = self._make_ff(grace_mode_enabled=True, grace_mode_days=7, trial_days=7)
        ks = MagicMock()
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        start = (datetime.now() - timedelta(days=8)).isoformat()
        hmac_val = svc._trial_hmac(start)

        def _get(k: str) -> str | None:
            if k == "trial_start_date":
                return start
            if k == "trial_hmac":
                return hmac_val
            return None

        ks.get_key.side_effect = _get
        ks.has_key.return_value = False
        msg = svc.get_status_message()
        assert "Grace Period" in msg
        assert "read-only" in msg


@_skip_no_requests
class TestRegistrationTrialExtension:
    """trial_extension_days adds bonus days to all active trials."""

    def test_trial_extension_bonus(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(
            trial_days=7,
            trial_extension_days=3,
        )
        ks = MagicMock()
        stored: dict[str, str] = {}
        ks.store_key.side_effect = stored.__setitem__
        ks.get_key.side_effect = stored.get
        ks.has_key.side_effect = lambda k: k in stored
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        svc.start_trial("User", "u@test.com")
        # 7 base + 3 extension = 10 total
        assert svc.get_trial_days_remaining() == 10
        assert svc._trial_days == 10


@_skip_no_requests
class TestRegistrationTierNames:
    """tier_names: remotely customisable status display names."""

    def _make_ff(self, tier_names: dict[str, str]) -> MagicMock:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(tier_names=tier_names)
        return ff

    def test_custom_tier_names_in_status(self) -> None:
        custom = {
            "L": "Patron for Life",
            "A": "Member",
            "C": "Donor",
            "T": "Beta Tester",
        }
        ff = self._make_ff(custom)
        ks = MagicMock()
        ks.get_key.side_effect = lambda k: "L" if k == "registration_status" else None
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert "Patron for Life" in svc.get_status_message()

    def test_default_tier_names_without_ff(self) -> None:
        ks = MagicMock()
        ks.get_key.side_effect = lambda k: "C" if k == "registration_status" else None
        ks.has_key.side_effect = lambda k: k == "registration_key"
        svc = BITS_RegistrationService(ks)
        assert "Paying Contributor" in svc.get_status_message()


@_skip_no_requests
class TestRegistrationAdminMessage:
    """admin_message and purchase_url properties."""

    def test_admin_message_from_remote(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(
            admin_message="Server maintenance tonight",
        )
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.get_admin_message() == "Server maintenance tonight"

    def test_purchase_url_from_remote(self) -> None:
        from bits_whisperer.core.feature_flags import LicensingConfig

        ff = MagicMock()
        ff.get_licensing_config.return_value = LicensingConfig(
            purchase_url="https://bits.org/buy",
        )
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks, feature_flag_service=ff)
        assert svc.get_purchase_url() == "https://bits.org/buy"

    def test_empty_admin_message_default(self) -> None:
        ks = MagicMock()
        ks.get_key.return_value = None
        ks.has_key.return_value = False
        svc = BITS_RegistrationService(ks)
        assert svc.get_admin_message() == ""
        assert svc.get_purchase_url() == ""
