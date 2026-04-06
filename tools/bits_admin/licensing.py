"""Licensing configuration management for BITS Admin CLI.

Reads and writes the ``licensing`` section of ``feature_flags.json``
so administrators can remotely adjust trial length, grace periods,
device limits, broadcast messages, and tier names without a code
change.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default path to feature_flags.json at the repo root
_DEFAULT_FF_PATH = Path(__file__).resolve().parent.parent.parent / "feature_flags.json"

# Keys in the licensing section and their types for validation
_FIELD_TYPES: dict[str, type] = {
    "activation_mode": str,
    "trial_days": int,
    "offline_grace_days": int,
    "reverify_hours": int,
    "trial_warning_days": int,
    "max_devices": int,
    "admin_message": str,
    "purchase_url": str,
    "trial_extension_days": int,
    "grace_mode_enabled": bool,
    "grace_mode_days": int,
    "tier_names": dict,
}

# Default values (must stay in sync with LicensingConfig dataclass)
_DEFAULTS: dict[str, Any] = {
    "activation_mode": "beta",
    "trial_days": 7,
    "offline_grace_days": 30,
    "reverify_hours": 24,
    "trial_warning_days": 2,
    "max_devices": 3,
    "admin_message": "",
    "purchase_url": "",
    "trial_extension_days": 0,
    "grace_mode_enabled": False,
    "grace_mode_days": 7,
    "tier_names": {
        "L": "Lifetime Member",
        "A": "Active Membership",
        "C": "Paying Contributor",
        "T": "Alpha Tester",
    },
}


def _feature_flags_path(override: Path | None = None) -> Path:
    """Resolve the feature_flags.json path."""
    return override or _DEFAULT_FF_PATH


def load_feature_flags(path: Path | None = None) -> dict[str, Any]:
    """Load the full feature_flags.json file.

    Args:
        path: Override file path.

    Returns:
        Parsed JSON dict.
    """
    p = _feature_flags_path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8"))


def save_feature_flags(data: dict[str, Any], path: Path | None = None) -> None:
    """Write the feature_flags.json file back to disk.

    Args:
        data: Full JSON dict to write.
        path: Override file path.
    """
    p = _feature_flags_path(path)
    p.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_licensing_config(path: Path | None = None) -> dict[str, Any]:
    """Return the ``licensing`` section with defaults applied.

    Args:
        path: Override feature_flags.json path.

    Returns:
        Dict with all licensing fields guaranteed.
    """
    data = load_feature_flags(path)
    section = data.get("licensing", {})
    # Merge defaults for any missing keys
    result = dict(_DEFAULTS)
    result.update(section)
    return result


def set_licensing_field(
    field: str,
    value: Any,
    *,
    path: Path | None = None,
) -> None:
    """Update a single licensing field in feature_flags.json.

    Args:
        field: The field name (e.g. ``trial_days``).
        value: The new value.
        path: Override file path.

    Raises:
        KeyError: If *field* is not a valid licensing field.
        TypeError: If *value* does not match the expected type.
    """
    if field not in _FIELD_TYPES:
        msg = f"Unknown licensing field: {field!r}. Valid fields: {sorted(_FIELD_TYPES)}"
        raise KeyError(msg)

    expected = _FIELD_TYPES[field]
    if not isinstance(value, expected):
        msg = f"Field {field!r} expects {expected.__name__}, got {type(value).__name__}"
        raise TypeError(msg)

    data = load_feature_flags(path)
    data.setdefault("licensing", {})
    data["licensing"][field] = value
    save_feature_flags(data, path)


def set_tier_name(
    code: str,
    name: str,
    *,
    path: Path | None = None,
) -> None:
    """Update a single tier display name.

    Args:
        code: Status code (``L``, ``A``, ``C``, ``T``).
        name: New display name.
        path: Override file path.

    Raises:
        ValueError: If *code* is not a valid status code.
    """
    valid = {"L", "A", "C", "T"}
    if code not in valid:
        msg = f"Invalid tier code {code!r}. Valid codes: {sorted(valid)}"
        raise ValueError(msg)

    data = load_feature_flags(path)
    section = data.setdefault("licensing", {})
    tier_names = section.setdefault("tier_names", dict(_DEFAULTS["tier_names"]))
    tier_names[code] = name
    save_feature_flags(data, path)


def get_max_devices(path: Path | None = None) -> int:
    """Return the configured max-devices limit.

    Args:
        path: Override file path.

    Returns:
        Max devices (default 3).
    """
    return int(get_licensing_config(path).get("max_devices", 3))


def coerce_value(field: str, raw: str) -> Any:
    """Coerce a CLI string value to the correct Python type.

    Args:
        field: The licensing field name.
        raw: The raw string from the command line.

    Returns:
        The coerced Python value.

    Raises:
        KeyError: If *field* is unknown.
        ValueError: If *raw* cannot be coerced.
    """
    if field not in _FIELD_TYPES:
        msg = f"Unknown field: {field!r}"
        raise KeyError(msg)

    expected = _FIELD_TYPES[field]
    if expected is int:
        return int(raw)
    if expected is bool:
        if raw.lower() in ("true", "1", "yes", "on"):
            return True
        if raw.lower() in ("false", "0", "no", "off"):
            return False
        msg = f"Cannot parse {raw!r} as bool"
        raise ValueError(msg)
    if expected is str:
        return raw
    if expected is dict:
        return json.loads(raw)
    msg = f"Unsupported type {expected}"
    raise ValueError(msg)
