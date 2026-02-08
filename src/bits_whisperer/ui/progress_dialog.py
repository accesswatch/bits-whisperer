"""Progress dialog for batch transcription operations."""

from __future__ import annotations

import logging

import wx

from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.utils.accessibility import (
    set_accessible_help,
    set_accessible_name,
)

logger = logging.getLogger(__name__)


class ProgressDialog(wx.Dialog):
    """Non-modal progress dialog for batch transcription.

    Shows
    -----
    - Overall progress bar
    - Per-file status list
    - Current file name and ETA
    - Cancel button
    """

    def __init__(self, parent: wx.Window, total_files: int) -> None:
        super().__init__(
            parent,
            title="Transcription Progress",
            size=(520, 400),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Transcription progress dialog")
        self._total = total_files
        self._completed = 0

        self._build_ui()
        self.CentreOnParent()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Current file
        self._current_label = wx.StaticText(self, label="Preparing…")
        self._current_label.SetFont(self._current_label.GetFont().Bold())
        set_accessible_name(self._current_label, "Current file")
        sizer.Add(self._current_label, 0, wx.ALL | wx.EXPAND, 8)

        # Overall progress
        lbl_overall = wx.StaticText(self, label=f"Overall: 0 / {self._total} files")
        set_accessible_name(lbl_overall, "Overall progress label")
        self._overall_label = lbl_overall
        sizer.Add(lbl_overall, 0, wx.LEFT | wx.RIGHT, 8)

        self._overall_gauge = wx.Gauge(self, range=self._total, style=wx.GA_HORIZONTAL)
        set_accessible_name(self._overall_gauge, "Overall progress bar")
        sizer.Add(self._overall_gauge, 0, wx.ALL | wx.EXPAND, 8)

        # Current file progress
        self._file_gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        set_accessible_name(self._file_gauge, "Current file progress bar")
        set_accessible_help(self._file_gauge, "Progress of the file currently being transcribed")
        sizer.Add(self._file_gauge, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # Status list
        self._status_list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_HRULES)
        set_accessible_name(self._status_list, "File status list")
        self._status_list.InsertColumn(0, "File", width=280)
        self._status_list.InsertColumn(1, "Status", width=100)
        self._status_list.InsertColumn(2, "Time", width=80)
        sizer.Add(self._status_list, 1, wx.ALL | wx.EXPAND, 8)

        # Cancel button
        self._cancel_btn = wx.Button(self, wx.ID_CANCEL, "&Cancel")
        set_accessible_name(self._cancel_btn, "Cancel all remaining jobs")
        sizer.Add(self._cancel_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(sizer)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update_job(self, job: Job) -> None:
        """Update display for a job.

        Args:
            job: The job with updated status/progress.
        """
        self._current_label.SetLabel(f"Processing: {job.display_name}")
        self._file_gauge.SetValue(int(job.progress_percent))

        # Find or insert row
        idx = self._find_row(job.display_name)
        if idx is None:
            idx = self._status_list.InsertItem(self._status_list.GetItemCount(), job.display_name)

        self._status_list.SetItem(idx, 1, job.status_text)

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            elapsed = ""
            if job.started_at and job.completed_at:
                # Compute elapsed if both timestamps are available
                elapsed = "—"
            self._status_list.SetItem(idx, 2, elapsed)
            self._completed += 1
            self._overall_gauge.SetValue(self._completed)
            self._overall_label.SetLabel(f"Overall: {self._completed} / {self._total} files")

    def all_complete(self) -> None:
        """Mark all jobs as complete."""
        self._current_label.SetLabel("All files complete!")
        self._file_gauge.SetValue(100)
        self._overall_gauge.SetValue(self._total)
        self._cancel_btn.SetLabel("&Close")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _find_row(self, name: str) -> int | None:
        for idx in range(self._status_list.GetItemCount()):
            if self._status_list.GetItemText(idx) == name:
                return idx
        return None
