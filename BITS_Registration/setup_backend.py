"""Initialize the BITS Registration backend environment.

Sets up the directory structure and empty data files needed by the
backend scripts and GitHub Actions workflows.

Usage::

    cd BITS_Registration
    python setup_backend.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def setup() -> None:
    """Run the first-time setup for the registration backend."""
    print("=" * 60)
    print("BITS Registration Backend — Setup")
    print("=" * 60)
    print()

    # 1. Check / install Python dependencies
    missing: list[str] = []
    for pkg in ("cryptography", "requests"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[!] Installing missing packages: {', '.join(missing)}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing],
            check=False,
        )
    else:
        print("[ok] Python dependencies are installed.")

    # 2. Verify backend_scripts/ directory
    scripts_dir = REPO_ROOT / "backend_scripts"
    if scripts_dir.is_dir():
        print("[ok] backend_scripts/ directory found.")
    else:
        print("[!!] backend_scripts/ directory is MISSING.", file=sys.stderr)

    # 3. Create empty data files if they don't exist
    data_files = {
        "tokens.json": "[]",
        "audit_log.json": "[]",
        "revoked_keys.json": "[]",
    }
    for filename, default in data_files.items():
        filepath = REPO_ROOT / filename
        if not filepath.exists():
            filepath.write_text(default, encoding="utf-8")
            print(f"[ok] Created {filename}")
        else:
            # Validate JSON
            try:
                json.loads(filepath.read_text(encoding="utf-8"))
                print(f"[ok] {filename} exists and is valid JSON.")
            except json.JSONDecodeError:
                print(f"[!!] {filename} exists but contains invalid JSON!", file=sys.stderr)

    # 4. Check for .gitignore entries
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# BITS Registration\n.mypy_cache/\n__pycache__/\n*.pyc\n.env\n",
            encoding="utf-8",
        )
        print("[ok] Created .gitignore")

    print()
    print("=" * 60)
    print("SETUP COMPLETE — NEXT STEPS:")
    print("=" * 60)
    print()
    print("1. Generate your Ed25519 key pair:")
    print("   python backend_scripts/key_generator.py")
    print()
    print("2. In your PRIVATE GitHub registry repo, add secrets:")
    print("   - BITS_PRIVATE_KEY_BASE64  (from step 1)")
    print("   - GROUPSIO_API_KEY         (for membership sync)")
    print("   - GROUPSIO_GROUP_NAME      (your Groups.io group)")
    print()
    print("3. In BITS Whisperer code (registration_service.py):")
    print("   - Set BITS_PUBLIC_KEY_BASE64 with the public key")
    print("   - Set MANIFEST_URL to your registry repo's raw URL")
    print()
    print("4. Test with the admin CLI:")
    print("   python backend_scripts/admin_cli.py issue test@example.com --type tester")
    print("   python backend_scripts/admin_cli.py list")
    print("   python backend_scripts/admin_cli.py stats")
    print()
    print("5. Copy .github/workflows/ to your registry repo.")
    print()
    print("=" * 60)


if __name__ == "__main__":
    setup()
