# BITS Whisperer Registration System

Comprehensive reference for the BITS Whisperer registration, licensing,
and activation system. Covers architecture, user flows, admin tooling,
backend infrastructure, security layers, and remote configuration.

---

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Activation flow](#activation-flow)
- [Activation modes](#activation-modes)
- [User activation paths](#user-activation-paths)
  - [Free trial](#free-trial)
  - [Registration key](#registration-key)
  - [BITS member verification](#bits-member-verification)
  - [Beta invitation](#beta-invitation)
  - [Alpha tester bypass](#alpha-tester-bypass)
- [Security layers](#security-layers)
- [Credential storage](#credential-storage)
- [Remote licensing configuration](#remote-licensing-configuration)
- [Grace mode](#grace-mode)
- [Client-side components](#client-side-components)
  - [Registration service](#registration-service)
  - [Member verification service](#member-verification-service)
  - [Beta service](#beta-service)
  - [Welcome dialog](#welcome-dialog)
  - [Licence dialog](#licence-dialog)
- [Admin CLI](#admin-cli)
  - [Key management](#key-management)
  - [Beta invitation management](#beta-invitation-management)
  - [Licensing configuration](#licensing-configuration)
  - [Bulk CSV operations](#bulk-csv-operations)
  - [Cryptographic operations](#cryptographic-operations)
- [Backend infrastructure](#backend-infrastructure)
  - [Registry repository](#registry-repository)
  - [Public manifest](#public-manifest)
  - [Device registration](#device-registration)
  - [Groups.io membership sync](#groupsio-membership-sync)
  - [GitHub Actions workflows](#github-actions-workflows)
- [WordPress integration](#wordpress-integration)
- [Status codes and tier names](#status-codes-and-tier-names)
- [Setting up the registration system](#setting-up-the-registration-system)
- [Troubleshooting](#troubleshooting)

---

## Overview

The registration system manages product activation, trial periods, beta
invitations, BITS membership verification, and licence key issuance for
BITS Whisperer. It runs at zero cost on GitHub infrastructure and the OS
credential store.

Key design principles:

- **Zero-cost infrastructure** - GitHub repository as the database,
  GitHub Actions as the backend, no paid hosting required.
- **Cryptographic security** - Ed25519 digital signatures on every
  licence blob, SHA-256 hashed keys, HMAC-protected trial dates.
- **Remote control** - Administrators adjust trial length, device limits,
  activation mode, broadcast messages, and tier names by editing a
  single JSON file. No code changes or user action required.
- **Privacy-first** - API keys and registration data stored in the OS
  credential store (Windows Credential Manager or macOS Keychain).
  Raw keys never appear in the public manifest.
- **Offline-capable** - Clients work offline for a configurable grace
  period (default 30 days) after the last successful verification.

---

## Architecture

The system has four components.

**1. Registry repository** (private GitHub repo)

Stores `tokens.json` (the key database), `audit_log.json`, `revoked_keys.json`,
and `public_manifest.json`. GitHub Actions workflows handle device registration,
daily membership sync, and manifest regeneration.

**2. Backend scripts** (`BITS_Registration/backend_scripts/`)

Python scripts executed by GitHub Actions or locally by administrators:
`registry_manager.py`, `manifest_generator.py`, `key_generator.py`,
`register_device.py`, `groupsio_sync.py`, and `admin_cli.py`.

**3. WordPress plugin** (`bits-registration.php`)

Optional WooCommerce integration that automatically issues licence keys
after payment. Triggers GitHub Actions workflows via `repository_dispatch`.

**4. BITS Whisperer client**

The desktop application contains the registration service, member
verification service, beta service, key store, feature flag service,
welcome dialog, and licence dialog.

Data flow for a typical activation:

1. User enters a registration key in the welcome dialog.
2. The client hashes the key with SHA-256 and queries the public manifest
   on GitHub (`public_manifest.json`).
3. The manifest returns the signed licence blob and the device list.
4. The client verifies the Ed25519 signature using the embedded public key.
5. If valid and the device limit is not exceeded, the client registers the
   device via a `repository_dispatch` event to GitHub Actions.
6. GitHub Actions runs `register_device.py`, adds the device ID to the
   registry, and regenerates the manifest.
7. The client stores the registration key, status, and name in the OS
   credential store.

---

## Activation flow

On every application startup, `app.py` runs the activation gate:

1. Create a `KeyStore` and `FeatureFlagService`.
2. Refresh feature flags from the remote `feature_flags.json` (or cache).
3. Create `BITS_RegistrationService` with the key store and feature flags.
4. Call `needs_activation()`.
5. If activation is needed, show the `WelcomeDialog` with tabs gated by
   `activation_mode`.
6. If the user exits, the application closes. Otherwise the main window
   opens.

The `needs_activation()` method checks bypass conditions in order,
respecting the remote `activation_mode`. See the next section for
details.

---

## Activation modes

The `activation_mode` field in `feature_flags.json` controls which
activation paths are available. Administrators change this value to
transition between rollout phases.

| Mode | Bypasses allowed | Welcome dialog tabs shown | Use case |
|---|---|---|---|
| `closed` | None | All tabs hidden, only Exit button | Emergency lockdown or pre-launch |
| `beta` | Registration key, beta invitation, alpha tester | Beta Tester only | Beta testing phase |
| `live` | All: trial, registration key, BITS member, beta, alpha | All five tabs | General availability |

Bypass evaluation order in `needs_activation()`:

```text
closed --> always needs activation (no bypasses)

beta --> registration_key? --> NO activation needed
     --> beta_invitation_hash? --> NO activation needed
     --> registration_status == "T"? --> NO activation needed
     --> otherwise --> needs activation

live  --> registration_key? --> NO activation needed
      --> beta_invitation_hash? --> NO activation needed
      --> registration_status == "T"? --> NO activation needed
      --> is_trial_active()? --> NO activation needed
      --> member_email_hash? --> NO activation needed
      --> otherwise --> needs activation
```

To transition from beta to general availability, change
`"activation_mode": "beta"` to `"activation_mode": "live"` in
`feature_flags.json` and push to the main branch. All deployed instances
pick up the change within 24 hours (the feature flag cache TTL) or on
the next application restart.

---

## User activation paths

### Free trial

Available in **live** mode only.

1. User navigates to the Free Trial tab in the welcome dialog.
2. Enters their full name and email address.
3. The device ID (multi-factor hardware fingerprint) is displayed
   read-only with a Copy button.
4. Clicks "Start 7-Day Trial".
5. The registration service stores the trial start date (ISO 8601),
   an HMAC-SHA256 integrity hash, the user's name, and email in the
   OS credential store.
6. The dialog closes and the application launches.

Trial protection:

- The trial start date is protected by HMAC-SHA256 using device-specific
  key material. Editing the date in the credential store invalidates the
  HMAC and the trial is treated as tampered (inactive).
- Trial length is remotely configurable via `trial_days` and
  `trial_extension_days` in `feature_flags.json`.
- When the trial has `trial_warning_days` or fewer days remaining, a
  gentle reminder is shown.
- A trial can only be started once per device. Attempting to start a
  second trial shows "Trial Unavailable".

### Registration key

Available in **beta** and **live** modes.

1. User navigates to the Register tab.
2. Enters their registration key (masked input).
3. Clicks "Register".
4. The client validates the key format (base64-safe, minimum 32
   characters).
5. Stores the key and calls `verify_key(force=True)`.
6. Verification hashes the key, queries the public manifest, checks the
   Ed25519 signature, and enforces the 3-device limit.
7. On success, stores name, status, email, and verified timestamp.
8. The dialog closes and the application launches.

### BITS member verification

Available in **live** mode only.

BITS members with a `@bitsusers.org` email address receive free lifetime
access. The OTP verification provides immediate access without waiting
for the daily Groups.io sync to issue a formal Ed25519-signed key.

1. User navigates to the BITS Member tab.
2. Enters their `@bitsusers.org` email address.
3. Clicks "Send Verification Code".
4. The client validates the email domain and generates a 6-digit OTP
   (cryptographically random, 1 000 000 combinations).
5. The OTP hash (HMAC-SHA256 with email-bound key material) is stored
   in memory with a 10-minute expiry.
6. The OTP is relayed to the backend for email delivery.
7. OTP entry and Verify button become enabled.
8. User enters the 6-digit code and clicks "Verify Code".
9. The client validates the OTP against the stored hash.
10. On success, stores a SHA-256 hash of the normalised email in the
    OS credential store (`member_email_hash`).
11. The dialog closes and the application launches.

The daily `groupsio_sync.py` script later issues a formal Ed25519-signed
lifetime registration key for the member, upgrading them from OTP-based
access to full cryptographic verification.

### Beta invitation

Available in **beta** and **live** modes.

1. User navigates to the Beta Tester tab.
2. Enters their beta invitation code (format: `BETA-XXXX-XXXX-XXXX`).
3. Clicks "Verify Invitation".
4. The beta service hashes the code with SHA-256 and checks it against
   the remote `beta_invitations.json`.
5. On success, stores the invitation hash in the OS credential store
   and enables beta mode.
6. The dialog closes and the application launches.

### Alpha tester bypass

Available in **beta** and **live** modes.

Alpha testers have `registration_status` set to `"T"` in the credential
store. This is set by `set_alpha_mode(enabled=True)` on the registration
service. Alpha testers bypass the activation gate without needing a
registration key or beta invitation.

---

## Security layers

The system implements seven security layers.

**1. Ed25519 cryptographic signatures**

Every licence blob is signed with the project's Ed25519 private key.
The client embeds the public key and verifies signatures locally. The
signed payload includes email, product ID, key type, expiry, issuance
timestamp, and schema version. Tampering with any field invalidates the
signature.

**2. Anti-replay timestamps**

Signed licence blobs include an issuance timestamp (`i` field). This
prevents old or revoked signatures from being replayed.

**3. SHA-256 hashing**

Raw registration keys never appear in the public manifest. Only SHA-256
hashes are published. The client hashes the user's key locally and looks
up the hash in the manifest.

**4. HMAC-SHA256 trial integrity**

Trial start dates are protected by HMAC-SHA256 using device-specific key
material. Directly editing the `trial_start_date` entry in the
credential store invalidates the HMAC, and the trial is treated as
expired.

**5. Device limit**

Each registration key is limited to a configurable number of concurrent
device activations (default 3, adjustable via `max_devices` in
`feature_flags.json`). The device list is stored in the registry and
embedded in the manifest.

**6. Revocation list**

Revoked key hashes are embedded in the public manifest (`_revoked`
array). Clients check the revocation list during verification and
immediately block revoked keys.

**7. Rate limiting and offline grace**

The client limits online verification to once per 60 seconds
(`_MIN_VERIFICATION_INTERVAL`). Cached verifications remain trusted for
a configurable offline grace period (default 30 days). Re-verification
is required every `reverify_hours` (default 24) when online.

---

## Credential storage

All registration data is stored in the OS credential store via the
`keyring` library, under the service name `"BITS Whisperer"`.

The key store manages 33 named entries.

**Transcription provider keys (16 entries):**
`openai`, `google`, `azure`, `azure_region`, `deepgram`, `assemblyai`,
`gemini`, `aws_access_key`, `aws_secret_key`, `aws_region`, `groq`,
`rev_ai`, `speechmatics`, `elevenlabs`, `auphonic`,
`mai_transcribe_region`.

**AI service keys (5 entries):**
`anthropic`, `azure_openai`, `azure_openai_endpoint`,
`azure_openai_deployment`, `copilot_github_token`.

**Registration and trial entries (10 entries):**
`registration_key`, `registration_status`, `registration_name`,
`registration_email`, `registration_install_count`,
`registration_verified_at`, `trial_start_date`, `trial_hmac`,
`trial_name`, `trial_email`.

**Beta and membership entries (2 entries):**
`beta_invitation_hash`, `member_email_hash`.

---

## Remote licensing configuration

The `licensing` section of `feature_flags.json` provides remotely
adjustable parameters. Changes take effect within 24 hours (the cache
TTL) or on the next application restart.

| Field | Type | Default | Description |
|---|---|---|---|
| `activation_mode` | string | `"beta"` | Controls which activation paths are available (`closed`, `beta`, `live`) |
| `trial_days` | integer | 7 | Free trial length in days |
| `trial_extension_days` | integer | 0 | Global bonus days added to all active trials |
| `trial_warning_days` | integer | 2 | Show warning when this many days or fewer remain |
| `offline_grace_days` | integer | 30 | Cached verification stays trusted this long offline |
| `reverify_hours` | integer | 24 | Re-verification interval when online |
| `max_devices` | integer | 3 | Maximum concurrent device activations per key |
| `admin_message` | string | `""` | System-wide broadcast banner in the licence dialog |
| `purchase_url` | string | `""` | Remotely updatable purchase and renewal page URL |
| `grace_mode_enabled` | boolean | `false` | Enable read-only grace mode after expiry |
| `grace_mode_days` | integer | 7 | Duration of read-only grace period |
| `tier_names` | object | See below | Human-readable display names for status codes |

Default tier names:

| Code | Default name |
|---|---|
| L | Lifetime Member |
| A | Active Membership |
| C | Paying Contributor |
| T | Alpha Tester |

---

## Grace mode

When `grace_mode_enabled` is `true`, expired trials and lapsed licences
enter a read-only grace period instead of a hard lockout.

During grace mode:

- The application launches normally.
- All features remain visible but write operations (new transcriptions)
  may be restricted at the UI level.
- A banner shows the number of grace days remaining.
- After `grace_mode_days` expire, the welcome dialog appears on the next
  startup.

---

## Client-side components

### Registration service

**Module:** `core/registration_service.py`

The `BITS_RegistrationService` class manages all activation logic. It
accepts a `KeyStore` for credential persistence and an optional
`FeatureFlagService` for remote configuration.

Public API:

| Method | Description |
|---|---|
| `needs_activation()` | Returns `True` if the activation gate should be shown |
| `activation_mode` | Property returning the current mode (`beta`, `live`, `closed`) |
| `start_trial(name, email)` | Activate a free trial with HMAC protection |
| `is_trial_active()` | Check whether the trial is valid and not expired |
| `get_trial_days_remaining()` | Days left in the trial (0 if expired) |
| `is_trial_expiring_soon()` | Whether the trial warning threshold is reached |
| `verify_key(force)` | Verify registration key against the public manifest |
| `is_valid_key_format(key)` | Static check for base64-safe format, minimum 32 characters |
| `get_device_id()` | Multi-factor hardware fingerprint (MAC, hostname, CPU, profile) |
| `revoke_device()` | Clear local registration and request slot release |
| `is_registered()` | Whether a valid registration key is stored |
| `get_registered_name()` | Cached display name from the licence token |
| `get_status_message()` | Human-readable membership status |
| `is_in_grace_mode()` | Whether the user is in the read-only grace period |
| `get_admin_message()` | Current broadcast message (may be empty) |
| `set_alpha_mode(enabled)` | Enable or disable alpha testing mode |

### Member verification service

**Module:** `core/member_verification.py`

The `MemberVerificationService` class handles OTP-based email
verification for BITS members with `@bitsusers.org` addresses.

Public API:

| Method | Description |
|---|---|
| `is_member_email(email)` | Static check for `@bitsusers.org` domain |
| `is_already_verified()` | Whether a member hash is stored |
| `get_verified_email()` | The verified email address (or empty) |
| `request_verification(email)` | Generate a 6-digit OTP (raises `ValueError` for non-member emails) |
| `verify_otp(email, otp)` | Validate the OTP and store the member hash |
| `send_otp_to_backend(email, otp)` | Relay the OTP to the backend for email delivery |
| `revoke_member_verification()` | Clear the stored member hash |

Constants:

- `MEMBER_DOMAIN = "bitsusers.org"`
- `OTP_LENGTH = 6` digits
- `OTP_EXPIRY_SECONDS = 600` (10 minutes)

### Beta service

**Module:** `core/beta_service.py`

The `BetaService` class manages beta programme invitations and the
What's New change detection system.

Public API:

| Method | Description |
|---|---|
| `is_beta_tester` | Property: verified invitation AND beta-enabled, or alpha mode |
| `is_alpha_tester` | Property: alpha testing mode active |
| `is_invitation_verified` | Property: whether any invitation has been verified |
| `verify_invitation(code)` | Verify a code against the remote invitation list |
| `set_beta_enabled(enabled)` | Update the beta-enabled flag |
| `set_alpha_mode(enabled)` | Enable or disable alpha testing |
| `hash_code(code)` | Static SHA-256 hash of an invitation code |
| `revoke_beta()` | Clear stored invitation and disable beta mode |

### Welcome dialog

**Module:** `ui/welcome_dialog.py`

The `WelcomeDialog` is a tabbed `wx.Dialog` shown at startup when
`needs_activation()` returns `True`. Tab visibility is controlled by
`activation_mode`.

Return codes:

| Code | Constant | Meaning |
|---|---|---|
| `wx.ID_YES` | `WELCOME_TRIAL` | Trial started |
| `wx.ID_APPLY` | `WELCOME_REGISTER` | Registration key entered and verified |
| `wx.ID_MORE` | `WELCOME_MEMBER` | BITS member email verified |
| `wx.ID_FORWARD` | `WELCOME_BETA` | Beta invitation verified |
| `wx.ID_EXIT` | `WELCOME_EXIT` | User chose to quit |

Accessibility: every control has `SetName()`, all panels use
`wx.TAB_TRAVERSAL`, email validation uses a compiled regex pattern,
all message boxes use `accessible_message_box()` for screen reader
compatibility.

### Licence dialog

**Module:** `ui/license_dialog.py`

The `LicenseDialog` is accessible from the main menu after activation.
It displays the current licence status, registered name, email,
installation count, last verification time, and tier name. Action
buttons allow registering a new key, opening the purchase page, or
revoking the current device.

---

## Admin CLI

**Module:** `tools/bits_admin/`

The admin CLI (`python -m tools.bits_admin`) provides commands for
managing the registration system from the command line.

### Key management

**Module:** `tools/bits_admin/registry.py`

Issue, renew, list, look up, and revoke registration keys.

```text
bits_admin keys issue user@example.com --type lifetime
bits_admin keys issue user@example.com --type annual --duration 2y
bits_admin keys list --status active
bits_admin keys lookup --email user@example.com
bits_admin keys revoke user@example.com --reason "Refund requested"
bits_admin keys reset-devices user@example.com
```

Key types:

| Type | Status code | Duration |
|---|---|---|
| `lifetime` | L | No expiry |
| `annual` | A | 365 days |
| `multi_year` | A | 730 days (or custom) |
| `contributor` | C | No expiry |

Key sources: `member`, `paid`, `contributor`, `admin`,
`groupsio_sync`, `beta`, `promotional`.

The registry entry data model (`RegistryEntry`) stores email, key,
token hash, product ID, key type, source, expiry, status, device list,
signed licence blob, timestamps, issuer, name, payment reference, notes,
and duration.

### Beta invitation management

**Module:** `tools/bits_admin/beta.py`

Generate, add, list, and revoke beta invitation codes.

```text
bits_admin beta generate --count 5 --prefix BETA
bits_admin beta generate --count 1 --email user@example.com --name "Tester"
bits_admin beta list
bits_admin beta revoke <code_hash>
```

Invitation code format: `PREFIX-XXXX-XXXX-XXXX` (16 random alphanumeric
characters). Codes are stored as SHA-256 hashes in
`beta_invitations.json`.

### Licensing configuration

**Module:** `tools/bits_admin/licensing.py`

Read and write the `licensing` section of `feature_flags.json`.

```text
bits_admin licensing get
bits_admin licensing set trial_days 14
bits_admin licensing set activation_mode live
bits_admin licensing set admin_message "Maintenance scheduled for Sunday"
bits_admin licensing set-tier L "Lifetime Supporter"
```

All fields are type-validated before writing. Boolean fields accept
`true`, `false`, `yes`, `no`, `1`, `0`.

### Bulk CSV operations

**Module:** `tools/bits_admin/csv_ops.py`

Import and export registration data in CSV format with flexible column
mapping.

```text
bits_admin csv-import members.csv --key path/to/private.key
bits_admin csv-export --output registry.csv
```

Supported column aliases (auto-detected from headers):

- Email: `email`, `e-mail`, `email_address`, `user_email`
- Name: `name`, `full_name`, `display_name`, `user_name`
- Key type: `type`, `key_type`, `license_type`, `tier`
- Source: `source`, `origin`, `channel`, `acquisition`
- Duration: `duration`, `duration_days`, `days`, `validity`
- Payment: `payment`, `invoice`, `transaction`, `order_id`
- Notes: `notes`, `note`, `comment`, `memo`

Duration values accept formats like `2y`, `18months`, `365`.

### Cryptographic operations

**Module:** `tools/bits_admin/crypto.py`

```text
bits_admin keygen
```

Generates an Ed25519 key pair. The private key is stored as a GitHub
repository secret (`BITS_PRIVATE_KEY_BASE64`). The public key is
embedded in the BITS Whisperer application source code.

Functions: `generate_keypair()`, `sign_license()`, `verify_signature()`,
`sha256_hex()`, `sha256_normalised()`, `generate_registration_key()`.

---

## Backend infrastructure

### Registry repository

A private GitHub repository stores the registration database. Required
files:

- `tokens.json` - Registration key database (array of `RegistryEntry`)
- `audit_log.json` - Administrative action log (capped at 10 000 entries)
- `revoked_keys.json` - Revoked key hashes with reasons and timestamps
- `public_manifest.json` - Public-facing manifest (only hashes, no raw keys)

### Public manifest

Generated by `manifest_generator.py`. Contains only active, non-expired,
non-revoked entries. Structure:

```json
{
  "_meta": {"generated_at": "2026-04-05T12:00:00Z", "version": 2},
  "_revoked": ["<hash1>", "<hash2>"],
  "bits_whisperer": {
    "<token_hash>": {
      "s": "<signed_licence_blob>",
      "d": ["<device_id_1>", "<device_id_2>"],
      "u": "2026-04-05"
    }
  }
}
```

The manifest is hosted via GitHub raw content URLs and cached by the
client with a 24-hour TTL.

### Device registration

When a client activates a registration key, it sends a
`repository_dispatch` event to the registry repository. The
`register-device.yml` GitHub Actions workflow runs `register_device.py`,
which:

1. Validates the request age (maximum 5 minutes, anti-replay).
2. Checks the request hash for integrity.
3. Verifies the token hash exists and is not revoked.
4. Checks the device limit (configurable, default 3).
5. Adds the device ID to the registry entry.
6. Regenerates the public manifest.

### Groups.io membership sync

The `groupsio_sync.py` script runs daily via the `daily_sync.yml`
GitHub Actions workflow. It:

1. Fetches all member emails from the configured Groups.io group
   (paginated, 100 per page).
2. For each member without a registration key, issues a **lifetime**
   Ed25519-signed key with source `groupsio_sync`.
3. For existing members with non-lifetime keys, upgrades them to
   lifetime.
4. Regenerates the public manifest.

Environment variables: `GROUPSIO_API_KEY`, `GROUPSIO_GROUP_NAME`,
`BITS_PRIVATE_KEY_BASE64`.

### GitHub Actions workflows

| Workflow | Trigger | Script | Purpose |
|---|---|---|---|
| `register-device.yml` | `repository_dispatch` | `register_device.py` | Register a device against a key |
| `daily_sync.yml` | Scheduled (daily) | `groupsio_sync.py` | Sync Groups.io members to lifetime keys |
| `issue-key.yml` | `repository_dispatch` | `registry_manager.py` | Issue a key after WooCommerce payment |

---

## WordPress integration

**Plugin:** `BITS Registration for WooCommerce` (`bits-registration.php`)

The WordPress plugin automatically issues licence keys when a
WooCommerce order is completed. It requires PHP 8.1+, WordPress 6.0+,
and WooCommerce 8.0+.

Settings (under wp-admin, Settings):

- **GitHub Token** - Fine-grained PAT with "Actions: write" scope on
  the registry repository.
- **Product Map** - Textarea mapping WooCommerce product IDs to key
  types (one per line, format: `product_id=key_type`).

Database table (`wp_bits_licence_keys`):

| Column | Type | Description |
|---|---|---|
| `order_id` | BIGINT | WooCommerce order ID |
| `user_id` | BIGINT | WordPress user ID |
| `email` | VARCHAR(255) | Customer email |
| `product_id` | VARCHAR(64) | BITS product identifier |
| `key_type` | VARCHAR(32) | Key type (`annual`, `lifetime`, etc.) |
| `licence_key` | VARCHAR(255) | The issued registration key |
| `status` | VARCHAR(32) | `pending`, `active`, `revoked` |
| `issued_at` | DATETIME | When the key was issued |
| `expires_at` | DATETIME | Expiry date (null for lifetime) |

---

## Status codes and tier names

| Code | Default display name | Issued by | Expiry |
|---|---|---|---|
| L | Lifetime Member | Groups.io sync or admin | Never |
| A | Active Membership | WooCommerce or admin | Annual or multi-year |
| C | Paying Contributor | Admin | Never |
| T | Alpha Tester | `set_alpha_mode(True)` | Never |

Tier display names are remotely configurable via the `tier_names` field
in `feature_flags.json`.

---

## Setting up the registration system

This section walks through the complete setup process, from generating
cryptographic keys to issuing your first licence. For the full
step-by-step deployment checklist, see the
[Deployment Guide](../BITS_Registration/DEPLOYMENT_GUIDE.md).

### Prerequisites

| Requirement | Details |
|---|---|
| Python 3.13+ | On the machine where you run admin scripts |
| `cryptography` package | `pip install cryptography requests` |
| GitHub organisation | Owner access to create a private registry repo |
| Groups.io API key | From your group's admin, API Keys page (optional, for membership sync) |
| WordPress with WooCommerce | For automated key issuance after payment (optional) |
| GitHub PAT (fine-grained) | Scoped to the registry repo, Actions read and write |

### Step 1: Generate an Ed25519 key pair

The key pair secures every licence token. The private key signs tokens;
the public key is embedded in the application for verification.

```bash
cd BITS_Registration/backend_scripts
pip install cryptography
python key_generator.py
```

Output:

```text
=== BITS Registration Key Pair Generator ===

Private key (base64): MC4CAQ...
Public key (base64):  MCowBQ...
```

Save both values securely. The private key becomes a GitHub Actions
secret. The public key is embedded in
`src/bits_whisperer/core/registration_service.py` as
`BITS_PUBLIC_KEY_BASE64`.

Never commit or share the private key.

### Step 2: Create the private registry repository

1. Create a new **private** GitHub repository (for example,
   `bits-whisperer-registry`).
2. Clone it locally and copy the backend scripts into it:

   ```bash
   git clone git@github.com:your-org/bits-whisperer-registry.git
   cd bits-whisperer-registry
   cp -r /path/to/bits-whisperer/BITS_Registration/backend_scripts/ .
   cp /path/to/bits-whisperer/BITS_Registration/setup_backend.py .
   ```

3. Run first-time setup to create the initial data files:

   ```bash
   python setup_backend.py
   ```

   This creates `tokens.json`, `audit_log.json`, `revoked_keys.json`,
   and `.gitignore`.

4. Commit and push:

   ```bash
   git add -A
   git commit -m "Initial backend setup"
   git push
   ```

### Step 3: Configure GitHub secrets

In the registry repository, go to **Settings, Secrets and variables,
Actions** and add:

| Secret name | Value |
|---|---|
| `BITS_PRIVATE_KEY_BASE64` | Ed25519 private key from step 1 |
| `GROUPSIO_API_KEY` | Groups.io REST API key (optional) |
| `GROUPSIO_GROUP_NAME` | Groups.io group identifier (optional) |

### Step 4: Deploy GitHub Actions workflows

Copy the workflow files from the main repository into the registry
repository:

```bash
mkdir -p .github/workflows
cp /path/to/bits-whisperer/BITS_Registration/.github/workflows/*.yml \
   .github/workflows/
git add .github/workflows/
git commit -m "Add GitHub Actions workflows"
git push
```

Three workflows are deployed:

| Workflow | Trigger | Purpose |
|---|---|---|
| `register-device.yml` | `repository_dispatch` | Register a device against a licence key |
| `daily_sync.yml` | Scheduled (daily, midnight UTC) | Sync Groups.io members to lifetime keys |
| `issue-key.yml` | `repository_dispatch` | Issue a key after WooCommerce payment |

Enable the daily sync workflow from the Actions tab after deployment.

### Step 5: Embed the public key in the application

Open `src/bits_whisperer/core/registration_service.py` and set:

```python
BITS_PUBLIC_KEY_BASE64 = "MCowBQ..."  # Your actual public key
```

Verify the manifest URL matches your registry repository:

```python
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "your-org/bits-whisperer-registry/"
    "main/public_manifest.json"
)
```

This is the only code change needed in the main BITS Whisperer
codebase.

### Step 6: Configure the activation mode

Edit `feature_flags.json` in the main repository to set the activation
mode and licensing parameters:

```json
{
  "licensing": {
    "activation_mode": "beta",
    "trial_days": 7,
    "max_devices": 3,
    "offline_grace_days": 30,
    "reverify_hours": 24,
    "trial_warning_days": 2,
    "trial_extension_days": 0,
    "grace_mode_enabled": false,
    "grace_mode_days": 7,
    "admin_message": "",
    "purchase_url": "",
    "tier_names": {
      "L": "Lifetime Member",
      "A": "Active Membership",
      "C": "Paying Contributor",
      "T": "Alpha Tester"
    }
  }
}
```

Start with `"activation_mode": "beta"` for testing. Change to `"live"`
when ready for general availability. See
[Activation modes](#activation-modes) for the full mode reference.

You can also set these values from the admin CLI:

```bash
python -m tools.bits_admin licensing set activation_mode beta
python -m tools.bits_admin licensing set trial_days 14
python -m tools.bits_admin licensing set max_devices 5
```

### Step 7: Issue your first test key

Use the admin CLI to issue a test registration key:

```bash
python -m tools.bits_admin keys issue test@example.com --type lifetime
```

Verify the key was created:

```bash
python -m tools.bits_admin keys lookup --email test@example.com
```

Generate the public manifest:

```bash
python -m tools.bits_admin keys list --status active
```

### Step 8: Generate beta invitations (optional)

If using beta mode, generate invitation codes for testers:

```bash
python -m tools.bits_admin beta generate --count 10 --prefix BETA
```

Codes are written to `beta_invitations.json` as SHA-256 hashes.
Distribute the plaintext codes (format: `BETA-XXXX-XXXX-XXXX`) to your
testers. They enter these in the Beta Tester tab of the welcome dialog.

### Step 9: Set up WordPress integration (optional)

If selling licences through WooCommerce:

1. Upload the `wordpress/bits-registration/` folder to
   `wp-content/plugins/` on your WordPress site.
2. Activate the plugin in **Plugins, Installed Plugins**.
3. Go to **Settings, BITS Registration** and configure:
   - **GitHub Token**: Fine-grained PAT with Actions write scope on the
     registry repo.
   - **Repository**: `your-org/bits-whisperer-registry`.
   - **Workflow filename**: `manual_issue.yml`.
   - **Product Mapping**: Map WooCommerce product IDs to key types, one
     per line (for example, `42=annual`).
4. Create a test order and verify a key appears in the order notes and
   in `tokens.json`.

### Step 10: End-to-end verification

Run through each activation path to confirm the full system works.

**Registration key test:**

1. Build BITS Whisperer with the embedded public key.
2. Launch the application. The welcome dialog should appear.
3. Enter the test key from step 7 in the Register tab.
4. The application should launch and show the registered name.

**Beta invitation test (if applicable):**

1. Enter a generated invitation code in the Beta Tester tab.
2. The application should launch with beta mode active.

**Trial test (live mode only):**

1. Set `activation_mode` to `live` in `feature_flags.json`.
2. Launch on a fresh device or clear the credential store.
3. Start a trial in the Free Trial tab.
4. Verify the trial countdown works and HMAC protection is active.

**Device limit test:**

1. Register the test key on the maximum number of devices (default 3).
2. Attempt one more registration. It should be blocked.

**Revocation test:**

```bash
python -m tools.bits_admin keys revoke test@example.com \
  --reason "End-to-end test"
```

After the next verification cycle (or forced refresh), the application
should show the key as revoked.

### Step 11: Go live checklist

- Ed25519 key pair generated and stored securely
- `BITS_PRIVATE_KEY_BASE64` secret set in the registry repo
- `setup_backend.py` run and initial files committed
- All three workflows deployed and visible in the Actions tab
- Public key embedded in `registration_service.py`
- Manifest URL matches the registry repo
- `activation_mode` set appropriately in `feature_flags.json`
- Test key issued and verified end-to-end
- Beta invitations generated (if using beta mode)
- WordPress plugin installed and configured (if selling licences)
- WooCommerce products mapped to key types (if selling licences)
- Groups.io secrets configured and daily sync enabled (if using
  membership sync)
- Device registration and revocation tested
- All test keys cleaned up from `tokens.json`

---

## Troubleshooting

**User cannot activate despite having a valid key:**
Check `activation_mode` in `feature_flags.json`. In `beta` mode, only
registration keys, beta invitations, and alpha testers bypass the gate.
Trials and BITS member verification are blocked.

**Trial appears expired immediately:**
The HMAC integrity check may have failed. This happens if the
`trial_start_date` or `trial_hmac` entries in the OS credential store
were modified externally. The user must register with a key instead.

**Device limit reached:**
The default limit is 3 devices. Use the admin CLI to reset devices:
`bits_admin keys reset-devices user@example.com`. Or increase the limit
by setting `max_devices` in `feature_flags.json`.

**BITS member OTP not received:**
Check that a `verification_url` is configured. If not configured, the
OTP is only logged for admin-assisted verification. The admin must
relay the OTP manually.

**Beta invitation code rejected:**
Verify the code has been added to `beta_invitations.json` via the admin
CLI. Codes are stored as SHA-256 hashes and the plaintext code is needed
for verification.

**Feature flags not updating:**
The client caches feature flags for 24 hours. Restart the application to
force a refresh, or wait for the cache TTL to expire.

**Grace mode not activating:**
Verify `grace_mode_enabled` is set to `true` in `feature_flags.json`.
Grace mode is disabled by default.
