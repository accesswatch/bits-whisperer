"""Transcript viewer/editor panel with export and speaker management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.job import Job
from bits_whisperer.export.base import ExportFormatter
from bits_whisperer.utils.accessibility import (
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import EXPORT_FORMATS, TRANSCRIPTS_DIR

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Lazy formatter cache — populated on first export to keep startup fast
_FORMATTERS: dict[str, ExportFormatter] = {}


def _get_formatters() -> dict[str, ExportFormatter]:
    """Return the formatter dict, populating it lazily on first call."""
    if not _FORMATTERS:
        from bits_whisperer.export.html_export import HTMLFormatter
        from bits_whisperer.export.json_export import JSONFormatter
        from bits_whisperer.export.markdown import MarkdownFormatter
        from bits_whisperer.export.plain_text import PlainTextFormatter
        from bits_whisperer.export.srt import SRTFormatter
        from bits_whisperer.export.vtt import VTTFormatter
        from bits_whisperer.export.word_export import WordFormatter

        _FORMATTERS.update(
            {
                "txt": PlainTextFormatter(),
                "md": MarkdownFormatter(),
                "html": HTMLFormatter(),
                "docx": WordFormatter(),
                "srt": SRTFormatter(),
                "vtt": VTTFormatter(),
                "json": JSONFormatter(),
            }
        )
    return _FORMATTERS


class TranscriptPanel(wx.Panel):
    """Right-side panel for viewing, editing speakers, and exporting transcripts.

    Features
    --------
    - Rich text display of the transcript
    - Metadata header (file, provider, model, duration)
    - Speaker management (rename, reassign, find/replace)
    - Right-click context menu for speaker assignment
    - Copy to clipboard
    - Export to any supported format
    - Search within transcript
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(self)
        set_accessible_name(self, "Transcript viewer")

        self._main_frame = main_frame
        self._current_job: Job | None = None
        self._last_search_pos: int = -1  # Track position for Find Next
        self._segment_line_map: dict[int, int] = {}  # line_number -> segment_index

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # -- Toolbar row --
        toolbar = wx.BoxSizer(wx.HORIZONTAL)

        header = wx.StaticText(self, label="Transcript")
        header.SetFont(header.GetFont().Bold())
        toolbar.Add(header, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._search_ctrl = wx.SearchCtrl(self, size=(200, -1))
        set_accessible_name(self._search_ctrl, "Search in transcript")
        set_accessible_help(self._search_ctrl, "Type to highlight text in the transcript")
        toolbar.Add(self._search_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._copy_btn = wx.Button(self, label="&Copy")
        set_accessible_name(self._copy_btn, "Copy transcript to clipboard")
        toolbar.Add(self._copy_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._export_btn = wx.Button(self, label="E&xport…")
        set_accessible_name(self._export_btn, "Export transcript to file")
        toolbar.Add(self._export_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # AI action buttons
        self._translate_btn = wx.Button(self, label="&Translate")
        set_accessible_name(self._translate_btn, "Translate transcript using AI")
        set_accessible_help(
            self._translate_btn,
            "Translate the current transcript to another language using AI",
        )
        toolbar.Add(self._translate_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._summarize_btn = wx.Button(self, label="S&ummarize")
        set_accessible_name(self._summarize_btn, "Summarize transcript using AI")
        set_accessible_help(
            self._summarize_btn,
            "Create an AI-powered summary of the current transcript",
        )
        toolbar.Add(self._summarize_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, 5)

        # -- Speaker toolbar row --
        speaker_bar = wx.BoxSizer(wx.HORIZONTAL)

        self._speaker_label = wx.StaticText(self, label="")
        set_accessible_name(self._speaker_label, "Detected speakers")
        speaker_bar.Add(self._speaker_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._manage_speakers_btn = wx.Button(self, label="&Manage Speakers...")
        set_accessible_name(self._manage_speakers_btn, "Manage and rename speakers")
        set_accessible_help(
            self._manage_speakers_btn,
            "Rename speakers or assign display names. Right-click a line "
            "to reassign its speaker.",
        )
        speaker_bar.Add(self._manage_speakers_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(speaker_bar, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 5)
        self._manage_speakers_btn.Hide()
        self._speaker_label.Hide()

        # -- Metadata area --
        self._meta_label = wx.StaticText(self, label="No transcript loaded")
        self._meta_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        set_accessible_name(self._meta_label, "Transcript metadata")
        sizer.Add(self._meta_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 5)

        # -- Text display --
        self._text_ctrl = wx.TextCtrl(
            self,
            style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_WORDWRAP | wx.HSCROLL),
        )
        set_accessible_name(self._text_ctrl, "Transcript text")
        set_accessible_help(
            self._text_ctrl,
            "Full transcript of the selected audio file. Use Ctrl+A to select all.",
        )
        font = wx.Font(
            11,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
        self._text_ctrl.SetFont(font)
        sizer.Add(self._text_ctrl, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 5)

        self.SetSizer(sizer)

        # Show a helpful welcome message
        self._show_empty_state()

        # Events
        self._copy_btn.Bind(wx.EVT_BUTTON, self._on_copy)
        self._export_btn.Bind(wx.EVT_BUTTON, self._on_export)
        self._translate_btn.Bind(wx.EVT_BUTTON, self._on_translate)
        self._summarize_btn.Bind(wx.EVT_BUTTON, self._on_summarize)
        self._search_ctrl.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self._on_search)
        self._search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self._search_ctrl.Bind(wx.EVT_TEXT, self._on_search_text_changed)
        self._text_ctrl.Bind(wx.EVT_CONTEXT_MENU, self._on_text_context_menu)
        self._manage_speakers_btn.Bind(wx.EVT_BUTTON, self._on_manage_speakers)

        # F3 = Find Next (bound at panel level so it works globally)
        find_next_id = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, self._on_find_next, id=find_next_id)
        accel = wx.AcceleratorTable(
            [
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F3, find_next_id),
            ]
        )
        self.SetAcceleratorTable(accel)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def show_transcript(self, job: Job) -> None:
        """Display the transcript for a completed job.

        Uses the format ``[mm:ss]  SpeakerName: text`` when speakers
        are detected, honouring any speaker renames in the result's
        ``speaker_map``.

        Args:
            job: A job with a populated ``result`` attribute.
        """
        self._current_job = job
        result = job.result
        if not result:
            self._text_ctrl.SetValue("(No transcript available)")
            self._meta_label.SetLabel("No transcript loaded")
            self._speaker_label.Hide()
            self._manage_speakers_btn.Hide()
            self.Layout()
            return

        # Metadata header
        duration_min = result.duration_seconds / 60
        meta = (
            f"{job.display_name}  |  {result.provider} / {result.model}  |  "
            f"{result.language}  |  {duration_min:.1f} min"
        )
        self._meta_label.SetLabel(meta)

        # Build display text with timestamps and speaker names
        lines: list[str] = []
        self._segment_line_map.clear()
        unique_speakers: set[str] = set()

        if result.segments:
            speaker_map = getattr(result, "speaker_map", {}) or {}
            for i, seg in enumerate(result.segments):
                ts = self._fmt_ts(seg.start)
                speaker_id = seg.speaker
                display_name = speaker_map.get(speaker_id, speaker_id) if speaker_id else ""
                if display_name:
                    unique_speakers.add(display_name)
                    lines.append(f"[{ts}]  {display_name}: {seg.text}")
                else:
                    lines.append(f"[{ts}]  {seg.text}")
                self._segment_line_map[len(lines) - 1] = i
        else:
            lines.append(result.full_text)

        self._text_ctrl.SetValue("\n".join(lines))
        self._text_ctrl.SetInsertionPoint(0)

        # Show/hide speaker bar
        if unique_speakers:
            names_str = ", ".join(sorted(unique_speakers))
            self._speaker_label.SetLabel(f"Speakers ({len(unique_speakers)}): {names_str}")
            self._speaker_label.Show()
            self._manage_speakers_btn.Show()
        else:
            self._speaker_label.Hide()
            self._manage_speakers_btn.Hide()
        self.Layout()

    def export_transcript(self) -> None:
        """Open the export dialog for the current transcript."""
        self._on_export(None)

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_copy(self, _event: wx.CommandEvent | None) -> None:
        text = self._text_ctrl.GetValue()
        if text and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            from bits_whisperer.utils.accessibility import announce_status

            announce_status(self._main_frame, "Transcript copied to clipboard")

    def _on_export(self, _event: wx.CommandEvent | None) -> None:
        if not self._current_job or not self._current_job.result:
            wx.MessageBox(
                "No transcript to export. Transcribe a file first.",
                "No Transcript",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Build wildcard from formatters
        parts: list[str] = []
        formatters = _get_formatters()
        for fmt_id, fmt_name in EXPORT_FORMATS.items():
            fmt = formatters.get(fmt_id)
            if fmt:
                parts.append(f"{fmt_name}|*{fmt.file_extension}")
        wildcard = "|".join(parts)

        stem = Path(self._current_job.file_path).stem
        dlg = wx.FileDialog(
            self,
            message="Export Transcript",
            defaultDir=str(TRANSCRIPTS_DIR),
            defaultFile=stem,
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() == wx.ID_OK:
            out_path = Path(dlg.GetPath())
            filter_idx = dlg.GetFilterIndex()
            fmt_ids = list(EXPORT_FORMATS.keys())
            chosen_id = fmt_ids[filter_idx] if filter_idx < len(fmt_ids) else "txt"

            formatter = _get_formatters().get(chosen_id)
            if formatter:
                # Ensure correct extension
                if not out_path.suffix:
                    out_path = out_path.with_suffix(formatter.file_extension)
                try:
                    formatter.export(self._current_job.result, out_path)
                    from bits_whisperer.utils.accessibility import announce_status

                    announce_status(
                        self._main_frame,
                        f"Exported to {out_path.name}",
                    )
                except Exception as exc:
                    logger.exception("Export failed")
                    wx.MessageBox(
                        f"Export failed:\n{exc}",
                        "Export Error",
                        wx.OK | wx.ICON_ERROR,
                        self,
                    )
        dlg.Destroy()

    def _on_search(self, event: wx.CommandEvent) -> None:
        query = self._search_ctrl.GetValue().strip()
        if not query:
            return
        # Start search from beginning
        self._last_search_pos = -1
        self._find_next(query)

    def _on_search_text_changed(self, event: wx.CommandEvent) -> None:
        """Reset search position when the query text changes."""
        self._last_search_pos = -1

    def _on_find_next(self, event: wx.CommandEvent) -> None:
        """F3 — find next occurrence of the current search query."""
        query = self._search_ctrl.GetValue().strip()
        if not query:
            return
        self._find_next(query)

    def _find_next(self, query: str) -> None:
        """Find the next occurrence of *query* after ``_last_search_pos``.

        Wraps around to the beginning when the end is reached.
        """
        text = self._text_ctrl.GetValue()
        text_lower = text.lower()
        query_lower = query.lower()

        start = self._last_search_pos + 1
        pos = text_lower.find(query_lower, start)

        if pos < 0 and start > 0:
            # Wrap around
            pos = text_lower.find(query_lower, 0)

        if pos >= 0:
            self._last_search_pos = pos
            self._text_ctrl.SetSelection(pos, pos + len(query))
            self._text_ctrl.ShowPosition(pos)
        else:
            self._last_search_pos = -1
            from bits_whisperer.utils.accessibility import announce_status

            announce_status(self._main_frame, f"'{query}' not found in transcript")

    def _on_translate(self, _event: wx.CommandEvent | None) -> None:
        """Delegate translate to main frame handler."""
        self._main_frame._on_translate(None)

    def _on_summarize(self, _event: wx.CommandEvent | None) -> None:
        """Delegate summarize to main frame handler."""
        self._main_frame._on_summarize(None)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _show_empty_state(self) -> None:
        """Display a friendly welcome message when no transcript is loaded."""
        self._text_ctrl.SetValue(
            "Welcome to BITS Whisperer!\n\n"
            "To get started:\n"
            "  1. Add audio files (Ctrl+O or drag and drop)\n"
            "  2. Press F5 to begin transcription\n"
            "  3. Your transcript will appear here\n\n"
            "Tip: Press F3 to find next in search results."
        )

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    # ------------------------------------------------------------------ #
    # Speaker management                                                   #
    # ------------------------------------------------------------------ #

    def _on_manage_speakers(self, _event: wx.CommandEvent) -> None:
        """Open the speaker rename dialog."""
        if not self._current_job or not self._current_job.result:
            return

        result = self._current_job.result

        # Collect unique speaker IDs preserving order
        unique_ids: list[str] = []
        seen: set[str] = set()
        for seg in result.segments:
            if seg.speaker and seg.speaker not in seen:
                unique_ids.append(seg.speaker)
                seen.add(seg.speaker)

        if not unique_ids:
            wx.MessageBox(
                "No speakers detected in this transcript.\n\n"
                "Enable speaker diarization in settings to detect speakers.",
                "No Speakers",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        current_map = dict(getattr(result, "speaker_map", {}) or {})
        dlg = SpeakerRenameDialog(self, unique_ids, current_map)
        if dlg.ShowModal() == wx.ID_OK:
            new_map = dlg.get_speaker_map()
            result.speaker_map = new_map
            self.show_transcript(self._current_job)
            from bits_whisperer.utils.accessibility import announce_status

            announce_status(self._main_frame, "Speaker names updated")
        dlg.Destroy()

    def _on_text_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        """Right-click context menu for speaker reassignment."""
        if not self._current_job or not self._current_job.result:
            return

        result = self._current_job.result
        if not result.segments:
            return

        # Find which segment the cursor is on
        pos = self._text_ctrl.GetInsertionPoint()
        col_line = self._text_ctrl.PositionToXY(pos)
        if col_line is None:
            return
        _, _, line_no = col_line
        seg_idx = self._segment_line_map.get(line_no)
        if seg_idx is None:
            return

        # Collect unique display names
        speaker_map = getattr(result, "speaker_map", {}) or {}
        display_names: list[str] = []
        id_by_name: dict[str, str] = {}
        seen: set[str] = set()
        for seg in result.segments:
            if seg.speaker and seg.speaker not in seen:
                name = speaker_map.get(seg.speaker, seg.speaker)
                display_names.append(name)
                id_by_name[name] = seg.speaker
                seen.add(seg.speaker)

        menu = wx.Menu()

        if display_names:
            assign_menu = wx.Menu()
            for name in display_names:
                item = assign_menu.Append(wx.ID_ANY, name)
                self.Bind(
                    wx.EVT_MENU,
                    lambda e, spk=id_by_name[name], idx=seg_idx: (
                        self._assign_speaker_to_segment(idx, spk)
                    ),
                    item,
                )
            menu.AppendSubMenu(assign_menu, "Assign to Speaker")

        new_item = menu.Append(wx.ID_ANY, "New Speaker...")
        self.Bind(
            wx.EVT_MENU,
            lambda e, idx=seg_idx: self._new_speaker_for_segment(idx),
            new_item,
        )

        self.PopupMenu(menu)
        menu.Destroy()

    def _assign_speaker_to_segment(self, seg_idx: int, speaker_id: str) -> None:
        """Reassign a segment to a different speaker.

        Args:
            seg_idx: Index of the segment in the result.
            speaker_id: Internal speaker ID to assign.
        """
        if not self._current_job or not self._current_job.result:
            return
        result = self._current_job.result
        if 0 <= seg_idx < len(result.segments):
            result.segments[seg_idx].speaker = speaker_id
            self.show_transcript(self._current_job)

    def _new_speaker_for_segment(self, seg_idx: int) -> None:
        """Prompt for a new speaker name and assign it to a segment.

        Args:
            seg_idx: Index of the segment in the result.
        """
        if not self._current_job or not self._current_job.result:
            return
        result = self._current_job.result
        if seg_idx < 0 or seg_idx >= len(result.segments):
            return

        dlg = wx.TextEntryDialog(
            self,
            "Enter a name for the new speaker:",
            "New Speaker",
        )
        set_accessible_name(dlg, "Enter new speaker name")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                # Create a new speaker ID
                speaker_map = getattr(result, "speaker_map", {}) or {}
                new_id = f"speaker_{len(speaker_map) + 1}"
                speaker_map[new_id] = name
                result.speaker_map = speaker_map
                result.segments[seg_idx].speaker = new_id
                self.show_transcript(self._current_job)
        dlg.Destroy()


class SpeakerRenameDialog(wx.Dialog):
    """Dialog for renaming speakers detected in a transcript.

    Displays all detected speaker IDs with editable name fields.
    The user can assign friendly names (e.g. Speaker 1 -> Alice)
    that are stored in the transcript's speaker_map and applied
    globally to all matching segments.
    """

    def __init__(
        self,
        parent: wx.Window,
        speaker_ids: list[str],
        current_map: dict[str, str],
    ) -> None:
        """Initialise the speaker rename dialog.

        Args:
            parent: Parent window.
            speaker_ids: List of unique speaker IDs found in the transcript.
            current_map: Current speaker_id -> display_name mapping.
        """
        super().__init__(
            parent,
            title="Manage Speakers",
            size=(420, min(200 + len(speaker_ids) * 36, 500)),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Rename speakers")
        self.SetMinSize((360, 200))
        self.Centre()

        self._speaker_ids = speaker_ids
        self._fields: dict[str, wx.TextCtrl] = {}

        self._build_ui(current_map)

    def _build_ui(self, current_map: dict[str, str]) -> None:
        """Build the rename dialog layout.

        Args:
            current_map: Current speaker mappings.
        """
        root = wx.BoxSizer(wx.VERTICAL)

        instructions = wx.StaticText(
            self,
            label=(
                "Assign display names to each speaker. These names replace "
                "the generic speaker IDs in the transcript."
            ),
        )
        instructions.Wrap(380)
        set_accessible_name(instructions, "Instructions")
        root.Add(instructions, 0, wx.ALL, 10)

        # Scrolled panel for speaker fields
        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 20)
        make_panel_accessible(scroll)

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        for speaker_id in self._speaker_ids:
            lbl = wx.StaticText(scroll, label=f"{speaker_id}:")
            set_accessible_name(lbl, f"Speaker ID {speaker_id}")

            txt = wx.TextCtrl(
                scroll,
                value=current_map.get(speaker_id, speaker_id),
                size=(200, -1),
            )
            set_accessible_name(txt, f"Display name for {speaker_id}")
            set_accessible_help(txt, f"Enter a friendly name for {speaker_id}")

            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(txt, 1, wx.EXPAND)
            self._fields[speaker_id] = txt

        scroll.SetSizer(grid)
        root.Add(scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 8)
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)

    def get_speaker_map(self) -> dict[str, str]:
        """Return the speaker_id -> display_name mapping from the dialog.

        Returns:
            Dict mapping internal speaker IDs to user-assigned names.
        """
        result: dict[str, str] = {}
        for speaker_id, txt in self._fields.items():
            name = txt.GetValue().strip()
            if name:
                result[speaker_id] = name
        return result
