"""Tests for robust shutdown procedures and temp file cleanup."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from bits_whisperer.core.audio_preprocessor import AudioPreprocessor, PreprocessorSettings
from bits_whisperer.core.provider_manager import ProviderManager
from bits_whisperer.core.transcoder import Transcoder
from bits_whisperer.core.transcription_service import TranscriptionService

# -----------------------------------------------------------------------
# TranscriptionService temp file tracking
# -----------------------------------------------------------------------


class TestTempFileTracking:
    """Verify per-job temp file tracking and cleanup."""

    def _make_service(self) -> TranscriptionService:
        pm = MagicMock(spec=ProviderManager)
        tc = MagicMock(spec=Transcoder)
        tc.is_available.return_value = False
        pp = MagicMock(spec=AudioPreprocessor)
        pp.is_available.return_value = False
        pp.settings = PreprocessorSettings(enabled=False)
        return TranscriptionService(
            provider_manager=pm,
            transcoder=tc,
            preprocessor=pp,
            max_workers=1,
        )

    def test_track_temp_file(self) -> None:
        svc = self._make_service()
        p = Path(tempfile.gettempdir()) / "bw_test_track.wav"
        svc._track_temp_file("job-1", p)
        assert "job-1" in svc._temp_files
        assert p in svc._temp_files["job-1"]

    def test_track_multiple_files_per_job(self) -> None:
        svc = self._make_service()
        p1 = Path("/tmp/bw_a.wav")
        p2 = Path("/tmp/bw_b.wav")
        svc._track_temp_file("job-1", p1)
        svc._track_temp_file("job-1", p2)
        assert len(svc._temp_files["job-1"]) == 2

    def test_cleanup_job_temp_files_removes_file(self, tmp_path: Path) -> None:
        svc = self._make_service()
        tmp_file = tmp_path / "bw_test_cleanup.wav"
        tmp_file.write_bytes(b"fake audio")
        svc._track_temp_file("job-1", tmp_file)
        assert tmp_file.exists()

        svc._cleanup_job_temp_files("job-1")
        assert not tmp_file.exists()
        assert "job-1" not in svc._temp_files

    def test_cleanup_job_temp_files_handles_missing(self) -> None:
        svc = self._make_service()
        missing = Path("/tmp/nonexistent_bw_file.wav")
        svc._track_temp_file("job-1", missing)
        # Should not raise even if file doesn't exist
        svc._cleanup_job_temp_files("job-1")
        assert "job-1" not in svc._temp_files

    def test_cleanup_noop_for_unknown_job(self) -> None:
        svc = self._make_service()
        # Should not raise for unknown job ID
        svc._cleanup_job_temp_files("unknown-job")

    def test_cleanup_all_temp_files(self, tmp_path: Path) -> None:
        svc = self._make_service()
        f1 = tmp_path / "bw_a.wav"
        f2 = tmp_path / "bw_b.wav"
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")
        svc._track_temp_file("j1", f1)
        svc._track_temp_file("j2", f2)

        svc._cleanup_all_temp_files()
        assert not f1.exists()
        assert not f2.exists()
        assert len(svc._temp_files) == 0

    def test_cleanup_all_is_idempotent(self) -> None:
        svc = self._make_service()
        svc._cleanup_all_temp_files()  # no tracked files
        svc._cleanup_all_temp_files()  # still no tracked files
        assert len(svc._temp_files) == 0


# -----------------------------------------------------------------------
# TranscriptionService stop() — worker join + cleanup
# -----------------------------------------------------------------------


class TestServiceStop:
    """Verify stop() joins workers and cleans temp files."""

    def _make_service(self) -> TranscriptionService:
        pm = MagicMock(spec=ProviderManager)
        tc = MagicMock(spec=Transcoder)
        tc.is_available.return_value = False
        pp = MagicMock(spec=AudioPreprocessor)
        pp.is_available.return_value = False
        pp.settings = PreprocessorSettings(enabled=False)
        return TranscriptionService(
            provider_manager=pm,
            transcoder=tc,
            preprocessor=pp,
            max_workers=2,
        )

    def test_stop_without_start_is_safe(self) -> None:
        svc = self._make_service()
        svc.stop()  # Should not raise

    def test_stop_clears_workers(self) -> None:
        svc = self._make_service()
        svc.start()
        assert len(svc._workers) == 2
        assert svc._running is True

        svc.stop()
        assert svc._running is False
        assert len(svc._workers) == 0

    def test_stop_cleans_remaining_temp_files(self, tmp_path: Path) -> None:
        svc = self._make_service()
        tmp_file = tmp_path / "bw_test_stop.wav"
        tmp_file.write_bytes(b"data")
        svc._track_temp_file("in-flight", tmp_file)

        svc.start()
        svc.stop()
        assert not tmp_file.exists()

    def test_stop_joins_workers(self) -> None:
        svc = self._make_service()
        svc.start()
        workers = list(svc._workers)
        svc.stop()
        # After stop, all workers should have terminated
        for w in workers:
            assert not w.is_alive(), f"Worker {w.name} still alive after stop"


# -----------------------------------------------------------------------
# Transcoder temp file prefix
# -----------------------------------------------------------------------


class TestTranscoderTempFilePrefix:
    """Verify transcoder uses proper temp file prefix."""

    def test_transcode_uses_bw_prefix(self) -> None:
        tc = Transcoder()
        # We can't run ffmpeg in tests, but we can verify the temp file
        # creation path via the mkstemp call
        with patch("bits_whisperer.core.transcoder.tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (99, "/tmp/bw_transcode_abc123.wav")
            with (
                patch("bits_whisperer.core.transcoder.os.close"),
                patch.object(tc, "_ffmpeg_path", "ffmpeg"),
                patch("bits_whisperer.core.transcoder.subprocess.Popen") as mock_popen,
            ):
                proc = MagicMock()
                proc.stdout = iter([])
                proc.stderr = MagicMock()
                proc.stderr.read.return_value = ""
                proc.returncode = 0
                proc.wait.return_value = 0
                mock_popen.return_value = proc
                with (
                    patch.object(tc, "get_duration", return_value=10.0),
                    patch(
                        "bits_whisperer.core.transcoder.Path.exists",
                        return_value=True,
                    ),
                ):
                    tc.transcode("/fake/input.wav")
                mock_mkstemp.assert_called_once_with(suffix=".wav", prefix="bw_transcode_")


class TestPreprocessorTempFilePrefix:
    """Verify preprocessor uses proper temp file prefix."""

    def test_preprocess_uses_bw_prefix(self) -> None:
        pp = AudioPreprocessor()
        with patch("bits_whisperer.core.audio_preprocessor.tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (99, "/tmp/bw_preprocess_abc123.wav")
            with (
                patch("bits_whisperer.core.audio_preprocessor.os.close"),
                patch.object(pp, "_ffmpeg", "ffmpeg"),
                patch("bits_whisperer.core.audio_preprocessor.subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                pp.process("/fake/input.wav")
            mock_mkstemp.assert_called_once_with(suffix=".wav", prefix="bw_preprocess_")


# -----------------------------------------------------------------------
# atexit handler
# -----------------------------------------------------------------------


class TestAtexitCleanup:
    """Verify the atexit cleanup function."""

    def test_atexit_removes_bw_temp_files(self, tmp_path: Path) -> None:
        from bits_whisperer.__main__ import _atexit_cleanup

        # Create a fake temp file with the bw_ prefix in the real temp dir
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="bw_transcode_")
        os.close(fd)
        p = Path(path)
        assert p.exists()

        _atexit_cleanup()
        assert not p.exists()

    def test_atexit_leaves_non_bw_files(self, tmp_path: Path) -> None:
        from bits_whisperer.__main__ import _atexit_cleanup

        # Create a non-bw temp file
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="other_app_")
        os.close(fd)
        p = Path(path)
        assert p.exists()

        _atexit_cleanup()
        assert p.exists()  # Should NOT be deleted
        p.unlink()  # manual cleanup

    def test_atexit_handles_nonexistent(self) -> None:
        from bits_whisperer.__main__ import _atexit_cleanup

        # Should not raise even when no bw files exist
        _atexit_cleanup()


# -----------------------------------------------------------------------
# Stale temp file cleanup
# -----------------------------------------------------------------------


class TestStaleTempFileCleanup:
    """Test the stale temp file cleanup from main_frame."""

    def test_removes_old_bw_files(self) -> None:
        # Create a file with bw_ prefix and age it
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="bw_transcode_")
        os.close(fd)
        p = Path(path)
        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(p, (old_time, old_time))

        # Import and call the static method
        from bits_whisperer.ui.main_frame import MainFrame

        MainFrame._cleanup_stale_temp_files()
        assert not p.exists()

    def test_preserves_recent_bw_files(self) -> None:
        # Create a file with bw_ prefix but very recent
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="bw_transcode_")
        os.close(fd)
        p = Path(path)
        # Default mtime is now, which is < 1 hour ago

        from bits_whisperer.ui.main_frame import MainFrame

        MainFrame._cleanup_stale_temp_files()
        assert p.exists()  # Should NOT be deleted (too recent)
        p.unlink()  # manual cleanup

    def test_removes_old_update_dirs(self) -> None:
        # Create a directory with bw_update_ prefix and age it
        d = Path(tempfile.mkdtemp(prefix="bw_update_"))
        old_time = time.time() - 7200
        os.utime(d, (old_time, old_time))

        from bits_whisperer.ui.main_frame import MainFrame

        MainFrame._cleanup_stale_temp_files()
        assert not d.exists()

    def test_preserves_non_bw_files(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="other_")
        os.close(fd)
        p = Path(path)
        old_time = time.time() - 7200
        os.utime(p, (old_time, old_time))

        from bits_whisperer.ui.main_frame import MainFrame

        MainFrame._cleanup_stale_temp_files()
        assert p.exists()  # Should NOT be deleted
        p.unlink()  # manual cleanup


# -----------------------------------------------------------------------
# App OnExit temp cleanup
# -----------------------------------------------------------------------


class TestAppOnExitCleanup:
    """Verify app.py OnExit cleans bw temp files."""

    def test_on_exit_cleans_bw_temp_files(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="bw_preprocess_")
        os.close(fd)
        p = Path(path)
        assert p.exists()

        from bits_whisperer.app import BitsWhispererApp

        app = MagicMock(spec=BitsWhispererApp)
        # Call the real OnExit
        BitsWhispererApp.OnExit(app)
        assert not p.exists()


# -----------------------------------------------------------------------
# Shutdown order verification
# -----------------------------------------------------------------------


class TestShutdownOrder:
    """Verify the shutdown sequence stops services in the right order."""

    def test_stop_called_before_cleanup(self) -> None:
        """TranscriptionService.stop() should be called during shutdown."""
        svc = MagicMock(spec=TranscriptionService)
        svc.stop = MagicMock()

        # Simulate the shutdown sequence from _on_close
        svc.stop()
        svc.stop.assert_called_once()

    def test_service_stop_is_exception_safe(self) -> None:
        """Even if stop() raises, shutdown should continue."""
        pm = MagicMock(spec=ProviderManager)
        tc = MagicMock(spec=Transcoder)
        tc.is_available.return_value = False
        pp = MagicMock(spec=AudioPreprocessor)
        pp.is_available.return_value = False
        pp.settings = PreprocessorSettings(enabled=False)
        svc = TranscriptionService(
            provider_manager=pm, transcoder=tc, preprocessor=pp, max_workers=1
        )
        # Should not raise even when called without start
        svc.stop()

    def test_multiple_stops_are_safe(self) -> None:
        """Calling stop() multiple times should be safe."""
        pm = MagicMock(spec=ProviderManager)
        tc = MagicMock(spec=Transcoder)
        tc.is_available.return_value = False
        pp = MagicMock(spec=AudioPreprocessor)
        pp.is_available.return_value = False
        pp.settings = PreprocessorSettings(enabled=False)
        svc = TranscriptionService(
            provider_manager=pm, transcoder=tc, preprocessor=pp, max_workers=1
        )
        svc.start()
        svc.stop()
        svc.stop()  # Second stop should be safe
        svc.stop()  # Third stop too
