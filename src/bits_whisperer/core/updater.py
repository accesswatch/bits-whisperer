"""Self-updater that checks GitHub Releases for new versions.

Workflow
--------
1. ``check_for_update()`` — hits the GitHub Releases API, compares the
   latest tag against ``APP_VERSION``.
2. If a newer release is found, returns an ``UpdateInfo`` with download
   URL, release notes, etc.
3. ``download_and_apply()`` — downloads the installer/archive, saves it
   to a temp location, and launches it (for `.exe`/`.msi`) or extracts
   in-place (for `.zip`).

This module uses **httpx** (already a project dependency) for HTTP and
``packaging.version`` for semantic version comparison.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    latest_version: str
    tag_name: str
    release_name: str
    release_notes: str
    download_url: str
    download_size_mb: float
    html_url: str  # browser link to release page
    published_at: str


class Updater:
    """Check for and apply application updates from GitHub Releases.

    Args:
        repo_owner: GitHub organisation or user (e.g. ``"myorg"``).
        repo_name: Repository name (e.g. ``"bits-whisperer"``).
        current_version: Semver string of the running application.
        asset_pattern: Glob-style suffix to match the correct release
            asset (e.g. ``".exe"``, ``"-win64.zip"``).
    """

    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        current_version: str,
        asset_pattern: str = ".exe",
    ) -> None:
        """Initialise the updater for a GitHub repository."""
        self._owner = repo_owner
        self._repo = repo_name
        self._current = current_version
        self._asset_pattern = asset_pattern
        self._api_base = f"https://api.github.com/repos" f"/{repo_owner}/{repo_name}"
        self._latest_info: UpdateInfo | None = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def check_for_update(self, timeout: float = 15.0) -> UpdateInfo | None:
        """Query GitHub for the latest release.

        Returns:
            ``UpdateInfo`` if a newer version is available, else ``None``.
        """
        try:
            from packaging.version import Version
        except ImportError:
            logger.warning("packaging not installed — cannot compare versions")
            return None

        url = f"{self._api_base}/releases/latest"
        logger.info("Checking for updates: %s", url)

        try:
            resp = httpx.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                timeout=timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Update check failed: %s", exc)
            return None

        data = resp.json()
        tag = data.get("tag_name", "").lstrip("v")

        try:
            latest = Version(tag)
            current = Version(self._current)
        except Exception:
            logger.warning(
                "Cannot parse versions: current=%s latest=%s",
                self._current,
                tag,
            )
            return None

        if latest <= current:
            logger.info(
                "Up to date (current=%s, latest=%s)",
                current,
                latest,
            )
            return None

        # Find matching asset
        download_url = ""
        download_size = 0.0
        for asset in data.get("assets", []):
            name: str = asset.get("name", "")
            if name.endswith(self._asset_pattern):
                download_url = asset.get("browser_download_url", "")
                download_size = asset.get("size", 0) / (1024 * 1024)
                break

        if not download_url:
            # Fall back to the release page itself
            download_url = data.get("html_url", "")

        info = UpdateInfo(
            current_version=str(current),
            latest_version=str(latest),
            tag_name=data.get("tag_name", ""),
            release_name=data.get("name", ""),
            release_notes=data.get("body", ""),
            download_url=download_url,
            download_size_mb=round(download_size, 1),
            html_url=data.get("html_url", ""),
            published_at=data.get("published_at", ""),
        )
        self._latest_info = info
        logger.info(
            "Update available: %s to %s (%s)",
            info.current_version,
            info.latest_version,
            info.download_url,
        )
        return info

    def download_update(
        self,
        info: UpdateInfo | None = None,
        dest_dir: str | Path | None = None,
        progress_callback: Callable[[float, float], None] | None = None,
    ) -> Path:
        """Download the release asset to a local file.

        Args:
            info: UpdateInfo from ``check_for_update()``. Uses cached
                info if ``None``.
            dest_dir: Directory to save the file. Defaults to temp dir.
            progress_callback: Optional ``(downloaded_mb, total_mb) -> None``.

        Returns:
            Path to the downloaded file.

        Raises:
            RuntimeError: If download fails.
        """
        info = info or self._latest_info
        if not info:
            raise RuntimeError("No update info — call check_for_update() first.")

        if not info.download_url:
            raise RuntimeError("No download URL in update info.")

        dest = Path(dest_dir or tempfile.mkdtemp(prefix="bw_update_"))
        dest.mkdir(parents=True, exist_ok=True)

        filename = info.download_url.rsplit("/", 1)[-1]
        file_path = dest / filename
        total = info.download_size_mb

        logger.info("Downloading update: %s (%.1f MB)", filename, total)

        try:
            with httpx.stream(
                "GET",
                info.download_url,
                follow_redirects=True,
                timeout=300.0,
            ) as resp:
                resp.raise_for_status()
                downloaded = 0
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            progress_callback(downloaded / (1024 * 1024), total)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Download failed: {exc}") from exc

        logger.info("Downloaded update to: %s", file_path)
        return file_path

    def launch_installer(self, file_path: str | Path) -> None:
        """Launch the downloaded installer and exit the current process.

        Args:
            file_path: Path to the downloaded ``.exe`` or ``.msi``.
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        logger.info("Launching installer: %s", file_path)

        if suffix == ".msi":
            subprocess.Popen(["msiexec", "/i", str(file_path)])
        elif suffix == ".exe":
            subprocess.Popen([str(file_path)])
        else:
            # Fall back to OS default handler
            from bits_whisperer.utils.platform_utils import open_file_or_folder

            open_file_or_folder(file_path)

    def open_release_page(self, info: UpdateInfo | None = None) -> None:
        """Open the release page in the default browser.

        Args:
            info: UpdateInfo, or uses cached info.
        """
        import webbrowser

        info = info or self._latest_info
        if info and info.html_url:
            webbrowser.open(info.html_url)
