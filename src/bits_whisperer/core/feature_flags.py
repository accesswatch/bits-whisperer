"""Remote feature flag service for staged feature rollout.

This module provides a :class:`FeatureFlagService` that fetches a
remote JSON configuration from a URL (typically a raw GitHub file)
and evaluates whether individual features should be enabled in the
running application.  The service supports:

- **Remote config**: Fetch feature flags from any HTTPS URL.
- **Local caching**: Cache the remote config on disk so the app
  works offline and starts instantly.
- **TTL-based refresh**: Re-fetch the remote config every *N* hours
  (default 24) to pick up changes without restart.
- **Version gating**: Each flag may specify a ``min_version``;
  features requiring a newer app version are automatically disabled.
- **Local overrides**: Developers and QA can force-enable or
  force-disable individual flags via settings, overriding the
  remote config.
- **Graceful degradation**: Network failures fall back to the
  cached config, then to built-in defaults (all enabled).

Usage
-----
::

    from bits_whisperer.core.feature_flags import FeatureFlagService

    service = FeatureFlagService()
    service.refresh()  # non-blocking; uses cache on failure

    if service.is_enabled("live_transcription"):
        show_live_transcription_menu()
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
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
_DEFAULT_REMOTE_URL: str = (
    f"https://raw.githubusercontent.com/"
    f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/main/feature_flags.json"
)
_CACHE_PATH: Path = DATA_DIR / "feature_flags_cache.json"
_DEFAULT_TTL_HOURS: float = 24.0
_FETCH_TIMEOUT: float = 10.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureFlag:
    """A single feature flag entry.

    Attributes:
        name: Internal identifier (e.g. ``"live_transcription"``).
        enabled: Whether the feature is enabled in the remote config.
        beta_enabled: Whether the feature is enabled for beta testers.
            When ``None``, inherits from ``enabled``.
        min_version: Minimum app version required (semver string).
        added_in_version: The version in which this feature was introduced.
        label: Human-readable feature name for UI display.
        description: Brief explanation shown in settings or logs.
        release_notes_url: URL or ``bitswhisperer://`` URI pointing
            to Markdown release notes for this feature.
    """

    name: str
    enabled: bool = True
    beta_enabled: bool | None = None
    min_version: str = "0.0.0"
    added_in_version: str = ""
    label: str = ""
    description: str = ""
    release_notes_url: str = ""


@dataclass(frozen=True)
class LicensingConfig:
    """Remotely adjustable licensing parameters.

    These values are served from ``feature_flags.json`` so admins can
    extend or shorten grace periods, trial durations, and verification
    intervals without pushing a code change or requiring user action.

    Attributes:
        trial_days: Length of the free trial in days.
        offline_grace_days: How many days a cached verification
            remains trusted when the device is offline.
        reverify_hours: How often (in hours) the licence key is
            re-checked against the backend.
        trial_warning_days: When the trial has this many days or
            fewer remaining, show a gentle reminder.
        max_devices: Maximum number of devices a single licence
            key can be activated on simultaneously.
        admin_message: System-wide broadcast message shown as a
            banner in the licence dialog.  Empty string means
            no message.
        purchase_url: Remotely updatable URL for the purchase /
            renewal page.  Falls back to a compiled default when
            empty.
        trial_extension_days: Global bonus days added to every
            active trial.  Admins can bump this to grant extra
            time without per-user changes.
        grace_mode_enabled: When ``True``, expired trials and
            lapsed licences enter a read-only grace mode instead
            of a hard lockout.
        grace_mode_days: How many days the read-only grace mode
            lasts after the trial or licence expires.
        activation_mode: Controls which activation paths are
            available.  ``"beta"`` restricts to beta testers
            and registered keys only.  ``"live"`` opens all
            paths (trial, register, BITS member, beta).
            ``"closed"`` blocks all new activations.
        tier_names: Human-readable display names keyed by status
            code (``L``, ``A``, ``C``, ``T``).  Admins can
            rename tiers (e.g. for rebranding) without a code
            change.
    """

    activation_mode: str = "beta"
    trial_days: int = 7
    offline_grace_days: int = 30
    reverify_hours: int = 24
    trial_warning_days: int = 2
    max_devices: int = 3
    admin_message: str = ""
    purchase_url: str = ""
    trial_extension_days: int = 0
    grace_mode_enabled: bool = False
    grace_mode_days: int = 7
    tier_names: dict[str, str] = field(
        default_factory=lambda: {
            "L": "Lifetime Member",
            "A": "Active Membership",
            "C": "Paying Contributor",
            "T": "Alpha Tester",
        }
    )


# Default instance when no remote config is available
_DEFAULT_LICENSING_CONFIG = LicensingConfig()


@dataclass
class FeatureFlagConfig:
    """The complete feature flag configuration document.

    Attributes:
        version: Schema version (currently ``1``).
        description: Human-readable description of the config.
        features: Mapping of feature name → :class:`FeatureFlag`.
        fetched_at: Unix timestamp of the last successful remote fetch.
        licensing: Remotely adjustable licensing parameters.
    """

    version: int = 1
    description: str = ""
    features: dict[str, FeatureFlag] = field(default_factory=dict)
    fetched_at: float = 0.0
    beta_invitations_url: str = ""
    beta_welcome_message: str = ""
    licensing: LicensingConfig = field(default_factory=LicensingConfig)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for caching."""
        return {
            "version": self.version,
            "description": self.description,
            "features": {name: asdict(flag) for name, flag in self.features.items()},
            "fetched_at": self.fetched_at,
            "beta": {
                "invitations_url": self.beta_invitations_url,
                "welcome_message": self.beta_welcome_message,
            },
            "licensing": asdict(self.licensing),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureFlagConfig:
        """Reconstruct from a JSON-compatible dict.

        Unknown keys in each feature entry are silently ignored so
        future schema extensions don't break older app versions.
        """
        features: dict[str, FeatureFlag] = {}
        raw_features = data.get("features", {})
        for name, entry in raw_features.items():
            if isinstance(entry, dict):
                beta_val = entry.get("beta_enabled")
                features[name] = FeatureFlag(
                    name=name,
                    enabled=entry.get("enabled", True),
                    beta_enabled=beta_val if beta_val is not None else None,
                    min_version=entry.get("min_version", "0.0.0"),
                    added_in_version=entry.get("added_in_version", ""),
                    label=entry.get("label", name),
                    description=entry.get("description", ""),
                    release_notes_url=entry.get("release_notes_url", ""),
                )
        beta_section = data.get("beta", {})
        lic_section = data.get("licensing", {})
        default_tier_names = {
            "L": "Lifetime Member",
            "A": "Active Membership",
            "C": "Paying Contributor",
            "T": "Alpha Tester",
        }
        raw_tiers = lic_section.get("tier_names", default_tier_names)
        # Ensure tier_names is a dict[str, str] even if remote JSON
        # has unexpected types.
        tier_names = {
            str(k): str(v)
            for k, v in raw_tiers.items()
            if isinstance(k, str) and isinstance(v, str)
        } or default_tier_names
        licensing = LicensingConfig(
            activation_mode=lic_section.get("activation_mode", "beta"),
            trial_days=lic_section.get("trial_days", 7),
            offline_grace_days=lic_section.get("offline_grace_days", 30),
            reverify_hours=lic_section.get("reverify_hours", 24),
            trial_warning_days=lic_section.get("trial_warning_days", 2),
            max_devices=lic_section.get("max_devices", 3),
            admin_message=lic_section.get("admin_message", ""),
            purchase_url=lic_section.get("purchase_url", ""),
            trial_extension_days=lic_section.get("trial_extension_days", 0),
            grace_mode_enabled=lic_section.get("grace_mode_enabled", False),
            grace_mode_days=lic_section.get("grace_mode_days", 7),
            tier_names=tier_names,
        )
        return cls(
            version=data.get("version", 1),
            description=data.get("description", ""),
            features=features,
            fetched_at=data.get("fetched_at", 0.0),
            beta_invitations_url=beta_section.get("invitations_url", ""),
            beta_welcome_message=beta_section.get("welcome_message", ""),
            licensing=licensing,
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FeatureFlagService:
    """Fetch, cache, and evaluate remote feature flags.

    Args:
        remote_url: HTTPS URL to the remote ``feature_flags.json``.
            Defaults to the raw GitHub URL for the main branch.
        cache_path: Local file path for the cached config.
        ttl_hours: How many hours before re-fetching the remote config.
        app_version: The running application version string.
        local_overrides: Dict of ``{feature_name: bool}`` to
            force-enable or force-disable flags regardless of the
            remote config.
    """

    def __init__(
        self,
        remote_url: str = "",
        cache_path: Path | None = None,
        ttl_hours: float = _DEFAULT_TTL_HOURS,
        app_version: str = "",
        local_overrides: dict[str, bool] | None = None,
    ) -> None:
        """Initialise the feature flag service."""
        self._remote_url = remote_url or _DEFAULT_REMOTE_URL
        self._cache_path = cache_path or _CACHE_PATH
        self._ttl_seconds = ttl_hours * 3600
        self._app_version = app_version or APP_VERSION
        self._local_overrides: dict[str, bool] = dict(local_overrides or {})
        self._config: FeatureFlagConfig = FeatureFlagConfig()
        self._loaded = False

        # Try loading from cache immediately (no network hit)
        self._load_cache()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def refresh(self, force: bool = False) -> bool:
        """Fetch the remote config if the cache is stale or *force* is set.

        This method is safe to call from any thread.  It blocks for up
        to ``_FETCH_TIMEOUT`` seconds on the HTTP request.

        Args:
            force: If ``True``, fetch regardless of TTL.

        Returns:
            ``True`` if the remote config was successfully fetched and
            applied, ``False`` otherwise (cache or defaults are used).
        """
        if not force and not self._is_stale():
            logger.debug("Feature flags cache is fresh — skipping fetch")
            return True

        return self._fetch_remote()

    def is_enabled(self, feature_name: str) -> bool:
        """Check whether a feature is enabled.

        Evaluation order:

        1. **Local overrides** — if the feature has a local override
           (from settings or developer config), that value wins.
        2. **Remote config** — if the feature exists in the config,
           check both ``enabled`` and ``min_version``.
        3. **Default** — unknown features are enabled by default,
           following the principle of least surprise.

        Args:
            feature_name: The feature identifier (e.g.
                ``"live_transcription"``).

        Returns:
            ``True`` if the feature should be shown to the user.
        """
        # 1. Local override (developer / settings)
        if feature_name in self._local_overrides:
            return self._local_overrides[feature_name]

        # 2. Remote config
        flag = self._config.features.get(feature_name)
        if flag is None:
            # Unknown feature — enable by default
            return True

        if not flag.enabled:
            return False

        # 3. Version gate
        return self._version_satisfies(flag.min_version)

    def get_flag(self, feature_name: str) -> FeatureFlag | None:
        """Get the full :class:`FeatureFlag` metadata for a feature.

        Args:
            feature_name: Feature identifier.

        Returns:
            The flag, or ``None`` if not present in the config.
        """
        return self._config.features.get(feature_name)

    def get_all_flags(self) -> dict[str, FeatureFlag]:
        """Return all feature flags from the current config.

        Returns:
            Dict mapping feature name → :class:`FeatureFlag`.
        """
        return dict(self._config.features)

    def is_enabled_for_beta(self, feature_name: str) -> bool:
        """Check whether a feature is enabled for beta testers.

        Same evaluation as :meth:`is_enabled`, but uses the
        ``beta_enabled`` value instead of ``enabled``.  Falls back
        to ``enabled`` when ``beta_enabled`` is ``None``.

        Args:
            feature_name: Feature identifier.

        Returns:
            ``True`` if the feature should be shown to beta users.
        """
        # 1. Local override always wins
        if feature_name in self._local_overrides:
            return self._local_overrides[feature_name]

        # 2. Remote config — prefer beta_enabled, fall back to enabled
        flag = self._config.features.get(feature_name)
        if flag is None:
            return True

        effective = flag.beta_enabled if flag.beta_enabled is not None else flag.enabled
        if not effective:
            return False

        return self._version_satisfies(flag.min_version)

    def set_override(self, feature_name: str, enabled: bool) -> None:
        """Set a local override for a feature flag.

        Args:
            feature_name: Feature identifier.
            enabled: Whether to force-enable (``True``) or
                force-disable (``False``).
        """
        self._local_overrides[feature_name] = enabled
        logger.info(
            "Feature flag override: %s = %s",
            feature_name,
            enabled,
        )

    def clear_override(self, feature_name: str) -> None:
        """Remove a local override, reverting to remote config.

        Args:
            feature_name: Feature identifier.
        """
        self._local_overrides.pop(feature_name, None)
        logger.info("Feature flag override removed: %s", feature_name)

    def get_overrides(self) -> dict[str, bool]:
        """Return all current local overrides.

        Returns:
            Dict of ``{feature_name: enabled}``.
        """
        return dict(self._local_overrides)

    @property
    def config(self) -> FeatureFlagConfig:
        """The current feature flag config (read-only)."""
        return self._config

    def get_licensing_config(self) -> LicensingConfig:
        """Return the current remotely configurable licensing parameters.

        Falls back to defaults when no remote config has been fetched.
        """
        return self._config.licensing

    @property
    def remote_url(self) -> str:
        """The configured remote URL."""
        return self._remote_url

    @property
    def is_loaded(self) -> bool:
        """Whether at least one config has been loaded (cache or remote)."""
        return self._loaded

    @property
    def last_fetched(self) -> float:
        """Unix timestamp of the last successful remote fetch."""
        return self._config.fetched_at

    # ------------------------------------------------------------------ #
    # Private methods                                                      #
    # ------------------------------------------------------------------ #

    def _is_stale(self) -> bool:
        """Check if the cached config has exceeded the TTL."""
        if not self._loaded or self._config.fetched_at <= 0:
            return True
        return (time.time() - self._config.fetched_at) > self._ttl_seconds

    def _fetch_remote(self) -> bool:
        """Fetch the remote feature flags JSON.

        Returns:
            ``True`` on success.
        """
        logger.info("Fetching feature flags from %s", self._remote_url)
        try:
            resp = httpx.get(
                self._remote_url,
                timeout=_FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch feature flags: %s", exc)
            return False
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid feature flags JSON: %s", exc)
            return False

        # Parse and apply
        self._config = FeatureFlagConfig.from_dict(data)
        self._config.fetched_at = time.time()
        self._loaded = True

        # Persist cache
        self._save_cache()

        logger.info(
            "Feature flags loaded: %d feature(s), schema v%d",
            len(self._config.features),
            self._config.version,
        )
        return True

    def _load_cache(self) -> bool:
        """Load config from the local cache file.

        Returns:
            ``True`` if the cache was loaded successfully.
        """
        if not self._cache_path.exists():
            return False
        try:
            data = json.loads(self._cache_path.read_text("utf-8"))
            self._config = FeatureFlagConfig.from_dict(data)
            self._loaded = True
            logger.debug(
                "Feature flags loaded from cache (%d features)",
                len(self._config.features),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to load feature flags cache: %s", exc)
            return False

    def _save_cache(self) -> None:
        """Persist the current config to the local cache file."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._config.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug("Feature flags cache saved to %s", self._cache_path)
        except Exception as exc:
            logger.warning("Failed to save feature flags cache: %s", exc)

    def _version_satisfies(self, min_version: str) -> bool:
        """Check if the app version meets the minimum requirement.

        Args:
            min_version: Semver string (e.g. ``"1.2.0"``).

        Returns:
            ``True`` if ``APP_VERSION >= min_version``.
        """
        try:
            from packaging.version import Version

            return Version(self._app_version) >= Version(min_version)
        except Exception:
            # If parsing fails, assume satisfied
            logger.debug(
                "Cannot compare versions: app=%s min=%s",
                self._app_version,
                min_version,
            )
            return True
