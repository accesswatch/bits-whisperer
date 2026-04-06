"""Generate the public manifest from the token registry.

The manifest is a JSON file published via ``raw.githubusercontent.com``
that the BITS Whisperer app fetches to verify registration keys.

Manifest structure::

    {
        "_meta": {"generated_at": "...", "version": 2},
        "_revoked": ["hash1", "hash2", ...],
        "bits_whisperer": {
            "<token_hash>": {
                "s": "<signed_blob>",
                "d": ["device1", "device2"],
                "u": "2025-01-15"
            },
            ...
        }
    }
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure sibling imports work regardless of CWD
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from registry_manager import (  # noqa: E402
    PUBLIC_MANIFEST_FILE,
    REGISTRY_FILE,
    REVOCATION_FILE,
)


def load_revoked_keys() -> list[str]:
    """Load the list of revoked token hashes."""
    if REVOCATION_FILE.exists():
        with open(REVOCATION_FILE, encoding="utf-8") as f:
            return [r["hash"] for r in json.load(f)]
    return []


def generate_manifest() -> None:
    """Build ``public_manifest.json`` from the token registry.

    Only active, non-expired, non-revoked entries are included.
    The revocation list is embedded so clients can check locally.
    """
    if not REGISTRY_FILE.exists():
        print("No registry found. Run setup_backend.py first.")
        return

    with open(REGISTRY_FILE, encoding="utf-8") as f:
        registry: list[dict] = json.load(f)

    revoked = set(load_revoked_keys())
    now = datetime.now().isoformat()

    manifest: dict = {
        "_meta": {
            "generated_at": now,
            "version": 2,
        },
        "_revoked": sorted(revoked),
    }

    for entry in registry:
        token_hash = entry.get("token_hash", "")

        # Skip revoked keys
        if token_hash in revoked:
            continue

        # Only include active, non-expired tokens
        if entry.get("status") != "active":
            continue
        expiry = entry.get("expiry")
        if expiry and expiry < now:
            continue

        pid = entry.get("product_id", "bits_whisperer")
        if pid not in manifest:
            manifest[pid] = {}

        manifest[pid][token_hash] = {
            "s": entry.get("signed_license", ""),
            "d": entry.get("devices", []),
            "u": entry.get("updated_at", "")[:10],
        }

    with open(PUBLIC_MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    products = [k for k in manifest if not k.startswith("_")]
    total = sum(len(manifest[p]) for p in products)
    print(f"Manifest generated: {total} active key(s) across {products}")


if __name__ == "__main__":
    generate_manifest()
