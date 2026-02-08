"""Persistent application settings backed by a JSON file.

All user-configurable options are stored and retrieved through
:class:`AppSettings`. Values are saved to ``DATA_DIR/settings.json``
whenever :meth:`save` is called (i.e. on OK / Apply in the settings
dialog).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from bits_whisperer.utils.constants import (
    DATA_DIR,
    DEFAULT_CHUNK_MINUTES,
    DEFAULT_CHUNK_OVERLAP_SECONDS,
    DEFAULT_MAX_BATCH_FILES,
    DEFAULT_MAX_BATCH_SIZE_GB,
    DEFAULT_MAX_CONCURRENT_JOBS,
    DEFAULT_MAX_DURATION_HOURS,
    DEFAULT_MAX_FILE_SIZE_MB,
    MODELS_DIR,
    TRANSCRIPTS_DIR,
)

logger = logging.getLogger(__name__)

_SETTINGS_PATH = DATA_DIR / "settings.json"


# -----------------------------------------------------------------------
# Nested option groups
# -----------------------------------------------------------------------


@dataclass
class GeneralSettings:
    """General / behaviour preferences."""

    language: str = "auto"
    prefer_local: bool = True
    default_provider: str = "local_whisper"
    default_model: str = "base"
    minimize_to_tray: bool = True
    auto_export: bool = False
    show_notifications: bool = True
    play_sound: bool = True
    start_minimized: bool = False
    check_updates_on_start: bool = True
    confirm_before_quit: bool = True
    restore_queue_on_start: bool = False
    experience_mode: str = "basic"  # "basic" or "advanced"
    activated_providers: list[str] = field(default_factory=list)


@dataclass
class TranscriptionSettings:
    """Transcription output control."""

    include_timestamps: bool = True
    timestamp_format: str = "hh:mm:ss"  # hh:mm:ss | mm:ss | seconds
    include_speakers: bool = True
    include_confidence: bool = False
    include_language_tag: bool = False
    include_word_level: bool = False
    paragraph_segmentation: bool = True
    max_segment_length: int = 0  # 0 = no limit
    merge_short_segments: bool = False
    merge_threshold_seconds: float = 1.0
    prompt: str = ""  # initial prompt / vocabulary hint
    temperature: float = 0.0
    beam_size: int = 5
    vad_filter: bool = True
    vad_threshold: float = 0.5
    compute_type: str = "auto"  # auto | float16 | int8 | float32


@dataclass
class OutputSettings:
    """Export & output configuration."""

    default_format: str = "txt"
    output_directory: str = str(TRANSCRIPTS_DIR)
    auto_export_format: str = "txt"
    auto_export_location: str = "alongside"  # alongside | output_dir | custom
    custom_export_dir: str = ""
    filename_template: str = "{stem}"
    overwrite_existing: bool = False
    append_counter: bool = True
    include_header: bool = True
    include_metadata: bool = True
    encoding: str = "utf-8"
    line_ending: str = "auto"  # auto | lf | crlf


@dataclass
class AudioProcessingSettings:
    """Audio preprocessing filter chain."""

    enabled: bool = True
    highpass_enabled: bool = True
    highpass_freq: int = 80
    lowpass_enabled: bool = True
    lowpass_freq: int = 8000
    noise_gate_enabled: bool = True
    noise_gate_threshold_db: float = -40.0
    deesser_enabled: bool = False
    deesser_freq: int = 5000
    compressor_enabled: bool = True
    compressor_threshold_db: float = -20.0
    compressor_ratio: float = 4.0
    compressor_attack_ms: float = 5.0
    compressor_release_ms: float = 50.0
    loudnorm_enabled: bool = True
    loudnorm_target_i: float = -16.0
    loudnorm_target_tp: float = -3.0
    loudnorm_target_lra: float = 11.0
    trim_silence_enabled: bool = True
    silence_threshold_db: float = -40.0
    silence_duration_s: float = 1.0


@dataclass
class PathSettings:
    """File / directory locations."""

    output_directory: str = str(TRANSCRIPTS_DIR)
    models_directory: str = str(MODELS_DIR)
    temp_directory: str = ""  # empty = system temp
    log_file: str = str(DATA_DIR / "app.log")


@dataclass
class DiarizationSettings:
    """Speaker diarization configuration."""

    enabled: bool = True
    max_speakers: int = 10
    min_speakers: int = 2
    use_local_diarization: bool = False
    local_engine: str = "pyannote"  # pyannote | none
    pyannote_model: str = "pyannote/speaker-diarization-3.1"
    speaker_map: dict[str, str] = field(default_factory=dict)


@dataclass
class ProviderDefaultSettings:
    """Per-provider default settings stored as a flexible dict.

    Each key is a provider ID (e.g. 'auphonic', 'deepgram'), and the
    value is a dict of provider-specific configuration.
    """

    defaults: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, provider_id: str) -> dict[str, Any]:
        """Get settings for a provider.

        Args:
            provider_id: Provider identifier.

        Returns:
            Dict of settings, or empty dict.
        """
        return self.defaults.get(provider_id, {})

    def set(self, provider_id: str, settings: dict[str, Any]) -> None:
        """Set settings for a provider.

        Args:
            provider_id: Provider identifier.
            settings: Dict of settings to store.
        """
        self.defaults[provider_id] = settings


@dataclass
class AISettings:
    """AI service configuration for translation and summarization."""

    selected_provider: str = "openai"  # openai, anthropic, azure_openai, gemini, copilot
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-sonnet-4-20250514"
    azure_openai_deployment: str = ""
    azure_openai_endpoint: str = ""
    gemini_model: str = "gemini-2.0-flash"
    copilot_model: str = "gpt-4o"
    translation_target_language: str = "en"
    summarization_style: str = "concise"  # "concise", "detailed", "bullet_points"
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class LiveTranscriptionSettings:
    """Live microphone transcription configuration."""

    enabled: bool = False
    model: str = "base"
    language: str = "auto"
    silence_threshold_seconds: float = 0.8
    sample_rate: int = 16000
    chunk_duration_seconds: float = 3.0
    vad_filter: bool = True
    input_device: str = ""  # empty = system default


@dataclass
class PluginSettings:
    """Plugin system configuration."""

    enabled: bool = True
    plugin_directory: str = ""  # empty = DATA_DIR / "plugins"
    disabled_plugins: list[str] = field(default_factory=list)
    auto_update: bool = False


@dataclass
class CopilotSettings:
    """GitHub Copilot SDK integration configuration."""

    enabled: bool = False
    cli_path: str = ""  # empty = auto-detect from PATH
    use_logged_in_user: bool = True
    default_model: str = "gpt-4o"
    streaming: bool = True
    system_message: str = (
        "You are a helpful transcript assistant for BITS Whisperer. "
        "You help users understand, analyze, and work with audio transcripts. "
        "Be concise, clear, and helpful."
    )
    agent_name: str = "BITS Transcript Assistant"
    agent_instructions: str = ""
    auto_start_cli: bool = True
    allow_transcript_tools: bool = True
    chat_panel_visible: bool = False


@dataclass
class AdvancedSettings:
    """Limits, concurrency, chunking."""

    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB
    max_duration_hours: float = DEFAULT_MAX_DURATION_HOURS
    max_batch_files: int = DEFAULT_MAX_BATCH_FILES
    max_batch_size_gb: float = DEFAULT_MAX_BATCH_SIZE_GB
    max_concurrent_jobs: int = DEFAULT_MAX_CONCURRENT_JOBS
    chunk_minutes: int = DEFAULT_CHUNK_MINUTES
    chunk_overlap_seconds: int = DEFAULT_CHUNK_OVERLAP_SECONDS
    background_processing: bool = True
    gpu_device_index: int = 0
    cpu_threads: int = 0  # 0 = auto-detect
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR


@dataclass
class AppSettings:
    """Root container for all application settings."""

    general: GeneralSettings = field(default_factory=GeneralSettings)
    transcription: TranscriptionSettings = field(
        default_factory=TranscriptionSettings,
    )
    output: OutputSettings = field(default_factory=OutputSettings)
    audio_processing: AudioProcessingSettings = field(
        default_factory=AudioProcessingSettings,
    )
    paths: PathSettings = field(default_factory=PathSettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    diarization: DiarizationSettings = field(default_factory=DiarizationSettings)
    provider_settings: ProviderDefaultSettings = field(
        default_factory=ProviderDefaultSettings,
    )
    ai: AISettings = field(default_factory=AISettings)
    live_transcription: LiveTranscriptionSettings = field(
        default_factory=LiveTranscriptionSettings,
    )
    plugins: PluginSettings = field(default_factory=PluginSettings)
    copilot: CopilotSettings = field(default_factory=CopilotSettings)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def save(self) -> None:
        """Persist settings to disk as JSON."""
        try:
            data = asdict(self)
            _SETTINGS_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Settings saved to %s", _SETTINGS_PATH)
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)

    @classmethod
    def load(cls) -> AppSettings:
        """Load settings from disk, falling back to defaults.

        Returns:
            Populated AppSettings instance.
        """
        if not _SETTINGS_PATH.exists():
            return cls()
        try:
            raw = json.loads(_SETTINGS_PATH.read_text("utf-8"))
            return cls._from_dict(raw)
        except Exception as exc:
            logger.warning("Failed to load settings, using defaults: %s", exc)
            return cls()

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> AppSettings:
        """Reconstruct from a JSON-compatible dict.

        Unknown keys are silently ignored so that upgrading from an
        older settings file always works.
        """

        def _safe(dc_cls, section: dict | None):
            if not section:
                return dc_cls()
            valid = {f.name for f in dc_cls.__dataclass_fields__.values()}
            return dc_cls(**{k: v for k, v in section.items() if k in valid})

        # DiarizationSettings has a dict field; handle specially
        diar_data = data.get("diarization", {})
        diar = _safe(DiarizationSettings, diar_data)

        # ProviderDefaultSettings wraps a nested dict
        ps_data = data.get("provider_settings", {})
        ps_defaults = ps_data.get("defaults", {}) if isinstance(ps_data, dict) else {}
        provider_settings = ProviderDefaultSettings(defaults=ps_defaults)

        return cls(
            general=_safe(GeneralSettings, data.get("general")),
            transcription=_safe(
                TranscriptionSettings,
                data.get("transcription"),
            ),
            output=_safe(OutputSettings, data.get("output")),
            audio_processing=_safe(
                AudioProcessingSettings,
                data.get("audio_processing"),
            ),
            paths=_safe(PathSettings, data.get("paths")),
            advanced=_safe(AdvancedSettings, data.get("advanced")),
            diarization=diar,
            provider_settings=provider_settings,
            ai=_safe(AISettings, data.get("ai")),
            live_transcription=_safe(
                LiveTranscriptionSettings,
                data.get("live_transcription"),
            ),
            plugins=_safe(PluginSettings, data.get("plugins")),
            copilot=_safe(CopilotSettings, data.get("copilot")),
        )
