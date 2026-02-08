"""JSON export formatter."""

from __future__ import annotations

import json
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult
from bits_whisperer.export.base import ExportFormatter


class JSONFormatter(ExportFormatter):
    """Export transcript as structured JSON."""

    @property
    def format_id(self) -> str:
        return "json"

    @property
    def display_name(self) -> str:
        return "JSON Data (.json)"

    @property
    def file_extension(self) -> str:
        return ".json"

    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export transcript as a JSON file.

        Args:
            result: Transcription data.
            output_path: Destination file path.
            include_timestamps: Include start/end in segment objects.
            include_speakers: Include speaker field in segment objects.
            include_confidence: Include confidence field in segment objects.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)

        data = result.to_dict()

        # Optionally strip fields
        if not include_timestamps:
            for seg in data.get("segments", []):
                seg.pop("start", None)
                seg.pop("end", None)
        if not include_speakers:
            for seg in data.get("segments", []):
                seg.pop("speaker", None)
        if not include_confidence:
            for seg in data.get("segments", []):
                seg.pop("confidence", None)

        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return output_path
