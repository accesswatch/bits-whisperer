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
APP_VERSION: Final[str] = "1.0.0"

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


# ---------------------------------------------------------------------------
# AI model catalog — pricing, subscription tiers, and capabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIModelInfo:
    """Metadata for an AI language model used for translation/summarization."""

    id: str
    name: str
    provider: str  # "openai", "anthropic", "gemini", "copilot"
    description: str
    input_price_per_1m: float  # USD per 1M input tokens (0 = free/included)
    output_price_per_1m: float  # USD per 1M output tokens (0 = free/included)
    context_window: int  # max tokens in context
    max_output_tokens: int
    copilot_tier: str = ""  # "free", "pro", "business", "enterprise", "" if not copilot
    is_premium: bool = False  # requires premium Copilot subscription
    supports_streaming: bool = True


# --- OpenAI models ---
OPENAI_AI_MODELS: Final[list[AIModelInfo]] = [
    AIModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        description="Fast and affordable. Best for routine translation and summarization tasks.",
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        context_window=128_000,
        max_output_tokens=16_384,
    ),
    AIModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        description="Best overall quality. Excellent for complex transcripts and nuanced analysis.",
        input_price_per_1m=2.50,
        output_price_per_1m=10.00,
        context_window=128_000,
        max_output_tokens=16_384,
    ),
    AIModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        description="Previous generation high-quality model. Strong reasoning capabilities.",
        input_price_per_1m=10.00,
        output_price_per_1m=30.00,
        context_window=128_000,
        max_output_tokens=4_096,
    ),
    AIModelInfo(
        id="gpt-3.5-turbo",
        name="GPT-3.5 Turbo",
        provider="openai",
        description="Legacy model. Very fast and cheap, but lower quality than GPT-4o.",
        input_price_per_1m=0.50,
        output_price_per_1m=1.50,
        context_window=16_385,
        max_output_tokens=4_096,
    ),
]

# --- Anthropic models ---
ANTHROPIC_AI_MODELS: Final[list[AIModelInfo]] = [
    AIModelInfo(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider="anthropic",
        description="Best balance of intelligence and speed. Excellent for detailed analysis.",
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        context_window=200_000,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="claude-haiku-4-20250414",
        name="Claude Haiku 4",
        provider="anthropic",
        description="Fastest Claude model. Great for quick summaries and translations.",
        input_price_per_1m=0.80,
        output_price_per_1m=4.00,
        context_window=200_000,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="claude-3-5-sonnet-20241022",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        description="Previous generation. Strong reasoning and analysis capabilities.",
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        context_window=200_000,
        max_output_tokens=8_192,
    ),
]

# --- Google Gemini models (including Gemma) ---
GEMINI_AI_MODELS: Final[list[AIModelInfo]] = [
    AIModelInfo(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="gemini",
        description="Fast and capable. Good for most translation and summarization tasks.",
        input_price_per_1m=0.10,
        output_price_per_1m=0.40,
        context_window=1_048_576,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="gemini",
        description="Most capable Gemini model. Best for complex analysis and long transcripts.",
        input_price_per_1m=1.25,
        output_price_per_1m=10.00,
        context_window=1_048_576,
        max_output_tokens=65_536,
    ),
    AIModelInfo(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider="gemini",
        description="Latest flash model. Great balance of speed and quality.",
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        context_window=1_048_576,
        max_output_tokens=65_536,
    ),
    # Gemma models (open-weight, run via Gemini API)
    AIModelInfo(
        id="gemma-3-27b-it",
        name="Gemma 3 27B",
        provider="gemini",
        description="Google's largest open-weight Gemma model. High quality, runs via Gemini API.",
        input_price_per_1m=0.10,
        output_price_per_1m=0.30,
        context_window=131_072,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="gemma-3-12b-it",
        name="Gemma 3 12B",
        provider="gemini",
        description="Mid-size Gemma model. Good balance of quality and speed.",
        input_price_per_1m=0.08,
        output_price_per_1m=0.20,
        context_window=131_072,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="gemma-3-4b-it",
        name="Gemma 3 4B",
        provider="gemini",
        description="Compact Gemma model. Fast and efficient for simple tasks.",
        input_price_per_1m=0.05,
        output_price_per_1m=0.10,
        context_window=131_072,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="gemma-3-1b-it",
        name="Gemma 3 1B",
        provider="gemini",
        description="Smallest Gemma model. Very fast, best for basic translation.",
        input_price_per_1m=0.02,
        output_price_per_1m=0.05,
        context_window=32_768,
        max_output_tokens=8_192,
    ),
    AIModelInfo(
        id="gemma-3n-e4b-it",
        name="Gemma 3n E4B",
        provider="gemini",
        description="Gemma Nano edge-optimized. Ultra-efficient for lightweight tasks.",
        input_price_per_1m=0.02,
        output_price_per_1m=0.05,
        context_window=32_768,
        max_output_tokens=8_192,
    ),
]

# --- GitHub Copilot models (subscription-based) ---
COPILOT_AI_MODELS: Final[list[AIModelInfo]] = [
    # Free tier models
    AIModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini (Copilot)",
        provider="copilot",
        description="Included with all Copilot plans. Fast, good for routine tasks.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=128_000,
        max_output_tokens=16_384,
        copilot_tier="free",
    ),
    AIModelInfo(
        id="gpt-4o",
        name="GPT-4o (Copilot)",
        provider="copilot",
        description="Included with Copilot Pro/Business. High-quality analysis.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=128_000,
        max_output_tokens=16_384,
        copilot_tier="pro",
    ),
    AIModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo (Copilot)",
        provider="copilot",
        description="Available with Copilot Pro/Business. Strong reasoning.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=128_000,
        max_output_tokens=4_096,
        copilot_tier="pro",
    ),
    AIModelInfo(
        id="claude-sonnet-4",
        name="Claude Sonnet 4 (Copilot)",
        provider="copilot",
        description="Anthropic model via Copilot Pro. Excellent for detailed analysis.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=200_000,
        max_output_tokens=8_192,
        copilot_tier="pro",
        is_premium=True,
    ),
    AIModelInfo(
        id="claude-haiku-4",
        name="Claude Haiku 4 (Copilot)",
        provider="copilot",
        description="Fast Anthropic model via Copilot. Quick summaries and translations.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=200_000,
        max_output_tokens=8_192,
        copilot_tier="pro",
        is_premium=True,
    ),
    AIModelInfo(
        id="o3-mini",
        name="o3-mini (Copilot)",
        provider="copilot",
        description="OpenAI reasoning model via Copilot Pro. Advanced analytical tasks.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=128_000,
        max_output_tokens=16_384,
        copilot_tier="pro",
        is_premium=True,
    ),
    AIModelInfo(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash (Copilot)",
        provider="copilot",
        description="Google model via Copilot Pro. Fast and efficient.",
        input_price_per_1m=0.0,
        output_price_per_1m=0.0,
        context_window=1_048_576,
        max_output_tokens=8_192,
        copilot_tier="pro",
        is_premium=True,
    ),
]

# Copilot subscription tiers
COPILOT_TIERS: Final[dict[str, dict[str, str]]] = {
    "free": {
        "name": "Copilot Free",
        "price": "Free",
        "description": "Limited monthly completions. GPT-4o Mini included.",
    },
    "pro": {
        "name": "Copilot Pro",
        "price": "$10/month",
        "description": "Unlimited completions. All models including premium.",
    },
    "business": {
        "name": "Copilot Business",
        "price": "$19/user/month",
        "description": "Organization management. All Pro features plus admin controls.",
    },
    "enterprise": {
        "name": "Copilot Enterprise",
        "price": "$39/user/month",
        "description": "Enterprise features. Knowledge bases, fine-tuning, compliance.",
    },
}

# All AI models combined for lookups
ALL_AI_MODELS: Final[list[AIModelInfo]] = (
    OPENAI_AI_MODELS + ANTHROPIC_AI_MODELS + GEMINI_AI_MODELS + COPILOT_AI_MODELS
)


def get_ai_model_by_id(model_id: str, provider: str = "") -> AIModelInfo | None:
    """Look up an AI model by its ID and optional provider.

    Args:
        model_id: Model identifier string.
        provider: Optional provider filter.

    Returns:
        AIModelInfo, or None if not found.
    """
    for m in ALL_AI_MODELS:
        if m.id == model_id and (not provider or m.provider == provider):
            return m
    return None


def get_models_for_provider(provider: str) -> list[AIModelInfo]:
    """Get all models available for a given provider.

    Args:
        provider: Provider identifier (openai, anthropic, gemini, copilot).

    Returns:
        List of AIModelInfo for that provider.
    """
    if provider == "openai":
        return list(OPENAI_AI_MODELS)
    elif provider == "anthropic":
        return list(ANTHROPIC_AI_MODELS)
    elif provider == "gemini":
        return list(GEMINI_AI_MODELS)
    elif provider == "copilot":
        return list(COPILOT_AI_MODELS)
    return []


def get_copilot_models_for_tier(tier: str) -> list[AIModelInfo]:
    """Get Copilot models available at or below a given subscription tier.

    Args:
        tier: Subscription tier (free, pro, business, enterprise).

    Returns:
        List of AIModelInfo available for that tier.
    """
    tier_order = {"free": 0, "pro": 1, "business": 2, "enterprise": 3}
    tier_level = tier_order.get(tier, 0)
    return [m for m in COPILOT_AI_MODELS if tier_order.get(m.copilot_tier, 0) <= tier_level]


def format_price_per_1k(price_per_1m: float) -> str:
    """Format a price-per-1M-tokens value as a human-friendly per-1K string.

    Args:
        price_per_1m: Price in USD per 1 million tokens.

    Returns:
        Formatted price string (e.g. '$0.0025/1K tokens' or 'Free').
    """
    if price_per_1m == 0.0:
        return "Free (included)"
    price_per_1k = price_per_1m / 1000.0
    if price_per_1k < 0.01:
        return f"${price_per_1k:.4f}/1K tokens"
    return f"${price_per_1k:.3f}/1K tokens"


# ---------------------------------------------------------------------------
# Prompt templates for AI operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptTemplate:
    """A reusable prompt template for AI operations."""

    id: str
    name: str
    category: str  # "translation", "summarization", "analysis", "custom"
    description: str
    template: str  # Use {text} for transcript, {language} for target language
    is_builtin: bool = True


BUILTIN_PROMPT_TEMPLATES: Final[list[PromptTemplate]] = [
    # Translation templates
    PromptTemplate(
        id="translate_standard",
        name="Standard Translation",
        category="translation",
        description="Translate with speaker labels and timestamps preserved.",
        template=(
            "Translate the following transcript to {language}. "
            "Preserve speaker labels, timestamps, and formatting exactly as they appear. "
            "Only translate the spoken content.\n\nTranscript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="translate_informal",
        name="Informal Translation",
        category="translation",
        description="Natural, conversational translation style.",
        template=(
            "Translate the following transcript to {language} using a natural, "
            "conversational tone. Preserve speaker labels but adapt idioms and "
            "expressions to sound natural in the target language.\n\nTranscript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="translate_technical",
        name="Technical Translation",
        category="translation",
        description="Precise translation for technical or medical content.",
        template=(
            "Translate the following transcript to {language}. This is technical content, "
            "so use precise terminology. Preserve speaker labels and timestamps. "
            "When domain-specific terms have standard translations, use them; "
            "otherwise keep the original term in parentheses.\n\nTranscript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="translate_legal",
        name="Legal Translation",
        category="translation",
        description="Formal translation for legal proceedings or depositions.",
        template=(
            "Translate the following transcript to {language} for legal purposes. "
            "Use formal, precise language. Preserve all speaker labels and timestamps "
            "exactly. Do not paraphrase or summarize — translate verbatim.\n\n"
            "Transcript:\n{text}"
        ),
    ),
    # Summarization templates
    PromptTemplate(
        id="summary_concise",
        name="Concise Summary",
        category="summarization",
        description="Brief 3-5 sentence summary with key takeaways.",
        template=(
            "Summarize the following transcript in a concise paragraph (3-5 sentences). "
            "Capture the main topics, key decisions, and action items.\n\n"
            "Transcript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="summary_detailed",
        name="Detailed Summary",
        category="summarization",
        description="Comprehensive summary with topics and speaker contributions.",
        template=(
            "Provide a detailed summary of the following transcript. "
            "Include main topics discussed, key points from each speaker, "
            "decisions made, and any action items or follow-ups mentioned.\n\n"
            "Transcript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="summary_bullets",
        name="Bullet Points",
        category="summarization",
        description="Organized bullet list of key points and decisions.",
        template=(
            "Summarize the following transcript as a bulleted list. "
            "Each bullet should capture one key point, decision, or action item. "
            "Group related points together with sub-bullets if appropriate.\n\n"
            "Transcript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="summary_meeting",
        name="Meeting Minutes",
        category="summarization",
        description="Formal meeting minutes with attendees, agenda, and actions.",
        template=(
            "Generate formal meeting minutes from this transcript. Include:\n"
            "- Attendees (from speaker labels)\n"
            "- Agenda topics discussed\n"
            "- Key decisions made\n"
            "- Action items with assigned owners (if mentioned)\n"
            "- Follow-up dates (if mentioned)\n\n"
            "Transcript:\n{text}"
        ),
    ),
    # Analysis templates
    PromptTemplate(
        id="analysis_sentiment",
        name="Sentiment Analysis",
        category="analysis",
        description="Analyze the emotional tone and sentiment of the conversation.",
        template=(
            "Analyze the sentiment and emotional tone of this transcript. "
            "For each speaker, describe their overall tone (positive, negative, "
            "neutral, frustrated, enthusiastic, etc.) and identify any shifts "
            "in sentiment during the conversation.\n\nTranscript:\n{text}"
        ),
    ),
    PromptTemplate(
        id="analysis_questions",
        name="Extract Questions",
        category="analysis",
        description="Extract all questions asked during the conversation.",
        template=(
            "Extract all questions asked in this transcript. For each question, "
            "include:\n- Who asked it (speaker label)\n- The question text\n"
            "- Whether it was answered (yes/no/partially)\n"
            "- Brief answer if provided\n\nTranscript:\n{text}"
        ),
    ),
]


def get_prompt_template_by_id(template_id: str) -> PromptTemplate | None:
    """Look up a prompt template by ID.

    Args:
        template_id: Template identifier.

    Returns:
        PromptTemplate, or None if not found.
    """
    for t in BUILTIN_PROMPT_TEMPLATES:
        if t.id == template_id:
            return t
    return None


def get_templates_by_category(category: str) -> list[PromptTemplate]:
    """Get all prompt templates in a given category.

    Args:
        category: Category name (translation, summarization, analysis).

    Returns:
        List of matching PromptTemplate instances.
    """
    return [t for t in BUILTIN_PROMPT_TEMPLATES if t.category == category]
