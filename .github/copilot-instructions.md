# Copilot / Agent Instructions — BITS Whisperer

Purpose: Actionable guidance for AI coding agents working on the BITS Whisperer project.

## Project Overview

**BITS Whisperer** is a consumer-grade WXPython desktop application for audio transcription.
- **Hybrid**: 17 providers — cloud services (OpenAI, Google, Azure, Deepgram,
  AssemblyAI, AWS, Groq, Gemini, Rev.ai, Speechmatics, ElevenLabs, Auphonic)
  + on-device Whisper (faster-whisper) + on-device Vosk (Kaldi) + on-device
  Parakeet (NVIDIA NeMo) + Windows built-in (SAPI5/WinRT, Azure Embedded)
- **AI services**: Translation (15+ languages) and summarization via OpenAI,
  Anthropic Claude, Azure OpenAI, Google Gemini, or Ollama; interactive
  transcript Q&A via GitHub Copilot SDK with custom agents
- **Live transcription**: Real-time microphone transcription using
  faster-whisper with energy-based VAD
- **Audio preview**: Pitch-preserving playback with clip-range selection
  before transcription
- **Plugin system**: Extensible architecture for custom transcription
  providers via `.py` plugins
- **Auphonic integration**: Cloud audio post-production with configurable
  speech recognition
- **Speaker diarization**: 10 cloud providers with built-in diarization +
  cloud-free local diarization via pyannote.audio + speaker editing UI
- **Accessibility-first**: WCAG 2.1/2.2 adapted for desktop; menu bar
  primary interface; full keyboard + screen reader support
- **Privacy-first**: local transcript storage by default; API keys in OS
  credential store
- **Cross-platform**: Windows 10+ and macOS 12+ support; Apple Silicon
  Metal GPU detection
- **First-run wizard**: 8-page setup wizard for hardware scan, model
  recommendations, downloads, provider setup, AI/Copilot setup, and
  preferences

## Agent Files

- `.github/accessibility.agent.md` — Accessibility expert agent
  (WXPython-adapted WCAG guidance). **MUST be read and followed for all
  UI work.**
- `.github/copilot-instructions.md` — This file.

## 1. Agent Workflow
- Run discovery: check `pyproject.toml`, `README.md`, `src/`, `tests/`,
  `docs/PRD.md`.
- Use `manage_todo_list` to plan before edits; mark steps completed as
  you go.
- Keep changes focused and minimal; prefer multiple small patches over
  one large patch.
- Ask the human before large architectural changes or file deletions.

## 2. Code Style
- Python 3.13+; use `black` (line-length 100) and `ruff` as configured
  in `pyproject.toml`.
- **Line length**: 100 characters maximum. Never exceed this.
- **Ruff rules**: E, F, W, I, UP, B, SIM, C4, RET, TCH, PIE, PLC,
  PLE, PLW, RUF, PERF, LOG, S (security/bandit), T20 (no print),
  PT (pytest style), A (builtins), ERA (commented-out code).
- **No `print()`** in production code — use `logging` instead. The
  T20 rule enforces this (relaxed in tests via per-file-ignores).
- Type hints required on all public functions.
- Docstrings on all public classes and methods (Google style).
- Use `from __future__ import annotations` in new modules.
- Prefer `collections.abc` types (`Sequence`, `Mapping`) over `list`,
  `dict` in type hints for parameters.
- Use `contextlib.suppress(ExcType)` instead of bare
  `try: ... except ExcType: pass`.
- Use `subprocess.run(..., check=False)` explicitly — never omit
  `check`.
- Lazy imports for optional SDKs (provider SDKs are imported inside
  methods, not at module level). This is by design.

## 3. Build & Test
```bash
pip install -e ".[dev]"
pytest tests/ -v --strict-markers
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
    audio_player.py           # Audio preview playback
    dependency_checker.py     # Startup dependency verification
    device_probe.py           # Hardware detection (CPU/RAM/GPU)
    diarization.py            # Cloud-free local speaker diarization
    model_manager.py          # Whisper model download/cache
    sdk_installer.py          # On-demand provider SDK installer
    wheel_installer.py        # PyPI wheel downloader/extractor
    settings.py               # Persistent settings (JSON-backed)
    transcoder.py             # ffmpeg audio normalisation
    updater.py                # GitHub Releases self-update
    job.py                    # Job data model
    ai_service.py             # AI translation & summarization
    live_transcription.py     # Real-time microphone transcription
    plugin_manager.py         # Plugin discovery & lifecycle
    copilot_service.py        # GitHub Copilot SDK integration
    context_manager.py        # Context window management
    document_reader.py        # Document text extraction
    feature_flags.py          # Remote feature flag service
  providers/               # 17 provider adapters (strategy pattern)
    base.py              # TranscriptionProvider ABC
    local_whisper.py     # faster-whisper (local, free)
    openai_whisper.py    # OpenAI Whisper API
    google_speech.py     # Google Cloud Speech-to-Text
    gemini_provider.py   # Google Gemini
    azure_speech.py      # Microsoft Azure Speech Services
    azure_embedded.py    # Azure Embedded Speech (offline)
    aws_transcribe.py    # Amazon Transcribe
    deepgram_provider.py # Deepgram Nova-2
    assemblyai_provider.py  # AssemblyAI
    groq_whisper.py      # Groq LPU Whisper
    rev_ai_provider.py   # Rev.ai
    speechmatics_provider.py # Speechmatics
    elevenlabs_provider.py   # ElevenLabs Scribe
    windows_speech.py    # Windows SAPI5 + WinRT (offline)
    vosk_provider.py     # Vosk offline speech (Kaldi-based)
    parakeet_provider.py # NVIDIA Parakeet (NeMo ASR)
    auphonic_provider.py # Auphonic post-production + transcription
  export/                  # Output formatters
    base.py, plain_text.py, markdown.py
    html_export.py, word_export.py
    srt.py, vtt.py, json_export.py
  storage/                 # Persistence
    database.py          # SQLite (WAL mode) for jobs
    key_store.py         # OS credential store via keyring (22 entries)
  ui/                      # WXPython UI
    main_frame.py        # Menu bar, splitter, status bar, tray
    queue_panel.py       # File queue list
    transcript_panel.py  # Transcript viewer/editor
    settings_dialog.py   # Tabbed settings
    progress_dialog.py   # Batch progress
    model_manager_dialog.py  # Model management
    add_provider_dialog.py   # Cloud provider onboarding
    setup_wizard.py      # First-run setup wizard (8 pages)
    tray_icon.py         # System tray (TaskBarIcon)
    live_transcription_dialog.py  # Live microphone transcription
    ai_settings_dialog.py  # AI provider configuration
    copilot_setup_dialog.py  # Copilot auth wizard
    copilot_chat_panel.py    # Interactive AI chat panel
    slash_commands.py        # Chat slash command registry
    agent_builder_dialog.py  # AI agent configuration builder
    audio_player_dialog.py   # Audio preview with clip selection
  utils/
    accessibility.py     # a11y helpers
    constants.py         # App-wide constants & model registry
    platform_utils.py    # Cross-platform helpers
```

## 5. Accessibility Rules (Non-Negotiable)
- Read `.github/accessibility.agent.md` before any UI work.
- Every control: `SetName()`, label association, keyboard reachable.
- All actions in menu bar with mnemonics + accelerators.
- Progress: `wx.Gauge` + status bar text for screen readers.
- Threading: `wx.CallAfter()` for all cross-thread UI updates.
- High contrast: use `wx.SystemSettings.GetColour()`, never hard-code
  colours.
- Test: NVDA keyboard-only walkthrough on every PR touching UI.

## 6. Security & Secrets
- API keys stored via `keyring` (Windows Credential Manager / macOS
  Keychain).
- Never log, print, or commit API keys.
- Validate keys on save with a dry-run API call.

## 7. Verification Gates (Non-Negotiable)
**Every change MUST pass ALL gates before being considered complete.**

Run these checks in order after every edit:

```bash
# Gate 1: Formatting — must produce zero reformats
black --check src/ tests/

# Gate 2: Linting — must produce zero errors
ruff check src/ tests/

# Gate 3: Tests — must produce zero failures
pytest tests/ -v --tb=short --strict-markers

# Gate 4 (if UI changed): Accessibility review
# Manually verify SetName(), keyboard nav, screen reader output
```

### Rules for AI agents
1. **Run all three gates** (`black --check`, `ruff check`, `pytest`)
   after completing edits. Do not mark work as done until all pass.
2. **Fix violations immediately** — do not leave lint or test
   failures for the user to clean up.
3. **If a new ruff rule fires**, fix the code rather than adding an
   ignore unless the pattern is intentional and project-wide.
4. **Test new functionality** — add tests for any new public method
   or class. Place tests in the appropriate `tests/test_*.py` file.
5. **Run `black` (not just `--check`)** if formatting is off — the
   formatter is authoritative.
6. **Check `get_errors` after edits** to catch type errors the linter
   may miss.

### Pre-commit hooks
Pre-commit hooks are configured in `.pre-commit-config.yaml`. After
cloning, developers should run:
```bash
pip install pre-commit
pre-commit install
```
This runs black, ruff, mypy, codespell, markdownlint, and
pre-commit-hooks automatically before each commit.

### CI pipeline
GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push and
PR to `main`:
- **Lint job**: black, ruff, mypy
- **Security job**: pip-audit (dependency vulnerability scanning)
- **Test job**: pytest with coverage on Ubuntu + Windows, Python 3.13
- **Quality gate**: blocks merge if lint or test fails

### VS Code workspace settings
The `.vscode/` directory configures the recommended development
environment:
- `settings.json`: Ruff as sole linter (flake8/pylint disabled),
  Black formatter with format-on-save, 100-char ruler, spell checker.
- `extensions.json`: Recommends Ruff, Black Formatter, Python, mypy,
  EditorConfig, Code Spell Checker. Blocks flake8 and pylint extensions.

## 8. Editing Policy
- Atomic commits with brief intent messages.
- Run all verification gates before marking work complete.
- When writing tests, use `pytest-mock` fixtures (`mocker`) for
  mocking, not raw `unittest.mock` where avoidable.

## 9. Documentation Maintenance (Non-Negotiable)
When adding features, providers, settings, or changing architecture:

1. **Update all documentation files** — keep these in sync:
   - `README.md` — project overview, features, providers table,
     architecture tree
   - `docs/PRD.md` — full product requirements, provider table,
     capabilities, architecture
   - `docs/USER_GUIDE.md` — comprehensive user guide (providers,
     settings, shortcuts, troubleshooting)
   - `ANNOUNCEMENT.md` — user-facing feature summary
   - `.github/copilot-instructions.md` — this file (architecture
     tree, provider count, overview)
2. **Rebuild HTML documentation** — run
   `python docs/build_html_docs.py` after any `.md` changes.
   This generates `docs/README.html`, `docs/ANNOUNCEMENT.html`, and
   `docs/PRD.html`.
3. **Provider count consistency** — when adding/removing providers,
   update the count in ALL docs (currently 17 providers, 22 API key
   entries in KeyStore).
4. **Architecture tree consistency** — when adding/removing/renaming
   source files, update the architecture tree in `README.md`,
   `docs/PRD.md`, and this file.
5. **Auphonic documentation** — Auphonic has both `AuphonicProvider`
   (transcription) and `AuphonicService` (standalone audio
   post-production). Both are in `auphonic_provider.py`. Keep
   capabilities tables, pricing, and API endpoint references current.

## 10. Feature Flags (Staged Rollout)

The app uses a **remote feature flag service** for staged feature
rollout. A JSON config file hosted on GitHub controls which features
are visible to users. This allows QA-gated releases without code
changes.

### Architecture
- **Remote config**: `feature_flags.json` in the repo root, fetched
  via raw GitHub URL.
- **Service**: `core/feature_flags.py` — `FeatureFlagService` class
  with TTL-based caching (24h default), offline fallback, version
  gating, and local overrides.
- **Settings**: `FeatureFlagSettings` dataclass in `core/settings.py`
  with `remote_url`, `refresh_hours`, and `local_overrides` dict.
- **UI integration**: `main_frame.py` uses `feature_flags.is_enabled()`
  in `_build_menu_bar()` to conditionally show/hide menu items and
  in `_refresh_chat_tab_visibility()` for tab visibility.
- **Tests**: `tests/test_feature_flags.py` (35 tests).

### Feature flag identifiers
`live_transcription`, `ai_translate`, `ai_summarize`, `ai_chat`,
`agent_builder`, `audio_preview`, `diarization`, `plugins`,
`copilot`, `self_updater`, `budget_tracking`,
`multi_language_translate`.

### Adding a new feature flag
1. Add the flag to `feature_flags.json` in the repo root.
2. Use `self.feature_flags.is_enabled("flag_name")` in
   `main_frame.py` to gate the UI element.
3. Add tests in `tests/test_feature_flags.py`.
4. Run all verification gates.

### Disabling a feature for staged rollout
1. Set `"enabled": false` in `feature_flags.json`.
2. Commit and push — all deployed instances will pick up the
   change within 24 hours (or on next app restart).
3. When QA approves, set `"enabled": true` and push.

## 11. Common Patterns

### Adding a new provider
1. Create `providers/new_provider.py` implementing
   `TranscriptionProvider` ABC from `providers/base.py`.
2. Register it in `core/provider_manager.py`.
3. Add SDK to optional dependencies in `pyproject.toml`.
4. Add tests in `tests/test_providers.py`.
5. Update provider count in all docs.
6. Run all verification gates.

### Adding a new AI provider
1. Add a new class in `core/ai_service.py` inheriting `AIProvider`.
2. Register in `AIService._get_provider()`.
3. Add key entry in `storage/key_store.py`
4. Add tests in `tests/test_gemini_copilot.py` or a new test file.
5. Update key count in docs (currently 22).
6. Run all verification gates.

### Adding new UI
1. Read `.github/accessibility.agent.md` first.
2. Every new control: `SetName()`, mnemonic, keyboard shortcut.
3. Menu bar integration for all actions.
4. `wx.CallAfter()` for cross-thread updates.
5. Run all verification gates.

## 12. When in Doubt
- Ask a concise question with options and a recommended default.
