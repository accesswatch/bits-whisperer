"""Watch folder service — automatic transcription of new audio files.

Monitors a user-configured directory for new audio files and
automatically queues them for transcription with the user's default
provider and settings.

Detection strategy:
- **Primary**: ``watchdog`` OS-level filesystem events
  (ReadDirectoryChangesW on Windows, FSEvents on macOS, inotify on
  Linux) for near-instant detection.
- **Fallback**: If ``watchdog`` is unavailable, falls back to a
  polling loop at a configurable interval (default 5 s).

Completed transcripts are auto-exported alongside the original audio
file.  The service works even when the application is minimized to
the system tray, enabling a hands-free "drop and transcribe" workflow.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bits_whisperer.core.job import Job
from bits_whisperer.utils.constants import SUPPORTED_AUDIO_EXTENSIONS

if TYPE_CHECKING:
    from collections.abc import Callable

    from bits_whisperer.core.settings import AppSettings, WatchFolderSettings
    from bits_whisperer.core.transcription_service import TranscriptionService

logger = logging.getLogger(__name__)

# Minimum file age (seconds) before picking up — avoids grabbing
# partially-written files (e.g. still being copied/downloaded).
_MIN_FILE_AGE_SECONDS = 3.0

# Default polling interval in seconds.
_DEFAULT_POLL_SECONDS = 5.0


class WatchFolderService:
    """Polls a directory for new audio files and auto-transcribes them.

    Attributes:
        is_running: Whether the polling loop is active.
        watch_path: The directory being monitored, or None.
    """

    def __init__(
        self,
        transcription_service: TranscriptionService,
        app_settings: AppSettings,
        *,
        on_job_queued: Callable[[Job], None] | None = None,
        on_status_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Initialise the watch folder service.

        Args:
            transcription_service: Service to submit jobs to.
            app_settings: Application settings (provides provider, model, etc.).
            on_job_queued: Optional callback when a new job is queued.
            on_status_change: Optional callback when running state changes.
        """
        self._transcription_service = transcription_service
        self._app_settings = app_settings
        self._on_job_queued = on_job_queued
        self._on_status_change = on_status_change

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._seen_files: set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._observer: Any = None  # watchdog Observer (if available)

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def is_running(self) -> bool:
        """Whether the service is actively monitoring."""
        return self._running

    @property
    def watch_path(self) -> Path | None:
        """The directory being watched, or None if not running."""
        wf = self._app_settings.watch_folder
        if wf.enabled and wf.folder_path:
            return Path(wf.folder_path)
        return None

    @property
    def settings(self) -> WatchFolderSettings:
        """Current watch folder settings."""
        return self._app_settings.watch_folder

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """Start monitoring in the background.

        Uses ``watchdog`` for event-driven detection if available,
        otherwise falls back to a polling loop.

        Returns:
            True if started successfully, False if already running or
            the watch folder is not configured.
        """
        wf = self._app_settings.watch_folder
        if not wf.enabled or not wf.folder_path:
            logger.warning("Watch folder not enabled or folder path not set.")
            return False

        folder = Path(wf.folder_path)
        if not folder.is_dir():
            logger.warning("Watch folder does not exist: %s", folder)
            return False

        if self._running:
            logger.debug("Watch folder service already running.")
            return False

        self._stop_event.clear()

        # Pre-scan existing files so we don't re-process them
        if not wf.process_existing:
            self._prescan(folder)

        self._running = True

        # Try watchdog first, fall back to polling
        if self._start_watchdog(folder, wf):
            logger.info("Watch folder started (watchdog): %s", folder)
        else:
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="watch-folder",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Watch folder started (polling, %ds): %s",
                wf.poll_interval_seconds,
                folder,
            )

        self._notify_status(True)
        return True

    def stop(self) -> None:
        """Stop monitoring and join background threads."""
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        # Stop watchdog observer if active
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=10.0)
            except Exception as exc:
                logger.debug("Error stopping watchdog observer: %s", exc)
            self._observer = None

        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                logger.warning("Watch folder thread did not exit within timeout.")
            self._thread = None

        self._notify_status(False)
        logger.info("Watch folder stopped.")

    def restart(self) -> bool:
        """Stop and re-start — useful after settings change.

        Returns:
            True if restarted successfully.
        """
        self.stop()
        with self._lock:
            self._seen_files.clear()
        return self.start()

    # ------------------------------------------------------------------ #
    # Watchdog (event-driven) backend                                      #
    # ------------------------------------------------------------------ #

    def _start_watchdog(self, folder: Path, wf: WatchFolderSettings) -> bool:
        """Try to start a ``watchdog`` observer for *folder*.

        Args:
            folder: Directory to monitor.
            wf: Watch folder settings.

        Returns:
            True if watchdog started successfully, False if the library
            is unavailable or an error occurred.
        """
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            logger.debug("watchdog not installed — falling back to polling.")
            return False

        service = self  # capture for the inner class

        class _AudioHandler(FileSystemEventHandler):
            """Handles file creation and move events."""

            def on_created(self, event: Any) -> None:
                if not event.is_directory:
                    service._handle_watchdog_event(Path(event.src_path), wf)

            def on_moved(self, event: Any) -> None:
                if not event.is_directory:
                    service._handle_watchdog_event(Path(event.dest_path), wf)

        try:
            observer = Observer()
            observer.schedule(
                _AudioHandler(),
                str(folder),
                recursive=wf.include_subfolders,
            )
            observer.daemon = True
            observer.start()
            self._observer = observer
            return True
        except Exception as exc:
            logger.warning("Failed to start watchdog observer: %s", exc)
            return False

    def _handle_watchdog_event(self, path: Path, wf: WatchFolderSettings) -> None:
        """Process a single file event from watchdog.

        Applies the same filters as the polling path: extension check,
        deduplication, file age guard, empty-file guard.

        Args:
            path: Path to the file that was created or moved.
            wf: Watch folder settings.
        """
        if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            return

        canonical = str(path.resolve())
        with self._lock:
            if canonical in self._seen_files:
                return
            self._seen_files.add(canonical)

        # Wait for file to finish writing (age guard) in a short thread
        # so the watchdog handler returns promptly.
        def _delayed_queue() -> None:
            # Re-check age after a brief delay
            time.sleep(_MIN_FILE_AGE_SECONDS)
            try:
                if not path.exists() or path.stat().st_size == 0:
                    return
            except OSError:
                return
            self._queue_file(path, wf)

        threading.Thread(
            target=_delayed_queue,
            daemon=True,
            name="watch-folder-delay",
        ).start()

    # ------------------------------------------------------------------ #
    # Polling (fallback) backend                                           #
    # ------------------------------------------------------------------ #

    def _poll_loop(self) -> None:
        """Main polling loop — runs in a daemon thread."""
        wf = self._app_settings.watch_folder
        folder = Path(wf.folder_path)
        interval = max(1.0, wf.poll_interval_seconds)

        while not self._stop_event.is_set():
            try:
                self._scan_and_queue(folder, wf)
            except Exception as exc:
                logger.error("Watch folder scan error: %s", exc)

            # Sleep in short increments so stop() is responsive
            self._stop_event.wait(timeout=interval)

    def _scan_and_queue(
        self,
        folder: Path,
        wf: WatchFolderSettings,
    ) -> None:
        """Scan *folder* for new audio files and queue them.

        Args:
            folder: Directory to scan.
            wf: Watch folder settings.
        """
        if not folder.is_dir():
            return

        now = time.time()
        new_files: list[Path] = []

        # Iterate top-level or recursively based on settings
        pattern_iter = folder.rglob("*") if wf.include_subfolders else folder.iterdir()

        for entry in pattern_iter:
            if self._stop_event.is_set():
                return

            if not entry.is_file():
                continue

            if entry.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            canonical = str(entry.resolve())

            with self._lock:
                if canonical in self._seen_files:
                    continue
                # Reserve immediately to prevent race with next poll cycle
                self._seen_files.add(canonical)

            # Check file age — skip files still being written
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue

            if (now - mtime) < _MIN_FILE_AGE_SECONDS:
                continue

            # Check file size — skip empty files
            try:
                if entry.stat().st_size == 0:
                    continue
            except OSError:
                continue

            new_files.append(entry)

        # Queue each new file
        for file_path in new_files:
            self._queue_file(file_path, wf)

    def _queue_file(self, file_path: Path, wf: WatchFolderSettings) -> None:
        """Create a Job for *file_path* and submit it.

        Args:
            file_path: Audio file to transcribe.
            wf: Watch folder settings for provider/model defaults.
        """
        try:
            file_size = file_path.stat().st_size
        except OSError:
            logger.warning("Cannot stat watch folder file: %s", file_path)
            return

        # Resolve provider and model — use watch folder overrides or app defaults
        provider = wf.provider or self._app_settings.general.default_provider
        model = wf.model or self._app_settings.general.default_model
        language = wf.language or self._app_settings.general.language

        # Auto-generate display name: stem + timestamp
        stem = file_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        display_name = f"{stem} (watch {timestamp})"

        job = Job(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_size,
            provider=provider,
            model=model,
            language=language,
            include_timestamps=self._app_settings.transcription.include_timestamps,
            include_diarization=False,  # Simple watch-and-transcribe
            custom_name=display_name,
        )

        logger.info(
            "Watch folder queued: %s (provider=%s, model=%s)",
            file_path.name,
            provider,
            model,
        )

        # Submit to transcription service
        self._transcription_service.add_job(job)
        if not self._transcription_service.is_running:
            self._transcription_service.start()

        # Notify UI
        if self._on_job_queued:
            with contextlib.suppress(Exception):
                self._on_job_queued(job)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _prescan(self, folder: Path) -> None:
        """Record existing files so they are not re-processed on start.

        Args:
            folder: Directory to pre-scan.
        """
        wf = self._app_settings.watch_folder
        pattern_iter = folder.rglob("*") if wf.include_subfolders else folder.iterdir()

        count = 0
        for entry in pattern_iter:
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                canonical = str(entry.resolve())
                with self._lock:
                    self._seen_files.add(canonical)
                count += 1

        if count:
            logger.info(
                "Watch folder pre-scan: %d existing file(s) skipped.",
                count,
            )

    def _notify_status(self, running: bool) -> None:
        """Fire the status-change callback.

        Args:
            running: New running state.
        """
        if self._on_status_change:
            with contextlib.suppress(Exception):
                self._on_status_change(running)

    def get_seen_count(self) -> int:
        """Return the number of files seen (including pre-scanned).

        Returns:
            Number of distinct file paths tracked.
        """
        with self._lock:
            return len(self._seen_files)

    def clear_seen(self) -> None:
        """Clear the set of seen files.

        After calling this, previously-seen files will be re-processed
        on the next scan cycle.
        """
        with self._lock:
            self._seen_files.clear()
        logger.info("Watch folder seen-file cache cleared.")

    @staticmethod
    def validate_folder(path: str) -> tuple[bool, str]:
        """Validate a folder path for use as a watch folder.

        Args:
            path: Filesystem path to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not path:
            return False, "No folder path specified."
        p = Path(path)
        if not p.exists():
            return False, f"Path does not exist: {path}"
        if not p.is_dir():
            return False, f"Path is not a directory: {path}"
        # Check read permissions
        if not os.access(path, os.R_OK):
            return False, f"No read permission for: {path}"
        return True, ""
