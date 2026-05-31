# Faster Whisper Integration Review

Generated: 2026-05-13

## Summary

The upstream `faster-whisper` project was cloned to `D:\code\faster-whisper` for local review. It is a strong fit for BITS Whisperer and is already the intended implementation behind the existing `local_whisper` provider.

Recommendation: keep using `faster-whisper` as an optional runtime dependency instead of vendoring the cloned source into BITS Whisperer. Use the clone for reference, debugging, and upstream issue review.

## Clone Details

- Repository: `https://github.com/SYSTRAN/faster-whisper.git`
- Local path: `D:\code\faster-whisper`
- Checked-out branch: `master`
- Verified commit: `ed9a06c`, `Adds new VAD parameters (#1386)`
- License: MIT

The MIT license is compatible with the BITS Whisperer MIT license, provided license notices are preserved if code is copied. Avoid copying upstream source unless there is a clear reason.

## Current BITS Whisperer Fit

BITS Whisperer already has the right architecture for `faster-whisper`:

- `local_whisper` is declared as an optional provider dependency in `pyproject.toml`.
- `requirements-providers.txt` includes `faster-whisper>=1.2.1,<2`.
- `src/bits_whisperer/providers/local_whisper.py` wraps `faster_whisper.WhisperModel` behind the provider interface.
- `src/bits_whisperer/core/model_manager.py` downloads models by instantiating `WhisperModel` with `download_root` under the app data models directory.
- `src/bits_whisperer/core/live_transcription.py` also uses `WhisperModel` for local live transcription.
- `src/bits_whisperer/core/sdk_installer.py` supports on-demand provider SDK installation.

This means BITS Whisperer should not need a large architectural change to benefit from `faster-whisper`.

## Important Compatibility Findings

### Python Version

`faster-whisper` supports Python 3.9 and newer. BITS Whisperer targets Python 3.13, and a local Python 3.13 install successfully installed `faster-whisper` and imported it.

### Dependency Set

The cloned upstream `requirements.txt` currently lists:

- `ctranslate2>=4.0,<5`
- `huggingface_hub>=0.23`
- `tokenizers>=0.13,<1`
- `onnxruntime>=1.14,<2`
- `av>=11`
- `tqdm`

The `onnxruntime` dependency matters. BITS Whisperer's `wheel_installer.py` currently excludes `onnxruntime` as a package that should never be downloaded. That exclusion is risky for current `faster-whisper` versions because `onnxruntime` is now a direct dependency.

Implemented safe recommendation: allow the CPU `onnxruntime` wheel to be installed on demand while keeping `onnxruntime_gpu` excluded.

### Existing Virtual Environment

The existing `D:\code\bw\.venv` is not usable on this machine. Its `pyvenv.cfg` points to `C:\PY\Python313`, which does not exist here.

Recommendation: recreate the BITS Whisperer virtual environment before running full tests:

```powershell
cd D:\code\bw
Remove-Item -Recurse -Force .venv
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,local-whisper]"
```

## Recommendations

### 1. Keep `faster-whisper` Optional, Not Bundled

The current lean installer strategy is sound. Keep provider SDKs out of the base PyInstaller bundle and install `faster-whisper` on demand.

Reason: `faster-whisper`, `ctranslate2`, `onnxruntime`, and model files can be large. Bundling them by default would make the installer much heavier for users who only want cloud transcription.

### 2. Pin a Tested Version Range

The previous dependency was broad: `faster-whisper>=1.0.0`. That was convenient but could allow upstream dependency changes to affect the app unexpectedly.

Implemented short-term pin:

```text
faster-whisper>=1.2.1,<2
```

This matches the version tested locally during the MP3 transcription work and keeps the app away from a future major-version break.

### 3. Fix On-Demand Wheel Installation for `onnxruntime`

Previous risk: the frozen-app wheel installer could skip `onnxruntime`, causing `faster_whisper` import or VAD behavior to fail after on-demand installation.

Implemented safe action:

- Removed CPU `onnxruntime` from `_EXCLUDED` in `src/bits_whisperer/core/wheel_installer.py`.
- Kept `onnxruntime_gpu` excluded to avoid a large GPU runtime install path unless it is explicitly designed later.

CPU-only `onnxruntime` is the safe default. Do not install `onnxruntime-gpu` automatically unless the user explicitly chooses a GPU path.

### 4. Add a Real Local Whisper Smoke Test

Current tests validate provider metadata but do not verify an actual local transcription path.

Recommended test:

- Generate a tiny WAV fixture or include a very short public-domain audio sample.
- Monkeypatch or use the smallest model only for an opt-in slow test.
- Verify `LocalWhisperProvider.transcribe()` returns at least one segment and non-empty text.

Mark the test as `slow` so normal CI can skip it unless provider integration is being validated.

### 5. Improve Long Audio Strategy

`faster-whisper` can handle long audio, but desktop UX is better when long files are chunked with progress reporting and cancellation.

Recommended action:

- Reuse BITS Whisperer's existing transcoder and chunking settings.
- Transcribe long files in chunks for UI responsiveness.
- Preserve timestamps by offsetting each chunk's segment times.
- Keep `vad_filter=True`, and expose a simple advanced setting for VAD sensitivity later.

### 6. Provide Clear Model Guidance for Users

The existing `WHISPER_MODELS` registry is good. The UI should continue nudging users toward practical defaults:

- Default: `base` or `base.en` for most English users.
- Low-powered devices: `tiny` or `tiny.en`.
- Higher accuracy: `small`.
- Professional transcript review: `medium` or larger only when hardware and time allow.

Use CPU `int8` by default. Use CUDA `float16` only when GPU detection is confident and the required NVIDIA runtime is present.

### 7. Keep the Upstream Clone as Reference Only

Do not add `D:\code\faster-whisper` to the BITS Whisperer import path. Do not install from the local clone for production builds.

Use the clone for:

- Reading upstream implementation details.
- Checking dependency changes.
- Debugging model behavior.
- Preparing upstream issue reports or patches.

Production installs should continue to use PyPI packages or a pinned direct Git dependency only when there is a specific upstream fix that is not released yet.

## Suggested Next Work Items

1. Recreate the broken BITS Whisperer `.venv`.
2. Install `.[dev,local-whisper]` and run provider tests.
3. Add a slow local Whisper smoke test.
4. Run the verification gates from `CLAUDE.md`.

## Bottom Line

`faster-whisper` is the right local transcription engine for BITS Whisperer. The existing provider architecture is already aligned with it. The safest packaging fix has been applied: CPU `onnxruntime` is no longer excluded from on-demand installation, while the GPU package remains excluded.