"""Transcription service — job queue, orchestration, and worker management."""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from bits_whisperer.core.audio_preprocessor import AudioPreprocessor
from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.core.provider_manager import ProviderManager
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.core.transcoder import Transcoder
from bits_whisperer.storage.key_store import KeyStore
from bits_whisperer.utils.constants import (
    DATA_DIR,
    DEFAULT_MAX_CONCURRENT_JOBS,
)

logger = logging.getLogger(__name__)

# Callback types for UI integration
JobUpdateCallback = Callable[[Job], None]
BatchCompleteCallback = Callable[[list[Job]], None]


class TranscriptionService:
    """Orchestrates transcription jobs with queueing and worker threads.

    Provides the main interface for the UI to submit, monitor, pause,
    and cancel transcription jobs. Workers pick jobs from a queue,
    transcode if needed, invoke the selected provider, and report
    progress back via callbacks.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        transcoder: Transcoder,
        key_store: KeyStore | None = None,
        preprocessor: AudioPreprocessor | None = None,
        app_settings: AppSettings | None = None,
        max_workers: int = DEFAULT_MAX_CONCURRENT_JOBS,
    ) -> None:
        """Initialise the transcription service."""
        self._provider_manager = provider_manager
        self._transcoder = transcoder
        self._key_store = key_store
        self._preprocessor = preprocessor or AudioPreprocessor()
        self._app_settings = app_settings
        self._max_workers = max_workers

        self._job_queue: queue.Queue[Job | None] = queue.Queue()
        self._active_jobs: dict[str, Job] = {}
        self._completed_jobs: list[Job] = []
        self._all_jobs: list[Job] = []
        self._workers: list[threading.Thread] = []
        self._running = False
        self._paused = False
        self._batch_notified = False
        self._lock = threading.Lock()

        # Temp file tracking — per-job temp files cleaned after completion
        self._temp_files: dict[str, list[Path]] = {}  # job_id -> [temp_paths]

        # Callbacks
        self._on_job_update: JobUpdateCallback | None = None
        self._on_batch_complete: BatchCompleteCallback | None = None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def set_job_update_callback(self, callback: JobUpdateCallback) -> None:
        """Set callback invoked whenever a job's status or progress changes.

        Args:
            callback: Function receiving the updated Job.
        """
        self._on_job_update = callback

    def set_batch_complete_callback(self, callback: BatchCompleteCallback) -> None:
        """Set callback invoked when all queued jobs finish.

        Args:
            callback: Function receiving the list of completed jobs.
        """
        self._on_batch_complete = callback

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def add_job(self, job: Job) -> None:
        """Add a single job to the queue.

        Args:
            job: The Job to enqueue.
        """
        with self._lock:
            self._all_jobs.append(job)
            self._batch_notified = False
        self._job_queue.put(job)
        self._notify_update(job)
        logger.info("Job queued: %s (%s)", job.display_name, job.id)

    def add_jobs(self, jobs: list[Job]) -> None:
        """Add multiple jobs to the queue.

        Args:
            jobs: List of Jobs to enqueue.
        """
        for job in jobs:
            self.add_job(job)

    def reset_for_new_batch(self) -> None:
        """Clear completed/failed/cancelled jobs to prepare for a fresh batch.

        Called before starting a new transcription run so that old
        finished jobs do not accumulate and interfere with batch-complete
        detection.
        """
        with self._lock:
            # Keep only jobs that are still actively processing
            self._all_jobs = [
                j
                for j in self._all_jobs
                if j.status
                in (
                    JobStatus.PENDING,
                    JobStatus.TRANSCODING,
                    JobStatus.TRANSCRIBING,
                )
            ]
            self._completed_jobs = [
                j
                for j in self._completed_jobs
                if j.status
                in (
                    JobStatus.PENDING,
                    JobStatus.TRANSCODING,
                    JobStatus.TRANSCRIBING,
                )
            ]
            self._batch_notified = False

    # ------------------------------------------------------------------
    # Queue control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start worker threads and begin processing the queue."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._batch_notified = False
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"transcription-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info(
            "Transcription service started with %d workers.",
            self._max_workers,
        )

    def stop(self) -> None:
        """Stop processing and shut down worker threads.

        Sends sentinel values to unblock workers, then joins each thread
        with a timeout to ensure a clean shutdown.  Any remaining temp
        files tracked by the service are cleaned up.
        """
        self._running = False
        # Unblock waiting workers with sentinels
        for _ in self._workers:
            self._job_queue.put(None)

        # Join worker threads so they finish before we exit
        for t in self._workers:
            t.join(timeout=5.0)
            if t.is_alive():
                logger.warning(
                    "Worker thread %s did not exit within timeout",
                    t.name,
                )
        self._workers.clear()

        # Clean up any remaining temp files from in-flight jobs
        self._cleanup_all_temp_files()

        logger.info("Transcription service stopped.")

    def pause(self) -> None:
        """Pause queue processing (current job continues)."""
        self._paused = True
        logger.info("Queue paused.")

    def resume(self) -> None:
        """Resume queue processing."""
        self._paused = False
        logger.info("Queue resumed.")

    @property
    def is_running(self) -> bool:
        """Whether the service is actively processing."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Whether the queue is paused."""
        return self._paused

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or active job.

        Args:
            job_id: The job ID to cancel.

        Returns:
            True if the job was found and cancelled.
        """
        with self._lock:
            for job in self._all_jobs:
                if job.id == job_id and job.status in (
                    JobStatus.PENDING,
                    JobStatus.TRANSCODING,
                    JobStatus.TRANSCRIBING,
                ):
                    job.status = JobStatus.CANCELLED
                    self._notify_update(job)
                    return True
        return False

    def get_all_jobs(self) -> list[Job]:
        """Return all jobs (including completed)."""
        with self._lock:
            return list(self._all_jobs)

    def get_queue_size(self) -> int:
        """Return the number of pending jobs."""
        return self._job_queue.qsize()

    def get_active_count(self) -> int:
        """Return the number of currently-processing jobs."""
        with self._lock:
            return len(self._active_jobs)

    def get_progress_summary(self) -> dict[str, Any]:
        """Return a summary of overall progress.

        Returns:
            Dict with total, completed, failed, active, pending counts
            and overall_percent.
        """
        with self._lock:
            total = len(self._all_jobs)
            completed = sum(1 for j in self._all_jobs if j.status == JobStatus.COMPLETED)
            failed = sum(1 for j in self._all_jobs if j.status == JobStatus.FAILED)
            active = len(self._active_jobs)
            pending = sum(1 for j in self._all_jobs if j.status == JobStatus.PENDING)
            pct = (completed / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "active": active,
            "pending": pending,
            "overall_percent": pct,
        }

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------
    def _track_temp_file(self, job_id: str, path: Path) -> None:
        """Register a temp file for cleanup after the job finishes."""
        with self._lock:
            self._temp_files.setdefault(job_id, []).append(path)

    def _cleanup_job_temp_files(self, job_id: str) -> None:
        """Remove all tracked temp files for a completed/failed job."""
        with self._lock:
            paths = self._temp_files.pop(job_id, [])
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
                    logger.debug("Cleaned up temp file: %s", p)
            except Exception as exc:
                logger.debug("Could not remove temp file %s: %s", p, exc)

    def _cleanup_all_temp_files(self) -> None:
        """Remove all tracked temp files (called during shutdown)."""
        with self._lock:
            all_paths = list(self._temp_files.values())
            self._temp_files.clear()
        for paths in all_paths:
            for p in paths:
                try:
                    if p.exists():
                        p.unlink()
                        logger.debug("Cleaned up temp file on shutdown: %s", p)
                except Exception as exc:
                    logger.debug("Could not remove temp file %s: %s", p, exc)

    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        """Worker thread main loop — processes jobs from the queue."""
        while self._running:
            # Pause support
            while self._paused and self._running:
                time.sleep(0.5)

            try:
                job = self._job_queue.get(timeout=1.0)
            except queue.Empty:
                # Check if all jobs are done
                self._check_batch_complete()
                continue

            if job is None:
                break  # Shutdown signal

            if job.status == JobStatus.CANCELLED:
                continue

            with self._lock:
                self._active_jobs[job.id] = job

            try:
                self._process_job(job)
            except Exception as exc:
                logger.error("Job %s failed: %s", job.id, exc)
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = datetime.now().isoformat()
                self._notify_update(job)
            finally:
                # Clean up temp files created during this job
                self._cleanup_job_temp_files(job.id)
                with self._lock:
                    self._active_jobs.pop(job.id, None)
                    self._completed_jobs.append(job)

            self._check_batch_complete()

    def _process_job(self, job: Job) -> None:
        """Process a single transcription job.

        Pipeline: validate, preprocess, transcode, transcribe.

        Args:
            job: The Job to process.
        """
        job.started_at = datetime.now().isoformat()

        # --- Step 0: Pre-validation ---
        if not os.path.isfile(job.file_path):
            raise RuntimeError(f"Audio file not found: {job.file_path}")
        file_size = os.path.getsize(job.file_path)
        if file_size == 0:
            raise RuntimeError(f"Audio file is empty (0 bytes): {job.file_path}")

        # Check SDK availability before attempting to load the provider
        from bits_whisperer.core.sdk_installer import (
            get_provider_sdk_info,
            is_sdk_available,
        )

        if not is_sdk_available(job.provider):
            sdk_info = get_provider_sdk_info(job.provider)
            name = sdk_info.display_name if sdk_info else job.provider
            raise RuntimeError(
                f"The {name} SDK is not installed. "
                "Please install it from the Model Manager or Settings "
                "before transcribing."
            )

        # Check provider exists early
        provider = self._provider_manager.get_provider(job.provider)
        if not provider:
            raise RuntimeError(f"Provider not found: {job.provider}")

        # Resolve and validate API key for cloud providers
        api_key = ""
        if self._key_store:
            api_key = self._resolve_api_key(job.provider)
        caps = provider.get_capabilities()
        if caps.provider_type == "cloud" and not api_key:
            raise RuntimeError(
                f"No API key configured for {caps.name}. "
                "Please add your key in Settings, then Cloud Providers."
            )

        # Check file size against provider limits
        file_size_mb = file_size / (1024 * 1024)
        if caps.max_file_size_mb and file_size_mb > caps.max_file_size_mb:
            raise RuntimeError(
                f"File too large for {caps.name}: "
                f"{file_size_mb:.0f} MB exceeds "
                f"{caps.max_file_size_mb} MB limit."
            )

        # --- Configure provider with user defaults ---
        if self._app_settings:
            prov_defaults = self._app_settings.provider_settings.get(job.provider)
            if prov_defaults:
                provider.configure(prov_defaults)

        # --- Step 1: Audio preprocessing ---
        job.status = JobStatus.TRANSCODING
        job.progress_percent = 0.0
        self._notify_update(job)

        audio_path = job.file_path
        clip_start = job.clip_start_seconds
        clip_end = job.clip_end_seconds

        if clip_start is not None or clip_end is not None:
            if clip_start is not None and clip_start < 0:
                clip_start = 0.0
            if clip_end is not None and clip_end <= 0:
                clip_end = None
            if clip_start is not None and clip_end is not None and clip_end <= clip_start:
                raise RuntimeError("Invalid clip range: end must be after start")

        pp = self._preprocessor
        if pp and pp.is_available() and pp.settings.enabled:
            try:
                logger.info("Preprocessing audio: %s", job.display_name)
                preprocessed = self._preprocessor.process(
                    audio_path,
                    start_seconds=clip_start,
                    end_seconds=clip_end,
                )
                if str(preprocessed) != audio_path:
                    self._track_temp_file(job.id, Path(preprocessed))
                audio_path = str(preprocessed)
                clip_start = None
                clip_end = None
            except Exception as exc:
                logger.warning("Preprocessing failed, using original: %s", exc)

        job.progress_percent = 10.0
        self._notify_update(job)

        # --- Step 2: Transcode ---
        def transcode_progress(pct: float) -> None:
            job.progress_percent = 10.0 + pct * 0.1  # 10-20% range
            self._notify_update(job)

        if self._transcoder.is_available():
            try:
                transcoded = self._transcoder.transcode(
                    audio_path,
                    start_seconds=clip_start,
                    end_seconds=clip_end,
                    progress_callback=transcode_progress,
                )
                if str(transcoded) != audio_path:
                    self._track_temp_file(job.id, Path(transcoded))
                audio_path = str(transcoded)
            except Exception as exc:
                logger.warning(
                    "Transcoding failed, using " "preprocessed/original: %s",
                    exc,
                )

        # --- Step 3: Transcribe ---
        job.status = JobStatus.TRANSCRIBING
        job.progress_percent = 20.0
        self._notify_update(job)

        def transcribe_progress(pct: float) -> None:
            job.progress_percent = 20.0 + pct * 0.8  # Transcription is ~80%
            self._notify_update(job)

        result = self._transcribe_with_retry(
            provider=provider,
            audio_path=audio_path,
            job=job,
            api_key=api_key,
            progress_callback=transcribe_progress,
        )

        # --- Step 4: Local diarization post-processing ---
        if (
            self._app_settings
            and self._app_settings.diarization.use_local_diarization
            and job.include_diarization
            and not any(seg.speaker for seg in result.segments)
        ):
            try:
                from bits_whisperer.core.diarization import (
                    LocalDiarizer,
                    is_available,
                )

                if is_available():
                    ds = self._app_settings.diarization
                    hf_token = ""
                    if self._key_store:
                        hf_token = self._key_store.get_key("hf_auth_token") or ""
                    diarizer = LocalDiarizer(
                        hf_token=hf_token,
                        model=ds.pyannote_model,
                    )
                    turns = diarizer.diarize(
                        audio_path,
                        min_speakers=ds.min_speakers,
                        max_speakers=ds.max_speakers,
                    )
                    diarizer.apply_to_transcript(result, turns)
                    logger.info(
                        "Local diarization applied: %d speaker turns",
                        len(turns),
                    )
                else:
                    logger.debug(
                        "Local diarization requested but pyannote.audio " "is not installed."
                    )
            except Exception as exc:
                logger.warning("Local diarization failed: %s", exc)

        # Apply speaker map from settings
        if self._app_settings and self._app_settings.diarization.speaker_map:
            from bits_whisperer.core.diarization import apply_speaker_map

            apply_speaker_map(
                result,
                self._app_settings.diarization.speaker_map,
            )

        # --- Step 5: Complete ---
        result.job_id = job.id
        job.result = result
        job.status = JobStatus.COMPLETED
        job.progress_percent = 100.0
        job.completed_at = datetime.now().isoformat()
        job.duration_seconds = result.duration_seconds
        self._notify_update(job)

        logger.info("Job completed: %s", job.display_name)

        # --- Step 6: Post-transcription AI action ---
        if job.ai_action_template:
            self._run_ai_action(job)

    def _resolve_api_key(self, provider_id: str) -> str:
        """Resolve the API key for a provider from the KeyStore.

        For AWS, combines access key, secret key, and region into the
        expected colon-separated format.

        Args:
            provider_id: Provider identifier string.

        Returns:
            API key string, or empty string if unavailable.
        """
        if not self._key_store:
            return ""

        # Provider-to-key-store mapping for composite keys
        if provider_id == "aws_transcribe":
            access = self._key_store.get_key("aws_access_key") or ""
            secret = self._key_store.get_key("aws_secret_key") or ""
            region = self._key_store.get_key("aws_region") or "us-east-1"
            if access and secret:
                return f"{access}:{secret}:{region}"
            return ""

        # Direct mapping for most providers
        key_map: dict[str, str] = {
            "openai_whisper": "openai",
            "google_speech": "google",
            "azure_speech": "azure",
            "azure_embedded": "azure",
            "deepgram": "deepgram",
            "assemblyai": "assemblyai",
            "gemini": "gemini",
            "groq_whisper": "groq",
            "rev_ai": "rev_ai",
            "speechmatics": "speechmatics",
            "elevenlabs": "elevenlabs",
            "auphonic": "auphonic",
        }

        store_key = key_map.get(provider_id, provider_id)
        return self._key_store.get_key(store_key) or ""

    # Transient error keywords for retry detection
    _TRANSIENT_KEYWORDS = (
        "timeout",
        "timed out",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "connection",
        "network",
        "temporarily unavailable",
        "service unavailable",
        "server error",
    )

    def _transcribe_with_retry(
        self,
        provider: Any,
        audio_path: str,
        job: Job,
        api_key: str,
        progress_callback: Any,
        max_retries: int = 2,
    ) -> Any:
        """Call provider.transcribe() with retry on transient failures.

        Uses exponential backoff (2s, 4s) for network/rate-limit errors.
        Non-transient errors (auth, format, missing key) are raised
        immediately.

        Args:
            provider: TranscriptionProvider instance.
            audio_path: Path to audio file.
            job: Current job for metadata.
            api_key: Resolved API key.
            progress_callback: Progress callback function.
            max_retries: Maximum retry attempts (default 2).

        Returns:
            TranscriptionResult from the provider.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return provider.transcribe(
                    audio_path=audio_path,
                    language=job.language,
                    model=job.model,
                    include_timestamps=job.include_timestamps,
                    include_diarization=job.include_diarization,
                    api_key=api_key,
                    progress_callback=progress_callback,
                )
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc).lower()
                is_transient = any(kw in err_msg for kw in self._TRANSIENT_KEYWORDS)

                if not is_transient or attempt >= max_retries:
                    raise

                delay = 2 ** (attempt + 1)  # 2s, 4s
                logger.warning(
                    "Transient error on attempt %d/%d for %s: %s " "(retrying in %ds)",
                    attempt + 1,
                    max_retries + 1,
                    job.display_name,
                    exc,
                    delay,
                )
                time.sleep(delay)

        # Should not reach here, but just in case
        raise last_exc or RuntimeError("Transcription failed after retries")

    def _notify_update(self, job: Job) -> None:
        """Fire the job-update callback if set.

        Args:
            job: The updated job.
        """
        if self._on_job_update:
            with contextlib.suppress(Exception):
                self._on_job_update(job)

    # ------------------------------------------------------------------
    # Post-transcription AI action
    # ------------------------------------------------------------------

    # Built-in AI action presets (name -> instructions)
    _BUILTIN_PRESETS: dict[str, str] = {
        "Meeting Minutes": (
            "You are a professional meeting minutes writer. "
            "Given the transcript below, "
            "produce well-structured meeting minutes that include:\n"
            "- Date/time and attendees (if identifiable)\n"
            "- Agenda items discussed\n"
            "- Key decisions made\n"
            "- Action items with owners and deadlines (if mentioned)\n"
            "- Follow-up items\n\n"
            "Use clear headings, bullet points, and concise language suitable "
            "for "
            "sharing with team members who were not present."
        ),
        "Action Items": (
            "You are a task extraction specialist. Analyze this "
            "transcript and extract every action item, task, "
            "commitment, follow-up, and to-do mentioned. "
            "For each item include:\n"
            "- What needs to be done\n"
            "- Who is responsible (if mentioned)\n"
            "- Deadline or timeline (if mentioned)\n"
            "- Priority level (high/medium/low, inferred from context)\n\n"
            "Present them as a numbered, actionable list."
        ),
        "Executive Summary": (
            "You are an executive briefing specialist. Produce a "
            "concise executive summary of this transcript suitable "
            "for senior leadership. Include:\n"
            "- One-paragraph overview (3-4 sentences)\n"
            "- Key takeaways (bullet points)\n"
            "- Strategic implications or concerns\n"
            "- Recommended next steps\n\n"
            "Keep the tone professional and focus on what matters most."
        ),
        "Interview Notes": (
            "You are an interview analysis expert. Create detailed "
            "interview notes "
            "from this transcript, including:\n"
            "- Candidate/interviewee information\n"
            "- Key questions asked and responses\n"
            "- Notable strengths and areas of concern\n"
            "- Relevant quotes\n"
            "- Overall assessment and recommendation\n\n"
            "Maintain objectivity and support observations with evidence from "
            "the transcript."
        ),
        "Lecture Notes": (
            "You are a study notes specialist. Transform this "
            "lecture/presentation "
            "transcript into well-organized study notes that include:\n"
            "- Main topics and subtopics with clear headings\n"
            "- Key concepts and definitions\n"
            "- Important examples and explanations\n"
            "- Formulas, processes, or frameworks mentioned\n"
            "- Questions raised and any answers given\n"
            "- Summary of key takeaways\n\n"
            "Use bullet points, numbered lists, and formatting "
            "for easy review."
        ),
        "Q&A Extraction": (
            "You are a Q&A extraction specialist. Identify every "
            "question asked in this transcript and its corresponding "
            "answer. Present them as a "
            "clean Q&A format:\n\n"
            "Q: [question]\n"
            "A: [answer]\n\n"
            "If a question was not answered, note it as 'Unanswered'. Include "
            "the speaker name if identifiable."
        ),
    }

    def _run_ai_action(self, job: Job) -> None:
        """Execute the post-transcription AI action for a completed job.

        Loads the AI action template (built-in preset or saved AgentConfig),
        builds a prompt with the template instructions and transcript text,
        and sends it to the configured AI provider.

        Args:
            job: Completed job with a transcript result and
                ai_action_template set.
        """
        template_ref = job.ai_action_template
        if not template_ref or not job.result:
            return

        logger.info(
            "Running AI action '%s' for job %s",
            template_ref,
            job.display_name,
        )
        job.ai_action_status = "running"
        self._notify_update(job)

        try:
            # Resolve instructions from template reference
            instructions = self._resolve_ai_action_instructions(template_ref)
            if not instructions:
                job.ai_action_status = "failed"
                job.ai_action_error = f"AI action template '{template_ref}' not found or empty."
                self._notify_update(job)
                return

            # Build transcript text
            result = job.result
            text = result.full_text
            if not text:
                text = "\n".join(s.text for s in result.segments)
            if not text.strip():
                job.ai_action_status = "failed"
                job.ai_action_error = "Transcript is empty — nothing to process."
                self._notify_update(job)
                return

            # Get AI provider
            if not self._app_settings or not self._key_store:
                job.ai_action_status = "failed"
                job.ai_action_error = "AI provider not configured."
                self._notify_update(job)
                return

            from bits_whisperer.core.ai_service import AIService

            ai_service = AIService(self._key_store, self._app_settings.ai)
            if not ai_service.is_configured():
                job.ai_action_status = "failed"
                job.ai_action_error = (
                    "No AI provider is configured. " "Add an API key in AI Provider Settings."
                )
                self._notify_update(job)
                return

            # Build prompt: instructions + attachments + transcript
            # (model-aware fitting).
            from bits_whisperer.core.context_manager import (
                create_context_manager,
            )

            model_id = ai_service.get_model_id()
            provider_id = self._app_settings.ai.selected_provider
            ctx_mgr = create_context_manager(self._app_settings.ai)

            # Resolve AI parameters from template
            max_tokens, temperature = self._resolve_ai_params(template_ref)

            # Resolve attachments from template and/or per-job overrides
            attachments_text = self._build_attachments_text(template_ref, job)

            prepared = ctx_mgr.prepare_action_context(
                model=model_id,
                provider=provider_id,
                instructions=instructions,
                transcript=text,
                attachments_text=attachments_text,
                response_reserve=max_tokens,
            )

            # Assemble the final prompt
            prompt_parts = [instructions, ""]
            if attachments_text:
                prompt_parts.append("--- ATTACHED DOCUMENTS ---")
                prompt_parts.append(attachments_text)
                prompt_parts.append("--- END ATTACHED DOCUMENTS ---")
                prompt_parts.append("")
            prompt_parts.append("--- TRANSCRIPT ---")
            prompt_parts.append(prepared.fitted_transcript)
            prompt_parts.append("--- END TRANSCRIPT ---")
            prompt_parts.append("")
            prompt_parts.append(
                "Please process this transcript according to the instructions " "above."
            )
            if attachments_text:
                prompt_parts.append(
                    "Use the attached documents as reference material " "where relevant."
                )
            prompt = "\n".join(prompt_parts)

            if prepared.budget.is_truncated:
                logger.info(
                    "AI action transcript truncated: %d -> %d tokens " "(%s strategy) for model %s",
                    prepared.budget.transcript_actual_tokens,
                    prepared.budget.transcript_fitted_tokens,
                    prepared.budget.strategy_used,
                    model_id,
                )

            # Call the AI provider
            provider = ai_service.get_provider()
            if not provider:
                job.ai_action_status = "failed"
                job.ai_action_error = "Failed to create AI provider instance."
                self._notify_update(job)
                return

            response = provider.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            if response.error:
                job.ai_action_status = "failed"
                job.ai_action_error = response.error
                logger.warning(
                    "AI action failed for %s: %s",
                    job.display_name,
                    response.error,
                )
            else:
                job.ai_action_result = response.text
                job.ai_action_status = "completed"
                logger.info(
                    "AI action completed for %s (%d chars, %d tokens)",
                    job.display_name,
                    len(response.text),
                    response.tokens_used,
                )

        except Exception as exc:
            job.ai_action_status = "failed"
            job.ai_action_error = str(exc)
            logger.exception(
                "AI action failed for %s: %s",
                job.display_name,
                exc,
            )

        self._notify_update(job)

    def _resolve_ai_action_instructions(self, template_ref: str) -> str:
        """Resolve template reference to instruction text.

        The template_ref can be:
        - A built-in preset name (e.g. "Meeting Minutes")
        - An absolute path to a saved AgentConfig JSON file

        Args:
            template_ref: Preset name or file path.

        Returns:
            The instruction text, or empty string if not found.
        """
        # Check built-in presets first
        if template_ref in self._BUILTIN_PRESETS:
            return self._BUILTIN_PRESETS[template_ref]

        # Try loading from file
        from pathlib import Path

        template_path = Path(template_ref)
        if not template_path.is_absolute():
            # Check in the agents directory
            template_path = DATA_DIR / "agents" / template_ref
            if not template_path.suffix:
                template_path = template_path.with_suffix(".json")

        if template_path.is_file():
            try:
                from bits_whisperer.core.copilot_service import AgentConfig

                config = AgentConfig.load(template_path)
                return config.instructions
            except Exception as exc:
                logger.warning(
                    "Failed to load AI action template '%s': %s",
                    template_ref,
                    exc,
                )
                return ""

        return ""

    def _resolve_ai_params(self, template_ref: str) -> tuple[int, float]:
        """Resolve AI parameters (max_tokens, temperature) from a template.

        Falls back to app settings defaults for built-in presets.

        Args:
            template_ref: Preset name or file path.

        Returns:
            Tuple of (max_tokens, temperature).
        """
        # For file-based templates, load the config
        from pathlib import Path

        template_path = Path(template_ref)
        if not template_path.is_absolute():
            template_path = DATA_DIR / "agents" / template_ref
            if not template_path.suffix:
                template_path = template_path.with_suffix(".json")

        if template_path.is_file():
            try:
                from bits_whisperer.core.copilot_service import AgentConfig

                config = AgentConfig.load(template_path)
                return config.max_tokens, config.temperature
            except Exception:
                pass

        # Default from settings or sensible fallbacks
        if self._app_settings:
            return (
                self._app_settings.ai.max_tokens,
                self._app_settings.ai.temperature,
            )
        return 4096, 0.3

    def _build_attachments_text(self, template_ref: str, job: Job) -> str:
        """Build formatted text from all attachments for the AI prompt.

        Collects attachments from the AgentConfig template (if file-based)
        and from per-job attachment overrides. Reads each file using
        the document reader and formats it with per-attachment instructions.

        Args:
            template_ref: Preset name or file path.
            job: The job being processed (may have per-job attachments).

        Returns:
            Formatted attachment text, or empty string if no attachments.
        """
        from bits_whisperer.core.copilot_service import Attachment
        from bits_whisperer.core.document_reader import read_document_safe

        attachments: list[Attachment] = []

        # 1. Collect from template AgentConfig
        template_path = Path(template_ref)
        if not template_path.is_absolute():
            template_path = DATA_DIR / "agents" / template_ref
            if not template_path.suffix:
                template_path = template_path.with_suffix(".json")
        if template_path.is_file():
            try:
                from bits_whisperer.core.copilot_service import AgentConfig

                config = AgentConfig.load(template_path)
                attachments.extend(config.attachments)
            except Exception as exc:
                logger.warning(
                    "Could not load attachments from template '%s': %s",
                    template_ref,
                    exc,
                )

        # 2. Collect from per-job attachments
        for att_dict in getattr(job, "ai_action_attachments", []):
            if isinstance(att_dict, dict):
                data = cast("dict[str, Any]", att_dict)
                attachments.append(Attachment.from_dict(data))
            elif isinstance(att_dict, Attachment):
                attachments.append(att_dict)

        if not attachments:
            return ""

        # 3. Read and format each attachment
        parts: list[str] = []
        for att in attachments:
            content = read_document_safe(att.file_path)
            header = f"=== Document: {att.name} ==="
            if att.instructions:
                header += f"\nInstructions: {att.instructions}"
            parts.append(f"{header}\n{content}\n=== End: {att.name} ===")
            logger.info(
                "Attached document '%s' (%d chars) for AI action",
                att.name,
                len(content),
            )

        return "\n\n".join(parts)

    def _check_batch_complete(self) -> None:
        """Check if all queued jobs are done and fire batch-complete callback.

        Uses ``_batch_notified`` to ensure the callback fires only once
        per batch, preventing repeated bell sounds and announcements.
        """
        jobs_snapshot: list[Job] | None = None
        with self._lock:
            if not self._all_jobs:
                return
            if self._batch_notified:
                return
            all_done = all(
                j.status
                in (
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                )
                for j in self._all_jobs
            )
            if (
                all_done
                and not self._active_jobs
                and self._job_queue.empty()
                and self._on_batch_complete
            ):
                self._batch_notified = True
                jobs_snapshot = list(self._all_jobs)

        # Fire callback outside the lock to avoid deadlock
        if jobs_snapshot is not None and self._on_batch_complete:
            with contextlib.suppress(Exception):
                self._on_batch_complete(jobs_snapshot)
