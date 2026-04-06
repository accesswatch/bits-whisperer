"""Tests for the BITS Admin utility.

Covers crypto, registry operations, beta management, CSV import/export,
and the CLI argument parser.
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Set up a temporary data directory and patch config paths."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    import tools.bits_admin.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg, "TOKENS_FILE", data_dir / "tokens.json")
    monkeypatch.setattr(cfg, "PUBLIC_MANIFEST_FILE", data_dir / "public_manifest.json")
    monkeypatch.setattr(cfg, "REVOKED_KEYS_FILE", data_dir / "revoked_keys.json")
    monkeypatch.setattr(cfg, "AUDIT_LOG_FILE", data_dir / "audit_log.json")
    monkeypatch.setattr(cfg, "BETA_INVITATIONS_FILE", tmp_path / "beta_invitations.json")

    # Patch registry module to use same config
    import tools.bits_admin.registry as reg

    monkeypatch.setattr(reg, "TOKENS_FILE", data_dir / "tokens.json")
    monkeypatch.setattr(reg, "PUBLIC_MANIFEST_FILE", data_dir / "public_manifest.json")
    monkeypatch.setattr(reg, "REVOKED_KEYS_FILE", data_dir / "revoked_keys.json")
    monkeypatch.setattr(reg, "AUDIT_LOG_FILE", data_dir / "audit_log.json")

    # Init empty files
    (data_dir / "tokens.json").write_text("[]")
    (data_dir / "revoked_keys.json").write_text("[]")
    (data_dir / "audit_log.json").write_text("[]")

    return data_dir


@pytest.fixture
def private_key_b64():
    """Generate a fresh Ed25519 private key for testing."""
    from tools.bits_admin.crypto import generate_keypair

    priv, _pub = generate_keypair()
    return priv


@pytest.fixture
def beta_file(tmp_path, monkeypatch):
    """Set up a temporary beta invitations file."""
    import tools.bits_admin.config as cfg

    path = tmp_path / "beta_invitations.json"
    path.write_text(json.dumps({"version": 1, "codes": [], "metadata": {}}))
    monkeypatch.setattr(cfg, "BETA_INVITATIONS_FILE", path)
    return path


# ===================================================================
# Crypto tests
# ===================================================================


class TestCrypto:
    """Tests for the crypto module."""

    def test_generate_keypair(self):
        from tools.bits_admin.crypto import generate_keypair

        priv, pub = generate_keypair()
        assert len(priv) > 20
        assert len(pub) > 20
        assert priv != pub

    def test_sign_and_verify(self):
        from tools.bits_admin.crypto import (
            generate_keypair,
            load_private_key,
            load_public_key,
            sign_license,
            verify_signature,
        )

        priv_b64, pub_b64 = generate_keypair()
        blob = sign_license(
            load_private_key(priv_b64),
            "user@example.com",
            "bits_whisperer",
            "lifetime",
            None,
        )
        assert verify_signature(load_public_key(pub_b64), blob) is True

    def test_verify_bad_signature(self):
        from tools.bits_admin.crypto import (
            generate_keypair,
            load_public_key,
            verify_signature,
        )

        _, pub_b64 = generate_keypair()
        assert verify_signature(load_public_key(pub_b64), "badsignature") is False

    def test_sha256_hex(self):
        from tools.bits_admin.crypto import sha256_hex

        h = sha256_hex("hello")
        assert len(h) == 64
        assert h == sha256_hex("hello")  # Deterministic
        assert h != sha256_hex("world")

    def test_sha256_normalised(self):
        from tools.bits_admin.crypto import sha256_normalised

        # Case insensitive, whitespace stripped
        assert sha256_normalised("ABC") == sha256_normalised("abc")
        assert sha256_normalised("  abc  ") == sha256_normalised("ABC")

    def test_generate_registration_key_format(self):
        from tools.bits_admin.crypto import generate_registration_key

        key = generate_registration_key("bits_whisperer")
        assert key.startswith("bits_whisperer-")
        parts = key.split("-")
        # product-uuid(5 parts)-checksum = 7 parts total
        assert len(parts) == 7
        # Last part is 4-char checksum
        assert len(parts[-1]) == 4


# ===================================================================
# Config tests
# ===================================================================


class TestConfig:
    """Tests for config data models."""

    def test_key_type_status_codes(self):
        from tools.bits_admin.config import KeyType

        assert KeyType.LIFETIME.status_code == "L"
        assert KeyType.ANNUAL.status_code == "A"
        assert KeyType.MULTI_YEAR.status_code == "A"
        assert KeyType.CONTRIBUTOR.status_code == "C"

    def test_key_type_durations(self):
        from tools.bits_admin.config import KeyType

        assert KeyType.LIFETIME.default_duration_days is None
        assert KeyType.ANNUAL.default_duration_days == 365
        assert KeyType.CONTRIBUTOR.default_duration_days is None

    def test_registry_entry_roundtrip(self):
        from tools.bits_admin.config import RegistryEntry

        entry = RegistryEntry(
            email="test@example.com",
            key="test-key",
            token_hash="abc123",
            name="Test User",
            payment_ref="INV-001",
            notes="A note",
        )
        d = entry.to_dict()
        assert d["email"] == "test@example.com"
        assert d["name"] == "Test User"
        assert d["payment_ref"] == "INV-001"

        restored = RegistryEntry.from_dict(d)
        assert restored.email == entry.email
        assert restored.name == entry.name
        assert restored.payment_ref == entry.payment_ref

    def test_registry_entry_omits_empty_extended_fields(self):
        from tools.bits_admin.config import RegistryEntry

        entry = RegistryEntry(email="a@b.com", key="k", token_hash="h")
        d = entry.to_dict()
        assert "name" not in d
        assert "payment_ref" not in d
        assert "notes" not in d
        assert "duration_days" not in d


# ===================================================================
# Registry tests
# ===================================================================


class TestRegistry:
    """Tests for registry management."""

    def test_issue_new_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import issue_key, load_registry

        entry, created = issue_key("alice@example.com", private_key_b64)
        assert created is True
        assert entry.email == "alice@example.com"
        assert entry.status == "active"
        assert entry.key.startswith("bits_whisperer-")
        assert len(entry.token_hash) == 64

        reg = load_registry()
        assert len(reg) == 1

    def test_issue_lifetime_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeyType
        from tools.bits_admin.registry import issue_key

        entry, created = issue_key(
            "life@example.com",
            private_key_b64,
            key_type=KeyType.LIFETIME,
        )
        assert created is True
        assert entry.expiry is None
        assert entry.key_type == "lifetime"

    def test_issue_paid_nonmember_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeySource, KeyType
        from tools.bits_admin.registry import issue_key

        entry, _ = issue_key(
            "customer@corp.com",
            private_key_b64,
            key_type=KeyType.LIFETIME,
            source=KeySource.PAID,
            payment_ref="STRIPE-pi_abc123",
            name="Jane Customer",
            notes="Enterprise licence",
        )
        assert entry.source == "paid"
        assert entry.payment_ref == "STRIPE-pi_abc123"
        assert entry.name == "Jane Customer"
        assert entry.notes == "Enterprise licence"

    def test_issue_multi_year_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeyType
        from tools.bits_admin.registry import issue_key

        entry, _ = issue_key(
            "multi@example.com",
            private_key_b64,
            key_type=KeyType.MULTI_YEAR,
            duration_days=1095,  # 3 years
        )
        assert entry.key_type == "multi_year"
        assert entry.duration_days == 1095
        assert entry.expiry is not None
        expiry = datetime.fromisoformat(entry.expiry)
        assert expiry > datetime.now() + timedelta(days=1090)

    def test_upgrade_existing_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeySource, KeyType
        from tools.bits_admin.registry import issue_key, load_registry

        # Issue annual first
        entry1, created1 = issue_key(
            "user@example.com",
            private_key_b64,
            key_type=KeyType.ANNUAL,
            source=KeySource.MEMBER,
        )
        assert created1 is True

        # Upgrade to lifetime
        entry2, created2 = issue_key(
            "user@example.com",
            private_key_b64,
            key_type=KeyType.LIFETIME,
            source=KeySource.PAID,
            payment_ref="PAY-001",
        )
        assert created2 is False  # Upgraded, not new
        assert entry2.key_type == "lifetime"
        assert entry2.source == "paid"
        assert entry2.expiry is None

        # Still only one entry
        assert len(load_registry()) == 1

    def test_case_insensitive_email(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import issue_key

        issue_key("User@Example.COM", private_key_b64)
        entry, created = issue_key("user@example.com", private_key_b64)
        assert created is False  # Found by case-insensitive match

    def test_renew_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeyType
        from tools.bits_admin.registry import issue_key, renew_key

        issue_key("renew@example.com", private_key_b64, key_type=KeyType.ANNUAL)
        entry = renew_key("renew@example.com", private_key_b64, duration_days=730)
        assert entry is not None
        assert entry.duration_days == 730
        expiry = datetime.fromisoformat(entry.expiry)
        assert expiry > datetime.now() + timedelta(days=725)

    def test_renew_nonexistent(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import renew_key

        assert renew_key("nobody@example.com", private_key_b64) is None

    def test_renew_lifetime_noop(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeyType
        from tools.bits_admin.registry import issue_key, renew_key

        issue_key("life@example.com", private_key_b64, key_type=KeyType.LIFETIME)
        entry = renew_key("life@example.com", private_key_b64)
        assert entry is not None
        assert entry.expiry is None  # Unchanged

    def test_revoke_key(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import issue_key, load_revoked_hashes, revoke_key

        entry, _ = issue_key("bad@example.com", private_key_b64)
        ok = revoke_key("bad@example.com", reason="Abuse")
        assert ok is True

        revoked = load_revoked_hashes()
        assert entry.token_hash in revoked

    def test_revoke_nonexistent(self, tmp_data_dir):
        from tools.bits_admin.registry import revoke_key

        assert revoke_key("nobody@example.com") is False

    def test_reset_devices(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import issue_key, load_registry, reset_devices

        issue_key("dev@example.com", private_key_b64)
        reg = load_registry()
        reg[0].devices = ["d1", "d2", "d3"]
        from tools.bits_admin.registry import save_registry

        save_registry(reg)

        cleared = reset_devices("dev@example.com")
        assert cleared == 3

        reg2 = load_registry()
        assert reg2[0].devices == []

    def test_find_entry(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import find_entry, issue_key

        issue_key("find@example.com", private_key_b64)
        found = find_entry("find@example.com")
        assert found is not None
        assert found.email == "find@example.com"
        assert find_entry("nope@example.com") is None

    def test_list_entries_filters(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeySource
        from tools.bits_admin.registry import issue_key, list_entries

        issue_key("m@b.com", private_key_b64, source=KeySource.MEMBER)
        issue_key("p@b.com", private_key_b64, source=KeySource.PAID)
        issue_key("c@b.com", private_key_b64, source=KeySource.CONTRIBUTOR)

        all_entries = list_entries()
        assert len(all_entries) == 3

        paid_only = list_entries(source="paid")
        assert len(paid_only) == 1
        assert paid_only[0].email == "p@b.com"

    def test_clean_expired(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeyType
        from tools.bits_admin.registry import clean_expired, issue_key, load_registry, save_registry

        issue_key("exp@example.com", private_key_b64, key_type=KeyType.ANNUAL)
        reg = load_registry()
        # Manually backdate the expiry
        reg[0].expiry = (datetime.now() - timedelta(days=1)).isoformat()
        save_registry(reg)

        count = clean_expired()
        assert count == 1

        reg2 = load_registry()
        assert reg2[0].status == "expired"

    def test_generate_manifest(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import PUBLIC_MANIFEST_FILE
        from tools.bits_admin.registry import generate_manifest, issue_key

        issue_key("mf@example.com", private_key_b64)
        count = generate_manifest()
        assert count == 1

        manifest = json.loads(PUBLIC_MANIFEST_FILE.read_text())
        assert "bits_whisperer" in manifest
        assert "_revoked" in manifest
        assert "_meta" in manifest

    def test_manifest_excludes_revoked(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import generate_manifest, issue_key, revoke_key

        entry, _ = issue_key("rev@example.com", private_key_b64)
        revoke_key("rev@example.com")
        count = generate_manifest()
        assert count == 0

    def test_get_stats(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.config import KeySource
        from tools.bits_admin.registry import get_stats, issue_key

        issue_key("a@b.com", private_key_b64, source=KeySource.MEMBER)
        issue_key("b@b.com", private_key_b64, source=KeySource.PAID)

        s = get_stats()
        assert s["total"] == 2
        assert s["active"] == 2
        assert s["by_source"]["member"] == 1
        assert s["by_source"]["paid"] == 1

    def test_export_registry(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import export_registry, issue_key

        issue_key("ex@example.com", private_key_b64)
        out = tmp_data_dir / "export.json"
        count = export_registry(out)
        assert count == 1

        data = json.loads(out.read_text())
        assert data[0]["key"] == "[REDACTED]"

    def test_audit_logging(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.registry import get_audit_log, issue_key

        issue_key("audit@example.com", private_key_b64)
        log = get_audit_log()
        assert len(log) >= 1
        assert log[-1]["action"] == "KEY_ISSUED"
        assert log[-1]["email"] == "audit@example.com"


# ===================================================================
# Beta tests
# ===================================================================


class TestBeta:
    """Tests for beta invitation management."""

    def test_generate_invitation_code(self):
        from tools.bits_admin.beta import generate_invitation_code

        code = generate_invitation_code()
        assert code.startswith("BETA-")
        parts = code.split("-")
        assert len(parts) == 5  # BETA + 4 groups

    def test_generate_custom_prefix(self):
        from tools.bits_admin.beta import generate_invitation_code

        code = generate_invitation_code(prefix="VIP")
        assert code.startswith("VIP-")

    def test_add_and_list_invitations(self, beta_file):
        from tools.bits_admin.beta import add_invitation, list_invitations

        h = add_invitation(
            "TEST-CODE-1234", email="user@test.com", name="Test User", path=beta_file
        )
        assert len(h) == 64

        invitations = list_invitations(beta_file)
        assert len(invitations) == 1
        assert invitations[0]["email"] == "user@test.com"
        assert invitations[0]["hash"] == h

    def test_add_deduplicates(self, beta_file):
        from tools.bits_admin.beta import add_invitation, list_invitations

        add_invitation("SAME-CODE", path=beta_file)
        add_invitation("SAME-CODE", path=beta_file)
        assert len(list_invitations(beta_file)) == 1

    def test_revoke_invitation(self, beta_file):
        from tools.bits_admin.beta import add_invitation, list_invitations, revoke_invitation

        h = add_invitation("REVOKE-ME", path=beta_file)
        assert revoke_invitation(h, path=beta_file) is True
        assert len(list_invitations(beta_file)) == 0

    def test_revoke_nonexistent(self, beta_file):
        from tools.bits_admin.beta import revoke_invitation

        assert revoke_invitation("nonexistent_hash", path=beta_file) is False

    def test_generate_and_add(self, beta_file):
        from tools.bits_admin.beta import generate_and_add, list_invitations

        results = generate_and_add(count=3, prefix="TEST", email="batch@test.com", path=beta_file)
        assert len(results) == 3
        for code, h in results:
            assert code.startswith("TEST-")
            assert len(h) == 64

        assert len(list_invitations(beta_file)) == 3

    def test_hash_matches_beta_service(self, beta_file):
        """Verify our hashing is compatible with BetaService in the app."""
        from tools.bits_admin.crypto import sha256_normalised

        # BetaService.hash_code does: strip().upper() -> SHA-256
        code = "beta-test-1234"
        expected = sha256_normalised(code)
        # Same as: hashlib.sha256("BETA-TEST-1234".encode("utf-8")).hexdigest()
        import hashlib

        manual = hashlib.sha256(b"BETA-TEST-1234").hexdigest()
        assert expected == manual


# ===================================================================
# CSV tests
# ===================================================================


class TestCSV:
    """Tests for CSV import/export operations."""

    def test_resolve_column_mapping_auto(self):
        from tools.bits_admin.csv_ops import resolve_column_mapping

        headers = ["Email", "Full_Name", "Type", "Payment"]
        mapping = resolve_column_mapping(headers)
        assert mapping["email"] == "Email"
        assert mapping["name"] == "Full_Name"
        assert mapping["key_type"] == "Type"
        assert mapping["payment_ref"] == "Payment"

    def test_resolve_column_mapping_explicit_override(self):
        from tools.bits_admin.csv_ops import resolve_column_mapping

        headers = ["user_email", "custom_col"]
        mapping = resolve_column_mapping(headers, explicit_map={"name": "custom_col"})
        assert mapping["email"] == "user_email"
        assert mapping["name"] == "custom_col"

    def test_parse_csv_text_basic(self):
        from tools.bits_admin.csv_ops import parse_csv_text

        csv_text = textwrap.dedent(
            """\
            email,name,type,source,payment_ref,notes
            alice@example.com,Alice,annual,member,,Free member
            bob@corp.com,Bob Smith,lifetime,paid,INV-001,Enterprise
        """
        )
        rows = parse_csv_text(csv_text)
        assert len(rows) == 2
        assert rows[0].email == "alice@example.com"
        assert rows[0].key_type == "annual"
        assert rows[0].source == "member"
        assert rows[1].name == "Bob Smith"
        assert rows[1].key_type == "lifetime"
        assert rows[1].source == "paid"
        assert rows[1].payment_ref == "INV-001"

    def test_parse_csv_text_type_aliases(self):
        from tools.bits_admin.csv_ops import parse_csv_text

        csv_text = "email,type\nuser@a.com,yearly\nboss@a.com,permanent\n"
        rows = parse_csv_text(csv_text)
        assert rows[0].key_type == "annual"
        assert rows[1].key_type == "lifetime"

    def test_parse_csv_text_source_aliases(self):
        from tools.bits_admin.csv_ops import parse_csv_text

        csv_text = "email,source\na@b.com,stripe\nc@d.com,groups.io\n"
        rows = parse_csv_text(csv_text)
        assert rows[0].source == "paid"
        assert rows[1].source == "groupsio_sync"

    def test_parse_csv_missing_email(self):
        from tools.bits_admin.csv_ops import parse_csv_text

        csv_text = "email,name\n,NoEmail\n"
        rows = parse_csv_text(csv_text)
        assert len(rows[0].errors) > 0
        assert "email" in rows[0].errors[0].lower()

    def test_parse_csv_duration_parsing(self):
        from tools.bits_admin.csv_ops import parse_csv_text

        csv_text = "email,duration\na@b.com,2y\nc@d.com,730\ne@f.com,6months\n"
        rows = parse_csv_text(csv_text)
        assert rows[0].duration_days == 730  # 2 * 365
        assert rows[1].duration_days == 730
        assert rows[2].duration_days == 180  # 6 * 30

    def test_export_csv(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.csv_ops import export_csv
        from tools.bits_admin.registry import issue_key, list_entries

        issue_key("exp@test.com", private_key_b64, name="Exp User")
        entries = list_entries()
        out = tmp_data_dir / "export.csv"
        count = export_csv(entries, out)
        assert count == 1

        content = out.read_text("utf-8-sig")
        assert "exp@test.com" in content
        assert "Exp User" in content
        # Keys should NOT be in export by default
        assert "bits_whisperer-" not in content

    def test_export_csv_with_keys(self, tmp_data_dir, private_key_b64):
        from tools.bits_admin.csv_ops import export_csv
        from tools.bits_admin.registry import issue_key, list_entries

        issue_key("expk@test.com", private_key_b64)
        entries = list_entries()
        out = tmp_data_dir / "export_keys.csv"
        export_csv(entries, out, include_keys=True)

        content = out.read_text("utf-8-sig")
        assert "bits_whisperer-" in content

    def test_export_beta_csv(self, beta_file, tmp_path):
        from tools.bits_admin.beta import generate_and_add, list_invitations
        from tools.bits_admin.csv_ops import export_beta_csv

        generate_and_add(2, email="beta@test.com", path=beta_file)
        invitations = list_invitations(beta_file)
        out = tmp_path / "beta_export.csv"
        count = export_beta_csv(invitations, out)
        assert count == 2
        assert "beta@test.com" in out.read_text()


# ===================================================================
# CLI parser tests
# ===================================================================


class TestCLIParser:
    """Test argument parsing (no actual execution)."""

    def test_keys_issue_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "keys",
                "issue",
                "user@test.com",
                "--type",
                "lifetime",
                "--source",
                "paid",
                "--payment-ref",
                "INV-001",
                "--name",
                "Test User",
            ]
        )
        assert args.command == "keys"
        assert args.keys_cmd == "issue"
        assert args.email == "user@test.com"
        assert args.type == "lifetime"
        assert args.source == "paid"
        assert args.payment_ref == "INV-001"
        assert args.name == "Test User"

    def test_keys_renew_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(["keys", "renew", "u@t.com", "--duration", "2y"])
        assert args.keys_cmd == "renew"
        assert args.duration == "2y"

    def test_beta_generate_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(["beta", "generate", "--count", "5", "--prefix", "VIP"])
        assert args.command == "beta"
        assert args.beta_cmd == "generate"
        assert args.count == 5
        assert args.prefix == "VIP"

    def test_csv_import_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "csv-import",
                "customers.csv",
                "--mode",
                "keys",
                "--map",
                "email=Email_Address",
                "--map",
                "name=Full Name",
                "--source-override",
                "paid",
                "--force",
            ]
        )
        assert args.command == "csv-import"
        assert args.file == "customers.csv"
        assert args.mode == "keys"
        assert len(args.map) == 2
        assert args.source_override == "paid"
        assert args.force is True

    def test_csv_export_keys_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "csv-export",
                "keys",
                "output.csv",
                "--source",
                "paid",
                "--include-keys",
            ]
        )
        assert args.what == "keys"
        assert args.output == "output.csv"
        assert args.source == "paid"
        assert args.include_keys is True

    def test_stats_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(["stats", "--product", "bits_whisperer"])
        assert args.command == "stats"
        assert args.product == "bits_whisperer"

    def test_keygen_parser(self):
        from tools.bits_admin.__main__ import build_parser

        parser = build_parser()
        args = parser.parse_args(["keygen"])
        assert args.command == "keygen"


# ===================================================================
# Integration tests
# ===================================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_lifecycle_member(self, tmp_data_dir, private_key_b64):
        """Issue, verify, renew, and revoke a member key."""
        from tools.bits_admin.config import KeySource, KeyType
        from tools.bits_admin.registry import (
            generate_manifest,
            issue_key,
            renew_key,
            revoke_key,
        )

        # Issue
        entry, created = issue_key(
            "member@bits.org",
            private_key_b64,
            key_type=KeyType.ANNUAL,
            source=KeySource.MEMBER,
        )
        assert created is True
        generate_manifest()

        # Verify it's in the manifest
        from tools.bits_admin.config import PUBLIC_MANIFEST_FILE

        manifest = json.loads(PUBLIC_MANIFEST_FILE.read_text())
        assert entry.token_hash in manifest["bits_whisperer"]

        # Renew
        renewed = renew_key("member@bits.org", private_key_b64, duration_days=365)
        assert renewed is not None
        generate_manifest()

        # Revoke
        ok = revoke_key("member@bits.org", reason="Left organisation")
        assert ok is True
        generate_manifest()

        manifest2 = json.loads(PUBLIC_MANIFEST_FILE.read_text())
        assert entry.token_hash not in manifest2.get("bits_whisperer", {})
        assert entry.token_hash in manifest2["_revoked"]

    def test_full_lifecycle_paid_customer(self, tmp_data_dir, private_key_b64):
        """Issue a paid non-member key with payment tracking."""
        from tools.bits_admin.config import KeySource, KeyType
        from tools.bits_admin.registry import find_entry, generate_manifest, issue_key

        entry, created = issue_key(
            "jane@corp.com",
            private_key_b64,
            key_type=KeyType.LIFETIME,
            source=KeySource.PAID,
            payment_ref="STRIPE-pi_3abc123",
            name="Jane Doe",
            notes="Enterprise single-user. Purchased 2026-01-15.",
        )
        assert created is True
        assert entry.source == "paid"
        assert entry.payment_ref == "STRIPE-pi_3abc123"
        assert entry.expiry is None  # Lifetime

        generate_manifest()

        # Verify full detail retrieval
        found = find_entry("jane@corp.com")
        assert found is not None
        assert found.name == "Jane Doe"
        assert found.notes == "Enterprise single-user. Purchased 2026-01-15."

    def test_csv_import_keys_roundtrip(self, tmp_data_dir, private_key_b64):
        """Import keys from CSV, then export and verify."""
        from tools.bits_admin.config import KeySource, KeyType
        from tools.bits_admin.csv_ops import export_csv, parse_csv_text
        from tools.bits_admin.registry import generate_manifest, issue_key, list_entries

        csv_text = textwrap.dedent(
            """\
            email,name,type,source,payment_ref
            alice@bits.org,Alice,annual,member,
            bob@corp.com,Bob,lifetime,paid,INV-99
            charlie@example.com,Charlie,contributor,contributor,DON-50
        """
        )
        rows = parse_csv_text(csv_text)
        for row in rows:
            type_values = [e.value for e in KeyType]
            kt = KeyType(row.key_type) if row.key_type in type_values else KeyType.ANNUAL
            src_values = [e.value for e in KeySource]
            src = KeySource(row.source) if row.source in src_values else KeySource.ADMIN
            issue_key(
                row.email,
                private_key_b64,
                key_type=kt,
                source=src,
                name=row.name,
                payment_ref=row.payment_ref,
            )
        generate_manifest()

        entries = list_entries()
        assert len(entries) == 3

        # Export
        out = tmp_data_dir / "roundtrip.csv"
        count = export_csv(entries, out)
        assert count == 3

        content = out.read_text("utf-8-sig")
        assert "alice@bits.org" in content
        assert "bob@corp.com" in content
        assert "INV-99" in content

    def test_beta_compatible_with_app(self, beta_file):
        """Ensure generated beta codes are verifiable by the app's BetaService."""
        from tools.bits_admin.beta import generate_and_add, load_invitations

        results = generate_and_add(1, path=beta_file)
        code, expected_hash = results[0]

        # Simulate what BetaService.verify_invitation does
        import hashlib

        app_hash = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
        assert app_hash == expected_hash

        # Check it's in the file
        data = load_invitations(beta_file)
        assert app_hash in data["codes"]
