"""Markdown export formatter."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter, format_timestamp


class MarkdownFormatter(ExportFormatter):
    """Export transcript as a formatted Markdown document."""

    @property
    def format_id(self) -> str:
        return "md"

    @property
    def display_name(self) -> str:
        return "Markdown (.md)"

    @property
    def file_extension(self) -> str:
        return ".md"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as Markdown.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Include timestamp blockquotes.
            include_speakers: Include speaker headings.
            include_confidence: Append confidence.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        lines: list[str] = []

        # Title
        lines.append(f"# Transcript: {result.audio_file}")
        lines.append("")
        lines.append(f"- **Provider**: {result.provider}")
        lines.append(f"- **Model**: {result.model}")
        lines.append(f"- **Language**: {result.language}")
        lines.append(f"- **Duration**: {format_timestamp(result.duration_seconds)}")
        lines.append(f"- **Date**: {result.created_at}")
        lines.append("")
        lines.append("---")
        lines.append("")

        if result.segments:
            current_speaker = ""
            for seg in result.segments:
                if include_speakers and seg.speaker and seg.speaker != current_speaker:
                    current_speaker = seg.speaker
                    lines.append(f"### {seg.speaker}")
                    lines.append("")

                if include_timestamps:
                    lines.append(
                        f"> *{format_timestamp(seg.start)} — " f"{format_timestamp(seg.end)}*"
                    )

                text = seg.text
                if include_confidence and seg.confidence > 0:
                    text += f" _{seg.confidence:.0%}_"
                lines.append(text)
                lines.append("")
        else:
            lines.append(result.full_text)

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
