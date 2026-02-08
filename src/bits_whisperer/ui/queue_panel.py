"""Queue panel — file list with status, progress, and batch controls."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.utils.accessibility import (
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import SUPPORTED_AUDIO_EXTENSIONS

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Column indices
COL_NAME = 0
COL_STATUS = 1
COL_PROGRESS = 2
COL_PROVIDER = 3
COL_COST = 4


class QueuePanel(wx.Panel):
    """Left-side panel showing the transcription job queue.

    Features
    --------
    - Multi-column list (Name, Status, Progress, Provider, Cost)
    - Drag-and-drop audio files onto the panel
    - Context menu for job-level actions
    - Full keyboard accessibility
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(self)
        set_accessible_name(self, "File queue")

        self._main_frame = main_frame
        self._jobs: dict[str, Job] = {}  # job_id to Job

        self._build_ui()
        self._setup_drag_drop()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(self, label="Transcription Queue")
        header.SetFont(header.GetFont().Bold())
        set_accessible_name(header, "Transcription queue header")
        sizer.Add(header, 0, wx.ALL | wx.EXPAND, 5)

        # List control
        self._list = wx.ListCtrl(
            self,
            style=(wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES),
        )
        set_accessible_name(self._list, "Job queue list")
        set_accessible_help(
            self._list,
            "List of audio files queued for transcription. "
            "Use arrow keys to navigate, Delete to cancel, Enter to view transcript.",
        )

        self._list.InsertColumn(COL_NAME, "File", width=160)
        self._list.InsertColumn(COL_STATUS, "Status", width=90)
        self._list.InsertColumn(COL_PROGRESS, "Progress", width=70)
        self._list.InsertColumn(COL_PROVIDER, "Provider", width=80)
        self._list.InsertColumn(COL_COST, "Cost", width=60)

        sizer.Add(self._list, 1, wx.ALL | wx.EXPAND, 5)

        # Summary label
        self._summary_label = wx.StaticText(self, label="No files in queue")
        set_accessible_name(self._summary_label, "Queue summary")
        sizer.Add(self._summary_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.SetSizer(sizer)

        # Events
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        self._list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_key_down)
        self._list.Bind(wx.EVT_RIGHT_DOWN, self._on_context_menu)

    def _setup_drag_drop(self) -> None:
        """Accept files dragged onto the panel."""
        dt = _FileDropTarget(self)
        self._list.SetDropTarget(dt)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add_files(self, paths: list[str]) -> None:
        """Add audio files to the queue.

        Args:
            paths: List of absolute file paths.
        """
        for path in paths:
            p = Path(path)
            if p.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            job = Job(
                id=str(uuid.uuid4()),
                file_path=str(p),
                file_name=p.name,
                file_size_bytes=p.stat().st_size if p.exists() else 0,
                provider=self._main_frame.provider_manager.recommend_provider(
                    duration_seconds=0, prefer_free=True, prefer_local=True
                )
                or "local_whisper",
            )
            self._jobs[job.id] = job

            idx = self._list.InsertItem(self._list.GetItemCount(), job.display_name)
            self._list.SetItem(idx, COL_STATUS, job.status_text)
            self._list.SetItem(idx, COL_PROGRESS, "0%")
            self._list.SetItem(idx, COL_PROVIDER, job.provider)
            self._list.SetItem(idx, COL_COST, job.cost_display)
            self._list.SetItemData(idx, hash(job.id) & 0x7FFFFFFF)

        self._update_summary()

    def get_pending_jobs(self) -> list[Job]:
        """Return copies of all pending jobs."""
        return [j for j in self._jobs.values() if j.status == JobStatus.PENDING]

    def get_selected_job_id(self) -> str | None:
        """Return the job ID of the selected item, or None."""
        idx = self._list.GetFirstSelected()
        if idx == -1:
            return None
        return self._job_id_at(idx)

    def update_job(self, job: Job) -> None:
        """Refresh the display for a job after status change."""
        idx = self._find_row_for_job(job.id)
        if idx is None:
            return
        self._jobs[job.id] = job
        self._list.SetItem(idx, COL_STATUS, job.status_text)
        self._list.SetItem(idx, COL_PROGRESS, f"{job.progress_percent:.0f}%")
        self._list.SetItem(idx, COL_COST, job.cost_display)

    def update_job_status(self, job_id: str, status_text: str) -> None:
        """Update just the status text column for a job."""
        idx = self._find_row_for_job(job_id)
        if idx is not None:
            self._list.SetItem(idx, COL_STATUS, status_text)

    def clear_all(self) -> None:
        """Remove all items from the queue."""
        self._list.DeleteAllItems()
        self._jobs.clear()
        self._update_summary()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _job_id_at(self, idx: int) -> str | None:
        """Resolve a list row index back to a job ID."""
        data_hash = self._list.GetItemData(idx)
        for jid in self._jobs:
            if (hash(jid) & 0x7FFFFFFF) == data_hash:
                return jid
        return None

    def _find_row_for_job(self, job_id: str) -> int | None:
        """Find the list row displaying a given job."""
        target = hash(job_id) & 0x7FFFFFFF
        for idx in range(self._list.GetItemCount()):
            if self._list.GetItemData(idx) == target:
                return idx
        return None

    def _update_summary(self) -> None:
        n = len(self._jobs)
        pending = sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)
        self._summary_label.SetLabel(
            f"{n} file{'s' if n != 1 else ''} in queue — {pending} pending"
        )

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_item_selected(self, event: wx.ListEvent) -> None:
        job_id = self._job_id_at(event.GetIndex())
        if job_id and job_id in self._jobs:
            job = self._jobs[job_id]
            if job.result:
                self._main_frame.transcript_panel.show_transcript(job)

    def _on_item_activated(self, event: wx.ListEvent) -> None:
        """Double-click or Enter — show transcript if available."""
        self._on_item_selected(event)

    def _on_key_down(self, event: wx.ListEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_DELETE:
            job_id = self.get_selected_job_id()
            if job_id:
                self._main_frame.transcription_service.cancel_job(job_id)
                self.update_job_status(job_id, "Cancelled")

    def _on_context_menu(self, event: wx.MouseEvent) -> None:
        job_id = self.get_selected_job_id()
        if not job_id:
            return

        menu = wx.Menu()
        view_item = menu.Append(wx.ID_ANY, "&View Transcript\tEnter")
        cancel_item = menu.Append(wx.ID_ANY, "&Cancel Job\tDel")
        remove_item = menu.Append(wx.ID_ANY, "&Remove from Queue")

        # Disable inappropriate actions based on job state
        job = self._jobs.get(job_id)
        if job:
            has_result = job.result is not None
            is_pending = job.status == JobStatus.PENDING
            view_item.Enable(has_result)
            cancel_item.Enable(is_pending or job.status == JobStatus.TRANSCRIBING)

        self.Bind(wx.EVT_MENU, self._on_ctx_view_transcript, view_item)
        self.Bind(wx.EVT_MENU, self._on_ctx_cancel_job, cancel_item)
        self.Bind(wx.EVT_MENU, self._on_ctx_remove_from_queue, remove_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_ctx_view_transcript(self, _event: wx.CommandEvent) -> None:
        """Context menu: view transcript for the selected job."""
        job_id = self.get_selected_job_id()
        if job_id and job_id in self._jobs:
            job = self._jobs[job_id]
            if job.result:
                self._main_frame.transcript_panel.show_transcript(job)

    def _on_ctx_cancel_job(self, _event: wx.CommandEvent) -> None:
        """Context menu: cancel the selected job."""
        job_id = self.get_selected_job_id()
        if job_id:
            self._main_frame.transcription_service.cancel_job(job_id)
            self.update_job_status(job_id, "Cancelled")

    def _on_ctx_remove_from_queue(self, _event: wx.CommandEvent) -> None:
        """Context menu: remove the selected job from the queue entirely."""
        job_id = self.get_selected_job_id()
        if not job_id:
            return
        idx = self._find_row_for_job(job_id)
        if idx is not None:
            self._list.DeleteItem(idx)
        self._jobs.pop(job_id, None)
        self._update_summary()


# ======================================================================= #
# Drag & drop target                                                       #
# ======================================================================= #


class _FileDropTarget(wx.FileDropTarget):
    """Accept dragged audio files into the queue."""

    def __init__(self, panel: QueuePanel) -> None:
        super().__init__()
        self._panel = panel

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:  # noqa: N802
        audio = [f for f in filenames if Path(f).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
        folders = [f for f in filenames if os.path.isdir(f)]
        for folder in folders:
            for p in sorted(Path(folder).rglob("*")):
                if p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    audio.append(str(p))
        if audio:
            self._panel.add_files(audio)
            return True
        return False
