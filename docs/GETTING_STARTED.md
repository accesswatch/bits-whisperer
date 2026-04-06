# Getting Started with BITS Whisperer

A step-by-step guide for first-time users. No technical experience required.

______________________________________________________________________

## What is BITS Whisperer?

BITS Whisperer turns spoken audio into written text. You give it a recording
(a meeting, interview, lecture, podcast, or voice memo) and it produces a
transcript you can read, edit, search, and export.

It runs on your computer, works with screen readers, and can transcribe
using free on-device AI or paid cloud services — your choice.

______________________________________________________________________

## Step 1: Install the Application

### Option A: Windows Installer (Recommended)

1. Download **BITS_Whisperer_Setup.exe** from the
   [Releases page](https://github.com/accesswatch/bits-whisperer/releases).
2. Run the installer. Follow the on-screen prompts.
3. When installation finishes, click **Launch BITS Whisperer**.

The application will appear in your Start Menu under **BITS Whisperer**.

### Option B: Install from Source (Developers)

If you prefer to run from source code:

```bash
# 1. Clone the repository
git clone https://github.com/accesswatch/bits-whisperer.git

# 2. Navigate into the folder
cd bits-whisperer

# 3. Install in development mode
pip install -e ".[dev]"

# 4. Launch the application
python -m bits_whisperer
```

**Requirements:** Python 3.13 or newer, Windows 10+ or macOS 12+.

______________________________________________________________________

## Step 2: Complete the Setup Wizard

When you launch BITS Whisperer for the first time, a **Setup Wizard** walks
you through initial configuration. Here is what each page does:

### Page 1 — Welcome

Read the overview and click **Next**.

### Page 2 — Experience Mode

Choose how much of the application you want to see:

- **Basic** (recommended for new users) — shows a streamlined interface with
  the most important settings. You can always switch to Advanced later.
- **Advanced** — shows all settings, all providers, and power-user options
  like audio preprocessing and GPU configuration.

### Page 3 — Hardware Scan

The wizard scans your computer and tells you:

- How much RAM and disk space you have.
- Whether you have a compatible GPU (NVIDIA CUDA or Apple Silicon Metal).
- Which transcription models will run well on your hardware.

No action needed — just review and click **Next**.

### Page 4 — Download a Model

This is where you download an AI model for **free, offline transcription**.
The wizard recommends the best model for your hardware (marked with a star).

- Check the box next to the model you want.
- Click **Download Selected Models Now**.
- Wait for the download to finish. A progress bar shows the status.

> **Tip:** If you only plan to use cloud providers, you can skip this step.
> But having at least one local model means you can transcribe without
> internet.

### Page 5 — Cloud Services (Optional)

If you have an account with a cloud transcription service (OpenAI, Google,
Azure, Deepgram, etc.), enter your API key here. If you do not have one, or
you only want to use the free local models, click **Next** to skip.

Each service shows a link to its sign-up page and pricing information.

### Page 6 — AI Features (Optional)

Set up AI translation and summarization. This lets you translate transcripts
into other languages or generate summaries after transcription.

- Enter an API key for at least one AI provider (OpenAI, Anthropic, Google
  Gemini, or set up Ollama for free local AI).
- Or skip this step and configure it later.

### Page 7 — Budget (Optional)

Configure spending controls for cloud providers:

- **Enable spending limits** — set a maximum spend per transcription.
- **Always confirm paid** — show a cost dialog before each cloud job.
- **Per-provider limits** — fine-grained limits per cloud provider.

Skip this step if you only use free local models.

### Page 8 — Preferences

Set your defaults:

- **Language** — the language of your recordings (or "auto-detect").
- **Export format** — how transcripts are saved (Plain Text, Word, etc.).
- **Minimize to tray** — whether the app hides to the system tray when you
  close the window (transcription continues in the background).

### Page 9 — Summary

Review your choices and click **Finish**. You are ready to go!

______________________________________________________________________

## Step 3: Transcribe Your First File

### Adding a file

1. Press **Ctrl+O** (or go to **File, then Add Files**).
2. Browse to an audio file on your computer (MP3, WAV, M4A, FLAC, OGG, or
   any other supported format).
3. The **Add File Wizard** opens. It shows:
   - **Provider** — which transcription engine to use (default: Local
     Whisper).
   - **Model** — which AI model to use (the one you downloaded earlier).
   - **Language** — auto-detect or a specific language.
   - **AI Action** — optionally run an AI task after transcription (like
     generating meeting minutes). You can leave this set to "None" for now.
4. Click **OK** to add the file to the queue.

### Starting transcription

1. Your file appears in the **queue panel** on the left side of the window.
2. Press **F5** (or go to **Queue, then Start Transcription**).
3. Watch the progress:
   - The **status bar** at the bottom shows what is happening.
   - The **progress gauge** fills up as the file is processed.
   - Your screen reader will announce progress updates automatically.

### Viewing the result

When transcription finishes:

- The transcript appears in the **right panel** automatically.
- You can read, edit, and search the text.
- Press **Ctrl+F** to search within the transcript.
- Press **F3** to find the next occurrence.

### Exporting

1. Press **Ctrl+E** (or go to **File, then Export**).
2. Choose a format:
   - **Plain Text** (.txt) — simple, works everywhere.
   - **Markdown** (.md) — good for documentation.
   - **Word** (.docx) — good for sharing and editing.
   - **SRT / VTT** — for video subtitles.
   - **HTML** — for web publishing.
   - **JSON** — for programmatic use.
3. Choose where to save the file.
4. Click **Save**.

______________________________________________________________________

## Step 4: Try Additional Features

Now that you have transcribed your first file, here are more things you can
do.

### Transcribe multiple files at once

1. Press **Ctrl+O** and select multiple files, or press **Ctrl+Shift+O** to
   add an entire folder.
2. All files are added to the queue.
3. Press **F5** to start — they are processed one by one (or in parallel if
   configured).

### Drag and drop

Drag audio files from Windows Explorer directly onto the BITS Whisperer
window. They are added to the queue automatically.

### Translate a transcript

1. After transcription, press **Ctrl+T** (or go to **AI, then Translate**).
2. The transcript is translated into your configured target language.
3. A dialog shows the result with a **Copy** button.

> **Prerequisite:** Configure an AI provider first in **Tools, then AI
> Provider Settings**.

### Summarize a transcript

1. After transcription, press **Ctrl+Shift+S** (or go to **AI, then
   Summarize**).
2. Choose a style: Concise, Detailed, or Bullet Points.
3. A dialog shows the summary with a **Copy** button.

### Use AI Actions for automatic processing

AI Actions run automatically after transcription — no extra step needed.

1. When adding files (Ctrl+O), choose an **AI Action** from the dropdown.
2. Built-in presets include: Meeting Minutes, Action Items, Executive
   Summary, Interview Notes, Lecture Notes, and Q&A Extraction.
3. After transcription finishes, the AI result appears below the transcript.

### Chat with your transcript

1. Press **Ctrl+Shift+C** to open the AI Chat Panel.
2. Type a question about your transcript (e.g., "What are the main topics
   discussed?").
3. The AI responds in real time with streaming text.
4. Quick action buttons at the top provide one-click Summarize, Key Points,
   Speakers, Action Items, and Questions.
5. Type `/help` to see all available slash commands.

### Live microphone transcription

1. Press **Ctrl+Alt+L** (or go to **Tools, then Live Transcription**).
2. Select your microphone and a Whisper model.
3. Click **Start** — your speech is transcribed in real time.
4. Use **Pause**, **Copy All**, and **Clear** as needed.
5. Click **Stop** when done.

### Monitor a folder for new recordings

1. Go to **Tools, then Watch Folder**.
2. Enable the watch folder and select a directory.
3. Any new audio file placed in that folder is automatically queued and
   transcribed.

______________________________________________________________________

## Essential Keyboard Shortcuts

These are the shortcuts you will use most often:

| What you want to do         | Press this     |
| --------------------------- | -------------- |
| Add files                   | Ctrl+O         |
| Add a folder                | Ctrl+Shift+O   |
| Start transcription         | F5             |
| Export transcript           | Ctrl+E         |
| Find in transcript          | Ctrl+F         |
| Find next                   | F3             |
| Translate                   | Ctrl+T         |
| Summarize                   | Ctrl+Shift+S   |
| Open settings               | Ctrl+,         |
| Manage AI models            | Ctrl+M         |
| Live microphone             | Ctrl+Alt+L     |
| Open AI chat                | Ctrl+Shift+C   |
| View all shortcuts          | Ctrl+Shift+K   |
| Toggle Basic/Advanced mode  | Ctrl+Shift+A   |

Press **Alt** to activate the menu bar, then use arrow keys to navigate
menus. Every menu item has a keyboard mnemonic (the underlined letter).

______________________________________________________________________

## Accessibility Notes

BITS Whisperer was built by Blind Information Technology Solutions (BITS)
with accessibility as a core requirement. Here is what to expect:

- **Screen reader support** — Every control has an accessible name. Status
  changes are announced automatically. Tested with NVDA and JAWS on Windows.
- **Full keyboard navigation** — Every feature is reachable by keyboard.
  Tab/Shift+Tab moves between controls. All actions are in the menu bar
  with mnemonics and accelerator keys.
- **High contrast** — The app uses your system colors. It works with
  Windows High Contrast mode and macOS Increased Contrast.
- **Context menus** — Right-click (or press Shift+F10 / the Apps key) on
  queue items, transcript text, and chat messages for additional options.
- **Focus management** — Dialogs set focus to the first interactive control
  when they open. Progress and completion are announced to screen readers.

______________________________________________________________________

## Where to Find Help

| What you need                | Where to go                                  |
| ---------------------------- | -------------------------------------------- |
| All keyboard shortcuts       | Help, then Keyboard Shortcuts (Ctrl+Shift+K) |
| Full user guide              | docs/USER_GUIDE.md                           |
| Application log              | Tools, then View Log                         |
| Check for updates            | Help, then Check for Updates                 |
| Report a bug                 | GitHub Issues page                           |
| Re-run the setup wizard      | Help, then Setup Wizard                      |
| Reset all settings           | Tools, then Settings, then Reset to Defaults |

______________________________________________________________________

## Common Questions

**Q: Do I need an internet connection?**
No. Once you download a local model, everything works offline. You only need
internet for cloud providers and model downloads.

**Q: Is my audio sent anywhere?**
Only if you choose a cloud provider. Local Whisper runs entirely on your
computer — your audio never leaves your machine.

**Q: Which model should I start with?**
The Setup Wizard recommends one for your hardware. As a general guide:

- 4 GB RAM, no GPU: use the **Base** model.
- 8 GB RAM, no GPU: use the **Small** model.
- NVIDIA GPU with 4+ GB VRAM: use **Large v3 Turbo**.

**Q: How are my API keys stored?**
In your operating system's credential vault (Windows Credential Manager or
macOS Keychain). They are never saved in plain text files.

**Q: Can I change the transcription provider per file?**
Yes. Right-click any file in the queue and choose **Change Provider**.

**Q: How do I switch between Basic and Advanced mode?**
Press **Ctrl+Shift+A** or go to **View, then Advanced Mode**. Your choice
is saved between sessions.

______________________________________________________________________

## Next Steps

- Read the full [User Guide](USER_GUIDE.md) for detailed documentation of
  every feature.
- Explore [AI Actions](USER_GUIDE.md#ai-actions) to automate
  post-transcription processing.
- Set up [Watch Folder](USER_GUIDE.md#watch-folder) for hands-free
  transcription.
- Try the [AI Chat Panel](USER_GUIDE.md#interactive-ai-chat-panel) for
  interactive transcript analysis.

______________________________________________________________________

*BITS Whisperer v1.0 — Developed by Blind Information Technology Solutions
(BITS). Made with care for accessibility and privacy.*
