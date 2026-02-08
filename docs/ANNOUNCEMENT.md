# BITS Whisperer — Your Audio, Your Words, Your Way

**The free, privacy-first desktop app that turns audio into text — fast, accurate, and fully accessible.**

---

## What Is BITS Whisperer?

BITS Whisperer is a powerful yet easy-to-use desktop application for Windows and macOS that converts speech to text. Whether you're a journalist, podcaster, student, researcher, content creator, or anyone who works with audio — BITS Whisperer gives you professional-quality transcription right from your desktop.

No subscriptions. No cloud lock-in. No data harvesting. Just drag, drop, and transcribe.

---

## Key Features

### 17 Transcription Engines — One App

Choose the best tool for the job:

- **On-device AI** — Whisper models from OpenAI run locally on your own hardware — your audio never leaves your computer. Choose from 14 model sizes (Tiny to Large v3 Turbo) matched to your hardware.
- **Cloud providers** — When you need maximum accuracy or speed, connect to OpenAI, Google Cloud Speech, Azure Speech, Deepgram, AssemblyAI, AWS Transcribe, Groq, Gemini, Rev.ai, Speechmatics, ElevenLabs, Auphonic, and more.
- **Auphonic integration** — Professional audio post-production (leveling, loudness normalization, noise & hum reduction, filtering, silence/filler/cough cutting) with configurable speech recognition (Whisper, Google, Amazon, Speechmatics). Provider-specific settings let you configure loudness targets, output formats, and which audio algorithms to apply.
- **Windows built-in** — Use the Windows Speech Recognizer (no setup required) or Azure Embedded Speech for offline cloud-quality results.
- **Vosk offline** — Lightweight, Kaldi-based speech recognition with 20+ language models (40-50 MB). Runs on the lowest-end hardware where even Whisper Tiny is too heavy.
- **NVIDIA Parakeet** — State-of-the-art English ASR via NeMo. 600M and 1.1B parameter models with CTC and TDT decoders for excellent accuracy and timestamp precision.
- **Smart routing** — BITS Whisperer automatically recommends the best model for your hardware and workload.

### Cloud Provider Onboarding

BITS Whisperer makes it easy to add cloud transcription services:

- **Add Provider wizard** — Go to Tools, then Add Provider to walk through a guided setup for any of the 12 cloud providers
- **Live API validation** — Your credentials are tested with a real API call before activation — no guessing whether your key works
- **One-click activation** — Once validated, the provider appears in your settings and is ready for transcription
- **Secure storage** — API keys stored in your OS credential vault (Windows Credential Manager / macOS Keychain)

### Deeply Configurable Transcription

Fine-tune every detail of your output:

- **Timestamps** — Toggle timestamps on/off, choose between `hh:mm:ss`, `mm:ss`, or seconds format
- **Speaker labels** — Identify who's speaking (diarization) via 10 cloud providers or cloud-free local pyannote.audio. Post-transcription speaker editing lets you rename speakers and reassign segments with a right-click
- **Confidence scores** — See how certain the model is about each segment
- **Word-level timing** — Get precise start/end times for every single word
- **Language detection** — Auto-detect from 99+ languages, or lock to a specific language
- **Paragraph segmentation** — Automatically group sentences into readable paragraphs
- **Segment merging** — Merge short fragments for cleaner output
- **VAD filtering** — Voice Activity Detection removes silence before transcription for faster, cleaner results
- **Model tuning** — Control temperature, beam size, compute type, and initial prompts for exact control over inference

### 7 Export Formats

Save your transcripts exactly how you need them:

- **Plain Text** (.txt) — Simple and universal
- **Markdown** (.md) — Formatted for blogs, wikis, and documentation
- **HTML** (.html) — Ready for the web
- **Microsoft Word** (.docx) — Professional documents with formatting
- **SubRip** (.srt) — Industry-standard subtitles
- **WebVTT** (.vtt) — Web-native captions
- **JSON** (.json) — Structured data for developers and integrations

### Audio Preprocessing Pipeline

Noisy recording? Uneven volume? BITS Whisperer cleans it up before transcription:

- **High-pass filter** — Removes low rumble and wind noise
- **Low-pass filter** — Cuts ultrasonic interference
- **Noise gate** — Silences background hiss
- **De-esser** — Tames harsh sibilance
- **Compressor** — Evens out volume differences between speakers
- **Loudness normalization** — EBU R128 broadcast-standard leveling
- **Silence trimming** — Removes dead air

Each filter is independently configurable — enable what you need, skip what you don't.

### Batch Processing

- Drag and drop entire folders of audio files
- Process up to 100 files per batch
- Multiple concurrent transcription jobs
- **Background processing** — Minimize to the system tray and let BITS Whisperer work while you do other things
- **Auto-export** — Finished transcripts are automatically saved in your chosen format
- **Notifications** — Balloon/toast notifications when jobs complete (even when minimized)
- **Progress tracking** — Real-time progress in the status bar and system tray tooltip

### Accessibility First

BITS Whisperer is built from the ground up to be usable by everyone:

- **Full keyboard navigation** — Every feature is reachable without a mouse
- **Screen reader friendly** — Tested with NVDA; all controls are labeled and announced
- **Menu bar primary interface** — All actions have keyboard mnemonics and accelerators
- **High contrast support** — Uses system colors; works with any Windows theme
- **Accessible settings dialog** — Tab, Shift+Tab, Ctrl+Tab, and Ctrl+Shift+Tab all work as expected

### Privacy & Security

- **Local storage** — Transcripts stay on your computer by default
- **Secure credential storage** — API keys are stored in your OS credential vault (Windows Credential Manager / macOS Keychain) — never in plain text
- **No telemetry** — We don't track you, period
- **Open source** — Inspect every line of code

### Modern Desktop Experience

- **First-run setup wizard** — Guided 7-page wizard that scans your hardware, lets you choose Basic or Advanced experience mode, recommends models, offers downloads, and configures everything in one magical experience
- **Basic & Advanced modes** — Start with a clean, simple interface (Basic) or unlock full control with all settings tabs, audio processing, and every provider (Advanced). Choose during setup or toggle anytime from the View menu (Ctrl+Shift+A)
- **Automatic dependency setup** — Detects missing ffmpeg at startup and offers one-click install via winget (Windows), with manual instructions fallback
- **On-demand SDK installer** — Provider SDKs are not bundled in the installer, keeping it small (~40 MB). When you first use a provider, the required SDK is downloaded and installed automatically — no system Python or pip needed
- **System tray** — Minimize and keep working; restore with a click
- **Recent files** — Quick access to your last 10 audio files
- **Hardware detection** — Automatically identifies your CPU, RAM, and GPU to recommend compatible models
- **Disk space checks** — Pre-flight validation before every model download; friendly warnings when space is low
- **Auto-update** — Checks GitHub for new releases on startup
- **Cross-platform** — Runs on Windows 10+ and macOS 12+ with GPU acceleration (CUDA / Apple Silicon Metal)
- **Settings persistence** — All your preferences are saved between sessions
- **Comprehensive user guide** — Built-in documentation covering every feature, shortcut, and troubleshooting step
- **Professional Windows installer** — Inno Setup-based installer with Start Menu shortcuts, optional desktop shortcut, and clean uninstaller
- **Setup Wizard in Help menu** — Re-run the setup wizard anytime from Help, then Setup Wizard
- **Learn more about BITS** — Quick link to the BITS website from the Help menu

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 / macOS 12+ | Windows 11 / macOS 14+ |
| Python | 3.10+ | 3.11+ |
| RAM | 4 GB | 16 GB |
| GPU | Not required | NVIDIA with 4+ GB VRAM |
| Disk | 500 MB | 5 GB (for large models) |
| ffmpeg | Required | Auto-installed on first launch |

---

## Getting Started

### Install from Source

```bash
git clone https://github.com/accesswatch/bits-whisperer.git
cd bits-whisperer
pip install -e ".[dev]"
bits-whisperer
```

### Install from Requirements

```bash
pip install -r requirements.txt
python -m bits_whisperer
```

### Build a Standalone Executable

```bash
pip install pyinstaller
python build_installer.py --lean
```

The built application will be in `dist/BITS Whisperer/`.

### Build a Windows Installer

```bash
# Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
iscc installer.iss
```

Output: `dist/BITS_Whisperer_Setup.exe`

---

## Who Is This For?

- **Journalists** — Interview transcription without expensive subscriptions
- **Students** — Record and transcribe lectures automatically
- **Podcasters** — Generate show notes and transcripts for accessibility
- **Content creators** — Subtitle your videos in multiple formats
- **Researchers** — Transcribe interviews and focus groups with confidence scores
- **Accessibility advocates** — Make audio content available to everyone
- **Privacy-conscious professionals** — Keep sensitive recordings off the cloud
- **Power users** — Maximum control over every aspect of transcription

---

## What's Next

- Real-time microphone transcription
- Translation and summarization
- Plugin system for custom providers

---

**BITS Whisperer** — because your words matter.

*Free. Open source. Accessible. Private.*

Developed by **Blind Information Technology Solutions (BITS)**.
