"""BITS Administration Utility — registration key + beta invitation management.

A standalone CLI tool for BITS administrators to:

- Issue, renew, revoke, and list registration keys (lifetime,
  annual, multi-year, contributor).
- Generate, manage, and audit beta invitation codes.
- Bulk import/export via CSV with flexible column mapping.
- Generate signed public manifests for the BITS Whisperer app.
- Validate data integrity and view audit logs.

Run with::

    python -m tools.bits_admin --help

Or from the ``tools/`` directory::

    python -m bits_admin --help
"""

from __future__ import annotations

__version__ = "1.0.0"
