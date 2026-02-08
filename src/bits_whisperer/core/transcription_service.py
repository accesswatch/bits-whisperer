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
from typing import Any

from bits_whisperer.core.audio_preprocessor import AudioPreprocessor
from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.core.provider_manager import ProviderManager
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.core.transcoder import Transcoder
from bits_whisperer.storage.key_store import KeyStore
from bits_whisperer.utils.constants import DEFAULT_MAX_CONCURRENT_JOBS

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
        self._provider_manager = provider_manager
        self._transcoder = transcoder
        self._key_store = key_store
        self._preprocessor = preprocessor or AudioPreprocessor()
        self._app_settings = app_settings
        self._max_workers = max_workers

        self._job_queue: queue.Queue[Job] = queue.Queue()
        self._active_jobs: dict[str, Job] = {}
        self._completed_jobs: list[Job] = []
        self._all_jobs: list[Job] = []
        self._workers: list[threading.Thread] = []
        self._running = False
        self._paused = False
        self._lock = threading.Lock()

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

    # ------------------------------------------------------------------
    # Queue control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start worker threads and begin processing the queue."""
        if self._running:
            return
        self._running = True
        self._paused = False
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop, name=f"transcription-worker-{i}", daemon=True
            )
            t.start()
            self._workers.append(t)
        logger.info("Transcription service started with %d workers.", self._max_workers)

    def stop(self) -> None:
        """Stop processing and shut down worker threads."""
        self._running = False
        # Unblock waiting workers
        for _ in self._workers:
            self._job_queue.put(None)  # type: ignore[arg-type]
        self._workers.clear()
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
        from bits_whisperer.core.sdk_installer import get_provider_sdk_info, is_sdk_available

        if not is_sdk_available(job.provider):
            sdk_info = get_provider_sdk_info(job.provider)
            name = sdk_info.display_name if sdk_info else job.provider
            raise RuntimeError(
                f"The {name} SDK is not installed. "
                "Please install it from the Model Manager or Settings before transcribing."
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
                f"{file_size_mb:.0f} MB exceeds {caps.max_file_size_mb} MB limit."
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

        pp = self._preprocessor
        if pp and pp.is_available() and pp.settings.enabled:
            try:
                logger.info("Preprocessing audio: %s", job.display_name)
                preprocessed = self._preprocessor.process(audio_path)
                audio_path = str(preprocessed)
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
                    audio_path, progress_callback=transcode_progress
                )
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

            apply_speaker_map(result, self._app_settings.diarization.speaker_map)

        # --- Step 5: Complete ---
        result.job_id = job.id
        job.result = result
        job.status = JobStatus.COMPLETED
        job.progress_percent = 100.0
        job.completed_at = datetime.now().isoformat()
        job.duration_seconds = result.duration_seconds
        self._notify_update(job)

        logger.info("Job completed: %s", job.display_name)

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
        """Call provider.transcribe() with automatic retry on transient failures.

        Uses exponential backoff (2s, 4s) for network/rate-limit errors.
        Non-transient errors (auth, format, missing key) are raised immediately.

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
                    "Transient error on attempt %d/%d for %s: %s (retrying in %ds)",
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

    def _check_batch_complete(self) -> None:
        """Check if all queued jobs are done and fire batch-complete callback."""
        with self._lock:
            if not self._all_jobs:
                return
            all_done = all(
                j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
                for j in self._all_jobs
            )
            if (
                all_done
                and self._active_jobs == {}
                and self._job_queue.empty()
                and self._on_batch_complete
            ):
                with contextlib.suppress(Exception):
                    self._on_batch_complete(list(self._all_jobs))
