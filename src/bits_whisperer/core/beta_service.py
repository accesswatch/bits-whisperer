"""Beta programme service for invitation-based beta testing.

This module manages:

- **Invitation code verification** against a remote JSON list of
  SHA-256 hashed codes hosted on the GitHub repository.
- **Beta tester status** persistence in the OS credential store
  (via :class:`~bits_whisperer.storage.key_store.KeyStore`).
- **Release notes fetching** for the What's New dialog, resolving
  ``bitswhisperer://release-notes/<feature>`` URIs to raw GitHub URLs.

Usage::

    from bits_whisperer.core.beta_service import BetaService

    service = BetaService(key_store=key_store)
    if service.verify_invitation("BETA-XXXX-YYYY"):
        # User is now a beta tester
        ...

    if service.is_beta_tester:
        # Show beta-only features
        ...
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from bits_whisperer.utils.constants import (
    APP_VERSION,
    DATA_DIR,
    GITHUB_REPO_NAME,
    GITHUB_REPO_OWNER,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INVITATIONS_CACHE: Path = DATA_DIR / "beta_invitations_cache.json"
_RELEASE_NOTES_CACHE_DIR: Path = DATA_DIR / "release_notes_cache"
_WHATS_NEW_STATE: Path = DATA_DIR / "whats_new_state.json"
_FETCH_TIMEOUT: float = 10.0
_DEFAULT_INVITATIONS_URL: str = (
    f"https://raw.githubusercontent.com/"
    f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/main/beta_invitations.json"
)
_RELEASE_NOTES_BASE_URL: str = f"https://raw.githubusercontent.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/main/docs/release_notes"
_BITSWHISPERER_SCHEME: str = "bitswhisperer://release-notes/"
_BETA_KEYSTORE_KEY: str = "beta_invitation_hash"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureChange:
    """Describes a single feature flag change for the What's New dialog.

    Attributes:
        feature_name: The feature flag identifier.
        label: Human-readable feature label.
        description: Short feature description.
        change_type: One of ``"added"``, ``"enabled"``,
            ``"disabled"``, ``"version_update"``.
        release_notes: Optional Markdown release notes content.
        added_in_version: The version the feature was introduced.
        change_category: Category of the change — ``"feature"``
            (default), ``"provider"``, or ``"system"``.
    """

    feature_name: str
    label: str
    description: str
    change_type: str  # "added", "enabled", "disabled", "version_update"
    release_notes: str = ""
    added_in_version: str = ""
    change_category: str = "feature"


@dataclass
class WhatsNewState:
    """Persisted state tracking what the user has already seen.

    Attributes:
        last_seen_version: The app version when the user last
            dismissed the What's New dialog.
        seen_flags: Dict of feature_name → enabled (bool) at the
            time the user last saw the state.
        last_checked: Unix timestamp of last state save.
        beta_mode: Whether beta mode was active last time.
    """

    last_seen_version: str = ""
    seen_flags: dict[str, bool] = field(default_factory=dict)
    last_checked: float = 0.0
    beta_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-compatible dict."""
        return {
            "last_seen_version": self.last_seen_version,
            "seen_flags": self.seen_flags,
            "last_checked": self.last_checked,
            "beta_mode": self.beta_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WhatsNewState:
        """Deserialise from a JSON dict."""
        return cls(
            last_seen_version=data.get("last_seen_version", ""),
            seen_flags=data.get("seen_flags", {}),
            last_checked=data.get("last_checked", 0.0),
            beta_mode=data.get("beta_mode", False),
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BetaService:
    """Manage beta programme enrolment and What's New change detection.

    Args:
        key_store: An optional :class:`KeyStore` instance. If provided,
            beta status is persisted in the OS credential store.
        invitations_url: URL to the remote ``beta_invitations.json``.
        beta_enabled_in_settings: Whether the user has toggled beta
            mode in settings (must also have a valid invitation).
    """

    def __init__(
        self,
        key_store: Any | None = None,
        invitations_url: str = "",
        beta_enabled_in_settings: bool = False,
        alpha_mode: bool = False,
    ) -> None:
        self._key_store = key_store
        self._invitations_url = invitations_url or _DEFAULT_INVITATIONS_URL
        self._beta_enabled_in_settings = beta_enabled_in_settings
        self._invitation_verified = False
        self._alpha_mode = alpha_mode

        # Check if already verified via keystore
        if self._key_store is not None:
            stored = self._key_store.get_key(_BETA_KEYSTORE_KEY)
            if stored:
                self._invitation_verified = True

    # ------------------------------------------------------------------ #
    # Beta tester status                                                   #
    # ------------------------------------------------------------------ #

    @property
    def is_beta_tester(self) -> bool:
        """Whether the user is an active beta tester.

        Requires both a verified invitation code AND beta mode
        enabled in settings — or alpha mode enabled (which
        bypasses invitation requirements).

        Returns:
            ``True`` if the user should see beta features.
        """
        if self._alpha_mode:
            return True
        return self._invitation_verified and self._beta_enabled_in_settings

    @property
    def is_alpha_tester(self) -> bool:
        """Whether alpha testing mode is active.

        Alpha testers are implicitly beta testers and do not
        require an invitation code.
        """
        return self._alpha_mode

    @property
    def is_invitation_verified(self) -> bool:
        """Whether an invitation code has been verified (ever)."""
        return self._invitation_verified

    def set_beta_enabled(self, enabled: bool) -> None:
        """Update the beta-enabled-in-settings flag.

        Args:
            enabled: Whether the user toggled beta mode on.
        """
        self._beta_enabled_in_settings = enabled

    def set_alpha_mode(self, enabled: bool) -> None:
        """Enable or disable alpha testing mode.

        When enabled, the user is implicitly a beta tester
        without requiring an invitation code.

        Args:
            enabled: Whether to activate alpha testing mode.
        """
        self._alpha_mode = enabled

    # ------------------------------------------------------------------ #
    # Invitation verification                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def hash_code(code: str) -> str:
        """Hash an invitation code with SHA-256.

        Args:
            code: The plaintext invitation code.

        Returns:
            Hex-encoded SHA-256 hash.
        """
        normalised = code.strip().upper()
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    def verify_invitation(self, code: str) -> bool:
        """Verify a beta invitation code against the remote list.

        Fetches the remote invitations JSON, hashes the provided
        code, and checks for a match. On success, persists the hash
        in the OS credential store.

        Args:
            code: Plaintext invitation code entered by the user.

        Returns:
            ``True`` if the code is valid.
        """
        if not code or not code.strip():
            return False

        code_hash = self.hash_code(code)
        valid_hashes = self._fetch_invitations()

        if code_hash in valid_hashes:
            self._invitation_verified = True
            if self._key_store is not None:
                self._key_store.store_key(_BETA_KEYSTORE_KEY, code_hash)
            logger.info("Beta invitation code verified successfully")
            return True

        logger.warning("Beta invitation code rejected")
        return False

    def revoke_beta(self) -> None:
        """Revoke beta tester status and clear stored invitation."""
        self._invitation_verified = False
        self._beta_enabled_in_settings = False
        if self._key_store is not None:
            self._key_store.delete_key(_BETA_KEYSTORE_KEY)
        logger.info("Beta tester status revoked")

    def _fetch_invitations(self) -> set[str]:
        """Fetch the remote invitations file.

        Returns:
            Set of valid SHA-256 hashed codes.
        """
        # Try remote first
        try:
            resp = httpx.get(
                self._invitations_url,
                timeout=_FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            codes = set(data.get("codes", []))

            # Cache for offline use
            self._save_invitations_cache(data)

            return codes
        except Exception as exc:
            logger.warning("Failed to fetch beta invitations: %s", exc)

        # Fall back to cache
        return self._load_invitations_cache()

    def _load_invitations_cache(self) -> set[str]:
        """Load invitation hashes from local cache."""
        if not _INVITATIONS_CACHE.exists():
            return set()
        try:
            data = json.loads(_INVITATIONS_CACHE.read_text("utf-8"))
            return set(data.get("codes", []))
        except Exception as exc:
            logger.warning("Failed to load invitations cache: %s", exc)
            return set()

    @staticmethod
    def _save_invitations_cache(data: dict[str, Any]) -> None:
        """Persist invitation data to local cache."""
        try:
            _INVITATIONS_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _INVITATIONS_CACHE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save invitations cache: %s", exc)

    # ------------------------------------------------------------------ #
    # Release notes                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def resolve_release_notes_url(uri: str) -> str:
        """Resolve a ``bitswhisperer://`` URI to a raw GitHub URL.

        Example::

            >>> BetaService.resolve_release_notes_url(
            ...     "bitswhisperer://release-notes/watch_folder"
            ... )
            'https://raw.githubusercontent.com/.../docs/release_notes/watch_folder.md'

        Args:
            uri: The ``bitswhisperer://release-notes/<feature>`` URI,
                or a plain HTTPS URL (returned unchanged).

        Returns:
            The resolved URL string.
        """
        if uri.startswith(_BITSWHISPERER_SCHEME):
            feature = uri[len(_BITSWHISPERER_SCHEME) :]
            return f"{_RELEASE_NOTES_BASE_URL}/{feature}.md"
        return uri

    def fetch_release_notes(self, feature_name: str, url: str = "") -> str:
        """Fetch release notes Markdown for a feature.

        Tries the network first, then falls back to a local cache.

        Args:
            feature_name: Feature identifier (used for cache key).
            url: The release notes URL or ``bitswhisperer://`` URI.

        Returns:
            Markdown string, or empty string on failure.
        """
        if not url:
            url = f"{_BITSWHISPERER_SCHEME}{feature_name}"
        resolved = self.resolve_release_notes_url(url)
        cache_file = _RELEASE_NOTES_CACHE_DIR / f"{feature_name}.md"

        # Try remote
        try:
            resp = httpx.get(
                resolved,
                timeout=_FETCH_TIMEOUT,
                follow_redirects=True,
            )
            resp.raise_for_status()
            content = resp.text

            # Cache
            _RELEASE_NOTES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content, encoding="utf-8")

            return content
        except Exception as exc:
            logger.debug("Failed to fetch release notes for %s: %s", feature_name, exc)

        # Fall back to cache
        if cache_file.exists():
            try:
                return cache_file.read_text("utf-8")
            except Exception:
                pass

        return ""

    # ------------------------------------------------------------------ #
    # What's New change detection                                          #
    # ------------------------------------------------------------------ #

    def load_whats_new_state(self) -> WhatsNewState:
        """Load the persisted What's New state from disk.

        Returns:
            The last saved state, or fresh defaults.
        """
        if not _WHATS_NEW_STATE.exists():
            return WhatsNewState()
        try:
            data = json.loads(_WHATS_NEW_STATE.read_text("utf-8"))
            return WhatsNewState.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to load What's New state: %s", exc)
            return WhatsNewState()

    @staticmethod
    def save_whats_new_state(state: WhatsNewState) -> None:
        """Persist the What's New state to disk.

        Args:
            state: The state to save.
        """
        try:
            state.last_checked = time.time()
            _WHATS_NEW_STATE.parent.mkdir(parents=True, exist_ok=True)
            _WHATS_NEW_STATE.write_text(
                json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save What's New state: %s", exc)

    def detect_changes(
        self,
        current_flags: dict[str, Any],
        is_beta: bool,
    ) -> list[FeatureChange]:
        """Detect feature flag changes since the user last saw them.

        Compares the current feature flag config against the persisted
        :class:`WhatsNewState`. Returns a list of :class:`FeatureChange`
        items for:

        - **New features** the user hasn't seen before.
        - **Enabled features** that were previously disabled.
        - **Disabled features** that were previously enabled.
        - **Version updates** (app version changed).

        Args:
            current_flags: Dict of ``{name: FeatureFlag}`` from the
                :class:`FeatureFlagService`.
            is_beta: Whether the user is currently a beta tester.

        Returns:
            List of changes to show in the What's New dialog.
        """
        state = self.load_whats_new_state()
        changes: list[FeatureChange] = []

        # 1. Version bump notification
        if state.last_seen_version and state.last_seen_version != APP_VERSION:
            changes.append(
                FeatureChange(
                    feature_name="__version__",
                    label=f"Updated to v{APP_VERSION}",
                    description=(
                        f"BITS Whisperer has been updated from "
                        f"v{state.last_seen_version} to v{APP_VERSION}."
                    ),
                    change_type="version_update",
                    added_in_version=APP_VERSION,
                    change_category="system",
                )
            )

        # 2. Beta mode toggled
        if is_beta != state.beta_mode and state.last_seen_version:
            label = "Beta Mode Enabled" if is_beta else "Beta Mode Disabled"
            desc = (
                "You are now receiving beta features ahead of general release."
                if is_beta
                else "Beta features have been deactivated. You will only see "
                "generally available features."
            )
            changes.append(
                FeatureChange(
                    feature_name="__beta_mode__",
                    label=label,
                    description=desc,
                    change_type="enabled" if is_beta else "disabled",
                )
            )

        # 3. Per-feature changes
        for name, flag in current_flags.items():
            # Determine effective enabled state
            if is_beta:
                currently_enabled = getattr(flag, "beta_enabled", flag.enabled)
            else:
                currently_enabled = flag.enabled

            previously_enabled = state.seen_flags.get(name)

            # Determine change category based on flag name
            category = "provider" if name.startswith("provider_") else "feature"

            if previously_enabled is None:
                # New feature the user hasn't seen
                if state.last_seen_version:
                    # Only show "added" if user has a prior state
                    changes.append(
                        FeatureChange(
                            feature_name=name,
                            label=flag.label or name,
                            description=flag.description,
                            change_type="added",
                            release_notes=getattr(flag, "release_notes_url", ""),
                            added_in_version=getattr(flag, "added_in_version", ""),
                            change_category=category,
                        )
                    )
            elif currently_enabled and not previously_enabled:
                changes.append(
                    FeatureChange(
                        feature_name=name,
                        label=flag.label or name,
                        description=flag.description,
                        change_type="enabled",
                        added_in_version=getattr(flag, "added_in_version", ""),
                        change_category=category,
                    )
                )
            elif not currently_enabled and previously_enabled:
                changes.append(
                    FeatureChange(
                        feature_name=name,
                        label=flag.label or name,
                        description=flag.description,
                        change_type="disabled",
                        added_in_version=getattr(flag, "added_in_version", ""),
                        change_category=category,
                    )
                )

        return changes

    def snapshot_current_state(
        self,
        current_flags: dict[str, Any],
        is_beta: bool,
    ) -> None:
        """Save the current flag states so future runs can detect changes.

        Call this after the user dismisses the What's New dialog.

        Args:
            current_flags: Dict of ``{name: FeatureFlag}`` from the
                :class:`FeatureFlagService`.
            is_beta: Whether beta mode is currently active.
        """
        seen: dict[str, bool] = {}
        for name, flag in current_flags.items():
            if is_beta:
                seen[name] = getattr(flag, "beta_enabled", flag.enabled)
            else:
                seen[name] = flag.enabled

        state = WhatsNewState(
            last_seen_version=APP_VERSION,
            seen_flags=seen,
            last_checked=time.time(),
            beta_mode=is_beta,
        )
        self.save_whats_new_state(state)
