"""BITS member email verification via one-time passcode (OTP).

Allows users with a ``@bitsusers.org`` email address to claim a free
lifetime licence by verifying email ownership.

Flow:

1. User enters a ``@bitsusers.org`` email in the welcome dialog.
2. App generates a 6-digit OTP and sends it to a backend
   verification endpoint for email delivery.
3. Backend verifies the email domain and sends the OTP to the user.
4. User enters the OTP in the app.
5. App validates the OTP and stores a member verification hash
   in the OS credential store, bypassing the activation gate.

The daily ``groupsio_sync.py`` script issues formal Ed25519-signed
lifetime keys for all BITS members.  The OTP verification acts as
an immediate unlock so the user does not have to wait for the next
sync cycle.

Security:

- OTPs are 6 random digits (1 000 000 combinations).
- OTPs expire after 10 minutes.
- OTP hashes use HMAC-SHA256 with email-bound key material.
- Stored member hash uses SHA-256 of the normalised email.
- The backend relay URL is configurable via ``feature_flags.json``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bits_whisperer.storage.key_store import KeyStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MEMBER_DOMAIN = "bitsusers.org"
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 600  # 10 minutes
_KEYSTORE_KEY = "member_email_hash"
_HMAC_KEY_MATERIAL = "BITS_MEMBER_VERIFY_2026"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class _PendingVerification:
    """In-memory state for a pending OTP verification."""

    email: str
    otp_hash: str
    created_at: float

    @property
    def is_expired(self) -> bool:
        """Return ``True`` if the OTP has expired."""
        return (time.time() - self.created_at) > OTP_EXPIRY_SECONDS


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class MemberVerificationService:
    """Verify BITS membership via email OTP.

    Args:
        key_store: OS credential store for persisting the member
            verification hash.
        verification_url: Optional backend URL for OTP email relay.
            When empty, the OTP is logged but not emailed (suitable
            for local testing or admin-assisted verification).
    """

    def __init__(
        self,
        key_store: KeyStore,
        verification_url: str = "",
    ) -> None:
        self._key_store = key_store
        self._verification_url = verification_url
        self._pending: _PendingVerification | None = None

    # ------------------------------------------------------------------ #
    # Email domain check                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_member_email(email: str) -> bool:
        """Return ``True`` if *email* belongs to the BITS member domain.

        Args:
            email: The email address to check.
        """
        email = email.strip().lower()
        if "@" not in email:
            return False
        return email.rsplit("@", 1)[1] == MEMBER_DOMAIN

    # ------------------------------------------------------------------ #
    # Verification status                                                  #
    # ------------------------------------------------------------------ #

    def is_already_verified(self) -> bool:
        """Return ``True`` if a member email is already verified."""
        return self._key_store.has_key(_KEYSTORE_KEY)

    def get_verified_email(self) -> str:
        """Return the verified member email, or empty string."""
        return self._key_store.get_key("registration_email") or ""

    # ------------------------------------------------------------------ #
    # OTP generation                                                       #
    # ------------------------------------------------------------------ #

    def request_verification(self, email: str) -> str:
        """Generate an OTP and prepare a verification request.

        The caller should relay the returned OTP to the backend
        for email delivery via :meth:`send_otp_to_backend`.

        Args:
            email: A ``@bitsusers.org`` email address.

        Returns:
            The plaintext 6-digit OTP.

        Raises:
            ValueError: If *email* is not a ``@bitsusers.org`` address.
        """
        if not self.is_member_email(email):
            msg = f"Email must end with @{MEMBER_DOMAIN}"
            raise ValueError(msg)

        otp = "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))
        otp_hash = self._hash_otp(email, otp)

        self._pending = _PendingVerification(
            email=email.strip().lower(),
            otp_hash=otp_hash,
            created_at=time.time(),
        )

        logger.info(
            "Member verification OTP generated for %s***",
            email[:3],
        )
        return otp

    # ------------------------------------------------------------------ #
    # OTP validation                                                       #
    # ------------------------------------------------------------------ #

    def verify_otp(self, email: str, otp: str) -> bool:
        """Validate the OTP entered by the user.

        On success, stores the member verification hash in the
        OS credential store and clears the pending request.

        Args:
            email: The email used in :meth:`request_verification`.
            otp: The 6-digit code entered by the user.

        Returns:
            ``True`` if the OTP is valid and the member is now
            verified.
        """
        if self._pending is None:
            logger.warning("OTP verification attempted with no pending request")
            return False

        if self._pending.is_expired:
            logger.warning("OTP expired for %s***", email[:3])
            self._pending = None
            return False

        normalised_email = email.strip().lower()
        if self._pending.email != normalised_email:
            logger.warning("OTP email mismatch")
            return False

        entered_hash = self._hash_otp(email, otp.strip())

        if hmac.compare_digest(self._pending.otp_hash, entered_hash):
            # Store verification in keystore
            email_hash = hashlib.sha256(normalised_email.encode()).hexdigest()
            self._key_store.store_key(_KEYSTORE_KEY, email_hash)
            self._key_store.store_key("registration_email", normalised_email)
            self._pending = None
            logger.info("BITS member verified: %s***", email[:3])
            return True

        logger.warning("Invalid OTP for %s***", email[:3])
        return False

    # ------------------------------------------------------------------ #
    # Backend relay                                                        #
    # ------------------------------------------------------------------ #

    def send_otp_to_backend(self, email: str, otp: str) -> bool:
        """Send the OTP to the backend for email delivery.

        The backend (a GitHub Actions workflow) sends the OTP to
        the user's email address.  If no ``verification_url`` is
        configured, the request is logged for admin-assisted
        verification.

        Args:
            email: The ``@bitsusers.org`` email address.
            otp: The plaintext OTP to deliver.

        Returns:
            ``True`` if the request was sent (or logged)
            successfully.
        """
        if not self._verification_url:
            logger.info(
                "No verification URL configured. Admin must relay OTP to %s manually.",
                email,
            )
            return True

        try:
            import httpx

            resp = httpx.post(
                self._verification_url,
                json={
                    "event_type": "verify-member",
                    "client_payload": {
                        "email": email,
                        "otp": otp,
                    },
                },
                timeout=15.0,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            logger.info("OTP relay request sent for %s***", email[:3])
            return True
        except Exception as exc:
            logger.error("Failed to send OTP relay request: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Revocation                                                           #
    # ------------------------------------------------------------------ #

    def revoke_member_verification(self) -> None:
        """Clear the stored member verification."""
        self._key_store.delete_key(_KEYSTORE_KEY)
        logger.info("Member verification revoked")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _hash_otp(email: str, otp: str) -> str:
        """HMAC-SHA256 the OTP with email-bound key material."""
        key = f"{_HMAC_KEY_MATERIAL}|{email.strip().lower()}"
        return hmac.new(
            key.encode(),
            otp.strip().encode(),
            hashlib.sha256,
        ).hexdigest()
