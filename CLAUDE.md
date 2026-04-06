# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

BITS Whisperer is an accessibility-first WXPython desktop app for audio
transcription. It supports 18 transcription providers (cloud + on-device),
AI translation/summarization, live microphone transcription, speaker
diarization, a plugin system, and 7 export formats. Built by Blind
Information Technology Solutions (BITS) for Windows 10+ and macOS 12+.
Python 3.13+.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run all tests (pyproject.toml sets testpaths=tests,
# addopts="-v --tb=short --strict-markers")
pytest

# Run a single test file
pytest tests/test_providers.py

# Run a single test by name
pytest tests/test_providers.py::TestProviderName::test_method

# Lint and format
ruff format --check src/ tests/
ruff check src/ tests/
pyright src/

# Auto-fix
ruff format src/ tests/
ruff check --fix src/ tests/

# Build executable (PyInstaller)
python build_installer.py              # Standard build
python build_installer.py --lean       # Clean venv, smallest output
python build_installer.py --onefile    # Single-file .exe

# Rebuild HTML docs after markdown changes
python docs/build_html_docs.py
```

## Code Style

- **ruff** (line-length 100) for both formatting and linting, configured
  in `pyproject.toml`.
- **Ruff rules**: E, F, W, I, UP, B, SIM, C4, RET, TCH, PIE, PLC, PLE,
  PLW, RUF, PERF, LOG, S (security/bandit), T20 (no print), PT
  (pytest style), A (builtins), ERA (commented-out code).
- **Line length**: 100 characters maximum. Never exceed this.
- **No `print()`** in production code — use `logging`. T20 rule
  enforces this (relaxed in tests).
- Type hints required on all public functions.
- Google-style docstrings on public classes/methods.
- Use `from __future__ import annotations` in new modules.
- Use `contextlib.suppress(ExcType)` instead of bare
  `try: ... except ExcType: pass`.
- Use `subprocess.run(..., check=False)` explicitly — never omit
  `check`.
- Lazy imports for optional SDKs (imported inside methods, not at
  module level). This is by design — do not "fix" them.

## Verification Gates (Non-Negotiable)

**Every change MUST pass ALL gates before being considered complete.**

```bash
# Gate 1: Formatting — must produce zero reformats
ruff format --check src/ tests/

# Gate 2: Linting — must produce zero errors
ruff check src/ tests/

# Gate 3: Tests — must produce zero failures
pytest tests/ -v --tb=short --strict-markers

# Gate 4 (if applicable): Problems pane — zero errors
# Resolve all warnings/errors shown in VS Code Problems pane
```

Rules:

1. Run all three gates after completing edits. Do not mark work as
   done until all pass.
2. Fix violations immediately — do not leave lint or test failures
   for the user.
3. If a new ruff rule fires, fix the code rather than adding an
   ignore unless the pattern is intentional and project-wide.
4. Test new functionality — add tests for any new public method or
   class.
5. Run `ruff format` (not just `--check`) if formatting is off.

### Pre-commit hooks

Pre-commit hooks are configured in `.pre-commit-config.yaml`:

```bash
pip install pre-commit
pre-commit install
```

Hooks: ruff (format + lint), pyright, codespell, markdownlint,
pre-commit-hooks (trailing whitespace, YAML/TOML/JSON validation,
debug statements, large files, merge conflicts).

### CI pipeline

GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push
and PR to `main`:

- **Lint job**: ruff (format + lint), pyright
- **Security job**: pip-audit (dependency vulnerability scanning)
- **Test job**: pytest with coverage on Windows, Python 3.13
- **Quality gate**: blocks merge if lint or test fails

### VS Code workspace

`.vscode/settings.json` configures:

- Ruff as sole linter and formatter (flake8/pylint/Black disabled)
- Format-on-save via Ruff extension
- 100-char ruler
- Spell checker dictionary for project terms

`.vscode/extensions.json` recommends:

- Ruff, Python, Pylance, EditorConfig, Code Spell Checker

## Architecture

Entry point: `src/bits_whisperer/__main__.py` -> `app.py` (wx.App)
-> `ui/main_frame.py`.

### Key layers

- **`core/`** — Business logic. `transcription_service.py`
  orchestrates job queue. `provider_manager.py` routes to providers
  and accepts `feature_flag_service` and `beta_service` for
  per-provider feature flag gating. `ai_service.py` handles
  translation/summarization (6 providers including Ollama).
  `copilot_service.py` manages GitHub Copilot SDK.
  `feature_flags.py` provides remote feature flag service.
  `watch_folder.py` monitors a directory for new audio files.
  `ollama_adapter.py` provides a native HTTP REST adapter for
  Ollama (streaming, model management, health monitoring,
  automatic fallback). `dnd_monitor.py` detects Windows Focus
  Assist / macOS DND status with configurable pause/resume.
  `scheduler_service.py` runs timed and recurring transcription
  jobs with DND-aware rules.
  `beta_service.py` handles beta invitations and status.
  `registration_service.py` manages product licensing.
  `member_verification.py` manages OTP-based BITS member
  email verification.
  `github_oauth.py` implements GitHub OAuth device flow.
  Provider SDKs are installed on-demand at runtime via
  `sdk_installer.py`.
- **`providers/`** — Strategy pattern. `base.py` defines
  `TranscriptionProvider` ABC. 18 concrete adapters (cloud + local).
  Each provider is lazy-imported only when selected.
- **`export/`** — Strategy pattern. `base.py` defines
  `TranscriptExporter` ABC. 7 formats: txt, md, html, docx, srt,
  vtt, json.
- **`storage/`** — `database.py` (SQLite WAL mode for jobs),
  `key_store.py` (OS keyring for 33 API key entries).
- **`ui/`** — WXPython. Menu-bar-driven design for accessibility.
  Thread safety via `wx.CallAfter()`. Includes `watch_folder_dialog.py`,
  `add_file_wizard.py`, `whats_new_dialog.py`,
  `beta_settings_dialog.py`, `keyboard_shortcuts_dialog.py`,
  `welcome_dialog.py`, `license_dialog.py`. All
  dialogs use `wx.TAB_TRAVERSAL` for consistent tab navigation.
  Window state (size, position, maximized) is persisted across
  sessions. Context menus in transcript, chat, model manager, and
  agent builder panels. Keyboard shortcuts reference dialog
  (Ctrl+Shift+K) accessible from Help menu.
- **`utils/`** — `constants.py` (model registry, app constants),
  `accessibility.py` (a11y helpers), `platform_utils.py`.

### Adding a new provider

1. Create `providers/new_provider.py` implementing
   `TranscriptionProvider` ABC from `providers/base.py`.
2. Register it in `core/provider_manager.py`.
3. Add SDK to optional dependencies in `pyproject.toml`.
4. Add tests in `tests/test_providers.py`.
5. Update provider count in all docs.
6. Run all verification gates.

## Feature Flags (Staged Rollout)

Remote feature flag service for QA-gated feature rollout.

- **Config**: `feature_flags.json` in repo root — fetched via raw
  GitHub URL, cached locally with 24h TTL.
- **Service**: `core/feature_flags.py` — `FeatureFlagService` with
  remote fetch, local cache, version gating, local overrides.
- **Settings**: `FeatureFlagSettings` in `core/settings.py` —
  `remote_url`, `refresh_hours`, `local_overrides`.
- **UI**: `main_frame.py` calls `feature_flags.is_enabled()` in
  `_build_menu_bar()` to show/hide menu items.

### Flag identifiers

`live_transcription`, `ai_translate`, `ai_summarize`, `ai_chat`,
`agent_builder`, `audio_preview`, `diarization`, `plugins`,
`copilot`, `self_updater`, `budget_tracking`,
`multi_language_translate`, `watch_folder`, `alpha_testing`.

**Ollama / infrastructure flags**:
`ollama_native`, `ollama_cli_fallback`, `ollama_model_catalog`,
`model_manager_treeview`, `dnd_monitor`, `scheduler`.

**Provider flags** (naming convention `provider_<key>`):
`provider_local_whisper`, `provider_openai_whisper`,
`provider_google_speech`, `provider_azure_speech`,
`provider_azure_embedded`, `provider_deepgram`,
`provider_assemblyai`, `provider_aws_transcribe`,
`provider_gemini`, `provider_groq_whisper`, `provider_rev_ai`,
`provider_speechmatics`, `provider_elevenlabs`,
`provider_auphonic`, `provider_vosk`, `provider_parakeet`,
`provider_windows_speech`, `provider_mai_transcribe`.

### Adding a feature flag

1. Add entry to `feature_flags.json`.
2. Gate UI with `self.feature_flags.is_enabled("flag_name")`.
3. Add tests in `tests/test_feature_flags.py`.
4. Run all verification gates.

For provider flags, use the naming convention `provider_<key>`
where `<key>` matches the provider's identifier in
`ProviderManager`. Set `change_category` to `"provider"` in the
`FeatureChange` dataclass.

## Accessibility (Non-Negotiable for UI work)

Read `.github/accessibility.agent.md` before any UI changes.

- Every control needs `SetName()`, label association, keyboard
  reachability.
- All actions must be in the menu bar with mnemonics + accelerators.
- Progress: `wx.Gauge` + status bar text for screen readers.
- High contrast: use `wx.SystemSettings.GetColour()`, never
  hard-code colors.
- Threading: `wx.CallAfter()` for all cross-thread UI updates.

## Documentation Maintenance

When adding features, providers, or changing architecture, update ALL
of these to stay in sync:

- `docs/README.md`, `docs/PRD.md`, `docs/USER_GUIDE.md`,
  `docs/ANNOUNCEMENT.md`
- `.github/copilot-instructions.md` (architecture tree, provider
  count)
- Then run `python docs/build_html_docs.py` to regenerate HTML docs.

## Security

API keys are stored via `keyring` (Windows Credential Manager / macOS
Keychain). Never log, print, or commit API keys. Validate keys on
save with a dry-run API call.
