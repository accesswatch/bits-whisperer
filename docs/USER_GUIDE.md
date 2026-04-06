# BITS Whisperer - User Guide

Welcome to **BITS Whisperer**. This guide walks you through the app from first
launch to everyday use, then on to advanced features when you are ready.

______________________________________________________________________

## Table of Contents

1. [Getting Started](#getting-started)
1. [Start Here](#start-here)
1. [Common Workflows](#common-workflows)
1. [Setup Wizard](#setup-wizard)
1. [Main Window](#main-window)
1. [Adding Files](#adding-files)
1. [Transcription](#transcription)
1. [Viewing & Editing Transcripts](#viewing--editing-transcripts)
1. [Exporting](#exporting)
1. [Live Microphone Transcription](#live-microphone-transcription)
1. [AI Translation & Summarization](#ai-translation--summarization)
1. [AI Actions](#ai-actions)
1. [GitHub Copilot Integration](#github-copilot-integration)
1. [Plugins](#plugins)
1. [Watch Folder](#watch-folder)
1. [Do Not Disturb](#do-not-disturb)
1. [Scheduled Transcription](#scheduled-transcription)
1. [Transcription Providers](#transcription-providers)
1. [AI Models](#ai-models)
1. [Settings Overview](#settings-overview)
1. [Audio Preprocessing](#audio-preprocessing)
1. [Queue Management](#queue-management)
1. [System Tray](#system-tray)
1. [View Menu Features](#view-menu-features)
1. [Settings Management](#settings-management)
1. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)
1. [Keyboard Shortcuts](#keyboard-shortcuts)
1. [Registration & Licensing](#registration--licensing)
1. [Updates, Release Notes & Beta Programme](#updates-release-notes--beta-programme)
1. [Accessibility](#accessibility)
1. [Troubleshooting](#troubleshooting)
1. [FAQ](#faq)

______________________________________________________________________

## Getting Started

### System Requirements

| Component  | Minimum                  | Recommended                   |
| ---------- | ------------------------ | ----------------------------- |
| OS         | Windows 10 / macOS 12+   | Windows 11 / macOS 14+        |
| RAM        | 4 GB                     | 8 GB+                         |
| Disk Space | 500 MB (app only)        | 5 GB+ (with AI models)        |
| GPU        | Not required             | NVIDIA with 4+ GB VRAM        |
| Internet   | For cloud providers only | Broadband for model downloads |

### Installation

1. Download the latest installer from
   [GitHub Releases](https://github.com/accesswatch/bits-whisperer/releases).
1. Run the installer and follow the on-screen instructions.
1. Launch BITS Whisperer from your Start Menu (Windows) or Applications folder
   (macOS).

### First Launch

On first launch, the **Setup Wizard** guides you through initial configuration.
You can skip it and configure everything later from the **Tools** menu.

After the wizard, BITS Whisperer checks for required external tools (like
**ffmpeg**). If ffmpeg is missing, the app will offer to install it
automatically using the Windows Package Manager (winget). If winget is
unavailable, you'll see step-by-step manual installation instructions. ffmpeg is
needed for audio preprocessing and format conversion.

### On-Demand SDK Installation

BITS Whisperer uses a lightweight installer. Provider SDKs, such as the OpenAI
client, Google Cloud libraries, or the faster-whisper engine, are **not
included** in the main download. The app installs them automatically the first
time you use a provider.

When you start a transcription or download a local model, the app will:

1. Check whether the required SDK is already installed.
1. If not, show a dialog explaining what will be downloaded and about how large
  it is.
1. Download the packages from PyPI and install them in a local folder managed
  by BITS Whisperer.
1. This usually happens only once for each provider.

**No system Python or pip is required.** The app handles this for you.

SDKs are stored in: `%LOCALAPPDATA%\BITS Whisperer\BITSWhisperer\site-packages\`
(Windows) or `~/Library/Application Support/BITS Whisperer/site-packages/`
(macOS).

______________________________________________________________________

## Start Here

If you want the easiest path through the app, use this checklist:

1. Install and open BITS Whisperer.
1. Run the **Setup Wizard** and choose **Basic** mode unless you already know
   that you want advanced controls.
1. Choose how you want to transcribe:
  - **Offline and private**: download a local Whisper model.
  - **Cloud-based**: add and validate a cloud provider.
1. Add one audio file with **File, then Add Files**.
1. Optionally listen first in **Tools, then Audio Preview**.
1. Start transcription with **F5**.
1. Review the transcript, fix wording, and rename speakers if needed.
1. Export the result in the format you need.
1. Optional: turn on AI features, live microphone transcription, Watch Folder,
   or scheduling once your basic workflow is working well.

If you only want the fastest first success, the easiest path is:

1. Use **Local Whisper**.
1. Download **Base** or **Small** if your computer does not already have a
  recommended model.
1. Add one short file.
1. Transcribe it.
1. Export it as text or Word.

______________________________________________________________________

## Common Workflows

### Everyday Transcription Workflow

Use this when you want to transcribe one recording, review it, and export it.

1. Add a file.
1. Choose provider, model, language, and any AI Action in the Add File Wizard.
1. Preview the audio if you want to confirm the file or trim the range.
1. Start transcription.
1. Review and edit the transcript.
1. Export in the format you need.

### Offline Private Workflow

Use this when you want your audio and transcript to stay on your computer.

1. Download a local Whisper model in **Tools, then Manage Models**.
1. Keep **Local Whisper** as your provider.
1. Turn on local export in **Settings, then Output**.
1. Optionally use local diarization and Ollama for local AI features.

### Cloud Accuracy Workflow

Use this when you want faster results, speaker labels, or provider-specific
features.

1. Open **Tools, then Add Provider**.
1. Validate your API key with a live check.
1. Choose the provider in the Add File Wizard or in Settings.
1. Review the cost estimate before large batches.

### AI Review Workflow

Use this when you want summaries, translations, or answers about a finished
transcript.

1. Set up an AI provider in **Tools, then AI Provider Settings**.
1. For GitHub Copilot, use **AI, then Copilot Setup**.
1. Open a transcript.
1. Use **AI, then Translate**, **AI, then Summarize**, or **AI, then Chat with
  Transcript**.

### Automation Workflow

Use this when you want new recordings handled with minimal manual work.

1. Turn on **Watch Folder** for automatic file pickup.
1. Configure **Scheduled Transcription** if you want jobs to run later.
1. Turn on **Do Not Disturb** awareness if you want work paused during Focus
  Assist.
1. Enable **Auto-export** so results are saved automatically.

______________________________________________________________________

## Setup Wizard

The setup wizard appears automatically on your first launch and walks you
through nine steps:

### Step 1: Welcome

A brief overview of what BITS Whisperer does and what the wizard will configure.
You'll see feature highlights and what to expect in the pages ahead.

### Step 2: Experience Mode

Choose between **Basic** and **Advanced** mode:

- **Basic** (recommended) - a simpler interface that hides advanced controls
  and shows only the providers you have turned on.
- **Advanced** - shows all settings tabs, all providers, and full control over
  audio preprocessing, GPU use, and concurrency.

You can change this at any time from **View, then Advanced Mode** (Ctrl+Shift+A).

### Step 3: Hardware Detection

The app scans your computer and shows:

- **Processor, RAM, GPU** - what your computer has
- **Free disk space** - how much room you have for AI models
- **Recommendation** - which models fit your hardware best

### Step 4: Model Selection

Choose which AI models to download for offline transcription:

- A **star** marks the recommended model for your hardware
- Check the boxes for models you want
- Total download size and disk space are shown
- Click **Download Selected Models Now** to start
- Downloads happen in the background — you'll get a notification when each model
  is ready

### Step 5: Cloud Providers (Optional)

Enter API keys for any cloud transcription service you use:

- Keys are stored in your operating system's secure credential vault
- Each service shows pricing and a direct link to get a key
- Available providers: OpenAI, Groq, Gemini, Deepgram, AssemblyAI, ElevenLabs,
  Auphonic
- Skip this step if you only want local (offline) transcription

### Step 6: AI & Copilot Configuration

Set up AI-powered features:

- **AI Provider** - Choose your preferred AI provider for translation and
  summarization (OpenAI, Anthropic, Azure OpenAI, Google Gemini, or GitHub
  Copilot)
- **API Keys** - Enter API keys for your chosen AI providers
- **GitHub Copilot** - Optionally sign in with GitHub in your browser and
  choose your Copilot
  plan for interactive transcript chat
- **Models** - Select default AI models (GPT-4o, Claude, Gemini Flash)

> **Tip**: You can skip this step and configure AI providers later from **Tools,
> then AI Provider Settings**.

### Step 7: Budget & Spending

Configure spending controls for cloud providers:

- **Enable spending limits** — set a default maximum spend per transcription
- **Always confirm paid** — show a cost confirmation dialog before each paid job
- **Per-provider limits** — set individual limits for each cloud provider
- View pricing information for all cloud providers

### Step 8: Preferences

Set your basics:

- **Language** — your primary transcription language
- **Export format** — default output format (Text, Markdown, Word, SRT)
- **Auto-export** — automatically save transcripts when done
- **Timestamps** — include time markers in transcripts
- **Minimize to tray** — keep running in the background
- **Notifications** — get alerts when transcription completes
- **Update checks** — automatically check for new versions

### Step 9: Summary

Review all your choices - hardware detected, models downloaded, providers
configured, experience mode, and budget settings - along with quick tips
for getting started. Click **Finish** to start using the app.

> **Tip**: You can always re-configure everything from **Tools, then Settings**
> (Ctrl+,) or **Tools, then Manage Models** (Ctrl+M).

______________________________________________________________________

## Main Window

The main window has four areas:

| Area                                | Purpose                                          |
| ----------------------------------- | ------------------------------------------------ |
| **Menu Bar**                        | All actions - File, Queue, AI, View, Tools, Help |
| **File Queue** (left panel)         | Files waiting to be transcribed                  |
| **Transcript Viewer** (right panel) | View/edit completed transcripts                  |
| **Status Bar**                      | Current activity, provider, job count            |

### Splitter

A movable divider separates the queue and transcript panels. Drag it to resize,
or use **View, then Focus Queue / Focus Transcript** from the menu.

______________________________________________________________________

## Adding Files

### Methods

- **Drag & Drop** - drag audio files onto the window
- **File, then Add Files** (Ctrl+O) - opens the Add File Wizard for per-file
  configuration
- **File, then Add Folder** (Ctrl+Shift+O) - add all audio files in a folder
  with cost estimation
- **Recent Files** - reopen files from **File, then Recent Files**

### Add File Wizard

When you add files, the Add File Wizard lets you configure each job:

1. **Provider & Model** - Choose the transcription provider and model
1. **Language** - Select the transcription language or auto-detect
1. **Custom Name** - Optionally give the job a display name (appears in queue
   and exports)
1. **AI Action** - Choose an AI Action to run automatically after transcription
   (see [AI Actions](#ai-actions))
1. **Audio Preview (single file)** - Listen with pitch-preserving speed control
   with configurable jump timing and optionally select a time range to transcribe

For multiple files, the custom name is automatically numbered (e.g., "Interview
(1)", "Interview (2)").

You can also open the audio preview tool from **Tools, then Audio Preview**
(Ctrl+Shift+P) to listen before adding files.

### Adding Folders

When adding a folder, BITS Whisperer:

1. Recursively scans for supported audio files
1. Opens the Add File Wizard - configure provider, model, language, custom name,
   and **AI Action** for the entire batch
1. Estimates total cost for cloud providers with a confirmation dialog
1. Groups files under a collapsible folder node in the queue

The AI Action you select in the wizard applies to every file in the folder. You
can also change AI actions per-file or per-folder after import via right-click >
**AI Action**.

### Custom Names

Give files and folders meaningful names:

- **During import** - Enter a custom name in the Add File Wizard
- **After import** - Press **F2** or right-click > **Rename** to rename any file
  or folder
- Custom names appear in the queue, transcript panel, and exports
- Clear a custom name to revert to the original filename

### Supported Formats

MP3, WAV, OGG, Opus, FLAC, M4A, AAC, WebM, WMA, AIFF, AMR, MP4

### Limits (configurable in Advanced Settings)

- Max file size: 500 MB
- Max duration: 4 hours
- Max batch: 100 files / 10 GB

______________________________________________________________________

## Transcription

### Starting

1. Add files to the queue.
1. Press **F5** or **Queue, then Start Transcription**.
1. Watch progress in the queue panel and status bar.

### Providers

By default, BITS Whisperer uses the **Local Whisper** provider (free, offline).
Change your default provider in **Tools, then Settings, then General**.

### Batch Processing

Add multiple files and they'll be processed sequentially (or in parallel if
configured). The status bar shows overall progress.

### Background Processing

If you minimize to the system tray, transcription continues in the background.
You'll get a desktop notification when each file finishes.

______________________________________________________________________

## Viewing & Editing Transcripts

After transcription completes, click a file in the queue to see its transcript
in the right panel.

- **Edit** - make corrections directly in the transcript viewer
- **Find** - use Ctrl+F to search within the transcript; F3 for Find Next
- **Timestamps** - shown inline if enabled in settings
- **Speakers** - speaker labels appear if the provider supports diarization

### Speaker Management

When speakers are detected, a **Speakers** bar appears above the transcript
showing all identified speakers.

#### Renaming Speakers

1. Click **Manage Speakers...** to open the rename dialog.
1. Replace generic IDs (Speaker 1, Speaker 2) with real names (Alice, Bob).
1. Click **OK** - all instances update instantly throughout the transcript.

#### Reassigning Segments

1. Right-click any line in the transcript.
1. Choose **Assign to Speaker** and select the correct speaker.
1. Or choose **New Speaker...** to create a new speaker and assign the line.

#### Speaker Display Format

Transcripts with speakers use the format:

```text
[00:05]  Alice: Welcome to our meeting.
[00:12]  Bob: Thanks for having me.
```

#### Cloud-Free Local Diarization

If your transcription provider doesn't support speaker detection, enable **local
diarization** in Settings:

1. Install pyannote.audio: `pip install pyannote.audio`
1. Set up a HuggingFace auth token (some models are gated)
1. Enable: Settings > Diarization > Use local diarization
1. Local diarization runs automatically as post-processing on any provider's
   output

______________________________________________________________________

## Exporting

### Manual Export

1. Select a transcript.
1. **File, then Export** (Ctrl+E).
1. Choose format and location.

### Auto-Export

Enable in **Settings, then General, then Auto-export**. Transcripts are saved
automatically when done, in your configured format and location.

You can choose the export format (Plain Text, Markdown, HTML, Word, SRT, VTT,
or JSON) and location (alongside the audio file, in a custom output directory,
or a specific folder) in **Settings, then Output**.

### Export Formats

| Format           | Extension | Best For              |
| ---------------- | --------- | --------------------- |
| Plain Text       | .txt      | Simple sharing, email |
| Markdown         | .md       | Documentation, GitHub |
| HTML             | .html     | Web publishing        |
| Microsoft Word   | .docx     | Reports, editing      |
| SubRip Subtitles | .srt      | Video subtitles       |
| WebVTT           | .vtt      | Web video captions    |
| JSON             | .json     | Data processing, APIs |

### Export Options (Settings, then Output)

- **Filename template** — custom naming with `{stem}`, `{date}`, etc.
- **Include header/metadata** — add file info at the top
- **Encoding** — UTF-8 (default), or other encodings
- **Overwrite** — replace existing files or auto-number

______________________________________________________________________

## Live Microphone Transcription

BITS Whisperer can transcribe speech from your microphone in real time.

### Opening

- **Keyboard**: Press **Ctrl+Alt+L**
- **Menu**: Go to **Tools, then Live Transcription**

### Using the Dialog

1. **Select your microphone** — Choose from the available input devices dropdown
1. **Select a Whisper model** — Smaller models (Tiny, Base) are faster; larger
   models are more accurate
1. **Press Start** — Speech will be transcribed in real-time and displayed in
   the text area
1. **Pause / Resume** — Temporarily halt transcription without losing context
1. **Copy All** — Copy the full transcript to the clipboard
1. **Clear** — Clear the transcript display and start fresh
1. **Stop** — End the transcription session

### AI Actions: How It Works

- Audio is captured at 16 kHz mono using sounddevice
- Energy-based voice activity detection (VAD) identifies speech segments
- When silence exceeds the configured threshold, the buffered audio is sent to
  faster-whisper for transcription
- Results are displayed in the text area via thread-safe UI callbacks

### Settings

Configure live transcription in **Settings, then Live Transcription** or from
the dialog:

| Setting           | Default   | Description                                |
| ----------------- | --------- | ------------------------------------------ |
| Model             | base      | Whisper model size                         |
| Language          | auto      | Force a specific language or auto-detect   |
| Sample rate       | 16000     | Audio capture sample rate in Hz            |
| Chunk duration    | 3.0 s     | Minimum audio chunk before transcription   |
| Silence threshold | 0.8 s     | Silence duration to trigger transcription  |
| VAD filter        | On        | Voice activity detection in faster-whisper |
| Input device      | (default) | Preferred microphone device                |

______________________________________________________________________

## AI Translation & Summarization

Use AI to translate and summarize your transcripts with OpenAI, Anthropic
Claude, Azure OpenAI, Google Gemini, GitHub Copilot, or Ollama on your own
computer.

### Setup

1. Go to **Tools, then AI Provider Settings**
1. In the **Providers** tab, set up at least one provider:
   - **OpenAI** - Get a key from [OpenAI API keys](https://platform.openai.com/api-keys)
   - **Anthropic** - Get a key from [Anthropic Console](https://console.anthropic.com/)
   - **Azure OpenAI** - Enter your endpoint URL, deployment name, and API key
     from the Azure portal
   - **Google Gemini** - Get a key from [Google AI Studio](https://aistudio.google.com/apikey)
   - **GitHub Copilot** - Use **AI, then Copilot Setup** and sign in with
     GitHub in your browser. Use **Other sign-in options** only if browser
     sign-in is not available or does not work for you.
   - **Ollama** - No API key is needed. Install [Ollama](https://ollama.com),
     download a model such as `llama3.2`, and BITS Whisperer will detect it.
1. Click **Validate** to test your key
1. Choose your preferred default provider
1. Set preferences in the **Preferences** tab (language, summarization style,
   temperature, max tokens)

### Translating a Transcript

1. Open or transcribe an audio file
1. Press **Ctrl+T** or go to **AI, then Translate** (or click the **Translate**
   button in the transcript toolbar)
1. The transcript will be translated to your configured target language
1. A dialog shows the result with a **Copy** button

### Summarizing a Transcript

1. Open or transcribe an audio file
1. Press **Ctrl+Shift+S** or go to **AI, then Summarize** (or click the
   **Summarize** button in the transcript toolbar)
1. Choose a summarization style in AI Provider Settings:
  - **Concise** - Brief overview (default)
  - **Detailed** - More complete summary
  - **Bullet Points** - Key points as a list
1. A dialog shows the result with a **Copy** button

### Supported AI Providers

| Provider       | Models                                                                                                  | Notes                                         |
| -------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| OpenAI         | GPT-4o, GPT-4o Mini, GPT-4 Turbo, GPT-3.5 Turbo                                                         | Fastest, most reliable                        |
| Anthropic      | Claude Sonnet 4, Claude Haiku 4, Claude 3.5 Sonnet                                                      | Strong for long transcripts                   |
| Azure OpenAI   | Configurable deployment                                                                                 | Enterprise-grade, GDPR compliant              |
| Google Gemini  | Gemini 2.0 Flash, 2.5 Pro, 2.5 Flash + 5 Gemma models                                                   | Fast, very affordable                         |
| GitHub Copilot | 7 models (GPT-4o Mini, GPT-4o, GPT-4 Turbo, Claude Sonnet 4, Claude Haiku 4, o3-mini, Gemini 2.0 Flash) | Plan-based access with GitHub-imposed usage limits |
| Ollama         | Any model from Ollama library or HuggingFace GGUF (Llama, Mistral, Gemma, Phi, etc.)                    | Free, private, runs entirely on your computer |

### AI Model Catalog

BITS Whisperer includes an AI model catalog with current pricing information to
help you choose a model. Open it from **Tools, then AI Provider Settings**.

#### OpenAI Models (4)

| Model         | Input Price/1M tokens | Output Price/1M tokens | Context Window |
| ------------- | --------------------- | ---------------------- | -------------- |
| GPT-4o Mini   | $0.15                 | $0.60                  | 128K           |
| GPT-4o        | $2.50                 | $10.00                 | 128K           |
| GPT-4 Turbo   | $10.00                | $30.00                 | 128K           |
| GPT-3.5 Turbo | $0.50                 | $1.50                  | 16K            |

#### Anthropic Models (3)

| Model             | Input Price/1M tokens | Output Price/1M tokens | Context Window |
| ----------------- | --------------------- | ---------------------- | -------------- |
| Claude Sonnet 4   | $3.00                 | $15.00                 | 200K           |
| Claude Haiku 4    | $0.80                 | $4.00                  | 200K           |
| Claude 3.5 Sonnet | $3.00                 | $15.00                 | 200K           |

#### Google Gemini Models (8, including 5 Gemma)

| Model            | Input Price/1M tokens | Output Price/1M tokens | Context Window |
| ---------------- | --------------------- | ---------------------- | -------------- |
| Gemini 2.0 Flash | $0.10                 | $0.40                  | 1M             |
| Gemini 2.5 Pro   | $1.25                 | $10.00                 | 1M             |
| Gemini 2.5 Flash | $0.15                 | $0.60                  | 1M             |
| Gemma 3 27B      | $0.10                 | $0.30                  | 128K           |
| Gemma 3 12B      | $0.08                 | $0.20                  | 128K           |
| Gemma 3 4B       | $0.05                 | $0.10                  | 128K           |
| Gemma 3 1B       | $0.02                 | $0.05                  | 32K            |
| Gemma 3n E4B     | $0.02                 | $0.05                  | 32K            |

#### GitHub Copilot Models (7)

Copilot models are included in your GitHub Copilot plan rather than billed per
token. Availability and monthly usage limits are enforced by GitHub:

| Model            | Min Tier | Premium | Context Window |
| ---------------- | -------- | ------- | -------------- |
| GPT-4o Mini      | Free     | No      | 128K           |
| GPT-4o           | Pro      | No      | 128K           |
| GPT-4 Turbo      | Pro      | No      | 128K           |
| Claude Sonnet 4  | Pro      | Yes     | 200K           |
| Claude Haiku 4   | Pro      | Yes     | 200K           |
| o3-mini          | Pro      | Yes     | 128K           |
| Gemini 2.0 Flash | Pro      | Yes     | 1M             |

### Copilot Subscription Tiers

Copilot model availability depends on your GitHub Copilot plan. Set your tier
in **Tools, then AI Provider Settings** to see the models that match your plan.
BITS Whisperer supports GitHub Copilot Free as well as paid plans, but Free
accounts remain subject to GitHub's lower monthly chat, completion, and premium
request limits.

| Tier           | Price          | Models Available                                          |
| -------------- | -------------- | --------------------------------------------------------- |
| **Free**       | $0             | GPT-4o Mini with lower monthly usage limits               |
| **Pro**        | $10/month      | Broader model access with higher limits                   |
| **Business**   | $19/user/month | Pro-level access plus organization admin controls         |
| **Enterprise** | $39/user/month | Business features plus enterprise knowledge and compliance |

### Custom Vocabulary

Improve AI accuracy for domain-specific content by adding custom terms:

1. Go to **Tools, then AI Provider Settings**
1. In the **Preferences** tab, find the **Custom Vocabulary** section
1. Add technical terms, acronyms, proper nouns, and specialized jargon - one per
   line
1. The vocabulary is automatically injected into AI prompts when translating or
   summarizing

**Examples:**

- Medical: "HIPAA", "myocardial infarction", "CBC panel"
- Legal: "habeas corpus", "voir dire", "amicus curiae"
- Technical: "Kubernetes", "WebSocket", "OAuth 2.0"

### Prompt Templates

BITS Whisperer includes 10 built-in prompt templates for common AI tasks:

#### Translation Templates (4)

| Template                  | Description                                          |
| ------------------------- | ---------------------------------------------------- |
| **Standard Translation**  | Preserves speaker labels, timestamps, and formatting |
| **Informal Translation**  | Natural, conversational tone; adapts idioms          |
| **Technical Translation** | Precise terminology for technical/medical content    |
| **Legal Translation**     | Verbatim formal translation for legal proceedings    |

#### Summarization Templates (4)

| Template             | Description                                             |
| -------------------- | ------------------------------------------------------- |
| **Concise Summary**  | Brief 3-5 sentence overview with key takeaways          |
| **Detailed Summary** | Comprehensive summary with speaker contributions        |
| **Bullet Points**    | Organized bullet list of key points and decisions       |
| **Meeting Minutes**  | Formal minutes with attendees, agenda, and action items |

#### Analysis Templates (2)

| Template               | Description                                      |
| ---------------------- | ------------------------------------------------ |
| **Sentiment Analysis** | Emotional tone per speaker with shift detection  |
| **Extract Questions**  | Lists all questions with answers and attribution |

Select a template before translating or summarizing in **Tools, then AI Provider
Settings**. You can also create custom templates.

### Multi-Language Simultaneous Translation

Translate a transcript into multiple languages at once:

1. Go to **Tools, then AI Provider Settings**
1. In the **Preferences** tab, configure multiple target languages
1. Press **Ctrl+T** to translate - each target language is translated
   independently
1. Results are returned as separate translations per language

This is ideal for creating multilingual documentation, subtitles, or
distributing transcripts to international teams.

### Real-Time Streaming Transcription

Some cloud providers support real-time streaming for faster results:

| Provider              | Streaming | Notes                                          |
| --------------------- | --------- | ---------------------------------------------- |
| **Deepgram**          | Yes       | Live WebSocket streaming with smart formatting |
| **AssemblyAI**        | Yes       | Real-time streaming with speaker detection     |
| Other cloud providers | No        | Standard batch processing                      |

______________________________________________________________________

## AI Actions

AI Actions automatically process your transcript through AI after transcription
completes - no manual step required. Choose an AI Action when adding files, and
the result appears alongside your transcript.

### How It Works

1. **Add files** via **File, then Add Files** (Ctrl+O) or **File, then Add Folder**
   (Ctrl+Shift+O)
1. **Select an AI Action** from the dropdown in the Add File Wizard
1. **Start transcription** - the file is transcribed normally
1. **AI processes automatically** - after transcription, AI analyzes the
   transcript using your chosen template
1. **View results** - the AI Action result appears below the transcript in the
   transcript panel

### Built-in Presets

BITS Whisperer includes 6 ready-to-use AI Action presets:

| Preset                | What It Does                                                                 |
| --------------------- | ---------------------------------------------------------------------------- |
| **Meeting Minutes**   | Generates formal meeting minutes with attendees, decisions, and action items |
| **Action Items**      | Extracts to-do items, deadlines, and assigned responsibilities               |
| **Executive Summary** | Creates a brief executive overview highlighting key points and decisions     |
| **Interview Notes**   | Identifies key discussion points, recurring themes, and notable quotes       |
| **Lecture Notes**     | Structures educational content into organized notes for study and review     |
| **Q&A Extraction**    | Identifies and pairs all questions with their answers                        |

### Creating Custom AI Actions

Use the AI Action Builder to create your own templates:

1. Go to **AI, then AI Action Builder**
1. Configure across 5 tabs:
   - **Identity** — Name your action and add a description
   - **Instructions** — Write custom processing instructions or start from a
     preset
   - **Tools** — Enable transcript-aware tools
   - **Welcome** — Set a greeting message
   - **Attachments** — Attach reference documents to provide extra context for
     AI processing
1. Click **Save** to store the template
1. Your custom action appears in the Add File Wizard dropdown (marked with ★)

### Attaching Reference Documents

The **Attachments** tab lets you attach external documents - glossaries, style
guides, meeting agendas, or any reference material - that the AI will consider
alongside your transcript.

1. In the AI Action Builder, switch to the **Attachments** tab
1. Click **Add File...** to browse for documents (multi-select supported)
1. Supported formats: Word (.docx), PDF (.pdf), Excel (.xlsx/.xls), RTF (.rtf),
   and plain text (.txt, .md, .csv, .log, .json, .xml, .yaml)
1. When you add a file, you'll be prompted for optional per-attachment
  instructions - for example:
   - "Use this as a glossary of technical terms"
   - "Cross-reference dates and names with this agenda"
   - "Follow the formatting rules in this style guide"
1. Use **Edit Instructions...** to update instructions for any attachment later
1. Use **Remove** to delete an attachment from the template
1. File size limit: 10 MB per attachment

Attachments are saved with the template and automatically read when the AI
action runs. The extracted text is injected between the system instructions and
the transcript in the AI prompt, with per-file headers and instructions
preserved.

> **Tip**: Attachments work with any AI provider. For best results, keep
> attachments concise - the AI's context window must fit the instructions,
> attachments, and transcript together. BITS Whisperer automatically adjusts the
> transcript budget to accommodate attachment content.

### Viewing AI Action Results

After transcription and AI processing complete:

- **Transcript Panel** — An "AI Action Result" section appears below the
  transcript text with the full AI output and a **Copy** button
- **Queue Panel** — Status indicators show progress:
  - ⭐ Action pending (transcription not yet started)
  - ⏳ AI Action running
  - ✓ AI Action completed
  - ✗ AI Action failed

### AI Action Providers

AI Actions work with **any configured AI provider** — OpenAI, Anthropic, Azure
OpenAI, Google Gemini, GitHub Copilot, or Ollama. The action uses whichever
provider is set as your default in AI Provider Settings.

> **Tip**: For best results with Meeting Minutes and Action Items, use a model
> with a large context window (GPT-4o, Claude, or Gemini Flash) to handle long
> transcripts. BITS Whisperer automatically fits transcripts to each model's
> context window — larger windows mean less content is omitted from very long
> recordings.

______________________________________________________________________

## GitHub Copilot Integration

BITS Whisperer includes GitHub Copilot for interactive transcript chat and
other AI-assisted tasks. You can ask questions about a transcript, get
summaries, and build custom AI actions without leaving the app.

### Copilot Setup Wizard

Before using Copilot features, complete the guided setup:

1. Go to **AI, then Copilot Setup**
1. The wizard prepares Copilot in the background while guiding you through the
  choices that matter:

| Step | What Happens |
| ---- | ------------ |
| **1. Prepare Copilot** | BITS Whisperer checks for the required Copilot components and installs or updates them automatically when needed. |
| **2. Sign In with GitHub** | Use the browser-based sign-in path. BITS Whisperer opens GitHub, gives you a short code if needed, and stores the sign-in securely for Copilot use. |
| **3. Other Sign-In Options** | If browser sign-in is not working, open **Other sign-in options** and use a GitHub access token as a fallback. |
| **4. Choose Plan & Model** | Pick your Copilot plan and a default model so the app can show the right options for your account. |
| **5. Test Connection** | The app runs a live connection test and confirms that transcript chat is ready to use. |

### Browser Sign-In Is the Standard Path

BITS Whisperer treats browser sign-in as the normal Copilot setup path.

Why this is recommended:

1. You sign in directly with GitHub instead of pasting secrets into the app.
1. It is easier for most users than creating a token manually.
1. It is the clearest setup path for screen reader and keyboard users.

If sign-in stalls, times out, or fails, the sign-in dialog gives you direct
**Retry** and **Close** actions so you can recover without starting over from
the main window.

### Manual Token Fallback

If you cannot complete browser sign-in, open **Other sign-in options** inside
Copilot Setup.

Use this only when needed:

1. Open the fallback section.
1. Create a GitHub access token.
1. Paste it into the token field.
1. Choose **Save and Verify Token**.

Most users should not need this fallback path.

> **Tip**: BITS Whisperer manages the Copilot components for you. Most users do
> not need to install or launch anything separately.

> **Copilot Free**: GitHub Copilot Free works in BITS Whisperer as long as your
> GitHub account is eligible and signed in successfully. GitHub applies lower
> monthly limits to Free accounts, so long chat sessions or repeated retries may
> exhaust your allowance sooner than on paid plans.

### Interactive AI Chat Panel

The chat panel lets you have a conversation with AI about your transcript:

#### Opening the Chat Panel

- **Keyboard**: Press **Ctrl+Shift+C**
- **Menu**: Go to **AI, then Copilot Chat**
- The panel appears alongside your transcript viewer

#### Using the Chat Panel

1. **Select a provider** — choose from configured AI providers in the dropdown
   (e.g., Copilot, OpenAI, Ollama)
1. **Select a model** — for Ollama, the model list is dynamically populated from
   your downloaded models; for other providers, models are preset. Your model
   choice is per-session and not persisted to settings.
1. **Manage Models…** - click this button to open Manage Models for
   downloading, deleting, or inspecting available models
1. **Type a question** in the input field at the bottom (e.g., "What are the
   main topics discussed?")
1. **Press Enter** or click **Send** to submit your question
1. **Watch the response stream** in real time - the AI replies as it writes
1. **Continue the conversation** - ask follow-up questions; context is
   maintained
1. **Start fresh** - click **Clear Chat** to remove the current conversation
  after confirmation and begin again

If no AI provider is ready yet, the chat panel explains what to configure next
and keeps the input disabled until a provider is available.

When Copilot is not ready yet, the fastest path is **AI, then Copilot Setup**.
If you want to use OpenAI, Anthropic, Gemini, Azure OpenAI, or Ollama instead,
open **Tools, then AI Provider Settings**.

#### Quick Actions

One-click buttons for common tasks appear at the top of the chat panel:

| Action           | What It Does                                        |
| ---------------- | --------------------------------------------------- |
| **Summarize**    | Generates a summary of the current transcript       |
| **Key Points**   | Extracts the main takeaways                         |
| **Speakers**     | Identifies and describes speakers in the transcript |
| **Action Items** | Lists action items or tasks mentioned               |
| **Questions**    | Generates discussion questions based on the content |

#### Transcript Context

The chat panel automatically sends your current transcript to the selected AI
provider as context. When you switch transcripts, the chat uses the new one.
You do not need to copy and paste the transcript yourself.

BITS Whisperer automatically manages context windows for every AI model.
Transcripts are intelligently fitted to each model’s token limit using
configurable strategies:

| Strategy            | Behavior                                                                                        |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| **Smart** (default) | Automatically chooses truncate or head+tail based on how much the transcript exceeds the budget |
| **Truncate**        | Keeps the beginning of the transcript                                                           |
| **Tail**            | Keeps the end of the transcript (useful for recent context)                                     |
| **Head + Tail**     | Keeps the beginning and end, omitting the middle with a marker                                  |

The status bar shows your current context budget (e.g., “Context: 45K/128K
tokens (35%)”). Use the `/context` slash command to see a detailed budget
breakdown including model, strategy, transcript tokens, and headroom.

Context window settings can be adjusted in **AI Provider Settings**:

| Setting                    | Default      | Description                                                   |
| -------------------------- | ------------ | ------------------------------------------------------------- |
| **Strategy**               | Smart        | How transcripts are fitted to the context window              |
| **Transcript budget**      | 70%          | Percentage of the context window allocated to transcript text |
| **Response reserve**       | 4,096 tokens | Tokens reserved for the AI’s response                         |
| **Max conversation turns** | 20           | Maximum chat turns kept in history                            |

#### Slash Commands

Type `/` in the chat input to access slash commands - shortcuts for AI
analysis, app actions, and template execution. An autocomplete popup appears as
you type, with keyboard navigation (Up/Down to select, Tab/Enter to accept,
Escape to dismiss).

**AI Commands** (require a loaded transcript unless noted):

| Command                 | Aliases                     | Description                                                   |
| ----------------------- | --------------------------- | ------------------------------------------------------------- |
| `/summarize [style]`    | `/sum`, `/summary`          | Summarize the transcript (styles: concise, detailed, bullets) |
| `/translate [language]` | `/trans`, `/tr`             | Translate the transcript to a target language                 |
| `/key-points`           | `/kp`, `/keypoints`         | Extract key points and takeaways                              |
| `/action-items`         | `/ai`, `/actions`, `/todos` | Extract action items, tasks, and follow-ups                   |
| `/topics`               |                             | Identify the main topics discussed                            |
| `/speakers`             |                             | Identify and describe each speaker                            |
| `/search <query>`       |                             | Search the transcript for specific content                    |
| `/ask <question>`       |                             | Ask a freeform question (no transcript required)              |
| `/run [template]`       |                             | Run an AI action template (lists available if no arg)         |
| `/copy`                 |                             | Copy the last AI response to the clipboard                    |

**App Commands:**

| Command            | Aliases              | Description                                             |
| ------------------ | -------------------- | ------------------------------------------------------- |
| `/help`            | `/?`, `/commands`    | Show all available slash commands                       |
| `/clear`           |                      | Clear the conversation history                          |
| `/status`          |                      | Show queue status and current provider info             |
| `/provider [id]`   |                      | Switch AI provider or show current one                  |
| `/export [format]` |                      | Export transcript (txt, md, html, docx, srt, vtt, json) |
| `/open`            | `/add`               | Open file picker to add audio files                     |
| `/open-folder`     | `/folder`            | Open folder picker to add a folder                      |
| `/start`           | `/go`, `/transcribe` | Start transcription of pending jobs                     |
| `/pause`           | `/resume`            | Pause or resume transcription                           |
| `/cancel`          | `/stop`              | Cancel the current transcription job                    |
| `/clear-queue`     |                      | Remove all jobs from the queue                          |
| `/retry`           |                      | Retry all failed jobs                                   |
| `/settings`        | `/config`, `/prefs`  | Open AI provider settings                               |
| `/live`            | `/mic`               | Open live microphone transcription                      |
| `/models`          |                      | Open the Whisper model manager                          |
| `/agent`           | `/builder`           | Open the AI Action Builder                              |
| `/history`         |                      | Show conversation statistics                            |
| `/context`         | `/ctx`, `/budget`    | Show context window budget and transcript fit info      |

> **Tip**: Type `/help` at any time to see the full command list with
> descriptions.

### AI Action Builder

Customize AI behavior and create reusable post-transcription processing
templates:

1. Go to **AI, then AI Action Builder**
1. Configure across 5 tabs:

| Tab              | What You Configure |
| ---------------- | ------------------ |
| **Identity**     | Action name (for example, "Meeting Analyst") and a short description |
| **Instructions** | System prompt with 8 built-in presets, or your own custom instructions |
| **Tools**        | Whether the action can search and inspect the transcript directly |
| **Welcome**      | The greeting shown when the action opens in chat |
| **Attachments**  | Reference documents and optional per-file instructions |

1. Click **Save** to apply your configuration. Saved templates appear in the AI
   Action dropdown when adding files (marked with ★) and persist between
   sessions.

> **Tip**: Templates are saved as JSON files in your app data folder and can be
> shared with colleagues.

### Copilot Settings

Fine-tune Copilot behavior in **Tools, then Settings**:

| Setting          | Default     | Description |
| ---------------- | ----------- | ----------- |
| Enabled          | Off         | Master toggle for Copilot features |
| Sign-in Method   | Browser     | Use browser sign-in with GitHub or a stored GitHub access token |
| Default Model    | gpt-4o      | AI model for chat responses |
| Streaming        | On          | Show responses as they arrive |
| Managed Runtime  | On          | Let the SDK start and manage the Copilot runtime automatically |
| Custom Runtime Path | Empty     | Optional override if you need to point to a specific Copilot runtime |
| Transcript Tools | On          | Allow the agent to access transcript data |

______________________________________________________________________

## Plugins

Extend BITS Whisperer with custom transcription providers via the plugin system.

### Creating a Plugin

1. Create a `.py` file in the plugins directory
1. Implement a `register(manager)` function that receives the `ProviderManager`:

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
1. Restart BITS Whisperer — plugins are loaded automatically on startup

### Managing Plugins

1. Go to **Tools, then Plugins**
1. View all discovered plugins with name, version, author, and status
1. Enable or disable individual plugins
1. Disabled plugins will not be loaded on next startup

### Plugin Metadata

Plugins can include optional metadata constants:

| Constant             | Description       |
| -------------------- | ----------------- |
| `PLUGIN_NAME`        | Display name      |
| `PLUGIN_VERSION`     | Version string    |
| `PLUGIN_AUTHOR`      | Author name       |
| `PLUGIN_DESCRIPTION` | Short description |

______________________________________________________________________

## Watch Folder

The Watch Folder feature automatically monitors a directory for new audio files
and queues them for transcription without manual intervention.

### Enabling Watch Folder

1. Go to **Tools, then Watch Folder**
1. Check **Enable Watch Folder**
1. Click **Browse** to select the folder to monitor
1. Configure optional overrides (provider, model, language)
1. Click **OK** to save

### Settings

| Setting                   | Description                                          | Default       |
| ------------------------- | ---------------------------------------------------- | ------------- |
| Enable Watch Folder       | Turn monitoring on or off                            | Off           |
| Watch Directory           | Folder path to monitor for new audio files           | (none)        |
| Include Subfolders        | Scan subdirectories recursively                      | No            |
| Process Existing Files    | Queue files already present when monitoring starts   | No            |
| Provider Override         | Override the default transcription provider          | (app default) |
| Model Override            | Override the default model                           | (app default) |
| Language Override         | Override the default language                        | (app default) |
| Poll Interval (seconds)   | How often to check for new files                     | 10            |

### Supported Audio Formats

Watch Folder detects files with these extensions:
`.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac`, `.wma`, `.opus`, `.webm`,
`.mp4`, `.avi`, `.mkv`, `.mov`

### How It Works

- Monitoring runs in a background thread with a configurable polling interval
- New files must be at least 3 seconds old to avoid picking up partially
  written files
- Empty files (0 bytes) are ignored
- Each file is processed only once per session — duplicates are tracked
  automatically
- When a file is detected, a transcription job is created using either the
  watch folder overrides or the app's default provider/model/language settings

### Auto-Start

If Watch Folder is enabled and a valid directory is configured, monitoring
starts automatically when the application launches.

### Keyboard Shortcut

There is no dedicated shortcut — access via **Tools, then Watch Folder**.

______________________________________________________________________

## Do Not Disturb

BITS Whisperer can detect your operating system's Do Not Disturb (DND) or Focus
Assist status and automatically pause transcription to avoid interruptions.

### How It Works

- **Windows**: Detects Focus Assist mode via the Windows API
- **macOS**: Detects DND status via system preferences

When DND is active, BITS Whisperer can automatically pause transcription and
live microphone capture. When DND ends, work resumes automatically.

### Settings

Configure DND behaviour in **Settings**:

| Setting                      | Default | Description                                         |
| ---------------------------- | ------- | --------------------------------------------------- |
| Enable DND detection         | Off     | Master toggle for DND awareness                     |
| Pause transcription          | On      | Pause queued transcription jobs when DND is active  |
| Pause live transcription     | On      | Pause live microphone capture when DND is active    |
| Auto-resume when DND ends    | On      | Automatically resume paused work when DND turns off |

______________________________________________________________________

## Scheduled Transcription

Schedule transcription jobs to run at specific times or on a recurring basis.
The scheduler is DND-aware — jobs can be deferred while Focus Assist is active.

### Creating a Schedule

1. Add files to the queue as normal
1. Configure a schedule with start time, optional recurrence, and DND rules
1. The scheduler runs in the background and starts jobs at the configured time

### Schedule Options

| Option             | Description                                          |
| ------------------ | ---------------------------------------------------- |
| **Start time**     | When to begin transcription                          |
| **Recurrence**     | One-time, daily, weekly, or custom interval          |
| **DND-aware**      | Defer jobs while Focus Assist / DND is active        |
| **Auto-retry**     | Retry failed jobs on the next schedule run           |

> **Tip**: Use scheduled transcription with Watch Folder for fully automated
> workflows — new files are detected and transcribed on your preferred schedule.

______________________________________________________________________

## Transcription Providers

BITS Whisperer supports **18 transcription engines** across three categories:

### Local (Free, Offline)

| Provider           | Description                                                       | Key Required |
| ------------------ | ----------------------------------------------------------------- | :----------: |
| **Local Whisper**  | On-device AI (faster-whisper). Free, private, no internet needed. | No           |
| **Windows Speech** | Built-in Windows SAPI5/WinRT recognition.                         | No           |
| **Azure Embedded** | Microsoft offline speech engine.                                  | No           |
| **Vosk**           | Lightweight offline ASR (Kaldi). 20+ languages, 40-50 MB models.  | No           |
| **Parakeet**       | NVIDIA NeMo high-accuracy English ASR. 600M–1.1B param models.    | No           |

### Cloud (Paid, Online)

| Provider              | Speed          | Price/min | Free Tier   | Key Required |
| --------------------- | -------------- | --------- | ----------- | :----------: |
| **OpenAI Whisper**    | Fast           | $0.006    | —           | Yes          |
| **Google Speech**     | Fast           | $0.016    | 60 min/mo   | Yes          |
| **Google Gemini**     | Fast           | $0.0002   | Generous    | Yes          |
| **Azure Speech**      | Fast           | $0.017    | 5 hrs/mo    | Yes          |
| **Deepgram Nova-3**   | Very fast      | $0.013    | $200 credit | Yes          |
| **AssemblyAI**        | Fast           | $0.011    | —           | Yes          |
| **AWS Transcribe**    | Fast           | $0.024    | 60 min/mo   | Yes          |
| **Groq Whisper**      | 188x real-time | $0.003    | —           | Yes          |
| **Rev.ai**            | Fast           | $0.020    | —           | Yes          |
| **Speechmatics**      | Fast           | $0.016    | —           | Yes          |
| **ElevenLabs Scribe** | Fast           | $0.005    | —           | Yes          |
| **MAI-Transcribe-1**  | Fast           | $0.006    | —           | Yes          |

### Cloud + Audio Processing

| Provider     | Description                                                                         | Free Tier | Key Required |
| ------------ | ----------------------------------------------------------------------------------- | --------- | :----------: |
| **Auphonic** | Audio post-production (noise reduction, leveling, loudness) + Whisper transcription | 2 hrs/mo  | Yes          |

### Setting Up Cloud Providers

BITS Whisperer provides two ways to configure cloud providers:

#### Method 1: Add Provider Wizard (Recommended)

1. Go to **Tools, then Add Provider**.
1. Select a cloud provider from the dropdown (13 available).
1. Read the description and pricing information.
1. Enter your API key (and any auxiliary credentials like AWS Region).
1. Click **Validate & Activate** — the app tests your key with a real API call.
1. On success, the provider is activated and ready for transcription.

The Add Provider wizard validates every credential with a live API call before
activation. This catches typos, expired keys, and configuration issues
immediately.

#### Method 2: Settings Dialog

1. Go to **Tools, then Settings, then Providers and Keys** (or during the Setup
   Wizard).
1. Enter your API key for the desired service.
1. Click the **Test** button to validate the key.
1. Keys are stored in your OS credential vault (Windows Credential Manager /
   macOS Keychain).

> **Note**: In Basic mode, only activated cloud providers appear in the provider
> dropdown. Use Add Provider to activate them, or switch to Advanced mode to see
> all providers.

### Choosing a Provider

- **Privacy first**: Local Whisper (your audio never leaves your computer)
- **Best English accuracy**: Parakeet TDT 1.1B (local) or Large v3 (local) or
  OpenAI Whisper (cloud)
- **Cheapest cloud**: Gemini ($0.0002/min) or Groq ($0.003/min)
- **Fastest cloud**: Groq (188x real-time) or Deepgram
- **Speaker labels**: Azure, Google, Deepgram, AssemblyAI, ElevenLabs, Rev.ai,
  Speechmatics, Amazon, Gemini (10 providers) or local pyannote.audio
- **Audio cleanup**: Auphonic (noise/hum removal + transcription)

______________________________________________________________________

## AI Models

BITS Whisperer includes **14 Whisper model variants** for local transcription:

| Model            | Size   | Speed  | Accuracy | Languages | Best For             |
| ---------------- | ------ | ------ | -------- | --------- | -------------------- |
| Tiny             | 75 MB  | 5 of 5 | 2 of 5   | 99        | Quick drafts         |
| Tiny (English)   | 75 MB  | 5 of 5 | 2 of 5   | EN only   | Fast English drafts  |
| Base             | 142 MB | 4 of 5 | 3 of 5   | 99        | Clear recordings     |
| Base (English)   | 142 MB | 4 of 5 | 3 of 5   | EN only   | English podcasts     |
| Small            | 466 MB | 3 of 5 | 4 of 5   | 99        | Most recordings      |
| Small (English)  | 466 MB | 3 of 5 | 4 of 5   | EN only   | English meetings     |
| Medium           | 1.5 GB | 2 of 5 | 4 of 5   | 99        | Important recordings |
| Medium (English) | 1.5 GB | 2 of 5 | 5 of 5   | EN only   | Professional English |
| Large v1         | 3 GB   | 1 of 5 | 5 of 5   | 99        | Professional work    |
| Large v2         | 3 GB   | 1 of 5 | 5 of 5   | 99        | Professional work    |
| Large v3         | 3 GB   | 1 of 5 | 5 of 5   | 99        | Best accuracy        |
| Large v3 Turbo   | 1.6 GB | 3 of 5 | 5 of 5   | 99        | Best value with GPU  |
| Distil Large v2  | 1.5 GB | 4 of 5 | 4 of 5   | EN only   | Fast English + GPU   |
| Distil Large v3  | 1.5 GB | 4 of 5 | 4 of 5   | EN only   | Fast English + GPU   |

### Managing Models

Open **Tools, then Manage Models** (Ctrl+M) to access the **Model Manager**.

The Model Manager uses a **tree view** organised by provider:

- **Whisper Models** — local transcription models (Tiny through Large v3)
- **Ollama Models** — locally downloaded LLMs for AI chat and actions

Each model shows its name, size, status, and a **rank score** indicating how
well it suits your hardware. Models are sorted by rank score (best fit first).

#### Model Details

Select a model and right-click (or press Shift+F10) to access the context menu:

| Action            | Description                                                                         |
| ----------------- | ----------------------------------------------------------------------------------- |
| **Download**      | Download the model (if not already downloaded)                                      |
| **Delete**        | Remove the model to free disk space                                                 |
| **View Details**  | Show full model metadata (size, family, quantization, recommended devices, version) |
| **Open Folder**   | Open the model's disk location in your file manager                                 |
| **Copy Model ID** | Copy the model identifier to the clipboard                                          |

You can also open the Model Manager from the **Manage Models…** button in the
AI Chat Panel or AI Provider Settings dialog.

### Hardware Requirements

The app automatically checks your hardware and classifies each model as:

- **Ready** — runs comfortably on your machine
- **Slow** — will work but may be slower than ideal
- **Too big** — won’t run (not enough RAM/GPU memory)

### Disk Space

Before each download, the app checks you have enough free disk space (with 10%
headroom). If you're low on space, you'll get a warning.

______________________________________________________________________

## Settings Overview

Open **Tools, then Settings** (Ctrl+,) for all configuration options.

### Tabs Overview

| Tab                  | What It Controls                                                                                                                                                       | Visibility    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| **General**          | Language, provider, model, registration, tray, notifications, updates                                                                                                  | Always        |
| **Transcription**    | Timestamps, speakers, VAD, temperature, beam size                                                                                                                      | Always        |
| **Output**           | Default format, directory, filename template, encoding                                                                                                                 | Always        |
| **Playback**         | Audio preview speed range, step size, and jump timing                                                                                                                  | Always        |
| **Budget**           | Spending limits, confirm paid, default limit, per-provider limits                                                                                                      | Always        |
| **Providers & Keys** | API keys for all cloud services with Test buttons                                                                                                                      | Always        |
| **Paths & Storage**  | Model directory, temp directory, log file                                                                                                                              | Always        |
| **AI Providers**     | AI provider (6 providers), model, temperature, max tokens, translation language, summarization style, Ollama connection mode, default chat model, Model Manager button | Always        |
| **Audio Processing** | 7-filter preprocessing chain                                                                                                                                           | Advanced only |
| **Advanced**         | File limits, concurrency, GPU settings, log level                                                                                                                      | Advanced only |

### Basic vs. Advanced Mode

**Basic Mode** (default):

- Shows 8 tabs: General, Transcription, Output, Playback, Budget, Providers &
   Keys, Paths & Storage, AI Providers
- Only local providers and **activated** cloud providers appear in the provider
  dropdown
- Use **Tools, then Add Provider** to activate cloud providers
- Recommended for everyday use

**Advanced Mode**:

- Shows all 9 tabs including Audio Processing and Advanced
- All cloud providers visible in the provider dropdown (activation not required)
- Full control over audio preprocessing, GPU settings, concurrency, and chunking
- Toggle via **View, then Advanced Mode** (Ctrl+Shift+A)

Your mode preference is saved between sessions. You can also set it in the Setup
Wizard.

______________________________________________________________________

## Audio Preprocessing

BITS Whisperer applies a 7-filter audio cleanup chain before transcription to
improve accuracy:

| Filter                 | Default    | What It Does                           |
| ---------------------- | :--------: | -------------------------------------- |
| High-pass              | 80 Hz      | Removes rumble and low-frequency noise |
| Low-pass               | 8 kHz      | Removes hiss and high-frequency noise  |
| Noise gate             | -40 dB     | Silences quiet background noise        |
| De-esser               | Off        | Reduces harsh "s" sounds               |
| Compressor             | -20 dB     | Evens out volume differences           |
| Loudness normalization | -16 LUFS   | Standardizes overall volume            |
| Silence trimming       | -40 dB, 1s | Removes long pauses                    |

Configure in **Settings, then Audio Processing**. Disable individual filters or
turn off the entire chain.

> **Note**: Auphonic does its own professional-grade audio processing in the
> cloud. If using Auphonic, you may want to disable local preprocessing.

______________________________________________________________________

## Queue Management

The transcription queue uses a **tree view** that organizes your files for easy
navigation and batch control.

### Queue Layout

- **Individual files** appear at the root level of the tree
- **Folders** appear as expandable branches — expand with arrow keys or
  double-click to see files inside
- Each item shows: **name — status — provider [— cost] [— AI action status]**
- Folders show a summary: **📁 FolderName (5 files — 2 done, 1 in progress)**

### Toolbar

Above the tree, a toolbar provides quick actions:

| Button             | Description                                  |
| ------------------ | -------------------------------------------- |
| **▶ Start**        | Start transcribing all pending jobs (F5)     |
| **✓ Clear Done**   | Remove all completed jobs from the queue     |
| **↻ Retry Failed** | Re-queue all failed jobs for another attempt |

### Filter Bar

Below the toolbar, a **filter bar** lets you search the queue:

- Type any text to filter by file name, custom name, provider, or status
- Matching items are **bolded**; non-matching items are dimmed
- Press the **✕** button or clear the text to show all items
- The status bar announces how many items match your filter

### Context Menus

**Right-click a file** (or press Shift+F10 / Apps key) to access:

- **View Transcript** — Open the transcript tab (Enter)
- **Rename** — Set a custom display name (F2)
- **Start Transcription** — Begin this job (F5, pending only)
- **Retry Job** — Re-queue a failed job (Ctrl+R)
- **Change Provider** — Switch to a different transcription provider
- **Change Model** — Select a different model for the provider
- **Change Language** — Set the transcription language
- **Include Diarization** — Toggle speaker identification
- **AI Action** — Choose which AI action template to run after transcription
  (built-in presets and custom templates)
- **File Operations** — Copy file path (Ctrl+C) or open file location (Ctrl+L)
- **Cancel / Remove** — Cancel an active job (Delete) or remove from queue
- **Properties** — View file details, provider, model, cost, and status

**Right-click a folder** to access:

- **Rename** — Set a custom folder name
- **Start All Pending / Retry All Failed / Cancel All Active** — Batch
  operations on the folder's files
- **Set AI Action for Pending** — Apply an AI action template to all pending
  files in the folder
- **Expand All / Collapse** — Control folder tree display
- **Copy Folder Path / Open Folder** — File system operations
- **Remove Folder** — Remove the folder and all its files from the queue
- **Properties** — View file count, total size, and status breakdown

**Right-click empty space** to access:

- **Add Files / Add Folder** — Queue new audio
- **Start All / Clear Completed / Retry All Failed** — Queue-wide batch
  operations
- **Clear Entire Queue** — Remove everything (Ctrl+Shift+Delete)

### Queue Custom Names

Rename any job or folder without changing files on disk:

1. Select an item and press **F2**, or right-click and choose **Rename**
1. Enter a custom name in the dialog — this name appears in the queue and
   transcript panel
1. Leave blank to restore the original file or folder name

### Drag and Drop

Drag audio files from your file manager directly onto the queue panel. Folders
can also be dropped — all supported audio files inside will be added
recursively.

### Status Indicators

| Icon       | Meaning                           |
| ---------- | --------------------------------- |
| ⭐         | Pending with AI action configured |
| ⏳         | AI action in progress             |
| ✓          | AI action completed               |
| ✗          | AI action failed                  |
| Green text | Transcription completed           |
| Red text   | Transcription failed              |
| Blue text  | Currently transcribing            |

### Budget Limits

Control spending on paid cloud providers:

1. Go to **Settings**, then **General**
1. Enable **Budget Limits** and set a default spending limit
1. Optionally set per-provider limits for fine-grained control
1. Enable **Always Confirm Paid** to see a cost confirmation dialog before each
   paid transcription
1. Cost estimates appear in the queue next to each job — format: `$0.05` for
   estimates, `~$0.05` for approximate costs

______________________________________________________________________

## System Tray

BITS Whisperer can minimize to the system tray for background processing:

- **Close with tray enabled**: the app minimizes to tray instead of quitting
- **Tray icon menu**: right-click for Show, Start, Pause, Settings, Quit
- **Notifications**: desktop balloon notifications when transcription completes
- **Configure**: Settings, then General, then "Minimize to system tray"

______________________________________________________________________

## View Menu Features

### Font Size Adjustment

Adjust the transcript font size for comfortable reading:

- **Increase Font Size**: Ctrl+= (or View, then Increase Font Size)
- **Decrease Font Size**: Ctrl+- (or View, then Decrease Font Size)
- **Reset Font Size**: Ctrl+0 (or View, then Reset Font Size)

Font size ranges from 6pt to 36pt. Changes are announced to screen readers.
The font size persists until reset.

### Do Not Disturb Status

Check the current DND / Focus Assist status from **View, then Do Not Disturb
Status**. A dialog shows whether DND is active, the current mode, and the
detection source.

### Transcript Statistics

When a transcript is displayed, word count, character count, and segment count
appear below the transcript metadata.

______________________________________________________________________

## Settings Management

### Import & Export

Back up or migrate your settings between machines:

- **Export**: Click **Export…** in the Settings dialog to save all settings to
  a JSON file
- **Import**: Click **Import…** to load settings from a previously exported
  JSON file

### Reset to Defaults

Click **Reset to Defaults** in the Settings dialog to restore all settings to
their factory defaults. A confirmation dialog prevents accidental resets.

______________________________________________________________________

## Keyboard Shortcuts Reference

Press **Ctrl+Shift+K** or go to **Help, then Keyboard Shortcuts** to open the
Keyboard Shortcuts Reference dialog. This searchable dialog lists all 35+
keyboard shortcuts organized into 7 categories (File, Queue, Transcript, AI,
Tools, Navigation, Help). Type in the search box to filter shortcuts in
real time.

______________________________________________________________________

## Keyboard Shortcuts

| Shortcut       | Action                        |
| -------------- | ----------------------------- |
| Ctrl+O         | Add files                     |
| Ctrl+Shift+O   | Add folder                    |
| Ctrl+E         | Export transcript             |
| Ctrl+S         | Save (manual save)            |
| Ctrl+,         | Open Settings                 |
| Ctrl+M         | Manage Models                 |
| Ctrl+Shift+A   | Toggle Advanced Mode          |
| Ctrl+Alt+L     | Live Transcription            |
| Ctrl+T         | Translate Transcript          |
| Ctrl+Shift+S   | Summarize Transcript          |
| Ctrl+Shift+P   | Audio Preview                 |
| Ctrl+Alt+P     | Preview Selected (Queue)      |
| Ctrl+Shift+C   | Copilot Chat Panel            |
| Ctrl+Shift+K   | Keyboard Shortcuts Reference  |
| Ctrl+=         | Increase Font Size            |
| Ctrl+-         | Decrease Font Size            |
| Ctrl+0         | Reset Font Size               |
| F5             | Start transcription           |
| Ctrl+P         | Pause / Resume transcription  |
| F2             | Rename selected item          |
| F3             | Find next in transcript       |
| Ctrl+F         | Find in transcript            |
| Ctrl+C         | Copy file path (in queue)     |
| Ctrl+R         | Retry selected job (in queue) |
| Ctrl+L         | Open file location (in queue) |
| Ctrl+W         | Toggle Watch Folder           |
| Ctrl+Shift+Del | Clear entire queue            |
| Delete         | Cancel or remove selected job |
| Alt+F          | File menu                     |
| Alt+Q          | Queue menu                    |
| Alt+V          | View menu                     |
| Alt+T          | Tools menu                    |
| Alt+A          | AI menu                       |
| Alt+H          | Help menu                     |
| Ctrl+Shift+L   | Licence management            |

All menu items have keyboard mnemonics (underlined letters) for quick access.

______________________________________________________________________

## Registration & Licensing

### First Launch — Welcome Dialog

On first launch (or when no licence or trial is active) you will see
the Welcome dialog with three options:

1. **Start a 7-Day Trial** — enter your name and email; a hardware
   token is generated automatically and sent with the trial
   registration.
2. **Register** — enter an existing registration key. The key
   contains your name and licence type, verified cryptographically.
3. **Exit** — close the application without activating.

### Trial

- The trial lasts **7 days** from the moment it is started.
- During the trial, all features are available.
- The trial cannot be restarted on the same device.
- When the trial expires, you must register with a licence key.

### Licence Types

| Code | Type         | Duration       |
| ---- | ------------ | -------------- |
| L    | Lifetime     | Never expires  |
| A    | Annual       | 365 days       |
| C    | Contributor  | Never expires  |
| T    | Alpha Tester | Never expires  |

### Licence Management (Help → Licence, Ctrl+Shift+L)

The Licence dialog shows:

- **Status** — current licence status with personalised greeting
- **Registered name** — decoded from the signed licence token
- **Email** — the email associated with the licence
- **Licence type** — Lifetime, Annual, Contributor, or Trial
- **Device ID** — this machine's hardware fingerprint
- **Installations** — how many of the 3 allowed device slots are used

Actions available:

- **Register** — enter a new registration key
- **Purchase Licence** — opens the purchase page in your browser
- **Revoke This Device** — frees a device slot so you can register
  on a different machine (cannot be undone)

### About Dialog (Help → About, F1)

The About dialog now shows licence status, registered name,
installation count, and trial days remaining (if applicable).

### Security

- Registration keys are verified with **Ed25519 cryptographic
  signatures** — keys cannot be forged or modified.
- The user's name is embedded in the signed licence token and
  extracted client-side for the personalised greeting.
- Hardware fingerprinting uses multiple factors (MAC address,
  platform, CPU, user profile) to prevent device spoofing.
- API keys and registration data are stored in the **OS credential
  store** (Windows Credential Manager / macOS Keychain).
- A **3-device limit** is enforced server-side per licence key.
- Verification uses **certificate-pinned HTTPS** to prevent
  man-in-the-middle attacks.
- Offline verification falls back to a **7-day cache**.

______________________________________________________________________

## Updates, Release Notes & Beta Programme

### Checking for Updates

BITS Whisperer can check GitHub for a newer version.

1. Open **Help, then Check for Updates**.
1. If a newer version is available, follow the prompt to download it.
1. If no update is available, the app tells you that you are up to date.

You can also leave update checks enabled in Settings so BITS Whisperer checks
automatically on startup.

### What's New

Use **Help, then What's New** to review recent feature changes and release
notes.

The What's New dialog can:

1. Show release notes for recently enabled or changed features.
1. Open automatically after updates if you leave it enabled.
1. Help you understand which new features are available before you go looking
   through menus.

### Beta Programme

Use **Help, then Beta Programme** to join or manage the beta testing programme.

The beta programme is useful if you want:

1. Early access to selected features.
1. Release notes for features still being rolled out.
1. Control over whether What's New appears automatically.

Some features may appear first for beta testers before they are enabled for all
users.

______________________________________________________________________

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

______________________________________________________________________

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
- Keys are validated on save — the app will confirm whether the key is valid or
  invalid
- Some services require billing to be enabled before the API works
- Re-generate the key on the provider's website if needed

### "Application won't start"

- Check the log file at: `%LOCALAPPDATA%\BITS Whisperer\app.log` (Windows) or
  `~/Library/Application Support/BITS Whisperer/app.log` (macOS)
- Delete `settings.json` to reset to defaults (same directory)
- Reinstall if the issue persists

### "ffmpeg not found"

- BITS Whisperer will try to install ffmpeg automatically on first launch
- If automatic installation didn't work, install manually:
  - **winget**: `winget install Gyan.FFmpeg`
  - **Chocolatey**: `choco install ffmpeg`
  - **Manual**: Download from [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) and add the
    `bin` folder to your PATH
- Restart BITS Whisperer after installing ffmpeg

### "Slow transcription"

- Use a smaller model (Tiny or Base)
- Enable GPU acceleration if you have an NVIDIA GPU
- Close other applications to free up RAM
- Use a cloud provider for faster processing
- Enable audio preprocessing — cleaner audio transcribes faster

### "SDK installation failed"

- Check your internet connection — SDKs are downloaded from PyPI.
- Ensure you have enough disk space. Some SDKs (like Local Whisper) need ~220
  MB.
- Check the log file (**Tools, then View Log**) for detailed error messages.
- Try again — the download may have been interrupted by network issues.
- As a fallback, you can install the SDK manually:
  - Open a command prompt
  - Run:
    `pip install --target "%LOCALAPPDATA%\BITS Whisperer\BITSWhisperer\site-packages" <package-name>`
  - Restart BITS Whisperer

### "Provider not available after SDK install"

- Restart BITS Whisperer — some SDKs require a fresh start to load correctly.
- Check that the API key is configured in **Settings, then Providers and Keys**.
- View the log file for import errors: **Tools, then View Log**.

### Leftover Temporary Files

BITS Whisperer creates temporary files during audio preprocessing and
transcoding. These are cleaned up automatically when each job completes and
again during shutdown. If the app crashes or is force-killed, temporary files
with prefixes `bw_transcode_*`, `bw_preprocess_*`, or `bw_update_*` may remain
in your system temp directory (`%TEMP%` on Windows, `/tmp` on macOS). These are
safe to delete. On the next normal shutdown, BITS Whisperer will automatically
remove any stale temp files older than 1 hour.

### Resetting the App

To start fresh:

1. Delete the data directory:
   - Windows: `%LOCALAPPDATA%\BITS Whisperer\`
   - macOS: `~/Library/Application Support/BITS Whisperer/`
1. This removes settings, downloaded models, and the job database.
1. The Setup Wizard will appear again on next launch.

______________________________________________________________________

## FAQ

**Q: Is my audio sent to the internet?** A: Only if you use a cloud provider.
Local Whisper processes everything on your computer. Your audio files are never
uploaded without your explicit choice.

**Q: Do I need an internet connection?** A: No — once you've downloaded a local
model, BITS Whisperer works entirely offline. You only need internet to download
models or use cloud providers.

**Q: Which model should I use?** A: The Setup Wizard recommends one based on
your hardware. As a rule of thumb:

- **4 GB RAM, no GPU**: Base
- **8 GB RAM, no GPU**: Small
- **GPU with 4+ GB VRAM**: Large v3 Turbo
- **GPU with 6+ GB VRAM**: Large v3

**Q: How are my API keys stored?** A: Keys are stored in your operating system's
credential vault (Windows Credential Manager or macOS Keychain) — the same
system used by web browsers and other apps. They are never written to plain-text
files or logs.

**Q: Can I use multiple providers for different files?** A: Yes! You can set a
default provider and change it per file from the queue or Settings.

**Q: How much disk space do I need?** A: The app itself needs about 100 MB.
Models range from 75 MB (Tiny) to 3 GB (Large). Download only the models you
need — you can always add more later.

**Q: Does it work on macOS?** A: Yes! BITS Whisperer runs on Windows 10+ and
macOS 12+. Linux support is planned.

**Q: How do I update?** A: The app checks for updates on startup (configurable).
When an update is available, you'll be prompted to download it. You can also
check manually via **Help, then Check for Updates**.

______________________________________________________________________

*BITS Whisperer v1.0.0 — Developed by Blind Information Technology Solutions
(BITS). Made with care for accessibility and privacy.*
