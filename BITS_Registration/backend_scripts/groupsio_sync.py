"""Groups.io membership synchronisation.

Fetches the member list from the BITS Groups.io group and issues
*lifetime* registration keys for each member. BITS members receive
free lifetime access as a benefit of their membership.

Required environment variables:
    GROUPSIO_API_KEY       API key for the Groups.io REST API.
    GROUPSIO_GROUP_NAME    Name of the Groups.io group to sync.

Usage::

    # Via GitHub Actions (daily_sync.yml) or manually:
    python backend_scripts/groupsio_sync.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

# Ensure sibling imports work regardless of CWD
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from registry_manager import issue_key  # noqa: E402

API_KEY = os.getenv("GROUPSIO_API_KEY", "")
GROUP_NAME = os.getenv("GROUPSIO_GROUP_NAME", "")

_PAGE_SIZE = 100
_API_URL = "https://groups.io/api/v1/getmembers"


def fetch_groupsio_members() -> list[str]:
    """Fetch all member email addresses from the Groups.io group.

    Paginates automatically and respects a 1-second delay between
    requests to avoid rate limiting.
    """
    emails: list[str] = []
    page = 1

    while True:
        payload = {
            "api_key": API_KEY,
            "group_name": GROUP_NAME,
            "limit": _PAGE_SIZE,
            "page": page,
        }
        response = requests.post(_API_URL, data=payload, timeout=30)
        if response.status_code != 200:
            print(f"Error fetching page {page}: HTTP {response.status_code}")
            break

        data = response.json()
        members = data.get("data", [])
        if not members:
            break

        for member in members:
            email = member.get("email")
            if email:
                emails.append(email)

        if len(members) < _PAGE_SIZE:
            break
        page += 1
        time.sleep(1)

    return emails


def sync_members(product_id: str = "bits_whisperer") -> None:
    """Sync Groups.io members → lifetime registration keys.

    BITS members receive **lifetime** keys (free benefit of membership).
    If a member already has a key it will be upgraded to lifetime.
    """
    emails = fetch_groupsio_members()
    print(f"Found {len(emails)} member(s) on Groups.io for {product_id}")

    issued = 0
    upgraded = 0
    for email in emails:
        _key, created = issue_key(
            email,
            product_id=product_id,
            key_type="lifetime",
        )
        if created:
            issued += 1
            print(f"  NEW lifetime key: {email}")
        else:
            upgraded += 1

    print(f"Sync complete: {issued} new, {upgraded} existing/upgraded.")


if __name__ == "__main__":
    if not API_KEY or not GROUP_NAME:
        print(
            "Error: GROUPSIO_API_KEY and GROUPSIO_GROUP_NAME environment variables must be set.",
            file=sys.stderr,
        )
        sys.exit(1)
    sync_members()
