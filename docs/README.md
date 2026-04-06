# BITS Whisperer

**Turn speech into text - privately, accurately, and accessibly.**

BITS Whisperer is a free, open-source desktop application for audio
transcription on Windows and macOS. Transcribe meetings, interviews, lectures,
podcasts, and voice memos using on-device AI or cloud services. You choose
what stays on your computer and what goes to the cloud.

built by [Blind Information Technology Solutions (BITS)](https://www.yourblindspot.com/)
with accessibility as a core requirement - every feature works with keyboard
navigation and screen readers.

______________________________________________________________________

## Why BITS Whisperer?

### Your audio stays on your computer

On-device transcription with 14 Whisper model sizes means your recordings
never leave your machine. No cloud, no internet, no data collection. API
keys are stored in your operating system's credential vault — never in
plain text.

### 18 transcription engines in one app

Local Whisper, Vosk, Parakeet, Windows Speech, and Azure Embedded for
offline use. OpenAI, Google, Azure, Deepgram, AssemblyAI, Amazon, Groq,
Gemini, Rev.ai, Speechmatics, ElevenLabs, Auphonic, and MAI-Transcribe-1
for cloud power.
The app recommends the best engine for your hardware automatically.

### AI that does more with your transcripts

Six AI providers — OpenAI, Anthropic Claude, Azure OpenAI, Google Gemini,
GitHub Copilot, and Ollama (free, local) — for translation, summarization,
and interactive chat. AI Actions process your transcript automatically
after transcription: meeting minutes, action items, executive summaries,
and more — with no extra step required.

GitHub Copilot setup is browser-first. Open **AI, then Copilot Setup** and sign
in with GitHub in your browser. A manual token path exists under **Other
sign-in options** only as a fallback.

### Accessible from the ground up

Full keyboard navigation, screen reader support (NVDA/JAWS), system
high-contrast compliance, and a menu-bar-first interface. Accessibility is
not an afterthought — it is the foundation.

______________________________________________________________________

## Key Features

### Transcription

- **18 providers** — 5 local (free, offline) + 13 cloud
- **14 Whisper models** — Tiny (75 MB) through Large v3 (3 GB) with
  hardware-aware recommendations
- **Speaker diarization** — 10 cloud providers + cloud-free local
  diarization via pyannote.audio, with speaker renaming and segment
  reassignment
- **Live microphone** — Real-time speech-to-text with voice activity
  detection (Ctrl+Alt+L)
- **Audio preprocessing** — 7-filter cleanup pipeline (noise gate,
  compressor, loudness normalization, and more)
- **Audio preview** — Pitch-preserving playback with clip-range selection
  before transcription
- **Batch processing** — Drag-and-drop files or folders with progress
  tracking and background processing

### AI Intelligence

- **Translate** transcripts into 15+ languages (Ctrl+T), including
  multi-language simultaneous translation
- **Summarize** as concise paragraphs, bullet points, or formal meeting
  minutes (Ctrl+Shift+S)
- **AI Actions** — Automatic post-transcription processing with 6 built-in
  presets (Meeting Minutes, Action Items, Executive Summary, Interview
  Notes, Lecture Notes, Q&A Extraction) or custom templates
- **Interactive chat** — Conversation with your transcript via the AI Chat
  Panel (Ctrl+Shift+C) with 28 slash commands
- **Document attachments** — Enrich AI actions with glossaries, style
  guides, and reference documents
- **Custom vocabulary** — Domain-specific terms for more accurate AI output
- **10 prompt templates** — 4 translation, 4 summarization, 2 analysis

### Workflow & Automation

- **Watch folder** — Monitor a directory for new audio files and
  auto-transcribe
- **Scheduled transcription** — Timed and recurring jobs with DND-aware
  rules
- **Do Not Disturb** — Detects Focus Assist (Windows) / DND (macOS) and
  pauses work automatically
- **7 export formats** — Plain text, Markdown, HTML, Word, SRT, VTT, JSON
  with auto-export option
- **System tray** — Background processing with desktop notifications
- **Budget limits** — Per-provider spending caps with cost estimation and
  confirmation dialogs
- **Plugin system** — Extend with custom transcription providers

### Setup & Usability

- **9-page setup wizard** — Guided first-run experience: hardware scan,
  model download, provider setup, AI configuration, budget, and preferences
- **Basic & Advanced modes** — Streamlined interface for everyday use;
  full control when you need it
- **On-demand SDK installer** — Provider SDKs download automatically on
  first use, keeping the installer small (~40 MB)
- **Self-update** — Check for new versions from the Help menu
- **Cross-platform** — Windows 10+ and macOS 12+ with GPU auto-detection
  (NVIDIA CUDA / Apple Silicon Metal)

______________________________________________________________________

## Transcription Providers

### Local (Free, Offline)

| Provider           | Description                                              |
| ------------------ | -------------------------------------------------------- |
| **Local Whisper**  | On-device AI, 14 model sizes, GPU-accelerated            |
| **Vosk**           | Lightweight offline ASR, 20+ languages, low-end hardware |
| **Parakeet**       | NVIDIA NeMo, high-accuracy English                       |
| **Windows Speech** | Built-in SAPI5 + WinRT, zero setup                       |
| **Azure Embedded** | Microsoft neural models, offline                         |

### Cloud (Paid, Online)

| Provider              | Rate/min | Highlights                            |
| --------------------- | -------- | ------------------------------------- |
| **Gemini**            | $0.0002  | Cheapest cloud, multimodal AI         |
| **Groq Whisper**      | $0.003   | 188x real-time speed                  |
| **ElevenLabs Scribe** | $0.005   | 99+ languages, best-in-class accuracy |
| **OpenAI Whisper**    | $0.006   | Fast, reliable                        |
| **Auphonic**          | ~$0.01   | Audio post-production + transcription |
| **AssemblyAI**        | $0.011   | Speaker labels, auto-chapters         |
| **Deepgram Nova-3**   | $0.013   | Smart formatting, streaming           |
| **Azure Speech**      | $0.017   | 100+ languages                        |
| **Speechmatics**      | $0.017   | 50+ languages, streaming              |
| **Rev.ai**            | $0.020   | Human-hybrid option                   |
| **Google Speech**     | $0.024   | Diarization, enhanced models          |
| **Amazon Transcribe** | $0.024   | S3 integration, medical vocabularies  |
| **MAI-Transcribe-1**  | $0.006   | Microsoft AI LLM Speech, 25 languages |

______________________________________________________________________

## System Requirements

| Component  | Minimum                | Recommended              |
| ---------- | ---------------------- | ------------------------ |
| OS         | Windows 10 / macOS 12+ | Windows 11 / macOS 14+   |
| RAM        | 4 GB                   | 8 GB+                    |
| Disk Space | 500 MB (app only)      | 5 GB+ (with AI models)   |
| GPU        | Not required           | NVIDIA with 4+ GB VRAM   |
| Internet   | Not required           | For cloud providers only |

______________________________________________________________________

## Installation

### Windows Installer (Recommended)

Download **BITS_Whisperer_Setup.exe** from the
[Releases page](https://github.com/accesswatch/bits-whisperer/releases)
and run it. The setup wizard will guide you through first-time configuration.

### Quick Start

1. Install and open BITS Whisperer.
1. Complete the setup wizard in **Basic** mode unless you need advanced
  controls.
1. Add one audio file with **File, then Add Files**.
1. Press **F5** to start transcription.
1. Review the transcript and export it.

### From Source

```bash
git clone https://github.com/accesswatch/bits-whisperer.git
cd bits-whisperer
pip install -e ".[dev]"
python -m bits_whisperer
```

Requires Python 3.13+.

______________________________________________________________________

## Essential Keyboard Shortcuts

| Action              | Shortcut     |
| ------------------- | ------------ |
| Add files           | Ctrl+O       |
| Add folder          | Ctrl+Shift+O |
| Start transcription | F5           |
| Export transcript   | Ctrl+E       |
| Find in transcript  | Ctrl+F       |
| Translate           | Ctrl+T       |
| Summarize           | Ctrl+Shift+S |
| AI Chat             | Ctrl+Shift+C |
| Live microphone     | Ctrl+Alt+L   |
| Settings            | Ctrl+,       |
| Manage models       | Ctrl+M       |
| All shortcuts       | Ctrl+Shift+K |

Press **Alt** to open the menu bar. Every menu item has a keyboard mnemonic.

______________________________________________________________________

## Documentation

| Document                               | Description                  |
| -------------------------------------- | ---------------------------- |
| [Getting Started](GETTING_STARTED.md)  | First-time user walkthrough |
| [User Guide](USER_GUIDE.md)            | Full end-user guide         |
| [Changelog](CHANGELOG.md)              | Version history             |
| [Product Requirements](PRD.md)         | Full technical specification |

______________________________________________________________________

## Supported Audio Formats

MP3, WAV, OGG, Opus, FLAC, M4A, AAC, WebM, WMA, AIFF, AMR, MP4

______________________________________________________________________

## License

MIT — Copyright (c) 2025 Blind Information Technology Solutions (BITS).

Developed by **Blind Information Technology Solutions (BITS)**.
