"""Secure API key storage using the OS credential store (keyring)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SERVICE_NAME = "BITS Whisperer"

# Map provider identifiers to human-readable key names
_KEY_NAMES: dict[str, str] = {
    "openai": "OpenAI API Key",
    "google": "Google Cloud Credentials Path",
    "azure": "Azure Speech Key",
    "azure_region": "Azure Speech Region",
    "deepgram": "Deepgram API Key",
    "assemblyai": "AssemblyAI API Key",
    "gemini": "Google Gemini API Key",
    "aws_access_key": "AWS Access Key ID",
    "aws_secret_key": "AWS Secret Access Key",
    "aws_region": "AWS Region",
    "groq": "Groq API Key",
    "rev_ai": "Rev.ai API Key",
    "speechmatics": "Speechmatics API Key",
    "elevenlabs": "ElevenLabs API Key",
    "auphonic": "Auphonic API Token",
    # AI service providers (translation / summarization)
    "anthropic": "Anthropic (Claude) API Key",
    "azure_openai": "Azure OpenAI API Key",
    "azure_openai_endpoint": "Azure OpenAI Endpoint URL",
    "azure_openai_deployment": "Azure OpenAI Deployment Name",
}


class KeyStore:
    """Manage API keys in the operating system's credential vault.

    On Windows this uses Windows Credential Manager via the `keyring`
    library.  API keys are never stored on disk in plaintext.
    """

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401

            self._available = True
        except ImportError:
            logger.warning(
                "keyring package not installed — API keys will NOT be persisted securely."
            )
            self._available = False

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def store_key(self, provider: str, key: str) -> None:
        """Store an API key for *provider* in the OS credential store.

        Args:
            provider: Provider identifier (e.g. ``"openai"``).
            key: The secret value to store.
        """
        if not self._available:
            return
        import keyring

        keyring.set_password(_SERVICE_NAME, _key_id(provider), key)
        logger.debug("Stored key for provider %s", provider)

    def get_key(self, provider: str) -> str | None:
        """Retrieve a stored API key. Returns ``None`` if not found.

        Args:
            provider: Provider identifier.
        """
        if not self._available:
            return None
        import keyring

        return keyring.get_password(_SERVICE_NAME, _key_id(provider))

    def delete_key(self, provider: str) -> bool:
        """Delete an API key. Returns ``True`` if the key was found and deleted.

        Args:
            provider: Provider identifier.
        """
        if not self._available:
            return False
        import keyring

        try:
            keyring.delete_password(_SERVICE_NAME, _key_id(provider))
            logger.debug("Deleted key for provider %s", provider)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    def has_key(self, provider: str) -> bool:
        """Check whether a key is stored for *provider*.

        Args:
            provider: Provider identifier.
        """
        return self.get_key(provider) is not None

    def list_providers_with_keys(self) -> list[str]:
        """Return provider identifiers that have stored keys."""
        return [p for p in _KEY_NAMES if self.has_key(p)]

    @staticmethod
    def get_supported_providers() -> dict[str, str]:
        """Return mapping of provider id to human-readable key name."""
        return dict(_KEY_NAMES)


def _key_id(provider: str) -> str:
    """Canonical key identifier for a provider."""
    return f"api_key_{provider}"
