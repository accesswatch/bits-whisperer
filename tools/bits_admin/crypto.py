"""Cryptographic primitives for BITS Admin.

Handles Ed25519 key-pair generation, license signing, SHA-256 hashing,
and registration key formatting.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# ---------------------------------------------------------------------------
# Key-pair management
# ---------------------------------------------------------------------------


def generate_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 key-pair.

    Returns:
        ``(private_base64, public_base64)`` tuple of raw-byte
        base-64 encoded keys.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return (
        base64.b64encode(private_bytes).decode(),
        base64.b64encode(public_bytes).decode(),
    )


def load_private_key(key_base64: str) -> ed25519.Ed25519PrivateKey:
    """Load a private key from its base-64 representation.

    Args:
        key_base64: The raw-byte base-64 encoded private key.

    Returns:
        An Ed25519 private-key object.
    """
    return ed25519.Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(key_base64),
    )


def load_public_key(key_base64: str) -> ed25519.Ed25519PublicKey:
    """Load a public key from its base-64 representation.

    Args:
        key_base64: The raw-byte base-64 encoded public key.

    Returns:
        An Ed25519 public-key object.
    """
    return ed25519.Ed25519PublicKey.from_public_bytes(
        base64.b64decode(key_base64),
    )


# ---------------------------------------------------------------------------
# Signing & verification
# ---------------------------------------------------------------------------


def sign_license(
    private_key: ed25519.Ed25519PrivateKey,
    email: str,
    product_id: str,
    key_type: str,
    expiry: str | None,
) -> str:
    """Create a signed license blob.

    The payload is a compact JSON dict (sorted keys) concatenated
    with the 32-byte Ed25519 signature, then base-64 encoded.

    Args:
        private_key: The signing key.
        email: Licensee email.
        product_id: Product identifier (e.g. ``bits_whisperer``).
        key_type: One of ``lifetime``, ``annual``, ``multi_year``,
            ``contributor``.
        expiry: ISO-8601 expiry timestamp, or ``None`` for
            non-expiring.

    Returns:
        A base-64 encoded ``payload + signature`` string.
    """
    payload = {
        "e": email,
        "p": product_id,
        "t": key_type,
        "x": expiry if expiry else "0",
        "i": datetime.now().isoformat(),
        "v": 2,
    }
    data = json.dumps(payload, sort_keys=True).encode()
    signature = private_key.sign(data)
    return base64.b64encode(data + signature).decode()


def verify_signature(
    public_key: ed25519.Ed25519PublicKey,
    signed_blob: str,
) -> bool:
    """Verify an Ed25519-signed license blob.

    Args:
        public_key: The verification key.
        signed_blob: Base-64 encoded ``payload + signature``.

    Returns:
        ``True`` if the signature is valid.
    """
    try:
        full = base64.b64decode(signed_blob)
        data, sig = full[:-64], full[-64:]
        public_key.verify(sig, data)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def sha256_hex(value: str) -> str:
    """Return the SHA-256 hex digest of a plain string.

    Args:
        value: The value to hash.

    Returns:
        64-character lower-case hex digest.
    """
    return hashlib.sha256(value.encode()).hexdigest()


def sha256_normalised(value: str) -> str:
    """SHA-256 hash after stripping whitespace and upper-casing.

    Used for beta invitation codes.

    Args:
        value: The invitation code.

    Returns:
        64-character lower-case hex digest.
    """
    return hashlib.sha256(value.strip().upper().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Registration key generation
# ---------------------------------------------------------------------------


def generate_registration_key(product_id: str) -> str:
    """Generate a new registration key string.

    Format: ``<product_id>-<uuid>-<4-char checksum>``

    The 4-character checksum catches transcription typos.

    Args:
        product_id: The product identifier to embed in the key.

    Returns:
        The formatted registration key.
    """
    key_id = str(uuid.uuid4())
    checksum = sha256_hex(f"{product_id}-{key_id}")[:4]
    return f"{product_id}-{key_id}-{checksum}"
