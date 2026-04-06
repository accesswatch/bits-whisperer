"""BITS Central Registration & License Key Management.

Security Features:
- Ed25519 cryptographic signatures (``cryptography`` library)
- Timestamp in signed payload (anti-replay)
- Key rotation support via ``BITS_PRIVATE_KEY_BASE64`` env var
- Audit logging for all state-changing operations

Key Types:
    annual       Paid annual subscription (365 days)
    lifetime     BITS member or paid lifetime licence (never expires)
    contributor  Donation / OSS contributor (never expires)
    tester       Alpha / beta tester (never expires)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution – all data files live in the *repository root*,
# i.e. the parent of ``backend_scripts/``.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent

REGISTRY_FILE = REPO_ROOT / "tokens.json"
AUDIT_LOG_FILE = REPO_ROOT / "audit_log.json"
REVOCATION_FILE = REPO_ROOT / "revoked_keys.json"
PUBLIC_MANIFEST_FILE = REPO_ROOT / "public_manifest.json"

# ---------------------------------------------------------------------------
# Valid key types – keep in sync with registration_service.py status codes.
#   annual      → status "A" (Active)
#   lifetime    → status "L" (Lifetime Member)
#   contributor → status "C" (Contributor)
#   tester      → status "T" (Alpha / Beta Tester)
# ---------------------------------------------------------------------------
VALID_KEY_TYPES: tuple[str, ...] = ("annual", "lifetime", "contributor", "tester")

# Maximum number of audit log entries to retain
_MAX_AUDIT_ENTRIES = 10_000


# ---------------------------------------------------------------------------
# Cryptographic helpers
# ---------------------------------------------------------------------------


def get_private_key() -> ed25519.Ed25519PrivateKey:
    """Load the Ed25519 private key from ``BITS_PRIVATE_KEY_BASE64``.

    Falls back to generating a temporary key when the env var is unset
    (convenient for local testing but **not** for production).
    """
    key_b64 = os.getenv("BITS_PRIVATE_KEY_BASE64")
    if not key_b64:
        logger.warning("BITS_PRIVATE_KEY_BASE64 not set – using ephemeral key (dev only).")
        return ed25519.Ed25519PrivateKey.generate()
    return ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_b64))


def sign_license_data(
    email: str,
    product_id: str,
    key_type: str,
    expiry: str | None,
    name: str = "",
) -> str:
    """Create a signed cryptographic blob with anti-replay timestamp.

    The blob format (base64-encoded) is ``<JSON payload><64-byte Ed25519 sig>``.
    The client-side ``registration_service.py`` splits the blob at ``[-64:]``
    to separate payload from signature.

    The ``n`` field carries the registered user's display name so the
    client can greet the user by name after successful verification
    without a separate lookup.

    Returns:
        Base64-encoded signed blob.
    """
    priv_key = get_private_key()
    payload = {
        "e": email,
        "n": name,
        "p": product_id,
        "t": key_type,
        "x": expiry if expiry else "0",
        "i": datetime.now().isoformat(),
        "v": 3,
    }
    data = json.dumps(payload, sort_keys=True).encode()
    signature = priv_key.sign(data)
    return base64.b64encode(data + signature).decode()


def get_hash(key: str) -> str:
    """SHA-256 hash a registration key."""
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def log_audit_event(
    action: str,
    email: str,
    product_id: str,
    details: dict | None = None,
) -> None:
    """Append an entry to the JSON audit log.

    The log is capped at ``_MAX_AUDIT_ENTRIES`` entries (FIFO).
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "email": email,
        "product_id": product_id,
        "details": details or {},
    }
    audit_log: list[dict] = []
    if AUDIT_LOG_FILE.exists():
        with open(AUDIT_LOG_FILE, encoding="utf-8") as f:
            audit_log = json.load(f)

    audit_log.append(entry)
    if len(audit_log) > _MAX_AUDIT_ENTRIES:
        audit_log = audit_log[-_MAX_AUDIT_ENTRIES:]

    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)


# ---------------------------------------------------------------------------
# Revocation list
# ---------------------------------------------------------------------------


def add_to_revocation_list(token_hash: str, reason: str) -> None:
    """Add a key hash to the revocation blocklist."""
    revoked: list[dict] = []
    if REVOCATION_FILE.exists():
        with open(REVOCATION_FILE, encoding="utf-8") as f:
            revoked = json.load(f)

    revoked.append(
        {
            "hash": token_hash,
            "reason": reason,
            "revoked_at": datetime.now().isoformat(),
        }
    )
    with open(REVOCATION_FILE, "w", encoding="utf-8") as f:
        json.dump(revoked, f, indent=2)


def is_revoked(token_hash: str) -> bool:
    """Return ``True`` if *token_hash* appears on the revocation list."""
    if not REVOCATION_FILE.exists():
        return False
    with open(REVOCATION_FILE, encoding="utf-8") as f:
        revoked = json.load(f)
    return any(r["hash"] == token_hash for r in revoked)


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------


def load_registry() -> list[dict]:
    """Load the token registry from disk."""
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_registry(registry: list[dict]) -> None:
    """Write the token registry to disk."""
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def lookup_key(
    *,
    email: str | None = None,
    key_value: str | None = None,
    key_hash: str | None = None,
    product_id: str | None = None,
) -> list[dict]:
    """Find registry entries matching the given criteria.

    At least one of *email*, *key_value*, or *key_hash* must be provided.

    Returns:
        A list of matching registry entries.
    """
    registry = load_registry()
    results: list[dict] = []
    for entry in registry:
        if email and entry.get("email") != email:
            continue
        if key_value and entry.get("key") != key_value:
            continue
        if key_hash and entry.get("token_hash") != key_hash:
            continue
        if product_id and entry.get("product_id") != product_id:
            continue
        results.append(entry)
    return results


def issue_key(
    email: str,
    product_id: str = "bits_whisperer",
    key_type: str = "annual",
    duration_days: int = 365,
    name: str = "",
) -> tuple[str, bool]:
    """Issue or upgrade a licence key for *email*.

    Args:
        email: User's email address.
        product_id: Product identifier (default ``bits_whisperer``).
        key_type: One of :data:`VALID_KEY_TYPES`.
        duration_days: Validity period for ``annual`` keys (ignored for
            lifetime / contributor / tester).
        name: Display name of the licence holder.  Embedded in the
            signed payload so the client can greet the user by name.

    Returns:
        ``(key_string, created)`` where *created* is ``True`` if a new
        key was generated, ``False`` if an existing key was upgraded.

    Raises:
        ValueError: If *key_type* is not in :data:`VALID_KEY_TYPES`.
    """
    if key_type not in VALID_KEY_TYPES:
        msg = f"Invalid key type {key_type!r}. Must be one of {VALID_KEY_TYPES}"
        raise ValueError(msg)

    registry = load_registry()

    expiry: str | None = None
    if key_type == "annual":
        expiry = (datetime.now() + timedelta(days=duration_days)).isoformat()

    # Check for existing key for this email + product
    for entry in registry:
        if entry["email"] == email and entry["product_id"] == product_id:
            old_type = entry["type"]
            entry["type"] = key_type
            entry["name"] = name or entry.get("name", "")
            entry["expiry"] = expiry
            entry["signed_license"] = sign_license_data(
                email,
                product_id,
                key_type,
                expiry,
                name=name or entry.get("name", ""),
            )
            entry["updated_at"] = datetime.now().isoformat()
            save_registry(registry)
            log_audit_event(
                "KEY_UPGRADED",
                email,
                product_id,
                {"from": old_type, "to": key_type, "name": name},
            )
            return entry["key"], False

    # Generate new key: format = product-uuid-checksum
    key_id = str(uuid.uuid4())
    checksum = hashlib.sha256(f"{product_id}-{key_id}".encode()).hexdigest()[:4]
    new_key = f"{product_id}-{key_id}-{checksum}"

    entry = {
        "key": new_key,
        "token_hash": get_hash(new_key),
        "name": name,
        "email": email,
        "product_id": product_id,
        "type": key_type,
        "expiry": expiry,
        "status": "active",
        "devices": [],
        "signed_license": sign_license_data(
            email,
            product_id,
            key_type,
            expiry,
            name=name,
        ),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    registry.append(entry)
    save_registry(registry)
    log_audit_event("KEY_ISSUED", email, product_id, {"type": key_type, "name": name})
    return new_key, True


def clean_expired_tokens() -> int:
    """Mark expired annual keys as ``expired``.

    Returns:
        Number of keys that were expired.
    """
    registry = load_registry()
    now = datetime.now().isoformat()
    count = 0
    for entry in registry:
        if entry.get("expiry") and entry["expiry"] < now and entry["status"] == "active":
            entry["status"] = "expired"
            count += 1
    if count:
        save_registry(registry)
    return count


def get_statistics() -> dict:
    """Return summary statistics about the registry.

    Returns:
        Dict with counts by type, status, total, and device count.
    """
    registry = load_registry()
    stats: dict = {
        "total": len(registry),
        "by_type": {},
        "by_status": {},
        "devices_registered": 0,
    }
    for entry in registry:
        kt = entry.get("type", "unknown")
        stats["by_type"][kt] = stats["by_type"].get(kt, 0) + 1
        st = entry.get("status", "unknown")
        stats["by_status"][st] = stats["by_status"].get(st, 0) + 1
        stats["devices_registered"] += len(entry.get("devices", []))
    return stats
