"""Registry management — issue, renew, revoke, and query keys.

This is the core business-logic layer for the admin utility,
managing the ``tokens.json`` file that stores all registration
records.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import (
    AUDIT_LOG_FILE,
    DEFAULT_PRODUCT_ID,
    MAX_AUDIT_ENTRIES,
    PUBLIC_MANIFEST_FILE,
    REVOKED_KEYS_FILE,
    TOKENS_FILE,
    KeySource,
    KeyType,
    RegistryEntry,
)
from .crypto import (
    generate_registration_key,
    load_private_key,
    sha256_hex,
    sign_license,
)

# ---------------------------------------------------------------------------
# Low-level I/O helpers
# ---------------------------------------------------------------------------


def _ensure_parent(path: Path) -> None:
    """Create parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)


def load_registry() -> list[RegistryEntry]:
    """Load all entries from ``tokens.json``."""
    if not TOKENS_FILE.exists():
        return []
    data = json.loads(TOKENS_FILE.read_text("utf-8"))
    return [RegistryEntry.from_dict(e) for e in data]


def save_registry(entries: list[RegistryEntry]) -> None:
    """Persist the registry to ``tokens.json``."""
    _ensure_parent(TOKENS_FILE)
    TOKENS_FILE.write_text(
        json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_revoked_hashes() -> set[str]:
    """Load token hashes from the revocation list."""
    if not REVOKED_KEYS_FILE.exists():
        return set()
    data = json.loads(REVOKED_KEYS_FILE.read_text("utf-8"))
    return {r["hash"] for r in data}


def _save_revoked(entries: list[dict]) -> None:
    _ensure_parent(REVOKED_KEYS_FILE)
    REVOKED_KEYS_FILE.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_revoked_raw() -> list[dict]:
    if not REVOKED_KEYS_FILE.exists():
        return []
    return json.loads(REVOKED_KEYS_FILE.read_text("utf-8"))


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def log_audit(
    action: str,
    email: str,
    product_id: str = DEFAULT_PRODUCT_ID,
    details: dict | None = None,
) -> None:
    """Append an entry to the security audit log.

    Args:
        action: Short action code (e.g. ``KEY_ISSUED``).
        email: The relevant email address.
        product_id: The product.
        details: Optional extra context.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "email": email,
        "product_id": product_id,
        "details": details or {},
    }
    log: list[dict] = []
    if AUDIT_LOG_FILE.exists():
        log = json.loads(AUDIT_LOG_FILE.read_text("utf-8"))
    log.append(entry)
    if len(log) > MAX_AUDIT_ENTRIES:
        log = log[-MAX_AUDIT_ENTRIES:]
    _ensure_parent(AUDIT_LOG_FILE)
    AUDIT_LOG_FILE.write_text(
        json.dumps(log, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_audit_log(limit: int = 50) -> list[dict]:
    """Return the most recent *limit* audit entries."""
    if not AUDIT_LOG_FILE.exists():
        return []
    log = json.loads(AUDIT_LOG_FILE.read_text("utf-8"))
    return log[-limit:]


# ---------------------------------------------------------------------------
# Issue / renew / upgrade
# ---------------------------------------------------------------------------


def _compute_expiry(
    key_type: KeyType,
    duration_days: int | None = None,
) -> tuple[str | None, int | None]:
    """Return ``(expiry_iso, duration_days)`` for a given key type."""
    if key_type in (KeyType.LIFETIME, KeyType.CONTRIBUTOR):
        return None, None
    days = duration_days or key_type.default_duration_days or 365
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    return expiry, days


def issue_key(
    email: str,
    private_key_b64: str,
    *,
    product_id: str = DEFAULT_PRODUCT_ID,
    key_type: KeyType = KeyType.ANNUAL,
    source: KeySource = KeySource.ADMIN,
    duration_days: int | None = None,
    name: str = "",
    payment_ref: str = "",
    notes: str = "",
) -> tuple[RegistryEntry, bool]:
    """Issue a new registration key or upgrade an existing one.

    If the user already has a key for the given *product_id*, the
    existing entry is upgraded in-place (type, expiry, source are
    overwritten).

    Args:
        email: Licensee email address.
        private_key_b64: Ed25519 private key (base-64, raw bytes).
        product_id: Product ID to issue for.
        key_type: Type of key.
        source: How the key was acquired.
        duration_days: Override duration (for multi-year, custom
            annual periods, etc.).
        name: Optional human name.
        payment_ref: Optional payment/invoice reference.
        notes: Admin notes.

    Returns:
        ``(entry, created)`` — the registry entry and whether it
        was newly created (``False`` means upgraded).
    """
    registry = load_registry()
    expiry, dur = _compute_expiry(key_type, duration_days)
    now_iso = datetime.now().isoformat()
    priv = load_private_key(private_key_b64)

    # Look for existing entry
    for entry in registry:
        if entry.email.lower() == email.lower() and entry.product_id == product_id:
            old_type = entry.key_type
            entry.key_type = key_type.value
            entry.source = source.value
            entry.expiry = expiry
            entry.duration_days = dur
            entry.updated_at = now_iso
            entry.status = "active"
            entry.signed_license = sign_license(priv, email, product_id, key_type.value, expiry)
            if name:
                entry.name = name
            if payment_ref:
                entry.payment_ref = payment_ref
            if notes:
                entry.notes = notes
            save_registry(registry)
            log_audit(
                "KEY_UPGRADED",
                email,
                product_id,
                {"from": old_type, "to": key_type.value, "source": source.value},
            )
            return entry, False

    # New entry
    raw_key = generate_registration_key(product_id)
    entry = RegistryEntry(
        email=email,
        key=raw_key,
        token_hash=sha256_hex(raw_key),
        product_id=product_id,
        key_type=key_type.value,
        source=source.value,
        expiry=expiry,
        status="active",
        devices=[],
        signed_license=sign_license(priv, email, product_id, key_type.value, expiry),
        created_at=now_iso,
        updated_at=now_iso,
        issued_by="bits_admin",
        name=name,
        payment_ref=payment_ref,
        notes=notes,
        duration_days=dur,
    )
    registry.append(entry)
    save_registry(registry)
    log_audit(
        "KEY_ISSUED",
        email,
        product_id,
        {
            "type": key_type.value,
            "source": source.value,
            "payment_ref": payment_ref or None,
        },
    )
    return entry, True


def renew_key(
    email: str,
    private_key_b64: str,
    *,
    product_id: str = DEFAULT_PRODUCT_ID,
    duration_days: int = 365,
    payment_ref: str = "",
) -> RegistryEntry | None:
    """Renew an existing key by extending the expiry.

    Only applicable to annual / multi-year keys. Lifetime and
    contributor keys are returned unchanged.

    Args:
        email: Licensee email.
        private_key_b64: Signing key.
        product_id: Product ID.
        duration_days: New duration from *today*.
        payment_ref: Optional new payment reference.

    Returns:
        The updated entry, or ``None`` if the user has no key.
    """
    registry = load_registry()
    priv = load_private_key(private_key_b64)
    now_iso = datetime.now().isoformat()

    for entry in registry:
        if entry.email.lower() == email.lower() and entry.product_id == product_id:
            if entry.key_type in (KeyType.LIFETIME.value, KeyType.CONTRIBUTOR.value):
                # Already non-expiring
                return entry

            entry.expiry = (datetime.now() + timedelta(days=duration_days)).isoformat()
            entry.duration_days = duration_days
            entry.status = "active"
            entry.updated_at = now_iso
            entry.signed_license = sign_license(
                priv, entry.email, product_id, entry.key_type, entry.expiry
            )
            if payment_ref:
                entry.payment_ref = payment_ref
            save_registry(registry)
            log_audit(
                "KEY_RENEWED",
                email,
                product_id,
                {"duration_days": duration_days, "new_expiry": entry.expiry},
            )
            return entry
    return None


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


def revoke_key(
    email: str,
    product_id: str = DEFAULT_PRODUCT_ID,
    reason: str = "Admin revocation",
) -> bool:
    """Revoke a key, adding it to the blocklist.

    Args:
        email: Licensee email.
        product_id: Product ID.
        reason: Human-readable reason (audited).

    Returns:
        ``True`` if a key was found and revoked.
    """
    registry = load_registry()
    for entry in registry:
        if entry.email.lower() == email.lower() and entry.product_id == product_id:
            entry.status = "revoked"
            save_registry(registry)
            # Add to blocklist
            revoked = _load_revoked_raw()
            revoked.append(
                {
                    "hash": entry.token_hash,
                    "reason": reason,
                    "revoked_at": datetime.now().isoformat(),
                }
            )
            _save_revoked(revoked)
            log_audit(
                "KEY_REVOKED",
                email,
                product_id,
                {"reason": reason, "token_hash": entry.token_hash[:16]},
            )
            return True
    return False


# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------


def reset_devices(
    email: str,
    product_id: str = DEFAULT_PRODUCT_ID,
) -> int:
    """Clear all registered devices for a user.

    Args:
        email: Licensee email.
        product_id: Product ID.

    Returns:
        Number of devices cleared, or -1 if user not found.
    """
    registry = load_registry()
    for entry in registry:
        if entry.email.lower() == email.lower() and entry.product_id == product_id:
            count = len(entry.devices)
            entry.devices = []
            save_registry(registry)
            log_audit(
                "DEVICES_RESET",
                email,
                product_id,
                {"cleared": count},
            )
            return count
    return -1


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def find_entry(
    email: str,
    product_id: str = DEFAULT_PRODUCT_ID,
) -> RegistryEntry | None:
    """Look up a single registry entry by email + product."""
    for entry in load_registry():
        if entry.email.lower() == email.lower() and entry.product_id == product_id:
            return entry
    return None


def list_entries(
    *,
    product_id: str | None = None,
    source: str | None = None,
    status: str | None = None,
    key_type: str | None = None,
    expired_only: bool = False,
) -> list[RegistryEntry]:
    """Return filtered registry entries.

    All filters are optional; when omitted, all entries are returned.

    Args:
        product_id: Filter by product.
        source: Filter by key source.
        status: Filter by status (``active``, ``revoked``, ``expired``).
        key_type: Filter by key type.
        expired_only: If ``True``, only return expired entries.

    Returns:
        List of matching :class:`RegistryEntry` objects.
    """
    now_iso = datetime.now().isoformat()
    results: list[RegistryEntry] = []
    for entry in load_registry():
        if product_id and entry.product_id != product_id:
            continue
        if source and entry.source != source:
            continue
        if status and entry.status != status:
            continue
        if key_type and entry.key_type != key_type:
            continue
        if expired_only and (not entry.expiry or entry.expiry > now_iso):
            continue
        results.append(entry)
    return results


def clean_expired() -> int:
    """Mark expired entries as ``expired``.

    Returns:
        Count of entries that transitioned to expired.
    """
    registry = load_registry()
    now_iso = datetime.now().isoformat()
    count = 0
    for entry in registry:
        if entry.status == "active" and entry.expiry and entry.expiry < now_iso:
            entry.status = "expired"
            count += 1
            log_audit("KEY_EXPIRED", entry.email, entry.product_id)
    if count:
        save_registry(registry)
    return count


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def get_stats(product_id: str | None = None) -> dict:
    """Return summary statistics for the registry.

    Args:
        product_id: Optional product filter.

    Returns:
        Dict with ``total``, ``active``, ``expired``, ``revoked``,
        ``by_type``, ``by_source``, ``by_product`` breakdowns.
    """
    entries = list_entries(product_id=product_id)
    stats: dict = {
        "total": len(entries),
        "active": 0,
        "expired": 0,
        "revoked": 0,
        "by_type": {},
        "by_source": {},
        "by_product": {},
    }
    for e in entries:
        stats[e.status] = stats.get(e.status, 0) + 1
        stats["by_type"][e.key_type] = stats["by_type"].get(e.key_type, 0) + 1
        stats["by_source"][e.source] = stats["by_source"].get(e.source, 0) + 1
        stats["by_product"][e.product_id] = stats["by_product"].get(e.product_id, 0) + 1
    return stats


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


def generate_manifest() -> int:
    """Regenerate ``public_manifest.json`` from the registry.

    Mirrors the logic of ``manifest_generator.py`` in the
    BITS_Registration backend.

    Returns:
        Number of keys included in the manifest.
    """
    entries = load_registry()
    revoked = load_revoked_hashes()
    now_iso = datetime.now().isoformat()

    manifest: dict = {
        "_meta": {
            "generated_at": now_iso,
            "version": 2,
        },
        "_revoked": sorted(revoked),
    }

    count = 0
    for entry in entries:
        if entry.token_hash in revoked:
            continue
        if entry.status != "active":
            continue
        if entry.expiry and entry.expiry < now_iso:
            continue

        pid = entry.product_id
        if pid not in manifest:
            manifest[pid] = {}

        manifest[pid][entry.token_hash] = {
            "s": entry.signed_license,
            "d": entry.devices,
            "u": entry.updated_at[:10] if entry.updated_at else "",
        }
        count += 1

    _ensure_parent(PUBLIC_MANIFEST_FILE)
    PUBLIC_MANIFEST_FILE.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return count


# ---------------------------------------------------------------------------
# Export / backup
# ---------------------------------------------------------------------------


def export_registry(
    output_path: Path,
    *,
    product_id: str | None = None,
    redact_keys: bool = True,
) -> int:
    """Export the registry to a JSON file.

    Args:
        output_path: Destination file.
        product_id: Optional product filter.
        redact_keys: If ``True`` (default), raw keys are replaced
            with ``"[REDACTED]"``.

    Returns:
        Count of exported entries.
    """
    entries = list_entries(product_id=product_id)
    data = [e.to_dict() for e in entries]
    if redact_keys:
        for d in data:
            d["key"] = "[REDACTED]"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(data)
