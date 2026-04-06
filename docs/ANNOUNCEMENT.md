# BITS Whisperer 1.0

**Turn Speech Into Text - Privately, Accurately, and Accessibly**

From Blind Information Technology Solutions (BITS)

______________________________________________________________________

BITS Whisperer is a free, open-source desktop application that turns spoken
audio into accurate, editable text. It runs on Windows and macOS, supports 18
transcription engines, and was built from the ground up to be accessible to
every user, including people who rely on screen readers and keyboard-only
navigation.

Whether you're transcribing a board meeting, a research interview, a podcast
episode, or a lecture, BITS Whisperer gives you a clear path from audio file to
finished transcript.

______________________________________________________________________

## Private by Default

Your audio stays on your computer unless you choose otherwise.

On-device transcription means no cloud, no internet, no data collection. API
keys are stored in your operating system's secure credential vault (Windows
Credential Manager or macOS Keychain) — never in plain text, never in config
files. BITS Whisperer collects no telemetry, phones home to no servers, and
includes no tracking of any kind.

When you choose a cloud provider, that is your decision — and the app does
nothing beyond what you explicitly ask for.

______________________________________________________________________

## 18 Transcription Engines in One App

**5 local engines** keep your audio entirely on your machine:

- **Local Whisper** — 14 AI model sizes (Tiny through Large-v3), GPU-accelerated
- **Vosk** — Lightweight offline ASR for low-end hardware, 20+ languages
- **Parakeet** — NVIDIA NeMo, state-of-the-art English accuracy
- **Windows Speech** — Built-in SAPI5 + WinRT, zero setup
- **Azure Embedded** — Microsoft neural models, offline

**13 cloud engines** connect you to the world's best speech platforms - OpenAI,
Google, Azure, Deepgram, AssemblyAI, Amazon, Groq, Gemini, Rev.ai, Speechmatics,
ElevenLabs, Auphonic, and MAI-Transcribe-1 — each with unique strengths like
real-time streaming, medical vocabularies, and broadcast-grade audio processing.

BITS Whisperer scans your hardware and recommends the best engine automatically.
You can always override the recommendation and choose exactly the provider,
model, and language you want.

______________________________________________________________________

## AI That Works With Your Transcripts

Six AI providers — OpenAI, Anthropic Claude, Azure OpenAI, Google Gemini,
Ollama (free, local), and GitHub Copilot — help you do more after transcription.

- **Translate** into 15+ languages with a single keystroke (Ctrl+T), including
  multi-language simultaneous translation
- **Summarize** as concise paragraphs, bullet points, or formal meeting minutes
  (Ctrl+Shift+S)
- **AI Actions** — Attach an action template when you add files. The AI
  processes your transcript automatically the moment transcription completes.
  Six built-in presets (Meeting Minutes, Action Items, Executive Summary,
  Interview Notes, Lecture Notes, Q&A Extraction) or create your own
- **Document Attachments** — Enrich AI actions with glossaries, style guides,
  or meeting agendas. Give each attachment its own instructions ("use as
  glossary", "cross-reference with transcript")
- **Interactive Chat** — Conversation with your transcript via the AI Chat
  Panel (Ctrl+Shift+C) with streaming responses, quick actions, and 28 slash
  commands (`/summarize`, `/translate`, `/key-points`, `/action-items`,
  `/run Meeting Minutes`)
- **GitHub Copilot setup** — Sign in with GitHub in your browser from
  **AI, then Copilot Setup**. A manual token option is still available as a
  fallback when needed.
- **Ollama** — Run AI entirely on-device using any model from the Ollama
  library or HuggingFace. Native HTTP adapter with streaming, model management,
  and health monitoring — no API key or cloud required

The app automatically manages context windows for every AI model — from
8K-token local models to 1M-token Gemini — so your transcripts fit intelligently
regardless of length.

______________________________________________________________________

## Speaker Diarization

Identify who spoke when. BITS Whisperer supports diarization through 10 cloud
providers and offers fully local, cloud-free diarization via pyannote.audio.

After transcription, rename speakers and reassign segments with a right-click —
turning "Speaker 1" and "Speaker 2" into real names throughout the entire
transcript.

______________________________________________________________________

## Audio Quality & Preview

**Seven-stage preprocessing** cleans your recordings before transcription:
high-pass filter, low-pass filter, noise gate, de-esser, compressor, loudness
normalization, and silence trimming. Each filter is independently configurable.

**Audio preview** lets you listen before transcribing with pitch-preserving
speed control and clip-range selection — transcribe only the section you want.

**Auphonic integration** provides broadcast-grade cloud processing: adaptive
leveling, loudness normalization, noise/hum reduction, silence and filler
cutting — with configurable speech recognition included.

______________________________________________________________________

## Workflow & Automation

- **Tree-view queue** — Drag-and-drop files and folders with live status,
  filtering, context menus, batch operations, and custom job naming (F2)
- **Watch folder** — Monitor a directory for new audio files and auto-transcribe
  with your preferred provider, model, and language
- **Scheduled transcription** — One-time or recurring jobs that launch
  automatically. DND-aware — jobs defer during Focus Assist and retry on the
  next run
- **Do Not Disturb** — Detects Focus Assist (Windows) / DND (macOS) and pauses
  transcription, live capture, and notifications during focus sessions
- **Budget limits** — Per-provider and per-model spending caps with cost
  estimation and confirmation dialogs
- **System tray** — Minimize and keep transcribing in the background with
  desktop notifications on completion
- **Seven export formats** — Plain Text, Markdown, HTML, Word, SRT, VTT, JSON
  with auto-export option
- **Live microphone** — Real-time speech-to-text with voice activity detection
  (Ctrl+Alt+L)
- **Plugin system** — Add custom transcription providers by dropping a `.py`
  file into the plugins directory

______________________________________________________________________

## Accessible to Everyone

BITS Whisperer was created by Blind Information Technology Solutions — an
organization founded by and for people who are blind or visually impaired.
Accessibility is not a feature added later. It is the foundation.

- Every control has an accessible name
- Every action is reachable by keyboard
- The menu bar is the primary interface, with mnemonics and accelerator keys
  on every item
- Progress is reported through gauges and status bar text that screen readers
  announce automatically
- The application respects system high-contrast settings and never hard-codes
  colors
- A 9-page setup wizard walks you through first-run configuration — hardware
  scanning, model recommendations, provider setup, AI configuration, budget,
  and preferences — all fully navigable with a screen reader

Tested with NVDA. Designed for everyone.

______________________________________________________________________

## Quick Start

1. Install and open BITS Whisperer.
1. Complete the setup wizard in **Basic** mode.
1. Add a file with **File, then Add Files**.
1. Press **F5** to start transcription.
1. Review the transcript and export it in the format you need.

______________________________________________________________________

## Setup & Usability

- **9-page setup wizard** — Guided first-run experience covering hardware scan,
  model download, provider setup, AI & Copilot configuration, budget, and
  preferences
- **Basic & Advanced modes** — Streamlined interface for everyday use; full
  control when you need it (Ctrl+Shift+A)
- **On-demand SDK installer** — Provider SDKs download automatically on first
  use, keeping the installer small (~40 MB)
- **Self-update** — Check for new versions from the Help menu
- **Cross-platform** — Windows 10+ and macOS 12+ with GPU auto-detection
  (NVIDIA CUDA / Apple Silicon Metal)
- **Searchable keyboard shortcuts** — Reference dialog (Ctrl+Shift+K) lists
  all shortcuts across 7 categories with real-time filtering
- **Settings import/export** — Back up and migrate your configuration with
  one click

______________________________________________________________________

## Free. Open Source. Accessible.

18 providers. 6 AI integrations. 7 export formats. Speaker diarization with
post-editing. Live microphone transcription. A seven-stage audio pipeline.
Intelligent context management. Do Not Disturb awareness. Scheduled
transcription. Budget tracking. A plugin system. Watch folder automation.

All of it free. All of it open source. All of it accessible.

**BITS Whisperer** - because your words matter.

______________________________________________________________________

*BITS Whisperer 1.0 — Developed by Blind Information Technology Solutions
(BITS)*

*Free and open source.
[github.com/accesswatch/bits-whisperer](https://github.com/accesswatch/bits-whisperer)*
