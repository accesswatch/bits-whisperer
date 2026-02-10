"""Tests for document attachments in AI actions.

Covers:
- Document reader: text extraction from various formats
- Attachment data model: serialization / deserialization
- AgentConfig with attachments: round-trip JSON
- Job model: per-job attachments field
- AI action pipeline: attachment text building
- Context manager: token budgeting with attachments
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.copilot_service import AgentConfig, Attachment
from bits_whisperer.core.document_reader import (
    SUPPORTED_EXTENSIONS,
    is_supported,
    read_document,
    read_document_safe,
)
from bits_whisperer.core.job import Job

# ======================================================================
# Document Reader Tests
# ======================================================================


class TestDocumentReaderSupport:
    """Test file extension support detection."""

    def test_supported_text_extensions(self) -> None:
        for ext in (".txt", ".md", ".csv", ".log", ".json", ".xml", ".yaml", ".yml"):
            assert is_supported(f"file{ext}"), f"{ext} should be supported"

    def test_supported_word_extensions(self) -> None:
        assert is_supported("report.docx")

    def test_supported_excel_extensions(self) -> None:
        assert is_supported("data.xlsx")
        assert is_supported("data.xls")

    def test_supported_pdf_extensions(self) -> None:
        assert is_supported("document.pdf")

    def test_supported_rtf_extensions(self) -> None:
        assert is_supported("notes.rtf")

    def test_unsupported_extensions(self) -> None:
        assert not is_supported("image.png")
        assert not is_supported("video.mp4")
        assert not is_supported("archive.zip")

    def test_case_insensitive_check(self) -> None:
        # is_supported lowercases the extension
        assert is_supported("FILE.TXT")
        assert is_supported("doc.DocX")

    def test_supported_extensions_set_is_frozen(self) -> None:
        assert isinstance(SUPPORTED_EXTENSIONS, frozenset)
        assert len(SUPPORTED_EXTENSIONS) > 10


class TestDocumentReaderTextFiles:
    """Test plain-text file reading."""

    def test_read_plain_text(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("Hello, world!\nSecond line.", encoding="utf-8")
        result = read_document(f)
        assert "Hello, world!" in result
        assert "Second line." in result

    def test_read_utf8_bom(self, tmp_path: Path) -> None:
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfBOM content")
        result = read_document(f)
        assert "BOM content" in result

    def test_read_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("name,value\nfoo,42\nbar,99", encoding="utf-8")
        result = read_document(f)
        assert "foo" in result
        assert "42" in result

    def test_read_json(self, tmp_path: Path) -> None:
        f = tmp_path / "config.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = read_document(f)
        assert '"key"' in result

    def test_read_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "README.md"
        f.write_text("# Title\n\nSome **bold** text.", encoding="utf-8")
        result = read_document(f)
        assert "# Title" in result

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_document("/nonexistent/path/file.txt")

    def test_file_too_large_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "huge.txt"
        f.write_bytes(b"x" * (11 * 1024 * 1024))  # 11 MB
        with pytest.raises(ValueError, match="too large"):
            read_document(f)


class TestDocumentReaderSafe:
    """Test the safe (non-raising) wrapper."""

    def test_safe_read_success(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.txt"
        f.write_text("safe content", encoding="utf-8")
        result = read_document_safe(f)
        assert result == "safe content"

    def test_safe_read_missing_file(self) -> None:
        result = read_document_safe("/nonexistent/file.txt")
        assert result.startswith("[Error")

    def test_safe_read_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * (11 * 1024 * 1024))
        result = read_document_safe(f)
        assert "too large" in result

    def test_safe_read_unknown_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.custom"
        f.write_text("custom format data", encoding="utf-8")
        result = read_document_safe(f)
        assert "custom format data" in result


class TestDocumentReaderDocx:
    """Test Word document reader (mocked)."""

    def test_docx_missing_library(self, tmp_path: Path) -> None:
        f = tmp_path / "test.docx"
        f.write_bytes(b"fake docx")
        with patch.dict("sys.modules", {"docx": None}):
            result = read_document_safe(f)
            assert "python-docx" in result or "Error" in result

    def test_docx_with_mock(self, tmp_path: Path) -> None:
        f = tmp_path / "test.docx"
        f.write_bytes(b"PK")  # minimal ZIP header

        mock_para = MagicMock()
        mock_para.text = "Paragraph text"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = []

        with patch(
            "bits_whisperer.core.document_reader.Document",
            return_value=mock_doc,
            create=True,
        ):
            # Import must be patched at the point of use
            import bits_whisperer.core.document_reader as dr

            with patch.object(dr, "_read_docx") as mock_read:
                mock_read.return_value = "Paragraph text"
                result = dr.read_document(f)
                assert "Paragraph text" in result


class TestDocumentReaderExcel:
    """Test Excel reader (mocked)."""

    def test_excel_missing_library(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")
        with patch.dict("sys.modules", {"openpyxl": None}):
            result = read_document_safe(f)
            assert "openpyxl" in result or "Error" in result


class TestDocumentReaderPDF:
    """Test PDF reader (mocked)."""

    def test_pdf_missing_library(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        with patch.dict("sys.modules", {"pypdf": None, "PyPDF2": None}):
            result = read_document_safe(f)
            assert "pypdf" in result or "Error" in result


# ======================================================================
# Attachment Data Model Tests
# ======================================================================


class TestAttachmentModel:
    """Test the Attachment dataclass."""

    def test_basic_creation(self) -> None:
        att = Attachment(file_path="/path/to/file.txt")
        assert att.file_path == "/path/to/file.txt"
        assert att.instructions == ""
        assert att.display_name == ""

    def test_name_property_uses_filename(self) -> None:
        att = Attachment(file_path="/docs/report.docx")
        assert att.name == "report.docx"

    def test_name_property_uses_display_name(self) -> None:
        att = Attachment(file_path="/docs/report.docx", display_name="Q4 Report")
        assert att.name == "Q4 Report"

    def test_to_dict(self) -> None:
        att = Attachment(
            file_path="/path/file.txt",
            instructions="Use as glossary",
            display_name="Glossary",
        )
        d = att.to_dict()
        assert d["file_path"] == "/path/file.txt"
        assert d["instructions"] == "Use as glossary"
        assert d["display_name"] == "Glossary"

    def test_from_dict(self) -> None:
        d = {
            "file_path": "/some/file.pdf",
            "instructions": "Reference doc",
            "display_name": "Spec",
        }
        att = Attachment.from_dict(d)
        assert att.file_path == "/some/file.pdf"
        assert att.instructions == "Reference doc"
        assert att.display_name == "Spec"

    def test_from_dict_missing_fields(self) -> None:
        att = Attachment.from_dict({"file_path": "/x.txt"})
        assert att.file_path == "/x.txt"
        assert att.instructions == ""
        assert att.display_name == ""

    def test_round_trip(self) -> None:
        original = Attachment(
            file_path="/a/b.docx",
            instructions="Cross-reference",
            display_name="Plan",
        )
        restored = Attachment.from_dict(original.to_dict())
        assert restored.file_path == original.file_path
        assert restored.instructions == original.instructions
        assert restored.display_name == original.display_name


# ======================================================================
# AgentConfig with Attachments Tests
# ======================================================================


class TestAgentConfigAttachments:
    """Test AgentConfig attachment serialization and persistence."""

    def test_default_empty_attachments(self) -> None:
        config = AgentConfig()
        assert config.attachments == []

    def test_config_with_attachments(self) -> None:
        att = Attachment(file_path="/doc.txt", instructions="Use as reference")
        config = AgentConfig(attachments=[att])
        assert len(config.attachments) == 1
        assert config.attachments[0].file_path == "/doc.txt"

    def test_to_dict_includes_attachments(self) -> None:
        att1 = Attachment(file_path="/a.txt", instructions="First")
        att2 = Attachment(file_path="/b.docx", instructions="Second")
        config = AgentConfig(attachments=[att1, att2])
        d = config.to_dict()
        assert "attachments" in d
        assert len(d["attachments"]) == 2
        assert d["attachments"][0]["file_path"] == "/a.txt"
        assert d["attachments"][1]["instructions"] == "Second"

    def test_from_dict_deserializes_attachments(self) -> None:
        d = {
            "name": "Test Agent",
            "attachments": [
                {"file_path": "/x.txt", "instructions": "Glossary", "display_name": ""},
                {"file_path": "/y.pdf", "instructions": "", "display_name": "Spec"},
            ],
        }
        config = AgentConfig.from_dict(d)
        assert len(config.attachments) == 2
        assert isinstance(config.attachments[0], Attachment)
        assert config.attachments[0].instructions == "Glossary"
        assert config.attachments[1].display_name == "Spec"

    def test_from_dict_empty_attachments(self) -> None:
        config = AgentConfig.from_dict({"attachments": []})
        assert config.attachments == []

    def test_from_dict_no_attachments_key(self) -> None:
        config = AgentConfig.from_dict({"name": "No Attachments"})
        assert config.attachments == []

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        att = Attachment(
            file_path="/docs/guide.pdf",
            instructions="Style guide reference",
            display_name="Style Guide",
        )
        config = AgentConfig(
            name="Test Template",
            attachments=[att],
        )

        path = tmp_path / "template.json"
        config.save(path)

        loaded = AgentConfig.load(path)
        assert loaded.name == "Test Template"
        assert len(loaded.attachments) == 1
        assert loaded.attachments[0].file_path == "/docs/guide.pdf"
        assert loaded.attachments[0].instructions == "Style guide reference"
        assert loaded.attachments[0].display_name == "Style Guide"

    def test_json_structure(self, tmp_path: Path) -> None:
        att = Attachment(file_path="/test.txt", instructions="test instructions")
        config = AgentConfig(attachments=[att])
        path = tmp_path / "cfg.json"
        config.save(path)

        raw = json.loads(path.read_text("utf-8"))
        assert "attachments" in raw
        assert raw["attachments"][0]["file_path"] == "/test.txt"
        assert raw["attachments"][0]["instructions"] == "test instructions"

    def test_backward_compatibility(self, tmp_path: Path) -> None:
        """Old config files without attachments should load fine."""
        old_data = {
            "name": "Legacy Agent",
            "instructions": "Do stuff",
            "model": "gpt-4o",
            "temperature": 0.5,
            "max_tokens": 2048,
        }
        path = tmp_path / "legacy.json"
        path.write_text(json.dumps(old_data), encoding="utf-8")

        config = AgentConfig.load(path)
        assert config.name == "Legacy Agent"
        assert config.attachments == []


# ======================================================================
# Job Model Attachment Tests
# ======================================================================


class TestJobAttachments:
    """Test per-job attachment field."""

    def test_default_empty(self) -> None:
        job = Job()
        assert job.ai_action_attachments == []

    def test_job_with_attachments(self) -> None:
        job = Job(
            ai_action_attachments=[
                {"file_path": "/extra.txt", "instructions": "Additional notes"},
            ]
        )
        assert len(job.ai_action_attachments) == 1
        assert job.ai_action_attachments[0]["file_path"] == "/extra.txt"


# ======================================================================
# Attachments Text Building Tests
# ======================================================================


class TestBuildAttachmentsText:
    """Test TranscriptionService._build_attachments_text."""

    def _make_service(self):
        """Create a minimal TranscriptionService for testing."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        svc = TranscriptionService.__new__(TranscriptionService)
        svc._app_settings = None
        svc._key_store = None
        return svc

    def test_no_attachments_returns_empty(self) -> None:
        svc = self._make_service()
        job = Job()
        result = svc._build_attachments_text("Meeting Minutes", job)
        assert result == ""

    def test_per_job_attachment_text(self, tmp_path: Path) -> None:
        svc = self._make_service()
        doc = tmp_path / "notes.txt"
        doc.write_text("Important notes content", encoding="utf-8")

        job = Job(
            ai_action_attachments=[
                {"file_path": str(doc), "instructions": "Reference notes", "display_name": "Notes"},
            ]
        )
        result = svc._build_attachments_text("Meeting Minutes", job)
        assert "Important notes content" in result
        assert "Reference notes" in result
        assert "Notes" in result

    def test_template_attachments(self, tmp_path: Path) -> None:
        svc = self._make_service()

        # Create a referenced document
        ref_doc = tmp_path / "glossary.txt"
        ref_doc.write_text("Term1: Definition1\nTerm2: Definition2", encoding="utf-8")

        # Create AgentConfig template with attachment
        att = Attachment(
            file_path=str(ref_doc),
            instructions="Use as glossary",
            display_name="Glossary",
        )
        config = AgentConfig(name="Test", attachments=[att])
        template_path = tmp_path / "template.json"
        config.save(template_path)

        job = Job()
        result = svc._build_attachments_text(str(template_path), job)
        assert "Term1: Definition1" in result
        assert "Use as glossary" in result
        assert "Glossary" in result

    def test_combined_template_and_job_attachments(self, tmp_path: Path) -> None:
        svc = self._make_service()

        # Template attachment
        tmpl_doc = tmp_path / "template_ref.txt"
        tmpl_doc.write_text("Template content", encoding="utf-8")
        config = AgentConfig(
            attachments=[Attachment(file_path=str(tmpl_doc), instructions="From template")],
        )
        tpl = tmp_path / "tpl.json"
        config.save(tpl)

        # Job attachment
        job_doc = tmp_path / "job_ref.txt"
        job_doc.write_text("Job content", encoding="utf-8")
        job = Job(
            ai_action_attachments=[
                {"file_path": str(job_doc), "instructions": "From job"},
            ]
        )

        result = svc._build_attachments_text(str(tpl), job)
        assert "Template content" in result
        assert "Job content" in result
        assert "From template" in result
        assert "From job" in result

    def test_missing_file_returns_error_text(self) -> None:
        svc = self._make_service()
        job = Job(
            ai_action_attachments=[
                {"file_path": "/nonexistent/file.txt", "instructions": ""},
            ]
        )
        result = svc._build_attachments_text("Meeting Minutes", job)
        assert "[Error" in result

    def test_formatting_structure(self, tmp_path: Path) -> None:
        svc = self._make_service()
        doc = tmp_path / "doc.txt"
        doc.write_text("Content here", encoding="utf-8")
        job = Job(
            ai_action_attachments=[
                {
                    "file_path": str(doc),
                    "instructions": "My instructions",
                    "display_name": "My Doc",
                },
            ]
        )
        result = svc._build_attachments_text("Meeting Minutes", job)
        assert "=== Document: My Doc ===" in result
        assert "Instructions: My instructions" in result
        assert "Content here" in result
        assert "=== End: My Doc ===" in result


# ======================================================================
# Context Manager with Attachments Tests
# ======================================================================


class TestContextManagerAttachments:
    """Test prepare_action_context with attachments_text parameter."""

    def _make_manager(self):
        from bits_whisperer.core.context_manager import ContextWindowManager, ContextWindowSettings

        settings = ContextWindowSettings()
        return ContextWindowManager(settings)

    def test_empty_attachments(self) -> None:
        mgr = self._make_manager()
        result = mgr.prepare_action_context(
            instructions="Summarize the transcript.",
            transcript="Speaker 1: Hello.\nSpeaker 2: Hi.",
            attachments_text="",
        )
        assert result.fitted_transcript  # transcript is returned
        assert result.budget.system_prompt_tokens > 0

    def test_attachments_consume_budget(self) -> None:
        mgr = self._make_manager()
        long_attachment = "Reference data: " + "x" * 5000

        result_no_att = mgr.prepare_action_context(
            instructions="Summarize.",
            transcript="Hello world. " * 1000,
            attachments_text="",
        )
        result_with_att = mgr.prepare_action_context(
            instructions="Summarize.",
            transcript="Hello world. " * 1000,
            attachments_text=long_attachment,
        )

        # With attachments, less budget should be available for transcript
        assert (
            result_with_att.budget.transcript_budget_tokens
            < result_no_att.budget.transcript_budget_tokens
        )

    def test_attachments_in_system_prompt_tokens(self) -> None:
        mgr = self._make_manager()
        attachment_text = "Glossary: term1 = definition1, term2 = definition2"

        result = mgr.prepare_action_context(
            instructions="Analyze the transcript.",
            transcript="Speaker: Content.",
            attachments_text=attachment_text,
        )

        # System prompt tokens should include both instructions + attachments
        result_no_att = mgr.prepare_action_context(
            instructions="Analyze the transcript.",
            transcript="Speaker: Content.",
            attachments_text="",
        )
        assert result.budget.system_prompt_tokens > result_no_att.budget.system_prompt_tokens
