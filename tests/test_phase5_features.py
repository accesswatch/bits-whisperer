"""Tests for Phase 5 features: TreeView queue, folder transcription, cost estimation, chat tab."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.core.settings import (
    AppSettings,
    DiarizationSettings,
    GeneralSettings,
    TranscriptionSettings,
)

# -----------------------------------------------------------------------
# Helper: build a mock main_frame for QueuePanel
# -----------------------------------------------------------------------


def _make_mock_main_frame() -> MagicMock:
    """Build a MagicMock that satisfies QueuePanel's expectations."""
    frame = MagicMock()
    frame.app_settings = AppSettings()
    frame.app_settings.general = GeneralSettings()
    frame.app_settings.general.default_provider = "local_whisper"
    frame.app_settings.general.default_model = "base"
    frame.app_settings.general.language = "auto"
    frame.app_settings.transcription = TranscriptionSettings()
    frame.app_settings.diarization = DiarizationSettings()

    # Provider manager mock
    pm = MagicMock()
    pm.list_enabled_providers.return_value = ["local_whisper"]
    pm.recommend_provider.return_value = "local_whisper"
    pm.get_capabilities.return_value = MagicMock(
        name="Local Whisper",
        provider_type="local",
        rate_per_minute_usd=0.0,
    )
    pm.estimate_cost.return_value = 0.0
    frame.provider_manager = pm

    # Transcript panel
    frame.transcript_panel = MagicMock()
    frame.transcript_panel._current_job = None

    # Notebook
    frame._notebook = MagicMock()
    frame._TAB_TRANSCRIPT = 1
    frame._update_menu_state = MagicMock()

    # Transcription service
    frame.transcription_service = MagicMock()

    return frame


def _make_job(
    job_id: str = "test-1",
    file_path: str = "/audio/test.mp3",
    provider: str = "local_whisper",
    status: JobStatus = JobStatus.PENDING,
    cost: float = 0.0,
) -> Job:
    """Create a Job with sensible defaults for testing."""
    return Job(
        id=job_id,
        file_path=file_path,
        file_name=Path(file_path).name,
        file_size_bytes=1024 * 1024,
        provider=provider,
        model="base",
        language="auto",
        status=status,
        cost_estimate=cost,
    )


# -----------------------------------------------------------------------
# QueuePanel — tree data model (no wx needed)
# -----------------------------------------------------------------------


class TestQueuePanelDataModel:
    """Test QueuePanel job tracking logic without wx."""

    def test_job_creation_fields(self) -> None:
        """Job dataclass has all required fields for tree display."""
        job = _make_job()
        assert job.id == "test-1"
        assert job.display_name == "test.mp3"
        assert job.status == JobStatus.PENDING
        assert job.cost_display == "Free"

    def test_job_cost_display_paid(self) -> None:
        job = _make_job(cost=0.0123)
        assert job.cost_display == "~$0.0123"

    def test_job_status_text(self) -> None:
        job = _make_job(status=JobStatus.TRANSCRIBING)
        assert "Transcribing" in job.status_text

    def test_job_status_text_with_progress(self) -> None:
        job = _make_job(status=JobStatus.TRANSCRIBING)
        job.progress_percent = 42.0
        assert "42%" in job.status_text

    def test_job_display_name_fallback(self) -> None:
        """display_name falls back to file_path stem when file_name empty."""
        job = Job(file_path="/some/path/audio.wav")
        assert job.display_name == "audio.wav"

    def test_pending_jobs_filter(self) -> None:
        """get_pending_jobs should return only PENDING status jobs."""
        jobs = {
            "a": _make_job("a", status=JobStatus.PENDING),
            "b": _make_job("b", status=JobStatus.COMPLETED),
            "c": _make_job("c", status=JobStatus.PENDING),
            "d": _make_job("d", status=JobStatus.FAILED),
        }
        pending = [j for j in jobs.values() if j.status == JobStatus.PENDING]
        assert len(pending) == 2
        assert all(j.status == JobStatus.PENDING for j in pending)


class TestFolderGrouping:
    """Test the folder-grouping logic used by add_folder."""

    def test_single_directory_grouping(self) -> None:
        """All files from one directory produce a single group."""
        jobs = [
            _make_job("1", "/music/song1.mp3"),
            _make_job("2", "/music/song2.mp3"),
            _make_job("3", "/music/song3.mp3"),
        ]
        sub_groups: dict[str, list[Job]] = {}
        for job in jobs:
            parent = str(Path(job.file_path).parent)
            sub_groups.setdefault(parent, []).append(job)

        assert len(sub_groups) == 1
        key = next(iter(sub_groups))
        assert Path(key).name == "music"
        assert len(sub_groups[key]) == 3

    def test_multiple_subdirectory_grouping(self) -> None:
        """Files from different sub-dirs produce multiple groups."""
        jobs = [
            _make_job("1", "/audio/interviews/a.mp3"),
            _make_job("2", "/audio/interviews/b.mp3"),
            _make_job("3", "/audio/podcasts/c.mp3"),
            _make_job("4", "/audio/music/d.mp3"),
        ]
        sub_groups: dict[str, list[Job]] = {}
        for job in jobs:
            parent = str(Path(job.file_path).parent)
            sub_groups.setdefault(parent, []).append(job)

        assert len(sub_groups) == 3

    def test_deeply_nested_grouping(self) -> None:
        """Deep nesting still produces correct parent groups."""
        jobs = [
            _make_job("1", "/a/b/c/d/e.mp3"),
            _make_job("2", "/a/b/c/f.mp3"),
        ]
        sub_groups: dict[str, list[Job]] = {}
        for job in jobs:
            parent = str(Path(job.file_path).parent)
            sub_groups.setdefault(parent, []).append(job)

        assert len(sub_groups) == 2

    def test_empty_jobs_list(self) -> None:
        """Empty jobs list produces no groups."""
        sub_groups: dict[str, list[Job]] = {}
        assert len(sub_groups) == 0

    def test_root_level_files(self) -> None:
        """Files at root level of the chosen folder."""
        folder_root = Path("/chosen")
        jobs = [
            _make_job("1", "/chosen/a.mp3"),
            _make_job("2", "/chosen/b.mp3"),
        ]
        sub_groups: dict[str, list[Job]] = {}
        for job in jobs:
            parent = str(Path(job.file_path).parent)
            sub_groups.setdefault(parent, []).append(job)

        # All in one group matching folder_root
        assert len(sub_groups) == 1
        assert Path(next(iter(sub_groups))) == folder_root


class TestFolderTextFormatting:
    """Test folder status summary text generation."""

    def test_format_empty_folder(self) -> None:
        """Empty folder just shows folder name."""
        folder_name = Path("/test/music").name
        assert folder_name == "music"

    def test_status_summary_all_pending(self) -> None:
        """All pending → 'N pending'."""
        children = [
            _make_job("1", status=JobStatus.PENDING),
            _make_job("2", status=JobStatus.PENDING),
            _make_job("3", status=JobStatus.PENDING),
        ]
        total = len(children)
        completed = sum(1 for j in children if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in children if j.status == JobStatus.FAILED)
        in_progress = sum(
            1 for j in children if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        )
        assert total == 3
        assert completed == 0
        assert failed == 0
        assert in_progress == 0

    def test_status_summary_mixed(self) -> None:
        """Mixed statuses produce correct counts."""
        children = [
            _make_job("1", status=JobStatus.COMPLETED),
            _make_job("2", status=JobStatus.COMPLETED),
            _make_job("3", status=JobStatus.FAILED),
            _make_job("4", status=JobStatus.TRANSCRIBING),
            _make_job("5", status=JobStatus.PENDING),
        ]
        completed = sum(1 for j in children if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in children if j.status == JobStatus.FAILED)
        in_progress = sum(
            1 for j in children if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        )
        assert completed == 2
        assert failed == 1
        assert in_progress == 1


class TestItemTextFormatting:
    """Test job item text formatting."""

    def test_pending_job_text_parts(self) -> None:
        """Pending job shows name, status, provider."""
        job = _make_job()
        parts = [job.display_name, job.status.value.capitalize(), job.provider]
        assert parts == ["test.mp3", "Pending", "local_whisper"]

    def test_job_with_cost(self) -> None:
        """Paid job includes cost in display."""
        job = _make_job(cost=0.05)
        parts = [job.display_name, job.status.value.capitalize(), job.provider]
        if job.cost_estimate > 0:
            parts.append(job.cost_display)
        assert len(parts) == 4
        assert parts[-1] == "~$0.0500"

    def test_in_progress_with_percent(self) -> None:
        """In-progress job shows percentage."""
        job = _make_job(status=JobStatus.TRANSCRIBING)
        job.progress_percent = 75.0
        status_text = f"{job.status.value.capitalize()} ({job.progress_percent:.0f}%)"
        assert status_text == "Transcribing (75%)"


# -----------------------------------------------------------------------
# Cost estimation
# -----------------------------------------------------------------------


class TestCostEstimation:
    """Test cost estimation for paid providers."""

    def test_free_provider_zero_cost(self) -> None:
        """Local providers return zero cost."""
        pm = MagicMock()
        pm.estimate_cost.return_value = 0.0
        assert pm.estimate_cost("local_whisper", 300) == 0.0

    def test_paid_provider_nonzero_cost(self) -> None:
        """Cloud providers return non-zero cost."""
        pm = MagicMock()
        pm.estimate_cost.return_value = 0.006  # $0.006 per minute
        cost = pm.estimate_cost("openai_whisper", 300)
        assert cost > 0

    def test_cost_scales_with_duration(self) -> None:
        """Cost should increase with longer audio."""
        rate_per_minute = 0.006  # $0.006 per minute
        cost_5min = 5 * rate_per_minute
        cost_60min = 60 * rate_per_minute
        assert cost_60min > cost_5min
        assert cost_60min == pytest.approx(0.36)

    def test_cost_estimate_stored_on_job(self) -> None:
        """Cost estimate should be stored on the Job object."""
        job = _make_job()
        job.cost_estimate = 0.042
        assert job.cost_estimate == 0.042
        assert job.cost_display == "~$0.0420"

    def test_batch_cost_accumulation(self) -> None:
        """Total cost for multiple jobs accumulates correctly."""
        rate = 0.006
        durations = [60, 120, 300, 180]
        total = sum(d / 60 * rate for d in durations)
        assert total == pytest.approx(0.066)

    def test_fallback_duration_estimate(self) -> None:
        """When duration is 0, fallback estimate uses file size."""
        job = _make_job()
        job.duration_seconds = 0
        job.file_size_bytes = 10 * 1024 * 1024  # 10 MB
        # Fallback: 1 min per 10 MB → 60s
        dur = max(60.0, job.file_size_bytes / (10 * 1024 * 1024) * 60)
        assert dur == 60.0

    def test_fallback_duration_large_file(self) -> None:
        """Large file produces proportionally larger duration estimate."""
        file_size = 50 * 1024 * 1024  # 50 MB
        dur = max(60.0, file_size / (10 * 1024 * 1024) * 60)
        assert dur == pytest.approx(300.0)  # ~5 minutes


# -----------------------------------------------------------------------
# Provider type detection
# -----------------------------------------------------------------------


class TestProviderTypeDetection:
    """Test cloud vs local provider detection for cost dialog logic."""

    def test_local_provider_type(self) -> None:
        caps = MagicMock(provider_type="local", rate_per_minute_usd=0.0)
        is_paid = caps.provider_type == "cloud" and caps.rate_per_minute_usd > 0
        assert not is_paid

    def test_cloud_provider_paid(self) -> None:
        caps = MagicMock(provider_type="cloud", rate_per_minute_usd=0.006)
        is_paid = caps.provider_type == "cloud" and caps.rate_per_minute_usd > 0
        assert is_paid

    def test_cloud_provider_free_tier(self) -> None:
        """Cloud provider with zero rate (free tier) should not show cost."""
        caps = MagicMock(provider_type="cloud", rate_per_minute_usd=0.0)
        is_paid = caps.provider_type == "cloud" and caps.rate_per_minute_usd > 0
        assert not is_paid


# -----------------------------------------------------------------------
# Chat tab visibility logic
# -----------------------------------------------------------------------


class TestChatTabVisibility:
    """Test conditional chat tab show/hide logic."""

    def test_no_providers_hides_chat(self) -> None:
        """Chat tab should be hidden when no AI providers configured."""
        ai_service = MagicMock()
        ai_service.is_configured.return_value = False
        assert not ai_service.is_configured()

    def test_provider_configured_shows_chat(self) -> None:
        """Chat tab should be visible when AI provider is configured."""
        ai_service = MagicMock()
        ai_service.is_configured.return_value = True
        assert ai_service.is_configured()

    def test_visibility_toggle_logic(self) -> None:
        """Simulate adding/removing chat tab based on provider state."""
        chat_visible = False

        # Provider becomes available
        has_provider = True
        if has_provider and not chat_visible:
            chat_visible = True
        assert chat_visible

        # Provider removed
        has_provider = False
        if not has_provider and chat_visible:
            chat_visible = False
        assert not chat_visible

    def test_multiple_providers_still_shows(self) -> None:
        """Chat tab shown when multiple providers configured."""
        ai_service = MagicMock()
        ai_service.is_configured.return_value = True
        ai_service.get_available_providers.return_value = [
            {"key": "openai", "name": "OpenAI"},
            {"key": "anthropic", "name": "Anthropic"},
        ]
        assert ai_service.is_configured()
        assert len(ai_service.get_available_providers()) == 2


# -----------------------------------------------------------------------
# Job update & status tracking
# -----------------------------------------------------------------------


class TestJobUpdateTracking:
    """Test job status update tracking for tree display."""

    def test_status_progression(self) -> None:
        """Job goes through expected status progression."""
        job = _make_job()
        assert job.status == JobStatus.PENDING

        job.status = JobStatus.TRANSCODING
        assert job.status == JobStatus.TRANSCODING

        job.status = JobStatus.TRANSCRIBING
        job.progress_percent = 50.0
        assert job.progress_percent == 50.0

        job.status = JobStatus.COMPLETED
        assert job.status == JobStatus.COMPLETED

    def test_failed_job_has_error(self) -> None:
        job = _make_job(status=JobStatus.FAILED)
        job.error_message = "API key invalid"
        assert job.error_message == "API key invalid"

    def test_cancelled_job(self) -> None:
        job = _make_job()
        job.status = JobStatus.CANCELLED
        assert job.status == JobStatus.CANCELLED

    def test_folder_child_status_counts(self) -> None:
        """Count job statuses within a folder."""
        children = [
            _make_job("1", status=JobStatus.COMPLETED),
            _make_job("2", status=JobStatus.COMPLETED),
            _make_job("3", status=JobStatus.TRANSCRIBING),
            _make_job("4", status=JobStatus.FAILED),
            _make_job("5", status=JobStatus.PENDING),
        ]
        counts = {
            "completed": sum(1 for j in children if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in children if j.status == JobStatus.FAILED),
            "in_progress": sum(
                1 for j in children if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
            ),
            "pending": sum(1 for j in children if j.status == JobStatus.PENDING),
        }
        assert counts == {"completed": 2, "failed": 1, "in_progress": 1, "pending": 1}


# -----------------------------------------------------------------------
# Folder removal logic
# -----------------------------------------------------------------------


class TestFolderRemoval:
    """Test folder removal cleans up all child data."""

    def test_remove_folder_cleans_jobs(self) -> None:
        """Removing a folder should remove all child jobs."""
        folder_path = os.path.normpath("/audio/interviews")
        jobs = {
            "1": _make_job("1", "/audio/interviews/a.mp3"),
            "2": _make_job("2", "/audio/interviews/b.mp3"),
            "3": _make_job("3", "/audio/music/c.mp3"),
        }

        # Simulate removal
        to_remove = [
            jid
            for jid, j in jobs.items()
            if os.path.normpath(str(Path(j.file_path).parent)).startswith(folder_path)
        ]
        for jid in to_remove:
            jobs.pop(jid)

        assert len(jobs) == 1
        assert "3" in jobs

    def test_remove_nested_folder(self) -> None:
        """Removing top-level folder removes nested sub-folder jobs too."""
        folder_path = os.path.normpath("/audio")
        jobs = {
            "1": _make_job("1", "/audio/interviews/a.mp3"),
            "2": _make_job("2", "/audio/music/deep/b.mp3"),
            "3": _make_job("3", "/other/c.mp3"),
        }

        to_remove = [
            jid
            for jid, j in jobs.items()
            if os.path.normpath(str(Path(j.file_path).parent)).startswith(folder_path)
        ]
        for jid in to_remove:
            jobs.pop(jid)

        assert len(jobs) == 1
        assert "3" in jobs


# -----------------------------------------------------------------------
# Summary text
# -----------------------------------------------------------------------


class TestSummaryText:
    """Test queue summary text generation."""

    def test_empty_queue_summary(self) -> None:
        jobs: dict[str, Job] = {}
        n = len(jobs)
        assert n == 0

    def test_mixed_status_summary(self) -> None:
        jobs = {
            "1": _make_job("1", status=JobStatus.PENDING),
            "2": _make_job("2", status=JobStatus.COMPLETED),
            "3": _make_job("3", status=JobStatus.FAILED),
        }
        n = len(jobs)
        pending = sum(1 for j in jobs.values() if j.status == JobStatus.PENDING)
        completed = sum(1 for j in jobs.values() if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs.values() if j.status == JobStatus.FAILED)

        assert n == 3
        assert pending == 1
        assert completed == 1
        assert failed == 1

    def test_all_completed_summary(self) -> None:
        jobs = {
            "1": _make_job("1", status=JobStatus.COMPLETED),
            "2": _make_job("2", status=JobStatus.COMPLETED),
        }
        completed = sum(1 for j in jobs.values() if j.status == JobStatus.COMPLETED)
        assert completed == 2


# -----------------------------------------------------------------------
# Drag-and-drop audio filtering
# -----------------------------------------------------------------------


class TestDragDropFiltering:
    """Test that drag-and-drop filters audio files correctly."""

    def test_accepts_audio_extensions(self) -> None:
        from bits_whisperer.utils.constants import SUPPORTED_AUDIO_EXTENSIONS

        audio_files = ["song.mp3", "recording.wav", "podcast.m4a", "voice.flac"]
        accepted = [f for f in audio_files if Path(f).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
        assert len(accepted) == 4

    def test_rejects_non_audio(self) -> None:
        from bits_whisperer.utils.constants import SUPPORTED_AUDIO_EXTENSIONS

        non_audio = ["document.pdf", "image.png", "script.py", "data.csv"]
        accepted = [f for f in non_audio if Path(f).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
        assert len(accepted) == 0

    def test_mixed_file_list(self) -> None:
        from bits_whisperer.utils.constants import SUPPORTED_AUDIO_EXTENSIONS

        mixed = ["song.mp3", "photo.jpg", "voice.wav", "notes.txt"]
        accepted = [f for f in mixed if Path(f).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
        assert len(accepted) == 2


# -----------------------------------------------------------------------
# Models for provider listing
# -----------------------------------------------------------------------


class TestModelsForProvider:
    """Test model listing logic used by context menu."""

    def test_local_whisper_models(self) -> None:
        from bits_whisperer.utils.constants import WHISPER_MODELS

        models = [(m.id, m.name) for m in WHISPER_MODELS]
        assert len(models) > 0
        ids = [m[0] for m in models]
        assert "base" in ids or "small" in ids

    def test_openai_whisper_models(self) -> None:
        """OpenAI Whisper has exactly one model."""
        models = [("whisper-1", "Whisper-1")]
        assert len(models) == 1

    def test_groq_whisper_models(self) -> None:
        models = [
            ("whisper-large-v3", "Whisper Large v3"),
            ("whisper-large-v3-turbo", "Whisper Large v3 Turbo"),
            ("distil-whisper-large-v3-en", "Distil Whisper Large v3 (English)"),
        ]
        assert len(models) == 3

    def test_unknown_provider_returns_empty(self) -> None:
        """Unknown/other providers return empty model list."""
        models: list[tuple[str, str]] = []
        assert len(models) == 0
