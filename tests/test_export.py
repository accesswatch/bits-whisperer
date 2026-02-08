"""Tests for export formatters."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult, TranscriptSegment
from bits_whisperer.export.base import format_timestamp, format_timestamp_srt
from bits_whisperer.export.plain_text import PlainTextFormatter


class TestFormatTimestamp:
    """Timestamp formatting helpers."""

    def test_zero(self) -> None:
        assert format_timestamp(0.0) == "00:00:00.000"

    def test_seconds_only(self) -> None:
        assert format_timestamp(5.5) == "00:00:05.500"

    def test_minutes_and_seconds(self) -> None:
        assert format_timestamp(125.75) == "00:02:05.750"

    def test_hours(self) -> None:
        assert format_timestamp(3661.123) == "01:01:01.123"

    def test_srt_format_uses_comma(self) -> None:
        ts = format_timestamp_srt(5.5)
        assert "," in ts
        assert "." not in ts
        assert ts == "00:00:05,500"


def _make_result(
    segments: list[TranscriptSegment] | None = None,
    full_text: str = "",
) -> TranscriptionResult:
    """Helper to create a test result."""
    return TranscriptionResult(
        job_id="test",
        audio_file="test.mp3",
        provider="test",
        model="test",
        language="en",
        duration_seconds=10.0,
        segments=segments or [],
        full_text=full_text,
    )


class TestPlainTextFormatter:
    """Plain text export."""

    def test_format_properties(self) -> None:
        fmt = PlainTextFormatter()
        assert fmt.format_id == "txt"
        assert fmt.file_extension == ".txt"
        assert "Plain Text" in fmt.display_name

    def test_export_full_text(self, tmp_path: Path) -> None:
        result = _make_result(full_text="Hello world")
        out = tmp_path / "output.txt"
        fmt = PlainTextFormatter()
        written = fmt.export(result, out)
        assert written == out
        assert out.read_text(encoding="utf-8") == "Hello world"

    def test_export_segments(self, tmp_path: Path) -> None:
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptSegment(start=2.0, end=4.0, text="World"),
        ]
        result = _make_result(segments=segments)
        out = tmp_path / "output.txt"
        fmt = PlainTextFormatter()
        fmt.export(result, out)
        content = out.read_text(encoding="utf-8")
        assert "Hello" in content
        assert "World" in content

    def test_export_with_timestamps(self, tmp_path: Path) -> None:
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
        ]
        result = _make_result(segments=segments)
        out = tmp_path / "output.txt"
        fmt = PlainTextFormatter()
        fmt.export(result, out, include_timestamps=True)
        content = out.read_text(encoding="utf-8")
        assert "[00:00:00.000]" in content
        assert "Hello" in content

    def test_export_with_speakers(self, tmp_path: Path) -> None:
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hi", speaker="Alice"),
        ]
        result = _make_result(segments=segments)
        out = tmp_path / "output.txt"
        fmt = PlainTextFormatter()
        fmt.export(result, out, include_speakers=True)
        content = out.read_text(encoding="utf-8")
        assert "Alice:" in content

    def test_export_with_confidence(self, tmp_path: Path) -> None:
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hi", confidence=0.95),
        ]
        result = _make_result(segments=segments)
        out = tmp_path / "output.txt"
        fmt = PlainTextFormatter()
        fmt.export(result, out, include_confidence=True)
        content = out.read_text(encoding="utf-8")
        assert "95%" in content
