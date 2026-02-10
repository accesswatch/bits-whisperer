"""Queue panel — tree view with folders, status, progress, and batch controls."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.job import Job, JobStatus
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    announce_to_screen_reader,
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import DATA_DIR, SUPPORTED_AUDIO_EXTENSIONS, WHISPER_MODELS

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


class QueuePanel(wx.Panel):
    """Panel showing the transcription job queue as a tree view.

    Features
    --------
    - Tree control: folders as expandable branches, lone files at root
    - Custom naming for jobs and folders (F2 to rename)
    - Status, progress, and provider shown inline in tree item text
    - Drag-and-drop audio files onto the panel
    - Rich context menus with job and folder actions
    - Comprehensive keyboard shortcuts (F2, F5, Ctrl+C, etc.)
    - Full keyboard accessibility with screen reader announcements
    - Live updates as transcription proceeds
    - Clear completed, retry failed, batch operations
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(self)
        set_accessible_name(self, "File queue")

        self._main_frame = main_frame
        self._jobs: dict[str, Job] = {}  # job_id -> Job
        self._job_tree_items: dict[str, wx.TreeItemId] = {}  # job_id -> tree item
        self._folder_tree_items: dict[str, wx.TreeItemId] = {}  # folder_path -> tree item
        self._folder_custom_names: dict[str, str] = {}  # folder_path -> custom name
        self._filter_text: str = ""  # current search/filter string

        self._build_ui()
        self._setup_drag_drop()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header row with title and toolbar buttons
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        header = wx.StaticText(self, label="Transcription Queue")
        header.SetFont(header.GetFont().Bold())
        set_accessible_name(header, "Transcription queue header")
        header_sizer.Add(header, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Toolbar buttons
        self._btn_start = wx.Button(self, label="▶ &Start", size=(70, -1))
        set_accessible_name(self._btn_start, "Start transcription")
        set_accessible_help(self._btn_start, "Start transcribing all pending jobs. Shortcut: F5")
        self._btn_start.Bind(wx.EVT_BUTTON, self._on_start_all)
        header_sizer.Add(self._btn_start, 0, wx.RIGHT, 4)

        self._btn_clear_done = wx.Button(self, label="✓ C&lear Done", size=(90, -1))
        set_accessible_name(self._btn_clear_done, "Clear completed jobs")
        set_accessible_help(self._btn_clear_done, "Remove all completed jobs from the queue")
        self._btn_clear_done.Bind(wx.EVT_BUTTON, self._on_clear_completed)
        header_sizer.Add(self._btn_clear_done, 0, wx.RIGHT, 4)

        self._btn_retry = wx.Button(self, label="↻ &Retry Failed", size=(100, -1))
        set_accessible_name(self._btn_retry, "Retry all failed jobs")
        set_accessible_help(self._btn_retry, "Re-queue all failed jobs for another attempt")
        self._btn_retry.Bind(wx.EVT_BUTTON, self._on_retry_all_failed)
        header_sizer.Add(self._btn_retry, 0)

        sizer.Add(header_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # Search / filter bar
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filter_label = wx.StaticText(self, label="&Filter:")
        set_accessible_name(filter_label, "Filter")
        filter_sizer.Add(filter_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._filter_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        set_accessible_name(self._filter_input, "Filter queue items")
        set_accessible_help(
            self._filter_input,
            "Type to filter the queue by file name or custom name. "
            "Press Enter or wait for automatic filtering. "
            "Clear to show all items.",
        )
        filter_sizer.Add(self._filter_input, 1, wx.RIGHT, 4)

        self._btn_clear_filter = wx.Button(self, label="✕", size=(30, -1))
        set_accessible_name(self._btn_clear_filter, "Clear filter")
        set_accessible_help(self._btn_clear_filter, "Clear the filter and show all queue items")
        self._btn_clear_filter.Bind(wx.EVT_BUTTON, self._on_clear_filter)
        filter_sizer.Add(self._btn_clear_filter, 0)

        sizer.Add(filter_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 5)

        self._filter_input.Bind(wx.EVT_TEXT, self._on_filter_changed)
        self._filter_input.Bind(wx.EVT_TEXT_ENTER, self._on_filter_changed)

        # Tree control
        self._tree = wx.TreeCtrl(
            self,
            style=(
                wx.TR_DEFAULT_STYLE
                | wx.TR_HAS_BUTTONS
                | wx.TR_LINES_AT_ROOT
                | wx.TR_SINGLE
                | wx.TR_NO_LINES
            ),
        )
        set_accessible_name(self._tree, "Job queue tree")
        set_accessible_help(
            self._tree,
            "Tree of audio files queued for transcription. "
            "Folders are expandable branches. "
            "Use arrow keys to navigate. "
            "F2 to rename, Enter to view transcript, "
            "F5 to start, Ctrl+C to copy file path, "
            "Delete to cancel, "
            "Shift+F10 or Apps key for context menu.",
        )

        # Root item (hidden — children appear at top level)
        self._root = self._tree.AddRoot("Queue")

        sizer.Add(self._tree, 1, wx.ALL | wx.EXPAND, 5)

        # Summary label
        self._summary_label = wx.StaticText(self, label="No files in queue")
        set_accessible_name(self._summary_label, "Queue summary")
        sizer.Add(self._summary_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.SetSizer(sizer)

        # Events
        self._tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_item_selected)
        self._tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_item_activated)
        self._tree.Bind(wx.EVT_TREE_KEY_DOWN, self._on_key_down)
        self._tree.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu_event)

    def _setup_drag_drop(self) -> None:
        """Accept files dragged onto the panel."""
        dt = _FileDropTarget(self)
        self._tree.SetDropTarget(dt)

    # ------------------------------------------------------------------ #
    # Tree item text formatting                                            #
    # ------------------------------------------------------------------ #

    def _format_item_text(self, job: Job) -> str:
        """Build the display text for a job tree item.

        Format: ``filename — Status — Provider [— Cost] [— AI Action]``

        Args:
            job: The job to format.

        Returns:
            Formatted display string.
        """
        parts = [job.display_name]

        # Status with progress
        if (
            job.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
            and job.progress_percent > 0
        ):
            parts.append(f"{job.status.value.capitalize()} ({job.progress_percent:.0f}%)")
        else:
            parts.append(job.status.value.capitalize())

        parts.append(job.provider)

        if job.cost_estimate > 0:
            parts.append(job.cost_display)

        # AI action status indicator
        if job.ai_action_status == "running":
            parts.append("\u23f3 AI Action")
        elif job.ai_action_status == "completed":
            parts.append("\u2713 AI Action")
        elif job.ai_action_status == "failed":
            parts.append("\u2717 AI Action")
        elif job.ai_action_template and job.status == JobStatus.PENDING:
            parts.append("\u2b50 AI Action")

        return " \u2014 ".join(parts)

    def _format_folder_text(self, folder_path: str) -> str:
        """Build display text for a folder branch.

        Shows the custom name (if set), otherwise the folder name,
        plus a summary of child job statuses.

        Args:
            folder_path: Absolute path to the folder.

        Returns:
            Formatted display string.
        """
        folder_name = self._folder_custom_names.get(folder_path) or Path(folder_path).name

        # Count child jobs by status
        children = self._get_jobs_in_folder(folder_path)
        if not children:
            return f"\U0001f4c1 {folder_name}"

        total = len(children)
        completed = sum(1 for j in children if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in children if j.status == JobStatus.FAILED)
        in_progress = sum(
            1 for j in children if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        )

        status_parts: list[str] = []
        if in_progress:
            status_parts.append(f"{in_progress} in progress")
        if completed:
            status_parts.append(f"{completed} done")
        if failed:
            status_parts.append(f"{failed} failed")

        status_str = ", ".join(status_parts) if status_parts else f"{total} pending"
        return f"\U0001f4c1 {folder_name} ({total} files \u2014 {status_str})"

    def _get_jobs_in_folder(self, folder_path: str) -> list[Job]:
        """Return all jobs whose file is inside *folder_path* (recursive).

        Args:
            folder_path: Absolute path of the folder.

        Returns:
            List of matching jobs.
        """
        fp_norm = os.path.normpath(folder_path)
        return [
            j
            for j in self._jobs.values()
            if os.path.normpath(str(Path(j.file_path).parent)).startswith(fp_norm)
        ]

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add_files(self, paths: list[str]) -> None:
        """Add audio files to the queue at the root level.

        Applies the user's default provider, model, and language
        from app settings to each new job.

        Args:
            paths: List of absolute file paths.
        """
        settings = self._main_frame.app_settings
        default_provider = settings.general.default_provider or "local_whisper"
        default_model = settings.general.default_model or ""
        default_language = settings.general.language or "auto"
        include_timestamps = settings.transcription.include_timestamps
        include_diarization = settings.diarization.enabled

        for path in paths:
            p = Path(path)
            if p.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            # Determine provider
            provider = default_provider
            enabled = self._main_frame.provider_manager.list_enabled_providers()
            if provider not in enabled:
                provider = (
                    self._main_frame.provider_manager.recommend_provider(
                        duration_seconds=0, prefer_free=True, prefer_local=True
                    )
                    or "local_whisper"
                )

            job = Job(
                id=str(uuid.uuid4()),
                file_path=str(p),
                file_name=p.name,
                file_size_bytes=p.stat().st_size if p.exists() else 0,
                provider=provider,
                model=default_model,
                language=default_language,
                include_timestamps=include_timestamps,
                include_diarization=include_diarization,
            )
            self._insert_job(job, parent_item=self._root)

        self._update_summary()

    def add_job(self, job: Job) -> None:
        """Add a pre-configured job to the queue at the root level.

        Used by the AddFileWizard to insert jobs whose settings
        the user has already chosen.

        Args:
            job: A Job object ready for queuing.
        """
        self._insert_job(job, parent_item=self._root)
        self._update_summary()

    def add_folder(self, folder_path: str, jobs: list[Job]) -> None:
        """Add a folder of jobs as a tree branch.

        Creates an expandable folder node and inserts all jobs as
        children. Supports nested sub-folders — each unique parent
        directory gets its own branch.

        Args:
            folder_path: The top-level folder path chosen by the user.
            jobs: List of Job objects for files within the folder.
        """
        if not jobs:
            return

        # Group jobs by their immediate parent directory
        folder_root = Path(folder_path)
        sub_groups: dict[str, list[Job]] = {}
        for job in jobs:
            job_parent = str(Path(job.file_path).parent)
            sub_groups.setdefault(job_parent, []).append(job)

        if len(sub_groups) == 1:
            # All files in one directory — single folder node
            parent_path = next(iter(sub_groups))
            folder_item = self._get_or_create_folder(parent_path, self._root)
            for job in jobs:
                self._insert_job(job, parent_item=folder_item)
            self._tree.Expand(folder_item)
        else:
            # Multiple sub-directories — create hierarchy
            top_item = self._get_or_create_folder(str(folder_root), self._root)

            for parent_path, group_jobs in sorted(sub_groups.items()):
                parent = Path(parent_path)
                if parent == folder_root:
                    for job in group_jobs:
                        self._insert_job(job, parent_item=top_item)
                else:
                    sub_item = self._get_or_create_folder(parent_path, top_item)
                    for job in group_jobs:
                        self._insert_job(job, parent_item=sub_item)
                    self._tree.Expand(sub_item)

            self._tree.Expand(top_item)

        self._update_summary()
        self._update_all_folder_labels()

    def _get_or_create_folder(self, folder_path: str, parent_item: wx.TreeItemId) -> wx.TreeItemId:
        """Get an existing folder tree item or create a new one.

        Args:
            folder_path: Absolute path of the folder.
            parent_item: Parent tree item to attach to.

        Returns:
            The tree item for the folder.
        """
        if folder_path in self._folder_tree_items:
            return self._folder_tree_items[folder_path]

        folder_name = Path(folder_path).name
        folder_text = f"\U0001f4c1 {folder_name}"
        item = self._tree.AppendItem(parent_item, folder_text)
        self._tree.SetItemData(item, {"type": "folder", "path": folder_path})
        self._folder_tree_items[folder_path] = item
        return item

    def _insert_job(self, job: Job, parent_item: wx.TreeItemId) -> None:
        """Insert a single job into the internal store and tree.

        Args:
            job: Job to insert.
            parent_item: Parent tree item (root or folder).
        """
        self._jobs[job.id] = job
        text = self._format_item_text(job)
        item = self._tree.AppendItem(parent_item, text)
        self._tree.SetItemData(item, {"type": "job", "job_id": job.id})
        self._job_tree_items[job.id] = item

    def get_pending_jobs(self) -> list[Job]:
        """Return copies of all pending jobs."""
        return [j for j in self._jobs.values() if j.status == JobStatus.PENDING]

    def get_selected_job_id(self) -> str | None:
        """Return the job ID of the selected tree item, or None."""
        item = self._tree.GetSelection()
        if not item or not item.IsOk():
            return None
        data = self._tree.GetItemData(item)
        if data and data.get("type") == "job":
            return data.get("job_id")
        return None

    def get_job(self, job_id: str) -> Job | None:
        """Return a job by ID, if present.

        Args:
            job_id: Job identifier.

        Returns:
            The Job instance, or None.
        """
        return self._jobs.get(job_id)

    def update_job(self, job: Job) -> None:
        """Refresh the display for a job after status change.

        Args:
            job: Updated job.
        """
        self._jobs[job.id] = job
        item = self._job_tree_items.get(job.id)
        if item is None or not item.IsOk():
            return

        self._tree.SetItemText(item, self._format_item_text(job))

        # Colour-code status
        if job.status == JobStatus.COMPLETED:
            self._tree.SetItemTextColour(item, wx.Colour(0, 128, 0))
        elif job.status == JobStatus.FAILED:
            self._tree.SetItemTextColour(item, wx.Colour(192, 0, 0))
        elif job.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING):
            self._tree.SetItemTextColour(item, wx.SystemSettings.GetColour(wx.SYS_COLOUR_HOTLIGHT))

        # Update parent folder label if this job is inside a folder
        self._update_parent_folder_label(job.id)
        self._update_summary()

    def update_job_status(self, job_id: str, status_text: str) -> None:
        """Update just the status text for a job (e.g. 'Cancelled').

        Args:
            job_id: Job identifier.
            status_text: New status string.
        """
        item = self._job_tree_items.get(job_id)
        if item is None or not item.IsOk():
            return
        job = self._jobs.get(job_id)
        if job:
            text = f"{job.display_name} \u2014 {status_text} \u2014 {job.provider}"
            self._tree.SetItemText(item, text)

    def clear_all(self) -> None:
        """Remove all items from the queue."""
        self._tree.DeleteChildren(self._root)
        self._jobs.clear()
        self._job_tree_items.clear()
        self._folder_tree_items.clear()
        self._update_summary()

    # ------------------------------------------------------------------ #
    # Folder label updates                                                 #
    # ------------------------------------------------------------------ #

    def _update_parent_folder_label(self, job_id: str) -> None:
        """Refresh the folder label for a job's parent folder.

        Args:
            job_id: The job whose parent folder should be updated.
        """
        item = self._job_tree_items.get(job_id)
        if item is None or not item.IsOk():
            return
        parent = self._tree.GetItemParent(item)
        if parent and parent.IsOk() and parent != self._root:
            data = self._tree.GetItemData(parent)
            if data and data.get("type") == "folder":
                folder_path = data["path"]
                self._tree.SetItemText(parent, self._format_folder_text(folder_path))

    def _update_all_folder_labels(self) -> None:
        """Refresh all folder branch labels to reflect current status counts."""
        for folder_path, item in self._folder_tree_items.items():
            if item.IsOk():
                self._tree.SetItemText(item, self._format_folder_text(folder_path))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _update_summary(self) -> None:
        n = len(self._jobs)
        pending = sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)
        in_progress = sum(
            1
            for j in self._jobs.values()
            if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        )
        completed = sum(1 for j in self._jobs.values() if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in self._jobs.values() if j.status == JobStatus.FAILED)

        parts: list[str] = []
        if pending:
            parts.append(f"{pending} pending")
        if in_progress:
            parts.append(f"{in_progress} in progress")
        if completed:
            parts.append(f"{completed} completed")
        if failed:
            parts.append(f"{failed} failed")

        detail = " \u2014 ".join(parts) if parts else "empty"
        self._summary_label.SetLabel(f"{n} file{'s' if n != 1 else ''} in queue \u2014 {detail}")

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_item_selected(self, event: wx.TreeEvent) -> None:
        item = event.GetItem()
        if not item or not item.IsOk():
            return
        data = self._tree.GetItemData(item)
        if data and data.get("type") == "job":
            job_id = data["job_id"]
            if job_id in self._jobs:
                job = self._jobs[job_id]
                if job.result:
                    self._main_frame.transcript_panel.show_transcript(job)
                    self._main_frame._update_menu_state()

    def _on_item_activated(self, event: wx.TreeEvent) -> None:
        """Double-click or Enter — show transcript and switch tab."""
        item = event.GetItem()
        if not item or not item.IsOk():
            return
        data = self._tree.GetItemData(item)
        if data and data.get("type") == "job":
            job_id = data["job_id"]
            if job_id in self._jobs:
                job = self._jobs[job_id]
                if job.result:
                    self._main_frame.transcript_panel.show_transcript(job)
                    self._main_frame._notebook.SetSelection(self._main_frame._TAB_TRANSCRIPT)
                    self._main_frame._update_menu_state()
        elif data and data.get("type") == "folder":
            # Toggle folder expansion
            if self._tree.IsExpanded(item):
                self._tree.Collapse(item)
            else:
                self._tree.Expand(item)

    def _on_key_down(self, event: wx.TreeEvent) -> None:
        key = event.GetKeyCode()
        key_event = event.GetKeyEvent()
        ctrl = key_event.ControlDown() if key_event else False

        if key == wx.WXK_DELETE:
            self._handle_delete_key()
        elif key == wx.WXK_F2:
            self._on_rename_item()
        elif key == wx.WXK_F5:
            self._on_start_all(None)
        elif ctrl and key == ord("C"):
            self._on_copy_file_path()
        elif ctrl and key == ord("R"):
            self._on_retry_selected()
        elif ctrl and key == ord("L"):
            self._on_open_file_location()
        else:
            event.Skip()

    def _handle_delete_key(self) -> None:
        """Handle Delete key — cancel or remove the selected job."""
        job_id = self.get_selected_job_id()
        if job_id:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.PENDING, JobStatus.TRANSCRIBING):
                self._main_frame.transcription_service.cancel_job(job_id)
                self.update_job_status(job_id, "Cancelled")
                announce_status(self._main_frame, f"Cancelled: {job.display_name}")
            elif job:
                # For completed/failed/cancelled — remove from queue
                self._remove_job(job_id)
                announce_status(self._main_frame, f"Removed: {job.display_name}")
        else:
            # Maybe a folder is selected
            item = self._tree.GetSelection()
            if item and item.IsOk():
                data = self._tree.GetItemData(item)
                if data and data.get("type") == "folder":
                    self._remove_folder(data["path"])

    def _on_context_menu_event(self, event: wx.ContextMenuEvent) -> None:
        """Handle context menu from right-click or keyboard."""
        pos = event.GetPosition()
        if pos == wx.DefaultPosition:
            # Keyboard-triggered
            item = self._tree.GetSelection()
            if item and item.IsOk():
                rect = self._tree.GetBoundingRect(item, textOnly=True)
                if rect:
                    pos = rect.GetPosition()
                    pos = self._tree.ClientToScreen(pos)
                else:
                    pos = self._tree.ClientToScreen(wx.Point(0, 0))
            else:
                pos = self._tree.ClientToScreen(wx.Point(0, 0))
        pos = self._tree.ScreenToClient(pos)
        self._on_context_menu(pos)

    def _on_context_menu(self, pos: wx.Point) -> None:
        """Build and show a context menu for the selected item."""
        hit_item, _flags = self._tree.HitTest(pos)
        if hit_item and hit_item.IsOk():
            self._tree.SelectItem(hit_item)

        item = self._tree.GetSelection()
        if not item or not item.IsOk():
            # No item selected — show empty-area context menu
            self._show_empty_area_context_menu()
            return

        data = self._tree.GetItemData(item)
        if not data:
            return

        if data.get("type") == "folder":
            self._show_folder_context_menu(data["path"])
            return

        job_id = data.get("job_id")
        if not job_id:
            return
        job = self._jobs.get(job_id)
        if not job:
            return

        menu = wx.Menu()
        is_pending = job.status == JobStatus.PENDING
        is_failed = job.status == JobStatus.FAILED
        is_active = job.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING)
        has_result = job.result is not None

        # -- View transcript --
        view_item = menu.Append(wx.ID_ANY, "&View Transcript\tEnter")
        view_item.Enable(has_result)
        self.Bind(wx.EVT_MENU, self._on_ctx_view_transcript, view_item)

        preview_item = menu.Append(wx.ID_ANY, "Audio &Preview…")
        self.Bind(
            wx.EVT_MENU,
            lambda e, jid=job_id: self._preview_audio_for_job(jid),
            preview_item,
        )

        menu.AppendSeparator()

        # -- Rename --
        rename_item = menu.Append(wx.ID_ANY, "Re&name…\tF2")
        self.Bind(wx.EVT_MENU, lambda e: self._on_rename_item(), rename_item)

        # -- Start this job --
        if is_pending:
            start_item = menu.Append(wx.ID_ANY, "&Start Transcription\tF5")
            self.Bind(wx.EVT_MENU, lambda e: self._on_start_all(None), start_item)

        # -- Retry failed job --
        if is_failed:
            retry_item = menu.Append(wx.ID_ANY, "&Retry Job\tCtrl+R")
            self.Bind(
                wx.EVT_MENU,
                lambda e, jid=job_id: self._retry_job(jid),
                retry_item,
            )

        menu.AppendSeparator()

        # -- Change Provider submenu --
        if is_pending:
            provider_menu = wx.Menu()
            enabled_providers = self._main_frame.provider_manager.list_enabled_providers()
            for pkey in enabled_providers:
                caps = self._main_frame.provider_manager.get_capabilities(pkey)
                label = caps.name if caps else pkey
                if pkey == job.provider:
                    label += " (current)"
                prov_item = provider_menu.AppendRadioItem(wx.ID_ANY, label)
                if pkey == job.provider:
                    prov_item.Check(True)
                self.Bind(
                    wx.EVT_MENU,
                    lambda e, pk=pkey, jid=job_id: self._change_job_provider(jid, pk),
                    prov_item,
                )
            menu.AppendSubMenu(provider_menu, "Change &Provider")

            # -- Change Model submenu --
            model_menu = wx.Menu()
            models = self._get_models_for_provider(job.provider)
            if models:
                for mid, mlabel in models:
                    if mid == job.model:
                        mlabel += " (current)"
                    m_item = model_menu.AppendRadioItem(wx.ID_ANY, mlabel)
                    if mid == job.model:
                        m_item.Check(True)
                    self.Bind(
                        wx.EVT_MENU,
                        lambda e, m=mid, jid=job_id: self._change_job_model(jid, m),
                        m_item,
                    )
            else:
                no_models = model_menu.Append(wx.ID_ANY, "(default)")
                no_models.Enable(False)
            menu.AppendSubMenu(model_menu, "Change &Model")

            # -- Change Language submenu --
            lang_menu = wx.Menu()
            common_langs = [
                ("auto", "Auto-Detect"),
                ("en", "English"),
                ("es", "Spanish"),
                ("fr", "French"),
                ("de", "German"),
                ("it", "Italian"),
                ("pt", "Portuguese"),
                ("nl", "Dutch"),
                ("ja", "Japanese"),
                ("ko", "Korean"),
                ("zh", "Chinese"),
                ("ar", "Arabic"),
                ("ru", "Russian"),
                ("hi", "Hindi"),
                ("pl", "Polish"),
                ("sv", "Swedish"),
                ("uk", "Ukrainian"),
            ]
            for lcode, lname in common_langs:
                display = lname
                if lcode == job.language:
                    display += " (current)"
                l_item = lang_menu.AppendRadioItem(wx.ID_ANY, display)
                if lcode == job.language:
                    l_item.Check(True)
                self.Bind(
                    wx.EVT_MENU,
                    lambda e, lc=lcode, jid=job_id: self._change_job_language(jid, lc),
                    l_item,
                )
            menu.AppendSubMenu(lang_menu, "Change &Language")

            # -- Toggle diarization --
            diar_item = menu.AppendCheckItem(wx.ID_ANY, "Include &Diarization")
            diar_item.Check(job.include_diarization)
            self.Bind(
                wx.EVT_MENU,
                lambda e, jid=job_id: self._toggle_job_diarization(jid),
                diar_item,
            )

            # -- AI Action submenu --
            ai_action_menu = self._build_ai_action_submenu(
                current=job.ai_action_template,
                callback=lambda template, jid=job_id: self._change_job_ai_action(jid, template),
            )
            menu.AppendSubMenu(ai_action_menu, "AI &Action")

            menu.AppendSeparator()

        # -- File operations --
        file_ops_menu = wx.Menu()
        copy_path_item = file_ops_menu.Append(wx.ID_ANY, "&Copy File Path\tCtrl+C")
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._copy_path_to_clipboard(job.file_path),
            copy_path_item,
        )
        open_loc_item = file_ops_menu.Append(wx.ID_ANY, "Open File &Location\tCtrl+L")
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._open_containing_folder(job.file_path),
            open_loc_item,
        )
        menu.AppendSubMenu(file_ops_menu, "&File Operations")

        menu.AppendSeparator()

        # -- Cancel / Remove --
        cancel_item = menu.Append(wx.ID_ANY, "&Cancel Job\tDel")
        cancel_item.Enable(is_pending or is_active)
        self.Bind(wx.EVT_MENU, self._on_ctx_cancel_job, cancel_item)

        remove_item = menu.Append(wx.ID_ANY, "&Remove from Queue")
        self.Bind(wx.EVT_MENU, self._on_ctx_remove_from_queue, remove_item)

        # -- Properties --
        menu.AppendSeparator()
        props_item = menu.Append(wx.ID_ANY, "P&roperties…")
        self.Bind(
            wx.EVT_MENU,
            lambda e, jid=job_id: self._show_job_properties(jid),
            props_item,
        )

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_ctx_view_transcript(self, _event: wx.CommandEvent) -> None:
        """Context menu: view transcript for the selected job."""
        job_id = self.get_selected_job_id()
        if job_id and job_id in self._jobs:
            job = self._jobs[job_id]
            if job.result:
                self._main_frame.transcript_panel.show_transcript(job)

    def _preview_audio_for_job(self, job_id: str) -> None:
        """Open the audio preview dialog for a job's source file."""
        job = self._jobs.get(job_id)
        if not job:
            return

        from bits_whisperer.ui.audio_player_dialog import AudioPlayerDialog

        dlg = AudioPlayerDialog(
            self,
            job.file_path,
            selection_start=job.clip_start_seconds,
            selection_end=job.clip_end_seconds,
            settings=self._main_frame.app_settings.playback,
        )
        dlg.ShowModal()
        dlg.Destroy()

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
        self._remove_job(job_id)
        self._update_all_folder_labels()
        self._update_summary()

    def _show_folder_context_menu(self, folder_path: str) -> None:
        """Show a context menu for a folder node.

        Args:
            folder_path: The absolute path of the folder.
        """
        menu = wx.Menu()

        # -- Rename --
        rename = menu.Append(wx.ID_ANY, "Re&name…\tF2")
        self.Bind(wx.EVT_MENU, lambda e: self._on_rename_item(), rename)

        menu.AppendSeparator()

        # -- Start / Retry / Cancel all in folder --
        children = self._get_jobs_in_folder(folder_path)
        has_pending = any(j.status == JobStatus.PENDING for j in children)
        has_failed = any(j.status == JobStatus.FAILED for j in children)
        has_active = any(
            j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING) for j in children
        )

        start_all = menu.Append(wx.ID_ANY, "&Start All Pending")
        start_all.Enable(has_pending)
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._start_folder_jobs(fp),
            start_all,
        )

        retry_failed = menu.Append(wx.ID_ANY, "Re&try All Failed")
        retry_failed.Enable(has_failed)
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._retry_folder_failed(fp),
            retry_failed,
        )

        cancel_all = menu.Append(wx.ID_ANY, "&Cancel All Active")
        cancel_all.Enable(has_active)
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._cancel_folder_active(fp),
            cancel_all,
        )

        # -- Set AI Action for all pending in folder --
        ai_action_menu = self._build_ai_action_submenu(
            current="",
            callback=lambda template, fp=folder_path: self._set_folder_ai_action(fp, template),
        )
        ai_action_folder = menu.AppendSubMenu(ai_action_menu, "Set AI &Action for Pending")
        ai_action_folder.Enable(has_pending)

        menu.AppendSeparator()

        expand = menu.Append(wx.ID_ANY, "&Expand All")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._expand_folder(fp),
            expand,
        )

        collapse = menu.Append(wx.ID_ANY, "Co&llapse")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._collapse_folder(fp),
            collapse,
        )

        menu.AppendSeparator()

        # -- File operations --
        copy_path = menu.Append(wx.ID_ANY, "&Copy Folder Path\tCtrl+C")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._copy_path_to_clipboard(fp),
            copy_path,
        )

        open_loc = menu.Append(wx.ID_ANY, "&Open Folder\tCtrl+L")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._open_containing_folder(fp, is_folder=True),
            open_loc,
        )

        menu.AppendSeparator()

        remove = menu.Append(wx.ID_ANY, "&Remove Folder from Queue")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._remove_folder(fp),
            remove,
        )

        menu.AppendSeparator()

        props = menu.Append(wx.ID_ANY, "P&roperties\u2026")
        self.Bind(
            wx.EVT_MENU,
            lambda e, fp=folder_path: self._show_folder_properties(fp),
            props,
        )

        self.PopupMenu(menu)
        menu.Destroy()

    def _expand_folder(self, folder_path: str) -> None:
        """Expand a folder and all sub-folders.

        Args:
            folder_path: Absolute path of the folder.
        """
        item = self._folder_tree_items.get(folder_path)
        if item and item.IsOk():
            self._tree.ExpandAllChildren(item)

    def _collapse_folder(self, folder_path: str) -> None:
        """Collapse a folder node.

        Args:
            folder_path: Absolute path of the folder.
        """
        item = self._folder_tree_items.get(folder_path)
        if item and item.IsOk():
            self._tree.CollapseAllChildren(item)

    def _remove_folder(self, folder_path: str) -> None:
        """Remove a folder and all its child jobs from the queue.

        Args:
            folder_path: Absolute path of the folder to remove.
        """
        item = self._folder_tree_items.get(folder_path)
        if not item or not item.IsOk():
            return

        # Remove all jobs within this folder
        fp_norm = os.path.normpath(folder_path)
        jobs_to_remove = [
            jid
            for jid, j in self._jobs.items()
            if os.path.normpath(str(Path(j.file_path).parent)).startswith(fp_norm)
        ]
        for jid in jobs_to_remove:
            self._jobs.pop(jid, None)
            self._job_tree_items.pop(jid, None)

        # Also remove any sub-folder entries
        sub_folders = [
            fp for fp in self._folder_tree_items if os.path.normpath(fp).startswith(fp_norm)
        ]
        for fp in sub_folders:
            self._folder_tree_items.pop(fp, None)

        self._tree.Delete(item)
        self._update_summary()

    def _show_folder_properties(self, folder_path: str) -> None:
        """Show properties dialog for a folder.

        Args:
            folder_path: Absolute path of the folder.
        """
        children = self._get_jobs_in_folder(folder_path)
        total_size = sum(j.file_size_bytes for j in children)
        size_mb = total_size / (1024 * 1024)
        pending = sum(1 for j in children if j.status == JobStatus.PENDING)
        completed = sum(1 for j in children if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in children if j.status == JobStatus.FAILED)
        custom_name = self._folder_custom_names.get(folder_path)

        display_name = custom_name or Path(folder_path).name
        msg = f"Folder: {display_name}\n"
        if custom_name:
            msg += f"Original name: {Path(folder_path).name}\n"
        msg += (
            f"Path: {folder_path}\n"
            f"Files: {len(children)}\n"
            f"Total size: {size_mb:.1f} MB\n\n"
            f"Pending: {pending}\n"
            f"Completed: {completed}\n"
            f"Failed: {failed}"
        )

        accessible_message_box(
            msg,
            f"Folder Properties \u2014 {display_name}",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------ #
    # Job setting helpers                                                  #
    # ------------------------------------------------------------------ #

    def _get_models_for_provider(self, provider_key: str) -> list[tuple[str, str]]:
        """Return a list of (model_id, display_label) pairs for a provider.

        Args:
            provider_key: Provider identifier.

        Returns:
            List of (id, label) tuples.
        """
        if provider_key in ("local_whisper",):
            return [(m.id, f"{m.name} \u2014 {m.description[:50]}") for m in WHISPER_MODELS]
        if provider_key == "openai_whisper":
            return [("whisper-1", "Whisper-1")]
        if provider_key == "groq_whisper":
            return [
                ("whisper-large-v3", "Whisper Large v3"),
                ("whisper-large-v3-turbo", "Whisper Large v3 Turbo"),
                ("distil-whisper-large-v3-en", "Distil Whisper Large v3 (English)"),
            ]
        if provider_key == "deepgram":
            return [
                ("nova-2", "Nova-2 (best)"),
                ("nova", "Nova"),
                ("enhanced", "Enhanced"),
                ("base", "Base"),
            ]
        if provider_key == "assemblyai":
            return [
                ("best", "Best"),
                ("nano", "Nano (faster, lower cost)"),
            ]
        if provider_key == "gemini":
            return [
                ("gemini-2.0-flash", "Gemini 2.0 Flash"),
                ("gemini-1.5-flash", "Gemini 1.5 Flash"),
                ("gemini-1.5-pro", "Gemini 1.5 Pro"),
            ]
        return []

    def _change_job_provider(self, job_id: str, provider_key: str) -> None:
        """Change the provider for a pending job.

        Args:
            job_id: Job identifier.
            provider_key: New provider key.
        """
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return
        job.provider = provider_key
        # Reset model to default for the new provider
        settings = self._main_frame.app_settings
        if provider_key == settings.general.default_provider:
            job.model = settings.general.default_model
        else:
            models = self._get_models_for_provider(provider_key)
            job.model = models[0][0] if models else ""
        # Update tree display
        item = self._job_tree_items.get(job_id)
        if item and item.IsOk():
            self._tree.SetItemText(item, self._format_item_text(job))
        announce_status(self._main_frame, f"Provider changed to {provider_key}")

    def _change_job_model(self, job_id: str, model_id: str) -> None:
        """Change the model for a pending job.

        Args:
            job_id: Job identifier.
            model_id: New model identifier.
        """
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return
        job.model = model_id
        announce_status(self._main_frame, f"Model changed to {model_id}")

    def _change_job_language(self, job_id: str, language: str) -> None:
        """Change the language for a pending job.

        Args:
            job_id: Job identifier.
            language: Language code or 'auto'.
        """
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return
        job.language = language
        label = language if language != "auto" else "Auto-Detect"
        announce_status(self._main_frame, f"Language changed to {label}")

    def _toggle_job_diarization(self, job_id: str) -> None:
        """Toggle speaker diarization for a pending job.

        Args:
            job_id: Job identifier.
        """
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return
        job.include_diarization = not job.include_diarization
        state = "enabled" if job.include_diarization else "disabled"
        announce_status(self._main_frame, f"Speaker diarization {state}")

    def _build_ai_action_submenu(
        self,
        current: str,
        callback,
    ) -> wx.Menu:
        """Build a submenu listing available AI action templates.

        Args:
            current: The currently selected template key (empty for none).
            callback: Called with the selected template key string.

        Returns:
            A :class:`wx.Menu` with radio items for each template.
        """
        from bits_whisperer.core.transcription_service import TranscriptionService

        sub = wx.Menu()

        # "None" option
        none_item = sub.AppendRadioItem(wx.ID_ANY, "None (transcribe only)")
        if not current:
            none_item.Check(True)
        self.Bind(
            wx.EVT_MENU,
            lambda e: callback(""),
            none_item,
        )

        # Built-in presets
        for preset_name in TranscriptionService._BUILTIN_PRESETS:
            label = preset_name
            if preset_name == current:
                label += " (current)"
            item = sub.AppendRadioItem(wx.ID_ANY, label)
            if preset_name == current:
                item.Check(True)
            self.Bind(
                wx.EVT_MENU,
                lambda e, t=preset_name: callback(t),
                item,
            )

        # Saved custom templates
        agents_dir = DATA_DIR / "agents"
        if agents_dir.is_dir():
            for f in sorted(agents_dir.glob("*.json")):
                try:
                    from bits_whisperer.core.copilot_service import AgentConfig

                    config = AgentConfig.load(f)
                    display = f"\u2605 {config.name}" if config.name else f.stem
                    fpath = str(f)
                    if fpath == current:
                        display += " (current)"
                    item = sub.AppendRadioItem(wx.ID_ANY, display)
                    if fpath == current:
                        item.Check(True)
                    self.Bind(
                        wx.EVT_MENU,
                        lambda e, t=fpath: callback(t),
                        item,
                    )
                except Exception:
                    pass

        return sub

    def _change_job_ai_action(self, job_id: str, template: str) -> None:
        """Change the AI action template for a pending job.

        Args:
            job_id: Job identifier.
            template: Template key (preset name, file path, or empty to clear).
        """
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return
        job.ai_action_template = template
        # Reset any prior AI action state
        job.ai_action_status = ""
        job.ai_action_result = ""
        job.ai_action_error = ""
        # Update tree display
        item = self._job_tree_items.get(job_id)
        if item and item.IsOk():
            self._tree.SetItemText(item, self._format_item_text(job))
        label = template.split("/")[-1].split("\\")[-1] if template else "None"
        announce_status(self._main_frame, f"AI action set to: {label}")

    def _set_folder_ai_action(self, folder_path: str, template: str) -> None:
        """Set the AI action template for all pending jobs in a folder.

        Args:
            folder_path: The folder whose pending jobs to update.
            template: Template key (preset name, file path, or empty to clear).
        """
        children = self._get_jobs_in_folder(folder_path)
        pending = [j for j in children if j.status == JobStatus.PENDING]
        for job in pending:
            job.ai_action_template = template
            job.ai_action_status = ""
            job.ai_action_result = ""
            job.ai_action_error = ""
            item = self._job_tree_items.get(job.id)
            if item and item.IsOk():
                self._tree.SetItemText(item, self._format_item_text(job))

        label = template.split("/")[-1].split("\\")[-1] if template else "None"
        count = len(pending)
        announce_status(
            self._main_frame,
            f"AI action set to {label} for {count} pending job{'s' if count != 1 else ''}",
        )

    def _show_job_properties(self, job_id: str) -> None:
        """Show a properties dialog for a job.

        Args:
            job_id: Job identifier.
        """
        job = self._jobs.get(job_id)
        if not job:
            return

        size_mb = job.file_size_bytes / (1024 * 1024)
        model_display = job.model or "(default)"
        lang_display = job.language if job.language != "auto" else "Auto-Detect"
        diar_display = "Yes" if job.include_diarization else "No"
        custom_name_display = job.custom_name or "(none)"

        msg = (
            f"File: {job.display_name}\n"
            f"Custom name: {custom_name_display}\n"
            f"Original file: {job.file_name or Path(job.file_path).name}\n"
            f"Path: {job.file_path}\n"
            f"Size: {size_mb:.1f} MB\n"
            f"Status: {job.status_text}\n\n"
            f"Provider: {job.provider}\n"
            f"Model: {model_display}\n"
            f"Language: {lang_display}\n"
            f"Diarization: {diar_display}\n"
            f"Timestamps: {'Yes' if job.include_timestamps else 'No'}\n"
            f"Cost: {job.cost_display}"
        )
        if job.error_message:
            msg += f"\n\nError: {job.error_message}"

        accessible_message_box(
            msg,
            f"Job Properties \u2014 {job.display_name}",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    # ------------------------------------------------------------------ #
    # Rename functionality                                                 #
    # ------------------------------------------------------------------ #

    def _on_rename_item(self) -> None:
        """Rename the currently selected job or folder via an accessible dialog."""
        item = self._tree.GetSelection()
        if not item or not item.IsOk():
            announce_to_screen_reader("No item selected to rename")
            return

        data = self._tree.GetItemData(item)
        if not data:
            return

        if data.get("type") == "job":
            self._rename_job(data["job_id"])
        elif data.get("type") == "folder":
            self._rename_folder(data["path"])

    def _rename_job(self, job_id: str) -> None:
        """Show a rename dialog for a job.

        Args:
            job_id: The job to rename.
        """
        job = self._jobs.get(job_id)
        if not job:
            return

        current_name = job.custom_name or job.display_name
        dlg = wx.TextEntryDialog(
            self,
            "Enter a custom name for this file.\n" "Leave blank to use the original file name.",
            "Rename — " + (job.file_name or Path(job.file_path).name),
            current_name,
        )
        set_accessible_name(dlg, "Rename file dialog")
        announce_to_screen_reader(
            f"Rename dialog. Current name: {current_name}. "
            "Type a new name or leave blank for the original."
        )

        if dlg.ShowModal() == wx.ID_OK:
            new_name = dlg.GetValue().strip()
            job.custom_name = new_name

            # Update tree display
            tree_item = self._job_tree_items.get(job_id)
            if tree_item and tree_item.IsOk():
                self._tree.SetItemText(tree_item, self._format_item_text(job))

            display = new_name or job.file_name or Path(job.file_path).name
            announce_status(self._main_frame, f"Renamed to: {display}")
            announce_to_screen_reader(f"Renamed to {display}")

        dlg.Destroy()

    def _rename_folder(self, folder_path: str) -> None:
        """Show a rename dialog for a folder.

        Args:
            folder_path: The folder to rename.
        """
        current_name = self._folder_custom_names.get(folder_path) or Path(folder_path).name
        dlg = wx.TextEntryDialog(
            self,
            "Enter a custom name for this folder.\n" "Leave blank to use the original folder name.",
            "Rename Folder — " + Path(folder_path).name,
            current_name,
        )
        set_accessible_name(dlg, "Rename folder dialog")
        announce_to_screen_reader(
            f"Rename folder dialog. Current name: {current_name}. "
            "Type a new name or leave blank for the original."
        )

        if dlg.ShowModal() == wx.ID_OK:
            new_name = dlg.GetValue().strip()
            if new_name:
                self._folder_custom_names[folder_path] = new_name
            else:
                self._folder_custom_names.pop(folder_path, None)

            # Update tree display
            tree_item = self._folder_tree_items.get(folder_path)
            if tree_item and tree_item.IsOk():
                self._tree.SetItemText(tree_item, self._format_folder_text(folder_path))

            display = new_name or Path(folder_path).name
            announce_status(self._main_frame, f"Folder renamed to: {display}")
            announce_to_screen_reader(f"Folder renamed to {display}")

        dlg.Destroy()

    # ------------------------------------------------------------------ #
    # File operations                                                      #
    # ------------------------------------------------------------------ #

    def _on_copy_file_path(self) -> None:
        """Copy the file path of the selected item to the clipboard."""
        item = self._tree.GetSelection()
        if not item or not item.IsOk():
            return

        data = self._tree.GetItemData(item)
        if not data:
            return

        if data.get("type") == "job":
            job = self._jobs.get(data["job_id"])
            if job:
                self._copy_path_to_clipboard(job.file_path)
        elif data.get("type") == "folder":
            self._copy_path_to_clipboard(data["path"])

    def _copy_path_to_clipboard(self, path: str) -> None:
        """Copy a path string to the system clipboard.

        Args:
            path: The file or folder path to copy.
        """
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(path))
            wx.TheClipboard.Close()
            announce_status(self._main_frame, f"Copied: {path}")
            announce_to_screen_reader("Path copied to clipboard")
        else:
            announce_to_screen_reader("Failed to copy to clipboard")

    def _on_open_file_location(self) -> None:
        """Open the containing folder of the selected item."""
        item = self._tree.GetSelection()
        if not item or not item.IsOk():
            return

        data = self._tree.GetItemData(item)
        if not data:
            return

        if data.get("type") == "job":
            job = self._jobs.get(data["job_id"])
            if job:
                self._open_containing_folder(job.file_path)
        elif data.get("type") == "folder":
            self._open_containing_folder(data["path"], is_folder=True)

    def _open_containing_folder(self, path: str, *, is_folder: bool = False) -> None:
        """Open the containing folder or the folder itself in the file manager.

        Args:
            path: File or folder path.
            is_folder: If ``True``, open *path* directly instead of its parent.
        """
        try:
            target = Path(path)
            folder = target if is_folder else target.parent

            if not folder.exists():
                accessible_message_box(
                    f"Folder not found:\n{folder}",
                    "Folder Not Found",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )
                return

            if sys.platform == "win32":
                if not is_folder and target.exists():
                    # Select the file in Explorer
                    subprocess.Popen(["explorer", "/select,", str(target)])
                else:
                    os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])

            announce_status(self._main_frame, f"Opened: {folder}")
        except Exception as exc:
            logger.warning("Could not open folder: %s", exc)
            announce_to_screen_reader("Could not open folder")

    # ------------------------------------------------------------------ #
    # Batch operations                                                     #
    # ------------------------------------------------------------------ #

    def _on_start_all(self, _event: wx.CommandEvent | None) -> None:
        """Start transcription for all pending jobs (delegates to main frame)."""
        self._main_frame._on_start(None)

    def _on_clear_completed(self, _event: wx.CommandEvent | None) -> None:
        """Remove all completed jobs from the queue."""
        completed_ids = [jid for jid, j in self._jobs.items() if j.status == JobStatus.COMPLETED]
        if not completed_ids:
            announce_status(self._main_frame, "No completed jobs to clear")
            return

        for jid in completed_ids:
            self._remove_job(jid)

        self._update_all_folder_labels()
        self._update_summary()
        count = len(completed_ids)
        announce_status(
            self._main_frame,
            f"Cleared {count} completed job{'s' if count != 1 else ''}",
        )
        announce_to_screen_reader(f"Cleared {count} completed jobs")

    def _on_retry_all_failed(self, _event: wx.CommandEvent | None) -> None:
        """Re-queue all failed jobs for another attempt."""
        failed_ids = [jid for jid, j in self._jobs.items() if j.status == JobStatus.FAILED]
        if not failed_ids:
            announce_status(self._main_frame, "No failed jobs to retry")
            return

        for jid in failed_ids:
            self._retry_job(jid)

        count = len(failed_ids)
        announce_status(
            self._main_frame,
            f"Retrying {count} failed job{'s' if count != 1 else ''}",
        )

    def _on_retry_selected(self) -> None:
        """Retry the currently selected failed job."""
        job_id = self.get_selected_job_id()
        if job_id:
            self._retry_job(job_id)

    def _retry_job(self, job_id: str) -> None:
        """Reset a failed or cancelled job back to pending for retry.

        Args:
            job_id: The job to retry.
        """
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
            announce_status(
                self._main_frame,
                f"Cannot retry — job is {job.status.value}",
            )
            return

        job.status = JobStatus.PENDING
        job.error_message = ""
        job.progress_percent = 0.0

        # Update tree display
        item = self._job_tree_items.get(job_id)
        if item and item.IsOk():
            self._tree.SetItemText(item, self._format_item_text(job))
            self._tree.SetItemTextColour(
                item, wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            )

        self._update_parent_folder_label(job_id)
        self._update_summary()
        self._main_frame._update_menu_state()
        announce_status(self._main_frame, f"Retrying: {job.display_name}")
        announce_to_screen_reader(f"Job reset to pending: {job.display_name}")

    def _remove_job(self, job_id: str) -> None:
        """Remove a single job from the queue.

        Args:
            job_id: The job to remove.
        """
        item = self._job_tree_items.get(job_id)
        if item and item.IsOk():
            self._tree.Delete(item)
        self._jobs.pop(job_id, None)
        self._job_tree_items.pop(job_id, None)

    # ------------------------------------------------------------------ #
    # Folder batch operations                                              #
    # ------------------------------------------------------------------ #

    def _start_folder_jobs(self, folder_path: str) -> None:
        """Start pending jobs within a specific folder.

        Args:
            folder_path: The folder whose pending jobs to start.
        """
        # We delegate to main frame start which picks up all pending jobs
        # For folder-specific, we could filter, but Start All is the common flow
        self._main_frame._on_start(None)

    def _retry_folder_failed(self, folder_path: str) -> None:
        """Retry all failed jobs within a folder.

        Args:
            folder_path: The folder path.
        """
        children = self._get_jobs_in_folder(folder_path)
        failed = [j for j in children if j.status == JobStatus.FAILED]
        for job in failed:
            self._retry_job(job.id)

        if failed:
            announce_status(
                self._main_frame,
                f"Retrying {len(failed)} failed job(s) in folder",
            )

    def _cancel_folder_active(self, folder_path: str) -> None:
        """Cancel all active jobs within a folder.

        Args:
            folder_path: The folder path.
        """
        children = self._get_jobs_in_folder(folder_path)
        active = [
            j
            for j in children
            if j.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING, JobStatus.PENDING)
        ]
        for job in active:
            self._main_frame.transcription_service.cancel_job(job.id)
            self.update_job_status(job.id, "Cancelled")

        if active:
            announce_status(
                self._main_frame,
                f"Cancelled {len(active)} job(s) in folder",
            )

    # ------------------------------------------------------------------ #
    # Empty area context menu                                              #
    # ------------------------------------------------------------------ #

    def _show_empty_area_context_menu(self) -> None:
        """Show a context menu when right-clicking on empty space."""
        menu = wx.Menu()

        add_files = menu.Append(wx.ID_ANY, "&Add Files…\tCtrl+O")
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._main_frame._on_add_files(None),
            add_files,
        )

        add_folder = menu.Append(wx.ID_ANY, "Add &Folder…\tCtrl+Shift+O")
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._main_frame._on_add_folder(None),
            add_folder,
        )

        menu.AppendSeparator()

        has_pending = bool(self.get_pending_jobs())
        has_completed = any(j.status == JobStatus.COMPLETED for j in self._jobs.values())
        has_failed = any(j.status == JobStatus.FAILED for j in self._jobs.values())

        start = menu.Append(wx.ID_ANY, "&Start All\tF5")
        start.Enable(has_pending)
        self.Bind(wx.EVT_MENU, lambda e: self._on_start_all(None), start)

        clear_done = menu.Append(wx.ID_ANY, "Clear &Completed")
        clear_done.Enable(has_completed)
        self.Bind(wx.EVT_MENU, lambda e: self._on_clear_completed(None), clear_done)

        retry = menu.Append(wx.ID_ANY, "&Retry All Failed")
        retry.Enable(has_failed)
        self.Bind(wx.EVT_MENU, lambda e: self._on_retry_all_failed(None), retry)

        menu.AppendSeparator()

        has_jobs = bool(self._jobs)
        clear_all = menu.Append(wx.ID_ANY, "C&lear Entire Queue\tCtrl+Shift+Del")
        clear_all.Enable(has_jobs)
        self.Bind(
            wx.EVT_MENU,
            lambda e: self._main_frame._on_clear_queue(None),
            clear_all,
        )

        self.PopupMenu(menu)
        menu.Destroy()

    # ------------------------------------------------------------------ #
    # Filter / search                                                      #
    # ------------------------------------------------------------------ #

    def _on_filter_changed(self, _event: wx.CommandEvent) -> None:
        """Handle changes to the filter input text."""
        self._filter_text = self._filter_input.GetValue().strip().lower()
        self._apply_filter()

    def _on_clear_filter(self, _event: wx.CommandEvent) -> None:
        """Clear the filter and show all items."""
        self._filter_input.SetValue("")
        self._filter_text = ""
        self._apply_filter()
        announce_to_screen_reader("Filter cleared — showing all items")

    def _apply_filter(self) -> None:
        """Show/hide tree items based on the current filter text.

        Since wx.TreeCtrl doesn't support hiding items, we toggle
        font colour to visually indicate filtered-out items and
        use bold for matches.
        """
        if not self._filter_text:
            # No filter — restore all items to default appearance
            normal_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            for job_id, item in self._job_tree_items.items():
                if item.IsOk():
                    job = self._jobs.get(job_id)
                    if job:
                        # Restore status-based colour
                        if job.status == JobStatus.COMPLETED:
                            self._tree.SetItemTextColour(item, wx.Colour(0, 128, 0))
                        elif job.status == JobStatus.FAILED:
                            self._tree.SetItemTextColour(item, wx.Colour(192, 0, 0))
                        elif job.status in (JobStatus.TRANSCODING, JobStatus.TRANSCRIBING):
                            self._tree.SetItemTextColour(
                                item,
                                wx.SystemSettings.GetColour(wx.SYS_COLOUR_HOTLIGHT),
                            )
                        else:
                            self._tree.SetItemTextColour(item, normal_colour)
                    self._tree.SetItemBold(item, False)
            for item in self._folder_tree_items.values():
                if item.IsOk():
                    self._tree.SetItemTextColour(item, normal_colour)
                    self._tree.SetItemBold(item, False)
            return

        # Apply filter — bold matches, dim non-matches
        dim_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        match_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        matched_folders: set[str] = set()

        for job_id, item in self._job_tree_items.items():
            if not item.IsOk():
                continue
            job = self._jobs.get(job_id)
            if not job:
                continue

            # Check if any searchable field matches
            searchable = (
                f"{job.display_name} {job.file_name} {job.custom_name} "
                f"{job.provider} {job.status.value}"
            ).lower()

            if self._filter_text in searchable:
                self._tree.SetItemBold(item, True)
                self._tree.SetItemTextColour(item, match_colour)
                # Mark parent folder as having a match
                parent = self._tree.GetItemParent(item)
                if parent and parent.IsOk() and parent != self._root:
                    parent_data = self._tree.GetItemData(parent)
                    if parent_data and parent_data.get("type") == "folder":
                        matched_folders.add(parent_data["path"])
            else:
                self._tree.SetItemBold(item, False)
                self._tree.SetItemTextColour(item, dim_colour)

        # Highlight folders with matches
        for fp, item in self._folder_tree_items.items():
            if not item.IsOk():
                continue
            folder_name = (self._folder_custom_names.get(fp, "") + " " + Path(fp).name).lower()
            if fp in matched_folders or self._filter_text in folder_name:
                self._tree.SetItemBold(item, True)
                self._tree.SetItemTextColour(item, match_colour)
                self._tree.Expand(item)
            else:
                self._tree.SetItemBold(item, False)
                self._tree.SetItemTextColour(item, dim_colour)

        # Count matches for screen reader
        match_count = sum(
            1
            for jid in self._job_tree_items
            if self._jobs.get(jid)
            and self._filter_text
            in (
                f"{self._jobs[jid].display_name} {self._jobs[jid].file_name} "
                f"{self._jobs[jid].custom_name} {self._jobs[jid].provider} "
                f"{self._jobs[jid].status.value}"
            ).lower()
        )
        total = len(self._jobs)
        announce_status(
            self._main_frame,
            f"Filter: {match_count} of {total} items match '{self._filter_text}'",
        )


# ======================================================================= #
# Drag & drop target                                                       #
# ======================================================================= #


class _FileDropTarget(wx.FileDropTarget):
    """Accept dragged audio files into the queue."""

    def __init__(self, panel: QueuePanel) -> None:
        super().__init__()
        self._panel = panel

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:
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
