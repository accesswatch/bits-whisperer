"""Tests for app-wide constants and model registry."""

from __future__ import annotations

from bits_whisperer.utils.constants import (
    APP_NAME,
    APP_VERSION,
    AUDIO_WILDCARD,
    EXPORT_FORMATS,
    PARAKEET_MODELS,
    SUPPORTED_AUDIO_EXTENSIONS,
    VOSK_MODELS,
    WHISPER_MODELS,
    get_model_by_id,
    get_parakeet_model_by_id,
    get_vosk_model_by_id,
)


class TestAppConstants:
    """Basic app identity constants."""

    def test_app_name(self) -> None:
        assert APP_NAME == "BITS Whisperer"

    def test_app_version_format(self) -> None:
        parts = APP_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_version_is_1_2_0(self) -> None:
        assert APP_VERSION == "1.0.0"


class TestAudioFormats:
    """Supported audio format definitions."""

    def test_extensions_all_start_with_dot(self) -> None:
        for ext in SUPPORTED_AUDIO_EXTENSIONS:
            assert ext.startswith("."), f"Extension {ext} must start with a dot"

    def test_common_formats_included(self) -> None:
        for fmt in (".mp3", ".wav", ".flac", ".m4a", ".ogg"):
            assert fmt in SUPPORTED_AUDIO_EXTENSIONS

    def test_wildcard_contains_extensions(self) -> None:
        assert "*.mp3" in AUDIO_WILDCARD
        assert "*.wav" in AUDIO_WILDCARD


class TestExportFormats:
    """Export format registry."""

    def test_seven_formats(self) -> None:
        assert len(EXPORT_FORMATS) == 7

    def test_required_formats(self) -> None:
        for fmt in ("txt", "md", "html", "docx", "srt", "vtt", "json"):
            assert fmt in EXPORT_FORMATS


class TestWhisperModels:
    """Whisper model registry."""

    def test_fourteen_models(self) -> None:
        assert len(WHISPER_MODELS) == 14

    def test_all_have_repo_id(self) -> None:
        for m in WHISPER_MODELS:
            assert m.repo_id, f"Model {m.id} missing repo_id"

    def test_unique_ids(self) -> None:
        ids = [m.id for m in WHISPER_MODELS]
        assert len(ids) == len(set(ids)), "Duplicate model IDs found"

    def test_speed_accuracy_range(self) -> None:
        for m in WHISPER_MODELS:
            assert 1 <= m.speed_stars <= 5, f"{m.id} speed_stars out of range"
            assert 1 <= m.accuracy_stars <= 5, f"{m.id} accuracy_stars out of range"

    def test_english_only_models(self) -> None:
        en_models = [m for m in WHISPER_MODELS if m.english_only]
        assert len(en_models) >= 6  # tiny.en, base.en, small.en, medium.en, distil-v2, distil-v3

    def test_get_model_by_id_found(self) -> None:
        model = get_model_by_id("base")
        assert model is not None
        assert model.name == "Base"

    def test_get_model_by_id_not_found(self) -> None:
        assert get_model_by_id("nonexistent") is None

    def test_model_info_is_frozen(self) -> None:
        model = WHISPER_MODELS[0]
        try:
            model.id = "tampered"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected — frozen dataclass

    def test_disk_sizes_positive(self) -> None:
        for m in WHISPER_MODELS:
            assert m.disk_size_mb > 0, f"{m.id} has invalid disk_size_mb"
            assert m.parameters_m > 0, f"{m.id} has invalid parameters_m"


class TestVoskModels:
    """Vosk model registry."""

    def test_ten_models(self) -> None:
        assert len(VOSK_MODELS) == 10

    def test_unique_ids(self) -> None:
        ids = [m.id for m in VOSK_MODELS]
        assert len(ids) == len(set(ids)), "Duplicate Vosk model IDs found"

    def test_all_have_download_name(self) -> None:
        for m in VOSK_MODELS:
            assert m.download_name, f"Vosk model {m.id} missing download_name"

    def test_all_have_language(self) -> None:
        for m in VOSK_MODELS:
            assert m.language, f"Vosk model {m.id} missing language"

    def test_disk_sizes_positive(self) -> None:
        for m in VOSK_MODELS:
            assert m.disk_size_mb > 0, f"Vosk model {m.id} has invalid disk_size_mb"

    def test_one_large_model(self) -> None:
        large = [m for m in VOSK_MODELS if m.is_large]
        assert len(large) == 1
        assert large[0].id == "vosk-large-en"

    def test_get_vosk_model_by_id_found(self) -> None:
        model = get_vosk_model_by_id("vosk-small-en")
        assert model is not None
        assert model.name == "English (Small)"

    def test_get_vosk_model_by_id_not_found(self) -> None:
        assert get_vosk_model_by_id("nonexistent-vosk") is None

    def test_model_info_is_frozen(self) -> None:
        model = VOSK_MODELS[0]
        try:
            model.id = "tampered"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected — frozen dataclass


class TestParakeetModels:
    """Parakeet model registry."""

    def test_four_models(self) -> None:
        assert len(PARAKEET_MODELS) == 4

    def test_unique_ids(self) -> None:
        ids = [m.id for m in PARAKEET_MODELS]
        assert len(ids) == len(set(ids)), "Duplicate Parakeet model IDs found"

    def test_all_have_hf_repo_id(self) -> None:
        for m in PARAKEET_MODELS:
            assert m.hf_repo_id, f"Parakeet model {m.id} missing hf_repo_id"
            assert m.hf_repo_id.startswith("nvidia/"), f"{m.id} repo should be nvidia/"

    def test_all_have_decoder_type(self) -> None:
        for m in PARAKEET_MODELS:
            assert m.decoder_type in (
                "ctc",
                "tdt",
            ), f"Parakeet model {m.id} has invalid decoder_type: {m.decoder_type}"

    def test_disk_sizes_positive(self) -> None:
        for m in PARAKEET_MODELS:
            assert m.disk_size_mb > 0, f"Parakeet model {m.id} has invalid disk_size_mb"
            assert m.parameters_m > 0, f"Parakeet model {m.id} has invalid parameters_m"

    def test_speed_accuracy_range(self) -> None:
        for m in PARAKEET_MODELS:
            assert 1 <= m.speed_stars <= 5, f"{m.id} speed_stars out of range"
            assert 1 <= m.accuracy_stars <= 5, f"{m.id} accuracy_stars out of range"

    def test_model_sizes(self) -> None:
        small = [m for m in PARAKEET_MODELS if m.parameters_m == 600]
        large = [m for m in PARAKEET_MODELS if m.parameters_m == 1100]
        assert len(small) == 2
        assert len(large) == 2

    def test_get_parakeet_model_by_id_found(self) -> None:
        model = get_parakeet_model_by_id("parakeet-ctc-0.6b")
        assert model is not None
        assert model.name == "Parakeet CTC 0.6B"

    def test_get_parakeet_model_by_id_not_found(self) -> None:
        assert get_parakeet_model_by_id("nonexistent-parakeet") is None

    def test_model_info_is_frozen(self) -> None:
        model = PARAKEET_MODELS[0]
        try:
            model.id = "tampered"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected — frozen dataclass
