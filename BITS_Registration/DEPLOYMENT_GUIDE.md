# BITS Registration System — Deployment Guide

Step-by-step instructions for deploying the BITS Registration system
from scratch. Follow these sections in order.

______________________________________________________________________

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Create the Private Registry Repository](#step-1-create-the-private-registry-repository)
3. [Step 2: Generate Ed25519 Key Pair](#step-2-generate-ed25519-key-pair)
4. [Step 3: Configure GitHub Secrets](#step-3-configure-github-secrets)
5. [Step 4: Run First-Time Setup](#step-4-run-first-time-setup)
6. [Step 5: Deploy GitHub Actions Workflows](#step-5-deploy-github-actions-workflows)
7. [Step 6: Embed the Public Key in BITS Whisperer](#step-6-embed-the-public-key-in-bits-whisperer)
8. [Step 7: Install the WordPress Plugin](#step-7-install-the-wordpress-plugin)
9. [Step 8: Configure WooCommerce Products](#step-8-configure-woocommerce-products)
10. [Step 9: End-to-End Testing](#step-9-end-to-end-testing)
11. [Step 10: Go Live Checklist](#step-10-go-live-checklist)

______________________________________________________________________

## Prerequisites

| Requirement             | Details                                      |
| ----------------------- | -------------------------------------------- |
| GitHub organisation     | Owner access to create private repos         |
| Python 3.13+            | On the machine where you run admin scripts   |
| `cryptography` package  | `pip install cryptography requests`          |
| WordPress site          | With WooCommerce active                      |
| Groups.io API key       | From your group's admin → API Keys page      |
| GitHub PAT              | Fine-grained, scoped to the registry repo    |

______________________________________________________________________

## Step 1: Create the Private Registry Repository

1. Go to **github.com → New Repository**.
2. Set:
   - **Owner**: Your GitHub organisation (e.g., `bits-whisperer`)
   - **Name**: `bits-whisperer-registry`
   - **Visibility**: **Private**
   - **Initialize**: Add a README (optional)
3. Clone locally:

   ```bash
   git clone git@github.com:bits-whisperer/bits-whisperer-registry.git
   cd bits-whisperer-registry
   ```

4. Copy backend scripts from the main repo:

   ```bash
   cp -r /path/to/bits-whisperer/BITS_Registration/backend_scripts/ .
   cp /path/to/bits-whisperer/BITS_Registration/setup_backend.py .
   ```

5. Create a `requirements.txt`:

   ```text
   cryptography>=43.0.0
   requests>=2.32.0
   ```

______________________________________________________________________

## Step 2: Generate Ed25519 Key Pair

Run the key generator on your local machine:

```bash
pip install cryptography
python backend_scripts/key_generator.py
```

This prints two base64-encoded values:

```text
=== BITS Registration Key Pair Generator ===

Private key (base64): MC4CAQ...
Public key (base64):  MCowBQ...

IMPORTANT:
  1. Store the PRIVATE key as a GitHub Actions secret
     named BITS_PRIVATE_KEY_BASE64.
  2. Embed the PUBLIC key in the BITS Whisperer app
     (registration_service.py, BITS_PUBLIC_KEY_BASE64).
  3. NEVER commit or share the private key.
```

**Save both values securely.** You will need them in the next two
steps.

______________________________________________________________________

## Step 3: Configure GitHub Secrets

Go to the registry repo → **Settings → Secrets and variables →
Actions** and add the following secrets:

| Secret Name               | Value                                       |
| ------------------------- | ------------------------------------------- |
| `BITS_PRIVATE_KEY_BASE64` | Ed25519 private key (from step 2)           |
| `GROUPSIO_API_KEY`        | Your Groups.io REST API key                 |
| `GROUPSIO_GROUP_NAME`     | Your Groups.io group identifier             |

For the WordPress plugin (optional, can be added later):

| Secret Name              | Value                                        |
| ------------------------ | -------------------------------------------- |
| No additional secrets    | The WordPress plugin uses its own PAT field  |

______________________________________________________________________

## Step 4: Run First-Time Setup

From the registry repo root:

```bash
python setup_backend.py
```

This creates the initial data files:

```text
✓ Created tokens.json
✓ Created audit_log.json
✓ Created revoked_keys.json
✓ Created .gitignore
```

Commit and push:

```bash
git add tokens.json audit_log.json revoked_keys.json .gitignore
git commit -m "Initial backend setup"
git push
```

______________________________________________________________________

## Step 5: Deploy GitHub Actions Workflows

1. Create the workflows directory:

   ```bash
   mkdir -p .github/workflows
   ```

2. Copy the three workflow files:

   ```bash
   cp /path/to/bits-whisperer/BITS_Registration/.github/workflows/*.yml \
      .github/workflows/
   ```

3. Commit and push:

   ```bash
   git add .github/workflows/
   git commit -m "Add GitHub Actions workflows"
   git push
   ```

4. Verify workflows appear in the repo's **Actions** tab.

### Test the manual issue workflow

1. Go to **Actions → Issue Licence Key (Manual)**.
2. Click **Run workflow**.
3. Enter:
   - Email: `test@example.com`
   - Product ID: `bits_whisperer`
   - Key type: `tester`
4. Click **Run workflow** and wait for completion.
5. Verify:
   - `tokens.json` has a new entry
   - `public_manifest.json` was created
   - `audit_log.json` has a `KEY_ISSUED` event

______________________________________________________________________

## Step 6: Embed the Public Key in BITS Whisperer

Open `src/bits_whisperer/core/registration_service.py` and set:

```python
BITS_PUBLIC_KEY_BASE64 = "MCowBQ..."  # Your actual public key
```

Also verify the manifest URL matches your repo:

```python
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "bits-whisperer/bits-whisperer-registry/"
    "main/public_manifest.json"
)
```

This is the only change needed in the main BITS Whisperer codebase.

______________________________________________________________________

## Step 7: Install the WordPress Plugin

### Upload

1. Copy the `wordpress/bits-registration/` folder to your WordPress
   site:

   ```bash
   scp -r wordpress/bits-registration/ \
     user@yoursite.com:/var/www/html/wp-content/plugins/
   ```

   Or upload via SFTP / WordPress admin (**Plugins → Add New →
   Upload Plugin** — zip the folder first).

2. Activate the plugin in **Plugins → Installed Plugins**.

### Configure

1. Go to **Settings → BITS Registration**.
2. Enter your **GitHub Personal Access Token**:
   - Create at github.com → Settings → Developer Settings →
     Fine-grained tokens
   - Scope: **Repository access** → select `bits-whisperer-registry`
   - Permissions: **Actions** → Read and write
3. Set the **GitHub repository** (e.g.,
   `bits-whisperer/bits-whisperer-registry`).
4. Set the **Workflow filename** to `manual_issue.yml`.
5. Add **Product Mapping** (one per line):

   ```text
   42=annual
   43=lifetime
   ```

6. Click **Save Changes**.

______________________________________________________________________

## Step 8: Configure WooCommerce Products

For each licence product in WooCommerce:

1. Go to **Products → Edit** for the product.
2. Note the product ID from the URL (e.g., `?post=42`).
3. Ensure the product price and billing period match the key type:
   - **Annual subscription**: Use WooCommerce Subscriptions or a
     simple product with `annual` key type.
   - **Lifetime licence**: Simple product with `lifetime` key type.
4. Add the mapping in the plugin settings (see step 7).

### Subscription renewals

For annual subscriptions with WooCommerce Subscriptions:

- The plugin fires on `woocommerce_order_status_completed`
  and `woocommerce_order_status_processing`.
- Renewal orders trigger key re-issuance automatically
  (the backend upgrades existing keys in place).

______________________________________________________________________

## Step 9: End-to-End Testing

### Test 1: Manual key issuance

```bash
python backend_scripts/admin_cli.py issue test@example.com --type tester
python backend_scripts/admin_cli.py lookup --email test@example.com
```

Expected: Key issued, visible in lookup with status `active`.

### Test 2: Manifest generation

```bash
python backend_scripts/admin_cli.py update-manifest
cat public_manifest.json | python -m json.tool | head -20
```

Expected: Manifest contains `bits_whisperer` section with the
test key hash.

### Test 3: App verification

1. Build BITS Whisperer with the embedded public key.
2. Enter the test key in **Settings → General → BITS Registration**.
3. Click **Verify**.
4. Expected: Status shows "Alpha/Beta Tester (T)".

### Test 4: WordPress purchase flow

1. Create a test WooCommerce order for a mapped product.
2. Set order status to **Completed**.
3. Check:
   - WordPress admin → Order notes → key should appear
   - GitHub Actions → manual_issue workflow should have run
   - `tokens.json` should have a new entry

### Test 5: Device limit

1. Register the test key on the maximum number of devices (default: 3,
   configurable via `feature_flags.json` → `licensing.max_devices`).
   You can simulate with different device IDs.
2. Attempt one more registration beyond the limit.
3. Expected: Registration blocked, audit log shows
   `DEVICE_LIMIT_EXCEEDED`.

### Test 6: Key revocation

```bash
python backend_scripts/admin_cli.py revoke test@example.com bits_whisperer \
  --reason "End-to-end test"
python backend_scripts/admin_cli.py update-manifest
```

Expected: App shows "Unregistered / Guest" after next verification.

### Test 7: Groups.io sync (dry run)

```bash
GROUPSIO_API_KEY=your_key GROUPSIO_GROUP_NAME=your_group \
  python backend_scripts/groupsio_sync.py
```

Expected: Members listed, lifetime keys issued for new members.

______________________________________________________________________

## Step 10: Go Live Checklist

- [ ] Ed25519 key pair generated and stored securely
- [ ] `BITS_PRIVATE_KEY_BASE64` secret set in registry repo
- [ ] `GROUPSIO_API_KEY` and `GROUPSIO_GROUP_NAME` secrets set
- [ ] `setup_backend.py` run and initial files committed
- [ ] All 3 workflows deployed and visible in Actions tab
- [ ] Manual issue workflow tested successfully
- [ ] Public key embedded in `registration_service.py`
- [ ] Manifest URL matches the registry repo
- [ ] WordPress plugin installed and configured
- [ ] WooCommerce products mapped to key types
- [ ] Test purchase completed successfully
- [ ] Device registration tested (including limit)
- [ ] Key revocation tested
- [ ] Groups.io sync tested
- [ ] Daily sync workflow enabled (Actions → daily_sync → Enable)
- [ ] Backup procedure documented
- [ ] BITS Whisperer build created with embedded public key
- [ ] All test keys cleaned up from `tokens.json`

______________________________________________________________________

## Post-Deployment

### Daily operations (automated)

- `daily_sync.yml` runs at midnight UTC:
  - Expires annual keys past their date
  - Syncs new Groups.io members → lifetime keys
  - Regenerates the manifest

### Weekly operations (manual)

- Review the audit log:
  `python backend_scripts/admin_cli.py audit --limit 50`
- Export a backup:
  `python backend_scripts/admin_cli.py export backup.json`
- Check statistics:
  `python backend_scripts/admin_cli.py stats`

### Monitoring

- Enable GitHub Actions email notifications for workflow failures.
- Monitor WordPress error logs for plugin issues.
- Periodically verify the manifest URL returns valid JSON:
  `curl -s https://raw.githubusercontent.com/.../public_manifest.json | python -m json.tool`
