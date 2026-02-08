"""Job data model for transcription jobs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(Enum):
    """Lifecycle states for a transcription job."""

    PENDING = "pending"
    TRANSCODING = "transcoding"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranscriptSegment:
    """A single segment of transcription output."""

    start: float
    end: float
    text: str
    confidence: float = 0.0
    speaker: str = ""


@dataclass
class TranscriptionResult:
    """Complete transcription output for a job."""

    job_id: str
    audio_file: str
    provider: str
    model: str
    language: str
    duration_seconds: float
    segments: list[TranscriptSegment] = field(default_factory=list)
    full_text: str = ""
    created_at: str = ""
    speaker_map: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON export."""
        return {
            "job_id": self.job_id,
            "audio_file": self.audio_file,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "confidence": s.confidence,
                    "speaker": s.speaker,
                }
                for s in self.segments
            ],
            "full_text": self.full_text,
            "speaker_map": dict(self.speaker_map),
        }


@dataclass
class Job:
    """Represents a transcription job in the queue."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    file_name: str = ""
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    status: JobStatus = JobStatus.PENDING
    provider: str = ""
    model: str = ""
    language: str = "auto"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""
    progress_percent: float = 0.0
    cost_estimate: float = 0.0
    cost_actual: float = 0.0
    transcript_path: str = ""
    error_message: str = ""
    include_timestamps: bool = True
    include_diarization: bool = False
    result: TranscriptionResult | None = None

    @property
    def display_name(self) -> str:
        """Human-readable name for display in the queue."""
        return self.file_name or Path(self.file_path).name

    @property
    def status_text(self) -> str:
        """Human-readable status string."""
        if self.status == JobStatus.TRANSCRIBING and self.progress_percent > 0:
            return f"Transcribing ({self.progress_percent:.0f}%)"
        return self.status.value.capitalize()

    @property
    def cost_display(self) -> str:
        """Formatted cost string."""
        if self.cost_estimate > 0:
            return f"~${self.cost_estimate:.4f}"
        return "Free"
