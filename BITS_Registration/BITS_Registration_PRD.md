# BITS Central Registration System
## Complete Setup Guide (Zero to Fully Working)

**Estimated Time**: 45-60 minutes
**Difficulty**: Beginner-friendly (no coding required after initial setup)
**Cost**: $0/month (100% free using GitHub)

---

# TABLE OF CONTENTS

1. [What This System Does](#1-what-this-system-does)
2. [What You Need Before Starting](#2-what-you-need-before-starting)
3. [Part A: Create Your GitHub Repository](#3-part-a-create-your-github-repository)
4. [Part B: Download and Prepare the Backend Scripts](#4-part-b-download-and-prepare-the-backend-scripts)
5. [Part C: Generate Your Security Keys](#5-part-c-generate-your-security-keys)
6. [Part D: Configure GitHub Secrets](#6-part-d-configure-github-secrets)
7. [Part E: Set Up GitHub Actions (Automation)](#7-part-e-set-up-github-actions-automation)
8. [Part F: Connect Groups.io for Automatic Membership Sync](#8-part-f-connect-groupsio-for-automatic-membership-sync)
9. [Part G: Update the BITS Whisperer App](#9-part-g-update-the-bits-whisperer-app)
10. [Testing Your Setup](#10-testing-your-setup)
11. [Day-to-Day Administration](#11-day-to-day-administration)
12. [Troubleshooting Guide](#12-troubleshooting-guide)
13. [Frequently Asked Questions (FAQ)](#13-frequently-asked-questions-faq)
14. [Technical Reference](#14-technical-reference)

---

# 1. What This System Does

The BITS Central Registration System manages software licenses for BITS products. Here's what it handles automatically:

| Feature | What It Means |
|---------|---------------|
| **Free keys for BITS members** | Anyone on the Groups.io mailing list automatically gets a free license |
| **Paid keys for non-members** | Non-members can purchase a license (processed manually or via Stripe) |
| **Configurable device limit** | Each license works on a limited number of computers (default: 3, configurable via `feature_flags.json`) |
| **Lifetime vs. Annual keys** | Some keys never expire, others expire after 1 year |
| **Instant revocation** | If someone abuses their license, you can block them immediately |
| **Zero monthly cost** | Everything runs on GitHub's free tier |

### How It Works (Simple Explanation)

1. **GitHub stores the database** - A private JSON file contains all registered users
2. **GitHub Actions does the work** - Automated scripts issue keys, sync memberships, etc.
3. **The app checks validity** - BITS Whisperer asks GitHub "is this key valid?" on launch
4. **Digital signatures prevent hacking** - Even if someone sees the public manifest, they can't forge a valid key

---

# 2. What You Need Before Starting

### Required Accounts (All Free)

| Account | Purpose | Sign Up Link |
|---------|---------|--------------|
| **GitHub** | Hosts your license database and automation | https://github.com/join |
| **Groups.io** (Admin access) | Provides BITS membership list | You should already have this |

### Required Software

| Software | Purpose | Download Link |
|----------|---------|---------------|
| **Python 3.10+** | Runs the backend scripts | https://www.python.org/downloads/ |
| **Git** | Clones and pushes to GitHub | https://git-scm.com/downloads |
| **VS Code** (recommended) | Edit configuration files | https://code.visualstudio.com/ |

### Verify Python is Installed

Open a terminal (PowerShell on Windows, Terminal on Mac) and type:

```powershell
python --version
```

You should see something like `Python 3.11.4`. If you see an error, install Python first.

---

# 3. Part A: Create Your GitHub Repository

This repository will be the "database" for all your licenses.

### Step A1: Log into GitHub

1. Go to https://github.com
2. Click **Sign in** (top right)
3. Enter your username and password

### Step A2: Create a New Repository

1. Click the **+** icon in the top-right corner
2. Click **New repository**
3. Fill in the form:
   - **Repository name**: `bits-registry` (or any name you prefer)
   - **Description**: `License management for BITS software products`
   - **Visibility**: Select **Private** ⚠️ THIS IS CRITICAL - must be Private!
   - **Initialize this repository with**: Check "Add a README file"
4. Click the green **Create repository** button

### Step A3: Clone the Repository to Your Computer

1. On your new repository page, click the green **Code** button
2. Copy the HTTPS URL (looks like `https://github.com/YOUR_USERNAME/bits-registry.git`)
3. Open PowerShell or Terminal
4. Navigate to where you want to store the project:
   ```powershell
   cd C:\Users\YourName\Documents
   ```
5. Clone the repository:
   ```powershell
   git clone https://github.com/YOUR_USERNAME/bits-registry.git
   ```
6. Enter the folder:
   ```powershell
   cd bits-registry
   ```

**✓ Checkpoint**: You should now have a folder called `bits-registry` with a `README.md` file inside.

---

# 4. Part B: Download and Prepare the Backend Scripts

### Step B1: Copy the Backend Scripts

Copy the entire `backend_scripts` folder from the BITS registration source into your `bits-registry` folder.

Your folder structure should look like this:

```
bits-registry/
├── README.md
├── backend_scripts/
│   ├── admin_cli.py
│   ├── key_generator.py
│   ├── manifest_generator.py
│   ├── register_device.py
│   ├── registry_manager.py
│   └── groupsio_sync.py
└── setup_backend.py
```

### Step B2: Install Required Python Packages

In your terminal (make sure you're in the `bits-registry` folder):

```powershell
pip install cryptography requests
```

You should see output ending with `Successfully installed cryptography-XX.X.X requests-X.XX.X`

### Step B3: Run the Setup Script

```powershell
python setup_backend.py
```

This creates the necessary folders and empty JSON files:

```
bits-registry/
├── data/
│   ├── tokens.json          (your license database - PRIVATE)
│   ├── public_manifest.json (anonymous key hashes - can be public)
│   ├── revoked_keys.json    (blocked licenses)
│   └── audit_log.json       (security event history)
```

**✓ Checkpoint**: Run `dir data` (Windows) or `ls data` (Mac/Linux). You should see the 4 JSON files.

---

# 5. Part C: Generate Your Security Keys

This is the most important security step. These keys are like the "master password" for your entire system.

### Step C1: Run the Key Generator

```powershell
python backend_scripts/key_generator.py
```

### Step C2: Save the Output

The script will display TWO keys. **Copy them both to a safe place** (like a password manager).

Example output:

```
============================================================
  BITS CENTRAL REGISTRATION - KEY GENERATION
============================================================

Your Ed25519 key pair has been generated.

PRIVATE KEY (Keep this SECRET! Store in GitHub Secrets):
MC4CAQAwBQYDK2VwBCIEIGxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

PUBLIC KEY (Embed this in your apps):
MCowBQYDK2VwAyEAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy

============================================================
IMPORTANT:
1. Add BITS_PRIVATE_KEY_BASE64 to your GitHub repository secrets
2. Add BITS_PUBLIC_KEY_BASE64 to your app's registration_service.py
============================================================
```

### What These Keys Do

| Key | Where It Goes | Purpose |
|-----|---------------|---------|
| **Private Key** | GitHub Secrets (never in code!) | Signs licenses - proves they came from BITS |
| **Public Key** | Inside the app code | Verifies signatures - confirms license is genuine |

⚠️ **NEVER share your Private Key**. If it leaks, you must regenerate both keys and re-issue all licenses.

**✓ Checkpoint**: You have both keys saved in a secure location.

---

# 6. Part D: Configure GitHub Secrets

GitHub Secrets are encrypted values that your automation can use without exposing them in code.

### Step D1: Navigate to Repository Settings

1. Go to your repository on GitHub (https://github.com/YOUR_USERNAME/bits-registry)
2. Click the **Settings** tab (gear icon, far right)
3. In the left sidebar, click **Secrets and variables**
4. Click **Actions**

### Step D2: Add the Private Key Secret

1. Click the green **New repository secret** button
2. Fill in:
   - **Name**: `BITS_PRIVATE_KEY_BASE64`
   - **Secret**: Paste your Private Key from Step C2 (the long string starting with `MC4CAQ...`)
3. Click **Add secret**

### Step D3: Add a Personal Access Token (for pushing changes)

GitHub Actions needs permission to commit changes back to the repository.

1. Click your profile picture (top-right) → **Settings**
2. Scroll down in the left sidebar, click **Developer settings**
3. Click **Personal access tokens** → **Tokens (classic)**
4. Click **Generate new token** → **Generate new token (classic)**
5. Fill in:
   - **Note**: `BITS Registry Automation`
   - **Expiration**: 90 days (or "No expiration" if you prefer)
   - **Select scopes**: Check only `repo` (Full control of private repositories)
6. Click **Generate token**
7. **COPY THE TOKEN NOW** - you won't see it again!
8. Go back to your repository's **Settings → Secrets → Actions**
9. Click **New repository secret**:
   - **Name**: `REPO_TOKEN`
   - **Secret**: Paste the token you just copied
10. Click **Add secret**

**✓ Checkpoint**: Your Secrets page should show:
- `BITS_PRIVATE_KEY_BASE64`
- `REPO_TOKEN`

---

# 7. Part E: Set Up GitHub Actions (Automation)

GitHub Actions are automated workflows that run when triggered. We have 3 workflows.

### Step E1: Create the Workflows Folder

In your local `bits-registry` folder, create the folder structure:

```powershell
mkdir -p .github/workflows
```

### Step E2: Create the Daily Sync Workflow

Create file `.github/workflows/daily_sync.yml`:

```yaml
name: Daily Membership Sync

on:
  schedule:
    - cron: '0 6 * * *'  # Runs at 6 AM UTC every day
  workflow_dispatch:  # Allows manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install cryptography requests

      - name: Sync Groups.io membership
        env:
          BITS_PRIVATE_KEY_BASE64: ${{ secrets.BITS_PRIVATE_KEY_BASE64 }}
          GROUPSIO_API_KEY: ${{ secrets.GROUPSIO_API_KEY }}
          GROUPSIO_GROUP_NAME: ${{ secrets.GROUPSIO_GROUP_NAME }}
        run: python backend_scripts/groupsio_sync.py

      - name: Regenerate public manifest
        env:
          BITS_PRIVATE_KEY_BASE64: ${{ secrets.BITS_PRIVATE_KEY_BASE64 }}
        run: python backend_scripts/manifest_generator.py

      - name: Commit changes
        run: |
          git config user.name "BITS Bot"
          git config user.email "bot@bits-registry.local"
          git add data/
          git diff --staged --quiet || git commit -m "Auto-sync: $(date -u +%Y-%m-%d)"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.REPO_TOKEN }}
```

### Step E3: Create the Manual Issue Workflow

Create file `.github/workflows/manual_issue.yml`:

```yaml
name: Issue License Key

on:
  workflow_dispatch:
    inputs:
      email:
        description: 'User email address'
        required: true
        type: string
      product:
        description: 'Product ID'
        required: true
        default: 'bits_whisperer'
        type: choice
        options:
          - bits_whisperer
          - bits_braille
          - bits_notetaker
      license_type:
        description: 'License type'
        required: true
        default: 'annual'
        type: choice
        options:
          - annual
          - lifetime
          - contributor

jobs:
  issue:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install cryptography requests

      - name: Issue key
        env:
          BITS_PRIVATE_KEY_BASE64: ${{ secrets.BITS_PRIVATE_KEY_BASE64 }}
        run: |
          python backend_scripts/admin_cli.py issue "${{ inputs.email }}" \
            --product "${{ inputs.product }}" \
            --type "${{ inputs.license_type }}"

      - name: Update manifest
        env:
          BITS_PRIVATE_KEY_BASE64: ${{ secrets.BITS_PRIVATE_KEY_BASE64 }}
        run: python backend_scripts/manifest_generator.py

      - name: Commit
        run: |
          git config user.name "BITS Bot"
          git config user.email "bot@bits-registry.local"
          git add data/
          git commit -m "Issued ${{ inputs.license_type }} key to ${{ inputs.email }}"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.REPO_TOKEN }}
```

### Step E4: Create the Device Registration Workflow

Create file `.github/workflows/register_device.yml`:

```yaml
name: Register Device

on:
  repository_dispatch:
    types: [register_device]

jobs:
  register:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install cryptography

      - name: Register device
        run: |
          python backend_scripts/register_device.py \
            "${{ github.event.client_payload.token_hash }}" \
            "${{ github.event.client_payload.device_id }}" \
            "${{ github.event.client_payload.product_id }}" \
            "${{ github.event.client_payload.timestamp }}" \
            "${{ github.event.client_payload.request_hash }}"

      - name: Regenerate manifest
        env:
          BITS_PRIVATE_KEY_BASE64: ${{ secrets.BITS_PRIVATE_KEY_BASE64 }}
        run: python backend_scripts/manifest_generator.py

      - name: Commit
        run: |
          git config user.name "BITS Bot"
          git config user.email "bot@bits-registry.local"
          git add data/
          git diff --staged --quiet || git commit -m "Device registered"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.REPO_TOKEN }}
```

### Step E5: Push Everything to GitHub

```powershell
git add .
git commit -m "Initial setup with backend scripts and workflows"
git push
```

**✓ Checkpoint**: Go to your repository on GitHub and click the **Actions** tab. You should see all 3 workflows listed.

---

# 8. Part F: Connect Groups.io for Automatic Membership Sync

This allows BITS members to automatically receive free licenses.

### Step F1: Get Your Groups.io API Key

1. Log into Groups.io as an admin of your BITS group
2. Click your group name to enter it
3. Click **Admin** in the left sidebar
4. Click **Settings** → **API Settings**
5. Click **Generate new API key**
6. Copy the key (it looks like a long random string)

### Step F2: Find Your Group Name

Your group name is the part after `https://groups.io/g/` in your group's URL.

Example: If your URL is `https://groups.io/g/BITS-Discussion`, your group name is `BITS-Discussion`

### Step F3: Add Groups.io Secrets to GitHub

Go back to your GitHub repository **Settings → Secrets → Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `GROUPSIO_API_KEY` | Your API key from Step F1 |
| `GROUPSIO_GROUP_NAME` | Your group name from Step F2 |

### Step F4: Test the Sync

1. Go to your repository's **Actions** tab
2. Click **Daily Membership Sync** in the left sidebar
3. Click **Run workflow** (dropdown on the right)
4. Click the green **Run workflow** button

Watch the workflow run. If successful, it will:
- Download your Groups.io member list
- Create license entries for each member
- Update the public manifest

**✓ Checkpoint**: After the workflow completes, check `data/tokens.json` - it should contain entries for your group members.

---

# 9. Part G: Update the BITS Whisperer App

Now we connect the app to your new license system.

### Step G1: Find the Registration Service File

Open: `src/bits_whisperer/core/registration_service.py`

### Step G2: Update the Public Key

Find this line near the top:

```python
BITS_PUBLIC_KEY_BASE64 = "PASTE_YOUR_PUBLIC_KEY_HERE"
```

Replace `PASTE_YOUR_PUBLIC_KEY_HERE` with your actual Public Key from Part C:

```python
BITS_PUBLIC_KEY_BASE64 = "MCowBQYDK2VwAyEAyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

### Step G3: Update the Manifest URL

Find this line:

```python
MANIFEST_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/bits-registry/main/data/public_manifest.json"
```

Replace `YOUR_USERNAME` with your actual GitHub username.

**Note**: For private repositories, you need to use a token-authenticated URL or GitHub API. The simplest option is to make `public_manifest.json` accessible via GitHub Pages or a public gist.

### Step G4: Alternative - Use GitHub API for Private Repos

If you want to keep the manifest private, modify the URL to use the API:

```python
MANIFEST_URL = "https://api.github.com/repos/YOUR_USERNAME/bits-registry/contents/data/public_manifest.json"
```

And add an `Authorization` header in the `_get_secure_session()` method. (Contact Jeff for advanced setup.)

**✓ Checkpoint**: The app should now be configured to check licenses against your GitHub repository.

---

# 10. Testing Your Setup

### Test 1: Issue a Test License

1. Go to GitHub → your repository → **Actions** tab
2. Click **Issue License Key**
3. Click **Run workflow**
4. Enter:
   - Email: `test@example.com`
   - Product: `bits_whisperer`
   - License type: `lifetime`
5. Click **Run workflow**
6. Wait for it to complete (green checkmark)

### Test 2: Verify the License Was Created

1. Go to your repository's main page
2. Navigate to `data/tokens.json`
3. You should see an entry for `test@example.com`

### Test 3: Check the Public Manifest

1. Navigate to `data/public_manifest.json`
2. You should see a hashed entry under `bits_whisperer`

### Test 4: Test in the App

1. Open BITS Whisperer
2. Go to Settings → Registration
3. Enter the registration key shown for `test@example.com` in tokens.json
4. Click **Verify Key**
5. If successful, you should see "Active BITS Membership" or similar

---

# 11. Day-to-Day Administration

## Issuing Keys (3 Methods)

### Method 1: GitHub Actions (Recommended)
1. Go to **Actions** → **Issue License Key** → **Run workflow**
2. Fill in email, product, and type
3. The key is automatically issued and synced

### Method 2: Command Line
```powershell
cd bits-registry
python backend_scripts/admin_cli.py issue user@email.com --type lifetime
python backend_scripts/admin_cli.py update-manifest
git add data/
git commit -m "Issued key to user@email.com"
git push
```

### Method 3: Automatic via Groups.io
Just add someone to your Groups.io mailing list—they'll get a key within 24 hours (or trigger manual sync).

## Common Admin Tasks

| Task | Command |
|------|---------|
| **List all licenses** | `python backend_scripts/admin_cli.py list` |
| **List with device info** | `python backend_scripts/admin_cli.py list --devices` |
| **Revoke a key** | `python backend_scripts/admin_cli.py revoke user@email.com bits_whisperer --reason "Shared key"` |
| **Reset device limit** | `python backend_scripts/admin_cli.py reset-devices user@email.com bits_whisperer` |
| **View security log** | `python backend_scripts/admin_cli.py audit --days 30` |
| **Export for backup** | `python backend_scripts/admin_cli.py export backup.json` |

**Remember**: After any command-line changes, you must:
1. Run `python backend_scripts/admin_cli.py update-manifest`
2. Commit and push: `git add data/ && git commit -m "Updated licenses" && git push`

---

## 4. Administrative Toolkit (How to Manage)
We have provided a command-line interface (`admin_cli.py`) so you don't have to manually edit JSON files.

### Quick Reference Card

| Goal | Command |
| :--- | :--- |
| **Issue a Lifetime License** | `python backend_scripts/admin_cli.py issue user@email.com --type lifetime` |
| **Issue an Annual License** | `python backend_scripts/admin_cli.py issue user@email.com --type annual` |
| **List All Active Users** | `python backend_scripts/admin_cli.py list` |
| **List with Device Info** | `python backend_scripts/admin_cli.py list --devices` |
| **Revoke a Key** | `python backend_scripts/admin_cli.py revoke user@email.com bits_whisperer --reason "Abuse"` |
| **Reset Device Limit** | `python backend_scripts/admin_cli.py reset-devices user@email.com bits_whisperer` |
| **View Security Log** | `python backend_scripts/admin_cli.py audit --days 7` |
| **Export Backup** | `python backend_scripts/admin_cli.py export backup.json` |
| **Update Public Manifest** | `python backend_scripts/admin_cli.py update-manifest` |

---

# 12. Troubleshooting Guide

## Installation Errors

### Error: "python is not recognized as an internal or external command"

**Cause**: Python is not in your system PATH.

**Fix** (Windows):
1. Re-run the Python installer
2. Check the box "Add Python to PATH"
3. Click "Modify" or reinstall
4. Restart your terminal

### Error: "pip is not recognized"

**Fix**: Use `python -m pip` instead:
```powershell
python -m pip install cryptography requests
```

### Error: "ModuleNotFoundError: No module named 'cryptography'"

**Fix**: Install the required package:
```powershell
pip install cryptography
```

## GitHub Errors

### Error: "Permission denied" when pushing

**Cause**: Your Personal Access Token is missing or expired.

**Fix**:
1. Generate a new token (see Part D, Step D3)
2. Update the `REPO_TOKEN` secret in your repository
3. If using HTTPS, re-authenticate: `git config --global credential.helper manager`

### Error: Workflow fails with "Resource not accessible by integration"

**Cause**: The workflow doesn't have write permissions.

**Fix**:
1. Go to repository **Settings** → **Actions** → **General**
2. Scroll to "Workflow permissions"
3. Select "Read and write permissions"
4. Click **Save**

### Error: "Signature verification failed" in the app

**Cause**: The Public Key in the app doesn't match the Private Key used to sign licenses.

**Fix**:
1. Verify you copied the COMPLETE Public Key (no missing characters)
2. Make sure you're using the matching key pair
3. If keys were regenerated, you must re-issue all licenses

## App Errors

### Error: "Key verification failed"

**Possible causes**:
1. No internet connection
2. Manifest URL is incorrect
3. The key hasn't been added to the registry yet

**Fix**:
1. Check internet connection
2. Verify `MANIFEST_URL` in `registration_service.py`
3. Wait for the next sync or trigger a manual sync

### Error: "Device limit reached"

**Cause**: The user has activated on the maximum number of allowed devices
(configurable via `feature_flags.json` → `licensing.max_devices`, default: 3).

**Fix** (if legitimate):
```powershell
python backend_scripts/admin_cli.py reset-devices user@email.com bits_whisperer
python backend_scripts/admin_cli.py update-manifest
git add data/ && git commit -m "Reset devices" && git push
```

### Error: "SECURITY: SSL verification failed"

**Cause**: Your network may be intercepting HTTPS traffic (corporate proxy, etc.)

**Fix**: This is a security feature. Do NOT bypass it. Instead:
1. Try from a different network
2. Check if your antivirus is intercepting SSL
3. Contact your IT department

---

# 13. Frequently Asked Questions (FAQ)

## General Questions

### Q: Is this really free?

**A**: Yes! GitHub Free accounts include:
- Unlimited private repositories
- 2,000 minutes/month of GitHub Actions
- The daily sync uses ~1 minute per day = ~30 minutes/month

You could run this system for 60+ years on the free tier.

### Q: What if GitHub goes down?

**A**: The app has an offline grace period (default: 30 days,
configurable via `feature_flags.json` → `licensing.offline_grace_days`).
Users can continue using the software even if GitHub is unreachable.
When GitHub returns, verification resumes automatically.

### Q: Can users share their keys?

**A**: They can try, but:
1. Each key is locked to a configurable number of devices (default: 3)
2. Device fingerprints use multiple hardware factors (hard to spoof)
3. Sharing would require giving up their own device slots
4. You can revoke abused keys instantly

### Q: What happens when an annual key expires?

**A**: The app will show "Unregistered / Guest" status. To renew:
1. Issue a new key with `--type annual`
2. The old key is automatically invalidated

### Q: Can I have multiple products?

**A**: Yes! The system supports multiple products from day one. Just use different `product_id` values:
- `bits_whisperer`
- `bits_braille`
- `bits_notetaker`

Each product has its own section in the manifest.

## Security Questions

### Q: What if someone steals my Private Key?

**A**: They could forge licenses. Immediately:
1. Generate a new key pair (Part C)
2. Update the `BITS_PRIVATE_KEY_BASE64` secret
3. Update the `BITS_PUBLIC_KEY_BASE64` in the app
4. Re-issue all existing licenses
5. Release an app update with the new Public Key

### Q: Can hackers read my tokens.json?

**A**: No. It's in a private repository. Only you (and GitHub Actions with your secrets) can access it.

### Q: Can hackers modify the public manifest?

**A**: No. Even if they could:
- They can't forge valid signatures (need Private Key)
- The app verifies signatures before trusting any data
- Revocation list is also signed

### Q: Is Ed25519 secure?

**A**: Yes. Ed25519 is:
- Used by SSH, Signal, WhatsApp, and more
- Considered quantum-resistant for the foreseeable future
- The same algorithm GitHub uses for SSH keys

## Operational Questions

### Q: How do I see who has licenses?

```powershell
python backend_scripts/admin_cli.py list
```

### Q: How do I add a paid customer?

```powershell
python backend_scripts/admin_cli.py issue customer@email.com --type contributor
python backend_scripts/admin_cli.py update-manifest
git add data/ && git commit -m "Paid license" && git push
```

### Q: How do I block someone?

```powershell
python backend_scripts/admin_cli.py revoke abuser@email.com bits_whisperer --reason "Shared key online"
python backend_scripts/admin_cli.py update-manifest
git add data/ && git commit -m "Revoked abuser" && git push
```

They will lose access within minutes (next time the app verifies).

### Q: How do I back up everything?

```powershell
python backend_scripts/admin_cli.py export backup-$(date +%Y%m%d).json
```

This exports all license data (with keys redacted for security).

### Q: How do I migrate to a new repository?

1. Clone your current repository
2. Create a new repository
3. Copy all files
4. Update `MANIFEST_URL` in the app
5. Update GitHub secrets in the new repository
6. Release an app update

---

# 14. Technical Reference

## File Structure

```
bits-registry/
├── .github/
│   └── workflows/
│       ├── daily_sync.yml      # Automatic Groups.io sync
│       ├── manual_issue.yml    # Manual key issuance
│       └── register_device.yml # Device registration
├── backend_scripts/
│   ├── admin_cli.py            # Command-line administration
│   ├── groupsio_sync.py        # Groups.io API integration
│   ├── key_generator.py        # Ed25519 key pair generator
│   ├── manifest_generator.py   # Public manifest builder
│   ├── register_device.py      # Device registration handler
│   └── registry_manager.py     # Core license management
├── data/
│   ├── audit_log.json          # Security event history
│   ├── public_manifest.json    # Anonymous key hashes (shareable)
│   ├── revoked_keys.json       # Blocked license hashes
│   └── tokens.json             # Full license database (PRIVATE!)
└── setup_backend.py            # Initial setup script
```

## Data Formats

### tokens.json Entry
```json
{
  "email": "user@example.com",
  "token": "BITS-XXXX-XXXX-XXXX",
  "token_hash": "sha256...",
  "product_id": "bits_whisperer",
  "type": "lifetime",
  "expiry": null,
  "status": "active",
  "signed_license": "base64...",
  "devices": ["device_hash_1", "device_hash_2"],
  "issued_at": "2026-02-09T10:30:00Z",
  "issued_by": "github_actions"
}
```

### public_manifest.json Structure
```json
{
  "_generated": "2026-02-09T10:30:00Z",
  "_revoked": ["revoked_hash_1", "revoked_hash_2"],
  "bits_whisperer": {
    "sha256_of_key": {
      "s": "base64_signed_blob",
      "d": ["device_hash_1", "device_hash_2"]
    }
  }
}
```

## Licensing Configuration (Remote)

The BITS Whisperer app reads licensing parameters from
`feature_flags.json` in the main code repository. These values are
fetched remotely and cached for 24 hours, allowing licensing behaviour
to be adjusted without releasing a new app build.

### Configuration fields

| Field                   | Type   | Default            | Description                                         |
|-------------------------|--------|--------------------|-----------------------------------------------------|
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

These are stored in `feature_flags.json` under the `licensing` key:

```json
"licensing": {
  "trial_days": 7,
  "offline_grace_days": 30,
  "reverify_hours": 24,
  "trial_warning_days": 2,
  "max_devices": 3,
  "admin_message": "",
  "purchase_url": "",
  "trial_extension_days": 0,
  "grace_mode_enabled": false,
  "grace_mode_days": 7,
  "tier_names": { "L": "Lifetime Member", "A": "Active Membership",
                  "C": "Paying Contributor", "T": "Alpha Tester" }
}
```

### Grace mode

When `grace_mode_enabled` is `true`, users whose trial or licence has
expired enter a read-only grace period (default: 7 days) before losing
access entirely. This gives them time to renew or purchase.

### Primary CLI management

The primary admin CLI at `tools/bits_admin/` includes a `licensing`
subcommand group for managing these fields without editing JSON
manually. See the ADMIN_GUIDE.md for full details.

---

## Security Architecture (7 Layers)

| Layer | Protection | Implementation |
|-------|------------|----------------|
| 1 | **Cryptographic Signatures** | Ed25519 (unforgeable without Private Key) |
| 2 | **Multi-Factor Fingerprinting** | MAC + Platform + CPU + User Path |
| 3 | **Replay Attack Prevention** | 5-minute timestamp expiry |
| 4 | **Instant Revocation** | `_revoked` list checked first |
| 5 | **Rate Limiting** | 60-second minimum between verifications |
| 6 | **SSL/TLS Enforcement** | Man-in-the-middle detection |
| 7 | **Audit Logging** | All operations recorded with timestamps |

## GitHub Secrets Reference

| Secret Name | Purpose | Example |
|-------------|---------|---------|
| `BITS_PRIVATE_KEY_BASE64` | Signs licenses | `MC4CAQAwBQ...` |
| `REPO_TOKEN` | Allows Actions to commit | `ghp_xxxx...` |
| `GROUPSIO_API_KEY` | Fetches member list | `abc123...` |
| `GROUPSIO_GROUP_NAME` | Which group to sync | `BITS-Discussion` |

## API Endpoints (For Advanced Users)

### Trigger Device Registration
```bash
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOUR_USERNAME/bits-registry/dispatches \
  -d '{
    "event_type": "register_device",
    "client_payload": {
      "token_hash": "sha256...",
      "device_id": "device_fingerprint",
      "product_id": "bits_whisperer",
      "timestamp": "2026-02-09T10:30:00Z",
      "request_hash": "integrity_hash"
    }
  }'
```

---

# 15. Future Enhancements (Roadmap)

- [ ] **Stripe Integration** - Automatic license issuance on payment
- [ ] **Email Notifications** - Warn users before expiration
- [ ] **Web Dashboard** - GitHub Pages-based admin interface
- [ ] **Key Rotation** - Change signing keys without re-issuing licenses
- [ ] **Usage Analytics** - Track which products are most used
- [ ] **Bulk Import** - CSV upload for initial user migration

---

# 16. Support & Contact

If you encounter issues not covered in this guide:

1. **Check the Audit Log**: `python backend_scripts/admin_cli.py audit --days 7`
2. **Review GitHub Actions**: Click the failed workflow for detailed error messages
3. **Search Issues**: Check if someone reported a similar problem
4. **Create an Issue**: Describe what you tried and what happened

---

**Document Version**: 2.1
**Last Updated**: February 15, 2026
**Maintainer**: BITS Development Team
