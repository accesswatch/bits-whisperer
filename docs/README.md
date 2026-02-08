# BITS Whisperer

**Consumer-grade audio transcription for Windows and macOS.**\
*Developed by Blind Information Technology Solutions (BITS).*

BITS Whisperer is a desktop application that converts speech to text using **17 transcription providers** — cloud services from Microsoft, Google, Amazon, OpenAI, and more, plus on-device Whisper models for complete privacy. Built with accessibility as a core requirement — every feature works with keyboard-only navigation and screen readers.

---

## Features

- **17 transcription providers** — Every major cloud platform plus free on-device options (see table below)
- **Auphonic integration** — Professional cloud audio post-production (leveling, loudness normalization, noise reduction, silence/filler/cough cutting, hum reduction) with configurable speech recognition (Whisper, Google, Amazon, Speechmatics) and output formats
- **Speaker diarization** — Automatic speaker detection via cloud providers (Azure, Google, Deepgram, AssemblyAI, Rev.ai, Speechmatics, ElevenLabs, Amazon, Gemini) or cloud-free local diarization using pyannote.audio
- **Speaker editing** — Post-transcription speaker management: rename speakers, reassign segments via right-click, create new speakers, with display format "Speaker: text" for natural reading
- **Provider-specific settings** — Configure each provider's unique features during onboarding (Auphonic loudness/silence/filler settings, Deepgram model/smart format, AssemblyAI chapters, Azure custom endpoints, and more)
- **14 Whisper models** — Tiny through Large-v3, plus Turbo and Distil variants, with plain-English descriptions and hardware eligibility checks
- **Audio preprocessing** — 7-filter ffmpeg pipeline (high-pass, low-pass, noise gate, de-esser, compressor, loudness normalisation, silence trim) to maximise transcription accuracy
- **Batch processing** — Drag-and-drop files or entire folders with concurrent workers
- **Background processing** — Minimize to system tray and keep transcribing; balloon notifications on completion or errors
- **System tray** — Progress tooltip, left-click show/hide, right-click context menu (pause/resume, progress summary, quit)
- **Real-time progress** — Per-file progress in the queue panel, status bar gauge, and tray tooltip
- **Cloud provider onboarding** — Add cloud providers via Tools, then Add Provider with step-by-step credential entry, live API validation, and one-click activation
- **Basic & Advanced modes** — Choose your experience level in the Setup Wizard or toggle anytime via View, then Advanced Mode (Ctrl+Shift+A). Basic mode shows a streamlined interface with only activated providers; Advanced mode unlocks all providers, audio processing, and power-user settings
- **7 export formats** — Plain Text, Markdown, HTML, Word (.docx), SRT, VTT, JSON
- **Auto-export** — Optionally save each transcript as `.txt` alongside the audio file on completion
- **Recent files** — Quick access to the last 10 opened files via File, then Recent Files
- **Self-update** — Help, then Check for Updates fetches the latest release from GitHub; silent startup check notifies you when a new version is available
- **View log** — Tools, then View Log opens the application log in your default text editor
- **Accessible** — Full keyboard navigation, screen reader support (NVDA/JAWS), high contrast, WCAG 2.1 adapted for desktop
- **Privacy-first** — Local transcript storage, API keys in Windows Credential Manager
- **Smart hardware detection** — Automatically identifies eligible Whisper models for your CPU, RAM, and GPU
- **Automatic dependency setup** — Detects missing ffmpeg at startup and offers one-click install via winget (Windows), with manual instructions fallback
- **On-demand SDK installer** — Provider SDKs are not bundled in the installer. When you first use a cloud or local provider, BITS Whisperer automatically downloads and installs only the packages needed — keeping the installer small (~40 MB) and startup fast
- **First-run setup wizard** — Guided 7-page wizard on first launch: experience mode selection, hardware scan, model recommendations, downloads, provider setup, preferences, and summary — all in one handholding experience
- **Disk space checks** — Pre-flight validation before every model download with 10% headroom; friendly warnings when space is low
- **Cross-platform** — Runs on Windows 10+ and macOS 12+; auto-detect GPU (CUDA / Apple Silicon Metal)
- **User guide** — Comprehensive built-in user guide covering every feature, provider, setting, and keyboard shortcut

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Windows 10/11** or **macOS 12+**
- **ffmpeg** on PATH (auto-installed on first launch if missing)
- **NVIDIA GPU** (optional, for larger Whisper models on Windows/Linux)
- **Apple Silicon** (optional, Metal acceleration on macOS)

### Install

```bash
git clone https://github.com/accesswatch/bits-whisperer.git
cd bits-whisperer
pip install -e ".[dev]"
```

### Run

```bash
bits-whisperer
# or
python -m bits_whisperer
```

## Architecture

```
src/bits_whisperer/
  __main__.py              # Entry point
  app.py                   # wx.App subclass
  core/                    # Business logic
    transcription_service.py  # Job queue & orchestration
    provider_manager.py       # Provider registry & routing
    audio_preprocessor.py     # 7-filter ffmpeg preprocessing
    dependency_checker.py     # Startup dependency verification & install
    device_probe.py           # Hardware detection (CPU/RAM/GPU)
    diarization.py            # Cloud-free local speaker diarization (pyannote)
    model_manager.py          # Whisper model download/cache
    sdk_installer.py          # On-demand provider SDK installer
    wheel_installer.py        # PyPI wheel downloader/extractor (frozen builds)
    settings.py               # Persistent settings (JSON-backed)
    transcoder.py             # ffmpeg audio normalisation
    updater.py                # GitHub Releases self-update
    job.py                    # Job data model
  providers/               # 17 provider adapters (strategy pattern)
    base.py              # TranscriptionProvider ABC
    local_whisper.py     # faster-whisper (local, free)
    openai_whisper.py    # OpenAI Whisper API
    google_speech.py     # Google Cloud Speech-to-Text
    gemini_provider.py   # Google Gemini
    azure_speech.py      # Microsoft Azure Speech Services
    azure_embedded.py    # Microsoft Azure Embedded Speech (offline)
    aws_transcribe.py    # Amazon Transcribe
    deepgram_provider.py # Deepgram Nova-2
    assemblyai_provider.py  # AssemblyAI
    groq_whisper.py      # Groq LPU Whisper
    rev_ai_provider.py   # Rev.ai
    speechmatics_provider.py # Speechmatics
    elevenlabs_provider.py   # ElevenLabs Scribe
    windows_speech.py    # Windows SAPI5 + WinRT (offline)
    vosk_provider.py     # Vosk offline speech (Kaldi-based)
    parakeet_provider.py # NVIDIA Parakeet (NeMo ASR, English)
    auphonic_provider.py # Auphonic audio post-production + transcription
  export/                  # Output formatters
    base.py, plain_text.py, markdown.py
    html_export.py, word_export.py
    srt.py, vtt.py, json_export.py
  storage/                 # Persistence
    database.py          # SQLite (WAL mode) for jobs
    key_store.py         # OS credential store via keyring
  ui/                      # WXPython UI
    main_frame.py        # Menu bar, splitter, status bar, tray integration
    queue_panel.py       # File queue list
    transcript_panel.py  # Transcript viewer/editor with speaker management
    settings_dialog.py   # Tabbed settings (3 simple + 2 advanced)
    progress_dialog.py   # Batch progress
    model_manager_dialog.py  # Model management
    add_provider_dialog.py   # Cloud provider onboarding
    setup_wizard.py      # First-run setup wizard (7 pages)
    tray_icon.py         # System tray (TaskBarIcon)
  utils/
    accessibility.py     # a11y helpers
    constants.py         # App-wide constants & model registry
    platform_utils.py    # Cross-platform helpers (file open, disk space, CPU/GPU detection)
```

## Supported Audio Formats

MP3, WAV, OGG, Opus, FLAC, M4A, AAC, WebM, WMA, AIFF, AMR, MP4

## Keyboard Shortcuts

| Action                 | Shortcut          |
|------------------------|-------------------|
| Add Files              | Ctrl+O            |
| Add Folder             | Ctrl+Shift+O      |
| Start Transcription    | F5                |
| Pause / Resume         | F6                |
| Cancel Selected        | Delete            |
| Clear Queue            | Ctrl+Shift+Del    |
| Export Transcript       | Ctrl+E            |
| Find Next in Transcript | F3                |
| Settings               | Ctrl+,            |
| Manage Models          | Ctrl+M            |
| Toggle Advanced Mode   | Ctrl+Shift+A      |
| Add Cloud Provider     | (Tools menu)      |
| Check for Updates      | (Help menu)       |
| Setup Wizard           | (Help menu)       |
| Learn More about BITS  | (Help menu)       |
| View Log               | (Tools menu)      |
| About                  | F1                |
| Exit / Minimize to Tray| Alt+F4            |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Building & Packaging

### PyInstaller (Portable)

```bash
# Standard build from current venv
python build_installer.py

# Lean build — clean venv, minimal output (~40 MB)
python build_installer.py --lean

# Single-file .exe (slower startup)
python build_installer.py --onefile
```

Output: `dist/BITS Whisperer/`

### Windows Installer (Inno Setup)

After building with PyInstaller, compile the Inno Setup script to create a professional Windows installer:

```bash
# Build the app first
python build_installer.py --lean

# Then compile the installer (requires Inno Setup 6+)
iscc installer.iss
```

Output: `dist/BITS_Whisperer_Setup.exe`

The installer includes Start Menu shortcuts, optional desktop shortcut, license agreement, uninstaller, and auto-launches the app after installation.

## Transcription Providers

| Provider              | Type   | Rate/min  | API Key | Highlights                              |
|-----------------------|--------|-----------|---------|------------------------------------------|
| Local Whisper         | Local  | Free      | No      | Offline, private, GPU-accelerated        |
| Windows Speech        | Local  | Free      | No      | SAPI5 + WinRT, offline (Windows only)    |
| Vosk                  | Local  | Free      | No      | Lightweight offline, 20+ languages, very low-end hardware |
| Parakeet              | Local  | Free      | No      | NVIDIA NeMo high-accuracy English ASR    |
| Azure Embedded Speech | Local  | Free      | No      | Microsoft neural models, offline         |
| OpenAI Whisper        | Cloud  | $0.006    | Yes     | Fast, reliable, verbose timestamps       |
| ElevenLabs Scribe     | Cloud  | $0.005    | Yes     | 99+ languages, best-in-class accuracy    |
| Groq Whisper          | Cloud  | $0.003    | Yes     | 188x real-time on LPU hardware            |
| AssemblyAI            | Cloud  | $0.011    | Yes     | Speaker labels, auto-chapters            |
| Deepgram Nova-2       | Cloud  | $0.013    | Yes     | Smart formatting, fast streaming         |
| Azure Speech          | Cloud  | $0.017    | Yes     | 100+ languages, continuous recog.        |
| Google Speech          | Cloud  | $0.024    | Yes     | Diarization, enhanced models             |
| Google Gemini         | Cloud  | $0.0002   | Yes     | Cheapest cloud, multimodal AI            |
| Amazon Transcribe     | Cloud  | $0.024    | Yes     | S3 integration, medical vocabularies     |
| Rev.ai                | Cloud  | $0.020    | Yes     | Human-hybrid option, high accuracy       |
| Speechmatics          | Cloud  | $0.017    | Yes     | 50+ languages, real-time streaming       |
| Auphonic              | Cloud  | ~$0.01    | Yes     | Audio post-production + configurable speech recognition |

## Speaker Diarization

BITS Whisperer supports **speaker diarization** (identifying who spoke when) through two approaches:

### Cloud Provider Diarization

10 cloud providers support built-in diarization — enable "Include speaker labels" in transcription settings:

| Provider         | Diarization | Max Speakers | Notes                          |
|------------------|-------------|-------------|--------------------------------|
| Azure Speech     | Yes         | Configurable | Uses ConversationTranscriber   |
| Google Speech    | Yes         | Configurable | Via diarization_config         |
| Deepgram         | Yes         | Auto        | Nova-2 speaker detection       |
| AssemblyAI       | Yes         | Auto        | speaker_labels feature         |
| Amazon Transcribe| Yes         | Configurable | ShowSpeakerLabels              |
| ElevenLabs       | Yes         | Auto        | Built-in diarize parameter     |
| Rev.ai           | Yes         | Auto        | Automatic speaker detection    |
| Speechmatics     | Yes         | Auto        | Speaker change detection       |
| Google Gemini    | Yes         | Auto        | Multimodal speaker detection   |
| Auphonic         | No          | n/a         | Post-production only           |

### Cloud-Free Local Diarization

For privacy-first workflows, enable **local diarization** using pyannote.audio:

1. Install pyannote.audio: `pip install pyannote.audio`
2. Set up a HuggingFace auth token (for gated models)
3. Enable in Settings: Diarization > Use local diarization
4. Works as post-processing — applies to ANY provider's output

### Speaker Editing (Post-Transcription)

After transcription, the transcript panel provides "magical" speaker management:

- **Manage Speakers** button — Opens a dialog showing all detected speakers with editable name fields. Rename "Speaker 1" to "Alice", "Speaker 2" to "Bob", etc.
- **Right-click context menu** — Click any transcript line and assign it to a different speaker or create a new one
- **Speaker notation** — Clear `[timestamp]  SpeakerName: text` format for easy reading and safe find/replace
- **Instant updates** — All speaker renames are applied globally and the transcript refreshes immediately

## Provider-Specific Settings

When adding a cloud provider via **Tools > Add Provider**, each provider shows its unique configurable options:

| Provider     | Configurable Settings                                              |
|--------------|--------------------------------------------------------------------|
| Auphonic     | Leveler, loudness, noise/hum reduction, silence/filler cutting, speech engine, output format |
| Deepgram     | Model (nova-2/nova/enhanced/base), smart format, punctuation, paragraphs |
| AssemblyAI   | Punctuation, formatting, auto chapters, content safety, sentiment  |
| Google Speech| Recognition model, max speaker count                               |
| Azure        | Custom endpoint ID                                                 |
| AWS          | Max speaker labels                                                 |
| Speechmatics | Operating point (enhanced/standard)                                |
| ElevenLabs   | Timestamp granularity (segment/word)                               |
| OpenAI       | Model, temperature                                                 |
| Groq         | Model (v3-turbo/v3/distil)                                         |
| Gemini       | Model (2.0-flash/1.5-flash/1.5-pro)                                |

## Auphonic Integration

Auphonic provides professional cloud-based audio post-production with built-in speech recognition. BITS Whisperer integrates two Auphonic components:

- **AuphonicProvider** — Transcription provider that uses Auphonic's production workflow:
  audio upload, then audio algorithms (leveler, loudness, denoising, filtering), then Whisper speech recognition, then transcript download
- **AuphonicService** — Standalone service for audio post-production without transcription (preprocessing step)

### Auphonic Capabilities

| Feature                      | Description                                          |
|------------------------------|------------------------------------------------------|
| Adaptive Leveler             | Corrects level differences between speakers          |
| Loudness Normalization       | Target LUFS (-16 podcast, -23 broadcast)              |
| Noise & Hum Reduction        | Automatic detection, configurable amount             |
| Filtering                    | High-pass, auto-EQ, bandwidth extension              |
| Silence & Filler Cutting     | Remove silences, filler words, coughs (configurable)         |
| Speech Recognition           | Built-in Whisper or Google/Amazon/Speechmatics (selectable)  |
| Hum Reduction                | 50/60 Hz hum removal                                         |
| Crosstalk Detection          | Detect overlapping speakers                                  |
| Multitrack                   | Process multi-speaker recordings per-track           |
| Output Formats               | MP3, AAC, FLAC, WAV, Opus, Vorbis, video             |
| Presets                      | Save and reuse processing configurations             |
| Publishing                   | Export to Dropbox, SoundCloud, YouTube, FTP, S3      |
| Webhooks                     | HTTP POST callbacks on completion                    |

### Auphonic Authentication

Generate an API token at https://auphonic.com/accounts/settings/#api-key and enter it in **Settings, then Providers and Keys, then Auphonic API Token**. The token is stored securely in Windows Credential Manager.

### Auphonic Pricing

| Plan        | Free Credits   | Cost        |
|-------------|----------------|-------------|
| Free        | 2 hours/month  | $0          |
| Starter     | 9 hours/month  | $11/month   |
| Professional| 45 hours/month | $49/month   |

## Audio Preprocessing

Enable via **View, then Advanced Mode, then Settings, then Audio Processing** tab:

| Filter               | Default | Purpose                                |
|-----------------------|---------|----------------------------------------|
| High-pass (80 Hz)     | On      | Remove low-frequency rumble            |
| Low-pass (8 kHz)      | On      | Cut high-frequency hiss                |
| Noise gate (-40 dB)   | On      | Suppress background noise              |
| De-esser (5 kHz)      | On      | Reduce sibilance                       |
| Compressor            | On      | Even out volume levels                 |
| Loudness norm (EBU R128) | On   | Standardise loudness to -16 LUFS      |
| Silence trim          | On      | Remove leading/trailing silence        |

## License

MIT — Copyright (c) 2025 Blind Information Technology Solutions (BITS). See [LICENSE](LICENSE).

Developed by **Blind Information Technology Solutions (BITS)**.
