"""Model Manager dialog — download, delete, and inspect Whisper models."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.device_probe import DeviceProfile
from bits_whisperer.core.model_manager import ModelManager
from bits_whisperer.core.sdk_installer import ensure_sdk
from bits_whisperer.utils.accessibility import (
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import WHISPER_MODELS, WhisperModelInfo
from bits_whisperer.utils.platform_utils import get_free_disk_space_mb, has_sufficient_disk_space

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ModelManagerDialog(wx.Dialog):
    """Dialog for managing local Whisper models.

    Shows all available Whisper models with:
    - Name and plain-English description
    - Disk size, VRAM/RAM requirements
    - Speed/accuracy star ratings
    - Download status and actions
    - Hardware eligibility indicator
    """

    def __init__(
        self,
        parent: wx.Window,
        model_manager: ModelManager,
        device_profile: DeviceProfile,
    ) -> None:
        super().__init__(
            parent,
            title="Manage Whisper Models",
            size=(750, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Model manager dialog")
        self._mm = model_manager
        self._dp = device_profile
        self._downloading = False
        self._download_model_id: str | None = None
        self._expected_bytes = 0
        self._download_dir = None
        self._progress_timer: wx.Timer | None = None

        self._build_ui()
        self._populate()
        self.CentreOnParent()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Intro
        intro = wx.StaticText(
            self,
            label=(
                "Download Whisper models for on-device transcription. "
                "Larger models are more accurate but need more memory and disk space. "
                "Models marked as Slow may run slowly on your hardware."
            ),
        )
        intro.Wrap(700)
        set_accessible_name(intro, "Model manager instructions")
        sizer.Add(intro, 0, wx.ALL, 8)

        # Disk usage
        total = self._mm.get_total_disk_usage_mb()
        self._disk_label = wx.StaticText(self, label=f"Disk usage: {total:.0f} MB")
        set_accessible_name(self._disk_label, "Total disk usage")
        sizer.Add(self._disk_label, 0, wx.LEFT | wx.RIGHT, 8)

        # Model list
        self._list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        set_accessible_name(self._list, "Available Whisper models")
        set_accessible_help(
            self._list,
            "List of all Whisper models. Select a model and press Download or Delete.",
        )

        self._list.InsertColumn(0, "Model", width=170)
        self._list.InsertColumn(1, "Status", width=90)
        self._list.InsertColumn(2, "Size", width=75)
        self._list.InsertColumn(3, "Speed", width=65)
        self._list.InsertColumn(4, "Accuracy", width=75)
        self._list.InsertColumn(5, "Hardware", width=80)

        sizer.Add(self._list, 1, wx.ALL | wx.EXPAND, 8)

        # Description area
        self._desc_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 60),
        )
        set_accessible_name(self._desc_text, "Model description")
        sizer.Add(self._desc_text, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # Progress row (gauge + percentage label) — hidden until download starts
        progress_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._progress = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        set_accessible_name(self._progress, "Download progress")
        self._progress_label = wx.StaticText(self, label="")
        set_accessible_name(self._progress_label, "Download progress percentage")
        progress_sizer.Add(self._progress, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        progress_sizer.Add(self._progress_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self._progress.Hide()
        self._progress_label.Hide()
        sizer.Add(progress_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._dl_btn = wx.Button(self, label="&Download")
        self._del_btn = wx.Button(self, label="D&elete")
        self._close_btn = wx.Button(self, wx.ID_CLOSE, "&Close")

        set_accessible_name(self._dl_btn, "Download selected model")
        set_accessible_name(self._del_btn, "Delete selected model")

        btn_sizer.Add(self._dl_btn, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._del_btn, 0, wx.RIGHT, 4)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._close_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)

        # Start with buttons disabled (nothing selected)
        self._dl_btn.Disable()
        self._del_btn.Disable()

        # Events
        self._dl_btn.Bind(wx.EVT_BUTTON, self._on_download)
        self._del_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        self._close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self._list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_deselect)
        self.Bind(wx.EVT_CLOSE, self._on_close_event)

    # ------------------------------------------------------------------ #
    # Populate                                                             #
    # ------------------------------------------------------------------ #

    def _populate(self, select_model_id: str | None = None) -> None:
        """Populate the model list, optionally selecting a specific model.

        Args:
            select_model_id: If provided, select and focus this model after populating.
        """
        self._list.DeleteAllItems()
        select_idx = -1
        for i, mi in enumerate(WHISPER_MODELS):
            idx = self._list.InsertItem(self._list.GetItemCount(), mi.name)
            downloaded = self._mm.is_downloaded(mi.id)
            self._list.SetItem(idx, 1, "Downloaded" if downloaded else "\u2014")
            self._list.SetItem(idx, 2, f"{mi.disk_size_mb} MB")
            self._list.SetItem(idx, 3, f"{mi.speed_stars} of 5")
            self._list.SetItem(idx, 4, f"{mi.accuracy_stars} of 5")

            if mi.id in self._dp.eligible_models:
                hw_status = "Ready"
            elif mi.id in self._dp.warned_models:
                hw_status = "Slow"
            else:
                hw_status = "Too big"
            self._list.SetItem(idx, 5, hw_status)

            if select_model_id and mi.id == select_model_id:
                select_idx = i

        self._update_disk_label()

        # Restore selection and focus
        if select_idx >= 0:
            self._list.Select(select_idx)
            self._list.Focus(select_idx)
            self._list.EnsureVisible(select_idx)
            mi = WHISPER_MODELS[select_idx]
            self._show_model_description(mi)
            self._update_button_states()

    def _update_disk_label(self) -> None:
        total = self._mm.get_total_disk_usage_mb()
        free = get_free_disk_space_mb(self._mm.models_dir)
        self._disk_label.SetLabel(f"Disk usage: {total:.0f} MB  |  Free: {free:.0f} MB")

    def _show_model_description(self, mi: WhisperModelInfo) -> None:
        """Update the description area with model info."""
        self._desc_text.SetValue(
            f"{mi.name}\n{mi.description}\n\n"
            f"Parameters: {mi.parameters_m}M  |  "
            f"Min RAM: {mi.min_ram_gb} GB  |  "
            f"Min VRAM: {mi.min_vram_gb} GB  |  "
            f"Languages: {mi.languages}"
        )

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _update_button_states(self) -> None:
        """Enable/disable Download and Delete buttons based on selection and model state."""
        if self._downloading:
            self._dl_btn.Disable()
            self._del_btn.Disable()
            return
        idx = self._list.GetFirstSelected()
        if idx == -1 or idx >= len(WHISPER_MODELS):
            self._dl_btn.Disable()
            self._del_btn.Disable()
            return
        mi = WHISPER_MODELS[idx]
        downloaded = self._mm.is_downloaded(mi.id)
        self._dl_btn.Enable(not downloaded)
        self._del_btn.Enable(downloaded)

    def _on_deselect(self, _event: wx.ListEvent) -> None:
        """Disable action buttons when no model is selected."""
        if not self._downloading:
            self._dl_btn.Disable()
            self._del_btn.Disable()

    def _on_select(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(WHISPER_MODELS):
            mi = WHISPER_MODELS[idx]
            self._show_model_description(mi)
        self._update_button_states()

    def _on_close(self, _event: wx.CommandEvent) -> None:
        """Handle Close button press."""
        if self._downloading:
            wx.MessageBox(
                "A model download is in progress.\n\n"
                "Please wait for it to finish before closing.",
                "Download In Progress",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        self.EndModal(wx.ID_CLOSE)

    def _on_close_event(self, event: wx.CloseEvent) -> None:
        """Handle window close (X button, Alt+F4)."""
        if self._downloading and event.CanVeto():
            wx.MessageBox(
                "A model download is in progress.\n\n"
                "Please wait for it to finish before closing.",
                "Download In Progress",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            event.Veto()
            return
        event.Skip()

    def _on_download(self, _event: wx.CommandEvent) -> None:
        idx = self._list.GetFirstSelected()
        if idx == -1 or self._downloading:
            return
        mi = WHISPER_MODELS[idx]
        if self._mm.is_downloaded(mi.id):
            wx.MessageBox(
                f"{mi.name} is already downloaded.",
                "Already Downloaded",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Ensure faster-whisper SDK is installed before downloading a model
        if not ensure_sdk("local_whisper", parent_window=self):
            return

        # Disk space pre-check
        required_mb = mi.disk_size_mb * 1.1
        if not has_sufficient_disk_space(self._mm.models_dir, required_mb):
            free = get_free_disk_space_mb(self._mm.models_dir)
            wx.MessageBox(
                f"Not enough disk space to download {mi.name}.\n\n"
                f"Required: {mi.disk_size_mb} MB\n"
                f"Available: {free:.0f} MB\n\n"
                "Please free up disk space and try again.",
                "Insufficient Disk Space",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        # Enter downloading state
        self._downloading = True
        self._download_model_id = mi.id
        self._dl_btn.Disable()
        self._del_btn.Disable()
        self._close_btn.Disable()

        # Show progress UI with determinate progress
        self._progress.SetValue(0)
        self._progress.Show()
        self._progress_label.SetLabel(f"Downloading {mi.name}\u2026 0%")
        self._progress_label.Show()
        self._desc_text.SetValue(
            f"Downloading {mi.name}\u2026\n" "This may take a few minutes for larger models."
        )
        self.Layout()

        # Update the list status column to show downloading
        self._list.SetItem(idx, 1, "Downloading")

        # Start progress monitoring timer (poll download dir size)
        self._expected_bytes = mi.disk_size_mb * 1024 * 1024
        self._download_dir = self._mm.get_download_dir(mi.id)
        self._progress_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_progress_tick, self._progress_timer)
        self._progress_timer.Start(500)

        def _do_download():
            try:
                self._mm.download_model(mi.id)
                safe_call_after(self._download_complete, mi, True, "")
            except Exception as exc:
                safe_call_after(self._download_complete, mi, False, str(exc))

        t = threading.Thread(target=_do_download, daemon=True)
        t.start()

    def _on_progress_tick(self, _event: wx.TimerEvent) -> None:
        """Poll download directory size and update progress UI."""
        if not self._downloading or not self._download_dir:
            return
        try:
            if self._download_dir.exists():
                current_bytes = sum(
                    f.stat().st_size for f in self._download_dir.rglob("*") if f.is_file()
                )
            else:
                current_bytes = 0

            if self._expected_bytes > 0:
                pct = min(int(current_bytes / self._expected_bytes * 100), 99)
            else:
                pct = 0

            self._progress.SetValue(pct)
            mi_name = ""
            if self._download_model_id:
                for m in WHISPER_MODELS:
                    if m.id == self._download_model_id:
                        mi_name = m.name
                        break
            self._progress_label.SetLabel(f"Downloading {mi_name}\u2026 {pct}%")
        except Exception:
            # Directory might be in flux during download; ignore transient errors
            pass

    def _download_complete(self, mi: WhisperModelInfo, success: bool, error: str) -> None:
        """Handle download completion on the UI thread."""
        # Stop progress timer
        if self._progress_timer:
            self._progress_timer.Stop()
            self._progress_timer = None

        # Exit downloading state
        self._downloading = False
        self._download_model_id = None

        # Hide progress UI
        self._progress.SetValue(100 if success else 0)
        self._progress.Hide()
        self._progress_label.Hide()

        # Re-enable close button
        self._close_btn.Enable()

        # Refresh list and restore selection to this model
        self._populate(select_model_id=mi.id)

        if success:
            # Inline success feedback — no dialog interruption
            self._desc_text.SetValue(
                f"\u2713 {mi.name} downloaded successfully!\n\n"
                f"{mi.description}\n\n"
                f"Parameters: {mi.parameters_m}M  |  "
                f"Min RAM: {mi.min_ram_gb} GB  |  "
                f"Min VRAM: {mi.min_vram_gb} GB  |  "
                f"Languages: {mi.languages}"
            )
            logger.info("Model '%s' downloaded successfully.", mi.id)
        else:
            wx.MessageBox(
                f"Failed to download {mi.name}:\n{error}",
                "Download Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_delete(self, _event: wx.CommandEvent) -> None:
        idx = self._list.GetFirstSelected()
        if idx == -1:
            return
        mi = WHISPER_MODELS[idx]
        if not self._mm.is_downloaded(mi.id):
            return

        if (
            wx.MessageBox(
                f"Delete {mi.name} ({mi.disk_size_mb} MB)?\n\n" "You can re-download it later.",
                "Confirm Delete",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            == wx.YES
        ):
            self._mm.delete_model(mi.id)
            self._populate(select_model_id=mi.id)
