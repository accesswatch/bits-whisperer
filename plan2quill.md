# Plan to Bring BITS Whisperer Transcription Features into QUILL

## Goal
Move a focused, safe subset of BITS Whisperer transcription capabilities into QUILL in phases, starting with model download and configuration only, then expanding incrementally after reliability and accessibility gates pass.

## Current State Review

### BITS Whisperer baseline (source system)
- Mature local transcription providers with model catalogs and runtime downloads:
  - Local Whisper via faster-whisper.
  - Vosk offline ASR.
  - NVIDIA Parakeet (NeMo) offline ASR.
- Existing unified model management concepts:
  - Provider-aware model metadata and status.
  - Hardware-aware model sizing metadata.
  - On-demand SDK install strategy and wheel extraction path for frozen builds.
- Existing local model catalogs are explicit and production-oriented.

Evidence reviewed in this repository:
- src/bits_whisperer/core/model_manager.py
- src/bits_whisperer/providers/local_whisper.py
- src/bits_whisperer/providers/vosk_provider.py
- src/bits_whisperer/providers/parakeet_provider.py
- src/bits_whisperer/utils/constants.py
- src/bits_whisperer/core/sdk_installer.py
- src/bits_whisperer/core/wheel_installer.py

### QUILL baseline (target system)
- Dictation in QUILL is currently centered on Windows dictation workflow, with placeholders/hooks for whisper and vosk recognition pathways.
- QUILL already has a separate AI model manager for local GGUF language models (assistant), including:
  - curated model registry,
  - first-use download,
  - saved model choice.
- This means QUILL has a proven pattern for model lifecycle management that can be reused for speech models.

Evidence reviewed in QUILL:
- quill/core/dictation.py
- quill/core/settings.py
- quill/ui/main_frame.py
- quill/core/ai/model_manager.py
- README.md
- docs/QUILL-PRD.md

## Recommended First Models to Bring to QUILL

### Bring now (phase 1)
1. Whisper tiny
- Why: very fast, lowest friction starter model, useful for constrained hardware.
- BW evidence: in WHISPER_MODELS list.

2. Whisper base
- Why: practical quality/speed default for most users.
- BW evidence: in WHISPER_MODELS list.

3. Whisper small
- Why: quality step-up for users with moderate hardware.
- BW evidence: in WHISPER_MODELS list.

4. Whisper large-v3-turbo
- Why: best quality-per-speed option for GPU-capable users.
- BW evidence: in WHISPER_MODELS list.

### Defer (phase 2+)
1. Full Vosk catalog
- Reason to defer: introduces separate model source, archive handling, and multilingual policy surface.

2. Parakeet catalog
- Reason to defer: NeMo dependency weight and operational complexity are high for first migration increment.

3. Remaining Whisper long tail
- large-v1, large-v2, large-v3, medium, distil variants can follow once telemetry and support burden are understood.

## Strategic Migration Approach

### Principle 1: Align with QUILL architecture first
Do not copy BW modules directly. Reuse QUILL patterns already used by quill/core/ai/model_manager.py:
- model registry object(s),
- persisted model selection,
- deterministic first-use download path,
- progress callbacks.

### Principle 2: Separate model lifecycle from transcription runtime
Phase 1 should deliver:
- model catalog,
- download management,
- config UI,
- preflight checks,
- no automatic runtime switchover until explicit opt-in.

### Principle 3: Keep accessibility and profile safety first-class
All new controls and settings should follow QUILL profile and accessibility conventions already used by feature-gated tools and settings flows.

## Delivery Plan

## Phase 0 - Design and hardening prep (1 sprint)
1. Define target data model in QUILL for speech model specs.
2. Choose storage paths in QUILL app data for speech models, separate from AI GGUF path.
3. Add risk controls:
- disk space preflight,
- checksum/hash optionality,
- interruption-safe partial download strategy.

Exit criteria:
- ADR or architecture note approved.
- Final model list for phase 1 frozen.

## Phase 1 - Whisper model download and configuration only (1-2 sprints)
1. Implement QUILL speech model registry for:
- tiny,
- base,
- small,
- large-v3-turbo.
2. Add settings and persistence:
- selected speech model,
- engine mode (keep existing dictation defaults safe).
3. Implement model download service with progress and resumable-safe behavior.
4. Add UI surface in Preferences and/or Dictation settings:
- list models,
- show size and hardware guidance,
- download/remove,
- set default model.
5. Keep dictation runtime unchanged by default; add feature flag or explicit toggle for whisper-backed path.

Exit criteria:
- users can download and configure model choices reliably,
- no regression in existing Windows dictation path,
- new tests pass.

## Phase 2 - Runtime integration and pilot (1 sprint)
1. Wire configured whisper models to dictation runtime under guarded feature flag.
2. Add fallback path if model unavailable or incompatible.
3. Pilot with internal users and collect quality/perf feedback.

Exit criteria:
- pilot acceptance metrics met,
- support incidents within acceptable threshold,
- accessibility walkthrough approved.

## Phase 3 - Optional expansions (later)
1. Add Vosk small-en first (single-model pilot) before multilingual expansion.
2. Add Parakeet only after dependency and packaging strategy is proven.
3. Expand Whisper catalog based on telemetry, not assumptions.

## Responsible Guardrails

1. Packaging and dependency control
- Follow BW lesson: keep heavy provider stacks optional and on-demand.
- Avoid bundling large speech runtimes in the default installer initially.

2. Reliability guardrails
- Handle partial downloads atomically.
- Validate model path integrity before activation.
- Keep safe fallback to existing dictation behavior.

3. Accessibility and UX guardrails
- Keep keyboard-only workflows complete.
- Announce model operations clearly (start, progress, completion, failure).
- Avoid hidden state transitions.

4. Security and privacy
- Keep local-first behavior clear in UI copy.
- No silent cloud calls in speech model management paths.

## Suggested Technical Work Breakdown

1. New QUILL modules (target naming suggestion)
- quill/core/speech/model_registry.py
- quill/core/speech/model_store.py
- quill/core/speech/model_downloader.py
- quill/core/speech/model_selection.py

2. Integration points
- quill/core/settings.py for persisted speech model config.
- quill/ui/main_frame.py and settings dialogs for management UI.
- quill/core/dictation.py for guarded runtime handoff.

3. Tests
- unit tests for registry and selection,
- downloader tests with failure and retry paths,
- integration tests for settings persistence and fallback behavior.

## What I Would Not Bring Over Immediately
1. Full BW multi-provider transcription matrix.
2. BW cloud provider onboarding for transcription.
3. BW Parakeet and full Vosk multilingual catalogs in the first increment.
4. Complex advanced features (diarization, watch-folder coupling, budget integration) until phase 1 and 2 stabilize.

## Concrete Recommendation
Start with Whisper-only model management in QUILL now, with exactly four models:
- tiny,
- base,
- small,
- large-v3-turbo.

This gives a clear quality ladder across low-end, mainstream, and high-end hardware while minimizing migration risk and support load.

After that lands cleanly, add runtime integration behind a guarded switch, pilot it, then decide if Vosk and Parakeet are worth the extra complexity in QUILL.
