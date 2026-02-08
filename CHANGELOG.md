# Changelog

All notable changes to BITS Whisperer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] — 2026-02-08

### Added
- **Google Gemini AI** — Added Gemini as an AI provider for translation and summarization using `google-genai` SDK. Supports `gemini-2.0-flash`, `gemini-2.5-pro`, and `gemini-2.5-flash` models
- **GitHub Copilot SDK integration** — Full Copilot SDK integration for interactive transcript analysis via `github-copilot-sdk` Python package:
  - **CopilotService** — Background async service managing Copilot CLI lifecycle, sessions, streaming responses, and custom tools (search_transcript, get_speakers, get_transcript_stats)
  - **AI Chat Panel** — Interactive bottom panel (Ctrl+Shift+C) for real-time transcript Q&A with streaming responses, quick action buttons (Summarize, Key Points, Topics, Speakers), and multi-turn conversations
  - **Copilot Setup Wizard** — 4-step guided dialog for CLI installation (WinGet/npm), SDK installation, authentication (CLI login or PAT), and connection testing
  - **Agent Builder** — 4-tab dialog for designing custom AI agents without knowing markdown/metadata: Identity, Instructions (with presets), Tools (permission checkboxes), and Welcome Message. Save/load agent configs as JSON
- **AI menu expansion** — New menu items: Chat with Transcript (Ctrl+Shift+C), Copilot Setup, Agent Builder
- **Setup Wizard AI page** — New page 6 in the first-run wizard for configuring Gemini, Copilot, and OpenAI AI features
- **Installer Copilot option** — Optional Copilot CLI installation via WinGet during setup (unchecked by default)
- **CopilotSettings** — New settings dataclass with 11 configurable fields (enabled, CLI path, model, streaming, system message, agent config, transcript tools)
- **5 AI providers** — AI Provider Settings dialog now supports OpenAI, Anthropic, Azure OpenAI, Google Gemini, and GitHub Copilot with model selection and key validation for each

### Changed
- **AI Provider Settings** — Added Gemini and Copilot provider entries with API key fields, model selectors, and validation buttons
- **Version** bumped to 1.2.0

---

## [1.1.0] — 2026-02-08

### Added
- **Live microphone transcription** — Real-time speech-to-text using faster-whisper with microphone input via sounddevice. Energy-based VAD, configurable model/language/device, pause/resume, full accessible dialog (Ctrl+L)
- **AI translation & summarization** — Translate transcripts to 15+ languages and generate summaries (concise, detailed, bullet points) using OpenAI GPT-4o, Anthropic Claude, or Azure OpenAI. New AI menu with Ctrl+T (Translate) and Ctrl+Shift+S (Summarize)
- **AI Provider Settings dialog** — Tabbed dialog for configuring AI API keys (OpenAI, Anthropic, Azure OpenAI), model selection, temperature, max tokens, and preferences
- **Plugin system** — Extensible plugin architecture for custom transcription providers. Plugins are discovered from a configurable directory, loaded dynamically via `register(manager)` entry point, with enable/disable management
- **3 new settings groups** — `AISettings` (provider, models, temperature, translation language, summarization style), `LiveTranscriptionSettings` (model, language, device, VAD, chunk duration), `PluginSettings` (enabled, directory, disabled list)
- **4 new key store entries** — Anthropic API Key, Azure OpenAI API Key/Endpoint/Deployment stored securely in OS credential vault
- **Translate & Summarize buttons** — Added to transcript panel toolbar for quick access
- **numpy dependency** — Added to core dependencies for audio buffer processing
- **Optional dependency groups** — `live` (sounddevice + faster-whisper), `ai-openai`, `ai-anthropic`, `ai-all` for selective installation

---

## [1.0.0] — 2026-02-08

### Added
- **17 transcription providers** — Local Whisper, Windows Speech (SAPI5), Azure Embedded Speech, OpenAI Whisper, ElevenLabs Scribe, Groq Whisper, AssemblyAI, Deepgram Nova-2, Azure Speech Services, Google Speech-to-Text, Google Gemini, Amazon Transcribe, Rev.ai, Speechmatics, Auphonic, Vosk, NVIDIA Parakeet
- **14 Whisper model variants** — Tiny through Large v3, plus Turbo and Distil variants, with plain-English descriptions and hardware eligibility checks
- **7 export formats** — Plain Text, Markdown, HTML, Word (.docx), SRT, VTT, JSON
- **Auphonic integration** — Full Auphonic API support: adaptive leveler, loudness normalization, noise & hum reduction, filtering, silence/filler/cough cutting, crosstalk detection, configurable speech recognition (Whisper/Google/Amazon/Speechmatics), output format/bitrate selection. All features configurable via provider settings.
- **Speaker diarization** — Automatic speaker detection via 10 cloud providers (Azure, Google, Deepgram, AssemblyAI, Rev.ai, Speechmatics, ElevenLabs, Amazon, Gemini) with configurable max speaker count. Enable "Include speaker labels" in transcription settings.
- **Cloud-free local diarization** — Optional pyannote.audio integration for privacy-first speaker detection. Works as post-processing on ANY provider's output. Configurable via `DiarizationSettings` (min/max speakers, model selection, HuggingFace auth token).
- **Speaker editing UI** — Post-transcription speaker management in the transcript panel: "Manage Speakers" dialog for global rename (Speaker 1 to Alice), right-click context menu for per-segment reassignment, "New Speaker" creation, and instant transcript refresh with `SpeakerName: text` notation.
- **Provider-specific settings** — Each cloud provider exposes its unique configurable options during onboarding (Add Provider dialog). Auphonic: loudness/noise/silence/filler/hum/speech engine/output format. Deepgram: model/smart format/punctuation. AssemblyAI: chapters/content safety/sentiment. All settings stored via `ProviderDefaultSettings` and applied automatically before transcription.
- **Provider `configure()` method** — Non-abstract method on `TranscriptionProvider` base class allows injecting per-provider default settings before transcription. Implemented on: Auphonic, Deepgram, AssemblyAI, Google Speech, Azure, Groq, OpenAI, ElevenLabs.
- **Cloud provider onboarding** — "Add Provider" wizard (Tools, then Add Provider) guides users step-by-step through configuring any of the 12 cloud transcription providers. Includes live API key validation with real API calls before saving.
- **Basic & Advanced modes** — Experience mode system with Basic (streamlined, 3 tabs, activated providers only) and Advanced (all 7 tabs, full control). Toggled via Ctrl+Shift+A or View menu. Persisted as `experience_mode` in settings.
- **First-run setup wizard** — Guided 7-page wizard: experience mode selection, hardware scan, model recommendations, model downloads, cloud provider setup, preferences, and summary.
- **NVIDIA Parakeet provider** — On-device English ASR using NVIDIA NeMo. GPU-accelerated (CUDA) with CPU fallback. 600M and 1.1B parameter models with CTC and TDT decoders.
- **Vosk provider** — On-device transcription using Vosk (Kaldi-based). 10 language models (40-50 MB small, 1.8 GB large English). Runs on very low-end hardware.
- **7-filter audio preprocessing pipeline** — High-pass, low-pass, noise gate, de-esser, compressor, loudness normalisation (EBU R128), silence trim -- all user-configurable
- **Automatic ffmpeg installation** — Detects missing ffmpeg at startup and offers one-click install via winget (Windows), with manual instructions fallback
- **Batch processing** — Drag-and-drop files or folders, concurrent workers, pause/resume, cancel, clear queue
- **Background processing** — Minimize to system tray with progress tooltip, balloon notifications on completion or errors
- **System tray integration** — Programmatic icon, left-click show/hide, right-click context menu, progress tooltip
- **Model Manager** — Download, delete, and manage Whisper models with hardware eligibility checks and disk space validation
- **Self-update system** — GitHub Releases-based update checking (startup + manual), version comparison via `packaging`
- **Auto-export** — Optionally save each transcript alongside the source audio file on completion
- **Recent files** — Quick access to the last 10 opened files via File, then Recent Files
- **View Log** — Open the application log in the default text editor
- **On-demand SDK installer** — Provider SDKs downloaded from PyPI and installed automatically on first use, keeping the base installer small (~40 MB). WheelInstaller for frozen builds.
- **Inno Setup installer script** — Professional Windows installer with Start Menu shortcuts, optional desktop shortcut, license agreement, custom pages, and clean uninstaller.
- **Full accessibility** — WCAG 2.1/2.2 adapted for desktop; every control labeled; full keyboard + screen reader (NVDA) support; high contrast; `wx.CallAfter()` thread safety
- **Privacy-first** — Local storage by default; API keys in OS credential store (Windows Credential Manager / macOS Keychain); no telemetry
- **Cross-platform** — Windows 10+ and macOS 12+; CUDA and Apple Silicon Metal GPU detection
- **Disk space checks** — Pre-flight validation before every model download with 10% headroom
- **Comprehensive user guide** — Built-in documentation covering all features, providers, settings, and keyboard shortcuts

### Provider Robustness
- All 17 providers audited for thread safety, file handle leaks, API key validation, timeout handling, error propagation, and confidence normalization
- Azure Speech: ConversationTranscriber for proper diarization, real WAV-based API key validation, 30-min polling timeout
- Azure Embedded Speech: 30-min polling timeout, detailed error logging
- AWS Transcribe: confidence scoping fix, 3-hour polling timeout, S3 cleanup on error
- Windows Speech: SAPI5 file handle leak fix with try/finally
- Local Whisper: confidence normalization from negative log-probs to [0, 1] scale; deferred imports for frozen builds
- Google Speech: real `ListOperations` API call for key validation
- Transcription service: file pre-validation, exponential retry/backoff, key mapping fixes

### Security
- API keys stored via `keyring` -- never logged, printed, or committed
- Key validation with dry-run API calls on save
- No telemetry or usage tracking

---

[1.1.0]: https://github.com/accesswatch/bits-whisperer/releases/tag/v1.1.0
[1.0.0]: https://github.com/accesswatch/bits-whisperer/releases/tag/v1.0.0
