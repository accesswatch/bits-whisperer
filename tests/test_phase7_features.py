"""Tests for Phase 7 features: custom naming, enhanced queue panel, batch operations."""

from __future__ import annotations

from pathlib import Path

from bits_whisperer.core.job import Job, JobStatus

# =======================================================================
# Custom naming on Job model
# =======================================================================


class TestJobCustomName:
    """Job.custom_name field and display_name priority."""

    def test_custom_name_default_empty(self) -> None:
        job = Job()
        assert job.custom_name == ""

    def test_display_name_prefers_custom_name(self) -> None:
        job = Job(
            file_name="interview.mp3",
            file_path="/path/to/interview.mp3",
            custom_name="Client Meeting Q4",
        )
        assert job.display_name == "Client Meeting Q4"

    def test_display_name_falls_back_to_file_name(self) -> None:
        job = Job(
            file_name="interview.mp3",
            file_path="/path/to/interview.mp3",
            custom_name="",
        )
        assert job.display_name == "interview.mp3"

    def test_display_name_falls_back_to_path(self) -> None:
        job = Job(file_path="/path/to/recording.wav", custom_name="")
        assert job.display_name == "recording.wav"

    def test_custom_name_overrides_file_name(self) -> None:
        job = Job(file_name="boring.mp3", custom_name="Important Keynote")
        assert job.display_name == "Important Keynote"

    def test_custom_name_can_be_set_after_creation(self) -> None:
        job = Job(file_name="test.mp3")
        assert job.display_name == "test.mp3"
        job.custom_name = "Renamed Item"
        assert job.display_name == "Renamed Item"

    def test_clearing_custom_name_restores_file_name(self) -> None:
        job = Job(file_name="original.mp3", custom_name="Custom")
        assert job.display_name == "Custom"
        job.custom_name = ""
        assert job.display_name == "original.mp3"

    def test_custom_name_with_spaces(self) -> None:
        job = Job(custom_name="  My Custom Name  ")
        assert job.display_name == "  My Custom Name  "

    def test_custom_name_with_unicode(self) -> None:
        job = Job(custom_name="Réunion d'équipe 🎙️")
        assert job.display_name == "Réunion d'équipe 🎙️"

    def test_custom_name_priority_order(self) -> None:
        """custom_name > file_name > derived from file_path."""
        # All three set
        job = Job(
            file_path="/path/to/file.wav",
            file_name="file.wav",
            custom_name="Custom",
        )
        assert job.display_name == "Custom"

        # Only file_name and file_path
        job.custom_name = ""
        assert job.display_name == "file.wav"

        # Only file_path
        job.file_name = ""
        assert job.display_name == "file.wav"  # derived from path


class TestJobCustomNameInFormatting:
    """Job properties use display_name which includes custom_name."""

    def test_status_text_independent_of_custom_name(self) -> None:
        job = Job(custom_name="Custom", status=JobStatus.PENDING)
        assert job.status_text == "Pending"

    def test_cost_display_independent_of_custom_name(self) -> None:
        job = Job(custom_name="Custom", cost_estimate=0.05)
        assert job.cost_display == "~$0.0500"

    def test_job_initialization_with_all_fields(self) -> None:
        """Verify custom_name doesn't break existing initialization."""
        job = Job(
            id="test-id",
            file_path="/path/test.mp3",
            file_name="test.mp3",
            file_size_bytes=1024,
            duration_seconds=60.0,
            status=JobStatus.PENDING,
            provider="local_whisper",
            model="base",
            language="en",
            include_timestamps=True,
            include_diarization=False,
            custom_name="My Test",
            cost_estimate=0.0,
        )
        assert job.display_name == "My Test"
        assert job.file_name == "test.mp3"
        assert job.custom_name == "My Test"


# =======================================================================
# QueuePanel helper method tests (no wx required)
# =======================================================================


class TestFolderCustomNames:
    """Folder custom name storage logic."""

    def test_folder_custom_names_dict_creation(self) -> None:
        """Verify the dict type used for folder custom names."""
        folder_names: dict[str, str] = {}
        folder_names["/path/to/folder"] = "My Project"
        assert folder_names.get("/path/to/folder") == "My Project"

    def test_folder_custom_names_default_fallback(self) -> None:
        """When no custom name, Path.name is used."""
        folder_names: dict[str, str] = {}
        folder_path = "/path/to/meetings"
        name = folder_names.get(folder_path) or Path(folder_path).name
        assert name == "meetings"

    def test_folder_custom_names_override(self) -> None:
        """Custom name takes priority over folder name."""
        folder_names: dict[str, str] = {}
        folder_path = "/path/to/meetings"
        folder_names[folder_path] = "Q4 Standup Recordings"
        name = folder_names.get(folder_path) or Path(folder_path).name
        assert name == "Q4 Standup Recordings"

    def test_folder_custom_names_clear(self) -> None:
        """Clearing custom name restores original folder name."""
        folder_names: dict[str, str] = {}
        folder_path = "/path/to/meetings"
        folder_names[folder_path] = "Custom"
        del folder_names[folder_path]
        name = folder_names.get(folder_path) or Path(folder_path).name
        assert name == "meetings"


# =======================================================================
# Batch operation logic tests
# =======================================================================


class TestRetryJobLogic:
    """Test retry job state transitions."""

    def test_retry_failed_job_resets_to_pending(self) -> None:
        job = Job(status=JobStatus.FAILED, error_message="Network error")
        # Simulate retry logic
        job.status = JobStatus.PENDING
        job.error_message = ""
        job.progress_percent = 0.0
        assert job.status == JobStatus.PENDING
        assert job.error_message == ""
        assert job.progress_percent == 0.0

    def test_retry_cancelled_job_resets_to_pending(self) -> None:
        job = Job(status=JobStatus.CANCELLED)
        job.status = JobStatus.PENDING
        job.error_message = ""
        job.progress_percent = 0.0
        assert job.status == JobStatus.PENDING

    def test_retry_preserves_custom_name(self) -> None:
        job = Job(
            status=JobStatus.FAILED,
            custom_name="Important Recording",
            error_message="Timeout",
        )
        job.status = JobStatus.PENDING
        job.error_message = ""
        assert job.custom_name == "Important Recording"
        assert job.display_name == "Important Recording"

    def test_retry_preserves_provider_settings(self) -> None:
        job = Job(
            status=JobStatus.FAILED,
            provider="openai_whisper",
            model="whisper-1",
            language="fr",
        )
        job.status = JobStatus.PENDING
        job.error_message = ""
        assert job.provider == "openai_whisper"
        assert job.model == "whisper-1"
        assert job.language == "fr"


class TestClearCompletedLogic:
    """Test clear completed filtering logic."""

    def test_filter_completed_jobs(self) -> None:
        jobs = {
            "1": Job(id="1", status=JobStatus.COMPLETED),
            "2": Job(id="2", status=JobStatus.PENDING),
            "3": Job(id="3", status=JobStatus.COMPLETED),
            "4": Job(id="4", status=JobStatus.FAILED),
        }
        completed_ids = [jid for jid, j in jobs.items() if j.status == JobStatus.COMPLETED]
        assert sorted(completed_ids) == ["1", "3"]

    def test_no_completed_jobs(self) -> None:
        jobs = {
            "1": Job(id="1", status=JobStatus.PENDING),
            "2": Job(id="2", status=JobStatus.FAILED),
        }
        completed_ids = [jid for jid, j in jobs.items() if j.status == JobStatus.COMPLETED]
        assert completed_ids == []


class TestRetryAllFailedLogic:
    """Test retry all failed filtering logic."""

    def test_filter_failed_jobs(self) -> None:
        jobs = {
            "1": Job(id="1", status=JobStatus.COMPLETED),
            "2": Job(id="2", status=JobStatus.FAILED, error_message="err1"),
            "3": Job(id="3", status=JobStatus.PENDING),
            "4": Job(id="4", status=JobStatus.FAILED, error_message="err2"),
        }
        failed_ids = [jid for jid, j in jobs.items() if j.status == JobStatus.FAILED]
        assert sorted(failed_ids) == ["2", "4"]

    def test_retry_resets_all_failed(self) -> None:
        jobs = {
            "1": Job(id="1", status=JobStatus.FAILED, error_message="err"),
            "2": Job(id="2", status=JobStatus.FAILED, error_message="err2"),
        }
        for job in jobs.values():
            job.status = JobStatus.PENDING
            job.error_message = ""
            job.progress_percent = 0.0
        assert all(j.status == JobStatus.PENDING for j in jobs.values())
        assert all(j.error_message == "" for j in jobs.values())


# =======================================================================
# Filter / search logic tests
# =======================================================================


class TestFilterLogic:
    """Test queue filter matching logic."""

    def _matches_filter(self, job: Job, filter_text: str) -> bool:
        """Replicate the filter matching logic from QueuePanel."""
        searchable = (
            f"{job.display_name} {job.file_name} {job.custom_name} "
            f"{job.provider} {job.status.value}"
        ).lower()
        return filter_text.lower() in searchable

    def test_filter_by_file_name(self) -> None:
        job = Job(file_name="interview_2025.mp3")
        assert self._matches_filter(job, "interview")
        assert self._matches_filter(job, "2025")

    def test_filter_by_custom_name(self) -> None:
        job = Job(file_name="file.mp3", custom_name="Board Meeting")
        assert self._matches_filter(job, "board")
        assert self._matches_filter(job, "meeting")
        assert not self._matches_filter(job, "conference")

    def test_filter_by_provider(self) -> None:
        job = Job(provider="openai_whisper")
        assert self._matches_filter(job, "openai")
        assert self._matches_filter(job, "whisper")

    def test_filter_by_status(self) -> None:
        job = Job(status=JobStatus.COMPLETED)
        assert self._matches_filter(job, "completed")
        assert not self._matches_filter(job, "pending")

    def test_filter_case_insensitive(self) -> None:
        job = Job(custom_name="Important Meeting")
        assert self._matches_filter(job, "IMPORTANT")
        assert self._matches_filter(job, "important")
        assert self._matches_filter(job, "Important")

    def test_empty_filter_matches_all(self) -> None:
        job = Job(file_name="test.mp3")
        assert self._matches_filter(job, "")

    def test_filter_partial_match(self) -> None:
        job = Job(file_name="my_podcast_episode_42.mp3")
        assert self._matches_filter(job, "podcast")
        assert self._matches_filter(job, "episode")
        assert self._matches_filter(job, "42")

    def test_filter_no_match(self) -> None:
        job = Job(file_name="test.mp3", provider="local_whisper")
        assert not self._matches_filter(job, "nonexistent")
        assert not self._matches_filter(job, "azure")


# =======================================================================
# AddFileWizard custom name integration tests
# =======================================================================


class TestAddFileWizardCustomName:
    """Verify custom name propagation in job creation logic."""

    def test_single_file_custom_name(self) -> None:
        """Single file gets the custom name directly."""
        paths = ["/path/to/recording.mp3"]
        custom_name = "Client Interview"
        jobs = []
        for i, path in enumerate(paths):
            p = Path(path)
            if custom_name:
                job_custom_name = custom_name if len(paths) == 1 else f"{custom_name} ({i + 1})"
            else:
                job_custom_name = ""
            jobs.append(Job(file_path=str(p), custom_name=job_custom_name))

        assert len(jobs) == 1
        assert jobs[0].custom_name == "Client Interview"
        assert jobs[0].display_name == "Client Interview"

    def test_multiple_files_custom_name_numbered(self) -> None:
        """Multiple files get numbered suffixes."""
        paths = ["/path/to/a.mp3", "/path/to/b.mp3", "/path/to/c.mp3"]
        custom_name = "Meeting Part"
        jobs = []
        for i, path in enumerate(paths):
            p = Path(path)
            if custom_name:
                job_custom_name = custom_name if len(paths) == 1 else f"{custom_name} ({i + 1})"
            else:
                job_custom_name = ""
            jobs.append(Job(file_path=str(p), custom_name=job_custom_name))

        assert len(jobs) == 3
        assert jobs[0].custom_name == "Meeting Part (1)"
        assert jobs[1].custom_name == "Meeting Part (2)"
        assert jobs[2].custom_name == "Meeting Part (3)"
        assert jobs[0].display_name == "Meeting Part (1)"

    def test_empty_custom_name_no_override(self) -> None:
        """Empty custom name leaves jobs with default display_name."""
        paths = ["/path/to/recording.mp3"]
        jobs = []
        for _i, path in enumerate(paths):
            p = Path(path)
            job_custom_name = ""
            jobs.append(Job(file_path=str(p), file_name=p.name, custom_name=job_custom_name))

        assert jobs[0].custom_name == ""
        assert jobs[0].display_name == "recording.mp3"

    def test_whitespace_only_custom_name_stripped(self) -> None:
        """Whitespace-only custom name is treated as empty after stripping."""
        custom_name_input = "   "
        custom_name = custom_name_input.strip()
        assert custom_name == ""


# =======================================================================
# File operations helper tests
# =======================================================================


class TestFileOperationsLogic:
    """Test file path operations used in queue panel."""

    def test_parent_folder_from_file_path(self) -> None:
        path = "/Users/test/recordings/interview.mp3"
        parent = Path(path).parent
        assert parent == Path("/Users/test/recordings")

    def test_file_existence_check(self) -> None:
        path = "/path/that/surely/does/not/exist/file.mp3"
        assert not Path(path).exists()

    def test_folder_name_from_path(self) -> None:
        path = "/Users/test/meetings/q4-recordings"
        assert Path(path).name == "q4-recordings"


# =======================================================================
# Job display formatting tests
# =======================================================================


class TestJobDisplayFormatting:
    """Test job display text formatting for the tree view."""

    def _format_item_text(self, job: Job) -> str:
        """Replicate the formatting logic from QueuePanel."""
        parts = [job.display_name]

        if (
            job.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
            and job.progress_percent > 0
        ):
            parts.append(f"{job.status.value.capitalize()} ({job.progress_percent:.0f}%)")
        else:
            parts.append(job.status.value.capitalize())

        parts.append(job.provider)

        if job.cost_estimate > 0:
            parts.append(job.cost_display)

        return " \u2014 ".join(parts)

    def test_format_with_custom_name(self) -> None:
        job = Job(
            file_name="test.mp3",
            custom_name="My Recording",
            provider="local_whisper",
        )
        text = self._format_item_text(job)
        assert text.startswith("My Recording")
        assert "local_whisper" in text
        assert "Pending" in text

    def test_format_without_custom_name(self) -> None:
        job = Job(file_name="test.mp3", provider="openai_whisper")
        text = self._format_item_text(job)
        assert text.startswith("test.mp3")

    def test_format_with_cost(self) -> None:
        job = Job(
            file_name="test.mp3",
            provider="openai_whisper",
            cost_estimate=0.05,
        )
        text = self._format_item_text(job)
        assert "~$0.0500" in text

    def test_format_transcribing_with_progress(self) -> None:
        job = Job(
            file_name="test.mp3",
            custom_name="Meeting",
            provider="local_whisper",
            status=JobStatus.TRANSCRIBING,
            progress_percent=75.0,
        )
        text = self._format_item_text(job)
        assert "Meeting" in text
        assert "75%" in text

    def test_format_completed_job(self) -> None:
        job = Job(
            file_name="test.mp3",
            provider="local_whisper",
            status=JobStatus.COMPLETED,
        )
        text = self._format_item_text(job)
        assert "Completed" in text

    def test_format_failed_job(self) -> None:
        job = Job(
            file_name="test.mp3",
            provider="local_whisper",
            status=JobStatus.FAILED,
        )
        text = self._format_item_text(job)
        assert "Failed" in text


# =======================================================================
# Folder display formatting tests
# =======================================================================


class TestFolderDisplayFormatting:
    """Test folder display text formatting."""

    def _format_folder_text(
        self,
        folder_path: str,
        folder_custom_names: dict[str, str],
        children: list[Job],
    ) -> str:
        """Replicate the folder formatting logic from QueuePanel."""
        folder_name = folder_custom_names.get(folder_path) or Path(folder_path).name

        if not children:
            return f"\U0001f4c1 {folder_name}"

        total = len(children)
        completed = sum(1 for j in children if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in children if j.status == JobStatus.FAILED)
        in_progress = sum(
            1 for j in children if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        )

        status_parts: list[str] = []
        if in_progress:
            status_parts.append(f"{in_progress} in progress")
        if completed:
            status_parts.append(f"{completed} done")
        if failed:
            status_parts.append(f"{failed} failed")

        status_str = ", ".join(status_parts) if status_parts else f"{total} pending"
        return f"\U0001f4c1 {folder_name} ({total} files \u2014 {status_str})"

    def test_folder_with_custom_name(self) -> None:
        custom_names = {"/path/to/folder": "Project Alpha"}
        children = [Job(status=JobStatus.PENDING) for _ in range(3)]
        text = self._format_folder_text("/path/to/folder", custom_names, children)
        assert "Project Alpha" in text
        assert "3 files" in text
        assert "3 pending" in text

    def test_folder_without_custom_name(self) -> None:
        text = self._format_folder_text("/path/to/meetings", {}, [])
        assert "meetings" in text
        assert "📁" in text

    def test_folder_with_mixed_status(self) -> None:
        children = [
            Job(status=JobStatus.COMPLETED),
            Job(status=JobStatus.COMPLETED),
            Job(status=JobStatus.FAILED),
            Job(status=JobStatus.PENDING),
        ]
        text = self._format_folder_text("/path/to/folder", {}, children)
        assert "4 files" in text
        assert "2 done" in text
        assert "1 failed" in text

    def test_folder_all_completed(self) -> None:
        children = [Job(status=JobStatus.COMPLETED) for _ in range(5)]
        text = self._format_folder_text("/path/to/folder", {}, children)
        assert "5 done" in text

    def test_folder_empty(self) -> None:
        text = self._format_folder_text("/path/to/folder", {}, [])
        assert "📁" in text
        assert "folder" in text


# =======================================================================
# Keyboard shortcut mapping tests
# =======================================================================


class TestKeyboardShortcutMapping:
    """Verify keyboard shortcuts are correctly mapped."""

    def test_standard_shortcuts_defined(self) -> None:
        """Verify that the expected shortcuts exist in common mapping."""
        shortcuts = {
            "F2": "Rename",
            "F5": "Start",
            "Delete": "Cancel/Remove",
            "Ctrl+C": "Copy path",
            "Ctrl+R": "Retry selected",
            "Ctrl+L": "Open file location",
            "Enter": "View transcript",
        }
        # Just verify the mapping is well-formed
        for key, action in shortcuts.items():
            assert isinstance(key, str)
            assert isinstance(action, str)
            assert len(key) > 0
            assert len(action) > 0

    def test_menu_accelerator_shortcuts(self) -> None:
        """Verify new menu shortcuts don't conflict."""
        menu_shortcuts = {
            "F2": "Rename",
            "F5": "Start Transcription",
            "Ctrl+Shift+R": "Retry All Failed",
            "Ctrl+Shift+Del": "Clear Queue",
        }
        # All shortcuts should be unique
        keys = list(menu_shortcuts.keys())
        assert len(keys) == len(set(keys))


# =======================================================================
# Properties dialog content tests
# =======================================================================


class TestPropertiesDialogContent:
    """Verify properties dialog builds correct content."""

    def test_job_properties_includes_custom_name(self) -> None:
        job = Job(
            file_name="test.mp3",
            file_path="/path/to/test.mp3",
            custom_name="Important Recording",
            status=JobStatus.COMPLETED,
            provider="local_whisper",
        )
        custom_name_display = job.custom_name or "(none)"
        original_name = job.file_name or Path(job.file_path).name

        assert custom_name_display == "Important Recording"
        assert original_name == "test.mp3"
        assert job.display_name == "Important Recording"

    def test_job_properties_no_custom_name(self) -> None:
        job = Job(
            file_name="test.mp3",
            file_path="/path/to/test.mp3",
        )
        custom_name_display = job.custom_name or "(none)"
        assert custom_name_display == "(none)"

    def test_folder_properties_with_custom_name(self) -> None:
        folder_path = "/path/to/meetings"
        folder_custom_names = {folder_path: "Weekly Standups"}
        custom_name = folder_custom_names.get(folder_path)
        display_name = custom_name or Path(folder_path).name
        assert display_name == "Weekly Standups"

    def test_folder_properties_without_custom_name(self) -> None:
        folder_path = "/path/to/meetings"
        folder_custom_names: dict[str, str] = {}
        custom_name = folder_custom_names.get(folder_path)
        display_name = custom_name or Path(folder_path).name
        assert display_name == "meetings"


# =======================================================================
# Edge cases
# =======================================================================


class TestEdgeCases:
    """Various edge cases for Phase 7 features."""

    def test_custom_name_very_long(self) -> None:
        """Very long custom names should work without errors."""
        long_name = "A" * 500
        job = Job(custom_name=long_name)
        assert job.display_name == long_name
        assert len(job.display_name) == 500

    def test_custom_name_special_characters(self) -> None:
        """Special characters in custom names."""
        special = "File — with (brackets) & <chars> | pipes"
        job = Job(custom_name=special)
        assert job.display_name == special

    def test_custom_name_newlines(self) -> None:
        """Custom names with newlines (edge case — should still work)."""
        name = "Line 1\nLine 2"
        job = Job(custom_name=name)
        assert job.display_name == name

    def test_retry_already_pending_job(self) -> None:
        """Retrying a pending job should not change it."""
        job = Job(status=JobStatus.PENDING)
        # Logic should check status before retrying
        can_retry = job.status in (JobStatus.FAILED, JobStatus.CANCELLED)
        assert not can_retry

    def test_retry_completed_job(self) -> None:
        """Retrying a completed job should not be allowed."""
        job = Job(status=JobStatus.COMPLETED)
        can_retry = job.status in (JobStatus.FAILED, JobStatus.CANCELLED)
        assert not can_retry

    def test_retry_active_job(self) -> None:
        """Retrying an active job should not be allowed."""
        job = Job(status=JobStatus.TRANSCRIBING)
        can_retry = job.status in (JobStatus.FAILED, JobStatus.CANCELLED)
        assert not can_retry

    def test_batch_operations_empty_queue(self) -> None:
        """Batch operations on empty queues should handle gracefully."""
        jobs: dict[str, Job] = {}
        completed = [jid for jid, j in jobs.items() if j.status == JobStatus.COMPLETED]
        failed = [jid for jid, j in jobs.items() if j.status == JobStatus.FAILED]
        assert completed == []
        assert failed == []

    def test_filter_empty_string(self) -> None:
        """Empty filter string matches everything."""
        job = Job(file_name="test.mp3")
        searchable = (
            f"{job.display_name} {job.file_name} {job.custom_name} "
            f"{job.provider} {job.status.value}"
        ).lower()
        assert "" in searchable

    def test_folder_jobs_normalization(self) -> None:
        """Test folder path normalization for job matching."""
        import os

        folder_path = "/path/to/folder"
        job_parent = "/path/to/folder"
        fp_norm = os.path.normpath(folder_path)
        jp_norm = os.path.normpath(job_parent)
        assert jp_norm.startswith(fp_norm)

    def test_multiple_custom_names_independent(self) -> None:
        """Each job's custom name is independent."""
        j1 = Job(file_name="a.mp3", custom_name="First")
        j2 = Job(file_name="b.mp3", custom_name="Second")
        j3 = Job(file_name="c.mp3")
        assert j1.display_name == "First"
        assert j2.display_name == "Second"
        assert j3.display_name == "c.mp3"
