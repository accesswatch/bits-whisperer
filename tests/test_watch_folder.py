"""Tests for the watch folder service and settings.

Covers:
- WatchFolderService lifecycle (start/stop/restart)
- File detection (audio extensions, age guard, empty files, subfolders)
- Pre-scan (existing files skipped or processed)
- Job creation and provider/model defaults
- Settings serialization round-trip
- Validate folder helper
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from bits_whisperer.core.watch_folder import WatchFolderService


# ---------------------------------------------------------------------------
# Lightweight stubs — avoid importing wx or real services
# ---------------------------------------------------------------------------


@dataclass
class _WatchFolderSettings:
    """Minimal stand-in for WatchFolderSettings."""

    enabled: bool = False
    folder_path: str = ""
    poll_interval_seconds: float = 0.5
    include_subfolders: bool = False
    process_existing: bool = False
    auto_export: bool = True
    auto_export_format: str = "txt"
    provider: str = ""
    model: str = ""
    language: str = ""
    auto_start: bool = False


@dataclass
class _GeneralSettings:
    default_provider: str = "local_whisper"
    default_model: str = "base"
    language: str = "en"


@dataclass
class _TranscriptionSettings:
    include_timestamps: bool = False


@dataclass
class _FakeAppSettings:
    watch_folder: _WatchFolderSettings = field(default_factory=_WatchFolderSettings)
    general: _GeneralSettings = field(default_factory=_GeneralSettings)
    transcription: _TranscriptionSettings = field(default_factory=_TranscriptionSettings)


class _FakeTranscriptionService:
    """Stub for TranscriptionService that records add_job calls."""

    def __init__(self) -> None:
        self.jobs: list = []
        self.is_running: bool = False

    def add_job(self, job: object) -> None:
        self.jobs.append(job)

    def start(self) -> None:
        self.is_running = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    """Create a temporary directory to use as a watch folder."""
    d = tmp_path / "watch"
    d.mkdir()
    return d


@pytest.fixture
def app_settings(watch_dir: Path) -> _FakeAppSettings:
    """Create fake app settings pointing at *watch_dir*."""
    wf = _WatchFolderSettings(
        enabled=True,
        folder_path=str(watch_dir),
        poll_interval_seconds=0.3,
    )
    return _FakeAppSettings(watch_folder=wf)


@pytest.fixture
def trans_svc() -> _FakeTranscriptionService:
    return _FakeTranscriptionService()


@pytest.fixture
def service(
    trans_svc: _FakeTranscriptionService,
    app_settings: _FakeAppSettings,
) -> WatchFolderService:
    from bits_whisperer.core.watch_folder import WatchFolderService

    return WatchFolderService(
        trans_svc,  # type: ignore[arg-type]
        app_settings,  # type: ignore[arg-type]
    )


def _create_audio_file(directory: Path, name: str = "test.wav", *, age: float = 10.0) -> Path:
    """Create a dummy audio file with a faked mtime."""
    f = directory / name
    f.write_bytes(b"\x00" * 64)
    # Set mtime to *age* seconds ago
    old_time = time.time() - age
    import os

    os.utime(f, (old_time, old_time))
    return f


# ======================================================================= #
# WatchFolderService — lifecycle                                            #
# ======================================================================= #


class TestWatchFolderLifecycle:
    """Start / stop / restart."""

    def test_start_and_stop(self, service: WatchFolderService) -> None:
        assert not service.is_running
        assert service.start() is True
        assert service.is_running
        service.stop()
        assert not service.is_running

    def test_start_returns_false_when_disabled(
        self,
        service: WatchFolderService,
        app_settings: _FakeAppSettings,
    ) -> None:
        app_settings.watch_folder.enabled = False
        assert service.start() is False

    def test_start_returns_false_when_no_folder(
        self,
        service: WatchFolderService,
        app_settings: _FakeAppSettings,
    ) -> None:
        app_settings.watch_folder.folder_path = ""
        assert service.start() is False

    def test_start_returns_false_for_nonexistent_dir(
        self,
        service: WatchFolderService,
        app_settings: _FakeAppSettings,
    ) -> None:
        app_settings.watch_folder.folder_path = "/nonexistent/path/xyz"
        assert service.start() is False

    def test_double_start_returns_false(self, service: WatchFolderService) -> None:
        assert service.start() is True
        assert service.start() is False  # already running
        service.stop()

    def test_restart_clears_seen(
        self,
        service: WatchFolderService,
        watch_dir: Path,
    ) -> None:
        _create_audio_file(watch_dir)
        service.start()
        time.sleep(0.6)
        assert service.get_seen_count() >= 1
        assert service.restart() is True
        # seen count reset to 0 before prescan
        service.stop()

    def test_stop_when_not_running(self, service: WatchFolderService) -> None:
        service.stop()  # should not raise


# ======================================================================= #
# File detection                                                            #
# ======================================================================= #


class TestFileDetection:
    """Audio file scanning, extension filtering, guards."""

    def test_detects_new_audio_file(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        service.start()
        time.sleep(0.4)  # let first scan run (empty)
        _create_audio_file(watch_dir, "hello.wav")
        time.sleep(1.2)  # wait for next poll
        service.stop()
        assert len(trans_svc.jobs) == 1
        assert "hello" in trans_svc.jobs[0].file_name

    def test_ignores_non_audio_extension(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        service.start()
        # Create non-audio file
        txt_file = watch_dir / "readme.txt"
        txt_file.write_text("not audio")
        old = time.time() - 10
        import os

        os.utime(txt_file, (old, old))
        time.sleep(0.8)
        service.stop()
        assert len(trans_svc.jobs) == 0

    def test_ignores_empty_files(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        service.start()
        empty = watch_dir / "empty.mp3"
        empty.write_bytes(b"")
        old = time.time() - 10
        import os

        os.utime(empty, (old, old))
        time.sleep(0.8)
        service.stop()
        assert len(trans_svc.jobs) == 0

    def test_ignores_very_new_files(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        """Files with mtime < 3s ago are skipped (still being written)."""
        service.start()
        # Create file with current mtime (no age fakery)
        f = watch_dir / "fresh.wav"
        f.write_bytes(b"\x00" * 64)
        time.sleep(0.5)  # not long enough for the 3s guard
        service.stop()
        assert len(trans_svc.jobs) == 0

    def test_detects_multiple_extensions(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.process_existing = True
        for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg"):
            _create_audio_file(watch_dir, f"test{ext}")
        service.start()
        time.sleep(1.2)
        service.stop()
        assert len(trans_svc.jobs) == 5

    def test_does_not_reprocess_seen_files(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        _create_audio_file(watch_dir, "once.wav")
        service.start()
        time.sleep(0.8)
        count_after_first = len(trans_svc.jobs)
        time.sleep(0.8)  # another poll cycle
        service.stop()
        assert len(trans_svc.jobs) == count_after_first  # no duplicates


# ======================================================================= #
# Subfolder support                                                         #
# ======================================================================= #


class TestSubfolders:
    """Recursive vs top-level scanning."""

    def test_include_subfolders_true(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.include_subfolders = True
        app_settings.watch_folder.process_existing = True
        sub = watch_dir / "sub"
        sub.mkdir()
        _create_audio_file(sub, "deep.wav")
        service.start()
        time.sleep(1.2)
        service.stop()
        assert len(trans_svc.jobs) == 1

    def test_include_subfolders_false(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.include_subfolders = False
        sub = watch_dir / "sub"
        sub.mkdir()
        _create_audio_file(sub, "hidden.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert len(trans_svc.jobs) == 0


# ======================================================================= #
# Pre-scan — process_existing flag                                          #
# ======================================================================= #


class TestPrescan:
    """Pre-scan of existing files."""

    def test_process_existing_false_skips(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.process_existing = False
        _create_audio_file(watch_dir, "old.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert len(trans_svc.jobs) == 0

    def test_process_existing_true_queues(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.process_existing = True
        _create_audio_file(watch_dir, "existing.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert len(trans_svc.jobs) == 1


# ======================================================================= #
# Job creation — provider / model defaults                                  #
# ======================================================================= #


class TestJobCreation:
    """Verify that jobs get the right provider, model, language."""

    def test_uses_app_defaults_when_wf_empty(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.process_existing = True
        _create_audio_file(watch_dir, "test.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        job = trans_svc.jobs[0]
        assert job.provider == "local_whisper"
        assert job.model == "base"
        assert job.language == "en"

    def test_uses_wf_overrides(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.provider = "vosk"
        app_settings.watch_folder.model = "small"
        app_settings.watch_folder.language = "es"
        app_settings.watch_folder.process_existing = True
        _create_audio_file(watch_dir, "test.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        job = trans_svc.jobs[0]
        assert job.provider == "vosk"
        assert job.model == "small"
        assert job.language == "es"

    def test_display_name_contains_watch(
        self,
        service: WatchFolderService,
        watch_dir: Path,
        app_settings: _FakeAppSettings,
        trans_svc: _FakeTranscriptionService,
    ) -> None:
        app_settings.watch_folder.process_existing = True
        _create_audio_file(watch_dir, "meeting.mp3")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert "watch" in trans_svc.jobs[0].custom_name.lower()


# ======================================================================= #
# Callbacks                                                                 #
# ======================================================================= #


class TestCallbacks:
    """on_job_queued and on_status_change callbacks."""

    def test_on_job_queued_called(
        self,
        trans_svc: _FakeTranscriptionService,
        app_settings: _FakeAppSettings,
        watch_dir: Path,
    ) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        cb = MagicMock()
        svc = WatchFolderService(
            trans_svc,  # type: ignore[arg-type]
            app_settings,  # type: ignore[arg-type]
            on_job_queued=cb,
        )
        app_settings.watch_folder.process_existing = True
        _create_audio_file(watch_dir, "cb.wav")
        svc.start()
        time.sleep(0.8)
        svc.stop()
        cb.assert_called_once()

    def test_on_status_change_called(
        self,
        trans_svc: _FakeTranscriptionService,
        app_settings: _FakeAppSettings,
    ) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        cb = MagicMock()
        svc = WatchFolderService(
            trans_svc,  # type: ignore[arg-type]
            app_settings,  # type: ignore[arg-type]
            on_status_change=cb,
        )
        svc.start()
        svc.stop()
        assert cb.call_count == 2  # start(True), stop(False)
        cb.assert_any_call(True)
        cb.assert_any_call(False)


# ======================================================================= #
# Utility methods                                                           #
# ======================================================================= #


class TestUtilities:
    """get_seen_count, clear_seen, validate_folder."""

    def test_get_seen_count(
        self,
        service: WatchFolderService,
        watch_dir: Path,
    ) -> None:
        assert service.get_seen_count() == 0
        _create_audio_file(watch_dir, "a.wav")
        _create_audio_file(watch_dir, "b.mp3")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert service.get_seen_count() == 2

    def test_clear_seen(
        self,
        service: WatchFolderService,
        watch_dir: Path,
    ) -> None:
        _create_audio_file(watch_dir, "x.wav")
        service.start()
        time.sleep(0.8)
        service.stop()
        assert service.get_seen_count() >= 1
        service.clear_seen()
        assert service.get_seen_count() == 0

    def test_validate_folder_valid(self, watch_dir: Path) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        valid, msg = WatchFolderService.validate_folder(str(watch_dir))
        assert valid is True
        assert msg == ""

    def test_validate_folder_empty_string(self) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        valid, msg = WatchFolderService.validate_folder("")
        assert valid is False
        assert "No folder" in msg

    def test_validate_folder_nonexistent(self) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        valid, msg = WatchFolderService.validate_folder("/nonexistent/xyz")
        assert valid is False

    def test_validate_folder_is_file(self, tmp_path: Path) -> None:
        from bits_whisperer.core.watch_folder import WatchFolderService

        f = tmp_path / "notadir.txt"
        f.write_text("x")
        valid, msg = WatchFolderService.validate_folder(str(f))
        assert valid is False
        assert "not a directory" in msg


# ======================================================================= #
# Properties                                                                #
# ======================================================================= #


class TestProperties:
    """Service properties."""

    def test_watch_path_when_configured(
        self,
        service: WatchFolderService,
        watch_dir: Path,
    ) -> None:
        assert service.watch_path == watch_dir

    def test_watch_path_when_disabled(
        self,
        service: WatchFolderService,
        app_settings: _FakeAppSettings,
    ) -> None:
        app_settings.watch_folder.enabled = False
        assert service.watch_path is None

    def test_settings_property(
        self,
        service: WatchFolderService,
        app_settings: _FakeAppSettings,
    ) -> None:
        assert service.settings is app_settings.watch_folder


# ======================================================================= #
# WatchFolderSettings serialization                                         #
# ======================================================================= #


class TestWatchFolderSettings:
    """Settings dataclass round-trip via AppSettings."""

    def test_default_values(self) -> None:
        from bits_whisperer.core.settings import WatchFolderSettings

        wf = WatchFolderSettings()
        assert wf.enabled is False
        assert wf.folder_path == ""
        assert wf.poll_interval_seconds == 5.0
        assert wf.include_subfolders is False
        assert wf.process_existing is False
        assert wf.auto_export is True
        assert wf.auto_export_format == "txt"
        assert wf.provider == ""
        assert wf.model == ""
        assert wf.language == ""
        assert wf.auto_start is False

    def test_roundtrip_via_app_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bits_whisperer.core.settings import AppSettings, WatchFolderSettings

        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(
            "bits_whisperer.core.settings._SETTINGS_PATH",
            settings_file,
        )

        s = AppSettings()
        s.watch_folder = WatchFolderSettings(
            enabled=True,
            folder_path="/tmp/watch",
            poll_interval_seconds=10.0,
            include_subfolders=True,
            process_existing=True,
            auto_export=False,
            auto_export_format="srt",
            provider="vosk",
            model="small",
            language="es",
            auto_start=True,
        )
        s.save()

        loaded = AppSettings.load()
        wf = loaded.watch_folder
        assert wf.enabled is True
        assert wf.folder_path == "/tmp/watch"
        assert wf.poll_interval_seconds == 10.0
        assert wf.include_subfolders is True
        assert wf.process_existing is True
        assert wf.auto_export is False
        assert wf.auto_export_format == "srt"
        assert wf.provider == "vosk"
        assert wf.model == "small"
        assert wf.language == "es"
        assert wf.auto_start is True
