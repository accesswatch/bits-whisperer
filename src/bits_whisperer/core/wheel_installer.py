"""Lightweight wheel installer — no pip or system Python required.

Downloads Python wheel packages directly from PyPI and extracts them
to a local ``site-packages`` directory, resolving transitive dependencies
automatically.

This module uses only:

* ``httpx`` — HTTP client (bundled with the app)
* ``packaging`` — wheel tag matching, version parsing (bundled)
* ``zipfile`` / ``tempfile`` / ``shutil`` — stdlib

It is designed specifically for frozen (PyInstaller) applications where
``sys.executable`` is the app binary and ``pip`` is not available.

Usage::

    from bits_whisperer.core.wheel_installer import WheelInstaller
    from bits_whisperer.utils.constants import SITE_PACKAGES_DIR

    installer = WheelInstaller(SITE_PACKAGES_DIR)
    success, error = installer.install(["openai>=1.0.0"])
"""

from __future__ import annotations

import importlib
import logging
import platform
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_DEP_DEPTH: Final[int] = 12
_PYPI_JSON: Final[str] = "https://pypi.org/pypi"
_USER_AGENT: Final[str] = "BITS-Whisperer/1.0 (https://github.com/BITSWhisperer/bits-whisperer)"

# Packages bundled with the frozen app — never download these.
# Names are normalised (lowercase, underscores).
_BUNDLED: Final[frozenset[str]] = frozenset(
    {
        # Direct deps from pyproject.toml
        "keyring",
        "platformdirs",
        "psutil",
        "pydub",
        "packaging",
        "markdown",
        "jinja2",
        "docx",
        "python_docx",
        "httpx",
        "wx",
        "wxpython",
        "winsdk",
        "comtypes",
        # Transitive deps of core packages
        "certifi",
        "idna",
        "sniffio",
        "anyio",
        "httpcore",
        "h11",
        "typing_extensions",
        "markupsafe",
        "pywin32_ctypes",
        "jaraco_classes",
        "jaraco_functools",
        "jaraco_context",
        "more_itertools",
        "importlib_metadata",
        "zipp",
        "colorama",
        # Build / meta — never needed at runtime
        "pip",
        "setuptools",
        "wheel",
        "pkg_resources",
    }
)

# Heavy packages that should NEVER be downloaded — they are either
# not needed at all (torch, tensorflow) or optional extras that the
# providers do not use.  Normalised names.
_EXCLUDED: Final[frozenset[str]] = frozenset(
    {
        # ML frameworks — faster-whisper uses CTranslate2, not torch
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorflow_gpu",
        "keras",
        # ONNX — optional extra for ctranslate2, not required
        "onnxruntime",
        "onnxruntime_gpu",
        "onnx",
        # Other large scientific stacks never needed at runtime
        "scipy",
        "scikit_learn",
        "sklearn",
        "pandas",
        "pyarrow",
        "matplotlib",
        "pillow",
        "pil",
        "numba",
        "llvmlite",
        "transformers",
        "accelerate",
        "peft",
        "diffusers",
        "datasets",
        "safetensors",
        "sentencepiece",
        # Dev / test tools
        "pytest",
        "black",
        "ruff",
        "mypy",
        "pylint",
        "coverage",
    }
)

# Type alias for progress callbacks
ProgressCB = Callable[[str], None] | None


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    """Normalise a Python package name for comparison."""
    return name.lower().replace("-", "_").replace(".", "_")


# ---------------------------------------------------------------------------
# Platform tag computation
# ---------------------------------------------------------------------------

_tag_cache: set[str] | None = None


def compatible_tags() -> set[str]:
    """Return all wheel tags compatible with the current platform.

    Tries ``packaging.tags.sys_tags()`` first (robust, version-aware)
    and falls back to manual computation if that fails (which can
    happen in some frozen environments).

    Returns:
        Set of tag strings like ``"cp313-cp313-win_amd64"``.
    """
    global _tag_cache
    if _tag_cache is not None:
        return _tag_cache

    try:
        from packaging.tags import sys_tags

        tags = {str(t) for t in sys_tags()}
        if tags:
            _tag_cache = tags
            return _tag_cache
    except Exception:
        pass

    _tag_cache = _fallback_tags()
    return _tag_cache


def _fallback_tags() -> set[str]:
    """Compute compatible wheel tags manually.

    Used when ``packaging.tags`` is unavailable or gives empty results.
    """
    vi = sys.version_info
    py_tags = [
        f"cp{vi.major}{vi.minor}",
        f"cp{vi.major}",
        f"py{vi.major}{vi.minor}",
        f"py{vi.major}",
        "py3",
    ]
    abi_tags = [f"cp{vi.major}{vi.minor}", "abi3", "none"]
    plat_tags = _platform_tags() + ["any"]

    result: set[str] = set()
    for py in py_tags:
        for abi in abi_tags:
            for plat in plat_tags:
                result.add(f"{py}-{abi}-{plat}")
    return result


def _platform_tags() -> list[str]:
    """Return platform-specific wheel tag parts."""
    s = platform.system().lower()
    m = platform.machine().lower()
    tags: list[str] = []

    if s == "windows":
        arch_map = {
            "amd64": "win_amd64",
            "x86_64": "win_amd64",
            "x86": "win32",
            "arm64": "win_arm64",
        }
        tag = arch_map.get(m)
        if tag:
            tags.append(tag)

    elif s == "darwin":
        if m == "arm64":
            for v in range(15, 10, -1):
                tags.append(f"macosx_{v}_0_arm64")
                tags.append(f"macosx_{v}_0_universal2")
        else:
            for v in range(15, 10, -1):
                tags.append(f"macosx_{v}_0_x86_64")
                tags.append(f"macosx_{v}_0_universal2")
            for minor in range(15, 8, -1):
                tags.append(f"macosx_10_{minor}_x86_64")
                tags.append(f"macosx_10_{minor}_universal2")

    elif s == "linux":
        arch_map = {"x86_64": "x86_64", "aarch64": "aarch64"}
        if m in arch_map:
            arch = arch_map[m]
            for glibc_minor in (17, 24, 27, 28, 31, 34, 35, 36, 38, 39):
                tags.append(f"manylinux_2_{glibc_minor}_{arch}")
            tags.append(f"linux_{arch}")

    return tags


def _wheel_is_compatible(filename: str) -> bool:
    """Check if a wheel filename is compatible with the current platform.

    Args:
        filename: Wheel filename (e.g. ``foo-1.0-cp313-cp313-win_amd64.whl``).

    Returns:
        True if at least one of the wheel's tags is compatible.
    """
    stem = filename
    if stem.endswith(".whl"):
        stem = stem[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        return False

    py_part = parts[-3]
    abi_part = parts[-2]
    plat_part = parts[-1]
    ctags = compatible_tags()

    for py in py_part.split("."):
        for abi in abi_part.split("."):
            for plat in plat_part.split("."):
                if f"{py}-{abi}-{plat}" in ctags:
                    return True
    return False


# ---------------------------------------------------------------------------
# WheelInstaller
# ---------------------------------------------------------------------------


class WheelInstaller:
    """Download and install Python wheels from PyPI.

    Does not require ``pip`` or a system Python installation.
    Uses ``httpx`` for HTTPS downloads and stdlib ``zipfile`` for
    extraction.

    Example::

        installer = WheelInstaller(Path("~/.myapp/site-packages"))
        ok, err = installer.install(["openai>=1.0.0"])
    """

    def __init__(self, target_dir: Path) -> None:
        """Initialise installer with a target directory.

        Args:
            target_dir: Directory to extract wheels into.
        """
        self._target = target_dir
        self._target.mkdir(parents=True, exist_ok=True)
        self._done: set[str] = set()
        self._tmp = Path(tempfile.gettempdir()) / "bw_wheels"
        self._tmp.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def install(
        self,
        requirements: list[str],
        progress_cb: ProgressCB = None,
    ) -> tuple[bool, str]:
        """Install packages and their transitive dependencies.

        Args:
            requirements: List of pip-style requirement strings
                (e.g. ``["openai>=1.0.0"]``).
            progress_cb: Optional callback receiving status messages.

        Returns:
            ``(success, error_message)`` tuple.
        """
        try:
            for req_str in requirements:
                self._install_one(req_str, progress_cb)
            return True, ""
        except Exception as exc:
            logger.error("Wheel install failed: %s", exc)
            return False, str(exc)
        finally:
            self._cleanup()

    # ---------------------------------------------------------------
    # Internal — resolution + install
    # ---------------------------------------------------------------

    def _install_one(
        self,
        req_str: str,
        cb: ProgressCB,
        depth: int = 0,
    ) -> None:
        """Install a single requirement and recurse for deps."""
        if depth > _MAX_DEP_DEPTH:
            logger.warning(
                "Dep depth limit reached at %s",
                req_str,
            )
            return

        from packaging.requirements import Requirement

        req = Requirement(req_str)
        name = _norm(req.name)

        # Already handled this session
        if name in self._done:
            return

        # Evaluate environment markers on the requirement itself
        if req.marker and not req.marker.evaluate():
            self._done.add(name)
            return

        # Skip excluded heavy packages
        if name in _EXCLUDED:
            logger.debug("Skipping excluded package: %s", name)
            self._done.add(name)
            return

        # Already satisfied (bundled or previously installed)
        if self._is_satisfied(name):
            self._done.add(name)
            return

        if cb:
            cb(f"Resolving {req.name}…")

        # Query PyPI
        pypi_data = self._query_pypi(req.name)
        version, url, filename, size = self._pick_wheel(
            pypi_data,
            req.specifier,
        )

        if cb:
            size_mb = round(size / (1024 * 1024), 1) if size else 0
            cb(f"Downloading {req.name} {version} ({size_mb} MB)…")

        # Download
        wheel_path = self._download(url, filename)

        # Read transitive dependencies before extracting
        deps = self._read_deps(wheel_path)

        if cb:
            cb(f"Installing {req.name} {version}…")

        # Extract wheel contents into target directory
        self._extract(wheel_path)
        wheel_path.unlink(missing_ok=True)

        self._done.add(name)

        # Recurse for transitive dependencies
        for dep_str in deps:
            self._install_one(dep_str, cb, depth + 1)

    # ---------------------------------------------------------------
    # PyPI queries
    # ---------------------------------------------------------------

    def _query_pypi(self, package_name: str) -> dict[str, Any]:
        """Fetch package metadata from PyPI JSON API.

        Args:
            package_name: Package name as listed on PyPI.

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: If the request fails.
        """
        url = f"{_PYPI_JSON}/{package_name}/json"
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=30,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                r = client.get(url)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                raise RuntimeError(f"Package '{package_name}' " "not found on PyPI.") from exc
            raise RuntimeError(f"PyPI request failed for '{package_name}': HTTP {status}") from exc
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise RuntimeError("Cannot reach PyPI (pypi.org). Check your internet connection.")
        except Exception as exc:
            raise RuntimeError(f"Failed to query PyPI for " f"'{package_name}': {exc}") from exc

    def _pick_wheel(
        self,
        pypi_data: dict[str, Any],
        specifier: Any,
    ) -> tuple[str, str, str, int]:
        """Choose the best compatible wheel from PyPI release data.

        Args:
            pypi_data: Parsed PyPI JSON response.
            specifier: ``packaging.specifiers.SpecifierSet`` or None.

        Returns:
            ``(version, download_url, filename, size_bytes)``

        Raises:
            RuntimeError: If no compatible wheel is found.
        """
        from packaging.version import Version

        releases = pypi_data.get("releases", {})
        pkg_name = pypi_data.get("info", {}).get("name", "unknown")

        # Walk versions newest-first
        for ver_str in sorted(releases.keys(), key=Version, reverse=True):
            try:
                ver = Version(ver_str)
            except Exception:
                continue
            if ver.is_prerelease or ver.is_devrelease:
                continue
            if specifier and not specifier.contains(ver):
                continue

            wheel = self._best_wheel_in_release(releases[ver_str])
            if wheel is not None:
                return (
                    ver_str,
                    wheel["url"],
                    wheel["filename"],
                    wheel.get("size", 0),
                )

        raise RuntimeError(
            f"No compatible wheel found for {pkg_name} "
            f"on {platform.system()} {platform.machine()}. "
            f"Version specifier: {specifier or 'any'}"
        )

    def _best_wheel_in_release(
        self,
        files: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Pick the best compatible wheel from a release's file list.

        Prefers platform-specific (native) wheels over pure-Python ones.

        Args:
            files: List of file dicts from the PyPI release.

        Returns:
            Best file dict, or None.
        """
        native: list[dict[str, Any]] = []
        pure: list[dict[str, Any]] = []

        for f in files:
            fn = f.get("filename", "")
            if not fn.endswith(".whl"):
                continue
            if not _wheel_is_compatible(fn):
                continue
            if "none-any" in fn:
                pure.append(f)
            else:
                native.append(f)

        # Prefer native wheels (contain compiled extensions)
        if native:
            return native[0]
        if pure:
            return pure[0]
        return None

    # ---------------------------------------------------------------
    # Download
    # ---------------------------------------------------------------

    def _download(self, url: str, filename: str) -> Path:
        """Download a wheel file to a temp directory.

        Streams the download to avoid holding large files in memory.

        Args:
            url: Download URL from PyPI.
            filename: Wheel filename.

        Returns:
            Path to the downloaded wheel file.

        Raises:
            RuntimeError: If download fails or produces an invalid zip.
        """
        dest = self._tmp / filename
        if dest.exists():
            dest.unlink()

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30),
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                with client.stream("GET", url) as r:
                    r.raise_for_status()
                    with dest.open("wb") as f:
                        for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Download failed: {filename}: " f"{exc}") from exc

        if not zipfile.is_zipfile(dest):
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded file is not a valid " f"wheel: {filename}")

        return dest

    # ---------------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------------

    def _extract(self, wheel_path: Path) -> None:
        """Extract wheel contents into the target directory.

        Handles ``.data/`` directories according to the wheel spec:
        ``purelib`` and ``platlib`` are extracted to the target root;
        ``scripts``, ``headers``, and ``data`` are skipped.

        Args:
            wheel_path: Path to the ``.whl`` file.
        """
        with zipfile.ZipFile(wheel_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue

                path = info.filename

                # Handle .data directories
                if ".data/" in path:
                    target = self._resolve_data_path(path)
                    if target is None:
                        continue  # skip scripts/headers/data
                else:
                    target = self._target / path

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    def _resolve_data_path(self, path: str) -> Path | None:
        """Map a ``.data/`` wheel path to the extraction target.

        Only ``purelib/`` and ``platlib/`` subdirectories are extracted.

        Args:
            path: Zip entry path, e.g. ``pkg-1.0.data/purelib/pkg/mod.py``.

        Returns:
            Target path, or None to skip.
        """
        parts = path.split("/")
        data_idx = next(
            (i for i, p in enumerate(parts) if p.endswith(".data")),
            None,
        )
        if data_idx is None or data_idx + 1 >= len(parts):
            return None

        subdir = parts[data_idx + 1]
        if subdir not in ("purelib", "platlib"):
            return None

        remainder = "/".join(parts[data_idx + 2 :])
        if not remainder:
            return None
        return self._target / remainder

    # ---------------------------------------------------------------
    # Dependency reading
    # ---------------------------------------------------------------

    def _read_deps(self, wheel_path: Path) -> list[str]:
        """Read ``Requires-Dist`` entries from wheel METADATA.

        Evaluates environment markers and skips extra-only, bundled,
        and platform-incompatible dependencies.

        Args:
            wheel_path: Path to the ``.whl`` file.

        Returns:
            List of requirement strings to install.
        """
        deps: list[str] = []
        try:
            with zipfile.ZipFile(wheel_path, "r") as zf:
                meta_name = next(
                    (n for n in zf.namelist() if n.endswith(".dist-info/METADATA")),
                    None,
                )
                if meta_name is None:
                    return deps
                raw = zf.read(meta_name).decode("utf-8")
                self._parse_requires_dist(raw, deps)
        except Exception as exc:
            logger.warning("Could not read wheel dependencies: %s", exc)
        return deps

    def _parse_requires_dist(self, metadata: str, out: list[str]) -> None:
        """Parse ``Requires-Dist`` lines from METADATA text.

        Args:
            metadata: Raw METADATA file contents.
            out: List to append requirement strings to.
        """
        from packaging.requirements import Requirement

        for line in metadata.splitlines():
            if not line.startswith("Requires-Dist:"):
                continue

            req_str = line[len("Requires-Dist:") :].strip()
            try:
                req = Requirement(req_str)
            except Exception:
                continue

            # Skip extra-only dependencies
            if req.marker:
                marker_str = str(req.marker)
                if "extra ==" in marker_str or "extra !=" in marker_str:
                    continue
                # Evaluate remaining environment markers
                if not req.marker.evaluate():
                    continue

            # Skip packages bundled with or excluded from the app
            norm_name = _norm(req.name)
            if norm_name in _BUNDLED or norm_name in _EXCLUDED:
                continue

            out.append(str(req))

    # ---------------------------------------------------------------
    # Satisfaction check
    # ---------------------------------------------------------------

    def _is_satisfied(self, name_normalised: str) -> bool:
        """Check if a package is already available.

        Checks (in order):
        1. Bundled with the app (in ``_BUNDLED``)
        2. Already installed in the target directory (has ``.dist-info``)
        3. Importable via any other path on ``sys.path``

        Args:
            name_normalised: Normalised package name.

        Returns:
            True if the package should be skipped.
        """
        if name_normalised in _BUNDLED:
            return True

        # Check for .dist-info in target directory
        try:
            for entry in self._target.iterdir():
                if (
                    entry.is_dir()
                    and entry.name.endswith(".dist-info")
                    and _norm(entry.name.rsplit("-", 1)[0]) == name_normalised
                ):
                    return True
        except OSError:
            pass

        # Try importing (covers bundled packages without dist-info)
        for mod_name in (name_normalised, name_normalised.replace("_", ".")):
            try:
                importlib.import_module(mod_name)
                return True
            except ImportError:
                pass

        return False

    # ---------------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------------

    def _cleanup(self) -> None:
        """Remove temporary download directory."""
        shutil.rmtree(self._tmp, ignore_errors=True)
