# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

BITS Whisperer is an accessibility-first WXPython desktop app for audio
transcription. It supports 17 transcription providers (cloud + on-device),
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
black --check src/ tests/
ruff check src/ tests/
mypy src/

# Auto-fix
black src/ tests/
ruff check --fix src/ tests/

# Build executable (PyInstaller)
python build_installer.py              # Standard build
python build_installer.py --lean       # Clean venv, smallest output
python build_installer.py --onefile    # Single-file .exe

# Rebuild HTML docs after markdown changes
python docs/build_html_docs.py
```

## Code Style

- **black** (line-length 100) and **ruff** configured in `pyproject.toml`.
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
black --check src/ tests/

# Gate 2: Linting — must produce zero errors
ruff check src/ tests/

# Gate 3: Tests — must produce zero failures
pytest tests/ -v --tb=short --strict-markers
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
5. Run `black` (not just `--check`) if formatting is off.

### Pre-commit hooks

Pre-commit hooks are configured in `.pre-commit-config.yaml`:
```bash
pip install pre-commit
pre-commit install
```
Hooks: black, ruff, mypy, codespell, markdownlint, pre-commit-hooks
(trailing whitespace, YAML/TOML/JSON validation, debug statements,
large files, merge conflicts).

### CI pipeline

GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push
and PR to `main`:
- **Lint job**: black, ruff, mypy
- **Security job**: pip-audit (dependency vulnerability scanning)
- **Test job**: pytest with coverage on Ubuntu + Windows, Python 3.13
- **Quality gate**: blocks merge if lint or test fails

### VS Code workspace

`.vscode/settings.json` configures:
- Ruff as sole linter (flake8/pylint disabled)
- Black as formatter with format-on-save
- 100-char ruler
- Spell checker dictionary for project terms

`.vscode/extensions.json` recommends:
- Ruff, Black Formatter, Python, mypy, EditorConfig, Code Spell Checker

## Architecture

Entry point: `src/bits_whisperer/__main__.py` -> `app.py` (wx.App)
-> `ui/main_frame.py`.

### Key layers

- **`core/`** — Business logic. `transcription_service.py`
  orchestrates job queue. `provider_manager.py` routes to providers.
  `ai_service.py` handles translation/summarization.
  `copilot_service.py` manages GitHub Copilot SDK. Provider SDKs are
  installed on-demand at runtime via `sdk_installer.py`.
- **`providers/`** — Strategy pattern. `base.py` defines
  `TranscriptionProvider` ABC. 17 concrete adapters (cloud + local).
  Each provider is lazy-imported only when selected.
- **`export/`** — Strategy pattern. `base.py` defines
  `TranscriptExporter` ABC. 7 formats: txt, md, html, docx, srt,
  vtt, json.
- **`storage/`** — `database.py` (SQLite WAL mode for jobs),
  `key_store.py` (OS keyring for 22 API key entries).
- **`ui/`** — WXPython. Menu-bar-driven design for accessibility.
  Thread safety via `wx.CallAfter()`.
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
