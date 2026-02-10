# BITS Whisperer 1.0

**Professional Audio Transcription for Everyone — Free, Private, and Fully
Accessible**

From Blind Information Technology Solutions (BITS)

______________________________________________________________________

BITS Whisperer is a desktop application that transforms spoken audio into
accurate, editable text. It runs on Windows and macOS, supports 17 transcription
engines, and was built from the ground up to be accessible to every user —
including those who rely on screen readers and keyboard-only navigation.

Whether you're transcribing a board meeting, a research interview, a podcast
episode, or a university lecture, BITS Whisperer gives you the tools to do it
your way.

______________________________________________________________________

## One App, 17 Engines

BITS Whisperer puts the world's best speech recognition at your fingertips —
local and cloud, free and paid, general-purpose and specialized.

**On-device transcription** keeps your audio entirely on your computer. Choose
from 14 OpenAI Whisper model sizes powered by faster-whisper, lightweight Vosk
models for low-end hardware, or NVIDIA Parakeet for state-of-the-art English
accuracy. No internet connection required.

**Cloud transcription** connects you to OpenAI, Google Cloud Speech, Microsoft
Azure, Deepgram, AssemblyAI, Amazon Transcribe, Groq, Google Gemini, Rev.ai,
Speechmatics, ElevenLabs, and Auphonic. Each provider brings its own strengths —
real-time streaming, industry-specific vocabularies, noise-resilient models, and
more.

**Windows built-in speech recognition** works with zero setup using SAPI5 or the
modern WinRT recognizer, plus Azure Embedded Speech for offline cloud-quality
results.

BITS Whisperer recommends the best engine for your hardware automatically. You
can always override the recommendation and choose exactly the provider, model,
and language you want.

______________________________________________________________________

## AI That Works With Your Transcripts

Transcription is just the beginning. BITS Whisperer integrates six AI providers
— OpenAI, Anthropic Claude, Microsoft Azure OpenAI, Google Gemini, Ollama
(local), and GitHub Copilot — to help you do more with your text.

**Translate** your transcript into 15+ languages with a single keystroke.
**Summarize** it as a concise paragraph, a detailed narrative, or clean bullet
points. The AI understands your transcript's context, speakers, and structure.

**AI Actions** take this further. When you add files for transcription, you can
attach an AI action — a template that tells the AI what to do with the finished
transcript. Choose from six built-in presets (Meeting Minutes, Action Items,
Executive Summary, Interview Notes, Lecture Notes, Q&A Extraction) or create
your own in the AI Action Builder. The action runs automatically the moment
transcription completes, and the results appear alongside your transcript.

**Document Attachments** let you enrich AI actions with reference materials.
Attach Word documents, PDFs, spreadsheets, or text files — glossaries, style
guides, meeting agendas — and give each attachment its own instructions ("use as
glossary", "cross-reference with transcript"). The AI reads your attachments
alongside the transcript for more informed, context-aware results.

**Interactive Chat** lets you have a conversation with your transcript through
the Copilot Chat Panel. Ask questions, request analysis, explore themes — with
full streaming responses and quick-action buttons for common tasks. Type `/` to
access 28 built-in slash commands for instant AI analysis (`/summarize`,
`/translate`, `/key-points`, `/action-items`), app control (`/start`, `/export`,
`/status`), context management (`/context`), and template execution
(`/run Meeting Minutes`) — all with real-time autocomplete.

BITS Whisperer automatically manages context windows for every AI model — from
8K-token local models to 1M-token Gemini. Transcripts are intelligently fitted
to each model's capacity using configurable strategies (smart, truncate,
head+tail), with token budgets reserved for responses and conversation history.
Type `/context` in chat to see your current budget breakdown.

For users who run Ollama locally, BITS Whisperer connects to any model in the
Ollama library — including thousands of models from HuggingFace — all without an
API key or cloud dependency.

______________________________________________________________________

## Know Who's Speaking

Speaker diarization identifies and labels individual voices in your recordings.
BITS Whisperer supports diarization through 10 cloud providers and also offers
fully local, cloud-free diarization via pyannote.audio.

After transcription, you can rename speakers and reassign segments with a
right-click — turning "Speaker 1" and "Speaker 2" into real names throughout the
entire transcript.

______________________________________________________________________

## Professional Audio Cleanup

A seven-stage audio preprocessing pipeline cleans your recordings before
transcription: high-pass filter, low-pass filter, noise gate, de-esser,
compressor, loudness normalization, and silence trimming. Each filter is
independently configurable.

For users who need broadcast-grade processing, Auphonic integration provides
cloud-based leveling, loudness normalization, noise and hum reduction,
filtering, and silence/filler/cough cutting — with configurable speech
recognition included.

______________________________________________________________________

## Audio Preview and Clip Selection

Listen to your recording before you transcribe it. BITS Whisperer now includes
an audio preview tool with pitch-preserving speed control (slow or very fast
without chipmunk voices) and a simple clip-range selector. Set a start and end
time to transcribe only the section you want — perfect for trimming dead air or
isolating key segments before sending them to a provider.

Playback jump timing is configurable via sliders in Settings, so you can choose
quick 1–60 second jumps that match your review workflow.

______________________________________________________________________

## A Queue That Keeps Up With You

The transcription queue is built as a tree view that organizes files
intelligently. Drop a folder of recordings and see them grouped as an expandable
branch with live status summaries. Rename any file or folder with F2 — custom
names follow the job everywhere without touching the original files.

A filter bar lets you search the queue by name, provider, or status. Rich
context menus give you per-job control — change the provider, model, or
language; toggle diarization; retry failed jobs; view detailed properties — all
without leaving the keyboard.

Budget limits keep cloud spending in check. Set a default spending cap or
per-provider limits, enable cost confirmations for paid transcriptions, and
watch estimated costs appear next to each job in the queue.

______________________________________________________________________

## Seven Export Formats

Save your transcripts as Plain Text, Markdown, HTML, Microsoft Word, SubRip
subtitles, WebVTT captions, or structured JSON. Timestamps, speaker labels, and
confidence scores are preserved in each format where applicable.

______________________________________________________________________

## Live Microphone Transcription

Press Ctrl+L to start transcribing from your microphone in real time. BITS
Whisperer uses faster-whisper with energy-based voice activity detection to
deliver live results as you speak. Pause, resume, copy, or clear at any time.

______________________________________________________________________

## Extensible by Design

A plugin system lets you add custom transcription providers by dropping a Python
file into the plugins directory. Plugins are discovered automatically, appear in
the provider list, and can be enabled or disabled from the Tools menu.

______________________________________________________________________

## Accessible to Everyone

BITS Whisperer was created by Blind Information Technology Solutions — an
organization founded by and for people who are blind or visually impaired.
Accessibility is not a feature we added later. It is the foundation.

Every control has an accessible name. Every action is reachable by keyboard. The
menu bar is the primary interface, with mnemonics and accelerator keys on every
item. Progress is reported through gauges and status bar text that screen
readers announce automatically. The application respects system high-contrast
settings and never hard-codes colors.

The first-run setup wizard walks you through everything in eight accessible
pages — hardware scanning, model recommendations, provider configuration, AI
setup, and experience mode selection. All of it is fully navigable with a screen
reader.

Tested with NVDA. Designed for everyone.

______________________________________________________________________

## Private by Default

Transcripts are stored locally on your computer. API keys live in your operating
system's secure credential vault — Windows Credential Manager or macOS Keychain
— never in plain text, never in config files. BITS Whisperer collects no
telemetry, phones home to no servers, and includes no tracking of any kind.

When you use on-device transcription, your audio never leaves your machine. When
you choose a cloud provider, that's your decision — and BITS Whisperer does
nothing beyond what you explicitly ask for.

______________________________________________________________________

## Cross-Platform

BITS Whisperer runs on Windows 10 and later and macOS 12 and later. GPU
acceleration is supported via NVIDIA CUDA on Windows and Apple Silicon Metal on
macOS. The application detects your hardware at startup and recommends
compatible models automatically.

______________________________________________________________________

## Built With Care

674 automated tests. 17 providers. 6 AI integrations. 7 export formats. 8
built-in AI action presets. A seven-stage audio pipeline. Intelligent context
window management. Full keyboard navigation. Screen reader support. System tray
background processing. Speaker diarization with post-editing. Live microphone
transcription. A plugin system. An eight-page setup wizard. Custom job naming.
Budget limits with cost estimation. A tree-view queue with drag-and-drop,
filtering, context menus, and batch operations.

A robust ordered shutdown sequence with worker thread joining, per-job temp file
tracking, stale file cleanup, and safety-net handlers — so nothing is left
behind when you close the app.

All of it free. All of it open source. All of it accessible.

______________________________________________________________________

**BITS Whisperer** — because your words matter.

*BITS Whisperer 1.0 — Developed by Blind Information Technology Solutions
(BITS)*

*Free and open source.
[github.com/accesswatch/bits-whisperer](https://github.com/accesswatch/bits-whisperer)*
