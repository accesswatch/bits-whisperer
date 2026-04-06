# Changelog

All notable changes to BITS Whisperer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

______________________________________________________________________

## [Unreleased]

______________________________________________________________________

## [1.0.0] — 2026-04-05

### Added

- **Watch folder** — Automatic directory monitoring for unattended
  transcription (`core/watch_folder.py`, `ui/watch_folder_dialog.py`).
  Configurable provider/model/language overrides, subfolder scanning,
  existing-file processing, and 3-second age guard. Feature-flagged via
  `watch_folder`.
- **Beta programme** — Invitation-based beta testing with SHA-256 hashed codes,
  signed manifests, feature flag gating (`beta_enabled`), and What’s New release
  notes dialog (`core/beta_service.py`, `ui/whats_new_dialog.py`,
  `ui/beta_settings_dialog.py`).
- **Product registration** — Ed25519-signed registration keys with hardware
  fingerprinting and encrypted local cache (`core/registration_service.py`).
- **GitHub OAuth** — RFC 8628 device flow for GitHub authentication
  (`core/github_oauth.py`).
- **Admin CLI tool** — `tools/bits_admin/` registration automation utility with
  17 subcommands for key generation, user management, beta invitations, CSV
  import/export, and manifest signing.
- **Watch folder tests** — 33 tests covering service lifecycle, file detection,
  subfolder scanning, pre-scan, job creation, callbacks, utilities, and settings
  round-trip (`tests/test_watch_folder.py`).
- **Ollama native HTTP adapter** — Direct REST API integration for Ollama
  (`core/ollama_adapter.py`). Streaming chat completion, model pull/delete,
  health monitoring, connection modes (HTTP/CLI/Manual), and automatic fallback.
  No OpenAI-compatible shim required.
- **Ollama as 6th AI provider** — `OllamaAIProvider` and
  `OllamaNativeAIProvider` in `core/ai_service.py`. Local, free, private AI
  translation, summarization, and chat using any Ollama model. AI Provider
  Settings updated to 6 providers.
- **Do Not Disturb detection** — Windows Focus Assist / macOS DND awareness
  (`core/dnd_monitor.py`). Configurable pause/resume for transcription and live
  microphone capture during focus sessions.
- **Scheduled transcription** — Timed and recurring transcription jobs with
  DND-aware rules (`core/scheduler_service.py`).
- **Model Manager TreeCtrl** — Multi-provider model tree view with rank score
  sorting, metadata display, and context menu (View Details, Open Folder, Copy
  Model ID).
- **Chat panel dynamic models** — Ollama model list dynamically queried from
  downloaded models. Per-session model selection (not persisted). Manage Models
  button opens Model Manager.
- **AI Settings enhancements** — Default chat model ComboBox populated from
  downloaded Ollama models, Ollama connection mode selector (HTTP/CLI/Manual),
  and Model Manager button.
- **Ollama/DND/Scheduler tests** — 50 tests covering adapter, DND monitor,
  scheduler, and settings (`tests/test_ollama_dnd_scheduler.py`).
- **Keyboard shortcuts reference dialog** — Searchable dialog listing all 35+
  shortcuts across 7 categories (File, Queue, Transcript, AI, Tools, Navigation,
  Help) with real-time filtering (`ui/keyboard_shortcuts_dialog.py`). Accessible
  from Help menu (Ctrl+Shift+K).
- **Ctrl+F find in transcript** — Frame-level accelerator that switches to the
  transcript tab and focuses the search bar.
- **Font size adjustment** — Increase (Ctrl+=), decrease (Ctrl+-), and reset
  (Ctrl+0) transcript font size. Range 6–36pt with screen reader announcements.
- **Transcript statistics** — Word count, character count, and segment count
  displayed below transcript metadata.
- **DND status in View menu** — Shows current Do Not Disturb / Focus Assist
  status in an accessible message box.
- **Progress dialog ETA & speed** — Elapsed time, estimated remaining time, and
  per-file processing speed in the batch progress dialog.
- **Settings Reset to Defaults** — One-click reset with confirmation dialog in
  the Settings dialog.
- **Settings Import/Export** — Export all settings to JSON and import from a
  previously exported file for backup and migration.
- **What's New changelog link** — HyperlinkCtrl linking to the full changelog on
  GitHub in the What's New dialog.
- **Scheduler maintenance jobs** — 3 recurring maintenance jobs registered at
  startup: Ollama health check, model cache pruning, and catalog refresh.
- **Cache pruning enforcement** — Scheduled task enforces the
  `ollama_cache_quota_gib` setting by deleting oldest models when disk usage
  exceeds the configured quota.

### Changed

- **Watch folder: watchdog backend** — Replaced 5-second polling loop with
  event-driven filesystem monitoring via `watchdog` library
  (ReadDirectoryChangesW on Windows, FSEvents on macOS). Polling retained as
  automatic fallback when `watchdog` is not installed.
- **Live transcription: Silero VAD** — Replaced RMS energy thresholding
  (energy > 0.01) with neural network-based voice activity detection via
  `silero-vad`. Provides approximately 95% accuracy vs approximately 70% with
  energy-based detection. Falls back to energy detection when `silero-vad` is
  not installed.
- **AI service: tenacity retries** — Added automatic retry with exponential
  backoff (3 attempts, 1 to 15 second delays) for transient API errors in
  OpenAI, Anthropic, Azure OpenAI, and Gemini providers. Handles rate limits,
  timeouts, connection failures, and server errors.
- **HTML export: stdlib escaping** — Replaced custom `_esc()` function with
  `html.escape()` from the standard library for more robust XSS prevention.
- **ffmpeg lookup: deduplicated** — Centralised `find_ffmpeg()` in
  `utils/platform_utils.py`. Removed duplicate implementations from
  `audio_preprocessor.py` and `transcoder.py`.
- **Deepgram default model** — Updated from Nova-2 to Nova-3. Nova-3 is
  Deepgram's current flagship model with improved accuracy and language support.
- **Deepgram model selector** — Added Nova-3 as top option in the model
  registry; Nova-2 remains available.
- **AssemblyAI speech_model forwarding** — The `speech_model` parameter is now
  correctly forwarded to the AssemblyAI SDK `TranscriptionConfig`. Previously
  the selected model was stored in metadata but not sent to the API.
- **AssemblyAI model selector** — Added Conformer-2 and Slam-1 model options
  alongside Best and Nano.
- **Google Speech model forwarding** — The `model` parameter is now forwarded
  to `RecognitionConfig`. Previously the model selection was ignored by the API
  call.
- **Google Speech model selector** — Added 5 model options: Latest Long
  (recommended), Latest Short, Chirp 2, Chirp, and Default.
- **Black → Ruff formatter** — Replaced Black with Ruff as the sole code
  formatter across all configuration (`.pre-commit-config.yaml`,
  `.github/workflows/ci.yml`, `.vscode/settings.json`,
  `.vscode/extensions.json`, `pyproject.toml`).
- **KeyStore entries** — Updated from 22 to 33 entries (registration, trial,
  beta, member verification, and Copilot keys added).
- **StrEnum migration** — `tools/bits_admin/config.py` enum classes migrated
  from `(str, Enum)` to `StrEnum` (Python 3.11+).

### Fixed

- **Admin tool `reset_devices`** — Now returns −1 for user-not-found (was 0,
  making the CLI branch unreachable).
- **Auto-export format** — Now uses the user's configured export format and
  location (`OutputSettings.auto_export_format`) instead of hard-coded plain
  text / `.txt`.
- **18 transcription providers** — Local Whisper, Windows Speech (SAPI5), Azure
  Embedded Speech, OpenAI Whisper, ElevenLabs Scribe, Groq Whisper, AssemblyAI,
  Deepgram Nova-2, Azure Speech Services, Google Speech-to-Text, Google Gemini,
  Amazon Transcribe, Rev.ai, Speechmatics, Auphonic, Vosk, NVIDIA Parakeet,
  MAI-Transcribe-1
- **14 Whisper model variants** — Tiny through Large v3, plus Turbo and Distil
  variants, with plain-English descriptions and hardware eligibility checks
- **7 export formats** — Plain Text, Markdown, HTML, Word (.docx), SRT, VTT,
  JSON
- **Auphonic integration** — Full Auphonic API support: adaptive leveler,
  loudness normalization, noise & hum reduction, filtering, silence/filler/cough
  cutting, crosstalk detection, configurable speech recognition
  (Whisper/Google/Amazon/Speechmatics), output format/bitrate selection. All
  features configurable via provider settings.
- **Speaker diarization** — Automatic speaker detection via 10 cloud providers
  (Azure, Google, Deepgram, AssemblyAI, Rev.ai, Speechmatics, ElevenLabs,
  Amazon, Gemini) with configurable max speaker count. Enable "Include speaker
  labels" in transcription settings.
- **Cloud-free local diarization** — Optional pyannote.audio integration for
  privacy-first speaker detection. Works as post-processing on ANY provider's
  output. Configurable via `DiarizationSettings` (min/max speakers, model
  selection, HuggingFace auth token).
- **Speaker editing UI** — Post-transcription speaker management in the
  transcript panel: "Manage Speakers" dialog for global rename (Speaker 1 to
  Alice), right-click context menu for per-segment reassignment, "New Speaker"
  creation, and instant transcript refresh with `SpeakerName: text` notation.
- **Provider-specific settings** — Each cloud provider exposes its unique
  configurable options during onboarding (Add Provider dialog). Auphonic:
  loudness/noise/silence/filler/hum/speech engine/output format. Deepgram:
  model/smart format/punctuation. AssemblyAI: chapters/content safety/sentiment.
  All settings stored via `ProviderDefaultSettings` and applied automatically
  before transcription.
- **Provider `configure()` method** — Non-abstract method on
  `TranscriptionProvider` base class allows injecting per-provider default
  settings before transcription. Implemented on: Auphonic, Deepgram, AssemblyAI,
  Google Speech, Azure, Groq, OpenAI, ElevenLabs.
- **Cloud provider onboarding** — "Add Provider" wizard (Tools, then Add
  Provider) guides users step-by-step through configuring any of the 13 cloud
  transcription providers. Includes live API key validation with real API calls
  before saving.
- **Basic & Advanced modes** — Experience mode system with Basic (streamlined, 3
  tabs, activated providers only) and Advanced (all 7 tabs, full control).
  Toggled via Ctrl+Shift+A or View menu. Persisted as `experience_mode` in
  settings.
- **First-run setup wizard** — Guided 9-page wizard: experience mode selection,
  hardware scan, model recommendations, model downloads, cloud provider setup,
  AI & Copilot setup, preferences, and summary.
- **NVIDIA Parakeet provider** — On-device English ASR using NVIDIA NeMo.
  GPU-accelerated (CUDA) with CPU fallback. 600M and 1.1B parameter models with
  CTC and TDT decoders.
- **Vosk provider** — On-device transcription using Vosk (Kaldi-based). 10
  language models (40-50 MB small, 1.8 GB large English). Runs on very low-end
  hardware.
- **7-filter audio preprocessing pipeline** — High-pass, low-pass, noise gate,
  de-esser, compressor, loudness normalisation (EBU R128), silence trim -- all
  user-configurable
- **Automatic ffmpeg installation** — Detects missing ffmpeg at startup and
  offers one-click install via winget (Windows), with manual instructions
  fallback
- **Batch processing** — Drag-and-drop files or folders, concurrent workers,
  pause/resume, cancel, clear queue
- **Background processing** — Minimize to system tray with progress tooltip,
  balloon notifications on completion or errors
- **System tray integration** — Programmatic icon, left-click show/hide,
  right-click context menu, progress tooltip
- **Model Manager** — Download, delete, and manage Whisper models with hardware
  eligibility checks and disk space validation
- **Self-update system** — GitHub Releases-based update checking (startup +
  manual), version comparison via `packaging`
- **Auto-export** — Optionally save each transcript alongside the source audio
  file on completion
- **Recent files** — Quick access to the last 10 opened files via File, then
  Recent Files
- **View Log** — Open the application log in the default text editor
- **On-demand SDK installer** — Provider SDKs downloaded from PyPI and installed
  automatically on first use, keeping the base installer small (~40 MB).
  WheelInstaller for frozen builds.
- **Inno Setup installer script** — Professional Windows installer with Start
  Menu shortcuts, optional desktop shortcut, license agreement, custom pages,
  and clean uninstaller.
- **Full accessibility** — WCAG 2.1/2.2 adapted for desktop; every control
  labeled; full keyboard + screen reader (NVDA) support; high contrast;
  `wx.CallAfter()` thread safety
- **Privacy-first** — Local storage by default; API keys in OS credential store
  (Windows Credential Manager / macOS Keychain); no telemetry
- **Cross-platform** — Windows 10+ and macOS 12+; CUDA and Apple Silicon Metal
  GPU detection
- **Disk space checks** — Pre-flight validation before every model download with
  10% headroom
- **Comprehensive user guide** — Built-in documentation covering all features,
  providers, settings, and keyboard shortcuts
- **Live microphone transcription** — Real-time speech-to-text using
  faster-whisper with microphone input via sounddevice. Energy-based VAD,
  configurable model/language/device, pause/resume, full accessible dialog
  (Ctrl+L)
- **AI translation & summarization** — Translate transcripts to 15+ languages
  and generate summaries (concise, detailed, bullet points) using OpenAI GPT-4o,
  Anthropic Claude, Azure OpenAI, Google Gemini, or GitHub Copilot. AI menu with
  Ctrl+T (Translate) and Ctrl+Shift+S (Summarize)
- **5 AI providers** — AI Provider Settings dialog supports OpenAI, Anthropic,
  Azure OpenAI, Google Gemini (Gemma models included), and GitHub Copilot with
  model selection, pricing info, and key validation
- **Google Gemini AI** — Gemini as an AI provider for translation/summarization
  using `google-genai` SDK. Supports `gemini-2.0-flash`, `gemini-2.5-pro`,
  `gemini-2.5-flash`, and Gemma models
- **GitHub Copilot SDK integration** — Full Copilot SDK integration for
  interactive transcript analysis via `github-copilot-sdk`:
  - **CopilotService** — Background async service managing Copilot CLI
    lifecycle, sessions, streaming responses, and custom tools
  - **AI Chat Panel** — Interactive bottom panel (Ctrl+Shift+C) for real-time
    transcript Q&A with streaming, quick action buttons, and multi-turn
    conversations
  - **Copilot Setup Wizard** — 4-step guided dialog for CLI installation
    (WinGet/npm), SDK installation, authentication (CLI login or PAT), and
    connection testing
  - **Agent Builder** — 4-tab dialog for designing custom AI agents: Identity,
    Instructions (with presets), Tools, and Welcome Message. Save/load agent
    configs as JSON
  - **Subscription-based model selection** — Full model catalog organized by
    Copilot subscription tier (Free, Pro, Business, Enterprise) with real-time
    pricing
- **Real-time streaming from cloud providers** — Progressive transcription
  streaming from Deepgram (WebSocket) and AssemblyAI (real-time) for live
  results during processing, with streaming status in AI chat panel
- **Custom vocabulary & prompt templates** — User-defined custom word lists for
  domain-specific accuracy and reusable prompt templates for
  translation/summarization workflows
- **Multi-language simultaneous translation** — Translate transcripts to
  multiple target languages at once, with parallel processing and combined
  output
- **Model pricing information** — Real-time cost estimates for AI models across
  all providers (OpenAI, Anthropic, Gemini, Copilot) displayed in settings and
  selection dialogs
- **Plugin system** — Extensible plugin architecture for custom transcription
  providers via `.py` plugins with `register(manager)` entry point
- **Installer Copilot option** — Optional Copilot CLI installation via WinGet
  during Windows setup
- **CopilotSettings** — Settings dataclass with 14 configurable fields (enabled,
  CLI path, model, streaming, system message, agent config, transcript tools,
  reasoning effort, infinite sessions, user input requests)

### Provider Robustness

- All 18 providers audited for thread safety, file handle leaks, API key
  validation, timeout handling, error propagation, and confidence normalization
- Azure Speech: ConversationTranscriber for proper diarization, real WAV-based
  API key validation, 30-min polling timeout
- Azure Embedded Speech: 30-min polling timeout, detailed error logging
- AWS Transcribe: confidence scoping fix, 3-hour polling timeout, S3 cleanup on
  error
- Windows Speech: SAPI5 file handle leak fix with try/finally
- Local Whisper: confidence normalization from negative log-probs to [0, 1]
  scale; deferred imports for frozen builds
- Google Speech: real `ListOperations` API call for key validation
- Transcription service: file pre-validation, exponential retry/backoff, key
  mapping fixes

### Security

- API keys stored via `keyring` -- never logged, printed, or committed
- Key validation with dry-run API calls on save
- No telemetry or usage tracking

______________________________________________________________________

[1.0.0]: https://github.com/accesswatch/bits-whisperer/releases/tag/v1.0.0
