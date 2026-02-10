# BITS Whisperer — User Guide

Welcome to **BITS Whisperer**, your desktop audio transcription companion. This
guide walks you through every feature so you can get the most out of the app.

______________________________________________________________________

## Table of Contents

1. [Getting Started](#getting-started)
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
1. [Providers](#providers)
1. [AI Models](#ai-models)
1. [Settings](#settings)
1. [Audio Preprocessing](#audio-preprocessing)
1. [Queue Management](#queue-management)
1. [System Tray](#system-tray)
1. [Keyboard Shortcuts](#keyboard-shortcuts)
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

BITS Whisperer uses a lightweight installer — provider SDKs (such as the OpenAI
client, Google Cloud libraries, or the faster-whisper AI engine) are **not
bundled** with the application. Instead, they are downloaded and installed
automatically the first time you use a provider.

When you start a transcription or download a local model, the app will:

1. Check if the required SDK is already installed.
1. If not, show a dialog explaining what will be downloaded and the approximate
   size.
1. Download the packages from PyPI and install them in a local folder managed by
   BITS Whisperer.
1. This only happens once per provider — subsequent uses are instant.

**No system Python or pip is required.** The app handles everything internally.

SDKs are stored in: `%LOCALAPPDATA%\BITS Whisperer\BITSWhisperer\site-packages\`
(Windows) or `~/Library/Application Support/BITS Whisperer/site-packages/`
(macOS).

______________________________________________________________________

## Setup Wizard

The setup wizard appears automatically on your first launch and walks you
through eight steps:

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
- Downloads happen in the background — you'll get a notification when each model
  is ready

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

### Step 6: AI & Copilot Configuration

Set up AI-powered features:

- **AI Provider** — Choose your preferred AI provider for translation and
  summarization (OpenAI, Anthropic, Azure OpenAI, Google Gemini, or GitHub
  Copilot)
- **API Keys** — Enter API keys for your chosen AI providers
- **GitHub Copilot** — Optionally install and configure GitHub Copilot CLI for
  interactive transcript chat
- **Models** — Select default AI models (GPT-4o, Claude, Gemini Flash)

> **Tip**: You can skip this step and configure AI providers later from **Tools,
> then AI Provider Settings**.

### Step 7: Summary

Review your choices and click **Finish** to start using the app.

### Step 8: Ready

> **Tip**: You can always re-configure everything from **Tools, then Settings**
> (Ctrl+,) or **Tools, then Manage Models** (Ctrl+M).

______________________________________________________________________

## Main Window

The main window has four areas:

| Area                                | Purpose                                      |
| ----------------------------------- | -------------------------------------------- |
| **Menu Bar**                        | All actions — File, Queue, View, Tools, Help |
| **File Queue** (left panel)         | Files waiting to be transcribed              |
| **Transcript Viewer** (right panel) | View/edit completed transcripts              |
| **Status Bar**                      | Current activity, provider, job count        |

### Splitter

A movable divider separates the queue and transcript panels. Drag it to resize,
or use **View, then Focus Queue / Focus Transcript** from the menu.

______________________________________________________________________

## Adding Files

### Methods

- **Drag & Drop** — drag audio files onto the window
- **File, then Add Files** (Ctrl+O) — opens the Add File Wizard for per-file
  configuration
- **File, then Add Folder** (Ctrl+Shift+O) — add all audio files in a folder
  with cost estimation
- **Recent Files** — re-open files from **File, then Recent Files**

### Add File Wizard

When you add files, the Add File Wizard lets you configure each job:

1. **Provider & Model** — Choose the transcription provider and model
1. **Language** — Select the transcription language or auto-detect
1. **Custom Name** — Optionally give the job a display name (appears in queue
   and exports)
1. **AI Action** — Choose an AI Action to run automatically after transcription
   (see [AI Actions](#ai-actions))
1. **Audio Preview (single file)** — Listen with pitch-preserving speed control
   with configurable jump timing and optionally select a time range to transcribe

For multiple files, the custom name is automatically numbered (e.g., "Interview
(1)", "Interview (2)").

You can also open the audio preview tool from **Tools, then Audio Preview**
(Ctrl+Shift+P) to listen before adding files.

### Adding Folders

When adding a folder, BITS Whisperer:

1. Recursively scans for supported audio files
1. Opens the Add File Wizard — configure provider, model, language, custom name,
   and **AI Action** for the entire batch
1. Estimates total cost for cloud providers with a confirmation dialog
1. Groups files under a collapsible folder node in the queue

The AI Action you select in the wizard applies to every file in the folder. You
can also change AI actions per-file or per-folder after import via right-click >
**AI Action**.

### Custom Names

Give files and folders meaningful names:

- **During import** — Enter a custom name in the Add File Wizard
- **After import** — Press **F2** or right-click > **Rename** to rename any file
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

- **Edit** — make corrections directly in the transcript viewer
- **Find** — use Ctrl+F to search within the transcript; F3 for Find Next
- **Timestamps** — shown inline if enabled in settings
- **Speakers** — speaker labels appear if the provider supports diarization

### Speaker Management

When speakers are detected, a **Speakers** bar appears above the transcript
showing all identified speakers.

#### Renaming Speakers

1. Click **Manage Speakers...** to open the rename dialog.
1. Replace generic IDs (Speaker 1, Speaker 2) with real names (Alice, Bob).
1. Click **OK** — all instances update instantly throughout the transcript.

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
automatically when done, in your chosen format and location.

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

- **Keyboard**: Press **Ctrl+L**
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

Use AI to translate and summarize your transcripts using OpenAI, Anthropic
Claude, Azure OpenAI, Google Gemini, GitHub Copilot, or Ollama (local).

### Setup

1. Go to **Tools, then AI Provider Settings**
1. In the **Providers** tab, enter your API key for at least one provider:
   - **OpenAI** — Get a key from <https://platform.openai.com/api-keys>
   - **Anthropic** — Get a key from <https://console.anthropic.com/>
   - **Azure OpenAI** — Enter your endpoint URL, deployment name, and API key
     from the Azure portal
   - **Google Gemini** — Get a key from <https://aistudio.google.com/apikey>
   - **GitHub Copilot** — See
     [GitHub Copilot Integration](#github-copilot-integration) for setup
   - **Ollama** — No API key needed! Install Ollama from <https://ollama.com>,
     pull a model (e.g., `ollama pull llama3.2`), and it works automatically
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
   - **Concise** — Brief overview (default)
   - **Detailed** — Comprehensive summary
   - **Bullet Points** — Key points as a list
1. A dialog shows the result with a **Copy** button

### Supported AI Providers

| Provider       | Models                                                                                                  | Notes                                         |
| -------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| OpenAI         | GPT-4o, GPT-4o Mini, GPT-4 Turbo, GPT-3.5 Turbo                                                         | Fastest, most reliable                        |
| Anthropic      | Claude Sonnet 4, Claude Haiku 4, Claude 3.5 Sonnet                                                      | Strong for long transcripts                   |
| Azure OpenAI   | Configurable deployment                                                                                 | Enterprise-grade, GDPR compliant              |
| Google Gemini  | Gemini 2.0 Flash, 2.5 Pro, 2.5 Flash + 5 Gemma models                                                   | Fast, very affordable                         |
| GitHub Copilot | 7 models (GPT-4o Mini, GPT-4o, GPT-4 Turbo, Claude Sonnet 4, Claude Haiku 4, o3-mini, Gemini 2.0 Flash) | Subscription-based, interactive chat          |
| Ollama         | Any model from Ollama library or HuggingFace GGUF (Llama, Mistral, Gemma, Phi, etc.)                    | Free, private, runs entirely on your computer |

### AI Model Catalog

BITS Whisperer includes a comprehensive AI model catalog with real-time pricing
for informed model selection. Access it via **Tools, then AI Provider
Settings**.

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

Copilot models are included in your subscription — no per-token charges:

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

Copilot model availability depends on your GitHub Copilot subscription tier. Set
your tier in **Tools, then Settings** to see only the models available for your
plan.

| Tier           | Price          | Models Available                                          |
| -------------- | -------------- | --------------------------------------------------------- |
| **Free**       | $0             | GPT-4o Mini                                               |
| **Pro**        | $10/month      | All 7 models (including premium: Claude, o3-mini, Gemini) |
| **Business**   | $19/user/month | All Pro models + organization admin controls              |
| **Enterprise** | $39/user/month | All models + knowledge bases, fine-tuning, compliance     |

### Custom Vocabulary

Improve AI accuracy for domain-specific content by adding custom terms:

1. Go to **Tools, then AI Provider Settings**
1. In the **Preferences** tab, find the **Custom Vocabulary** section
1. Add technical terms, acronyms, proper nouns, and specialized jargon — one per
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
1. Press **Ctrl+T** to translate — each target language is translated
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
completes — no manual step required. Choose an AI Action when adding files, and
the result appears alongside your transcript.

### How It Works

1. **Add files** via File > Add Files (Ctrl+O) or File > Add Folder
   (Ctrl+Shift+O)
1. **Select an AI Action** from the dropdown in the Add File Wizard
1. **Start transcription** — the file is transcribed normally
1. **AI processes automatically** — after transcription, AI analyzes the
   transcript using your chosen template
1. **View results** — the AI Action result appears below the transcript in the
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

The **Attachments** tab lets you attach external documents — glossaries, style
guides, meeting agendas, or any reference material — that the AI will consider
alongside your transcript.

1. In the AI Action Builder, switch to the **Attachments** tab
1. Click **Add File...** to browse for documents (multi-select supported)
1. Supported formats: Word (.docx), PDF (.pdf), Excel (.xlsx/.xls), RTF (.rtf),
   and plain text (.txt, .md, .csv, .log, .json, .xml, .yaml)
1. When you add a file, you'll be prompted for optional per-attachment
   instructions — for example:
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
> attachments concise — the AI's context window must fit the instructions,
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

BITS Whisperer integrates the GitHub Copilot SDK for interactive, AI-powered
transcript analysis. Chat with your transcripts, ask questions, get insights,
and configure custom AI agents — all without leaving the app.

### Copilot Setup Wizard

Before using Copilot features, complete the guided setup:

1. Go to **Tools, then Copilot Setup**
1. The wizard walks you through 4 steps:

| Step                  | What Happens                                                                                                                      |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **1. CLI Install**    | Checks if the GitHub Copilot CLI is installed. If not, offers to install it via WinGet (Windows) or provides manual instructions. |
| **2. SDK Install**    | Installs the Copilot SDK Python package into the BITS Whisperer environment.                                                      |
| **3. Authentication** | Authenticates with your GitHub account using the CLI device flow. Opens your browser for secure sign-in.                          |
| **4. Test**           | Runs a connection test to verify Copilot is working. You'll see a success message if everything is configured correctly.          |

> **Tip**: The Windows installer can optionally install the GitHub Copilot CLI
> via WinGet during application installation.

### Interactive AI Chat Panel

The chat panel lets you have a conversation with AI about your transcript:

#### Opening the Chat Panel

- **Keyboard**: Press **Ctrl+Shift+C**
- **Menu**: Go to **AI, then Copilot Chat**
- The panel appears alongside your transcript viewer

#### Using the Chat Panel

1. **Type a question** in the input field at the bottom (e.g., "What are the
   main topics discussed?")
1. **Press Enter** or click **Send** to submit your question
1. **Watch the response stream** in real time — Copilot replies token by token
1. **Continue the conversation** — ask follow-up questions; context is
   maintained
1. **Start fresh** — click **New Conversation** to clear history and begin again

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

The chat panel automatically provides your current transcript as context to the
AI agent. When you switch transcripts, the agent is updated with the new
content. No need to copy and paste — the agent always knows what transcript
you’re working with.

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

Type `/` in the chat input to access powerful slash commands — shortcuts for AI
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
1. Configure across 4 tabs:

| Tab              | What You Configure                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Identity**     | Action name (e.g., "Meeting Analyst") and a brief description                                                                                                                         |
| **Instructions** | System prompt with 8 built-in presets (Meeting Minutes, Action Items, Executive Summary, Interview Notes, Lecture Notes, Q&A Extraction, General Assistant, Custom) or write your own |
| **Tools**        | Enable or disable transcript-aware tools for direct transcript access                                                                                                                 |
| **Welcome**      | Set the greeting message for the chat panel                                                                                                                                           |

1. Click **Save** to apply your configuration. Saved templates appear in the AI
   Action dropdown when adding files (marked with ★) and persist between
   sessions.

> **Tip**: Templates are saved as JSON files in your app data folder and can be
> shared with colleagues.

### Copilot Settings

Fine-tune Copilot behavior in **Tools, then Settings**:

| Setting          | Default     | Description                                                 |
| ---------------- | ----------- | ----------------------------------------------------------- |
| Enabled          | Off         | Master toggle for Copilot features                          |
| CLI Path         | Auto-detect | Path to GitHub Copilot CLI (leave empty for auto-detection) |
| Default Model    | gpt-4o      | AI model for chat responses                                 |
| Streaming        | On          | Show responses token-by-token                               |
| Auto-start CLI   | On          | Automatically start the Copilot CLI process                 |
| Transcript Tools | On          | Allow the agent to access transcript data                   |

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

## Transcription Providers

BITS Whisperer supports **17 transcription engines** across three categories:

### Local (Free, Offline)

| Provider           | Description                                                       | Key Required |
| ------------------ | ----------------------------------------------------------------- | :----------: |
| **Local Whisper**  | On-device AI (faster-whisper). Free, private, no internet needed. |      No      |
| **Windows Speech** | Built-in Windows SAPI5/WinRT recognition.                         |      No      |
| **Azure Embedded** | Microsoft offline speech engine.                                  |      No      |
| **Vosk**           | Lightweight offline ASR (Kaldi). 20+ languages, 40-50 MB models.  |      No      |
| **Parakeet**       | NVIDIA NeMo high-accuracy English ASR. 600M–1.1B param models.    |      No      |

### Cloud (Paid, Online)

| Provider              | Speed          | Price/min | Free Tier   | Key Required |
| --------------------- | -------------- | --------- | ----------- | :----------: |
| **OpenAI Whisper**    | Fast           | $0.006    | —           |     Yes      |
| **Google Speech**     | Fast           | $0.016    | 60 min/mo   |     Yes      |
| **Google Gemini**     | Fast           | $0.0002   | Generous    |     Yes      |
| **Azure Speech**      | Fast           | $0.017    | 5 hrs/mo    |     Yes      |
| **Deepgram Nova-2**   | Very fast      | $0.013    | $200 credit |     Yes      |
| **AssemblyAI**        | Fast           | $0.011    | —           |     Yes      |
| **AWS Transcribe**    | Fast           | $0.024    | 60 min/mo   |     Yes      |
| **Groq Whisper**      | 188x real-time | $0.003    | —           |     Yes      |
| **Rev.ai**            | Fast           | $0.020    | —           |     Yes      |
| **Speechmatics**      | Fast           | $0.016    | —           |     Yes      |
| **ElevenLabs Scribe** | Fast           | $0.005    | —           |     Yes      |

### Cloud + Audio Processing

| Provider     | Description                                                                         | Free Tier | Key Required |
| ------------ | ----------------------------------------------------------------------------------- | --------- | :----------: |
| **Auphonic** | Audio post-production (noise reduction, leveling, loudness) + Whisper transcription | 2 hrs/mo  |     Yes      |

### Setting Up Cloud Providers

BITS Whisperer provides two ways to configure cloud providers:

#### Method 1: Add Provider Wizard (Recommended)

1. Go to **Tools, then Add Provider**.
1. Select a cloud provider from the dropdown (12 available).
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

Before each download, the app checks you have enough free disk space (with 10%
headroom). If you're low on space, you'll get a warning.

______________________________________________________________________

## Settings Overview

Open **Tools, then Settings** (Ctrl+,) for all configuration options.

### Tabs Overview

| Tab                  | What It Controls                                                                       | Visibility    |
| -------------------- | -------------------------------------------------------------------------------------- | ------------- |
| **General**          | Language, provider, model, tray, notifications, updates                                | Always        |
| **Transcription**    | Timestamps, speakers, VAD, temperature, beam size                                      | Always        |
| **Output**           | Default format, directory, filename template, encoding                                 | Always        |
| **Playback**         | Audio preview speed range, step size, and jump timing                                  | Always        |
| **Providers & Keys** | API keys for all cloud services with Test buttons                                      | Always        |
| **Paths & Storage**  | Model directory, temp directory, log file                                              | Always        |
| **AI Providers**     | AI provider, model, temperature, max tokens, translation language, summarization style | Always        |
| **Audio Processing** | 7-filter preprocessing chain                                                           | Advanced only |
| **Advanced**         | File limits, concurrency, GPU settings, log level                                      | Advanced only |

### Basic vs. Advanced Mode

**Basic Mode** (default):

- Shows 7 tabs: General, Transcription, Output, Providers & Keys, Paths &
   Storage, Playback, AI Providers
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

| Filter                 |  Default   | What It Does                           |
| ---------------------- | :--------: | -------------------------------------- |
| High-pass              |   80 Hz    | Removes rumble and low-frequency noise |
| Low-pass               |   8 kHz    | Removes hiss and high-frequency noise  |
| Noise gate             |   -40 dB   | Silences quiet background noise        |
| De-esser               |    Off     | Reduces harsh "s" sounds               |
| Compressor             |   -20 dB   | Evens out volume differences           |
| Loudness normalization |  -16 LUFS  | Standardizes overall volume            |
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
| Ctrl+L         | Live Transcription            |
| Ctrl+T         | Translate Transcript          |
| Ctrl+Shift+S   | Summarize Transcript          |
| Ctrl+Shift+P   | Audio Preview                 |
| Ctrl+Alt+P     | Preview Selected (Queue)      |
| Ctrl+Shift+C   | Copilot Chat Panel            |
| F5             | Start transcription           |
| F2             | Rename selected item          |
| F3             | Find next in transcript       |
| Ctrl+F         | Find in transcript            |
| Ctrl+C         | Copy file path (in queue)     |
| Ctrl+R         | Retry selected job (in queue) |
| Ctrl+L         | Open file location (in queue) |
| Ctrl+W         | Close file                    |
| Ctrl+Q         | Quit                          |
| Ctrl+Shift+Del | Clear entire queue            |
| Delete         | Cancel or remove selected job |
| Alt+F          | File menu                     |
| Alt+Q          | Queue menu                    |
| Alt+V          | View menu                     |
| Alt+T          | Tools menu                    |
| Alt+A          | AI menu                       |
| Alt+H          | Help menu                     |

All menu items have keyboard mnemonics (underlined letters) for quick access.

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
  - **Manual**: Download from <https://www.gyan.dev/ffmpeg/builds/> and add the
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
