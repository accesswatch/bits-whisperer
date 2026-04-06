"""Administrative CLI for BITS Central Registration System.

Usage::

    python backend_scripts/admin_cli.py issue user@example.com --type lifetime
    python backend_scripts/admin_cli.py list --status active --type lifetime
    python backend_scripts/admin_cli.py lookup --email user@example.com
    python backend_scripts/admin_cli.py revoke user@example.com bits_whisperer
    python backend_scripts/admin_cli.py stats
    python backend_scripts/admin_cli.py audit --limit 20
    python backend_scripts/admin_cli.py update-manifest

Run from the repository root (``BITS_Registration/`` when standalone,
or ``BITS_Registration/`` subfolder within the main repo).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure backend_scripts/ is on sys.path so sibling imports work
# regardless of CWD.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from registry_manager import (  # noqa: E402
    AUDIT_LOG_FILE,
    VALID_KEY_TYPES,
    add_to_revocation_list,
    clean_expired_tokens,
    get_statistics,
    is_revoked,
    issue_key,
    load_registry,
    log_audit_event,
    lookup_key,
    save_registry,
)
from manifest_generator import generate_manifest  # noqa: E402


# ---------------------------------------------------------------------------
# Licensing config helper
# ---------------------------------------------------------------------------

_FEATURE_FLAGS_PATHS = [
    Path(__file__).resolve().parent.parent.parent / "feature_flags.json",
    Path(__file__).resolve().parent.parent / "feature_flags.json",
    Path.cwd() / "feature_flags.json",
]


def _get_max_devices() -> int:
    """Read max_devices from feature_flags.json (default 3)."""
    for p in _FEATURE_FLAGS_PATHS:
        if p.exists():
            try:
                data = json.loads(p.read_text("utf-8"))
                return int(data.get("licensing", {}).get("max_devices", 3))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    return 3


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_issue(args: argparse.Namespace) -> None:
    """Issue or upgrade a licence key."""
    try:
        key, created = issue_key(
            args.email,
            product_id=args.product,
            key_type=args.type,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    generate_manifest()
    status = "Issued NEW" if created else "UPGRADED existing"
    print(f"{status} key for {args.email}:")
    print(f"  Key:     {key}")
    print(f"  Type:    {args.type}")
    print(f"  Product: {args.product}")


def cmd_list(args: argparse.Namespace) -> None:
    """List all registration keys with optional filters."""
    registry = load_registry()

    # Apply filters
    if args.product:
        registry = [e for e in registry if e["product_id"] == args.product]
    if args.status:
        registry = [e for e in registry if e["status"] == args.status]
    if args.type:
        registry = [e for e in registry if e["type"] == args.type]

    if not registry:
        print("No keys match the given filters.")
        return

    # Header
    print(
        f"{'Email':<30}  {'Product':<16}  {'Type':<12}  "
        f"{'Status':<8}  {'Dev':>3}  {'Expires':<12}  {'Flags'}"
    )
    print("-" * 105)

    for entry in registry:
        devices = len(entry.get("devices", []))
        expiry_raw = entry.get("expiry")
        expiry = expiry_raw[:10] if expiry_raw else "Never"
        flags: list[str] = []
        if is_revoked(entry.get("token_hash", "")):
            flags.append("REVOKED")
        if entry.get("status") == "expired":
            flags.append("EXPIRED")
        flag_str = " ".join(flags)

        print(
            f"{entry['email']:<30}  {entry['product_id']:<16}  "
            f"{entry['type']:<12}  {entry['status']:<8}  "
            f"{devices:>1}/{_get_max_devices()}  {expiry:<12}  {flag_str}"
        )

        if args.devices and entry.get("devices"):
            for dev in entry["devices"]:
                print(f"    └─ Device: {dev}")

    print(f"\nTotal: {len(registry)} key(s)")


def cmd_lookup(args: argparse.Namespace) -> None:
    """Look up a specific key by email, key value, or hash."""
    results = lookup_key(
        email=args.email,
        key_value=args.key,
        key_hash=args.hash,
        product_id=args.product,
    )
    if not results:
        print("No matching keys found.")
        sys.exit(1)

    for entry in results:
        revoked = is_revoked(entry.get("token_hash", ""))
        print(f"  Email:      {entry['email']}")
        print(f"  Product:    {entry['product_id']}")
        print(f"  Type:       {entry['type']}")
        print(f"  Status:     {entry['status']}{'  [REVOKED]' if revoked else ''}")
        print(f"  Key:        {entry['key']}")
        print(f"  Hash:       {entry['token_hash'][:16]}...")
        print(f"  Devices:    {len(entry.get('devices', []))}/{_get_max_devices()}")
        print(f"  Created:    {entry.get('created_at', 'N/A')[:19]}")
        print(f"  Updated:    {entry.get('updated_at', 'N/A')[:19]}")
        expiry = entry.get("expiry")
        print(f"  Expires:    {expiry[:10] if expiry else 'Never'}")
        if entry.get("devices"):
            print("  Registered devices:")
            for dev in entry["devices"]:
                print(f"    - {dev}")
        print()


def cmd_revoke(args: argparse.Namespace) -> None:
    """Revoke a key and add it to the revocation blocklist."""
    registry = load_registry()
    found = False
    for entry in registry:
        if entry["email"] == args.email and entry["product_id"] == args.product:
            entry["status"] = "revoked"
            add_to_revocation_list(entry["token_hash"], args.reason)
            log_audit_event(
                "KEY_REVOKED",
                args.email,
                args.product,
                {"reason": args.reason},
            )
            found = True
            break

    if found:
        save_registry(registry)
        generate_manifest()
        print(f"REVOKED key for {args.email} ({args.product})")
        print(f"  Reason: {args.reason}")
        print("  Added to blocklist. Manifest updated.")
    else:
        print(f"No key found for {args.email} / {args.product}", file=sys.stderr)
        sys.exit(1)


def cmd_reset_devices(args: argparse.Namespace) -> None:
    """Reset the device list for a user."""
    registry = load_registry()
    found = False
    cleared = 0
    for entry in registry:
        if entry["email"] == args.email and entry["product_id"] == args.product:
            cleared = len(entry.get("devices", []))
            entry["devices"] = []
            log_audit_event(
                "DEVICES_RESET",
                args.email,
                args.product,
                {"cleared": cleared},
            )
            found = True
            break

    if found:
        save_registry(registry)
        generate_manifest()
        print(
            f"Device list reset for {args.email} / {args.product}. "
            f"Cleared {cleared} device(s). Manifest updated."
        )
    else:
        print(f"No key found for {args.email} / {args.product}", file=sys.stderr)
        sys.exit(1)


def cmd_audit(args: argparse.Namespace) -> None:
    """Display the security audit log."""
    if not AUDIT_LOG_FILE.exists():
        print("No audit log found.")
        return

    with open(AUDIT_LOG_FILE, encoding="utf-8") as f:
        log = json.load(f)

    if not log:
        print("Audit log is empty.")
        return

    entries = log[-args.limit :]
    print(f"{'Timestamp':<20}  {'Action':<20}  {'Email':<30}  {'Product'}")
    print("-" * 100)
    for entry in entries:
        ts = entry["timestamp"][:19]
        print(f"{ts:<20}  {entry['action']:<20}  {entry['email']:<30}  {entry['product_id']}")
        if args.verbose and entry.get("details"):
            print(f"    Details: {json.dumps(entry['details'])}")

    print(f"\nShowing {len(entries)} of {len(log)} entries.")


def cmd_stats(_args: argparse.Namespace) -> None:
    """Display registry summary statistics."""
    stats = get_statistics()
    print("=== BITS Registration Statistics ===\n")
    print(f"Total keys:         {stats['total']}")
    print(f"Devices registered: {stats['devices_registered']}")
    print()
    print("By type:")
    for kt, count in sorted(stats["by_type"].items()):
        print(f"  {kt:<14}  {count}")
    print()
    print("By status:")
    for st, count in sorted(stats["by_status"].items()):
        print(f"  {st:<14}  {count}")

    # Check for expired keys
    expired = clean_expired_tokens()
    if expired:
        print(f"\n[!] Marked {expired} expired key(s).")


def cmd_export(args: argparse.Namespace) -> None:
    """Export the registry to a JSON file (keys redacted)."""
    registry = load_registry()
    if args.product:
        registry = [e for e in registry if e["product_id"] == args.product]

    # Redact sensitive data
    for entry in registry:
        entry.pop("key", None)
        entry.pop("signed_license", None)

    output = Path(args.output)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print(f"Exported {len(registry)} entries to {output} (keys & signatures redacted).")


def cmd_update_manifest(_args: argparse.Namespace) -> None:
    """Force-regenerate the public manifest."""
    generate_manifest()
    print("Public manifest updated.")


def cmd_expire(_args: argparse.Namespace) -> None:
    """Scan for and mark expired annual keys."""
    count = clean_expired_tokens()
    if count:
        generate_manifest()
        print(f"Marked {count} expired key(s). Manifest updated.")
    else:
        print("No expired keys found.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="admin_cli",
        description="BITS Central Registration — Administrative Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  issue user@example.com --type lifetime       Issue a lifetime key
  issue user@example.com --type tester         Issue a tester key
  list --status active --type lifetime         List active lifetime keys
  list --product bits_whisperer --devices      List keys with device info
  lookup --email user@example.com              Look up keys by email
  revoke user@example.com bits_whisperer       Revoke and block a key
  reset-devices user@example.com bits_whisperer  Clear device list
  stats                                        Show registry statistics
  audit --limit 20 --verbose                   View audit log with details
  export backup.json                           Export registry (redacted)
  expire                                       Mark expired keys
  update-manifest                              Regenerate public manifest
""",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- issue ---
    p_issue = subparsers.add_parser("issue", help="Issue or upgrade a licence key")
    p_issue.add_argument("email", help="User email address")
    p_issue.add_argument(
        "--product",
        default="bits_whisperer",
        help="Product ID (default: bits_whisperer)",
    )
    p_issue.add_argument(
        "--type",
        choices=VALID_KEY_TYPES,
        default="annual",
        help="Key type (default: annual)",
    )

    # --- list ---
    p_list = subparsers.add_parser("list", help="List registration keys")
    p_list.add_argument("--product", help="Filter by product ID")
    p_list.add_argument(
        "--status",
        choices=["active", "expired", "revoked"],
        help="Filter by status",
    )
    p_list.add_argument("--type", choices=VALID_KEY_TYPES, help="Filter by key type")
    p_list.add_argument(
        "--devices",
        action="store_true",
        help="Show registered device IDs",
    )

    # --- lookup ---
    p_lookup = subparsers.add_parser("lookup", help="Look up a specific key")
    p_lookup.add_argument("--email", help="Look up by email")
    p_lookup.add_argument("--key", help="Look up by raw key value")
    p_lookup.add_argument("--hash", help="Look up by token hash")
    p_lookup.add_argument("--product", help="Filter by product ID")

    # --- revoke ---
    p_revoke = subparsers.add_parser(
        "revoke",
        help="Revoke a key (adds to blocklist)",
    )
    p_revoke.add_argument("email", help="User email")
    p_revoke.add_argument("product", help="Product ID")
    p_revoke.add_argument(
        "--reason",
        default="Admin revocation",
        help="Reason for revocation",
    )

    # --- reset-devices ---
    p_reset = subparsers.add_parser(
        "reset-devices",
        help="Reset device list for a user",
    )
    p_reset.add_argument("email", help="User email")
    p_reset.add_argument("product", help="Product ID")

    # --- audit ---
    p_audit = subparsers.add_parser("audit", help="View security audit log")
    p_audit.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of entries to show (default: 50)",
    )
    p_audit.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show operation details",
    )

    # --- stats ---
    subparsers.add_parser("stats", help="Show registry statistics")

    # --- export ---
    p_export = subparsers.add_parser(
        "export",
        help="Export registry to JSON (keys redacted)",
    )
    p_export.add_argument("output", help="Output file path")
    p_export.add_argument("--product", help="Filter by product ID")

    # --- expire ---
    subparsers.add_parser("expire", help="Mark expired annual keys")

    # --- update-manifest ---
    subparsers.add_parser("update-manifest", help="Regenerate the public manifest")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COMMANDS = {
    "issue": cmd_issue,
    "list": cmd_list,
    "lookup": cmd_lookup,
    "revoke": cmd_revoke,
    "reset-devices": cmd_reset_devices,
    "audit": cmd_audit,
    "stats": cmd_stats,
    "export": cmd_export,
    "expire": cmd_expire,
    "update-manifest": cmd_update_manifest,
}


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = _COMMANDS.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
