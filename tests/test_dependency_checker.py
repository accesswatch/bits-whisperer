"""Tests for the dependency checker module."""

from __future__ import annotations

import shutil
from unittest.mock import patch

from bits_whisperer.core.dependency_checker import is_ffmpeg_available


class TestFfmpegDetection:
    """ffmpeg availability detection."""

    def test_ffmpeg_found_on_path(self) -> None:
        with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
            assert is_ffmpeg_available() is True

    def test_ffmpeg_not_found(self) -> None:
        with (
            patch.object(shutil, "which", return_value=None),
            patch("bits_whisperer.core.dependency_checker.Path.exists", return_value=False),
        ):
            assert is_ffmpeg_available() is False
