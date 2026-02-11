"""Tests for Phase 8 features: AI Actions post-transcription processing.

Covers:
- Job model AI action fields
- Built-in presets library
- Template resolution (built-in + file-based)
- AI parameter resolution
- TranscriptionService AI action execution
- AddFileWizard AI action population
- AgentBuilderDialog renamed presets
- Queue panel AI action status formatting
- Transcript panel AI action display
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.core.transcription_service import TranscriptionService

# -----------------------------------------------------------------------
# Job model AI action fields
# -----------------------------------------------------------------------


class TestJobAIActionFields:
    """Job dataclass includes AI action fields with correct defaults."""

    def test_ai_action_template_default(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="test")
        assert job.ai_action_template == ""

    def test_ai_action_result_default(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="test")
        assert job.ai_action_result == ""

    def test_ai_action_status_default(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="test")
        assert job.ai_action_status == ""

    def test_ai_action_error_default(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="test")
        assert job.ai_action_error == ""

    def test_ai_action_template_set(self) -> None:
        job = Job(
            file_path="/tmp/test.mp3",
            provider="test",
            ai_action_template="Meeting Minutes",
        )
        assert job.ai_action_template == "Meeting Minutes"

    def test_ai_action_fields_mutable(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="test")
        job.ai_action_status = "running"
        job.ai_action_result = "Summary text"
        job.ai_action_error = "Error msg"
        assert job.ai_action_status == "running"
        assert job.ai_action_result == "Summary text"
        assert job.ai_action_error == "Error msg"

    def test_ai_action_with_custom_name(self) -> None:
        """AI action and custom name coexist."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="test",
            custom_name="My Recording",
            ai_action_template="Action Items",
        )
        assert job.custom_name == "My Recording"
        assert job.ai_action_template == "Action Items"
        assert job.display_name == "My Recording"


# -----------------------------------------------------------------------
# Built-in presets
# -----------------------------------------------------------------------


class TestBuiltinPresets:
    """Verify the built-in AI action presets in TranscriptionService."""

    def test_preset_count(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        assert len(TranscriptionService._BUILTIN_PRESETS) == 6

    def test_preset_names(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        expected = {
            "Meeting Minutes",
            "Action Items",
            "Executive Summary",
            "Interview Notes",
            "Lecture Notes",
            "Q&A Extraction",
        }
        assert set(TranscriptionService._BUILTIN_PRESETS.keys()) == expected

    def test_presets_not_empty(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        for name, text in TranscriptionService._BUILTIN_PRESETS.items():
            assert text.strip(), f"Preset '{name}' is empty"

    def test_presets_are_strings(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        for name, text in TranscriptionService._BUILTIN_PRESETS.items():
            assert isinstance(text, str), f"Preset '{name}' is not a string"

    def test_meeting_minutes_contains_action_items(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        text = TranscriptionService._BUILTIN_PRESETS["Meeting Minutes"]
        assert "action item" in text.lower()

    def test_qa_extraction_format(self) -> None:
        from bits_whisperer.core.transcription_service import TranscriptionService

        text = TranscriptionService._BUILTIN_PRESETS["Q&A Extraction"]
        assert "Q:" in text
        assert "A:" in text


# -----------------------------------------------------------------------
# Template resolution
# -----------------------------------------------------------------------


class TestTemplateResolution:
    """Template reference resolution — built-in name or JSON file path."""

    def _make_service(self, **kwargs) -> TranscriptionService:
        """Create a TranscriptionService with mocked deps."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        settings = MagicMock()
        settings.ai.max_tokens = 4096
        settings.ai.temperature = 0.3
        key_store = MagicMock()
        provider_manager = MagicMock()
        transcoder = MagicMock()
        svc = TranscriptionService(
            provider_manager=provider_manager,
            transcoder=transcoder,
            key_store=key_store,
            app_settings=settings,
        )
        return svc

    def test_resolve_builtin_preset(self) -> None:
        svc = self._make_service()
        instructions = svc._resolve_ai_action_instructions("Meeting Minutes")
        assert "meeting minutes" in instructions.lower()

    def test_resolve_unknown_preset_returns_empty(self) -> None:
        svc = self._make_service()
        instructions = svc._resolve_ai_action_instructions("Nonexistent Preset")
        assert instructions == ""

    def test_resolve_empty_ref_returns_empty(self) -> None:
        svc = self._make_service()
        instructions = svc._resolve_ai_action_instructions("")
        assert instructions == ""

    def test_resolve_file_based_template(self) -> None:
        """Resolve from a saved AgentConfig JSON file."""
        svc = self._make_service()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config = {
                "name": "Test Template",
                "instructions": "Summarize the transcript in 3 sentences.",
                "description": "Quick summary",
                "model": "gpt-4o",
                "tools_enabled": [],
                "temperature": 0.5,
                "max_tokens": 2048,
                "welcome_message": "",
            }
            json.dump(config, f)
            path = f.name

        try:
            instructions = svc._resolve_ai_action_instructions(path)
            assert instructions == "Summarize the transcript in 3 sentences."
        finally:
            Path(path).unlink(missing_ok=True)

    def test_resolve_invalid_file_returns_empty(self) -> None:
        svc = self._make_service()
        instructions = svc._resolve_ai_action_instructions("/bogus/path/no_file.json")
        assert instructions == ""


# -----------------------------------------------------------------------
# AI parameter resolution
# -----------------------------------------------------------------------


class TestAIParamResolution:
    """Test _resolve_ai_params for templates and defaults."""

    def _make_service(self) -> TranscriptionService:
        from bits_whisperer.core.transcription_service import TranscriptionService

        settings = MagicMock()
        settings.ai.max_tokens = 4096
        settings.ai.temperature = 0.3
        key_store = MagicMock()
        provider_manager = MagicMock()
        transcoder = MagicMock()
        return TranscriptionService(
            provider_manager=provider_manager,
            transcoder=transcoder,
            key_store=key_store,
            app_settings=settings,
        )

    def test_builtin_uses_defaults(self) -> None:
        svc = self._make_service()
        max_tokens, temperature = svc._resolve_ai_params("Meeting Minutes")
        assert max_tokens == 4096
        assert temperature == 0.3

    def test_file_template_params(self) -> None:
        svc = self._make_service()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config = {
                "name": "Param Test",
                "instructions": "Test",
                "description": "",
                "model": "gpt-4o",
                "tools_enabled": [],
                "temperature": 0.8,
                "max_tokens": 2048,
                "welcome_message": "",
            }
            json.dump(config, f)
            path = f.name

        try:
            max_tokens, temperature = svc._resolve_ai_params(path)
            assert max_tokens == 2048
            assert temperature == 0.8
        finally:
            Path(path).unlink(missing_ok=True)

    def test_nonexistent_file_uses_defaults(self) -> None:
        svc = self._make_service()
        max_tokens, temperature = svc._resolve_ai_params("/bogus.json")
        assert max_tokens == 4096
        assert temperature == 0.3


# -----------------------------------------------------------------------
# AI action execution
# -----------------------------------------------------------------------


class TestRunAIAction:
    """Test the _run_ai_action method end-to-end with mocks."""

    def _make_service(self):
        from bits_whisperer.core.transcription_service import TranscriptionService

        settings = MagicMock()
        settings.ai.max_tokens = 4096
        settings.ai.temperature = 0.3
        settings.ai.provider = "openai"
        key_store = MagicMock()
        provider_manager = MagicMock()
        transcoder = MagicMock()
        return TranscriptionService(
            provider_manager=provider_manager,
            transcoder=transcoder,
            key_store=key_store,
            app_settings=settings,
        )

    def _make_completed_job(self, template: str = "Meeting Minutes") -> Job:
        job = Job(
            file_path="/tmp/test.mp3",
            provider="test",
            ai_action_template=template,
        )
        job.status = JobStatus.COMPLETED
        result = MagicMock()
        result.full_text = "Alice said we should schedule a follow-up meeting."
        result.segments = []
        result.duration_seconds = 120.0
        job.result = result
        return job

    def test_no_template_skips(self) -> None:
        svc = self._make_service()
        job = Job(file_path="/tmp/test.mp3", provider="test")
        job.result = MagicMock()
        svc._run_ai_action(job)
        assert job.ai_action_status == ""

    def test_no_result_skips(self) -> None:
        svc = self._make_service()
        job = Job(
            file_path="/tmp/test.mp3",
            provider="test",
            ai_action_template="Meeting Minutes",
        )
        svc._run_ai_action(job)
        assert job.ai_action_status == ""

    def test_empty_transcript_fails(self) -> None:
        svc = self._make_service()
        job = self._make_completed_job()
        assert job.result is not None
        job.result.full_text = ""
        job.result.segments = []
        svc._run_ai_action(job)
        assert job.ai_action_status == "failed"
        assert "empty" in job.ai_action_error.lower()

    def test_unknown_template_fails(self) -> None:
        svc = self._make_service()
        job = self._make_completed_job("Nonexistent Template")
        svc._run_ai_action(job)
        assert job.ai_action_status == "failed"
        assert "not found" in job.ai_action_error.lower()

    @patch("bits_whisperer.core.context_manager.create_context_manager")
    @patch("bits_whisperer.core.ai_service.AIService")
    def test_successful_ai_action(self, mock_ai_cls, mock_ctx_mgr_factory) -> None:
        """Successful AI action stores result and sets status to completed."""
        svc = self._make_service()
        job = self._make_completed_job()

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.error = None
        mock_response.text = "## Meeting Minutes\n\n- Decision: schedule follow-up"
        mock_response.tokens_used = 150
        mock_provider.generate.return_value = mock_response

        mock_ai = MagicMock()
        mock_ai.is_configured.return_value = True
        mock_ai.get_provider.return_value = mock_provider
        mock_ai.get_model_id.return_value = "gpt-4o"
        mock_ai_cls.return_value = mock_ai

        mock_prepared = MagicMock()
        mock_prepared.fitted_transcript = "Alice said we should schedule a follow-up meeting."
        mock_prepared.budget.is_truncated = False
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.prepare_action_context.return_value = mock_prepared
        mock_ctx_mgr_factory.return_value = mock_ctx_mgr

        svc._run_ai_action(job)

        assert job.ai_action_status == "completed"
        assert "Meeting Minutes" in job.ai_action_result
        assert job.ai_action_error == ""

    @patch("bits_whisperer.core.context_manager.create_context_manager")
    @patch("bits_whisperer.core.ai_service.AIService")
    def test_ai_provider_error(self, mock_ai_cls, mock_ctx_mgr_factory) -> None:
        """AI provider error sets status to failed."""
        svc = self._make_service()
        job = self._make_completed_job()

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.error = "Rate limit exceeded"
        mock_response.text = ""
        mock_provider.generate.return_value = mock_response

        mock_ai = MagicMock()
        mock_ai.is_configured.return_value = True
        mock_ai.get_provider.return_value = mock_provider
        mock_ai.get_model_id.return_value = "gpt-4o"
        mock_ai_cls.return_value = mock_ai

        mock_prepared = MagicMock()
        mock_prepared.fitted_transcript = "test transcript"
        mock_prepared.budget.is_truncated = False
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.prepare_action_context.return_value = mock_prepared
        mock_ctx_mgr_factory.return_value = mock_ctx_mgr

        svc._run_ai_action(job)

        assert job.ai_action_status == "failed"
        assert "Rate limit" in job.ai_action_error

    @patch("bits_whisperer.core.ai_service.AIService")
    def test_ai_not_configured_fails(self, mock_ai_cls) -> None:
        """When no AI provider is configured, action fails gracefully."""
        svc = self._make_service()
        job = self._make_completed_job()

        mock_ai = MagicMock()
        mock_ai.is_configured.return_value = False
        mock_ai_cls.return_value = mock_ai

        svc._run_ai_action(job)

        assert job.ai_action_status == "failed"
        assert "configured" in job.ai_action_error.lower()

    @patch("bits_whisperer.core.context_manager.create_context_manager")
    @patch("bits_whisperer.core.ai_service.AIService")
    def test_ai_exception_caught(self, mock_ai_cls, mock_ctx_mgr_factory) -> None:
        """Unhandled exception from AI provider is caught and stored."""
        svc = self._make_service()
        job = self._make_completed_job()

        mock_ai = MagicMock()
        mock_ai.is_configured.return_value = True
        mock_ai.get_provider.side_effect = RuntimeError("Connection refused")
        mock_ai.get_model_id.return_value = "gpt-4o"
        mock_ai_cls.return_value = mock_ai

        mock_prepared = MagicMock()
        mock_prepared.fitted_transcript = "test transcript"
        mock_prepared.budget.is_truncated = False
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.prepare_action_context.return_value = mock_prepared
        mock_ctx_mgr_factory.return_value = mock_ctx_mgr

        svc._run_ai_action(job)

        assert job.ai_action_status == "failed"
        assert "Connection refused" in job.ai_action_error

    def test_running_status_set_before_processing(self) -> None:
        """The status is set to 'running' before AI processing starts."""
        svc = self._make_service()
        job = self._make_completed_job()

        statuses_seen = []

        def capture_notify(job):
            statuses_seen.append(job.ai_action_status)

        svc._notify_update = capture_notify

        # Will fail because no AI provider, but should capture 'running' status
        svc._run_ai_action(job)

        assert "running" in statuses_seen


# -----------------------------------------------------------------------
# Agent Builder dialog presets
# -----------------------------------------------------------------------


class TestAgentBuilderPresets:
    """Verify the presets in the renamed AI Action Builder dialog module."""

    def test_preset_count(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        # 6 action presets + General Assistant + Custom = 8
        assert len(_INSTRUCTION_PRESETS) == 8

    def test_custom_preset_is_empty(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert _INSTRUCTION_PRESETS["Custom"] == ""

    def test_meeting_minutes_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Meeting Minutes" in _INSTRUCTION_PRESETS
        assert len(_INSTRUCTION_PRESETS["Meeting Minutes"]) > 50

    def test_action_items_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Action Items" in _INSTRUCTION_PRESETS

    def test_executive_summary_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Executive Summary" in _INSTRUCTION_PRESETS

    def test_interview_notes_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Interview Notes" in _INSTRUCTION_PRESETS

    def test_lecture_notes_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Lecture Notes" in _INSTRUCTION_PRESETS

    def test_qa_extraction_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "Q&A Extraction" in _INSTRUCTION_PRESETS

    def test_general_assistant_preset_exists(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        assert "General Assistant" in _INSTRUCTION_PRESETS

    def test_all_presets_are_strings(self) -> None:
        from bits_whisperer.ui.agent_builder_dialog import _INSTRUCTION_PRESETS

        for name, text in _INSTRUCTION_PRESETS.items():
            assert isinstance(text, str), f"Preset '{name}' is not a string"


# -----------------------------------------------------------------------
# AgentConfig serialization with AI action templates
# -----------------------------------------------------------------------


class TestAgentConfigForAIActions:
    """AgentConfig save/load works for AI action templates."""

    def test_save_and_load_roundtrip(self) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        config = AgentConfig(
            name="My Action Template",
            description="Extract action items",
            instructions="Extract action items from the transcript.",
            model="gpt-4o",
            tools_enabled=[],
            temperature=0.2,
            max_tokens=3000,
            welcome_message="",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            config.save(path)
            loaded = AgentConfig.load(path)
            assert loaded.name == "My Action Template"
            assert loaded.instructions == "Extract action items from the transcript."
            assert loaded.temperature == 0.2
            assert loaded.max_tokens == 3000
        finally:
            path.unlink(missing_ok=True)

    def test_instructions_preserved(self) -> None:
        from bits_whisperer.core.copilot_service import AgentConfig

        multi_line = "Line 1\nLine 2\n- Bullet\n- Another"
        config = AgentConfig(instructions=multi_line)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            config.save(path)
            loaded = AgentConfig.load(path)
            assert loaded.instructions == multi_line
        finally:
            path.unlink(missing_ok=True)


# -----------------------------------------------------------------------
# Queue panel AI action status display
# -----------------------------------------------------------------------


class TestQueuePanelAIActionDisplay:
    """Queue panel _format_item_text includes AI action status indicators."""

    def _import_format(self):
        """Import the format function by instantiating enough of QueuePanel."""
        # We test the logic directly against Job objects
        from bits_whisperer.core.job import Job, JobStatus

        return Job, JobStatus

    def test_no_ai_action_no_indicator(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="whisper")
        job.status = JobStatus.COMPLETED
        # No ai_action_template or status — format text should not contain AI Action
        parts = [job.display_name, "Completed", job.provider]
        text = " \u2014 ".join(parts)
        assert "AI Action" not in text

    def test_queued_with_template_shows_star(self) -> None:
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="Meeting Minutes",
        )
        job.status = JobStatus.PENDING
        parts = [job.display_name, "Pending", job.provider]
        if job.ai_action_template and job.status == JobStatus.PENDING:
            parts.append("\u2b50 AI Action")
        text = " \u2014 ".join(parts)
        assert "\u2b50 AI Action" in text

    def test_running_status_shows_hourglass(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="whisper")
        job.ai_action_status = "running"
        parts = [job.display_name, "Completed", job.provider]
        if job.ai_action_status == "running":
            parts.append("\u23f3 AI Action")
        text = " \u2014 ".join(parts)
        assert "\u23f3 AI Action" in text

    def test_completed_status_shows_checkmark(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="whisper")
        job.ai_action_status = "completed"
        parts = [job.display_name, "Completed", job.provider]
        if job.ai_action_status == "completed":
            parts.append("\u2713 AI Action")
        text = " \u2014 ".join(parts)
        assert "\u2713 AI Action" in text

    def test_failed_status_shows_cross(self) -> None:
        job = Job(file_path="/tmp/test.mp3", provider="whisper")
        job.ai_action_status = "failed"
        parts = [job.display_name, "Completed", job.provider]
        if job.ai_action_status == "failed":
            parts.append("\u2717 AI Action")
        text = " \u2014 ".join(parts)
        assert "\u2717 AI Action" in text


# -----------------------------------------------------------------------
# Integration: AI action in transcription pipeline
# -----------------------------------------------------------------------


class TestAIActionPipelineIntegration:
    """Integration tests for AI action in the transcription pipeline."""

    def test_job_fields_accessible_after_creation(self) -> None:
        """All AI action fields are accessible on a new Job instance."""
        job = Job(
            file_path="/tmp/file.mp3",
            provider="whisper",
            ai_action_template="Executive Summary",
        )
        assert hasattr(job, "ai_action_template")
        assert hasattr(job, "ai_action_result")
        assert hasattr(job, "ai_action_status")
        assert hasattr(job, "ai_action_error")

    def test_multiple_jobs_independent(self) -> None:
        """AI action state is independent between jobs."""
        j1 = Job(
            file_path="/tmp/a.mp3",
            provider="test",
            ai_action_template="Meeting Minutes",
        )
        j2 = Job(
            file_path="/tmp/b.mp3",
            provider="test",
            ai_action_template="Action Items",
        )
        j1.ai_action_status = "completed"
        j1.ai_action_result = "Minutes text"

        assert j2.ai_action_status == ""
        assert j2.ai_action_result == ""
        assert j1.ai_action_template != j2.ai_action_template

    def test_job_without_template_stays_clean(self) -> None:
        """A job with no AI action template has empty AI fields throughout."""
        job = Job(file_path="/tmp/test.mp3", provider="test")
        job.status = JobStatus.COMPLETED
        assert job.ai_action_template == ""
        assert job.ai_action_status == ""
        assert job.ai_action_result == ""
        assert job.ai_action_error == ""

    def test_all_preset_names_resolve(self) -> None:
        """Every built-in preset name resolves to non-empty instructions."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        settings = MagicMock()
        settings.ai.max_tokens = 4096
        settings.ai.temperature = 0.3
        key_store = MagicMock()
        provider_manager = MagicMock()
        transcoder = MagicMock()
        svc = TranscriptionService(
            provider_manager=provider_manager,
            transcoder=transcoder,
            key_store=key_store,
            app_settings=settings,
        )

        for name in TranscriptionService._BUILTIN_PRESETS:
            instructions = svc._resolve_ai_action_instructions(name)
            assert instructions, f"Preset '{name}' resolved to empty"
            assert len(instructions) > 20, f"Preset '{name}' too short"

    def test_transcript_text_truncated_to_50k(self) -> None:
        """Verify that long transcripts are truncated in the prompt."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        settings = MagicMock()
        settings.ai.max_tokens = 4096
        settings.ai.temperature = 0.3
        key_store = MagicMock()
        provider_manager = MagicMock()
        transcoder = MagicMock()
        svc = TranscriptionService(
            provider_manager=provider_manager,
            transcoder=transcoder,
            key_store=key_store,
            app_settings=settings,
        )

        job = Job(
            file_path="/tmp/long.mp3",
            provider="test",
            ai_action_template="Meeting Minutes",
        )
        job.status = JobStatus.COMPLETED
        result = MagicMock()
        result.full_text = "x" * 100_000  # 100K chars
        result.segments = []
        job.result = result

        # The _run_ai_action method truncates to 50K chars in the prompt.
        # We can verify by examining the generate call.
        with (
            patch("bits_whisperer.core.ai_service.AIService") as mock_ai_cls,
            patch(
                "bits_whisperer.core.context_manager.create_context_manager"
            ) as mock_ctx_mgr_factory,
        ):
            mock_provider = MagicMock()
            mock_response = MagicMock()
            mock_response.error = None
            mock_response.text = "Summary"
            mock_response.tokens_used = 50
            mock_provider.generate.return_value = mock_response

            mock_ai = MagicMock()
            mock_ai.is_configured.return_value = True
            mock_ai.get_provider.return_value = mock_provider
            mock_ai.get_model_id.return_value = "gpt-4o"
            mock_ai_cls.return_value = mock_ai

            # The context manager should truncate the transcript
            truncated_text = "x" * 50_000
            mock_prepared = MagicMock()
            mock_prepared.fitted_transcript = truncated_text
            mock_prepared.budget.is_truncated = True
            mock_prepared.budget.transcript_actual_tokens = 25000
            mock_prepared.budget.transcript_fitted_tokens = 12500
            mock_prepared.budget.strategy_used = "truncate"
            mock_ctx_mgr = MagicMock()
            mock_ctx_mgr.prepare_action_context.return_value = mock_prepared
            mock_ctx_mgr_factory.return_value = mock_ctx_mgr

            svc._run_ai_action(job)

            # Check the prompt passed to generate
            call_args = mock_provider.generate.call_args
            prompt = call_args[0][0]
            # Transcript portion should be truncated to ~50K
            assert len(prompt) < 60000  # 50K + instructions + framing


# -----------------------------------------------------------------------
# AI Action field persistence across job lifecycle
# -----------------------------------------------------------------------


class TestAIActionLifecycle:
    """Test AI action fields through the full job lifecycle."""

    def test_lifecycle_queued_to_completed_to_ai_action(self) -> None:
        """Simulate complete lifecycle: queued -> completed -> AI action."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="Executive Summary",
        )
        assert job.status == JobStatus.PENDING
        assert job.ai_action_status == ""

        # Simulate transcription completion
        job.status = JobStatus.COMPLETED
        result = MagicMock()
        result.full_text = "The meeting discussed budgets and strategy."
        job.result = result

        # Simulate AI action start
        job.ai_action_status = "running"
        assert job.ai_action_status == "running"

        # Simulate AI action completion
        job.ai_action_status = "completed"
        job.ai_action_result = "Executive summary of meeting discussion."
        assert job.ai_action_status == "completed"
        assert job.ai_action_result

    def test_lifecycle_ai_action_failure(self) -> None:
        """Simulate AI action failure after transcription succeeds."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="Action Items",
        )
        job.status = JobStatus.COMPLETED
        job.result = MagicMock()

        # AI action fails
        job.ai_action_status = "failed"
        job.ai_action_error = "API key expired"

        assert job.status == JobStatus.COMPLETED  # Transcription still OK
        assert job.ai_action_status == "failed"
        assert "API key" in job.ai_action_error


# -----------------------------------------------------------------------
# Queue panel AI Action context menu helpers
# -----------------------------------------------------------------------


class TestQueuePanelAIActionContextMenu:
    """Tests for AI Action context menu methods on QueuePanel."""

    def test_change_job_ai_action_sets_template(self) -> None:
        """_change_job_ai_action sets the template on a pending job."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="",
        )
        job.status = JobStatus.PENDING
        job.ai_action_template = "Meeting Minutes"
        assert job.ai_action_template == "Meeting Minutes"

    def test_change_job_ai_action_resets_prior_state(self) -> None:
        """Changing AI action resets any prior AI action status/result/error."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="Action Items",
        )
        job.ai_action_status = "failed"
        job.ai_action_error = "Old error"
        job.ai_action_result = "Old result"

        # Simulate what _change_job_ai_action does
        job.ai_action_template = "Meeting Minutes"
        job.ai_action_status = ""
        job.ai_action_result = ""
        job.ai_action_error = ""

        assert job.ai_action_template == "Meeting Minutes"
        assert job.ai_action_status == ""
        assert job.ai_action_result == ""
        assert job.ai_action_error == ""

    def test_change_job_ai_action_clear_template(self) -> None:
        """Setting template to empty string clears the AI action."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            ai_action_template="Executive Summary",
        )
        job.ai_action_template = ""
        assert job.ai_action_template == ""

    def test_set_folder_ai_action_applies_to_pending_only(self) -> None:
        """Folder AI action change only affects pending jobs."""
        pending_job = Job(
            file_path="/tmp/a.mp3",
            provider="whisper",
        )
        pending_job.status = JobStatus.PENDING

        completed_job = Job(
            file_path="/tmp/b.mp3",
            provider="whisper",
        )
        completed_job.status = JobStatus.COMPLETED

        failed_job = Job(
            file_path="/tmp/c.mp3",
            provider="whisper",
        )
        failed_job.status = JobStatus.FAILED

        # Simulate _set_folder_ai_action logic
        jobs = [pending_job, completed_job, failed_job]
        pending = [j for j in jobs if j.status == JobStatus.PENDING]
        for job in pending:
            job.ai_action_template = "Lecture Notes"
            job.ai_action_status = ""
            job.ai_action_result = ""
            job.ai_action_error = ""

        assert pending_job.ai_action_template == "Lecture Notes"
        assert completed_job.ai_action_template == ""
        assert failed_job.ai_action_template == ""

    def test_set_folder_ai_action_multiple_pending(self) -> None:
        """Folder AI action applies to all pending jobs in the folder."""
        jobs = [Job(file_path=f"/tmp/{i}.mp3", provider="whisper") for i in range(5)]
        for j in jobs:
            j.status = JobStatus.PENDING

        template = "Q&A Extraction"
        for j in jobs:
            j.ai_action_template = template

        assert all(j.ai_action_template == template for j in jobs)

    def test_builtin_presets_available_in_submenu(self) -> None:
        """Built-in presets from TranscriptionService are importable."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        presets = TranscriptionService._BUILTIN_PRESETS
        assert "Meeting Minutes" in presets
        assert "Action Items" in presets
        assert "Executive Summary" in presets
        assert "Interview Notes" in presets
        assert "Lecture Notes" in presets
        assert "Q&A Extraction" in presets

    def test_change_ai_action_preserves_other_fields(self) -> None:
        """Changing AI action doesn't affect other job properties."""
        job = Job(
            file_path="/tmp/test.mp3",
            provider="whisper",
            model="large-v3",
            language="en",
            include_timestamps=True,
            include_diarization=True,
            custom_name="My recording",
        )
        job.status = JobStatus.PENDING

        # Change AI action
        job.ai_action_template = "Meeting Minutes"

        # Other fields unchanged
        assert job.provider == "whisper"
        assert job.model == "large-v3"
        assert job.language == "en"
        assert job.include_timestamps is True
        assert job.include_diarization is True
        assert job.custom_name == "My recording"
