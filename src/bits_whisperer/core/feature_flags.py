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
        min_version: Minimum app version required (semver string).
        label: Human-readable feature name for UI display.
        description: Brief explanation shown in settings or logs.
    """

    name: str
    enabled: bool = True
    min_version: str = "0.0.0"
    label: str = ""
    description: str = ""


@dataclass
class FeatureFlagConfig:
    """The complete feature flag configuration document.

    Attributes:
        version: Schema version (currently ``1``).
        description: Human-readable description of the config.
        features: Mapping of feature name → :class:`FeatureFlag`.
        fetched_at: Unix timestamp of the last successful remote fetch.
    """

    version: int = 1
    description: str = ""
    features: dict[str, FeatureFlag] = field(default_factory=dict)
    fetched_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for caching."""
        return {
            "version": self.version,
            "description": self.description,
            "features": {name: asdict(flag) for name, flag in self.features.items()},
            "fetched_at": self.fetched_at,
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
                features[name] = FeatureFlag(
                    name=name,
                    enabled=entry.get("enabled", True),
                    min_version=entry.get("min_version", "0.0.0"),
                    label=entry.get("label", name),
                    description=entry.get("description", ""),
                )
        return cls(
            version=data.get("version", 1),
            description=data.get("description", ""),
            features=features,
            fetched_at=data.get("fetched_at", 0.0),
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
