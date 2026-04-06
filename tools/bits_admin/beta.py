"""Beta invitation code management.

Generates, hashes, and maintains the ``beta_invitations.json`` file
used by the BITS Whisperer app to verify beta tester status.
"""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime
from pathlib import Path

from .config import BETA_INVITATIONS_FILE
from .crypto import sha256_normalised

# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

_CODE_LENGTH = 16
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_invitation_code(prefix: str = "BETA") -> str:
    """Generate a random beta invitation code.

    Format: ``PREFIX-XXXX-XXXX-XXXX`` (16 random alphanumeric
    characters in groups of four).

    Args:
        prefix: Code prefix (default ``BETA``). Can also be
            ``VIP``, ``CONF``, etc.

    Returns:
        A formatted invitation code string.
    """
    chars = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    groups = [chars[i : i + 4] for i in range(0, _CODE_LENGTH, 4)]
    return f"{prefix}-" + "-".join(groups)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def load_invitations(path: Path | None = None) -> dict:
    """Load the ``beta_invitations.json`` file.

    Returns:
        The parsed JSON dict (with ``version``, ``codes``, etc.).
    """
    p = path or BETA_INVITATIONS_FILE
    if not p.exists():
        return {"version": 1, "description": "", "codes": [], "metadata": {}}
    return json.loads(p.read_text("utf-8"))


def save_invitations(data: dict, path: Path | None = None) -> None:
    """Write the invitations JSON back to disk."""
    p = path or BETA_INVITATIONS_FILE
    p.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def add_invitation(
    code: str,
    *,
    email: str = "",
    name: str = "",
    notes: str = "",
    path: Path | None = None,
) -> str:
    """Hash a code and add it to the invitations file.

    If metadata tracking is enabled (email/name), the hash is
    stored alongside human-readable info in a ``metadata`` dict
    separated from the ``codes`` list so the codes list stays a
    simple array of hashes.

    Args:
        code: Plaintext invitation code.
        email: Recipient email (stored in metadata only).
        name: Recipient name (stored in metadata only).
        notes: Admin notes (stored in metadata only).
        path: Override file path.

    Returns:
        The SHA-256 hash that was stored.
    """
    code_hash = sha256_normalised(code)
    data = load_invitations(path)

    # De-duplicate
    if code_hash in data.get("codes", []):
        return code_hash

    data.setdefault("codes", []).append(code_hash)

    # Metadata sidecar (never includes the plaintext code)
    if email or name or notes:
        meta = data.setdefault("metadata", {})
        meta[code_hash] = {
            "email": email,
            "name": name,
            "notes": notes,
            "added_at": datetime.now().isoformat(),
        }

    save_invitations(data, path)
    return code_hash


def revoke_invitation(
    code_hash: str,
    *,
    path: Path | None = None,
) -> bool:
    """Remove a code hash from the invitations file.

    Args:
        code_hash: The SHA-256 hash to remove.
        path: Override file path.

    Returns:
        ``True`` if the hash was found and removed.
    """
    data = load_invitations(path)
    codes: list[str] = data.get("codes", [])
    if code_hash not in codes:
        return False
    codes.remove(code_hash)
    data["codes"] = codes
    # Remove metadata entry too
    meta: dict = data.get("metadata", {})
    meta.pop(code_hash, None)
    save_invitations(data, path)
    return True


def list_invitations(path: Path | None = None) -> list[dict]:
    """Return a list of invitation entries with metadata.

    Each entry contains ``hash``, ``email``, ``name``, ``notes``,
    ``added_at``.

    Returns:
        List of dicts describing each invitation.
    """
    data = load_invitations(path)
    codes: list[str] = data.get("codes", [])
    meta: dict = data.get("metadata", {})
    results: list[dict] = []
    for h in codes:
        info = meta.get(h, {})
        results.append(
            {
                "hash": h,
                "email": info.get("email", ""),
                "name": info.get("name", ""),
                "notes": info.get("notes", ""),
                "added_at": info.get("added_at", ""),
            }
        )
    return results


def generate_and_add(
    count: int = 1,
    *,
    prefix: str = "BETA",
    email: str = "",
    name: str = "",
    notes: str = "",
    path: Path | None = None,
) -> list[tuple[str, str]]:
    """Generate one or more codes and immediately add their hashes.

    Args:
        count: How many codes to generate.
        prefix: Code prefix.
        email: Recipient email.
        name: Recipient name.
        notes: Admin notes.
        path: Override file path.

    Returns:
        List of ``(plaintext_code, sha256_hash)`` tuples.
        **The plaintext is only returned once** — it is NOT stored.
    """
    results: list[tuple[str, str]] = []
    for _ in range(count):
        code = generate_invitation_code(prefix)
        h = add_invitation(code, email=email, name=name, notes=notes, path=path)
        results.append((code, h))
    return results
