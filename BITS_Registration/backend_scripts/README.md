# BITS Central Registration Backend

This folder contains the automation and management scripts for the
BITS Registration system.

## Quick Start

1. **Read the guides**: See `ADMIN_GUIDE.md` and `DEPLOYMENT_GUIDE.md`
   in the parent folder.
2. **Run setup**: `python setup_backend.py` (from the repo root).
3. **Manage keys**: `python backend_scripts/admin_cli.py --help`.

## Licensing Configuration

The device limit, trial period, offline grace period, and other
licensing parameters are read from `feature_flags.json` in the main
BITS Whisperer repository (under the `licensing` key). The
`admin_cli.py` script reads `max_devices` from this file so that
device count displays match the configured limit. See
`ADMIN_GUIDE.md` → **Licensing Configuration** for the full list of
configurable fields.

## Scripts

| Script                   | Purpose                                       |
| ------------------------ | --------------------------------------------- |
| `admin_cli.py`           | Administrative CLI (10 commands)              |
| `registry_manager.py`    | Core library: key issuance, signing, registry |
| `manifest_generator.py`  | Builds `public_manifest.json` from registry   |
| `register_device.py`     | Device registration with anti-replay          |
| `groupsio_sync.py`       | Syncs Groups.io members → lifetime keys       |
| `key_generator.py`       | Generates Ed25519 key pair for signing        |

## Key Types

| Type          | Code | Expiry   | Description                     |
| ------------- | ---- | -------- | ------------------------------- |
| `annual`      | A    | 365 days | Paid annual subscription        |
| `lifetime`    | L    | Never    | BITS member or paid lifetime    |
| `contributor` | C    | Never    | Donation / OSS contribution     |
| `tester`      | T    | Never    | Alpha / beta tester             |

## Admin CLI Commands

```text
issue           Issue or upgrade a licence key
list            List all keys (with filters)
lookup          Find a specific key by email/hash/value
revoke          Revoke a key and add to blocklist
reset-devices   Clear device registrations
audit           View audit log
stats           Show registry statistics
export          Export registry (redacted)
expire          Mark expired annual keys
update-manifest Regenerate public_manifest.json
```

Run `python backend_scripts/admin_cli.py <command> --help` for
options on each command.
