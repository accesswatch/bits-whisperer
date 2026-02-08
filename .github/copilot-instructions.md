# Copilot / Agent Instructions — BITS Whisperer

Purpose: Actionable guidance for AI coding agents working on the BITS Whisperer project.

## Project Overview

**BITS Whisperer** is a consumer-grade WXPython desktop application for audio transcription.
- **Hybrid**: 17 providers — cloud services (OpenAI, Google, Azure, Deepgram, AssemblyAI, AWS, Groq, Gemini, Rev.ai, Speechmatics, ElevenLabs, Auphonic) + on-device Whisper (faster-whisper) + on-device Vosk (Kaldi) + on-device Parakeet (NVIDIA NeMo) + Windows built-in (SAPI5/WinRT, Azure Embedded)
- **AI services**: Translation (15+ languages) and summarization (concise/detailed/bullet points) via OpenAI, Anthropic Claude, Azure OpenAI, or Google Gemini; interactive transcript Q&A via GitHub Copilot SDK with custom agents
- **Live transcription**: Real-time microphone transcription using faster-whisper with energy-based VAD
- **Plugin system**: Extensible architecture for custom transcription providers via `.py` plugins
- **Auphonic integration**: Cloud audio post-production (leveling, loudness normalization, noise/hum reduction, filtering, silence/filler/cough cutting) with configurable speech recognition (Whisper/Google/Amazon/Speechmatics)
- **Speaker diarization**: 10 cloud providers with built-in diarization + cloud-free local diarization via pyannote.audio + post-transcription speaker editing UI
- **Accessibility-first**: WCAG 2.1/2.2 adapted for desktop; menu bar primary interface; full keyboard + screen reader support
- **Privacy-first**: local transcript storage by default; API keys in OS credential store
- **Cross-platform**: Windows 10+ and macOS 12+ support; Apple Silicon Metal GPU detection
- **First-run wizard**: 8-page setup wizard for hardware scan, model recommendations, downloads, provider setup, AI/Copilot setup, and preferences

## Agent Files

- `.github/accessibility.agent.md` — Accessibility expert agent (WXPython-adapted WCAG guidance). **MUST be read and followed for all UI work.**
- `.github/copilot-instructions.md` — This file.

## 1. Agent Workflow
- Run discovery: check `pyproject.toml`, `README.md`, `src/`, `tests/`, `docs/PRD.md`.
- Use `manage_todo_list` to plan before edits; mark steps completed as you go.
- Keep changes focused and minimal; prefer multiple small patches over one large patch.
- Ask the human before large architectural changes or file deletions.

## 2. Code Style
- Python — use `black` (line-length 100) and `ruff` as configured in `pyproject.toml`.
- Type hints required on all public functions.
- Docstrings on all public classes and methods (Google style).

## 3. Build & Test
```bash
pip install -e ".[dev]"
pytest tests/ -v
black --check src/ tests/
ruff check src/ tests/
```

## 4. Architecture
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
    ai_service.py             # AI translation & summarization (OpenAI/Anthropic/Azure/Gemini/Copilot)
    live_transcription.py     # Real-time microphone transcription
    plugin_manager.py         # Plugin discovery, loading & lifecycle
    copilot_service.py        # GitHub Copilot SDK integration & agent management
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
    key_store.py         # OS credential store via keyring (20 entries)
  ui/                      # WXPython UI
    main_frame.py        # Menu bar, splitter, status bar, tray integration
    queue_panel.py       # File queue list
    transcript_panel.py  # Transcript viewer/editor with speaker management
    settings_dialog.py   # Tabbed settings (6 simple + 2 advanced)
    progress_dialog.py   # Batch progress
    model_manager_dialog.py  # Model management
    add_provider_dialog.py   # Cloud provider onboarding
    setup_wizard.py      # First-run setup wizard (8 pages)
    tray_icon.py         # System tray (TaskBarIcon)
    live_transcription_dialog.py  # Live microphone transcription dialog
    ai_settings_dialog.py  # AI provider configuration dialog (5 providers)
    copilot_setup_dialog.py  # Copilot CLI installation & auth wizard
    copilot_chat_panel.py    # Interactive AI transcript chat panel
    agent_builder_dialog.py  # Guided AI agent configuration builder
  utils/
    accessibility.py     # a11y helpers
    constants.py         # App-wide constants & model registry
    platform_utils.py    # Cross-platform helpers (file open, disk space, CPU/GPU detection)
```

## 5. Accessibility Rules (Non-Negotiable)
- Read `.github/accessibility.agent.md` before any UI work.
- Every control: `SetName()`, label association, keyboard reachable.
- All actions in menu bar with mnemonics + accelerators.
- Progress: `wx.Gauge` + status bar text for screen readers.
- Threading: `wx.CallAfter()` for all cross-thread UI updates.
- High contrast: use `wx.SystemSettings.GetColour()`, never hard-code colours.
- Test: NVDA keyboard-only walkthrough on every PR touching UI.

## 6. Security & Secrets
- API keys stored via `keyring` (Windows Credential Manager / macOS Keychain).
- Never log, print, or commit API keys.
- Validate keys on save with a dry-run API call.

## 7. Editing Policy
- Atomic commits with brief intent messages.
- Run `pytest` before marking work complete.

## 8. Documentation Maintenance (Non-Negotiable)
When adding features, providers, settings, or changing architecture:

1. **Update all documentation files** — keep these in sync:
   - `README.md` — project overview, features, providers table, architecture tree
   - `docs/PRD.md` — full product requirements, provider table, capabilities, architecture
   - `docs/USER_GUIDE.md` — comprehensive user guide (providers, settings, shortcuts, troubleshooting)
   - `ANNOUNCEMENT.md` — user-facing feature summary
   - `.github/copilot-instructions.md` — this file (architecture tree, provider count, overview)
2. **Rebuild HTML documentation** — run `python docs/build_html_docs.py` after any `.md` changes.
   This generates `docs/README.html`, `docs/ANNOUNCEMENT.html`, and `docs/PRD.html`.
3. **Provider count consistency** — when adding/removing providers, update the count in ALL docs
   (currently 17 providers, 20 API key entries in KeyStore).
4. **Architecture tree consistency** — when adding/removing/renaming source files, update the
   architecture tree in `README.md`, `docs/PRD.md`, and this file.
5. **Auphonic documentation** — Auphonic has both `AuphonicProvider` (transcription) and
   `AuphonicService` (standalone audio post-production). Both are in `auphonic_provider.py`.
   Keep capabilities tables, pricing, and API endpoint references current.

## 9. When in Doubt
- Ask a concise question with options and a recommended default.
