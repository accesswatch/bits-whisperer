"""Cross-platform utility helpers.

Provides portable alternatives for Windows-only APIs such as
``os.startfile()`` and platform-aware disk-space checks.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_WINDOWS: bool = sys.platform == "win32"
IS_MACOS: bool = sys.platform == "darwin"
IS_LINUX: bool = sys.platform.startswith("linux")


def open_file_or_folder(path: str | Path) -> None:
    """Open a file or folder with the OS default handler.

    Works on Windows, macOS, and Linux.

    Args:
        path: Path to a file or directory.
    """
    path_str = str(path)
    try:
        if IS_WINDOWS:
            os.startfile(path_str)  # type: ignore[attr-defined]  # noqa: S606
        elif IS_MACOS:
            subprocess.Popen(["open", path_str])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", path_str])  # noqa: S603,S607
    except Exception:
        logger.warning("Failed to open: %s", path_str)


def get_free_disk_space_mb(path: str | Path) -> float:
    """Return free disk space in MB for the volume containing *path*.

    Args:
        path: Any path on the target volume.

    Returns:
        Free space in megabytes, or 0.0 on failure.
    """
    try:
        usage = shutil.disk_usage(str(path))
        return round(usage.free / (1024 * 1024), 1)
    except Exception:
        logger.debug("Could not determine free disk space for %s", path)
        return 0.0


def get_free_disk_space_gb(path: str | Path) -> float:
    """Return free disk space in GB for the volume containing *path*.

    Args:
        path: Any path on the target volume.

    Returns:
        Free space in gigabytes, or 0.0 on failure.
    """
    return round(get_free_disk_space_mb(path) / 1024, 2)


def has_sufficient_disk_space(path: str | Path, required_mb: float) -> bool:
    """Check whether the volume has at least *required_mb* free space.

    Args:
        path: Any path on the target volume.
        required_mb: Required free space in megabytes.

    Returns:
        True if enough space is available.
    """
    free = get_free_disk_space_mb(path)
    return free >= required_mb


def detect_cpu_features() -> dict[str, bool]:
    """Detect CPU instruction set features (AVX, AVX2).

    Returns:
        Dict with ``"avx"`` and ``"avx2"`` boolean flags.
    """
    result = {"avx": False, "avx2": False}

    system = platform.system()

    if system == "Linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            flags_line = ""
            for line in cpuinfo.splitlines():
                if line.startswith("flags"):
                    flags_line = line.lower()
                    break
            result["avx"] = " avx " in f" {flags_line} " or "avx" in flags_line
            result["avx2"] = " avx2 " in f" {flags_line} " or "avx2" in flags_line
        except Exception:
            # Assume modern CPU
            result["avx"] = True
            result["avx2"] = True

    elif system == "Darwin":
        # macOS: use sysctl
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.features"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            features = out.upper()
            result["avx"] = "AVX1.0" in features or "AVX " in features
            result["avx2"] = "AVX2" in features

            # Also check leaf7 features for AVX2 on some macOS versions
            try:
                leaf7 = subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.leaf7_features"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                )
                if "AVX2" in leaf7.upper():
                    result["avx2"] = True
            except Exception:
                pass

        except Exception:
            # Apple Silicon (ARM) doesn't have AVX but faster-whisper
            # works via Rosetta 2 or native ARM builds
            try:
                arch = subprocess.check_output(
                    ["uname", "-m"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                ).strip()
                if arch == "arm64":
                    # ARM Macs can still run faster-whisper, no AVX needed
                    result["avx"] = True
                    result["avx2"] = True
            except Exception:
                result["avx"] = True
                result["avx2"] = True

    else:
        # Windows or unknown: assume modern CPU has AVX
        result["avx"] = True
        result["avx2"] = True

    return result


def detect_gpu() -> tuple[bool, str, float]:
    """Detect NVIDIA CUDA GPU availability.

    Returns:
        (has_cuda, gpu_name, vram_gb)
    """
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        lines = output.strip().split("\n")
        if lines and lines[0]:
            parts = lines[0].split(",")
            name = parts[0].strip()
            vram_mb = float(parts[1].strip()) if len(parts) > 1 else 0
            vram_gb = round(vram_mb / 1024, 1)
            return True, name, vram_gb
    except Exception:
        pass

    # Check for Apple Silicon GPU (Metal) on macOS
    if IS_MACOS:
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            # Apple Silicon has unified memory, report it
            if "Apple" in out:
                for line in out.splitlines():
                    if "Chipset Model" in line or "Chip" in line:
                        name = line.split(":")[-1].strip()
                        # Apple Silicon uses unified memory — report total RAM
                        # as available for ML workloads
                        import psutil

                        mem = psutil.virtual_memory()
                        # Roughly half of unified memory can be used for GPU
                        gpu_mem_gb = round(mem.total / (1024**3) * 0.5, 1)
                        return False, f"{name} (Metal)", gpu_mem_gb
        except Exception:
            pass

    return False, "", 0.0
