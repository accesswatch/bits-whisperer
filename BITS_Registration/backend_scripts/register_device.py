"""Device Registration with Anti-Replay Protection.

Called by the ``register_device.yml`` GitHub Actions workflow when
a BITS Whisperer client requests device registration via
``repository_dispatch``.

Usage::

    python backend_scripts/register_device.py <token_hash> <device_id> \
        [timestamp] [request_hash]
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

# Ensure sibling imports work regardless of CWD
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from registry_manager import (  # noqa: E402
    load_registry,
    log_audit_event,
    save_registry,
)

# Maximum age of a registration request (prevents replay attacks)
MAX_REQUEST_AGE_SECONDS = 300  # 5 minutes
MAX_DEVICES = 3


def validate_request(
    token_hash: str,
    device_id: str,
    timestamp: int,
    request_hash: str,
) -> bool:
    """Validate the registration request is fresh and untampered."""
    current_time = int(time.time())
    age = abs(current_time - timestamp)
    if age > MAX_REQUEST_AGE_SECONDS:
        print(f"Request expired. Age: {age}s (max {MAX_REQUEST_AGE_SECONDS}s).")
        return False

    expected = hashlib.sha256(
        f"{token_hash}|{device_id}|{timestamp}".encode(),
    ).hexdigest()[:16]
    if request_hash != expected:
        print("Request integrity check failed.")
        return False

    return True


def register_device(
    token_hash: str,
    device_id: str,
    timestamp: str | None = None,
    request_hash: str | None = None,
) -> bool:
    """Register a device against a token hash.

    Returns:
        ``True`` if the device was registered (or already registered).
    """
    # Validate anti-replay params if provided
    if timestamp and request_hash:
        if not validate_request(token_hash, device_id, int(timestamp), request_hash):
            log_audit_event(
                "DEVICE_REG_FAILED",
                "unknown",
                "unknown",
                {"token_hash": token_hash[:16], "reason": "validation_failed"},
            )
            return False

    registry = load_registry()
    user_email = "unknown"
    product_id = "unknown"

    for entry in registry:
        if entry.get("token_hash") != token_hash:
            continue

        user_email = entry["email"]
        product_id = entry["product_id"]

        devices: list[str] = entry.get("devices", [])

        if device_id in devices:
            print(f"Device {device_id[:8]}... already registered.")
            return True

        if len(devices) >= MAX_DEVICES:
            print(f"Device limit ({MAX_DEVICES}) reached for {token_hash[:16]}...")
            log_audit_event(
                "DEVICE_LIMIT_EXCEEDED",
                user_email,
                product_id,
                {"device_id": device_id[:8], "current_count": MAX_DEVICES},
            )
            return False

        devices.append(device_id)
        entry["devices"] = devices
        save_registry(registry)
        log_audit_event(
            "DEVICE_REGISTERED",
            user_email,
            product_id,
            {"device_id": device_id[:8], "count": len(devices)},
        )
        print(f"Device {device_id[:8]}... registered. ({len(devices)}/{MAX_DEVICES})")
        return True

    print(f"No token found for hash {token_hash[:16]}...")
    log_audit_event(
        "DEVICE_REG_FAILED",
        "unknown",
        "unknown",
        {"token_hash": token_hash[:16], "reason": "token_not_found"},
    )
    return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: register_device.py <token_hash> <device_id> [timestamp] [request_hash]",
        )
        sys.exit(1)

    success = register_device(*sys.argv[1:])
    sys.exit(0 if success else 1)
