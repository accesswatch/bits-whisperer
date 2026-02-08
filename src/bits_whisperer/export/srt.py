"""SubRip (.srt) subtitle export formatter."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter, format_timestamp_srt


class SRTFormatter(ExportFormatter):
    """Export transcript as SubRip (.srt) subtitle format."""

    @property
    def format_id(self) -> str:
        return "srt"

    @property
    def display_name(self) -> str:
        return "SubRip Subtitles (.srt)"

    @property
    def file_extension(self) -> str:
        return ".srt"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as an SRT subtitle file.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Ignored (always included in SRT).
            include_speakers: Prepend speaker label to subtitle text.
            include_confidence: Ignored for SRT format.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        lines: list[str] = []

        if result.segments:
            for idx, seg in enumerate(result.segments, start=1):
                lines.append(str(idx))
                lines.append(
                    f"{format_timestamp_srt(seg.start)} --> {format_timestamp_srt(seg.end)}"
                )
                text = seg.text
                if include_speakers and seg.speaker:
                    text = f"[{seg.speaker}] {text}"
                lines.append(text)
                lines.append("")  # blank line between cues
        else:
            # Fallback: single cue spanning full duration
            lines.append("1")
            lines.append(
                f"{format_timestamp_srt(0)} --> " f"{format_timestamp_srt(result.duration_seconds)}"
            )
            lines.append(result.full_text)
            lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
