# BITS Registration System — Administrative Guide

This document covers the full administration of the BITS Whisperer
registration and licensing system: issuing keys, managing users,
monitoring security, and operating the WordPress storefront.

______________________________________________________________________

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Key Types & Status Codes](#key-types--status-codes)
4. [Admin CLI Reference](#admin-cli-reference)
5. [WordPress Plugin Administration](#wordpress-plugin-administration)
6. [GitHub Actions Workflows](#github-actions-workflows)
7. [Groups.io Membership Sync](#groupsio-membership-sync)
8. [Security Operations](#security-operations)
9. [Troubleshooting](#troubleshooting)

______________________________________________________________________

## System Overview

The BITS Registration system uses a **GitHub-centric architecture**
where a private GitHub repository serves as the single source of truth
for all licence data. The system has four components:

| Component              | Role                                                  |
| ---------------------- | ----------------------------------------------------- |
| **Registry repo**      | Private GitHub repo storing keys, audit log, manifest |
| **Backend scripts**    | Python CLI tools for key management                   |
| **WordPress plugin**   | WooCommerce integration for paid licence sales        |
| **BITS Whisperer app** | Client-side verification against the public manifest  |

### Data flow

```text
Customer pays on WooCommerce
        │
        ▼
WordPress plugin triggers GitHub workflow_dispatch
        │
        ▼
GitHub Actions runs admin_cli.py → issues key → updates manifest
        │
        ▼
BITS Whisperer app fetches manifest → verifies key + device
```

______________________________________________________________________

## Architecture

### Repository structure

```text
bits-whisperer-registry/           (private GitHub repo)
├── .github/workflows/
│   ├── daily_sync.yml             Daily Groups.io sync + expiry
│   ├── manual_issue.yml           Manual key issuance via UI
│   └── register_device.yml        Device registration handler
├── backend_scripts/
│   ├── admin_cli.py               Administrative command-line tool
│   ├── groupsio_sync.py           Groups.io membership sync
│   ├── key_generator.py           Ed25519 key pair generator
│   ├── manifest_generator.py      Public manifest builder
│   ├── register_device.py         Device registration handler
│   └── registry_manager.py        Core licence management library
├── wordpress/
│   └── bits-registration/         WooCommerce plugin
│       ├── bits-registration.php  Plugin main file
│       └── readme.txt             WordPress readme
├── tokens.json                    Licence registry (sensitive)
├── audit_log.json                 Security audit trail
├── revoked_keys.json              Revocation blocklist
├── public_manifest.json           Published manifest (safe to expose)
├── requirements.txt               Python dependencies
├── setup_backend.py               First-time setup script
└── BITS_Registration_PRD.md       Product requirements document
```

### Security layers

1. **Ed25519 cryptographic signatures** — every licence blob is signed
   with the project's private key and verified client-side.
2. **Anti-replay timestamps** — signed payloads include issuance time.
3. **SHA-256 hashing** — raw keys are never stored in the manifest;
   only hashes are published.
4. **Configurable device limit** — each key can be activated on a
   limited number of devices (default: 3). The limit is set in
   `feature_flags.json` → `licensing.max_devices` and can be changed
   remotely without an app update. Device fingerprints combine MAC
   address, platform, processor, and user path.
5. **Revocation list** — revoked key hashes are embedded in the
   manifest for instant client-side blocking.
6. **Offline grace period** — clients can work offline for up to
   30 days after the last successful verification (configurable via
   `feature_flags.json` → `licensing.offline_grace_days`).
7. **Rate limiting** — the app limits online verification to once per
   60 seconds.

______________________________________________________________________

## Key Types & Status Codes

| Key Type       | Status Code | Expiry    | Description                          |
| -------------- | ----------- | --------- | ------------------------------------ |
| `annual`       | A           | 365 days  | Paid annual subscription             |
| `lifetime`     | L           | Never     | BITS member (free) or paid lifetime  |
| `contributor`  | C           | Never     | Donation or OSS contribution         |
| `tester`       | T           | Never     | Alpha / beta tester                  |

**Status code derivation**: The BITS Whisperer app extracts the first
letter of the key type from the signed payload:
`status_code = payload["t"][0].upper()`.

BITS members receive `lifetime` keys automatically via the Groups.io
daily sync. Paid customers receive `annual` or `lifetime` keys
depending on purchase.

______________________________________________________________________

## Admin CLI Reference

All commands are run from the registry repository root:

```bash
python backend_scripts/admin_cli.py <command> [options]
```

### Commands

#### `issue` — Issue or upgrade a key

```bash
python backend_scripts/admin_cli.py issue user@example.com --type lifetime
python backend_scripts/admin_cli.py issue user@example.com --type annual
python backend_scripts/admin_cli.py issue user@example.com --type tester
python backend_scripts/admin_cli.py issue user@example.com --type contributor
```

Options:

- `--product` — Product ID (default: `bits_whisperer`)
- `--type` — Key type: `annual`, `lifetime`, `contributor`, `tester`

#### `list` — List all keys

```bash
python backend_scripts/admin_cli.py list
python backend_scripts/admin_cli.py list --status active --type lifetime
python backend_scripts/admin_cli.py list --product bits_whisperer --devices
```

Options:

- `--product` — Filter by product ID
- `--status` — Filter: `active`, `expired`, `revoked`
- `--type` — Filter: `annual`, `lifetime`, `contributor`, `tester`
- `--devices` — Show registered device IDs

#### `lookup` — Find a specific key

```bash
python backend_scripts/admin_cli.py lookup --email user@example.com
python backend_scripts/admin_cli.py lookup --hash abc123...
python backend_scripts/admin_cli.py lookup --key bits_whisperer-uuid-xxxx
```

#### `revoke` — Revoke a key

```bash
python backend_scripts/admin_cli.py revoke user@example.com bits_whisperer --reason "Refund"
```

This revokes the key, adds the hash to the blocklist, and
regenerates the manifest. The user will be blocked within 24 hours
(manifest cache TTL) or immediately on next fresh verification.

#### `reset-devices` — Clear device registrations

```bash
python backend_scripts/admin_cli.py reset-devices user@example.com bits_whisperer
```

Use this when a user replaces their computer or reaches the device
limit (configurable via `feature_flags.json` → `licensing.max_devices`,
default: 3).

#### `stats` — Show statistics

```bash
python backend_scripts/admin_cli.py stats
```

Displays total keys, breakdown by type and status, total devices,
and marks any newly expired keys.

#### `audit` — View audit log

```bash
python backend_scripts/admin_cli.py audit --limit 20 --verbose
```

#### `export` — Export registry (redacted)

```bash
python backend_scripts/admin_cli.py export backup.json --product bits_whisperer
```

Exports the registry with keys and signatures redacted.

#### `expire` — Mark expired keys

```bash
python backend_scripts/admin_cli.py expire
```

Scans for annual keys past their expiry date and marks them expired.

#### `update-manifest` — Regenerate manifest

```bash
python backend_scripts/admin_cli.py update-manifest
```

______________________________________________________________________

## WordPress Plugin Administration

### Installation

1. Copy `wordpress/bits-registration/` to
   `/wp-content/plugins/bits-registration/` on your WordPress site.
2. Activate via **Plugins → Installed Plugins**.
3. Navigate to **Settings → BITS Registration**.

### Configuration

#### GitHub Personal Access Token

Create a fine-grained PAT on GitHub with:

- **Repository access**: Select the registry repo only
- **Permissions**: Actions → Read and write

Paste the token into the **GitHub Personal Access Token** field.

#### Product mapping

Map WooCommerce product IDs to key types. Add one mapping per line:

```text
42=annual
43=lifetime
44=contributor
```

Where `42`, `43`, `44` are the WooCommerce product IDs (visible in
the product edit URL: `?post=42`).

### How it works

1. Customer purchases a mapped WooCommerce product.
2. When order status changes to **Processing** or **Completed**, the
   plugin triggers a `workflow_dispatch` event on the registry repo.
3. The `manual_issue.yml` workflow runs and issues the key.
4. The key appears in:
   - Order notes (customer-visible)
   - Order confirmation email
   - **My Account → Licence Keys** page

### Customer experience

- Customers see a **Licence Keys** tab in their WooCommerce My Account.
- Each key shows: value, type, status, issue date, expiry date.
- Activation instructions are displayed below the keys table.

### Admin features

- **Orders list**: A "Licence" column shows a checkmark for orders
  with issued keys.
- **Settings page**: Shows licence statistics (count by status).
- **Duplicate prevention**: Keys are only issued once per order
  (tracked via `_bits_keys_issued` meta).

______________________________________________________________________

## GitHub Actions Workflows

### daily_sync.yml

**Schedule**: Daily at midnight UTC (also manually triggerable).

**Actions**:

1. Runs `admin_cli.py expire` to mark expired annual keys.
2. Runs `groupsio_sync.py` to issue lifetime keys for new members.
3. Regenerates `public_manifest.json`.
4. Commits and pushes changes.

**Required secrets**:

- `BITS_PRIVATE_KEY_BASE64` — Ed25519 private key
- `GROUPSIO_API_KEY` — Groups.io REST API key
- `GROUPSIO_GROUP_NAME` — Groups.io group identifier

### manual_issue.yml

**Trigger**: Manual via GitHub Actions UI or `workflow_dispatch` API.

**Inputs**: `email`, `product_id`, `key_type`.

**Actions**:

1. Runs `admin_cli.py issue` with the provided inputs.
2. Regenerates the manifest.
3. Commits and pushes.

**Required secrets**: `BITS_PRIVATE_KEY_BASE64`.

### register_device.yml

**Trigger**: `repository_dispatch` event (type: `register-device`).

**Payload**: `token_hash`, `device_id`, `timestamp`, `request_hash`.

**Actions**:

1. Runs `register_device.py` with anti-replay validation.
2. Regenerates the manifest.
3. Commits and pushes.

**Required secrets**: `BITS_PRIVATE_KEY_BASE64`.

______________________________________________________________________

## Groups.io Membership Sync

BITS members (via the Groups.io mailing list) receive **free lifetime**
licences. The `daily_sync.yml` workflow fetches the member list and
issues lifetime keys automatically.

### Setup

1. Obtain a Groups.io API key from your group's admin settings.
2. Add secrets to the registry repo:
   - `GROUPSIO_API_KEY` — your API key
   - `GROUPSIO_GROUP_NAME` — your group name (e.g., `bits-users`)
3. The sync runs daily and is idempotent — existing keys are
   upgraded to lifetime if they were previously annual.

### Manual sync

```bash
GROUPSIO_API_KEY=... GROUPSIO_GROUP_NAME=... \
  python backend_scripts/groupsio_sync.py
```

______________________________________________________________________

## Security Operations

### Revoking a compromised key

```bash
python backend_scripts/admin_cli.py revoke user@example.com bits_whisperer \
  --reason "Key compromised - shared publicly"
python backend_scripts/admin_cli.py update-manifest
git add . && git commit -m "Revoke compromised key" && git push
```

The key hash is added to the revocation list and will be blocked
within 24 hours (or immediately when the user's app next checks).

### Rotating the signing key

1. Generate a new key pair:
   `python backend_scripts/key_generator.py`
2. Update `BITS_PRIVATE_KEY_BASE64` secret in the registry repo.
3. Update `BITS_PUBLIC_KEY_BASE64` in the BITS Whisperer app code.
4. Re-sign all existing keys:
   `python backend_scripts/admin_cli.py list` (get all emails)
   Then re-issue each key to generate new signatures.
5. Regenerate the manifest.
6. Release a new BITS Whisperer build with the updated public key.

**Important**: Old app versions will fail signature verification
after key rotation. Plan a transition period.

### Audit log review

The audit log (`audit_log.json`) records all state-changing operations:

- `KEY_ISSUED` — new key created
- `KEY_UPGRADED` — existing key type changed
- `KEY_REVOKED` — key revoked by admin
- `DEVICES_RESET` — device list cleared
- `DEVICE_REGISTERED` — new device added
- `DEVICE_LIMIT_EXCEEDED` — registration blocked (device limit reached)
- `DEVICE_REG_FAILED` — device registration failed validation

Review regularly for suspicious activity.

### Backup

Export a redacted backup weekly:

```bash
python backend_scripts/admin_cli.py export backup_$(date +%Y%m%d).json
```

The export excludes raw keys and signatures. The full `tokens.json`
is version-controlled in the private repo (Git history serves as
a complete backup).

______________________________________________________________________

## Licensing Configuration

The BITS Whisperer app reads licensing parameters from
`feature_flags.json` in the main repository. These values are fetched
remotely and cached for 24 hours, allowing you to adjust licensing
behaviour without releasing a new app build.

### Configuration fields

| Field                   | Type   | Default            | Description                                         |
| ----------------------- | ------ | ------------------ | --------------------------------------------------- |
| `trial_days`            | int    | 7                  | Length of the free trial period (days)               |
| `offline_grace_days`    | int    | 30                 | Days the app works offline after last verification   |
| `reverify_hours`        | int    | 24                 | Hours between online re-verification checks          |
| `trial_warning_days`    | int    | 2                  | Days before trial expiry to show a warning           |
| `max_devices`           | int    | 3                  | Maximum device activations per licence key           |
| `admin_message`         | string | `""`               | Banner message shown to all users (empty = hidden)   |
| `purchase_url`          | string | `""`               | URL for purchasing a licence (shown in trial UI)     |
| `trial_extension_days`  | int    | 0                  | Bonus days added to every trial (global extension)   |
| `grace_mode_enabled`    | bool   | false              | Enable read-only grace period after expiry           |
| `grace_mode_days`       | int    | 7                  | Duration of the grace period (days)                  |
| `tier_names`            | dict   | See below          | Display names for each licence status code           |

Default tier names:

```json
{
  "L": "Lifetime Member",
  "A": "Active Membership",
  "C": "Paying Contributor",
  "T": "Alpha Tester"
}
```

### Changing a value

Edit `feature_flags.json` in the main BITS Whisperer repository,
commit, and push. All deployed app instances will pick up the change
within 24 hours (or on next restart).

Example — increase device limit to 5:

```json
"licensing": {
  "max_devices": 5
}
```

Example — broadcast a maintenance message:

```json
"licensing": {
  "admin_message": "Server maintenance scheduled for 10 PM UTC tonight."
}
```

Example — extend all trials by 3 days:

```json
"licensing": {
  "trial_extension_days": 3
}
```

### Primary CLI (tools/bits_admin)

The primary admin CLI in `tools/bits_admin/` includes a full
`licensing` subcommand group for managing these fields:

```bash
python -m tools.bits_admin licensing show              # Show all config
python -m tools.bits_admin licensing set max_devices 5  # Set a field
python -m tools.bits_admin licensing broadcast "msg"    # Set admin message
python -m tools.bits_admin licensing extend-trials 3    # Set trial extension
python -m tools.bits_admin licensing grace-mode enable  # Enable grace mode
python -m tools.bits_admin licensing tiers show         # Show tier names
```

______________________________________________________________________

## Troubleshooting

### Customer says "Unregistered / Guest"

1. Look up their key:
   `python backend_scripts/admin_cli.py lookup --email user@example.com`
2. If no key exists, check WooCommerce order status.
3. If key exists but status is `expired`, renew:
   `python backend_scripts/admin_cli.py issue user@example.com --type annual`
4. If key is `active`, check device count (they may have hit the
   device limit — configurable in `feature_flags.json`, default 3):
   `python backend_scripts/admin_cli.py reset-devices user@example.com bits_whisperer`
5. Ask the user to go to **Settings → General → BITS Registration**
   and click **Verify** to force a fresh check.

### Customer says "Key Pending Verification..."

- They have a key stored locally but it hasn't been verified online.
- Check internet connectivity.
- Check that `public_manifest.json` in the registry repo is up to
  date: `python backend_scripts/admin_cli.py update-manifest`
- Ensure the manifest URL in the app matches the repo URL.

### GitHub workflow fails

- Check the repository Actions tab for error logs.
- Verify all secrets are set: `BITS_PRIVATE_KEY_BASE64`,
  `GROUPSIO_API_KEY`, `GROUPSIO_GROUP_NAME`.
- Ensure the PAT has **Actions: write** and **Contents: write**
  permissions.

### WordPress plugin doesn't issue keys

- Verify the GitHub PAT in **Settings → BITS Registration**.
- Check that the product-to-key-type mapping includes the purchased
  product ID.
- Review the WordPress error log (`wp-content/debug.log`) for
  "BITS Registration" entries.
- Ensure the order status reaches **Processing** or **Completed**.
