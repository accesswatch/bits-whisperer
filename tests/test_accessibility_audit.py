"""Accessibility regression tests.

These tests enforce structural accessibility rules across the codebase
so that regressions are caught automatically in CI.

Tests
-----
* No hardcoded ``wx.Colour()`` in UI files (high-contrast compliance).
* All dialog classes include ``wx.TAB_TRAVERSAL`` in their style flags.
* ``accessible_message_box`` callers compare with ``wx.YES`` not ``wx.ID_YES``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "bits_whisperer" / "ui"


# ----------------------------------------------------------------------- #
# Helpers                                                                    #
# ----------------------------------------------------------------------- #


def _ui_python_files() -> list[Path]:
    """Return all Python files in the UI directory."""
    return sorted(UI_DIR.glob("*.py"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------- #
# Test: No hardcoded wx.Colour in UI files                                  #
# ----------------------------------------------------------------------- #

# Allow wx.Colour in tray_icon.py (icon bitmap rendering, not a UI control)
_COLOUR_ALLOWLIST = {"tray_icon.py"}

# Pattern matches wx.Colour(123, ...) with numeric RGB args
_HARDCODED_COLOUR_RE = re.compile(r"wx\.Colour\(\s*\d")


class TestNoHardcodedColours:
    """Ensure UI files use wx.SystemSettings.GetColour() instead of literals."""

    @pytest.mark.parametrize("path", _ui_python_files(), ids=lambda p: p.name)
    def test_no_hardcoded_wx_colour(self, path: Path) -> None:
        if path.name in _COLOUR_ALLOWLIST:
            pytest.skip(f"{path.name} is allowlisted for icon rendering")
        source = _read_text(path)
        matches = _HARDCODED_COLOUR_RE.findall(source)
        assert not matches, (
            f"{path.name} contains hardcoded wx.Colour() — "
            "use wx.SystemSettings.GetColour() for high-contrast compliance"
        )


# ----------------------------------------------------------------------- #
# Test: All dialogs have wx.TAB_TRAVERSAL                                   #
# ----------------------------------------------------------------------- #

# Pattern: style=wx.DEFAULT_DIALOG_STYLE ...  must include TAB_TRAVERSAL
_DIALOG_STYLE_RE = re.compile(
    r"style\s*=\s*wx\.DEFAULT_DIALOG_STYLE([^,\)]*)",
    re.MULTILINE,
)


class TestDialogTabTraversal:
    """Ensure every wx.Dialog subclass includes wx.TAB_TRAVERSAL."""

    @pytest.mark.parametrize("path", _ui_python_files(), ids=lambda p: p.name)
    def test_dialogs_have_tab_traversal(self, path: Path) -> None:
        source = _read_text(path)
        # Only check files that define Dialog subclasses
        if "wx.DEFAULT_DIALOG_STYLE" not in source:
            pytest.skip("No dialog style found")

        for match in _DIALOG_STYLE_RE.finditer(source):
            style_suffix = match.group(1)
            # The full style expression should contain TAB_TRAVERSAL
            assert "TAB_TRAVERSAL" in style_suffix, (
                f"{path.name} has a dialog with wx.DEFAULT_DIALOG_STYLE "
                f"but missing wx.TAB_TRAVERSAL in style flags: "
                f"style=wx.DEFAULT_DIALOG_STYLE{style_suffix}"
            )


# ----------------------------------------------------------------------- #
# Test: accessible_message_box callers use wx.YES not wx.ID_YES             #
# ----------------------------------------------------------------------- #

_ID_YES_AFTER_AMB = re.compile(
    r"accessible_message_box\(.*?\)\s*\n\s*.*?wx\.ID_YES",
    re.DOTALL,
)


class TestAccessibleMessageBoxUsage:
    """Ensure callers compare accessible_message_box results correctly."""

    @pytest.mark.parametrize("path", _ui_python_files(), ids=lambda p: p.name)
    def test_no_wx_id_yes_comparison(self, path: Path) -> None:
        source = _read_text(path)
        if "accessible_message_box" not in source:
            pytest.skip("No accessible_message_box usage")

        # Check that accessible_message_box results are never compared
        # with wx.ID_YES (it returns wx.YES, not wx.ID_YES).
        # Look for lines where accessible_message_box result is compared
        # within the same function (max 20 lines apart).
        lines = source.splitlines()
        amb_result_vars: dict[int, str] = {}
        for i, line in enumerate(lines):
            m = re.search(r"(\w+)\s*=\s*accessible_message_box\(", line)
            if m:
                amb_result_vars[i] = m.group(1)

        bad_lines: list[int] = []
        for amb_line, var_name in amb_result_vars.items():
            # Check within 20 lines after the call
            for j in range(amb_line, min(amb_line + 20, len(lines))):
                if re.search(rf"\b{var_name}\b.*wx\.ID_YES", lines[j]):
                    bad_lines.append(j + 1)

        assert not bad_lines, (
            f"{path.name} compares accessible_message_box result with "
            f"wx.ID_YES (lines {bad_lines}) — use wx.YES instead"
        )


# ----------------------------------------------------------------------- #
# Test: Key accessibility utility functions exist                           #
# ----------------------------------------------------------------------- #


class TestAccessibilityUtilities:
    """Verify the accessibility module provides required functions."""

    def test_core_functions_exist(self) -> None:
        from bits_whisperer.utils.accessibility import (
            accessible_message_box,
            announce_status,
            announce_to_screen_reader,
            label_control,
            make_panel_accessible,
            safe_call_after,
            set_accessible_help,
            set_accessible_name,
            speak,
        )

        # All imported successfully — they exist
        assert callable(speak)
        assert callable(announce_to_screen_reader)
        assert callable(set_accessible_name)
        assert callable(set_accessible_help)
        assert callable(label_control)
        assert callable(announce_status)
        assert callable(safe_call_after)
        assert callable(make_panel_accessible)
        assert callable(accessible_message_box)
