"""WebVTT (.vtt) subtitle export formatter."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter


class VTTFormatter(ExportFormatter):
    """Export transcript as WebVTT (.vtt) subtitle format."""

    @property
    def format_id(self) -> str:
        return "vtt"

    @property
    def display_name(self) -> str:
        return "WebVTT Subtitles (.vtt)"

    @property
    def file_extension(self) -> str:
        return ".vtt"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as a WebVTT subtitle file.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Ignored (always present in VTT).
            include_speakers: Prepend speaker labels.
            include_confidence: Ignored for VTT format.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        lines: list[str] = ["WEBVTT", ""]

        if result.segments:
            for idx, seg in enumerate(result.segments, start=1):
                lines.append(str(idx))
                lines.append(f"{_vtt_ts(seg.start)} --> {_vtt_ts(seg.end)}")
                text = seg.text
                if include_speakers and seg.speaker:
                    text = f"<v {seg.speaker}>{text}"
                lines.append(text)
                lines.append("")
        else:
            lines.append("1")
            lines.append(f"{_vtt_ts(0)} --> {_vtt_ts(result.duration_seconds)}")
            lines.append(result.full_text)
            lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


def _vtt_ts(seconds: float) -> str:
    """Format seconds as VTT timestamp HH:MM:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
