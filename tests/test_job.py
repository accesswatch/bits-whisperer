"""Tests for the Job data model."""

from __future__ import annotations

from bits_whisperer.core.job import (
    Job,
    JobStatus,
    TranscriptionResult,
    TranscriptSegment,
)


class TestJobStatus:
    """JobStatus enum values."""

    def test_all_statuses_exist(self) -> None:
        expected = {"pending", "transcoding", "transcribing", "completed", "failed", "cancelled"}
        actual = {s.value for s in JobStatus}
        assert actual == expected

    def test_enum_values_lowercase(self) -> None:
        for status in JobStatus:
            assert status.value == status.value.lower()


class TestTranscriptSegment:
    """TranscriptSegment dataclass."""

    def test_defaults(self) -> None:
        seg = TranscriptSegment(start=0.0, end=1.0, text="hello")
        assert seg.confidence == 0.0
        assert seg.speaker == ""

    def test_all_fields(self) -> None:
        seg = TranscriptSegment(
            start=1.5, end=3.2, text="world", confidence=0.95, speaker="Speaker 1"
        )
        assert seg.start == 1.5
        assert seg.end == 3.2
        assert seg.text == "world"
        assert seg.confidence == 0.95
        assert seg.speaker == "Speaker 1"


class TestTranscriptionResult:
    """TranscriptionResult dataclass and serialization."""

    def _make_result(self) -> TranscriptionResult:
        return TranscriptionResult(
            job_id="test-id",
            audio_file="test.mp3",
            provider="local_whisper",
            model="base",
            language="en",
            duration_seconds=60.0,
            segments=[
                TranscriptSegment(start=0.0, end=2.0, text="Hello", confidence=0.9),
                TranscriptSegment(start=2.0, end=5.0, text="world", confidence=0.8),
            ],
            full_text="Hello world",
            created_at="2025-01-01T00:00:00",
        )

    def test_to_dict_keys(self) -> None:
        result = self._make_result()
        d = result.to_dict()
        expected_keys = {
            "job_id",
            "audio_file",
            "provider",
            "model",
            "language",
            "duration_seconds",
            "created_at",
            "segments",
            "full_text",
            "speaker_map",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_segments(self) -> None:
        result = self._make_result()
        d = result.to_dict()
        assert len(d["segments"]) == 2
        seg = d["segments"][0]
        assert seg["text"] == "Hello"
        assert seg["start"] == 0.0
        assert seg["end"] == 2.0
        assert seg["confidence"] == 0.9

    def test_empty_result(self) -> None:
        result = TranscriptionResult(
            job_id="empty", audio_file="", provider="", model="", language="", duration_seconds=0
        )
        d = result.to_dict()
        assert d["segments"] == []
        assert d["full_text"] == ""


class TestJob:
    """Job dataclass and properties."""

    def test_defaults(self) -> None:
        job = Job()
        assert job.status == JobStatus.PENDING
        assert job.language == "auto"
        assert job.progress_percent == 0.0
        assert job.include_timestamps is True
        assert job.include_diarization is False
        assert job.result is None

    def test_unique_ids(self) -> None:
        j1 = Job()
        j2 = Job()
        assert j1.id != j2.id

    def test_display_name_from_file_name(self) -> None:
        job = Job(file_name="interview.mp3", file_path="/path/to/interview.mp3")
        assert job.display_name == "interview.mp3"

    def test_display_name_from_path(self) -> None:
        job = Job(file_path="/path/to/recording.wav")
        assert job.display_name == "recording.wav"

    def test_status_text_pending(self) -> None:
        job = Job()
        assert job.status_text == "Pending"

    def test_status_text_transcribing_with_progress(self) -> None:
        job = Job(status=JobStatus.TRANSCRIBING, progress_percent=42.5)
        assert job.status_text == "Transcribing (42%)"

    def test_status_text_completed(self) -> None:
        job = Job(status=JobStatus.COMPLETED)
        assert job.status_text == "Completed"

    def test_cost_display_free(self) -> None:
        job = Job()
        assert job.cost_display == "Free"

    def test_cost_display_with_estimate(self) -> None:
        job = Job(cost_estimate=0.0123)
        assert job.cost_display == "~$0.0123"
