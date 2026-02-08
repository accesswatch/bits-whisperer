"""Base class for all export formatters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from bits_whisperer.core.job import TranscriptionResult


class ExportFormatter(ABC):
    """Abstract base for transcript export formatters.

    Each formatter converts a TranscriptionResult into a specific
    file format and writes it to disk.
    """

    @property
    @abstractmethod
    def format_id(self) -> str:
        """Short identifier for this format (e.g. 'txt', 'docx')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable format name for UI display."""
        ...

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """File extension including the dot (e.g. '.txt')."""
        ...

    @abstractmethod
    def export(
        self,
        result: TranscriptionResult,
        output_path: str | Path,
        include_timestamps: bool = True,
        include_speakers: bool = True,
        include_confidence: bool = False,
    ) -> Path:
        """Export a transcript to the target format.

        Args:
            result: Transcription data to export.
            output_path: Destination file path.
            include_timestamps: Whether to include timestamps.
            include_speakers: Whether to include speaker labels.
            include_confidence: Whether to include confidence scores.

        Returns:
            Path to the written file.
        """
        ...


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds.

    Returns:
        SRT-formatted timestamp.
    """
    return format_timestamp(seconds).replace(".", ",")
