"""BITS Administration Utility — CLI entry point.

Run with::

    python -m tools.bits_admin <command> [options]

Commands:
    keys        Registration key management
    beta        Beta invitation management
    licensing   Licensing configuration management
    csv-import  Bulk import from CSV
    csv-export  Export to CSV
    manifest    Regenerate the public manifest
    audit       View audit log
    stats       Registry statistics
    keygen      Generate an Ed25519 key-pair
    init        Initialise the data directory

Examples::

    # Generate Ed25519 keys (first time setup)
    python -m tools.bits_admin keygen

    # Issue a lifetime key for a paid non-member customer
    python -m tools.bits_admin keys issue customer@corp.com \\
        --type lifetime --source paid --payment-ref INV-2024-042 \\
        --name "Jane Doe" --notes "Enterprise single-user licence"

    # Issue an annual key for a BITS member
    python -m tools.bits_admin keys issue member@bits.org \\
        --type annual --source member

    # Issue a 3-year key for a paid customer
    python -m tools.bits_admin keys issue buyer@co.com \\
        --type multi_year --source paid --duration 3y \\
        --payment-ref STRIPE-pi_123

    # Renew a key for another year
    python -m tools.bits_admin keys renew user@example.com --duration 365

    # List all keys
    python -m tools.bits_admin keys list

    # List paid non-member keys only
    python -m tools.bits_admin keys list --source paid

    # Revoke a key
    python -m tools.bits_admin keys revoke abuser@example.com \\
        --reason "Shared key online"

    # Generate 5 beta invitation codes
    python -m tools.bits_admin beta generate --count 5

    # Import paid customers from CSV
    python -m tools.bits_admin csv-import customers.csv \\
        --mode keys --source paid

    # Import beta testers from CSV
    python -m tools.bits_admin csv-import testers.csv --mode beta

    # Export all keys to CSV
    python -m tools.bits_admin csv-export keys output.csv

    # View audit log
    python -m tools.bits_admin audit --limit 20

    # Show statistics
    python -m tools.bits_admin stats

    # Licensing: Show current configuration
    python -m tools.bits_admin licensing show

    # Licensing: Set max devices to 5
    python -m tools.bits_admin licensing set max_devices 5

    # Licensing: Broadcast admin message
    python -m tools.bits_admin licensing broadcast Scheduled maintenance tonight

    # Licensing: Extend all trials by 3 days
    python -m tools.bits_admin licensing extend-trials 3

    # Licensing: Enable grace mode for 14 days
    python -m tools.bits_admin licensing grace-mode enable --days 14

    # Licensing: Rename a tier
    python -m tools.bits_admin licensing tiers L Lifetime Patron
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Private key resolution
# ---------------------------------------------------------------------------

_ENV_KEY = "BITS_PRIVATE_KEY_BASE64"


def _get_private_key(args: argparse.Namespace) -> str:
    """Resolve the signing key from --key, env var, or prompt."""
    # CLI flag takes priority
    key = getattr(args, "key", None)
    if key:
        return key

    # Environment variable
    env = os.environ.get(_ENV_KEY)
    if env:
        return env

    # Interactive prompt
    print(f"No private key found (set {_ENV_KEY} or use --key).")
    sys.exit(1)


def _parse_duration(value: str) -> int:
    """Parse a human-friendly duration into days."""
    v = value.strip().lower()
    try:
        return int(v)
    except ValueError:
        pass
    for suffix, multiplier in [
        ("y", 365),
        ("yr", 365),
        ("yrs", 365),
        ("year", 365),
        ("years", 365),
        ("m", 30),
        ("mo", 30),
        ("mos", 30),
        ("month", 30),
        ("months", 30),
    ]:
        if v.endswith(suffix):
            try:
                return int(v[: -len(suffix)].strip()) * multiplier
            except ValueError:
                pass
    print(f"Cannot parse duration: {value!r}")
    sys.exit(1)


# ===================================================================
# Sub-command handlers
# ===================================================================


def _cmd_keygen(_args: argparse.Namespace) -> None:
    """Generate a new Ed25519 key-pair."""
    from .crypto import generate_keypair

    priv, pub = generate_keypair()
    print("=" * 60)
    print("BITS CENTRAL REGISTRATION — KEY GENERATION")
    print("=" * 60)
    print()
    print("[GITHUB SECRET]")
    print(f"  Name:  {_ENV_KEY}")
    print(f"  Value: {priv}")
    print()
    print("[APP CODE]")
    print("  Name:  BITS_PUBLIC_KEY_BASE64")
    print(f"  Value: {pub}")
    print()
    print("=" * 60)
    print("CRITICAL: Save the private key securely. If lost, all")
    print("licences must be re-issued.")
    print("=" * 60)


def _cmd_init(_args: argparse.Namespace) -> None:
    """Initialise the data directory."""
    from .config import (
        AUDIT_LOG_FILE,
        BETA_INVITATIONS_FILE,
        DATA_DIR,
        REVOKED_KEYS_FILE,
        TOKENS_FILE,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f, default in [
        (TOKENS_FILE, "[]"),
        (REVOKED_KEYS_FILE, "[]"),
        (AUDIT_LOG_FILE, "[]"),
    ]:
        if not f.exists():
            f.write_text(default, encoding="utf-8")
            print(f"  Created {f}")
        else:
            print(f"  Exists  {f}")

    if not BETA_INVITATIONS_FILE.exists():
        import json

        BETA_INVITATIONS_FILE.write_text(
            json.dumps(
                {
                    "version": 1,
                    "description": "Beta programme invitation codes (SHA-256 hashed).",
                    "codes": [],
                    "metadata": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  Created {BETA_INVITATIONS_FILE}")
    else:
        print(f"  Exists  {BETA_INVITATIONS_FILE}")

    print("\nInitialisation complete.")


# ---------------------------------------------------------------------------
# keys sub-commands
# ---------------------------------------------------------------------------


def _cmd_keys_issue(args: argparse.Namespace) -> None:
    """Issue a registration key."""
    from .config import KeySource, KeyType
    from .registry import generate_manifest, issue_key

    private_key = _get_private_key(args)
    kt = KeyType(args.type)
    src = KeySource(args.source)
    duration = None
    if args.duration:
        duration = _parse_duration(args.duration)

    entry, created = issue_key(
        args.email,
        private_key,
        product_id=args.product,
        key_type=kt,
        source=src,
        duration_days=duration,
        name=args.name or "",
        payment_ref=args.payment_ref or "",
        notes=args.notes or "",
    )
    generate_manifest()

    action = "Issued" if created else "Upgraded"
    print(f"{action} key for {args.email}:")
    print(f"  Key:     {entry.key}")
    print(f"  Type:    {entry.key_type}")
    print(f"  Source:  {entry.source}")
    print(f"  Product: {entry.product_id}")
    if entry.expiry:
        print(f"  Expiry:  {entry.expiry[:10]}")
    if entry.payment_ref:
        print(f"  Payment: {entry.payment_ref}")


def _cmd_keys_renew(args: argparse.Namespace) -> None:
    """Renew an existing key."""
    from .registry import generate_manifest, renew_key

    private_key = _get_private_key(args)
    duration = _parse_duration(args.duration) if args.duration else 365

    entry = renew_key(
        args.email,
        private_key,
        product_id=args.product,
        duration_days=duration,
        payment_ref=args.payment_ref or "",
    )
    if entry:
        generate_manifest()
        print(f"Renewed key for {args.email}:")
        print(f"  New expiry: {entry.expiry[:10] if entry.expiry else 'Never'}")
    else:
        print(f"No key found for {args.email} / {args.product}")
        sys.exit(1)


def _cmd_keys_revoke(args: argparse.Namespace) -> None:
    """Revoke a key."""
    from .registry import generate_manifest, revoke_key

    ok = revoke_key(args.email, args.product, args.reason)
    if ok:
        generate_manifest()
        print(f"REVOKED key for {args.email} ({args.product})")
        print(f"  Reason: {args.reason}")
    else:
        print(f"No key found for {args.email} / {args.product}")
        sys.exit(1)


def _cmd_keys_reset_devices(args: argparse.Namespace) -> None:
    """Reset device limit."""
    from .registry import generate_manifest, reset_devices

    count = reset_devices(args.email, args.product)
    if count >= 0:
        generate_manifest()
        print(f"Cleared {count} device(s) for {args.email} / {args.product}")
    else:
        print(f"No entry found for {args.email} / {args.product}")
        sys.exit(1)


def _cmd_keys_list(args: argparse.Namespace) -> None:
    """List registration keys."""
    from .licensing import get_max_devices
    from .registry import list_entries, load_revoked_hashes

    entries = list_entries(
        product_id=args.product,
        source=args.source,
        status=args.status,
        key_type=args.type,
        expired_only=args.expired,
    )
    revoked = load_revoked_hashes()

    if not entries:
        print("No keys found matching the filters.")
        return

    # Header
    print(
        f"{'Email':<35} {'Name':<18} {'Product':<16} "
        f"{'Type':<12} {'Source':<12} {'Status':<9} "
        f"{'Devices':<8} {'Expires':<12} {'Payment'}"
    )
    print("-" * 140)

    for e in entries:
        rev_tag = " [REVOKED]" if e.token_hash in revoked else ""
        expiry = e.expiry[:10] if e.expiry else "Never"
        name = (e.name[:16] + "..") if len(e.name) > 18 else e.name
        print(
            f"{e.email:<35} {name:<18} {e.product_id:<16} "
            f"{e.key_type:<12} {e.source:<12} {e.status:<9} "
            f"{len(e.devices)}/{get_max_devices():<5} {expiry:<12} {e.payment_ref}{rev_tag}"
        )
        if args.devices and e.devices:
            for dev in e.devices:
                print(f"    device: {dev}")

    print(f"\nTotal: {len(entries)} key(s)")


def _cmd_keys_show(args: argparse.Namespace) -> None:
    """Show detailed info for a single key."""
    from .licensing import get_max_devices
    from .registry import find_entry

    entry = find_entry(args.email, args.product)
    if not entry:
        print(f"No key found for {args.email} / {args.product}")
        sys.exit(1)

    print(f"Email:       {entry.email}")
    print(f"Name:        {entry.name or '(none)'}")
    print(f"Key:         {entry.key}")
    print(f"Hash:        {entry.token_hash[:24]}...")
    print(f"Product:     {entry.product_id}")
    print(f"Type:        {entry.key_type}")
    print(f"Source:      {entry.source}")
    print(f"Status:      {entry.status}")
    print(f"Expiry:      {entry.expiry or 'Never'}")
    if entry.duration_days:
        print(f"Duration:    {entry.duration_days} days")
    print(f"Devices:     {len(entry.devices)}/{get_max_devices()}")
    for i, d in enumerate(entry.devices, 1):
        print(f"  [{i}] {d}")
    print(f"Created:     {entry.created_at}")
    print(f"Updated:     {entry.updated_at}")
    print(f"Issued by:   {entry.issued_by}")
    if entry.payment_ref:
        print(f"Payment ref: {entry.payment_ref}")
    if entry.notes:
        print(f"Notes:       {entry.notes}")


# ---------------------------------------------------------------------------
# beta sub-commands
# ---------------------------------------------------------------------------


def _cmd_beta_generate(args: argparse.Namespace) -> None:
    """Generate beta invitation codes."""
    from .beta import generate_and_add

    results = generate_and_add(
        count=args.count,
        prefix=args.prefix,
        email=args.email or "",
        name=args.name or "",
        notes=args.notes or "",
    )
    print(f"Generated {len(results)} invitation code(s):\n")
    for code, code_hash in results:
        print(f"  Code: {code}")
        print(f"  Hash: {code_hash[:24]}...")
        if args.email:
            print(f"  For:  {args.email}")
        print()
    print("IMPORTANT: The plaintext codes above are shown ONCE ONLY.")
    print("Send them securely to recipients and do NOT store them.")


def _cmd_beta_list(args: argparse.Namespace) -> None:
    """List beta invitations."""
    from .beta import list_invitations

    invitations = list_invitations()
    if not invitations:
        print("No beta invitations found.")
        return

    print(f"{'Hash (first 24)':<26} {'Email':<30} {'Name':<20} {'Added'}")
    print("-" * 100)
    for inv in invitations:
        print(
            f"{inv['hash'][:24]:<26} {inv['email'] or '(anon)':<30} "
            f"{inv['name'] or '':<20} {inv['added_at'][:10] if inv['added_at'] else ''}"
        )
    print(f"\nTotal: {len(invitations)} invitation(s)")


def _cmd_beta_revoke(args: argparse.Namespace) -> None:
    """Revoke a beta invitation."""
    from .beta import revoke_invitation

    ok = revoke_invitation(args.hash)
    if ok:
        print(f"Revoked invitation {args.hash[:24]}...")
    else:
        print(f"Hash not found: {args.hash[:24]}...")
        sys.exit(1)


def _cmd_beta_verify(args: argparse.Namespace) -> None:
    """Verify a beta code (without adding it)."""
    from .beta import load_invitations
    from .crypto import sha256_normalised

    code_hash = sha256_normalised(args.code)
    data = load_invitations()
    codes = data.get("codes", [])
    if code_hash in codes:
        print(f"VALID — code matches hash {code_hash[:24]}...")
    else:
        print("INVALID — no matching hash found")
        sys.exit(1)


# ---------------------------------------------------------------------------
# csv sub-commands
# ---------------------------------------------------------------------------


def _cmd_csv_import(args: argparse.Namespace) -> None:
    """Import from CSV."""
    from .beta import add_invitation
    from .config import KeySource, KeyType
    from .csv_ops import parse_csv
    from .registry import generate_manifest, issue_key

    csv_path = Path(args.file)
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    # Build explicit column map from --map flags
    explicit_map: dict[str, str] = {}
    if args.map:
        for m in args.map:
            if "=" not in m:
                print(f"Invalid --map format: {m!r} (expected canonical=csv_header)")
                sys.exit(1)
            canonical, csv_header = m.split("=", 1)
            explicit_map[canonical.strip()] = csv_header.strip()

    rows = parse_csv(csv_path, column_map=explicit_map)
    if not rows:
        print("CSV is empty or could not be parsed.")
        return

    # Validate
    errors = [(r.line_number, r.errors) for r in rows if r.errors]
    if errors:
        print(f"Validation errors in {len(errors)} row(s):")
        for line, errs in errors:
            print(f"  Line {line}: {'; '.join(errs)}")
        if not args.force:
            print("\nUse --force to skip invalid rows and process the rest.")
            sys.exit(1)

    valid_rows = [r for r in rows if not r.errors]

    if args.mode == "keys":
        private_key = _get_private_key(args)
        issued = 0
        upgraded = 0
        for row in valid_rows:
            type_values = [e.value for e in KeyType]
            kt = KeyType(row.key_type) if row.key_type in type_values else KeyType.ANNUAL
            src_val = args.source_override or row.source
            src = KeySource(src_val) if src_val in [e.value for e in KeySource] else KeySource.ADMIN
            _entry, created = issue_key(
                row.email,
                private_key,
                product_id=row.product_id,
                key_type=kt,
                source=src,
                duration_days=row.duration_days,
                name=row.name,
                payment_ref=row.payment_ref,
                notes=row.notes,
            )
            if created:
                issued += 1
            else:
                upgraded += 1
        generate_manifest()
        print(f"Imported {issued} new key(s), upgraded {upgraded} existing key(s).")
        print("Manifest updated.")

    elif args.mode == "beta":
        from .beta import generate_invitation_code

        generated: list[tuple[str, str]] = []
        for row in valid_rows:
            code = generate_invitation_code(row.prefix)
            code_hash = add_invitation(
                code,
                email=row.email,
                name=row.name,
                notes=row.notes,
            )
            generated.append((code, code_hash))

        print(f"Generated {len(generated)} beta invitation(s):\n")
        for code, _ in generated:
            print(f"  {code}")
        print("\nIMPORTANT: Save these codes now. They will NOT be shown again.")

    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)


def _cmd_csv_export(args: argparse.Namespace) -> None:
    """Export to CSV."""
    output = Path(args.output)

    if args.what == "keys":
        from .csv_ops import export_csv
        from .registry import list_entries

        entries = list_entries(
            product_id=args.product,
            source=args.source,
        )
        count = export_csv(entries, output, include_keys=args.include_keys)
        print(f"Exported {count} key(s) to {output}")

    elif args.what == "beta":
        from .beta import list_invitations
        from .csv_ops import export_beta_csv

        invitations = list_invitations()
        count = export_beta_csv(invitations, output)
        print(f"Exported {count} invitation(s) to {output}")

    else:
        print(f"Unknown export type: {args.what}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# manifest, audit, stats
# ---------------------------------------------------------------------------


def _cmd_manifest(args: argparse.Namespace) -> None:
    """Regenerate the public manifest."""
    from .registry import generate_manifest

    count = generate_manifest()
    print(f"Manifest regenerated with {count} active key(s).")


def _cmd_audit(args: argparse.Namespace) -> None:
    """View audit log."""
    from .registry import get_audit_log

    entries = get_audit_log(args.limit)
    if not entries:
        print("No audit entries found.")
        return

    print(f"{'Timestamp':<26} {'Action':<18} {'Email':<30} {'Product':<16} Details")
    print("-" * 120)
    for e in entries:
        details = ""
        if e.get("details"):
            details = str(e["details"])
            if len(details) > 40:
                details = details[:37] + "..."
        print(
            f"{e['timestamp']:<26} {e['action']:<18} "
            f"{e['email']:<30} {e['product_id']:<16} {details}"
        )
    print(f"\nShowing {len(entries)} entries.")


def _cmd_stats(args: argparse.Namespace) -> None:
    """Show registry statistics."""
    from .licensing import get_licensing_config
    from .registry import get_stats

    s = get_stats(args.product)
    print("=" * 50)
    print("BITS Registration Statistics")
    print("=" * 50)
    print(f"Total keys:  {s['total']}")
    print(f"Active:      {s['active']}")
    print(f"Expired:     {s['expired']}")
    print(f"Revoked:     {s['revoked']}")
    print()
    print("By type:")
    for k, v in sorted(s["by_type"].items()):
        print(f"  {k:<16} {v}")
    print()
    print("By source:")
    for k, v in sorted(s["by_source"].items()):
        print(f"  {k:<16} {v}")
    print()
    print("By product:")
    for k, v in sorted(s["by_product"].items()):
        print(f"  {k:<16} {v}")

    # Beta stats
    from .beta import list_invitations

    invitations = list_invitations()
    print(f"\nBeta invitations: {len(invitations)}")

    # Licensing config summary
    lic = get_licensing_config()
    print()
    print("Licensing config:")
    print(f"  Trial days:        {lic['trial_days']}")
    print(f"  Max devices:       {lic['max_devices']}")
    print(f"  Offline grace:     {lic['offline_grace_days']} days")
    print(f"  Re-verify every:   {lic['reverify_hours']}h")
    print(f"  Trial extension:   +{lic['trial_extension_days']} days")
    print(f"  Grace mode:        {'ON' if lic['grace_mode_enabled'] else 'OFF'}")
    if lic["admin_message"]:
        print(f"  Admin message:     {lic['admin_message']}")


# ---------------------------------------------------------------------------
# licensing sub-commands
# ---------------------------------------------------------------------------


def _cmd_licensing_show(_args: argparse.Namespace) -> None:
    """Display current licensing configuration."""
    from .licensing import get_licensing_config

    lic = get_licensing_config()
    print("=" * 50)
    print("Licensing Configuration")
    print("=" * 50)
    for key, value in lic.items():
        if key == "tier_names":
            print(f"  {key}:")
            for code, name in value.items():
                print(f"    {code} = {name}")
        else:
            print(f"  {key:<24} {value}")


def _cmd_licensing_set(args: argparse.Namespace) -> None:
    """Set a licensing config field."""
    from .licensing import coerce_value, set_licensing_field

    try:
        value = coerce_value(args.field, args.value)
        set_licensing_field(args.field, value)
        print(f"Set licensing.{args.field} = {value!r}")
    except (KeyError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_licensing_broadcast(args: argparse.Namespace) -> None:
    """Set or clear the admin broadcast message."""
    from .licensing import set_licensing_field

    message = " ".join(args.message) if args.message else ""
    set_licensing_field("admin_message", message)
    if message:
        print(f"Broadcast set: {message}")
    else:
        print("Broadcast cleared.")


def _cmd_licensing_extend_trials(args: argparse.Namespace) -> None:
    """Set global trial extension bonus days."""
    from .licensing import set_licensing_field

    set_licensing_field("trial_extension_days", args.days)
    if args.days:
        print(f"All active trials extended by +{args.days} bonus day(s).")
    else:
        print("Trial extension bonus cleared (0 extra days).")


def _cmd_licensing_grace_mode(args: argparse.Namespace) -> None:
    """Enable or disable grace mode."""
    from .licensing import set_licensing_field

    enabled = args.action == "enable"
    set_licensing_field("grace_mode_enabled", enabled)
    if args.days is not None:
        set_licensing_field("grace_mode_days", args.days)
    status = "ENABLED" if enabled else "DISABLED"
    days_str = f" ({args.days} days)" if args.days is not None else ""
    print(f"Grace mode {status}{days_str}.")


def _cmd_licensing_tiers(args: argparse.Namespace) -> None:
    """Show or update tier display names."""
    from .licensing import get_licensing_config, set_tier_name

    if args.code and args.name:
        try:
            set_tier_name(args.code, " ".join(args.name))
            print(f"Tier {args.code} renamed to: {' '.join(args.name)}")
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        lic = get_licensing_config()
        print("Tier display names:")
        for code, name in lic["tier_names"].items():
            print(f"  {code} = {name}")


# ===================================================================
# Argument parser
# ===================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the full argument parser with all sub-commands."""
    parser = argparse.ArgumentParser(
        prog="bits_admin",
        description="BITS Administration Utility — manage registration keys, "
        "beta invitations, and user records.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--key",
        metavar="BASE64",
        help=f"Ed25519 private key (base64). Also reads {_ENV_KEY} env var.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Top-level commands")

    # ---- keygen ----
    subparsers.add_parser("keygen", help="Generate a new Ed25519 key-pair")

    # ---- init ----
    subparsers.add_parser("init", help="Initialise the data directory")

    # ---- keys ----
    keys_parser = subparsers.add_parser("keys", help="Registration key management")
    keys_sub = keys_parser.add_subparsers(dest="keys_cmd")

    # keys issue
    ki = keys_sub.add_parser("issue", help="Issue or upgrade a key")
    ki.add_argument("email", help="User email address")
    ki.add_argument("--product", default="bits_whisperer", help="Product ID")
    ki.add_argument(
        "--type",
        choices=["annual", "lifetime", "multi_year", "contributor"],
        default="annual",
        help="Key type",
    )
    ki.add_argument(
        "--source",
        choices=["member", "paid", "contributor", "admin", "groupsio_sync", "beta", "promotional"],
        default="admin",
        help="How the key was acquired",
    )
    ki.add_argument(
        "--duration",
        help="Duration (e.g. 365, 2y, 3years, 6m). Overrides default for type.",
    )
    ki.add_argument("--name", help="Recipient name")
    ki.add_argument("--payment-ref", help="Payment/invoice reference (Stripe, PayPal, etc.)")
    ki.add_argument("--notes", help="Admin notes")

    # keys renew
    kr = keys_sub.add_parser("renew", help="Renew an existing key")
    kr.add_argument("email")
    kr.add_argument("--product", default="bits_whisperer")
    kr.add_argument("--duration", default="365", help="Duration from today (e.g. 365, 1y)")
    kr.add_argument("--payment-ref", help="New payment reference")

    # keys revoke
    kv = keys_sub.add_parser("revoke", help="Revoke a key (adds to blocklist)")
    kv.add_argument("email")
    kv.add_argument("--product", default="bits_whisperer")
    kv.add_argument("--reason", default="Admin revocation", help="Reason for revocation")

    # keys reset-devices
    krd = keys_sub.add_parser("reset-devices", help="Reset device limit for a user")
    krd.add_argument("email")
    krd.add_argument("--product", default="bits_whisperer")

    # keys list
    kl = keys_sub.add_parser("list", help="List keys")
    kl.add_argument("--product", help="Filter by product ID")
    kl.add_argument("--source", help="Filter by source (member, paid, ...)")
    kl.add_argument("--status", help="Filter by status (active, revoked, expired)")
    kl.add_argument("--type", help="Filter by key type")
    kl.add_argument("--expired", action="store_true", help="Show only expired keys")
    kl.add_argument("--devices", action="store_true", help="Show device IDs")

    # keys show
    ks = keys_sub.add_parser("show", help="Show detailed info for a key")
    ks.add_argument("email")
    ks.add_argument("--product", default="bits_whisperer")

    # ---- beta ----
    beta_parser = subparsers.add_parser("beta", help="Beta invitation management")
    beta_sub = beta_parser.add_subparsers(dest="beta_cmd")

    # beta generate
    bg = beta_sub.add_parser("generate", help="Generate invitation codes")
    bg.add_argument("--count", type=int, default=1, help="Number of codes")
    bg.add_argument("--prefix", default="BETA", help="Code prefix (BETA, VIP, CONF...)")
    bg.add_argument("--email", help="Recipient email")
    bg.add_argument("--name", help="Recipient name")
    bg.add_argument("--notes", help="Admin notes")

    # beta list
    beta_sub.add_parser("list", help="List invitations")

    # beta revoke
    br = beta_sub.add_parser("revoke", help="Revoke an invitation by hash")
    br.add_argument("hash", help="Full SHA-256 hash of the code to revoke")

    # beta verify
    bv = beta_sub.add_parser("verify", help="Check if a code is valid (testing)")
    bv.add_argument("code", help="Plaintext code to verify")

    # ---- csv-import ----
    ci = subparsers.add_parser("csv-import", help="Bulk import from CSV")
    ci.add_argument("file", help="Path to CSV file")
    ci.add_argument(
        "--mode",
        choices=["keys", "beta"],
        required=True,
        help="Import as registration keys or beta invitations",
    )
    ci.add_argument(
        "--map",
        action="append",
        metavar="FIELD=HEADER",
        help="Map canonical field to CSV header (e.g. email=Email_Address)",
    )
    ci.add_argument(
        "--source-override",
        help="Override the source for all imported keys (e.g. --source-override paid)",
    )
    ci.add_argument(
        "--force",
        action="store_true",
        help="Skip invalid rows instead of aborting",
    )

    # ---- csv-export ----
    ce = subparsers.add_parser("csv-export", help="Export to CSV")
    ce.add_argument("what", choices=["keys", "beta"], help="What to export")
    ce.add_argument("output", help="Output CSV file path")
    ce.add_argument("--product", help="Filter by product (keys only)")
    ce.add_argument("--source", help="Filter by source (keys only)")
    ce.add_argument(
        "--include-keys",
        action="store_true",
        help="Include plaintext keys in export (SECURITY WARNING)",
    )

    # ---- manifest ----
    subparsers.add_parser("manifest", help="Regenerate the public manifest")

    # ---- audit ----
    au = subparsers.add_parser("audit", help="View security audit log")
    au.add_argument("--limit", type=int, default=50, help="Number of entries")

    # ---- stats ----
    st = subparsers.add_parser("stats", help="Show registry statistics")
    st.add_argument("--product", help="Filter by product")

    # ---- licensing ----
    lic_parser = subparsers.add_parser(
        "licensing",
        help="Licensing configuration management",
    )
    lic_sub = lic_parser.add_subparsers(dest="lic_cmd")

    # licensing show
    lic_sub.add_parser("show", help="Display current licensing config")

    # licensing set
    ls = lic_sub.add_parser("set", help="Set a licensing config field")
    ls.add_argument("field", help="Field name (e.g. trial_days, max_devices)")
    ls.add_argument("value", help="New value")

    # licensing broadcast
    lb = lic_sub.add_parser(
        "broadcast",
        help="Set or clear admin broadcast message",
    )
    lb.add_argument(
        "message",
        nargs="*",
        help="Message text (omit to clear)",
    )

    # licensing extend-trials
    le = lic_sub.add_parser(
        "extend-trials",
        help="Set global trial extension bonus days",
    )
    le.add_argument("days", type=int, help="Bonus days (0 to clear)")

    # licensing grace-mode
    lg = lic_sub.add_parser(
        "grace-mode",
        help="Enable or disable grace mode",
    )
    lg.add_argument(
        "action",
        choices=["enable", "disable"],
        help="Enable or disable",
    )
    lg.add_argument(
        "--days",
        type=int,
        help="Grace mode duration in days",
    )

    # licensing tiers
    lt = lic_sub.add_parser(
        "tiers",
        help="Show or update tier display names",
    )
    lt.add_argument(
        "code",
        nargs="?",
        help="Status code (L, A, C, T)",
    )
    lt.add_argument(
        "name",
        nargs="*",
        help="New display name",
    )

    return parser


# ===================================================================
# Main dispatch
# ===================================================================


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch: dict[str, object] = {
        "keygen": _cmd_keygen,
        "init": _cmd_init,
        "manifest": _cmd_manifest,
        "audit": _cmd_audit,
        "stats": _cmd_stats,
        "csv-import": _cmd_csv_import,
        "csv-export": _cmd_csv_export,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
        return

    if args.command == "keys":
        keys_dispatch: dict[str, object] = {
            "issue": _cmd_keys_issue,
            "renew": _cmd_keys_renew,
            "revoke": _cmd_keys_revoke,
            "reset-devices": _cmd_keys_reset_devices,
            "list": _cmd_keys_list,
            "show": _cmd_keys_show,
        }
        if args.keys_cmd in keys_dispatch:
            keys_dispatch[args.keys_cmd](args)
        else:
            parser.parse_args(["keys", "--help"])
        return

    if args.command == "beta":
        beta_dispatch: dict[str, object] = {
            "generate": _cmd_beta_generate,
            "list": _cmd_beta_list,
            "revoke": _cmd_beta_revoke,
            "verify": _cmd_beta_verify,
        }
        if args.beta_cmd in beta_dispatch:
            beta_dispatch[args.beta_cmd](args)
        else:
            parser.parse_args(["beta", "--help"])
        return

    if args.command == "licensing":
        lic_dispatch: dict[str, object] = {
            "show": _cmd_licensing_show,
            "set": _cmd_licensing_set,
            "broadcast": _cmd_licensing_broadcast,
            "extend-trials": _cmd_licensing_extend_trials,
            "grace-mode": _cmd_licensing_grace_mode,
            "tiers": _cmd_licensing_tiers,
        }
        if args.lic_cmd in lic_dispatch:
            lic_dispatch[args.lic_cmd](args)
        else:
            parser.parse_args(["licensing", "--help"])
        return

    parser.print_help()


if __name__ == "__main__":
    main()
