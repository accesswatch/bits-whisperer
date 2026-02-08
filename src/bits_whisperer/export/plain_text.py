"""Plain text export formatter."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter, format_timestamp


class PlainTextFormatter(ExportFormatter):
    """Export transcript as a simple plain-text file."""

    @property
    def format_id(self) -> str:
        return "txt"

    @property
    def display_name(self) -> str:
        return "Plain Text (.txt)"

    @property
    def file_extension(self) -> str:
        return ".txt"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = False,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as plain text.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Prefix lines with timestamps.
            include_speakers: Include speaker labels.
            include_confidence: Append confidence scores.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        lines: list[str] = []

        if result.segments:
            for seg in result.segments:
                parts: list[str] = []
                if include_timestamps:
                    parts.append(f"[{format_timestamp(seg.start)}]")
                if include_speakers and seg.speaker:
                    parts.append(f"{seg.speaker}:")
                parts.append(seg.text)
                if include_confidence and seg.confidence > 0:
                    parts.append(f"({seg.confidence:.0%})")
                lines.append(" ".join(parts))
        else:
            lines.append(result.full_text)

        output_path.write_text("\n\n".join(lines), encoding="utf-8")
        return output_path
