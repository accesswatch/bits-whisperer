"""Background scheduler for recurring maintenance tasks.

Provides an optional scheduler (using ``APScheduler`` when available,
or a simple ``threading.Timer``-based fallback) for:

- Model cache pruning (enforce disk quota)
- Ollama daemon health checks
- Feature flag / model catalog refresh

The scheduler is started once by the application and stopped on exit.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bits_whisperer.core.settings import SchedulerSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job descriptor
# ---------------------------------------------------------------------------


@dataclass
class ScheduledJob:
    """Describes a recurring job to be executed by the scheduler."""

    job_id: str
    name: str
    func: Callable[[], Any]
    interval_seconds: float
    enabled: bool = True


# ---------------------------------------------------------------------------
# Timer-based fallback scheduler
# ---------------------------------------------------------------------------


class _TimerScheduler:
    """Simple repeating-timer scheduler for environments without APScheduler."""

    def __init__(self) -> None:
        self._timers: dict[str, threading.Timer] = {}
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False

    def add_job(self, job: ScheduledJob) -> None:
        """Register a recurring job."""
        self._jobs[job.job_id] = job
        if self._running and job.enabled:
            self._start_timer(job)

    def start(self) -> None:
        """Start all registered jobs."""
        self._running = True
        for job in self._jobs.values():
            if job.enabled:
                self._start_timer(job)

    def stop(self) -> None:
        """Cancel all running timers."""
        self._running = False
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()

    def _start_timer(self, job: ScheduledJob) -> None:
        """Start a repeating timer for a single job."""

        def _run() -> None:
            if not self._running:
                return
            try:
                job.func()
            except Exception:
                logger.exception("Scheduled job '%s' failed", job.job_id)
            if self._running and job.enabled:
                self._start_timer(job)

        timer = threading.Timer(job.interval_seconds, _run)
        timer.daemon = True
        timer.name = f"sched-{job.job_id}"
        self._timers[job.job_id] = timer
        timer.start()


# ---------------------------------------------------------------------------
# Scheduler service
# ---------------------------------------------------------------------------


@dataclass
class SchedulerService:
    """Application-level scheduler that manages recurring maintenance jobs.

    Tries to use APScheduler if installed, otherwise falls back to a
    simple timer-based implementation.

    Args:
        settings: Scheduler configuration from AppSettings.
    """

    settings: SchedulerSettings
    _jobs: list[ScheduledJob] = field(default_factory=list, repr=False)
    _backend: Any = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)

    def register_job(self, job: ScheduledJob) -> None:
        """Register a job to be started when the scheduler starts.

        Args:
            job: Job descriptor with function and interval.
        """
        self._jobs.append(job)
        logger.debug(
            "Registered scheduler job '%s' (interval=%.0fs, enabled=%s)",
            job.job_id,
            job.interval_seconds,
            job.enabled,
        )

    def start(self) -> None:
        """Start the scheduler and all enabled jobs."""
        if not self.settings.enabled:
            logger.info("Scheduler disabled in settings.")
            return
        if self._running:
            return

        self._backend = self._create_backend()

        for job in self._jobs:
            if not job.enabled:
                continue
            self._add_to_backend(job)

        self._start_backend()
        self._running = True
        logger.info(
            "Scheduler started with %d job(s).",
            sum(1 for j in self._jobs if j.enabled),
        )

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if not self._running:
            return
        self._running = False
        self._stop_backend()
        logger.info("Scheduler stopped.")

    @property
    def is_running(self) -> bool:
        """Return whether the scheduler is currently active."""
        return self._running

    # ------------------------------------------------------------------
    # Backend management
    # ------------------------------------------------------------------

    def _create_backend(self) -> Any:
        """Create the scheduler backend (APScheduler or timer fallback)."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            scheduler = BackgroundScheduler(daemon=True)
            logger.debug("Using APScheduler backend.")
            return scheduler
        except ImportError:
            logger.debug("APScheduler not available; using timer-based fallback.")
            return _TimerScheduler()

    def _add_to_backend(self, job: ScheduledJob) -> None:
        """Add a job to the active backend."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            if isinstance(self._backend, BackgroundScheduler):
                self._backend.add_job(
                    job.func,
                    "interval",
                    seconds=job.interval_seconds,
                    id=job.job_id,
                    name=job.name,
                    replace_existing=True,
                    max_instances=1,
                )
                return
        except ImportError:
            pass

        # Fallback
        if isinstance(self._backend, _TimerScheduler):
            self._backend.add_job(job)

    def _start_backend(self) -> None:
        """Start the backend scheduler."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            if isinstance(self._backend, BackgroundScheduler):
                self._backend.start()
                return
        except ImportError:
            pass
        if isinstance(self._backend, _TimerScheduler):
            self._backend.start()

    def _stop_backend(self) -> None:
        """Stop the backend scheduler."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            if isinstance(self._backend, BackgroundScheduler):
                self._backend.shutdown(wait=False)
                return
        except ImportError:
            pass
        if isinstance(self._backend, _TimerScheduler):
            self._backend.stop()
