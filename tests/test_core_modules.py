"""Tests for core modules: device_probe, audio_player, transcoder, document_reader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.audio_player import AudioPlayer
from bits_whisperer.core.device_probe import DeviceProbe, DeviceProfile
from bits_whisperer.core.document_reader import (
    SUPPORTED_EXTENSIONS,
    is_supported,
    read_document,
    read_document_safe,
)
from bits_whisperer.core.transcoder import Transcoder
from bits_whisperer.utils.constants import WhisperModelInfo
from bits_whisperer.utils.platform_utils import find_ffmpeg

# ---------------------------------------------------------------------------
# DeviceProbe
# ---------------------------------------------------------------------------


class TestDeviceProfile:
    """DeviceProfile dataclass defaults."""

    def test_default_values(self) -> None:
        p = DeviceProfile()
        assert p.cpu_name == ""
        assert p.cpu_cores_physical == 0
        assert p.cpu_cores_logical == 0
        assert p.has_avx is False
        assert p.has_avx2 is False
        assert p.ram_gb == 0.0
        assert p.gpu_name == ""
        assert p.gpu_vram_gb == 0.0
        assert p.has_cuda is False
        assert p.eligible_models == []
        assert p.warned_models == []
        assert p.ineligible_models == []


class TestDeviceProbe:
    """DeviceProbe hardware detection and model eligibility."""

    def _make_probe(self) -> DeviceProbe:
        return DeviceProbe()

    def _model(
        self,
        model_id: str = "tiny",
        name: str = "Tiny",
        min_ram_gb: int = 2,
        min_vram_gb: int = 0,
        min_cpu_cores: int = 1,
    ) -> WhisperModelInfo:
        """Helper to create a WhisperModelInfo with test defaults."""
        return WhisperModelInfo(
            id=model_id,
            name=name,
            description="Test model",
            parameters_m=39,
            disk_size_mb=75,
            min_ram_gb=min_ram_gb,
            min_vram_gb=min_vram_gb,
            min_cpu_cores=min_cpu_cores,
            speed_stars=3,
            accuracy_stars=3,
            languages=99,
        )

    def test_model_fully_eligible_cpu_only(self) -> None:
        """CPU-only model with sufficient RAM and cores."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=8.0)
        model = self._model(min_ram_gb=2, min_vram_gb=0, min_cpu_cores=2)
        assert probe._model_fully_eligible(model, profile) is True

    def test_model_fully_eligible_gpu(self) -> None:
        """GPU model with sufficient VRAM and RAM."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=16.0, has_cuda=True, gpu_vram_gb=8.0)
        model = self._model(
            model_id="large", name="Large", min_ram_gb=10, min_vram_gb=6, min_cpu_cores=4
        )
        assert probe._model_fully_eligible(model, profile) is True

    def test_model_ineligible_low_ram(self) -> None:
        """Model requires more RAM than available."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=4.0)
        model = self._model(
            model_id="large", name="Large", min_ram_gb=10, min_vram_gb=0, min_cpu_cores=2
        )
        assert probe._model_fully_eligible(model, profile) is False

    def test_model_ineligible_needs_gpu(self) -> None:
        """Model requires GPU but none available."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=16.0, has_cuda=False)
        model = self._model(
            model_id="large", name="Large", min_ram_gb=10, min_vram_gb=6, min_cpu_cores=4
        )
        assert probe._model_fully_eligible(model, profile) is False

    def test_model_warn_eligible_cpu_fallback(self) -> None:
        """Small GPU model on CPU with enough RAM — warn-eligible."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=8.0, has_cuda=False)
        model = self._model(
            model_id="small", name="Small", min_ram_gb=4, min_vram_gb=2, min_cpu_cores=2
        )
        assert probe._model_warn_eligible(model, profile) is True

    def test_model_warn_eligible_low_vram(self) -> None:
        """GPU with less VRAM than ideal but >70% — warn-eligible."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=16.0, has_cuda=True, gpu_vram_gb=5.0)
        model = self._model(
            model_id="large", name="Large", min_ram_gb=10, min_vram_gb=6, min_cpu_cores=4
        )
        # 5.0 >= 6.0 * 0.7 = 4.2 → True
        assert probe._model_warn_eligible(model, profile) is True

    def test_evaluate_models(self) -> None:
        """Classify models into eligible/warned/ineligible."""
        probe = self._make_probe()
        profile = DeviceProfile(cpu_cores_physical=4, ram_gb=8.0, has_cuda=False)
        probe._evaluate_models(profile)
        # At least tiny should be eligible
        assert "tiny" in profile.eligible_models
        # Some large models should be ineligible
        assert len(profile.ineligible_models) > 0

    def test_is_model_eligible(self) -> None:
        probe = self._make_probe()
        probe._profile = DeviceProfile(
            eligible_models=["tiny", "base"],
            warned_models=["small"],
            ineligible_models=["large"],
        )
        assert probe.is_model_eligible("tiny") is True
        assert probe.is_model_eligible("small") is True
        assert probe.is_model_eligible("large") is False

    def test_get_eligibility_reason_eligible(self) -> None:
        probe = self._make_probe()
        probe._profile = DeviceProfile(eligible_models=["tiny"])
        model = self._model(min_ram_gb=2, min_vram_gb=0, min_cpu_cores=1)
        reason = probe.get_eligibility_reason(model)
        assert "can run this model" in reason

    def test_get_eligibility_reason_warned(self) -> None:
        probe = self._make_probe()
        probe._profile = DeviceProfile(warned_models=["small"])
        model = self._model(
            model_id="small", name="Small", min_ram_gb=4, min_vram_gb=2, min_cpu_cores=2
        )
        reason = probe.get_eligibility_reason(model)
        assert "may be slow" in reason

    def test_get_eligibility_reason_ineligible(self) -> None:
        probe = self._make_probe()
        probe._profile = DeviceProfile(ram_gb=4.0, cpu_cores_physical=2, has_cuda=False)
        model = self._model(
            model_id="large", name="Large", min_ram_gb=10, min_vram_gb=6, min_cpu_cores=4
        )
        reason = probe.get_eligibility_reason(model)
        assert "can't run" in reason
        assert "RAM" in reason or "GPU" in reason

    def test_get_recommended_model(self) -> None:
        probe = self._make_probe()
        probe._profile = DeviceProfile(
            eligible_models=["tiny", "base", "small"],
            warned_models=["medium"],
            ineligible_models=["large"],
        )
        recommended = probe.get_recommended_model()
        assert recommended == "small"  # best eligible (non-warned)


# ---------------------------------------------------------------------------
# AudioPlayer
# ---------------------------------------------------------------------------


class TestAudioPlayerAtempo:
    """AudioPlayer._build_atempo_chain — pure logic, no I/O."""

    def test_speed_1x_no_filter(self) -> None:
        """Speed 1.0 should return empty string."""
        assert AudioPlayer._build_atempo_chain(1.0) == ""

    def test_speed_1_5x(self) -> None:
        result = AudioPlayer._build_atempo_chain(1.5)
        assert "atempo=1.500" in result

    def test_speed_2x(self) -> None:
        result = AudioPlayer._build_atempo_chain(2.0)
        assert "atempo=2.000" in result

    def test_speed_4x_chained(self) -> None:
        """Speed > 2.0 must chain multiple atempo filters."""
        result = AudioPlayer._build_atempo_chain(4.0)
        parts = result.split(",")
        assert len(parts) >= 2
        assert "atempo=2.000" in parts[0]

    def test_speed_0_5x(self) -> None:
        result = AudioPlayer._build_atempo_chain(0.5)
        assert "atempo=0.500" in result

    def test_speed_0_25x_chained(self) -> None:
        """Speed < 0.5 must chain atempo filters."""
        result = AudioPlayer._build_atempo_chain(0.25)
        parts = result.split(",")
        assert len(parts) >= 2


class TestAudioPlayerClipRange:
    """AudioPlayer.set_clip_range — no audio needed."""

    def _make_player(self) -> AudioPlayer:
        with (
            patch.object(AudioPlayer, "_find_ffmpeg", return_value="ffmpeg"),
            patch.object(AudioPlayer, "_get_default_sample_rate", return_value=48000),
        ):
            player = AudioPlayer()
        player._duration = 30.0
        return player

    def test_set_clip_range(self) -> None:
        player = self._make_player()
        player.set_clip_range(5.0, 15.0)
        assert player._selection_start == 5.0
        assert player._selection_end == 15.0

    def test_set_clip_range_end_before_start(self) -> None:
        """If end <= start, end should be set to None (full duration)."""
        player = self._make_player()
        player.set_clip_range(10.0, 5.0)
        assert player._selection_start == 10.0
        assert player._selection_end is None

    def test_set_clip_range_negative_start(self) -> None:
        """Negative start should clamp to 0."""
        player = self._make_player()
        player.set_clip_range(-5.0, 10.0)
        assert player._selection_start == 0.0

    def test_set_speed_clamped(self) -> None:
        player = self._make_player()
        player.set_speed(0.1)
        assert player._speed == 0.25

        player.set_speed(20.0)
        assert player._speed == 8.0

    def test_initial_state(self) -> None:
        player = self._make_player()
        assert player.is_playing is False
        assert player.duration == 30.0


class TestAudioPlayerCallbacks:
    """AudioPlayer callback registration."""

    def _make_player(self) -> AudioPlayer:
        with (
            patch.object(AudioPlayer, "_find_ffmpeg", return_value="ffmpeg"),
            patch.object(AudioPlayer, "_get_default_sample_rate", return_value=48000),
        ):
            return AudioPlayer()

    def test_progress_callback_registration(self) -> None:
        player = self._make_player()
        cb = MagicMock()
        player.set_progress_callback(cb)
        assert player._progress_cb is cb

    def test_state_callback_fires(self) -> None:
        player = self._make_player()
        cb = MagicMock()
        player.set_state_callback(cb)
        player._fire_state("stopped")
        cb.assert_called_once_with("stopped")


# ---------------------------------------------------------------------------
# Transcoder
# ---------------------------------------------------------------------------


class TestTranscoder:
    """Transcoder utility."""

    def test_is_available(self) -> None:
        """Transcoder should detect ffmpeg availability."""
        t = Transcoder()
        # Just test the method exists and returns bool
        assert isinstance(t.is_available(), bool)

    def test_transcode_missing_input(self, tmp_path: Path) -> None:
        """Should raise TranscoderError for missing input file."""
        from bits_whisperer.core.transcoder import TranscoderError

        t = Transcoder()
        if not t.is_available():
            pytest.skip("ffmpeg not installed")
        with pytest.raises(TranscoderError, match="Input file not found"):
            t.transcode(tmp_path / "nonexistent.wav")


# ---------------------------------------------------------------------------
# DocumentReader
# ---------------------------------------------------------------------------


class TestDocumentReaderSupported:
    """Extension support detection."""

    def test_txt_supported(self) -> None:
        assert is_supported("file.txt")

    def test_md_supported(self) -> None:
        assert is_supported("file.md")

    def test_csv_supported(self) -> None:
        assert is_supported("file.csv")

    def test_json_supported(self) -> None:
        assert is_supported("file.json")

    def test_xml_supported(self) -> None:
        assert is_supported("file.xml")

    def test_yaml_supported(self) -> None:
        assert is_supported("file.yaml")

    def test_docx_supported(self) -> None:
        assert is_supported("doc.docx")

    def test_pdf_supported(self) -> None:
        assert is_supported("doc.pdf")

    def test_xlsx_supported(self) -> None:
        assert is_supported("data.xlsx")

    def test_rtf_supported(self) -> None:
        assert is_supported("doc.rtf")

    def test_unsupported_extension(self) -> None:
        assert not is_supported("file.exe")

    def test_unsupported_mp3(self) -> None:
        assert not is_supported("audio.mp3")

    def test_supported_extensions_is_frozen(self) -> None:
        """SUPPORTED_EXTENSIONS should be immutable."""
        assert isinstance(SUPPORTED_EXTENSIONS, frozenset)


class TestDocumentReaderText:
    """Plain text file reading."""

    def test_read_txt(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello world", encoding="utf-8")
        assert read_document(f) == "Hello world"

    def test_read_md(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nParagraph", encoding="utf-8")
        content = read_document(f)
        assert "# Title" in content
        assert "Paragraph" in content

    def test_read_json(self, tmp_path: Path) -> None:
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        content = read_document(f)
        assert '"key"' in content

    def test_read_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "test.csv"
        f.write_text("a,b,c\n1,2,3", encoding="utf-8")
        content = read_document(f)
        assert "a,b,c" in content

    def test_read_utf8_bom(self, tmp_path: Path) -> None:
        """Read UTF-8 with BOM."""
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello BOM")
        content = read_document(f)
        assert "Hello BOM" in content

    def test_read_latin1(self, tmp_path: Path) -> None:
        """Fall back to Latin-1 for non-UTF-8 files."""
        f = tmp_path / "latin.txt"
        f.write_bytes(b"caf\xe9")
        content = read_document(f)
        assert "caf" in content


class TestDocumentReaderErrors:
    """Error handling in document reader."""

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_document("nonexistent.txt")

    def test_file_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_text("x", encoding="utf-8")

        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 20 * 1024 * 1024
        mock_stat_result.st_mode = f.stat().st_mode

        with (
            patch.object(Path, "stat", return_value=mock_stat_result),
            patch.object(Path, "is_file", return_value=True),
            pytest.raises(ValueError, match="too large"),
        ):
            read_document(f)

    def test_read_document_safe_returns_error_string(self) -> None:
        result = read_document_safe("nonexistent_file.txt")
        assert "[Error" in result

    def test_read_document_safe_success(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.txt"
        f.write_text("safe content", encoding="utf-8")
        assert read_document_safe(f) == "safe content"


# ---------- platform_utils.find_ffmpeg ----------


class TestFindFfmpeg:
    """Tests for the centralised find_ffmpeg helper."""

    def test_found_on_path(self) -> None:
        with patch(
            "bits_whisperer.utils.platform_utils.shutil.which", return_value="/usr/bin/ffmpeg"
        ):
            assert find_ffmpeg() == "/usr/bin/ffmpeg"

    def test_fallback_windows_path(self) -> None:
        existing_path = r"C:\ffmpeg\bin\ffmpeg.exe"
        with (
            patch("bits_whisperer.utils.platform_utils.shutil.which", return_value=None),
            patch("bits_whisperer.utils.platform_utils.Path.exists", return_value=True),
        ):
            result = find_ffmpeg()
            assert result == existing_path

    def test_returns_empty_when_not_found(self) -> None:
        with patch("bits_whisperer.utils.platform_utils.shutil.which", return_value=None):
            assert find_ffmpeg() == ""


# ---------- ai_service retry helpers ----------


class TestAIRetryHelpers:
    """Tests for _is_retryable in ai_service."""

    def test_retryable_by_class_name(self) -> None:
        from bits_whisperer.core.ai_service import _is_retryable

        class RateLimitError(Exception):
            pass

        assert _is_retryable(RateLimitError("too many")) is True

    def test_not_retryable_generic(self) -> None:
        from bits_whisperer.core.ai_service import _is_retryable

        assert _is_retryable(ValueError("bad value")) is False

    def test_retryable_timeout(self) -> None:
        from bits_whisperer.core.ai_service import _is_retryable

        class APITimeoutError(Exception):
            pass

        assert _is_retryable(APITimeoutError()) is True

    def test_retryable_connection_error(self) -> None:
        from bits_whisperer.core.ai_service import _is_retryable

        class APIConnectionError(Exception):
            pass

        assert _is_retryable(APIConnectionError()) is True

    def test_not_retryable_status_code_400(self) -> None:
        from bits_whisperer.core.ai_service import _is_retryable

        exc = ValueError("bad request")
        assert _is_retryable(exc) is False
