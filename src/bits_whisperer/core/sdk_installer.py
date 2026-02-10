"""On-demand SDK installer for provider dependencies.

Installs provider-specific Python packages at runtime when a user first
configures or uses a provider. This keeps the base installer small — only
core dependencies are bundled. Provider SDKs are fetched on first use.

**Frozen-app (PyInstaller) strategy:**

When running as a frozen EXE, ``sys.executable`` points to the app binary,
not a Python interpreter.  Instead of relying on pip or a system Python,
the installer uses ``WheelInstaller`` to download wheels directly from
PyPI and extract them into an isolated ``site-packages`` directory under
``%LOCALAPPDATA%/BITS Whisperer/``.  That directory is prepended to
``sys.path`` at startup via ``init_sdk_path``.

No system Python installation is required.

**Development mode:**

When running from source (``is_frozen() == False``), the installer falls
back to the standard ``pip install`` via ``sys.executable``.

Usage::

    from bits_whisperer.core.sdk_installer import (
        init_sdk_path,
        is_sdk_available,
        ensure_sdk,
        get_provider_sdk_info,
    )

    # At startup — before any provider imports
    init_sdk_path()

    # When user selects a provider
    if not is_sdk_available("openai_whisper"):
        ensure_sdk("openai_whisper", parent_window=frame)
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_to_screen_reader,
)

logger = logging.getLogger(__name__)


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller (or similar) bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


# ---------------------------------------------------------------------------
# Isolated site-packages management
# ---------------------------------------------------------------------------


def _get_site_packages_dir() -> Path:
    """Return the isolated site-packages directory path.

    Imports ``SITE_PACKAGES_DIR`` from constants.  Falls back to a
    sensible default if constants have not been initialised yet (early
    startup).
    """
    try:
        from bits_whisperer.utils.constants import SITE_PACKAGES_DIR

        return SITE_PACKAGES_DIR
    except Exception:
        from platformdirs import user_data_dir

        base = Path(user_data_dir("BITS Whisperer", "BITSWhisperer"))
        sp = base / "site-packages"
        sp.mkdir(parents=True, exist_ok=True)
        return sp


def init_sdk_path() -> None:
    """Prepend the isolated site-packages directory to ``sys.path``.

    Also registers DLL search directories on Windows so that native
    extensions (e.g. ``ctranslate2``, ``numpy``) can find their bundled
    DLLs.

    Call this **once**, as early as possible in the app entrypoint (before
    any provider module is imported), so that on-demand-installed packages
    are discoverable by ``import``.
    """
    sp = _get_site_packages_dir()
    sp_str = str(sp)
    if sp_str not in sys.path:
        sys.path.insert(0, sp_str)
        logger.debug("Prepended isolated site-packages to sys.path: %s", sp_str)

    # Windows: register DLL search directories for native extensions.
    # Since Python 3.8 Windows no longer searches PATH for DLLs when
    # loading extension modules.  Packages like ctranslate2 and numpy
    # bundle their DLLs inside the wheel, so we register those dirs.
    if sys.platform == "win32" and sp.exists() and hasattr(os, "add_dll_directory"):
        _register_dll_dirs(sp)


def _register_dll_dirs(base: Path) -> None:
    """Add directories containing ``.dll`` files to the DLL search path.

    Only scans one level deep (the package directories inside
    ``site-packages``).

    Args:
        base: The isolated site-packages directory.
    """
    with contextlib.suppress(OSError):
        os.add_dll_directory(str(base))
    try:
        for child in base.iterdir():
            if child.is_dir() and any(child.glob("*.dll")):
                with contextlib.suppress(OSError):
                    os.add_dll_directory(str(child))
    except OSError:
        pass


@dataclass(frozen=True)
class SDKInfo:
    """Describes the SDK requirements for a provider."""

    provider_key: str
    display_name: str
    pip_packages: list[str] = field(default_factory=list)
    test_import: str = ""  # Module name to test if installed
    install_size_mb: int = 0  # Approximate installed size


# ---------------------------------------------------------------------------
# Provider SDK registry
# ---------------------------------------------------------------------------

_SDK_REGISTRY: Final[dict[str, SDKInfo]] = {
    "local_whisper": SDKInfo(
        provider_key="local_whisper",
        display_name="Local Whisper (faster-whisper)",
        pip_packages=["faster-whisper>=1.0.0"],
        test_import="faster_whisper",
        install_size_mb=220,
    ),
    "openai_whisper": SDKInfo(
        provider_key="openai_whisper",
        display_name="OpenAI Whisper API",
        pip_packages=["openai>=1.0.0"],
        test_import="openai",
        install_size_mb=30,
    ),
    "google_speech": SDKInfo(
        provider_key="google_speech",
        display_name="Google Cloud Speech-to-Text",
        pip_packages=["google-cloud-speech>=2.20.0"],
        test_import="google.cloud.speech",
        install_size_mb=80,
    ),
    "azure_speech": SDKInfo(
        provider_key="azure_speech",
        display_name="Azure Speech Services",
        pip_packages=["azure-cognitiveservices-speech>=1.32.0"],
        test_import="azure.cognitiveservices.speech",
        install_size_mb=60,
    ),
    "azure_embedded": SDKInfo(
        provider_key="azure_embedded",
        display_name="Azure Embedded Speech",
        pip_packages=["azure-cognitiveservices-speech>=1.32.0"],
        test_import="azure.cognitiveservices.speech",
        install_size_mb=60,
    ),
    "deepgram": SDKInfo(
        provider_key="deepgram",
        display_name="Deepgram Nova-2",
        pip_packages=["deepgram-sdk>=3.0.0"],
        test_import="deepgram",
        install_size_mb=20,
    ),
    "assemblyai": SDKInfo(
        provider_key="assemblyai",
        display_name="AssemblyAI",
        pip_packages=["assemblyai>=0.20.0"],
        test_import="assemblyai",
        install_size_mb=15,
    ),
    "aws_transcribe": SDKInfo(
        provider_key="aws_transcribe",
        display_name="Amazon Transcribe",
        pip_packages=["boto3>=1.28.0"],
        test_import="boto3",
        install_size_mb=120,
    ),
    "gemini": SDKInfo(
        provider_key="gemini",
        display_name="Google Gemini",
        pip_packages=["google-genai>=0.4.0"],
        test_import="google.generativeai",
        install_size_mb=40,
    ),
    "groq_whisper": SDKInfo(
        provider_key="groq_whisper",
        display_name="Groq LPU Whisper",
        pip_packages=["groq>=0.4.0"],
        test_import="groq",
        install_size_mb=15,
    ),
    "rev_ai": SDKInfo(
        provider_key="rev_ai",
        display_name="Rev.ai",
        pip_packages=["rev-ai>=2.17.0"],
        test_import="rev_ai",
        install_size_mb=15,
    ),
    "speechmatics": SDKInfo(
        provider_key="speechmatics",
        display_name="Speechmatics",
        pip_packages=["speechmatics-python>=1.0.0"],
        test_import="speechmatics",
        install_size_mb=10,
    ),
    # Providers that only need httpx (already a core dep): no extra install
    "elevenlabs": SDKInfo(
        provider_key="elevenlabs",
        display_name="ElevenLabs Scribe",
        pip_packages=[],
        test_import="httpx",
        install_size_mb=0,
    ),
    "auphonic": SDKInfo(
        provider_key="auphonic",
        display_name="Auphonic",
        pip_packages=[],
        test_import="httpx",
        install_size_mb=0,
    ),
    "windows_speech": SDKInfo(
        provider_key="windows_speech",
        display_name="Windows Speech",
        pip_packages=[],
        test_import="comtypes",
        install_size_mb=0,
    ),
    "vosk": SDKInfo(
        provider_key="vosk",
        display_name="Vosk Offline Speech",
        pip_packages=["vosk>=0.3.45"],
        test_import="vosk",
        install_size_mb=25,
    ),
    "parakeet": SDKInfo(
        provider_key="parakeet",
        display_name="NVIDIA Parakeet (NeMo)",
        pip_packages=["nemo_toolkit[asr]>=2.0.0"],
        test_import="nemo",
        install_size_mb=2000,
    ),
    "copilot_sdk": SDKInfo(
        provider_key="copilot_sdk",
        display_name="GitHub Copilot SDK",
        pip_packages=["github-copilot-sdk>=0.1.0"],
        test_import="copilot",
        install_size_mb=110,
    ),
}


def get_provider_sdk_info(provider_key: str) -> SDKInfo | None:
    """Look up SDK info for a provider.

    Args:
        provider_key: Provider identifier (e.g. ``"openai_whisper"``).

    Returns:
        SDKInfo or None if the provider has no special SDK needs.
    """
    return _SDK_REGISTRY.get(provider_key)


def is_sdk_available(provider_key: str) -> bool:
    """Check whether the SDK for a provider is importable.

    Args:
        provider_key: Provider identifier.

    Returns:
        True if the required package can be imported.
    """
    info = _SDK_REGISTRY.get(provider_key)
    if info is None:
        return True  # Unknown provider — assume fine

    if not info.test_import:
        return True  # No import required

    try:
        importlib.import_module(info.test_import)
        return True
    except ImportError:
        return False


def get_missing_sdks() -> list[SDKInfo]:
    """Return SDKInfo for all providers whose SDK is not installed.

    Returns:
        List of SDKInfo for providers with missing packages.
    """
    missing: list[SDKInfo] = []
    for key, info in _SDK_REGISTRY.items():
        if (
            info.pip_packages
            and not is_sdk_available(key)
            # Deduplicate (e.g. azure_speech + azure_embedded share a package)
            and not any(m.test_import == info.test_import for m in missing)
        ):
            missing.append(info)
    return missing


def install_sdk(
    provider_key: str,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Install the SDK packages for a provider.

    In frozen mode, downloads wheels directly from PyPI and extracts
    them into the isolated ``SITE_PACKAGES_DIR`` (no pip or system
    Python required).  In dev mode, shells out to ``pip install``.

    Args:
        provider_key: Provider identifier.
        progress_callback: Optional callable receiving status strings.

    Returns:
        Tuple of ``(success, error_message)``.
    """
    info = _SDK_REGISTRY.get(provider_key)
    if info is None:
        return False, f"Unknown provider: {provider_key}"

    if not info.pip_packages:
        return True, ""  # Nothing to install

    if is_sdk_available(provider_key):
        return True, ""  # Already installed

    packages_str = " ".join(info.pip_packages)
    target_dir = _get_site_packages_dir()

    if progress_callback:
        progress_callback(f"Installing {info.display_name} SDK ({packages_str})…")

    logger.info(
        "Installing SDK for %s: %s (frozen=%s, target=%s)",
        provider_key,
        packages_str,
        is_frozen(),
        target_dir if is_frozen() else "default",
    )

    # --- Frozen: use WheelInstaller (no pip needed) ---
    if is_frozen():
        return _install_frozen(info, target_dir, progress_callback)

    # --- Dev mode: use pip directly ---
    return _install_dev(info, packages_str)


def _install_frozen(
    info: SDKInfo,
    target_dir: Path,
    progress_callback: Callable[[str], None] | None,
) -> tuple[bool, str]:
    """Install via WheelInstaller (frozen builds)."""
    from bits_whisperer.core.wheel_installer import WheelInstaller

    installer = WheelInstaller(target_dir)
    success, error = installer.install(info.pip_packages, progress_callback)

    if success:
        importlib.invalidate_caches()
        init_sdk_path()  # Ensure DLL dirs are registered
        logger.info("SDK for %s installed successfully (wheel)", info.provider_key)
    else:
        logger.warning("Wheel install failed for %s: %s", info.provider_key, error)

    return success, error


def _install_dev(info: SDKInfo, packages_str: str) -> tuple[bool, str]:
    """Install via ``pip install`` (dev / source runs)."""
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", *info.pip_packages]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
        )
        if result.returncode == 0:
            importlib.invalidate_caches()
            logger.info("SDK for %s installed successfully (pip)", info.provider_key)
            return True, ""
        error = result.stderr.strip() or result.stdout.strip()
        logger.warning("pip install failed for %s: %s", info.provider_key, error)
        return False, error
    except subprocess.TimeoutExpired:
        return False, "Installation timed out (10 minutes)"
    except Exception as exc:
        return False, str(exc)


def uninstall_sdk(provider_key: str) -> tuple[bool, str]:
    """Remove an SDK's packages from the isolated site-packages directory.

    In frozen mode, deletes the package directories and ``.dist-info``
    folders directly.  In dev mode, hints to use ``pip uninstall``.

    Args:
        provider_key: Provider identifier.

    Returns:
        Tuple of ``(success, error_message)``.
    """
    if not is_frozen():
        return False, "Use pip uninstall directly when running from source."

    info = _SDK_REGISTRY.get(provider_key)
    if info is None:
        return False, f"Unknown provider: {provider_key}"

    if not info.pip_packages:
        return True, ""

    sp = _get_site_packages_dir()
    if not sp.exists():
        return True, ""

    try:
        for pkg_spec in info.pip_packages:
            # Strip version specifiers to bare package name
            name = pkg_spec.split(">=")[0].split("==")[0].split("<")[0].strip()
            norm = name.lower().replace("-", "_").replace(".", "_")
            _purge_package(sp, norm)

        importlib.invalidate_caches()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _purge_package(sp: Path, norm_name: str) -> None:
    """Delete all directories belonging to *norm_name* from *sp*.

    Removes both the importable package directory and any
    ``.dist-info`` metadata directory.

    Args:
        sp: Site-packages directory.
        norm_name: Normalised package name (lowercase, underscores).
    """
    for item in list(sp.iterdir()):
        if not item.is_dir():
            continue
        item_norm = item.name.lower().replace("-", "_")
        # Match dist-info directories: <name>-<version>.dist-info
        if item_norm.endswith((".dist_info", ".dist-info")):
            pkg_part = item_norm.rsplit("-", 1)[0] if "-" in item_norm else item_norm
            # dist-info names have version: e.g. "openai-1.82.0.dist-info"
            # After rsplit we get "openai_1.82.0" — split once more
            pkg_part = pkg_part.split("-")[0].replace(".", "_")
            if pkg_part == norm_name:
                shutil.rmtree(item, ignore_errors=True)
                continue
        # Match importable package directory (exact name match)
        if item_norm == norm_name:
            shutil.rmtree(item, ignore_errors=True)


def get_installed_sdk_size_mb() -> float:
    """Return total size of the isolated site-packages directory in MB.

    Returns:
        Size in megabytes, or 0.0 if the directory doesn't exist.
    """
    sp = _get_site_packages_dir()
    if not sp.exists():
        return 0.0
    total = sum(f.stat().st_size for f in sp.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


def ensure_sdk(provider_key: str, parent_window=None) -> bool:
    """Check for and install the SDK for a provider, prompting the user.

    Shows a wx dialog to confirm before installing. If already installed,
    returns True immediately.

    Args:
        provider_key: Provider identifier.
        parent_window: Optional wx parent window for dialogs.

    Returns:
        True if the SDK is available after this call.
    """
    if is_sdk_available(provider_key):
        return True

    info = _SDK_REGISTRY.get(provider_key)
    if info is None or not info.pip_packages:
        return True

    import wx

    packages_str = ", ".join(info.pip_packages)
    msg = (
        f"The {info.display_name} provider requires additional packages:\n\n"
        f"  {packages_str}\n\n"
        f"Approximate download size: ~{info.install_size_mb} MB\n\n"
        "Packages will be downloaded from PyPI and installed to a\n"
        "local folder managed by BITS Whisperer.\n\n"
        "Would you like to install them now? "
        "This only needs to happen once."
    )

    dlg = wx.MessageDialog(
        parent_window,
        msg,
        f"Install {info.display_name} SDK",
        wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
    )
    announce_to_screen_reader(f"Install {info.display_name} SDK? {msg}")
    answer = dlg.ShowModal()
    dlg.Destroy()

    if answer != wx.ID_YES:
        return False

    # Install with progress dialog
    progress = wx.ProgressDialog(
        f"Installing {info.display_name}",
        f"Installing {packages_str}…\nThis may take a minute.",
        maximum=100,
        parent=parent_window,
        style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT,
    )
    progress.Pulse()

    result_holder: list[tuple[bool, str]] = [(False, "")]

    def _do_install() -> None:
        result_holder[0] = install_sdk(provider_key)
        wx.CallAfter(progress.Destroy)

    t = threading.Thread(target=_do_install, daemon=True)
    t.start()

    while t.is_alive():
        wx.MilliSleep(200)
        cont, _ = progress.Pulse()
        if not cont:
            break
        wx.GetApp().Yield()

    t.join(timeout=5)

    with contextlib.suppress(Exception):
        if not progress.WasCancelled():
            progress.Destroy()

    success, error = result_holder[0]

    if success:
        accessible_message_box(
            f"{info.display_name} SDK installed successfully!\n\n"
            "The provider is now ready to use.",
            "Installation Complete",
            wx.OK | wx.ICON_INFORMATION,
            parent_window,
        )
    else:
        sp = _get_site_packages_dir()
        fallback_msg = (
            f"Failed to install {info.display_name} SDK.\n\n"
            f"Error: {error}\n\n"
            "You can try installing manually:\n"
        )
        if is_frozen():
            fallback_msg += f'  pip install --target "{sp}" {packages_str}'
        else:
            fallback_msg += f"  pip install {packages_str}"

        accessible_message_box(
            fallback_msg,
            "Installation Failed",
            wx.OK | wx.ICON_WARNING,
            parent_window,
        )

    return success
