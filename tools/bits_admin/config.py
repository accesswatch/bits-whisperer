"""Configuration, constants, and path management for BITS Admin.

Centralises all file paths, product IDs, key-type definitions,
and source classifications used by the admin utility.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


# ---------------------------------------------------------------------------
# Working directory — defaults to cwd, overridable with BITS_ADMIN_DIR
# ---------------------------------------------------------------------------
def get_data_dir() -> Path:
    """Return the data directory for registry files.

    Uses ``BITS_ADMIN_DIR`` environment variable if set, otherwise
    the ``data/`` sub-folder of the current working directory.
    """
    env = os.environ.get("BITS_ADMIN_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "data"


# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
DATA_DIR = get_data_dir()
TOKENS_FILE = DATA_DIR / "tokens.json"
PUBLIC_MANIFEST_FILE = DATA_DIR / "public_manifest.json"
REVOKED_KEYS_FILE = DATA_DIR / "revoked_keys.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
BETA_INVITATIONS_FILE = Path.cwd() / "beta_invitations.json"

MAX_AUDIT_ENTRIES = 10_000
MAX_DEVICES = 3


# ---------------------------------------------------------------------------
# Key type definitions
# ---------------------------------------------------------------------------
class KeyType(StrEnum):
    """Registration key type, maps to status codes in the app."""

    LIFETIME = "lifetime"
    ANNUAL = "annual"
    MULTI_YEAR = "multi_year"
    CONTRIBUTOR = "contributor"

    @property
    def status_code(self) -> str:
        """Return the single-char status code stored in manifests.

        ``L`` = Lifetime, ``A`` = Active (annual/multi-year),
        ``C`` = Contributing (paid contributor).
        """
        return {
            KeyType.LIFETIME: "L",
            KeyType.ANNUAL: "A",
            KeyType.MULTI_YEAR: "A",
            KeyType.CONTRIBUTOR: "C",
        }[self]

    @property
    def default_duration_days(self) -> int | None:
        """Default duration in days, or ``None`` for non-expiring."""
        return {
            KeyType.LIFETIME: None,
            KeyType.ANNUAL: 365,
            KeyType.MULTI_YEAR: 730,  # 2 years default; overridden by CLI
            KeyType.CONTRIBUTOR: None,
        }[self]


# ---------------------------------------------------------------------------
# Source classification — how the key was acquired
# ---------------------------------------------------------------------------
class KeySource(StrEnum):
    """How the user obtained their registration key."""

    MEMBER = "member"  # Free — BITS Groups.io member
    PAID = "paid"  # Non-member purchased on website
    CONTRIBUTOR = "contributor"  # Paid contributor/donor
    ADMIN = "admin"  # Manually issued by an administrator
    GROUPSIO_SYNC = "groupsio_sync"  # Issued automatically by sync
    BETA = "beta"  # Beta tester promotional key
    PROMOTIONAL = "promotional"  # Giveaway / conference / review


# ---------------------------------------------------------------------------
# Product IDs
# ---------------------------------------------------------------------------
DEFAULT_PRODUCT_ID = "bits_whisperer"

KNOWN_PRODUCTS: list[str] = [
    "bits_whisperer",
    "bits_braille",
    "bits_notetaker",
]


# ---------------------------------------------------------------------------
# Data model for a single registry entry
# ---------------------------------------------------------------------------
@dataclass
class RegistryEntry:
    """A single registration key record.

    This mirrors the ``tokens.json`` schema produced by the
    BITS_Registration backend scripts, extended with additional
    fields for source tracking, payment references, and notes.
    """

    email: str
    key: str
    token_hash: str
    product_id: str = DEFAULT_PRODUCT_ID
    key_type: str = KeyType.ANNUAL.value
    source: str = KeySource.ADMIN.value
    expiry: str | None = None
    status: str = "active"
    devices: list[str] = field(default_factory=list)
    signed_license: str = ""
    created_at: str = ""
    updated_at: str = ""
    issued_by: str = "bits_admin"
    # Extended fields
    name: str = ""  # Optional human name
    payment_ref: str = ""  # Stripe / PayPal / invoice reference
    notes: str = ""  # Free-form admin notes
    duration_days: int | None = None  # For multi-year tracking

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict."""
        d: dict = {
            "email": self.email,
            "key": self.key,
            "token_hash": self.token_hash,
            "product_id": self.product_id,
            "type": self.key_type,
            "source": self.source,
            "expiry": self.expiry,
            "status": self.status,
            "devices": self.devices,
            "signed_license": self.signed_license,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "issued_by": self.issued_by,
        }
        # Only include extended fields when non-empty
        if self.name:
            d["name"] = self.name
        if self.payment_ref:
            d["payment_ref"] = self.payment_ref
        if self.notes:
            d["notes"] = self.notes
        if self.duration_days is not None:
            d["duration_days"] = self.duration_days
        return d

    @classmethod
    def from_dict(cls, data: dict) -> RegistryEntry:
        """Deserialise from a ``tokens.json`` entry."""
        return cls(
            email=data.get("email", ""),
            key=data.get("key", ""),
            token_hash=data.get("token_hash", ""),
            product_id=data.get("product_id", DEFAULT_PRODUCT_ID),
            key_type=data.get("type", KeyType.ANNUAL.value),
            source=data.get("source", KeySource.ADMIN.value),
            expiry=data.get("expiry"),
            status=data.get("status", "active"),
            devices=data.get("devices", []),
            signed_license=data.get("signed_license", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            issued_by=data.get("issued_by", "bits_admin"),
            name=data.get("name", ""),
            payment_ref=data.get("payment_ref", ""),
            notes=data.get("notes", ""),
            duration_days=data.get("duration_days"),
        )
