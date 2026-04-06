"""CSV import / export for bulk key and beta-invitation operations.

Supports flexible column mapping so the administrator can point
any CSV layout at the tool and map columns to registry fields.

Typical CSV layouts handled:

1. **Bulk key issuance** (members or paid customers)::

       email,name,type,source,duration_days,payment_ref,notes
       alice@example.com,Alice,annual,member,365,,
       bob@corp.com,Bob Smith,lifetime,paid,,INV-2023-042,Enterprise licence

2. **Bulk beta invitations**::

       email,name,prefix,notes
       tester@example.com,Tester,BETA,QA team
       vip@company.com,VIP User,VIP,Conference attendee

3. **Custom mapping** via CLI ``--map`` flags::

       bits_admin csv-import users.csv --map email=Email --map name=Full_Name
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from .config import DEFAULT_PRODUCT_ID, KeySource, KeyType, RegistryEntry

# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

# Canonical field names → common CSV header aliases (case-insensitive)
_ALIASES: dict[str, list[str]] = {
    "email": ["email", "e-mail", "email_address", "emailaddress", "user_email", "mail"],
    "name": ["name", "full_name", "fullname", "display_name", "displayname", "user_name"],
    "key_type": ["type", "key_type", "keytype", "license_type", "licence_type", "tier"],
    "source": ["source", "origin", "channel", "acquisition"],
    "product_id": ["product", "product_id", "productid", "app"],
    "duration_days": ["duration", "duration_days", "days", "validity"],
    "payment_ref": [
        "payment_ref",
        "payment",
        "invoice",
        "transaction",
        "order_id",
        "stripe_id",
        "paypal_id",
        "reference",
    ],
    "notes": ["notes", "note", "comment", "comments", "memo"],
    "expiry": ["expiry", "expires", "expiry_date", "expiration", "expires_at"],
    # Beta-specific
    "prefix": ["prefix", "code_prefix"],
}


def _build_alias_lookup() -> dict[str, str]:
    """Return ``{alias_lower: canonical_field}`` for fast look-up."""
    lookup: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            lookup[alias.lower()] = canonical
    return lookup


_ALIAS_LOOKUP = _build_alias_lookup()


def resolve_column_mapping(
    headers: list[str],
    explicit_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map CSV headers to canonical field names.

    Uses built-in aliases first, then applies any explicit overrides
    provided via ``--map`` on the CLI.

    Args:
        headers: The CSV header row (raw strings).
        explicit_map: ``{canonical: csv_header}`` overrides.

    Returns:
        ``{canonical_field: csv_header}`` mapping for all columns
        that could be resolved.
    """
    mapping: dict[str, str] = {}

    # Auto-detect from aliases
    for header in headers:
        canonical = _ALIAS_LOOKUP.get(header.strip().lower())
        if canonical:
            mapping[canonical] = header

    # Explicit overrides take precedence
    if explicit_map:
        for canonical, csv_header in explicit_map.items():
            # Verify the header actually exists in the CSV
            matched = [h for h in headers if h.strip().lower() == csv_header.strip().lower()]
            if matched:
                mapping[canonical] = matched[0]
            else:
                mapping[canonical] = csv_header  # Trust the user

    return mapping


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass
class ImportRow:
    """A single parsed CSV row ready for processing."""

    email: str = ""
    name: str = ""
    key_type: str = KeyType.ANNUAL.value
    source: str = KeySource.ADMIN.value
    product_id: str = DEFAULT_PRODUCT_ID
    duration_days: int | None = None
    payment_ref: str = ""
    notes: str = ""
    expiry: str = ""
    prefix: str = "BETA"  # For beta imports
    raw: dict[str, str] = field(default_factory=dict)
    line_number: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_key_type(value: str) -> str:
    """Normalise a key-type value from CSV."""
    v = value.strip().lower()
    aliases: dict[str, str] = {
        "lifetime": KeyType.LIFETIME.value,
        "life": KeyType.LIFETIME.value,
        "permanent": KeyType.LIFETIME.value,
        "annual": KeyType.ANNUAL.value,
        "yearly": KeyType.ANNUAL.value,
        "1year": KeyType.ANNUAL.value,
        "1-year": KeyType.ANNUAL.value,
        "multi_year": KeyType.MULTI_YEAR.value,
        "multiyear": KeyType.MULTI_YEAR.value,
        "multi-year": KeyType.MULTI_YEAR.value,
        "2year": KeyType.MULTI_YEAR.value,
        "2-year": KeyType.MULTI_YEAR.value,
        "3year": KeyType.MULTI_YEAR.value,
        "3-year": KeyType.MULTI_YEAR.value,
        "5year": KeyType.MULTI_YEAR.value,
        "5-year": KeyType.MULTI_YEAR.value,
        "contributor": KeyType.CONTRIBUTOR.value,
        "contrib": KeyType.CONTRIBUTOR.value,
        "paying": KeyType.CONTRIBUTOR.value,
        "paid": KeyType.CONTRIBUTOR.value,
    }
    return aliases.get(v, value)


def _parse_source(value: str) -> str:
    """Normalise a source value from CSV."""
    v = value.strip().lower()
    aliases: dict[str, str] = {
        "member": KeySource.MEMBER.value,
        "bits_member": KeySource.MEMBER.value,
        "groupsio": KeySource.GROUPSIO_SYNC.value,
        "groups.io": KeySource.GROUPSIO_SYNC.value,
        "paid": KeySource.PAID.value,
        "purchase": KeySource.PAID.value,
        "purchased": KeySource.PAID.value,
        "website": KeySource.PAID.value,
        "stripe": KeySource.PAID.value,
        "paypal": KeySource.PAID.value,
        "contributor": KeySource.CONTRIBUTOR.value,
        "contrib": KeySource.CONTRIBUTOR.value,
        "donor": KeySource.CONTRIBUTOR.value,
        "admin": KeySource.ADMIN.value,
        "manual": KeySource.ADMIN.value,
        "beta": KeySource.BETA.value,
        "promo": KeySource.PROMOTIONAL.value,
        "promotional": KeySource.PROMOTIONAL.value,
        "giveaway": KeySource.PROMOTIONAL.value,
        "conference": KeySource.PROMOTIONAL.value,
    }
    return aliases.get(v, value)


def _parse_duration(value: str) -> int | None:
    """Parse a duration string into days.

    Accepts plain integers (days), or suffixed values like
    ``2y``, ``2years``, ``6m``, ``18months``.
    """
    v = value.strip().lower()
    if not v:
        return None
    # Pure integer
    try:
        return int(v)
    except ValueError:
        pass
    # Year suffixes
    for suffix in ("y", "yr", "yrs", "year", "years"):
        if v.endswith(suffix):
            try:
                return int(v[: -len(suffix)].strip()) * 365
            except ValueError:
                pass
    # Month suffixes
    for suffix in ("m", "mo", "mos", "month", "months"):
        if v.endswith(suffix):
            try:
                return int(v[: -len(suffix)].strip()) * 30
            except ValueError:
                pass
    return None


def parse_csv(
    csv_path: Path,
    *,
    column_map: dict[str, str] | None = None,
    encoding: str = "utf-8-sig",
) -> list[ImportRow]:
    """Parse a CSV file into a list of validated rows.

    Performs column auto-detection, applies explicit overrides, and
    validates each row (e.g. email is required).

    Args:
        csv_path: Path to the CSV file.
        column_map: Optional ``{canonical: csv_header}`` overrides.
        encoding: File encoding.

    Returns:
        List of :class:`ImportRow` objects.
    """
    text = csv_path.read_text(encoding=encoding)
    return parse_csv_text(text, column_map=column_map)


def parse_csv_text(
    text: str,
    *,
    column_map: dict[str, str] | None = None,
) -> list[ImportRow]:
    """Parse CSV text (in-memory) into import rows."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []

    mapping = resolve_column_mapping(list(reader.fieldnames), column_map)
    rows: list[ImportRow] = []

    for line_no, raw_row in enumerate(reader, start=2):
        row = ImportRow(line_number=line_no, raw=dict(raw_row))

        # Map columns
        email_col = mapping.get("email")
        if email_col:
            row.email = raw_row.get(email_col, "").strip()
        name_col = mapping.get("name")
        if name_col:
            row.name = raw_row.get(name_col, "").strip()
        kt_col = mapping.get("key_type")
        if kt_col:
            row.key_type = _parse_key_type(raw_row.get(kt_col, ""))
        src_col = mapping.get("source")
        if src_col:
            row.source = _parse_source(raw_row.get(src_col, ""))
        prod_col = mapping.get("product_id")
        if prod_col:
            row.product_id = raw_row.get(prod_col, "").strip() or DEFAULT_PRODUCT_ID
        dur_col = mapping.get("duration_days")
        if dur_col:
            row.duration_days = _parse_duration(raw_row.get(dur_col, ""))
        pay_col = mapping.get("payment_ref")
        if pay_col:
            row.payment_ref = raw_row.get(pay_col, "").strip()
        notes_col = mapping.get("notes")
        if notes_col:
            row.notes = raw_row.get(notes_col, "").strip()
        expiry_col = mapping.get("expiry")
        if expiry_col:
            row.expiry = raw_row.get(expiry_col, "").strip()
        prefix_col = mapping.get("prefix")
        if prefix_col:
            row.prefix = raw_row.get(prefix_col, "").strip() or "BETA"

        # Validation
        if not row.email:
            row.errors.append("Missing email address")

        # Infer duration from year-suffixed types
        if row.key_type == KeyType.MULTI_YEAR.value and row.duration_days is None:
            # Try to infer from the raw type value
            raw_type = raw_row.get(mapping.get("key_type", ""), "")
            inferred = _parse_duration(raw_type)
            if inferred:
                row.duration_days = inferred

        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_csv(
    entries: list[RegistryEntry],
    output_path: Path,
    *,
    include_keys: bool = False,
) -> int:
    """Export registry entries to CSV.

    Args:
        entries: The entries to export.
        output_path: Destination CSV file.
        include_keys: If ``True``, include the plaintext key.
            Default ``False`` for security.

    Returns:
        Row count written.
    """
    fieldnames = [
        "email",
        "name",
        "product_id",
        "type",
        "source",
        "status",
        "expiry",
        "duration_days",
        "devices",
        "payment_ref",
        "notes",
        "created_at",
        "updated_at",
    ]
    if include_keys:
        fieldnames.insert(0, "key")

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            row = {
                "email": entry.email,
                "name": entry.name,
                "product_id": entry.product_id,
                "type": entry.key_type,
                "source": entry.source,
                "status": entry.status,
                "expiry": entry.expiry or "",
                "duration_days": entry.duration_days or "",
                "devices": len(entry.devices),
                "payment_ref": entry.payment_ref,
                "notes": entry.notes,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }
            if include_keys:
                row["key"] = entry.key
            writer.writerow(row)
    return len(entries)


def export_beta_csv(
    invitations: list[dict],
    output_path: Path,
) -> int:
    """Export beta invitations to CSV.

    Args:
        invitations: List of invitation dicts from
            :func:`beta.list_invitations`.
        output_path: Destination CSV file.

    Returns:
        Row count written.
    """
    fieldnames = ["hash", "email", "name", "notes", "added_at"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for inv in invitations:
            writer.writerow(inv)
    return len(invitations)
