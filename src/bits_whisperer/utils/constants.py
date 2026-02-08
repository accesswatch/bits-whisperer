"""App-wide constants and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from platformdirs import user_data_dir

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_NAME: Final[str] = "BITS Whisperer"
APP_AUTHOR: Final[str] = "BITSWhisperer"
APP_VERSION: Final[str] = "1.1.0"

# ---------------------------------------------------------------------------
# GitHub updater
# ---------------------------------------------------------------------------
GITHUB_REPO_OWNER: Final[str] = "BITSWhisperer"
GITHUB_REPO_NAME: Final[str] = "bits-whisperer"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR: Final[Path] = Path(user_data_dir(APP_NAME, APP_AUTHOR))
TRANSCRIPTS_DIR: Final[Path] = DATA_DIR / "transcripts"
MODELS_DIR: Final[Path] = DATA_DIR / "models"
SITE_PACKAGES_DIR: Final[Path] = DATA_DIR / "site-packages"
DB_PATH: Final[Path] = DATA_DIR / "bits_whisperer.db"
LOG_PATH: Final[Path] = DATA_DIR / "app.log"

# Ensure directories exist
for _d in (DATA_DIR, TRANSCRIPTS_DIR, MODELS_DIR, SITE_PACKAGES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Audio formats
# ---------------------------------------------------------------------------
SUPPORTED_AUDIO_EXTENSIONS: Final[tuple[str, ...]] = (
    ".mp3",
    ".wav",
    ".ogg",
    ".opus",
    ".flac",
    ".m4a",
    ".aac",
    ".webm",
    ".wma",
    ".aiff",
    ".aif",
    ".amr",
    ".mp4",
)

AUDIO_WILDCARD: Final[str] = (
    "Audio files|" + ";".join(f"*{ext}" for ext in SUPPORTED_AUDIO_EXTENSIONS) + "|All files|*.*"
)

# ---------------------------------------------------------------------------
# Export formats
# ---------------------------------------------------------------------------
EXPORT_FORMATS: Final[dict[str, str]] = {
    "txt": "Plain Text (.txt)",
    "md": "Markdown (.md)",
    "html": "HTML Document (.html)",
    "docx": "Microsoft Word (.docx)",
    "srt": "SubRip Subtitles (.srt)",
    "vtt": "WebVTT Subtitles (.vtt)",
    "json": "JSON Data (.json)",
}

# ---------------------------------------------------------------------------
# Limits (defaults — user-configurable in Advanced settings)
# ---------------------------------------------------------------------------
DEFAULT_MAX_FILE_SIZE_MB: Final[int] = 500
DEFAULT_MAX_DURATION_HOURS: Final[float] = 4.0
DEFAULT_MAX_BATCH_FILES: Final[int] = 100
DEFAULT_MAX_BATCH_SIZE_GB: Final[float] = 10.0
DEFAULT_MAX_CONCURRENT_JOBS: Final[int] = 2
DEFAULT_CHUNK_MINUTES: Final[int] = 30
DEFAULT_CHUNK_OVERLAP_SECONDS: Final[int] = 2

# ---------------------------------------------------------------------------
# Transcoding
# ---------------------------------------------------------------------------
TRANSCODE_SAMPLE_RATE: Final[int] = 16_000
TRANSCODE_CHANNELS: Final[int] = 1  # mono
TRANSCODE_FORMAT: Final[str] = "wav"

# ---------------------------------------------------------------------------
# Whisper models — registry with hardware requirements & user descriptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WhisperModelInfo:
    """Metadata for a Whisper model variant."""

    id: str
    name: str
    description: str  # Plain-English for consumers
    parameters_m: int  # millions of parameters
    disk_size_mb: int
    min_ram_gb: int
    min_vram_gb: int  # 0 = can run on CPU
    min_cpu_cores: int
    speed_stars: int  # 1–5, higher = faster
    accuracy_stars: int  # 1–5, higher = better
    languages: int | str  # 99 or "English"
    english_only: bool = False
    is_distil: bool = False
    repo_id: str = ""  # HuggingFace repo for faster-whisper


WHISPER_MODELS: Final[list[WhisperModelInfo]] = [
    WhisperModelInfo(
        id="tiny",
        name="Tiny",
        description=(
            "Lightning fast, basic accuracy. Great for quick drafts and "
            "getting the gist. Works on any computer."
        ),
        parameters_m=39,
        disk_size_mb=75,
        min_ram_gb=2,
        min_vram_gb=0,
        min_cpu_cores=2,
        speed_stars=5,
        accuracy_stars=2,
        languages=99,
        repo_id="Systran/faster-whisper-tiny",
    ),
    WhisperModelInfo(
        id="tiny.en",
        name="Tiny (English)",
        description=(
            "Lightning fast, slightly better for English-only recordings. " "Works on any computer."
        ),
        parameters_m=39,
        disk_size_mb=75,
        min_ram_gb=2,
        min_vram_gb=0,
        min_cpu_cores=2,
        speed_stars=5,
        accuracy_stars=2,
        languages="English",
        english_only=True,
        repo_id="Systran/faster-whisper-tiny.en",
    ),
    WhisperModelInfo(
        id="base",
        name="Base",
        description=(
            "Fast and decent accuracy. Good for clear recordings with one "
            "speaker. Works on any computer."
        ),
        parameters_m=74,
        disk_size_mb=142,
        min_ram_gb=2,
        min_vram_gb=0,
        min_cpu_cores=2,
        speed_stars=4,
        accuracy_stars=3,
        languages=99,
        repo_id="Systran/faster-whisper-base",
    ),
    WhisperModelInfo(
        id="base.en",
        name="Base (English)",
        description=(
            "Fast with improved English accuracy. Perfect for interviews "
            "and podcasts. Works on any computer."
        ),
        parameters_m=74,
        disk_size_mb=142,
        min_ram_gb=2,
        min_vram_gb=0,
        min_cpu_cores=2,
        speed_stars=4,
        accuracy_stars=3,
        languages="English",
        english_only=True,
        repo_id="Systran/faster-whisper-base.en",
    ),
    WhisperModelInfo(
        id="small",
        name="Small",
        description=(
            "Balanced speed and accuracy. Solid choice for most recordings. "
            "Needs a decent computer (4+ GB RAM)."
        ),
        parameters_m=244,
        disk_size_mb=466,
        min_ram_gb=4,
        min_vram_gb=2,
        min_cpu_cores=4,
        speed_stars=3,
        accuracy_stars=4,
        languages=99,
        repo_id="Systran/faster-whisper-small",
    ),
    WhisperModelInfo(
        id="small.en",
        name="Small (English)",
        description=(
            "Balanced speed with strong English accuracy. Great for clear "
            "English recordings. Needs a decent computer."
        ),
        parameters_m=244,
        disk_size_mb=466,
        min_ram_gb=4,
        min_vram_gb=2,
        min_cpu_cores=4,
        speed_stars=3,
        accuracy_stars=4,
        languages="English",
        english_only=True,
        repo_id="Systran/faster-whisper-small.en",
    ),
    WhisperModelInfo(
        id="medium",
        name="Medium",
        description=(
            "High accuracy, takes longer. Great for important recordings. "
            "Needs a powerful computer or a GPU."
        ),
        parameters_m=769,
        disk_size_mb=1500,
        min_ram_gb=8,
        min_vram_gb=4,
        min_cpu_cores=4,
        speed_stars=2,
        accuracy_stars=4,
        languages=99,
        repo_id="Systran/faster-whisper-medium",
    ),
    WhisperModelInfo(
        id="medium.en",
        name="Medium (English)",
        description=(
            "High accuracy for English. Great for professional English "
            "transcripts. Needs a powerful computer or a GPU."
        ),
        parameters_m=769,
        disk_size_mb=1500,
        min_ram_gb=8,
        min_vram_gb=4,
        min_cpu_cores=4,
        speed_stars=2,
        accuracy_stars=5,
        languages="English",
        english_only=True,
        repo_id="Systran/faster-whisper-medium.en",
    ),
    WhisperModelInfo(
        id="large-v1",
        name="Large v1",
        description=(
            "Very high accuracy. For professional-quality transcripts. "
            "Requires a powerful GPU with 6+ GB video memory."
        ),
        parameters_m=1550,
        disk_size_mb=3000,
        min_ram_gb=12,
        min_vram_gb=6,
        min_cpu_cores=8,
        speed_stars=1,
        accuracy_stars=5,
        languages=99,
        repo_id="Systran/faster-whisper-large-v1",
    ),
    WhisperModelInfo(
        id="large-v2",
        name="Large v2",
        description=(
            "Excellent accuracy — improved over v1. For professional work. "
            "Requires a powerful GPU with 6+ GB video memory."
        ),
        parameters_m=1550,
        disk_size_mb=3000,
        min_ram_gb=12,
        min_vram_gb=6,
        min_cpu_cores=8,
        speed_stars=1,
        accuracy_stars=5,
        languages=99,
        repo_id="Systran/faster-whisper-large-v2",
    ),
    WhisperModelInfo(
        id="large-v3",
        name="Large v3",
        description=(
            "Best accuracy available. Perfect for critical or professional "
            "work. Requires a powerful GPU with 6+ GB video memory."
        ),
        parameters_m=1550,
        disk_size_mb=3000,
        min_ram_gb=12,
        min_vram_gb=6,
        min_cpu_cores=8,
        speed_stars=1,
        accuracy_stars=5,
        languages=99,
        repo_id="Systran/faster-whisper-large-v3",
    ),
    WhisperModelInfo(
        id="large-v3-turbo",
        name="Large v3 Turbo",
        description=(
            "Near-best accuracy at much faster speed. Best value if you "
            "have a GPU. Great balance of speed and quality."
        ),
        parameters_m=809,
        disk_size_mb=1600,
        min_ram_gb=8,
        min_vram_gb=4,
        min_cpu_cores=4,
        speed_stars=3,
        accuracy_stars=5,
        languages=99,
        repo_id="Systran/faster-whisper-large-v3-turbo",
    ),
    WhisperModelInfo(
        id="distil-large-v2",
        name="Distil Large v2 (English)",
        description=(
            "Fast and accurate for English. Distilled version — great speed "
            "with minimal quality loss. Needs a GPU."
        ),
        parameters_m=756,
        disk_size_mb=1500,
        min_ram_gb=8,
        min_vram_gb=4,
        min_cpu_cores=4,
        speed_stars=4,
        accuracy_stars=4,
        languages="English",
        english_only=True,
        is_distil=True,
        repo_id="Systran/faster-distil-whisper-large-v2",
    ),
    WhisperModelInfo(
        id="distil-large-v3",
        name="Distil Large v3 (English)",
        description=(
            "Fast and accurate for English. Latest distilled version — "
            "excellent speed with near-best quality. Needs a GPU."
        ),
        parameters_m=756,
        disk_size_mb=1500,
        min_ram_gb=8,
        min_vram_gb=4,
        min_cpu_cores=4,
        speed_stars=4,
        accuracy_stars=4,
        languages="English",
        english_only=True,
        is_distil=True,
        repo_id="Systran/faster-distil-whisper-large-v3",
    ),
]


def get_model_by_id(model_id: str) -> WhisperModelInfo | None:
    """Look up a Whisper model by its ID string."""
    for m in WHISPER_MODELS:
        if m.id == model_id:
            return m
    return None


# ---------------------------------------------------------------------------
# Vosk models — lightweight offline ASR (Kaldi-based)
# ---------------------------------------------------------------------------

VOSK_MODELS_DIR: Final[Path] = MODELS_DIR / "vosk"
VOSK_MODELS_DIR.mkdir(parents=True, exist_ok=True)

VOSK_MODEL_URL_BASE: Final[str] = "https://alphacephei.com/vosk/models"


@dataclass(frozen=True)
class VoskModelInfo:
    """Metadata for a Vosk model variant."""

    id: str
    name: str
    description: str
    language: str  # ISO language code or "en-us"
    disk_size_mb: int
    download_name: str  # Name used for download URL and directory
    is_large: bool = False  # Large models need more RAM


VOSK_MODELS: Final[list[VoskModelInfo]] = [
    VoskModelInfo(
        id="vosk-small-en",
        name="English (Small)",
        description=(
            "Lightweight English model. Fast and low memory. "
            "Good for clear recordings on low-end hardware."
        ),
        language="en-us",
        disk_size_mb=40,
        download_name="vosk-model-small-en-us-0.15",
    ),
    VoskModelInfo(
        id="vosk-large-en",
        name="English (Large)",
        description=(
            "High-accuracy English model. Slower but significantly more "
            "accurate than the small model."
        ),
        language="en-us",
        disk_size_mb=1800,
        download_name="vosk-model-en-us-0.22",
        is_large=True,
    ),
    VoskModelInfo(
        id="vosk-small-cn",
        name="Chinese (Small)",
        description="Lightweight Mandarin Chinese model for quick transcription.",
        language="zh",
        disk_size_mb=42,
        download_name="vosk-model-small-cn-0.22",
    ),
    VoskModelInfo(
        id="vosk-small-de",
        name="German (Small)",
        description="Lightweight German model for quick transcription.",
        language="de",
        disk_size_mb=45,
        download_name="vosk-model-small-de-0.15",
    ),
    VoskModelInfo(
        id="vosk-small-fr",
        name="French (Small)",
        description="Lightweight French model for quick transcription.",
        language="fr",
        disk_size_mb=41,
        download_name="vosk-model-small-fr-0.22",
    ),
    VoskModelInfo(
        id="vosk-small-es",
        name="Spanish (Small)",
        description="Lightweight Spanish model for quick transcription.",
        language="es",
        disk_size_mb=39,
        download_name="vosk-model-small-es-0.42",
    ),
    VoskModelInfo(
        id="vosk-small-ru",
        name="Russian (Small)",
        description="Lightweight Russian model for quick transcription.",
        language="ru",
        disk_size_mb=45,
        download_name="vosk-model-small-ru-0.22",
    ),
    VoskModelInfo(
        id="vosk-small-ja",
        name="Japanese (Small)",
        description="Lightweight Japanese model for quick transcription.",
        language="ja",
        disk_size_mb=48,
        download_name="vosk-model-small-ja-0.22",
    ),
    VoskModelInfo(
        id="vosk-small-it",
        name="Italian (Small)",
        description="Lightweight Italian model for quick transcription.",
        language="it",
        disk_size_mb=48,
        download_name="vosk-model-small-it-0.22",
    ),
    VoskModelInfo(
        id="vosk-small-pt",
        name="Portuguese (Small)",
        description="Lightweight Portuguese model for quick transcription.",
        language="pt",
        disk_size_mb=31,
        download_name="vosk-model-small-pt-0.3",
    ),
]


def get_vosk_model_by_id(model_id: str) -> VoskModelInfo | None:
    """Look up a Vosk model by its ID string."""
    for m in VOSK_MODELS:
        if m.id == model_id:
            return m
    return None


# ---------------------------------------------------------------------------
# Parakeet models — NVIDIA NeMo on-device ASR
# ---------------------------------------------------------------------------

PARAKEET_MODELS_DIR: Final[Path] = MODELS_DIR / "parakeet"
PARAKEET_MODELS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ParakeetModelInfo:
    """Metadata for an NVIDIA Parakeet model variant."""

    id: str
    name: str
    description: str
    parameters_m: int  # millions of parameters
    disk_size_mb: int
    min_ram_gb: int
    min_vram_gb: int  # 0 = can run on CPU
    speed_stars: int  # 1–5, higher = faster
    accuracy_stars: int  # 1–5, higher = better
    hf_repo_id: str  # HuggingFace repo (e.g. 'nvidia/parakeet-tdt-0.6b')
    decoder_type: str  # 'tdt' or 'ctc'


PARAKEET_MODELS: Final[list[ParakeetModelInfo]] = [
    ParakeetModelInfo(
        id="parakeet-ctc-0.6b",
        name="Parakeet CTC 0.6B",
        description=(
            "Fast and accurate English model (600M params). CTC decoder — "
            "simple and fast. Great for clear recordings on modern hardware."
        ),
        parameters_m=600,
        disk_size_mb=1200,
        min_ram_gb=4,
        min_vram_gb=0,
        speed_stars=4,
        accuracy_stars=4,
        hf_repo_id="nvidia/parakeet-ctc-0.6b",
        decoder_type="ctc",
    ),
    ParakeetModelInfo(
        id="parakeet-tdt-0.6b",
        name="Parakeet TDT 0.6B",
        description=(
            "Fast and accurate English model (600M params). TDT decoder — "
            "better timestamp accuracy. Great for clear recordings."
        ),
        parameters_m=600,
        disk_size_mb=1200,
        min_ram_gb=4,
        min_vram_gb=0,
        speed_stars=4,
        accuracy_stars=4,
        hf_repo_id="nvidia/parakeet-tdt-0.6b",
        decoder_type="tdt",
    ),
    ParakeetModelInfo(
        id="parakeet-ctc-1.1b",
        name="Parakeet CTC 1.1B",
        description=(
            "High-accuracy English model (1.1B params). CTC decoder. "
            "Needs a powerful computer or GPU for best speed."
        ),
        parameters_m=1100,
        disk_size_mb=2200,
        min_ram_gb=8,
        min_vram_gb=4,
        speed_stars=2,
        accuracy_stars=5,
        hf_repo_id="nvidia/parakeet-ctc-1.1b",
        decoder_type="ctc",
    ),
    ParakeetModelInfo(
        id="parakeet-tdt-1.1b",
        name="Parakeet TDT 1.1B",
        description=(
            "Highest-accuracy English model (1.1B params). TDT decoder "
            "with excellent timestamp precision. Needs a GPU."
        ),
        parameters_m=1100,
        disk_size_mb=2200,
        min_ram_gb=8,
        min_vram_gb=4,
        speed_stars=2,
        accuracy_stars=5,
        hf_repo_id="nvidia/parakeet-tdt-1.1b",
        decoder_type="tdt",
    ),
]


def get_parakeet_model_by_id(model_id: str) -> ParakeetModelInfo | None:
    """Look up a Parakeet model by its ID string."""
    for m in PARAKEET_MODELS:
        if m.id == model_id:
            return m
    return None
