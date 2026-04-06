"""Generate an Ed25519 key pair for the BITS Registration system.

Outputs:
    - Private key (base64) → store as ``BITS_PRIVATE_KEY_BASE64``
      GitHub repository secret.
    - Public key (base64) → embed in the BITS Whisperer app as
      ``BITS_PUBLIC_KEY_BASE64`` in ``registration_service.py``.

Usage::

    python backend_scripts/key_generator.py
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_keys() -> None:
    """Generate and display an Ed25519 key pair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_b64 = base64.b64encode(private_bytes).decode()

    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_b64 = base64.b64encode(public_bytes).decode()

    print("=" * 60)
    print("BITS REGISTRATION — Ed25519 KEY PAIR GENERATOR")
    print("=" * 60)
    print()
    print("[GITHUB REPOSITORY SECRET]")
    print(f"  Name:   BITS_PRIVATE_KEY_BASE64")
    print(f"  Value:  {private_b64}")
    print()
    print("[BITS WHISPERER APP CODE]")
    print(f"  Name:   BITS_PUBLIC_KEY_BASE64")
    print(f"  Value:  {public_b64}")
    print()
    print("=" * 60)
    print("CRITICAL: Store the private key securely. If lost, all")
    print("existing licence signatures become unverifiable.")
    print("=" * 60)


if __name__ == "__main__":
    generate_keys()
