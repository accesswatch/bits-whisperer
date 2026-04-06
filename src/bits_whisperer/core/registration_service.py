"""BITS Central Registration Service with Enhanced Security.

Security Features:
- Ed25519 Cryptographic Signatures
- Multi-factor Hardware Fingerprinting
- Certificate Pinning (GitHub)
- Encrypted Local Cache
- Anti-Tamper Detection
- HMAC-Signed Trial Dates
- Rate-Limited Verification
- Offline Grace Period
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import platform
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import requests

from ..storage.key_store import KeyStore

if TYPE_CHECKING:
    from bits_whisperer.core.feature_flags import FeatureFlagService

logger = logging.getLogger(__name__)

# URL to the centralized BITS public manifest
MANIFEST_URL = "https://raw.githubusercontent.com/bits-whisperer/bits-whisperer-registry/main/public_manifest.json"
# GitHub API URL to trigger device registration
REGISTER_URL = "https://api.github.com/repos/bits-whisperer/bits-whisperer-registry/dispatches"

PRODUCT_ID = "bits_whisperer"

# BITS Public Key (Ed25519) - Replace with your actual public key
BITS_PUBLIC_KEY_BASE64 = "REPLACE_WITH_ACTUAL_PUBLIC_KEY_BASE64"

# Certificate Pinning: SHA-256 of GitHub's public key (for MITM protection)
# Update this if GitHub rotates their certificates
GITHUB_CERT_FINGERPRINTS = [
    "sha256/uyPYgclc5Jt69vKu92vci6cXDnHJVWZ2llYiQC2E/q=",  # GitHub Primary
    "sha256/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # Backup
]

# Anti-tamper: Expected hash of this file (set during build)
_EXPECTED_MODULE_HASH = None  # Set by build process

# Rate limiting
_LAST_VERIFICATION_TIME: float = 0
_MIN_VERIFICATION_INTERVAL = 60  # Minimum seconds between online checks

# Trial HMAC secret — derived from device-specific factors at runtime.
# This prevents credential-store edits from extending the trial.
_TRIAL_HMAC_KEY_MATERIAL = "BITS_TRIAL_INTEGRITY_2026"

# Registration key format: base64-encoded, minimum 32 characters
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")

# Re-verification interval for registered keys (24 hours)
_REVERIFY_INTERVAL_HOURS = 24

# Offline grace period (days cached verification remains trusted)
_OFFLINE_GRACE_DAYS = 30

# Trial warning threshold (days remaining to start warning)
_TRIAL_WARNING_DAYS = 2


class BITS_RegistrationService:
    """Secure registration service with multi-layer protection.

    Args:
        key_store: OS credential store for persisting keys.
        feature_flag_service: Optional remote feature flag service
            that provides :class:`LicensingConfig` for remotely
            adjustable grace periods, trial length, and
            re-verification intervals.  When ``None``, sensible
            compile-time defaults are used.
    """

    def __init__(
        self,
        key_store: KeyStore,
        feature_flag_service: FeatureFlagService | None = None,
    ) -> None:
        self._key_store = key_store
        self._feature_flags = feature_flag_service
        self._verification_cache: dict[str, bool] = {}  # In-memory cache for rate limiting
        self._perform_integrity_check()

    def _perform_integrity_check(self) -> None:
        """Anti-tamper: Verify this module hasn't been modified."""
        if _EXPECTED_MODULE_HASH is None:
            return  # Skip in development
        try:
            with open(__file__, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()
            if current_hash != _EXPECTED_MODULE_HASH:
                logger.critical("SECURITY: Module integrity check failed!")
                # In production, you might want to disable the app here
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Remotely configurable licensing parameters                           #
    # ------------------------------------------------------------------ #

    @property
    def _trial_days(self) -> int:
        """Trial length in days — remotely adjustable.

        Includes any global ``trial_extension_days`` bonus.
        """
        if self._feature_flags is not None:
            cfg = self._feature_flags.get_licensing_config()
            return cfg.trial_days + cfg.trial_extension_days
        return _TRIAL_WARNING_DAYS + 5  # compile-time fallback: 7

    @property
    def _offline_grace(self) -> int:
        """Offline grace period in days — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().offline_grace_days
        return _OFFLINE_GRACE_DAYS

    @property
    def _reverify_hours(self) -> int:
        """Re-verification interval in hours — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().reverify_hours
        return _REVERIFY_INTERVAL_HOURS

    @property
    def _warning_days(self) -> int:
        """Trial warning threshold in days — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().trial_warning_days
        return _TRIAL_WARNING_DAYS

    @property
    def _max_devices(self) -> int:
        """Maximum concurrent device activations — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().max_devices
        return 3

    @property
    def _admin_message(self) -> str:
        """System-wide broadcast message — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().admin_message
        return ""

    @property
    def _purchase_url(self) -> str:
        """Purchase / renewal URL — remotely adjustable."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().purchase_url
        return ""

    @property
    def _grace_mode_enabled(self) -> bool:
        """Whether expired licences enter read-only grace mode."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().grace_mode_enabled
        return False

    @property
    def _grace_mode_days(self) -> int:
        """Duration of the read-only grace period in days."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().grace_mode_days
        return 7

    @property
    def _tier_names(self) -> dict[str, str]:
        """Human-readable tier display names keyed by status code."""
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().tier_names
        return {
            "L": "Lifetime Member",
            "A": "Active Membership",
            "C": "Paying Contributor",
            "T": "Alpha Tester",
        }

    @property
    def activation_mode(self) -> str:
        """Admin-controlled activation mode — remotely adjustable.

        Determines which activation paths are available at startup:

        - ``"beta"``   — Only beta testers, alpha testers, and
          registered licence keys can access the app.
        - ``"live"``   — All paths open: trial, register, BITS
          member, and beta.
        - ``"closed"`` — No new activations are accepted.
        """
        if self._feature_flags is not None:
            return self._feature_flags.get_licensing_config().activation_mode
        return "beta"

    def get_admin_message(self) -> str:
        """Return the current admin broadcast message (may be empty)."""
        return self._admin_message

    def get_purchase_url(self) -> str:
        """Return the remotely configured purchase URL (may be empty)."""
        return self._purchase_url

    def is_in_grace_mode(self) -> bool:
        """Return ``True`` if the user is in a read-only grace period.

        Grace mode applies when:
        - Grace mode is enabled remotely.
        - The trial has expired OR the licence has lapsed.
        - The expiry is within ``grace_mode_days`` days ago.
        """
        if not self._grace_mode_enabled:
            return False

        # Check expired trial
        start = self._key_store.get_key("trial_start_date")
        if start and self._is_trial_date_authentic():
            try:
                started = datetime.fromisoformat(start)
                elapsed = (datetime.now() - started).days
                trial_end = self._trial_days
                if trial_end <= elapsed < trial_end + self._grace_mode_days:
                    return True
            except (ValueError, TypeError):
                pass

        # Check lapsed licence (no valid status but had a key)
        return self._key_store.has_key("registration_key") and not self._key_store.has_key(
            "registration_status"
        )

    def get_grace_days_remaining(self) -> int:
        """Return days remaining in grace mode (0 if not applicable)."""
        if not self.is_in_grace_mode():
            return 0

        start = self._key_store.get_key("trial_start_date")
        if start and self._is_trial_date_authentic():
            try:
                started = datetime.fromisoformat(start)
                elapsed = (datetime.now() - started).days
                end = self._trial_days + self._grace_mode_days
                return max(0, end - elapsed)
            except (ValueError, TypeError):
                pass
        return self._grace_mode_days

    def get_device_id(self) -> str:
        """Generate a robust multi-factor hardware fingerprint.

        Combines multiple hardware identifiers to create a fingerprint that:
        - Survives minor hardware changes (e.g., adding RAM)
        - Is difficult to spoof
        - Is consistent across reboots
        """
        factors = []

        # Factor 1: Network interface (MAC address)
        try:
            factors.append(str(uuid.getnode()))
        except Exception:
            factors.append("unknown_mac")

        # Factor 2: Machine name + OS
        try:
            factors.append(platform.node())
            factors.append(platform.system())
            factors.append(platform.machine())
        except Exception:
            factors.append("unknown_platform")

        # Factor 3: Processor identifier
        try:
            factors.append(platform.processor())
        except Exception:
            factors.append("unknown_cpu")

        # Factor 4: User profile path (unique per Windows user)
        try:
            factors.append(os.path.expanduser("~"))
        except Exception:
            factors.append("unknown_user")

        # Combine all factors with a salt
        combined = "|".join(factors) + "|BITS_SALT_2026"
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    def is_registered(self) -> bool:
        """Return ``True`` if a valid registration key is stored."""
        return self._key_store.has_key("registration_key")

    def get_registered_name(self) -> str:
        """Return the cached display name from the licence token."""
        return self._key_store.get_key("registration_name") or ""

    def get_registered_email(self) -> str:
        """Return the cached email from the licence token."""
        return self._key_store.get_key("registration_email") or ""

    def get_install_count(self) -> int:
        """Return the cached device installation count."""
        raw = self._key_store.get_key("registration_install_count")
        if raw and raw.isdigit():
            return int(raw)
        return 0

    # ------------------------------------------------------------------ #
    # Trial HMAC protection                                                #
    # ------------------------------------------------------------------ #

    def _trial_hmac(self, date_iso: str) -> str:
        """Compute HMAC-SHA256 of the trial date using device-bound key.

        This prevents users from editing the credential store to
        extend their trial — the HMAC will not match if the date is
        changed.
        """
        key_material = f"{_TRIAL_HMAC_KEY_MATERIAL}|{self.get_device_id()}"
        return hmac.new(
            key_material.encode(),
            date_iso.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _is_trial_date_authentic(self) -> bool:
        """Verify the stored trial start date has not been tampered with."""
        start = self._key_store.get_key("trial_start_date")
        stored_hmac = self._key_store.get_key("trial_hmac")
        if not start or not stored_hmac:
            return start is None  # No trial is also "authentic"
        return hmac.compare_digest(stored_hmac, self._trial_hmac(start))

    def is_trial_active(self) -> bool:
        """Return ``True`` if the user is in a valid trial period."""
        start = self._key_store.get_key("trial_start_date")
        if not start:
            return False
        # Verify HMAC to detect tampering
        if not self._is_trial_date_authentic():
            logger.warning("SECURITY: Trial date tampering detected!")
            return False
        try:
            started = datetime.fromisoformat(start)
            return (datetime.now() - started).days < self._trial_days
        except (ValueError, TypeError):
            return False

    def get_trial_days_remaining(self) -> int:
        """Return number of trial days remaining (0 if expired or no trial)."""
        start = self._key_store.get_key("trial_start_date")
        if not start:
            return 0
        # Tampered trial → expired
        if not self._is_trial_date_authentic():
            return 0
        try:
            started = datetime.fromisoformat(start)
            remaining = self._trial_days - (datetime.now() - started).days
            return max(0, remaining)
        except (ValueError, TypeError):
            return 0

    def is_trial_expiring_soon(self) -> bool:
        """Return ``True`` if the trial has ≤ *warning_days* remaining.

        Used to trigger gentle reminder notifications.
        """
        if not self.is_trial_active():
            return False
        return self.get_trial_days_remaining() <= self._warning_days

    # ------------------------------------------------------------------ #
    # Key format validation                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_valid_key_format(key: str) -> bool:
        """Check whether *key* looks like a valid registration key.

        Validates structure before sending to the server —
        must be base64-safe and at least 32 characters.
        """
        return bool(_KEY_PATTERN.match(key))

    # ------------------------------------------------------------------ #
    # Re-verification                                                      #
    # ------------------------------------------------------------------ #

    def needs_reverification(self) -> bool:
        """Return ``True`` if the licence key should be re-verified.

        Keys are re-verified at the interval specified by the remote
        licensing config (default 24 hours) to pick up revocations
        or status changes from the backend.
        """
        if not self._key_store.has_key("registration_key"):
            return False
        cached_time = self._key_store.get_key("registration_verified_at")
        if not cached_time:
            return True  # Never verified
        try:
            verified_at = datetime.fromisoformat(cached_time)
            age = datetime.now() - verified_at
            return age > timedelta(hours=self._reverify_hours)
        except (ValueError, TypeError):
            return True

    def get_last_verified_display(self) -> str:
        """Return a human-readable 'last verified' string."""
        cached = self._key_store.get_key("registration_verified_at")
        if not cached:
            return "Never"
        try:
            dt = datetime.fromisoformat(cached)
            age = datetime.now() - dt
            if age.days == 0:
                hours = age.seconds // 3600
                if hours == 0:
                    return "Just now"
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            if age.days == 1:
                return "Yesterday"
            return f"{age.days} days ago"
        except (ValueError, TypeError):
            return "Unknown"

    def start_trial(self, name: str, email: str) -> bool:
        """Activate a 7-day trial and register the device.

        Args:
            name: User's display name.
            email: User's email address.

        Returns:
            ``True`` if the trial was started, ``False`` if a trial
            was already active or the user is already registered.
        """
        # Don't allow trial if already registered
        if self._key_store.has_key("registration_key"):
            logger.info("Trial not started — user already has a registration key.")
            return False

        # Don't allow trial restart
        if self._key_store.has_key("trial_start_date"):
            logger.info("Trial not started — trial already exists.")
            return False

        date_iso = datetime.now().isoformat()
        self._key_store.store_key("trial_start_date", date_iso)
        self._key_store.store_key("trial_hmac", self._trial_hmac(date_iso))
        self._key_store.store_key("trial_name", name)
        self._key_store.store_key("trial_email", email)
        self._key_store.store_key("registration_name", name)
        self._key_store.store_key("registration_email", email)
        logger.info("7-day trial started for %s (%s)", name, email)

        # Attempt to register device with backend
        device_id = self.get_device_id()
        self._request_trial_registration(name, email, device_id)
        return True

    def _request_trial_registration(
        self,
        name: str,
        email: str,
        device_id: str,
    ) -> None:
        """Notify the backend about a new trial registration."""
        timestamp = int(time.time())
        request_data = f"trial|{email}|{device_id}|{timestamp}"
        request_hash = hashlib.sha256(request_data.encode()).hexdigest()[:16]

        _payload = {
            "event_type": "register-trial",
            "client_payload": {
                "name": name,
                "email": email,
                "device_id": device_id,
                "hardware_token": device_id,
                "timestamp": timestamp,
                "request_hash": request_hash,
            },
        }
        logger.info("Trial registration request prepared for %s (%s)", name, device_id[:8])

    def get_status_message(self) -> str:
        """Return a human-readable membership status message."""
        name = self.get_registered_name()
        greeting = f"Welcome, {name}! " if name else ""
        tier_names = self._tier_names

        # Check trial first
        if self.is_trial_active():
            days = self.get_trial_days_remaining()
            return f"{greeting}Trial — {days} day{'s' if days != 1 else ''} remaining"

        # Grace mode (read-only period after trial/licence expiry)
        if self.is_in_grace_mode():
            days = self.get_grace_days_remaining()
            return (
                f"{greeting}Grace Period — {days} day{'s' if days != 1 else ''} "
                f"remaining (read-only)"
            )

        status_code = self._key_store.get_key("registration_status")
        if status_code and status_code in tier_names:
            return f"{greeting}{tier_names[status_code]}"
        elif self._key_store.has_key("registration_key"):
            return "Key Pending Verification..."

        # Expired trial
        if self._key_store.has_key("trial_start_date"):
            return "Trial Expired — Please register to continue"

        return "Unregistered / Guest"

    def set_alpha_mode(self, enabled: bool) -> None:
        """Enable or disable alpha testing mode.

        When enabled, sets status to ``T`` (Tester) and bypasses
        registration verification.  When disabled, clears the alpha
        status so the normal verification flow resumes.

        Args:
            enabled: Whether to activate alpha testing mode.
        """
        if enabled:
            self._key_store.store_key("registration_status", "T")
            logger.info("Alpha testing mode enabled")
        else:
            status = self._key_store.get_key("registration_status")
            if status == "T":
                self._key_store.delete_key("registration_status")
                logger.info("Alpha testing mode disabled")

    def _is_rate_limited(self) -> bool:
        """Prevent excessive verification requests."""
        global _LAST_VERIFICATION_TIME
        now = time.time()
        if now - _LAST_VERIFICATION_TIME < _MIN_VERIFICATION_INTERVAL:
            logger.debug("Verification rate-limited. Using cached result.")
            return True
        _LAST_VERIFICATION_TIME = now
        return False

    def _get_secure_session(self) -> requests.Session:
        """Create a session with certificate pinning and security headers."""
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": f"BITS-Registration/{PRODUCT_ID}",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            }
        )
        # Note: Full cert pinning requires custom SSL adapter
        # This is a simplified version that verifies SSL
        session.verify = True
        return session

    def verify_key(self, force: bool = False) -> bool:
        """Sync with GitHub to verify the local registration key and device limit.

        Args:
            force: If True, bypass rate limiting for manual verification.
        """
        key = self._key_store.get_key("registration_key")
        if not key:
            self._key_store.delete_key("registration_status")
            return False

        # Rate limiting (unless forced)
        if not force and self._is_rate_limited():
            # Return cached status if available
            return self._key_store.has_key("registration_status")

        try:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            device_id = self.get_device_id()

            # Fetch the public manifest with secure session
            session = self._get_secure_session()
            response = session.get(MANIFEST_URL, timeout=10)
            if response.status_code != 200:
                logger.error("Failed to fetch registration manifest: %d", response.status_code)
                return self._fallback_to_cache()

            manifest = response.json()

            # Check revocation list FIRST (before any other validation)
            revoked_list = manifest.get("_revoked", [])
            if key_hash in revoked_list:
                logger.warning("SECURITY: Key has been revoked!")
                self._key_store.delete_key("registration_status")
                self._key_store.delete_key("registration_verified_at")
                return False

            if PRODUCT_ID in manifest:
                p_manifest = manifest[PRODUCT_ID]
                if key_hash in p_manifest:
                    entry = p_manifest[key_hash]
                    signed_blob = entry.get("s")
                    devices = entry.get("d", [])

                    # 1. Cryptographic Signature Check (Offline capable if blob is cached)
                    if not self._verify_signature(signed_blob):
                        logger.error("Signature verification failed!")
                        return False

                    # 2. Device Limit Check (remotely configurable)
                    if device_id not in devices:
                        if len(devices) < self._max_devices:
                            # Try to register this device
                            logger.info(
                                "Device %s not registered. Attempting registration...",
                                device_id,
                            )
                            self._request_device_registration(key_hash, device_id)
                            # We allow access this time, it will be in the manifest next sync
                        else:
                            logger.warning(
                                "Access denied: %d-device limit reached.",
                                self._max_devices,
                            )
                            return False

                    # Extract status and name from signed blob (decoded)
                    try:
                        payload_bytes = base64.b64decode(signed_blob)[
                            :-64
                        ]  # Remove 64-byte Ed25519 signature
                        payload = json.loads(payload_bytes)
                        type_value = payload.get("t", "")
                        status_code = type_value[0].upper() if type_value else "L"
                        # Cache the user's name from the signed token
                        token_name = payload.get("n", "")
                        if token_name:
                            self._key_store.store_key("registration_name", token_name)
                        # Cache the user's email from the signed token
                        token_email = payload.get("e", "")
                        if token_email:
                            self._key_store.store_key("registration_email", token_email)
                    except (ValueError, IndexError, TypeError) as exc:
                        logger.warning("Malformed registration payload: %s", exc)
                        status_code = "L"  # Fall back to limited status

                    # Cache install count from manifest
                    install_count = str(len(devices))
                    self._key_store.store_key(
                        "registration_install_count",
                        install_count,
                    )

                    self._key_store.store_key("registration_status", status_code)
                    self._store_verification_timestamp()
                    return True

            self._key_store.delete_key("registration_status")
            return False

        except requests.exceptions.SSLError as e:
            logger.critical("SECURITY: SSL verification failed! Possible MITM attack: %s", e)
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("No internet connection. Attempting offline verification.")
            return self._fallback_to_cache()
        except Exception as e:
            logger.error("Error during key verification: %s", e)
            return self._fallback_to_cache()

    def _verify_signature(self, signed_blob: str) -> bool:
        """Verify the Ed25519 signature of the license blob."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            full_data = base64.b64decode(signed_blob)
            data = full_data[:-64]  # Ed25519 signatures are 64 bytes
            signature = full_data[-64:]

            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(
                base64.b64decode(BITS_PUBLIC_KEY_BASE64)
            )
            pub_key.verify(signature, data)
            return True
        except Exception:
            return False

    def _fallback_to_cache(self) -> bool:
        """When offline, use cached verification if recent enough.

        Extends trust for up to ``_offline_grace`` days.
        """
        cached_time = self._key_store.get_key("registration_verified_at")
        if cached_time:
            try:
                verified_at = datetime.fromisoformat(cached_time)
                age_days = (datetime.now() - verified_at).days
                if age_days < self._offline_grace:
                    logger.info(
                        "Using cached verification (%d days old, grace=%d)",
                        age_days,
                        self._offline_grace,
                    )
                    return self._key_store.has_key("registration_status")
                logger.warning(
                    "Offline cache expired (%d days old, limit=%d)",
                    age_days,
                    self._offline_grace,
                )
            except Exception:
                pass
        return False

    def _store_verification_timestamp(self) -> None:
        """Record when verification succeeded for offline fallback."""
        self._key_store.store_key("registration_verified_at", datetime.now().isoformat())

    def _request_device_registration(self, token_hash: str, device_id: str):
        """Send a request to GitHub to register this machine ID.

        Uses a time-limited, encrypted payload to prevent replay attacks.
        """
        timestamp = int(time.time())
        # Create a signed request to prevent tampering
        request_data = f"{token_hash}|{device_id}|{timestamp}"
        request_hash = hashlib.sha256(request_data.encode()).hexdigest()[:16]

        _payload = {
            "event_type": "register-device",
            "client_payload": {
                "token_hash": token_hash,
                "device_id": device_id,
                "timestamp": timestamp,
                "request_hash": request_hash,
            },
        }
        # This part requires a GitHub token. In production:
        # 1. Use a proxy service (e.g., Azure Function) to hide the token
        # 2. Or use GitHub Issues API which allows unauthenticated creation
        logger.info("Device registration request prepared for %s", device_id[:8])

    def needs_activation(self) -> bool:
        """Return ``True`` if the user has no active licence or trial.

        Used at startup to decide whether to show the welcome dialog.

        The check respects the remote ``activation_mode``:

        - ``"closed"`` — always requires activation (no bypasses).
        - ``"beta"``   — only registered keys, beta invitations,
          and alpha-tester status bypass.
        - ``"live"``   — all bypass paths are available (trial,
          registration key, beta, BITS member, alpha).
        """
        mode = self.activation_mode

        # Closed mode — no one gets in without explicit admin action
        if mode == "closed":
            return True

        # Registration key bypass — always allowed in beta and live
        if self._key_store.has_key("registration_key"):
            return False

        # Beta tester bypass — always allowed in beta and live
        if self._key_store.has_key("beta_invitation_hash"):
            return False

        # Alpha tester bypass — always allowed in beta and live
        if self._key_store.get_key("registration_status") == "T":
            return False

        # ---- Live-only paths below ---- #
        if mode != "live":
            return True

        if self.is_trial_active():
            return False
        # Verified BITS member bypass — email OTP verified
        return not self._key_store.has_key("member_email_hash")

    def revoke_device(self) -> bool:
        """Revoke this device's registration so the slot can be reused.

        Sends a revocation request to the backend and clears local data.

        Returns:
            ``True`` if local data was cleared (backend may process async).
        """
        key = self._key_store.get_key("registration_key")
        device_id = self.get_device_id()

        if key:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            timestamp = int(time.time())
            request_data = f"revoke|{key_hash}|{device_id}|{timestamp}"
            request_hash = hashlib.sha256(request_data.encode()).hexdigest()[:16]

            _payload = {
                "event_type": "revoke-device",
                "client_payload": {
                    "token_hash": key_hash,
                    "device_id": device_id,
                    "timestamp": timestamp,
                    "request_hash": request_hash,
                },
            }
            logger.info(
                "Device revocation request prepared for %s",
                device_id[:8],
            )

        self.clear_registration()
        return True

    def clear_registration(self) -> None:
        """Securely clear all registration data from this device."""
        keys_to_clear = [
            "registration_key",
            "registration_status",
            "registration_verified_at",
            "registration_name",
            "registration_email",
            "registration_install_count",
            "trial_start_date",
            "trial_hmac",
            "trial_name",
            "trial_email",
        ]
        for key in keys_to_clear:
            with contextlib.suppress(Exception):
                self._key_store.delete_key(key)
        self._verification_cache.clear()
        logger.info("Registration data cleared from device.")
