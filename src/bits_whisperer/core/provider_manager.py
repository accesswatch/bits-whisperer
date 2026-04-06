"""Provider registry and routing for transcription jobs.

Provider modules are loaded lazily — only when a user actually selects or
configures a provider. This keeps the initial import lightweight and allows
the installer to ship without bundling every provider SDK.

Providers can be gated via remote feature flags (``provider_<key>``).
When a provider's flag is disabled, it is excluded from discovery and
listing — the same as if its SDK were not installed.
"""

from __future__ import annotations

import importlib
import logging
import sys
from typing import TYPE_CHECKING, Final

from bits_whisperer.core.sdk_installer import is_sdk_available
from bits_whisperer.providers.base import ProviderCapabilities, TranscriptionProvider

if TYPE_CHECKING:
    from bits_whisperer.core.beta_service import BetaService
    from bits_whisperer.core.feature_flags import FeatureFlagService

logger = logging.getLogger(__name__)

# Map of provider key to (module_path, class_name)
_PROVIDER_MODULES: Final[dict[str, tuple[str, str]]] = {
    "local_whisper": (
        "bits_whisperer.providers.local_whisper",
        "LocalWhisperProvider",
    ),
    "openai_whisper": (
        "bits_whisperer.providers.openai_whisper",
        "OpenAIWhisperProvider",
    ),
    "google_speech": (
        "bits_whisperer.providers.google_speech",
        "GoogleSpeechProvider",
    ),
    "azure_speech": (
        "bits_whisperer.providers.azure_speech",
        "AzureSpeechProvider",
    ),
    "azure_embedded": (
        "bits_whisperer.providers.azure_embedded",
        "AzureEmbeddedSpeechProvider",
    ),
    "deepgram": (
        "bits_whisperer.providers.deepgram_provider",
        "DeepgramProvider",
    ),
    "assemblyai": (
        "bits_whisperer.providers.assemblyai_provider",
        "AssemblyAIProvider",
    ),
    "aws_transcribe": (
        "bits_whisperer.providers.aws_transcribe",
        "AWSTranscribeProvider",
    ),
    "gemini": (
        "bits_whisperer.providers.gemini_provider",
        "GeminiProvider",
    ),
    "groq_whisper": (
        "bits_whisperer.providers.groq_whisper",
        "GroqWhisperProvider",
    ),
    "rev_ai": (
        "bits_whisperer.providers.rev_ai_provider",
        "RevAIProvider",
    ),
    "speechmatics": (
        "bits_whisperer.providers.speechmatics_provider",
        "SpeechmaticsProvider",
    ),
    "elevenlabs": (
        "bits_whisperer.providers.elevenlabs_provider",
        "ElevenLabsProvider",
    ),
    "auphonic": (
        "bits_whisperer.providers.auphonic_provider",
        "AuphonicProvider",
    ),
    "mai_transcribe": (
        "bits_whisperer.providers.mai_transcribe_provider",
        "MAITranscribeProvider",
    ),
    "vosk": (
        "bits_whisperer.providers.vosk_provider",
        "VoskProvider",
    ),
    "parakeet": (
        "bits_whisperer.providers.parakeet_provider",
        "ParakeetProvider",
    ),
}

# Windows-only provider
if sys.platform == "win32":
    _PROVIDER_MODULES["windows_speech"] = (
        "bits_whisperer.providers.windows_speech",
        "WindowsSpeechProvider",
    )


def _load_provider_class(key: str) -> type[TranscriptionProvider] | None:
    """Lazily import and return a provider class by key.

    Args:
        key: Provider identifier.

    Returns:
        The provider class, or None if loading fails.
    """
    entry = _PROVIDER_MODULES.get(key)
    if entry is None:
        return None

    module_path, class_name = entry
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except Exception as exc:
        logger.debug("Could not load provider module '%s': %s", key, exc)
        return None


class ProviderManager:
    """Registry of available transcription providers.

    Providers are loaded lazily — their Python module is imported only
    when ``get_provider()`` is called (or during the first listing that
    needs provider capabilities). This means the app starts quickly
    even if most SDK packages are not installed.

    Args:
        feature_flag_service: Optional feature flag service for
            provider-level gating via ``provider_<key>`` flags.
        beta_service: Optional beta service to determine whether
            the user is a beta tester (uses ``is_enabled_for_beta``).
    """

    def __init__(
        self,
        feature_flag_service: FeatureFlagService | None = None,
        beta_service: BetaService | None = None,
    ) -> None:
        self._providers: dict[str, TranscriptionProvider] = {}
        self._enabled: set[str] = set()
        self._unavailable: set[str] = set()  # SDK not installed
        self._flag_disabled: set[str] = set()  # Disabled by feature flag
        self._feature_flags = feature_flag_service
        self._beta_service = beta_service
        self._discover_available()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _is_provider_flag_enabled(self, key: str) -> bool:
        """Check if the ``provider_<key>`` feature flag is enabled.

        Args:
            key: Provider identifier.

        Returns:
            ``True`` if the provider is allowed by feature flags
            (or if no flag service is configured).
        """
        if self._feature_flags is None:
            return True
        flag_name = f"provider_{key}"
        if self._beta_service is not None and self._beta_service.is_beta_tester:
            return self._feature_flags.is_enabled_for_beta(flag_name)
        return self._feature_flags.is_enabled(flag_name)

    def _discover_available(self) -> None:
        """Populate the enabled set based on SDK availability and feature flags.

        Does NOT import provider modules — uses the SDK registry check
        (which tests the *SDK* import, not the provider module itself).
        Providers whose SDK is missing are tracked in ``_unavailable``.
        Providers disabled by feature flags are tracked in ``_flag_disabled``.
        """
        for key in _PROVIDER_MODULES:
            if not self._is_provider_flag_enabled(key):
                self._flag_disabled.add(key)
                logger.debug("Provider '%s': disabled by feature flag", key)
            elif is_sdk_available(key):
                self._enabled.add(key)
            else:
                self._unavailable.add(key)
                logger.debug("Provider '%s': SDK not installed — skipped", key)

    def _ensure_loaded(self, key: str) -> TranscriptionProvider | None:
        """Lazily load and cache a provider instance.

        Args:
            key: Provider identifier.

        Returns:
            TranscriptionProvider instance, or None on failure.
        """
        if key in self._providers:
            return self._providers[key]

        cls = _load_provider_class(key)
        if cls is None:
            return None

        try:
            instance = cls()
            self._providers[key] = instance
            return instance
        except Exception as exc:
            logger.warning("Failed to instantiate provider '%s': %s", key, exc)
            return None

    def _register_defaults(self) -> None:
        """Instantiate all built-in provider adapters.

        Kept for backward compatibility — callers that expect all
        providers to be loaded eagerly can invoke this.
        """
        for key in list(_PROVIDER_MODULES.keys()):
            if key not in self._unavailable:
                self._ensure_loaded(key)

    def register(self, key: str, provider: TranscriptionProvider) -> None:
        """Register a custom or replacement provider.

        Args:
            key: Unique provider identifier.
            provider: TranscriptionProvider instance.
        """
        self._providers[key] = provider
        self._enabled.add(key)
        self._unavailable.discard(key)

    def refresh_availability(self) -> None:
        """Recheck which provider SDKs are installed.

        Call after installing an SDK via ``sdk_installer.install_sdk``
        to make newly-installed providers appear.
        """
        for key in list(self._unavailable):
            if is_sdk_available(key):
                self._unavailable.discard(key)
                self._enabled.add(key)
                logger.info("Provider '%s': SDK now available", key)

    def refresh_feature_flags(self) -> None:
        """Re-evaluate provider visibility after feature flag changes.

        Moves providers between ``_flag_disabled`` and ``_enabled``
        based on current feature flag state.
        """
        # Re-enable providers whose flag was turned on
        for key in list(self._flag_disabled):
            if self._is_provider_flag_enabled(key):
                self._flag_disabled.discard(key)
                if is_sdk_available(key):
                    self._enabled.add(key)
                else:
                    self._unavailable.add(key)
                logger.info("Provider '%s': re-enabled by feature flag", key)

        # Disable providers whose flag was turned off
        for key in list(self._enabled):
            if not self._is_provider_flag_enabled(key):
                self._enabled.discard(key)
                self._flag_disabled.add(key)
                logger.info("Provider '%s': disabled by feature flag", key)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_providers(self) -> list[str]:
        """Return keys of all known providers (including unavailable)."""
        return list(_PROVIDER_MODULES.keys())

    def list_enabled_providers(self) -> list[str]:
        """Return keys of enabled providers (SDK installed)."""
        return [k for k in _PROVIDER_MODULES if k in self._enabled]

    def list_unavailable_providers(self) -> list[str]:
        """Return keys of providers whose SDK is not installed."""
        return list(self._unavailable)

    def get_provider(self, key: str) -> TranscriptionProvider | None:
        """Get a provider instance by key (lazy-loaded).

        Args:
            key: Provider identifier.

        Returns:
            TranscriptionProvider or None.
        """
        if key in self._unavailable or key in self._flag_disabled:
            return None
        return self._ensure_loaded(key)

    def get_capabilities(self, key: str) -> ProviderCapabilities | None:
        """Get capabilities for a provider (lazy-loads if needed).

        Args:
            key: Provider identifier.

        Returns:
            ProviderCapabilities or None.
        """
        provider = self.get_provider(key)
        return provider.get_capabilities() if provider else None

    def get_all_capabilities(self) -> dict[str, ProviderCapabilities]:
        """Return capabilities for all enabled providers.

        Lazy-loads each provider module as needed.

        Returns:
            Dict mapping provider key to capabilities.
        """
        result: dict[str, ProviderCapabilities] = {}
        for key in self._enabled:
            provider = self.get_provider(key)
            if provider:
                result[key] = provider.get_capabilities()
        return result

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def enable_provider(self, key: str) -> None:
        """Enable a provider.

        Args:
            key: Provider key.
        """
        if key in self._providers:
            self._enabled.add(key)

    def disable_provider(self, key: str) -> None:
        """Disable a provider (keeps registration, hides from routing).

        Args:
            key: Provider key.
        """
        self._enabled.discard(key)

    def is_enabled(self, key: str) -> bool:
        """Check whether a provider is enabled.

        Args:
            key: Provider key.

        Returns:
            True if enabled.
        """
        return key in self._enabled

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------

    def get_free_providers(self) -> list[str]:
        """Return enabled providers with zero cost."""
        return [
            k
            for k in self._enabled
            if (p := self.get_provider(k)) and p.get_capabilities().rate_per_minute_usd == 0.0
        ]

    def get_cloud_providers(self) -> list[str]:
        """Return enabled cloud providers."""
        return [
            k
            for k in self._enabled
            if (p := self.get_provider(k)) and p.get_capabilities().provider_type == "cloud"
        ]

    def get_local_providers(self) -> list[str]:
        """Return enabled local/on-device providers."""
        return [
            k
            for k in self._enabled
            if (p := self.get_provider(k)) and p.get_capabilities().provider_type == "local"
        ]

    def estimate_cost(self, key: str, duration_seconds: float) -> float:
        """Estimate cost for a provider and audio duration.

        Args:
            key: Provider key.
            duration_seconds: Audio duration.

        Returns:
            Estimated cost in USD.
        """
        provider = self.get_provider(key)
        if provider:
            return provider.estimate_cost(duration_seconds)
        return 0.0

    def recommend_provider(
        self,
        duration_seconds: float,
        prefer_free: bool = True,
        prefer_local: bool = True,
    ) -> str:
        """Recommend the best provider based on preferences.

        Args:
            duration_seconds: Audio length.
            prefer_free: Prefer free providers.
            prefer_local: Prefer on-device providers.

        Returns:
            Provider key of the recommended provider.
        """
        if prefer_local:
            local = self.get_local_providers()
            if local:
                return local[0]

        if prefer_free:
            free = self.get_free_providers()
            if free:
                return free[0]

        # Pick cheapest cloud
        best_key = "local_whisper"
        best_cost = float("inf")
        for key in self._enabled:
            cost = self.estimate_cost(key, duration_seconds)
            if cost < best_cost:
                best_cost = cost
                best_key = key

        return best_key
