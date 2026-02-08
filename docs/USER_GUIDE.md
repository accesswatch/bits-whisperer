# BITS Whisperer — User Guide

Welcome to **BITS Whisperer**, your desktop audio transcription companion. This guide walks you through every feature so you can get the most out of the app.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Setup Wizard](#setup-wizard)
3. [Main Window](#main-window)
4. [Adding Files](#adding-files)
5. [Transcription](#transcription)
6. [Viewing & Editing Transcripts](#viewing--editing-transcripts)
7. [Exporting](#exporting)
8. [Live Microphone Transcription](#live-microphone-transcription)
9. [AI Translation & Summarization](#ai-translation--summarization)
10. [Plugins](#plugins)
11. [Providers](#providers)
12. [AI Models](#ai-models)
13. [Settings](#settings)
14. [Audio Preprocessing](#audio-preprocessing)
15. [System Tray](#system-tray)
16. [Keyboard Shortcuts](#keyboard-shortcuts)
17. [Accessibility](#accessibility)
18. [Troubleshooting](#troubleshooting)
19. [FAQ](#faq)

---

## Getting Started

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 / macOS 12+ | Windows 11 / macOS 14+ |
| RAM | 4 GB | 8 GB+ |
| Disk Space | 500 MB (app only) | 5 GB+ (with AI models) |
| GPU | Not required | NVIDIA with 4+ GB VRAM |
| Internet | For cloud providers only | Broadband for model downloads |

### Installation

1. Download the latest installer from [GitHub Releases](https://github.com/accesswatch/bits-whisperer/releases).
2. Run the installer and follow the on-screen instructions.
3. Launch BITS Whisperer from your Start Menu (Windows) or Applications folder (macOS).

### First Launch

On first launch, the **Setup Wizard** guides you through initial configuration. You can skip it and configure everything later from the **Tools** menu.

After the wizard, BITS Whisperer checks for required external tools (like **ffmpeg**). If ffmpeg is missing, the app will offer to install it automatically using the Windows Package Manager (winget). If winget is unavailable, you'll see step-by-step manual installation instructions. ffmpeg is needed for audio preprocessing and format conversion.

### On-Demand SDK Installation

BITS Whisperer uses a lightweight installer — provider SDKs (such as the OpenAI client, Google Cloud libraries, or the faster-whisper AI engine) are **not bundled** with the application. Instead, they are downloaded and installed automatically the first time you use a provider.

When you start a transcription or download a local model, the app will:

1. Check if the required SDK is already installed.
2. If not, show a dialog explaining what will be downloaded and the approximate size.
3. Download the packages from PyPI and install them in a local folder managed by BITS Whisperer.
4. This only happens once per provider — subsequent uses are instant.

**No system Python or pip is required.** The app handles everything internally.

SDKs are stored in: `%LOCALAPPDATA%\BITS Whisperer\BITSWhisperer\site-packages\` (Windows) or `~/Library/Application Support/BITS Whisperer/site-packages/` (macOS).

---

## Setup Wizard

The setup wizard appears automatically on your first launch and walks you through five steps:

### Step 1: Welcome
A brief overview of what BITS Whisperer does and what the wizard will configure.

### Step 2: Hardware Detection
The app scans your computer and shows:
- **Processor, RAM, GPU** — what you're working with
- **Free disk space** — how much room for AI models
- **Recommendation** — which models fit your hardware best

### Step 3: Model Selection
Choose which AI models to download for offline transcription:
- A **star** marks the recommended model for your hardware
- Check the boxes for models you want
- Total download size and disk space are shown
- Click **Download Selected Models Now** to start
- Downloads happen in the background — you'll get a notification when each model is ready

### Step 4: Cloud Services (Optional)
Enter API keys for any cloud transcription service you use:
- Keys are stored in your operating system's secure credential vault
- Each service shows pricing and a direct link to get a key
- Skip this step if you only want local (offline) transcription

### Step 5: Preferences
Set your basics:
- **Language** — your primary transcription language
- **Export format** — default output format (Text, Markdown, Word, SRT)
- **Auto-export** — automatically save transcripts when done
- **Timestamps** — include time markers in transcripts
- **Minimize to tray** — keep running in the background
- **Notifications** — get alerts when transcription completes
- **Update checks** — automatically check for new versions

### Step 6: Summary
Review your choices and click **Finish** to start using the app.

> **Tip**: You can always re-configure everything from **Tools, then Settings** (Ctrl+,) or **Tools, then Manage Models** (Ctrl+M).

---

## Main Window

The main window has four areas:

| Area | Purpose |
|------|---------|
| **Menu Bar** | All actions — File, Queue, View, Tools, Help |
| **File Queue** (left panel) | Files waiting to be transcribed |
| **Transcript Viewer** (right panel) | View/edit completed transcripts |
| **Status Bar** | Current activity, provider, job count |

### Splitter
A movable divider separates the queue and transcript panels. Drag it to resize, or use **View, then Focus Queue / Focus Transcript** from the menu.

---

## Adding Files

### Methods
- **Drag & Drop** — drag audio files onto the window
- **File, then Add Files** (Ctrl+O) — browse and select files
- **File, then Add Folder** — add all audio files in a folder
- **Recent Files** — re-open files from **File, then Recent Files**

### Supported Formats
MP3, WAV, OGG, Opus, FLAC, M4A, AAC, WebM, WMA, AIFF, AMR, MP4

### Limits (configurable in Advanced Settings)
- Max file size: 500 MB
- Max duration: 4 hours
- Max batch: 100 files / 10 GB

---

## Transcription

### Starting
1. Add files to the queue.
2. Press **F5** or **Queue, then Start Transcription**.
3. Watch progress in the queue panel and status bar.

### Providers
By default, BITS Whisperer uses the **Local Whisper** provider (free, offline). Change your default provider in **Tools, then Settings, then General**.

### Batch Processing
Add multiple files and they'll be processed sequentially (or in parallel if configured). The status bar shows overall progress.

### Background Processing
If you minimize to the system tray, transcription continues in the background. You'll get a desktop notification when each file finishes.

---

## Viewing & Editing Transcripts

After transcription completes, click a file in the queue to see its transcript in the right panel.

- **Edit** — make corrections directly in the transcript viewer
- **Find** — use Ctrl+F to search within the transcript; F3 for Find Next
- **Timestamps** — shown inline if enabled in settings
- **Speakers** — speaker labels appear if the provider supports diarization

### Speaker Management

When speakers are detected, a **Speakers** bar appears above the transcript showing all identified speakers.

#### Renaming Speakers
1. Click **Manage Speakers...** to open the rename dialog.
2. Replace generic IDs (Speaker 1, Speaker 2) with real names (Alice, Bob).
3. Click **OK** — all instances update instantly throughout the transcript.

#### Reassigning Segments
1. Right-click any line in the transcript.
2. Choose **Assign to Speaker** and select the correct speaker.
3. Or choose **New Speaker...** to create a new speaker and assign the line.

#### Speaker Display Format
Transcripts with speakers use the format:
```
[00:05]  Alice: Welcome to our meeting.
[00:12]  Bob: Thanks for having me.
```

#### Cloud-Free Local Diarization
If your transcription provider doesn't support speaker detection, enable **local diarization** in Settings:
1. Install pyannote.audio: `pip install pyannote.audio`
2. Set up a HuggingFace auth token (some models are gated)
3. Enable: Settings > Diarization > Use local diarization
4. Local diarization runs automatically as post-processing on any provider's output

---

## Exporting

### Manual Export
1. Select a transcript.
2. **File, then Export** (Ctrl+E).
3. Choose format and location.

### Auto-Export
Enable in **Settings, then General, then Auto-export**. Transcripts are saved automatically when done, in your chosen format and location.

### Export Formats

| Format | Extension | Best For |
|--------|-----------|----------|
| Plain Text | .txt | Simple sharing, email |
| Markdown | .md | Documentation, GitHub |
| HTML | .html | Web publishing |
| Microsoft Word | .docx | Reports, editing |
| SubRip Subtitles | .srt | Video subtitles |
| WebVTT | .vtt | Web video captions |
| JSON | .json | Data processing, APIs |

### Export Options (Settings, then Output)
- **Filename template** — custom naming with `{stem}`, `{date}`, etc.
- **Include header/metadata** — add file info at the top
- **Encoding** — UTF-8 (default), or other encodings
- **Overwrite** — replace existing files or auto-number

---

## Live Microphone Transcription

BITS Whisperer can transcribe speech from your microphone in real time.

### Opening

- **Keyboard**: Press **Ctrl+L**
- **Menu**: Go to **Tools, then Live Transcription**

### Using the Dialog

1. **Select your microphone** — Choose from the available input devices dropdown
2. **Select a Whisper model** — Smaller models (Tiny, Base) are faster; larger models are more accurate
3. **Press Start** — Speech will be transcribed in real-time and displayed in the text area
4. **Pause / Resume** — Temporarily halt transcription without losing context
5. **Copy All** — Copy the full transcript to the clipboard
6. **Clear** — Clear the transcript display and start fresh
7. **Stop** — End the transcription session

### How It Works

- Audio is captured at 16 kHz mono using sounddevice
- Energy-based voice activity detection (VAD) identifies speech segments
- When silence exceeds the configured threshold, the buffered audio is sent to faster-whisper for transcription
- Results are displayed in the text area via thread-safe UI callbacks

### Settings

Configure live transcription in **Settings, then Live Transcription** or from the dialog:

| Setting | Default | Description |
|---------|---------|-------------|
| Model | base | Whisper model size |
| Language | auto | Force a specific language or auto-detect |
| Sample rate | 16000 | Audio capture sample rate in Hz |
| Chunk duration | 3.0 s | Minimum audio chunk before transcription |
| Silence threshold | 0.8 s | Silence duration to trigger transcription |
| VAD filter | On | Voice activity detection in faster-whisper |
| Input device | (default) | Preferred microphone device |

---

## AI Translation & Summarization

Use AI to translate and summarize your transcripts using OpenAI, Anthropic Claude, or Azure OpenAI.

### Setup

1. Go to **Tools, then AI Provider Settings**
2. In the **Providers** tab, enter your API key for at least one provider:
   - **OpenAI** — Get a key from https://platform.openai.com/api-keys
   - **Anthropic** — Get a key from https://console.anthropic.com/
   - **Azure OpenAI** — Enter your endpoint URL, deployment name, and API key from the Azure portal
3. Click **Validate** to test your key
4. Choose your preferred default provider
5. Set preferences in the **Preferences** tab (language, summarization style, temperature, max tokens)

### Translating a Transcript

1. Open or transcribe an audio file
2. Press **Ctrl+T** or go to **AI, then Translate** (or click the **Translate** button in the transcript toolbar)
3. The transcript will be translated to your configured target language
4. A dialog shows the result with a **Copy** button

### Summarizing a Transcript

1. Open or transcribe an audio file
2. Press **Ctrl+Shift+S** or go to **AI, then Summarize** (or click the **Summarize** button in the transcript toolbar)
3. Choose a summarization style in AI Provider Settings:
   - **Concise** — Brief overview (default)
   - **Detailed** — Comprehensive summary
   - **Bullet Points** — Key points as a list
4. A dialog shows the result with a **Copy** button

### Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| OpenAI | gpt-4o, gpt-4o-mini | Fastest, most reliable |
| Anthropic | Claude Sonnet 4, Claude Haiku | Strong for long transcripts |
| Azure OpenAI | Configurable deployment | Enterprise-grade, GDPR compliant |

---

## Plugins

Extend BITS Whisperer with custom transcription providers via the plugin system.

### Creating a Plugin

1. Create a `.py` file in the plugins directory
2. Implement a `register(manager)` function that receives the `ProviderManager`:

```python
PLUGIN_NAME = "My Custom Provider"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Your Name"
PLUGIN_DESCRIPTION = "Adds support for a custom transcription service"

def register(manager):
    from bits_whisperer.providers.base import TranscriptionProvider
    # Create and register your provider class
    manager.register("my_provider", MyProvider)
```

### Installing Plugins

1. Copy your plugin `.py` file to the plugins directory
   - Default: `%LOCALAPPDATA%\BITS Whisperer\plugins\` (Windows)
   - Custom: Set in **Settings, then Plugins, then Plugin Directory**
2. Restart BITS Whisperer — plugins are loaded automatically on startup

### Managing Plugins

1. Go to **Tools, then Plugins**
2. View all discovered plugins with name, version, author, and status
3. Enable or disable individual plugins
4. Disabled plugins will not be loaded on next startup

### Plugin Metadata

Plugins can include optional metadata constants:

| Constant | Description |
|----------|-------------|
| `PLUGIN_NAME` | Display name |
| `PLUGIN_VERSION` | Version string |
| `PLUGIN_AUTHOR` | Author name |
| `PLUGIN_DESCRIPTION` | Short description |

---

## Providers

BITS Whisperer supports **17 transcription engines** across three categories:

### Local (Free, Offline)

| Provider | Description | Key Required |
|----------|-------------|:------------:|
| **Local Whisper** | On-device AI (faster-whisper). Free, private, no internet needed. | No |
| **Windows Speech** | Built-in Windows SAPI5/WinRT recognition. | No |
| **Azure Embedded** | Microsoft offline speech engine. | No |
| **Vosk** | Lightweight offline ASR (Kaldi). 20+ languages, 40-50 MB models. | No |
| **Parakeet** | NVIDIA NeMo high-accuracy English ASR. 600M–1.1B param models. | No |

### Cloud (Paid, Online)

| Provider | Speed | Price/min | Free Tier | Key Required |
|----------|-------|-----------|-----------|:------------:|
| **OpenAI Whisper** | Fast | $0.006 | — | Yes |
| **Google Speech** | Fast | $0.016 | 60 min/mo | Yes |
| **Google Gemini** | Fast | $0.0002 | Generous | Yes |
| **Azure Speech** | Fast | $0.017 | 5 hrs/mo | Yes |
| **Deepgram Nova-2** | Very fast | $0.013 | $200 credit | Yes |
| **AssemblyAI** | Fast | $0.011 | — | Yes |
| **AWS Transcribe** | Fast | $0.024 | 60 min/mo | Yes |
| **Groq Whisper** | 188x real-time | $0.003 | — | Yes |
| **Rev.ai** | Fast | $0.020 | — | Yes |
| **Speechmatics** | Fast | $0.016 | — | Yes |
| **ElevenLabs Scribe** | Fast | $0.005 | — | Yes |

### Cloud + Audio Processing

| Provider | Description | Free Tier | Key Required |
|----------|-------------|-----------|:------------:|
| **Auphonic** | Audio post-production (noise reduction, leveling, loudness) + Whisper transcription | 2 hrs/mo | Yes |

### Setting Up Cloud Providers

BITS Whisperer provides two ways to configure cloud providers:

#### Method 1: Add Provider Wizard (Recommended)
1. Go to **Tools, then Add Provider**.
2. Select a cloud provider from the dropdown (12 available).
3. Read the description and pricing information.
4. Enter your API key (and any auxiliary credentials like AWS Region).
5. Click **Validate & Activate** — the app tests your key with a real API call.
6. On success, the provider is activated and ready for transcription.

The Add Provider wizard validates every credential with a live API call before activation. This catches typos, expired keys, and configuration issues immediately.

#### Method 2: Settings Dialog
1. Go to **Tools, then Settings, then Providers and Keys** (or during the Setup Wizard).
2. Enter your API key for the desired service.
3. Click the **Test** button to validate the key.
4. Keys are stored in your OS credential vault (Windows Credential Manager / macOS Keychain).

> **Note**: In Basic mode, only activated cloud providers appear in the provider dropdown. Use Add Provider to activate them, or switch to Advanced mode to see all providers.

### Choosing a Provider
- **Privacy first**: Local Whisper (your audio never leaves your computer)
- **Best English accuracy**: Parakeet TDT 1.1B (local) or Large v3 (local) or OpenAI Whisper (cloud)
- **Cheapest cloud**: Gemini ($0.0002/min) or Groq ($0.003/min)
- **Fastest cloud**: Groq (188x real-time) or Deepgram
- **Speaker labels**: Azure, Google, Deepgram, AssemblyAI, ElevenLabs, Rev.ai, Speechmatics, Amazon, Gemini (10 providers) or local pyannote.audio
- **Audio cleanup**: Auphonic (noise/hum removal + transcription)

---

## AI Models

BITS Whisperer includes **14 Whisper model variants** for local transcription:

| Model | Size | Speed | Accuracy | Languages | Best For |
|-------|------|-------|----------|-----------|----------|
| Tiny | 75 MB | 5 of 5 | 2 of 5 | 99 | Quick drafts |
| Tiny (English) | 75 MB | 5 of 5 | 2 of 5 | EN only | Fast English drafts |
| Base | 142 MB | 4 of 5 | 3 of 5 | 99 | Clear recordings |
| Base (English) | 142 MB | 4 of 5 | 3 of 5 | EN only | English podcasts |
| Small | 466 MB | 3 of 5 | 4 of 5 | 99 | Most recordings |
| Small (English) | 466 MB | 3 of 5 | 4 of 5 | EN only | English meetings |
| Medium | 1.5 GB | 2 of 5 | 4 of 5 | 99 | Important recordings |
| Medium (English) | 1.5 GB | 2 of 5 | 5 of 5 | EN only | Professional English |
| Large v1 | 3 GB | 1 of 5 | 5 of 5 | 99 | Professional work |
| Large v2 | 3 GB | 1 of 5 | 5 of 5 | 99 | Professional work |
| Large v3 | 3 GB | 1 of 5 | 5 of 5 | 99 | Best accuracy |
| Large v3 Turbo | 1.6 GB | 3 of 5 | 5 of 5 | 99 | Best value with GPU |
| Distil Large v2 | 1.5 GB | 4 of 5 | 4 of 5 | EN only | Fast English + GPU |
| Distil Large v3 | 1.5 GB | 4 of 5 | 4 of 5 | EN only | Fast English + GPU |

### Managing Models
Open **Tools, then Manage Models** (Ctrl+M) to:
- See which models are downloaded
- Download new models
- Delete models to free disk space
- Check hardware compatibility
- See disk space usage

### Hardware Requirements
The app automatically checks your hardware and classifies each model as:
- **Ready** — runs comfortably on your machine
- **Slow** — will work but may be slower than ideal
- **Too big** — won’t run (not enough RAM/GPU memory)

### Disk Space
Before each download, the app checks you have enough free disk space (with 10% headroom). If you're low on space, you'll get a warning.

---

## Settings

Open **Tools, then Settings** (Ctrl+,) for all configuration options.

### Tabs Overview

| Tab | What It Controls | Visibility |
|-----|-----------------|------------|
| **General** | Language, provider, model, tray, notifications, updates | Always |
| **Transcription** | Timestamps, speakers, VAD, temperature, beam size | Always |
| **Output** | Default format, directory, filename template, encoding | Always |
| **Providers & Keys** | API keys for all cloud services with Test buttons | Always |
| **Paths & Storage** | Model directory, temp directory, log file | Always |
| **Audio Processing** | 7-filter preprocessing chain | Advanced only |
| **Advanced** | File limits, concurrency, GPU settings, log level | Advanced only |

### Basic vs. Advanced Mode

**Basic Mode** (default):
- Shows 5 tabs: General, Transcription, Output, Providers & Keys, Paths & Storage
- Only local providers and **activated** cloud providers appear in the provider dropdown
- Use **Tools, then Add Provider** to activate cloud providers
- Recommended for everyday use

**Advanced Mode**:
- Shows all 7 tabs including Audio Processing and Advanced
- All cloud providers visible in the provider dropdown (activation not required)
- Full control over audio preprocessing, GPU settings, concurrency, and chunking
- Toggle via **View, then Advanced Mode** (Ctrl+Shift+A)

Your mode preference is saved between sessions. You can also set it in the Setup Wizard.

---

## Audio Preprocessing

BITS Whisperer applies a 7-filter audio cleanup chain before transcription to improve accuracy:

| Filter | Default | What It Does |
|--------|:-------:|--------------|
| High-pass | 80 Hz | Removes rumble and low-frequency noise |
| Low-pass | 8 kHz | Removes hiss and high-frequency noise |
| Noise gate | -40 dB | Silences quiet background noise |
| De-esser | Off | Reduces harsh "s" sounds |
| Compressor | -20 dB | Evens out volume differences |
| Loudness normalization | -16 LUFS | Standardizes overall volume |
| Silence trimming | -40 dB, 1s | Removes long pauses |

Configure in **Settings, then Audio Processing**. Disable individual filters or turn off the entire chain.

> **Note**: Auphonic does its own professional-grade audio processing in the cloud. If using Auphonic, you may want to disable local preprocessing.

---

## System Tray

BITS Whisperer can minimize to the system tray for background processing:

- **Close with tray enabled**: the app minimizes to tray instead of quitting
- **Tray icon menu**: right-click for Show, Start, Pause, Settings, Quit
- **Notifications**: desktop balloon notifications when transcription completes
- **Configure**: Settings, then General, then "Minimize to system tray"

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Add files |
| Ctrl+E | Export transcript |
| Ctrl+S | Save (manual save) |
| Ctrl+, | Open Settings |
| Ctrl+M | Manage Models |
| Ctrl+Shift+A | Toggle Advanced Mode |
| Ctrl+L | Live Transcription |
| Ctrl+T | Translate Transcript |
| Ctrl+Shift+S | Summarize Transcript |
| F5 | Start transcription |
| F3 | Find next in transcript |
| Ctrl+F | Find in transcript |
| Ctrl+W | Close file |
| Ctrl+Q | Quit |
| Alt+F | File menu |
| Alt+Q | Queue menu |
| Alt+V | View menu |
| Alt+T | Tools menu |
| Alt+A | AI menu |
| Alt+H | Help menu |

All menu items have keyboard mnemonics (underlined letters) for quick access.

---

## Accessibility

BITS Whisperer is designed for full accessibility:

### Screen Readers
- All controls have accessible names and descriptions
- Status updates are announced via the status bar
- Progress is reported through gauges and text
- Tested with NVDA on Windows

### Keyboard Navigation
- Full Tab/Shift+Tab navigation through all controls
- All actions available through the menu bar with mnemonics
- Accelerator keys for common actions (see Shortcuts above)
- Arrow keys for list navigation

### Visual
- Respects system high-contrast settings
- No hard-coded colors — uses system theme
- Resizable dialogs and panels
- Clear text labels on all controls

### Tips
- Press **Alt** to activate the menu bar, then use arrow keys
- Press **Tab** to move between panels
- Press **Enter** to activate buttons
- Press **Space** to toggle checkboxes

---

## Troubleshooting

### "Model download failed"
- Check your internet connection
- Ensure you have enough disk space (the app will warn you)
- Try again — downloads can be interrupted by network issues
- Check the log file: **Help, then View Log**

### "Transcription failed"
- Check the file is a supported audio format
- Try a different provider
- For local models, ensure the model is downloaded
- For cloud services, verify your API key is correct
- Check file size is within limits (default: 500 MB)
- View the error in the log: **Help, then View Log**

### "Provider key invalid"
- Double-check the key in **Settings, then Providers and Keys**
- Keys are validated on save — the app will confirm whether the key is valid or invalid
- Some services require billing to be enabled before the API works
- Re-generate the key on the provider's website if needed

### "Application won't start"
- Check the log file at: `%LOCALAPPDATA%\BITS Whisperer\app.log` (Windows) or `~/Library/Application Support/BITS Whisperer/app.log` (macOS)
- Delete `settings.json` to reset to defaults (same directory)
- Reinstall if the issue persists

### "ffmpeg not found"
- BITS Whisperer will try to install ffmpeg automatically on first launch
- If automatic installation didn't work, install manually:
  - **winget**: `winget install Gyan.FFmpeg`
  - **Chocolatey**: `choco install ffmpeg`
  - **Manual**: Download from https://www.gyan.dev/ffmpeg/builds/ and add the `bin` folder to your PATH
- Restart BITS Whisperer after installing ffmpeg

### "Slow transcription"
- Use a smaller model (Tiny or Base)
- Enable GPU acceleration if you have an NVIDIA GPU
- Close other applications to free up RAM
- Use a cloud provider for faster processing
- Enable audio preprocessing — cleaner audio transcribes faster

### "SDK installation failed"
- Check your internet connection — SDKs are downloaded from PyPI.
- Ensure you have enough disk space. Some SDKs (like Local Whisper) need ~220 MB.
- Check the log file (**Tools, then View Log**) for detailed error messages.
- Try again — the download may have been interrupted by network issues.
- As a fallback, you can install the SDK manually:
  - Open a command prompt
  - Run: `pip install --target "%LOCALAPPDATA%\BITS Whisperer\BITSWhisperer\site-packages" <package-name>`
  - Restart BITS Whisperer

### "Provider not available after SDK install"
- Restart BITS Whisperer — some SDKs require a fresh start to load correctly.
- Check that the API key is configured in **Settings, then Providers and Keys**.
- View the log file for import errors: **Tools, then View Log**.

### Resetting the App
To start fresh:
1. Delete the data directory:
   - Windows: `%LOCALAPPDATA%\BITS Whisperer\`
   - macOS: `~/Library/Application Support/BITS Whisperer/`
2. This removes settings, downloaded models, and the job database.
3. The Setup Wizard will appear again on next launch.

---

## FAQ

**Q: Is my audio sent to the internet?**
A: Only if you use a cloud provider. Local Whisper processes everything on your computer. Your audio files are never uploaded without your explicit choice.

**Q: Do I need an internet connection?**
A: No — once you've downloaded a local model, BITS Whisperer works entirely offline. You only need internet to download models or use cloud providers.

**Q: Which model should I use?**
A: The Setup Wizard recommends one based on your hardware. As a rule of thumb:
- **4 GB RAM, no GPU**: Base
- **8 GB RAM, no GPU**: Small
- **GPU with 4+ GB VRAM**: Large v3 Turbo
- **GPU with 6+ GB VRAM**: Large v3

**Q: How are my API keys stored?**
A: Keys are stored in your operating system's credential vault (Windows Credential Manager or macOS Keychain) — the same system used by web browsers and other apps. They are never written to plain-text files or logs.

**Q: Can I use multiple providers for different files?**
A: Yes! You can set a default provider and change it per file from the queue or Settings.

**Q: How much disk space do I need?**
A: The app itself needs about 100 MB. Models range from 75 MB (Tiny) to 3 GB (Large). Download only the models you need — you can always add more later.

**Q: Does it work on macOS?**
A: Yes! BITS Whisperer runs on Windows 10+ and macOS 12+. Linux support is planned.

**Q: How do I update?**
A: The app checks for updates on startup (configurable). When an update is available, you'll be prompted to download it. You can also check manually via **Help, then Check for Updates**.

---

*BITS Whisperer v1.1.0 — Developed by Blind Information Technology Solutions (BITS). Made with care for accessibility and privacy.*
