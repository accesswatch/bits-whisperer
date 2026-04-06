"""Model Manager dialog — download, delete, and inspect models.

Multi-provider treeview supporting Whisper (faster-whisper) and
Ollama (local LLM) model management from a single unified dialog.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.device_probe import DeviceProfile
from bits_whisperer.core.model_manager import ModelManager, UnifiedModelInfo
from bits_whisperer.core.sdk_installer import ensure_sdk
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_to_screen_reader,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import WHISPER_MODELS, WhisperModelInfo
from bits_whisperer.utils.platform_utils import get_free_disk_space_mb, has_sufficient_disk_space

if TYPE_CHECKING:
    from bits_whisperer.core.ollama_adapter import CancelToken

logger = logging.getLogger(__name__)


class ModelManagerDialog(wx.Dialog):
    """Dialog for managing local models across all providers.

    Uses a ``wx.TreeCtrl`` with provider root nodes (Whisper, Ollama)
    and model child nodes showing status, size, and hardware eligibility.
    Supports downloading/pulling and deleting models for each provider.
    """

    def __init__(
        self,
        parent: wx.Window,
        model_manager: ModelManager,
        device_profile: DeviceProfile,
    ) -> None:
        super().__init__(
            parent,
            title="Manage Models",
            size=(800, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, "Model manager dialog")
        self._mm = model_manager
        self._dp = device_profile
        self._downloading = False
        self._download_model_id: str | None = None
        self._download_provider: str = ""
        self._expected_bytes = 0
        self._download_dir: Path | None = None
        self._progress_timer: wx.Timer | None = None
        self._cancel_token: CancelToken | None = None

        # Map tree item IDs → UnifiedModelInfo
        self._item_map: dict[int, UnifiedModelInfo] = {}

        self._build_ui()
        self._populate()
        self.CentreOnParent()
        wx.CallAfter(self._tree.SetFocus)

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Intro
        intro = wx.StaticText(
            self,
            label=(
                "Manage transcription and AI chat models. "
                "Whisper models run on-device for transcription. "
                "Ollama models run locally for AI chat. "
                "Larger models need more memory and disk space."
            ),
        )
        intro.Wrap(760)
        set_accessible_name(intro, "Model manager instructions")
        sizer.Add(intro, 0, wx.ALL, 8)

        # Disk usage
        total = self._mm.get_total_disk_usage_mb()
        self._disk_label = wx.StaticText(self, label=f"Whisper disk usage: {total:.0f} MB")
        set_accessible_name(self._disk_label, "Total disk usage")
        sizer.Add(self._disk_label, 0, wx.LEFT | wx.RIGHT, 8)

        # Model tree
        self._tree = wx.TreeCtrl(
            self,
            style=(wx.TR_DEFAULT_STYLE | wx.TR_SINGLE | wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT),
        )
        set_accessible_name(self._tree, "Available models")
        set_accessible_help(
            self._tree,
            "Tree of model providers and their models. "
            "Select a model and press Download or Delete.",
        )
        sizer.Add(self._tree, 1, wx.ALL | wx.EXPAND, 8)

        # Description area
        self._desc_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 70),
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
        self._pull_btn = wx.Button(self, label="&Pull Ollama Model\u2026")
        self._close_btn = wx.Button(self, wx.ID_CLOSE, "&Close")

        set_accessible_name(self._dl_btn, "Download selected model")
        set_accessible_help(
            self._dl_btn,
            "Download or pull the selected model for offline use",
        )
        set_accessible_name(self._del_btn, "Delete selected model")
        set_accessible_help(
            self._del_btn,
            "Remove the selected model from disk to free space",
        )
        set_accessible_name(self._pull_btn, "Pull an Ollama model by name")
        set_accessible_help(
            self._pull_btn,
            "Enter a model name to pull from the Ollama library or Hugging Face",
        )

        btn_sizer.Add(self._dl_btn, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._del_btn, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._pull_btn, 0, wx.RIGHT, 4)
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
        self._pull_btn.Bind(wx.EVT_BUTTON, self._on_pull_ollama)
        self._close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        self._tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_select)
        self._tree.Bind(wx.EVT_CONTEXT_MENU, self._on_tree_context_menu)
        self.Bind(wx.EVT_CLOSE, self._on_close_event)

    # ------------------------------------------------------------------ #
    # Populate                                                             #
    # ------------------------------------------------------------------ #

    def _populate(self, select_model_id: str | None = None) -> None:
        """Populate the tree with provider roots and model children.

        Args:
            select_model_id: If provided, select and focus this model after populating.
        """
        self._tree.DeleteAllItems()
        self._item_map.clear()

        root = self._tree.AddRoot("Models")
        summaries = self._mm.get_provider_summaries()
        unified = self._mm.get_unified_models()

        select_item: wx.TreeItemId | None = None

        for summary in summaries:
            label = f"{summary.name}  ({summary.downloaded_count}/{summary.available_count})"
            provider_item = self._tree.AppendItem(root, label)

            # Add child nodes for this provider, sorted by rank descending
            provider_models = sorted(
                [m for m in unified if m.provider == summary.provider_id],
                key=lambda m: m.rank_score,
                reverse=True,
            )
            for model in provider_models:
                child_label = self._format_model_label(model)
                child = self._tree.AppendItem(provider_item, child_label)
                self._item_map[child.GetID()] = model
                if select_model_id and model.model_id == select_model_id:
                    select_item = child

            self._tree.Expand(provider_item)

        self._update_disk_label()

        if select_item is not None:
            self._tree.SelectItem(select_item)
            self._tree.EnsureVisible(select_item)
        elif self._tree.GetChildrenCount(root) > 0:
            # Select first provider node
            first_child, _cookie = self._tree.GetFirstChild(root)
            if first_child.IsOk():
                self._tree.Expand(first_child)

    def _format_model_label(self, model: UnifiedModelInfo) -> str:
        """Create a tree item label for a model.

        Args:
            model: Unified model info.

        Returns:
            Formatted label string.
        """
        status = model.status.title()
        size_str = (
            f"{model.size_gb:.1f} GB" if model.size_gb >= 1.0 else f"{int(model.size_gb * 1024)} MB"
        )

        if model.provider == "whisper":
            hw_label = self._whisper_hw_label(model.model_id)
            speed = model.extra.get("speed_stars", "")
            acc = model.extra.get("accuracy_stars", "")
            extras = f" | Speed {speed}/5 | Accuracy {acc}/5" if speed else ""
            return f"{model.name} — {status} — {size_str} — {hw_label}{extras}"

        # Ollama and other providers
        param = f" ({model.parameter_size})" if model.parameter_size else ""
        return f"{model.name}{param} — {status} — {size_str}"

    def _whisper_hw_label(self, model_id: str) -> str:
        """Return a hardware eligibility label for a Whisper model.

        Args:
            model_id: Whisper model identifier.

        Returns:
            'Ready', 'Slow', or 'Too big'.
        """
        if model_id in self._dp.eligible_models:
            return "Ready"
        if model_id in self._dp.warned_models:
            return "Slow"
        return "Too big"

    def _update_disk_label(self) -> None:
        total = self._mm.get_total_disk_usage_mb()
        free = get_free_disk_space_mb(self._mm.models_dir)
        self._disk_label.SetLabel(f"Whisper disk usage: {total:.0f} MB  |  Free: {free:.0f} MB")

    def _show_model_description(self, model: UnifiedModelInfo) -> None:
        """Update the description area with model info.

        Args:
            model: The selected model's unified info.
        """
        if model.provider == "whisper":
            mi = self._get_whisper_info(model.model_id)
            if mi:
                self._desc_text.SetValue(
                    f"{mi.name}\n{mi.description}\n\n"
                    f"Parameters: {mi.parameters_m}M  |  "
                    f"Min RAM: {mi.min_ram_gb} GB  |  "
                    f"Min VRAM: {mi.min_vram_gb} GB  |  "
                    f"Languages: {mi.languages}"
                )
                return

        # Ollama or generic
        lines = [model.name]
        if model.description:
            lines.append(model.description)
        details = []
        if model.parameter_size:
            details.append(f"Parameters: {model.parameter_size}")
        if model.size_gb:
            details.append(f"Size: {model.size_gb:.1f} GB")
        if model.context_window:
            details.append(f"Context: {model.context_window:,} tokens")
        quant = model.extra.get("quantization", "")
        if quant:
            details.append(f"Quantization: {quant}")
        if model.version:
            details.append(f"Version: {model.version}")
        if model.rank_score:
            details.append(f"Rank: {model.rank_score:.1f}")
        rec = model.extra.get("recommended_devices", "")
        if rec:
            details.append(f"Devices: {rec}")
        if model.last_updated:
            details.append(f"Updated: {model.last_updated}")
        if model.disk_path:
            details.append(f"Path: {model.disk_path}")
        if details:
            lines.append("\n" + "  |  ".join(details))
        self._desc_text.SetValue("\n".join(lines))

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _get_selected_model(self) -> UnifiedModelInfo | None:
        """Return the ``UnifiedModelInfo`` for the selected tree item."""
        sel = self._tree.GetSelection()
        if not sel.IsOk():
            return None
        return self._item_map.get(sel.GetID())

    def _get_whisper_info(self, model_id: str) -> WhisperModelInfo | None:
        """Look up a Whisper model by ID.

        Args:
            model_id: Whisper model identifier.

        Returns:
            WhisperModelInfo or None if not found.
        """
        for m in WHISPER_MODELS:
            if m.id == model_id:
                return m
        return None

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on selection and model state."""
        if self._downloading:
            self._dl_btn.Disable()
            self._del_btn.Disable()
            return

        model = self._get_selected_model()
        if not model:
            self._dl_btn.Disable()
            self._del_btn.Disable()
            return

        if model.provider == "whisper":
            downloaded = self._mm.is_downloaded(model.model_id)
            self._dl_btn.SetLabel("&Download")
            self._dl_btn.Enable(not downloaded)
            self._del_btn.Enable(downloaded)
        elif model.provider == "ollama":
            # Ollama models listed are always downloaded
            self._dl_btn.SetLabel("&Download")
            self._dl_btn.Disable()
            self._del_btn.Enable(True)
        else:
            self._dl_btn.Disable()
            self._del_btn.Disable()

    def _on_tree_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        """Right-click context menu for the model tree."""
        model = self._get_selected_model()
        menu = wx.Menu()

        if model and model.provider == "whisper":
            downloaded = self._mm.is_downloaded(model.model_id)
            dl_item = menu.Append(wx.ID_ANY, "&Download")
            self.Bind(wx.EVT_MENU, self._on_download, dl_item)
            dl_item.Enable(not downloaded and not self._downloading)

            del_item = menu.Append(wx.ID_ANY, "D&elete")
            self.Bind(wx.EVT_MENU, self._on_delete, del_item)
            del_item.Enable(downloaded and not self._downloading)

        elif model and model.provider == "ollama":
            del_item = menu.Append(wx.ID_ANY, "D&elete from Ollama")
            self.Bind(wx.EVT_MENU, self._on_delete, del_item)
            del_item.Enable(not self._downloading)

        menu.AppendSeparator()

        pull_item = menu.Append(wx.ID_ANY, "&Pull Ollama Model\u2026")
        self.Bind(wx.EVT_MENU, self._on_pull_ollama, pull_item)

        if model:
            menu.AppendSeparator()

            details_item = menu.Append(wx.ID_ANY, "&View Details")
            self.Bind(
                wx.EVT_MENU,
                lambda e, m=model: self._show_model_details(m),
                details_item,
            )

            folder_item = menu.Append(wx.ID_ANY, "Open &Folder")
            self.Bind(
                wx.EVT_MENU,
                lambda e, m=model: self._open_model_folder(m),
                folder_item,
            )
            # Enable Open Folder only when a disk path is available
            folder_item.Enable(bool(model.disk_path) or model.provider == "whisper")

            copy_item = menu.Append(wx.ID_ANY, "&Copy Model ID")
            self.Bind(
                wx.EVT_MENU,
                lambda e, m=model: self._copy_model_id(m),
                copy_item,
            )

        self.PopupMenu(menu)
        menu.Destroy()

    def _copy_model_id(self, model: UnifiedModelInfo) -> None:
        """Copy the model ID to the clipboard.

        Args:
            model: The model whose ID to copy.
        """
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(model.model_id))
            wx.TheClipboard.Close()
            announce_to_screen_reader(f"Copied {model.model_id}")

    def _show_model_details(self, model: UnifiedModelInfo) -> None:
        """Show a dialog with full model details.

        Args:
            model: The model to inspect.
        """
        lines = [
            f"Model ID: {model.model_id}",
            f"Name: {model.name}",
            f"Provider: {model.provider}",
            f"Status: {model.status.title()}",
        ]
        if model.description:
            lines.append(f"Description: {model.description}")
        if model.size_gb:
            lines.append(f"Size: {model.size_gb:.2f} GB")
        if model.parameter_size:
            lines.append(f"Parameters: {model.parameter_size}")
        if model.context_window:
            lines.append(f"Context Window: {model.context_window:,} tokens")
        if model.version:
            lines.append(f"Version: {model.version}")
        if model.rank_score:
            lines.append(f"Rank Score: {model.rank_score:.1f}")
        rec = model.extra.get("recommended_devices", "")
        if rec:
            lines.append(f"Recommended Devices: {rec}")
        if model.last_updated:
            lines.append(f"Last Updated: {model.last_updated}")
        if model.disk_path:
            lines.append(f"Disk Path: {model.disk_path}")
        quant = model.extra.get("quantization", "")
        if quant:
            lines.append(f"Quantization: {quant}")
        family = model.extra.get("family", "")
        if family:
            lines.append(f"Family: {family}")
        # Whisper-specific extras
        for key, label in [
            ("speed_stars", "Speed"),
            ("accuracy_stars", "Accuracy"),
            ("min_ram_gb", "Min RAM (GB)"),
            ("min_vram_gb", "Min VRAM (GB)"),
            ("repo_id", "HuggingFace Repo"),
        ]:
            val = model.extra.get(key, "")
            if val:
                lines.append(f"{label}: {val}")

        accessible_message_box(
            "\n".join(lines),
            f"Model Details — {model.name}",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _open_model_folder(self, model: UnifiedModelInfo) -> None:
        """Open the model's disk location in the system file explorer.

        Args:
            model: The model whose folder to open.
        """
        import os
        import subprocess

        folder: Path | None = None
        if model.disk_path:
            folder = Path(model.disk_path)
        elif model.provider == "whisper":
            folder = self._mm.get_download_dir(model.model_id)

        if folder and folder.exists():
            if wx.Platform == "__WXMSW__":
                os.startfile(str(folder))
            elif wx.Platform == "__WXMAC__":
                subprocess.Popen(["open", str(folder)], check=False)
            else:
                subprocess.Popen(["xdg-open", str(folder)], check=False)
        else:
            accessible_message_box(
                "Could not locate the model folder on disk.",
                "Folder Not Found",
                wx.OK | wx.ICON_WARNING,
                self,
            )

    def _on_select(self, _event: wx.TreeEvent) -> None:
        """Handle tree selection change."""
        model = self._get_selected_model()
        if model:
            self._show_model_description(model)
        self._update_button_states()

    def _on_close(self, _event: wx.CommandEvent) -> None:
        """Handle Close button press."""
        if self._downloading:
            accessible_message_box(
                "A model download is in progress.\n\nPlease wait for it to finish before closing.",
                "Download In Progress",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        self.EndModal(wx.ID_CLOSE)

    def _on_close_event(self, event: wx.CloseEvent) -> None:
        """Handle window close (X button, Alt+F4)."""
        if self._downloading and event.CanVeto():
            accessible_message_box(
                "A model download is in progress.\n\nPlease wait for it to finish before closing.",
                "Download In Progress",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            event.Veto()
            return
        event.Skip()

    def _on_download(self, _event: wx.CommandEvent) -> None:
        """Download/pull the selected model."""
        model = self._get_selected_model()
        if not model or self._downloading:
            return

        if model.provider == "whisper":
            self._download_whisper(model)
        elif model.provider == "ollama":
            self._pull_ollama_model(model.model_id)

    def _on_delete(self, _event: wx.CommandEvent) -> None:
        """Delete the selected model."""
        model = self._get_selected_model()
        if not model:
            return

        if model.provider == "whisper":
            self._delete_whisper(model)
        elif model.provider == "ollama":
            self._delete_ollama(model)

    def _on_pull_ollama(self, _event: wx.CommandEvent) -> None:
        """Prompt the user for an Ollama model name and pull it."""
        if self._downloading:
            accessible_message_box(
                "A download is already in progress.",
                "Download In Progress",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        dlg = wx.TextEntryDialog(
            self,
            "Enter a model name to pull from the Ollama library "
            "or Hugging Face.\n\n"
            "Examples:\n"
            "  llama3.2\n"
            "  mistral:7b-instruct\n"
            "  hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF",
            "Pull Ollama Model",
        )
        set_accessible_name(dlg, "Pull Ollama model name entry")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            dlg.Destroy()
            if name:
                self._pull_ollama_model(name)
        else:
            dlg.Destroy()

    # ------------------------------------------------------------------ #
    # Whisper download / delete                                            #
    # ------------------------------------------------------------------ #

    def _download_whisper(self, model: UnifiedModelInfo) -> None:
        """Download a Whisper model.

        Args:
            model: The unified model info for a Whisper model.
        """
        mi = self._get_whisper_info(model.model_id)
        if not mi:
            return

        if self._mm.is_downloaded(mi.id):
            accessible_message_box(
                f"{mi.name} is already downloaded.",
                "Already Downloaded",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Ensure faster-whisper SDK is installed before downloading
        if not ensure_sdk("local_whisper", parent_window=self):
            return

        # Disk space pre-check
        required_mb = mi.disk_size_mb * 1.1
        if not has_sufficient_disk_space(self._mm.models_dir, required_mb):
            free = get_free_disk_space_mb(self._mm.models_dir)
            accessible_message_box(
                f"Not enough disk space to download {mi.name}.\n\n"
                f"Required: {mi.disk_size_mb} MB\n"
                f"Available: {free:.0f} MB\n\n"
                "Please free up disk space and try again.",
                "Insufficient Disk Space",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._enter_download_state(mi.id, "whisper", mi.name)
        self._expected_bytes = mi.disk_size_mb * 1024 * 1024
        self._download_dir = self._mm.get_download_dir(mi.id)
        self._start_progress_timer()

        def _do_download() -> None:
            try:
                self._mm.download_model(mi.id)
                safe_call_after(self._download_complete, mi.id, mi.name, True, "")
            except Exception as exc:
                safe_call_after(self._download_complete, mi.id, mi.name, False, str(exc))

        threading.Thread(target=_do_download, daemon=True).start()

    def _delete_whisper(self, model: UnifiedModelInfo) -> None:
        """Delete a Whisper model.

        Args:
            model: The unified model info for a Whisper model.
        """
        mi = self._get_whisper_info(model.model_id)
        if not mi or not self._mm.is_downloaded(mi.id):
            return

        if (
            accessible_message_box(
                f"Delete {mi.name} ({mi.disk_size_mb} MB)?\n\nYou can re-download it later.",
                "Confirm Delete",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            == wx.YES
        ):
            self._mm.delete_model(mi.id)
            self._populate(select_model_id=mi.id)

    # ------------------------------------------------------------------ #
    # Ollama pull / delete                                                 #
    # ------------------------------------------------------------------ #

    def _pull_ollama_model(self, model_name: str) -> None:
        """Pull an Ollama model in a background thread.

        Args:
            model_name: Model identifier to pull.
        """
        if not self._mm._ollama:
            accessible_message_box(
                "Ollama is not configured.\n\n"
                "Set Ollama mode to 'HTTP' in AI Provider Settings "
                "and make sure Ollama is running.",
                "Ollama Not Available",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        from bits_whisperer.core.ollama_adapter import CancelToken

        self._cancel_token = CancelToken()
        self._enter_download_state(model_name, "ollama", model_name)

        def _do_pull() -> None:
            try:

                def _progress(pct: int) -> None:
                    safe_call_after(self._update_pull_progress, model_name, pct)

                success = self._mm.pull_ollama_model(
                    model_name,
                    progress_callback=lambda mid, pct: _progress(int(pct)),
                    cancel_token=self._cancel_token,
                )
                safe_call_after(
                    self._download_complete,
                    model_name,
                    model_name,
                    success,
                    "" if success else "Pull failed or was cancelled",
                )
            except Exception as exc:
                safe_call_after(self._download_complete, model_name, model_name, False, str(exc))

        threading.Thread(target=_do_pull, daemon=True).start()

    def _update_pull_progress(self, model_name: str, pct: int) -> None:
        """Update the progress UI during an Ollama pull.

        Args:
            model_name: Name of the model being pulled.
            pct: Progress percentage (0-100).
        """
        if not self._downloading:
            return
        clamped = min(pct, 99)
        self._progress.SetValue(clamped)
        self._progress_label.SetLabel(f"Pulling {model_name}\u2026 {clamped}%")

    def _delete_ollama(self, model: UnifiedModelInfo) -> None:
        """Delete an Ollama model.

        Args:
            model: The unified model info for an Ollama model.
        """
        size_str = (
            f"{model.size_gb:.1f} GB" if model.size_gb >= 1.0 else f"{int(model.size_gb * 1024)} MB"
        )
        if (
            accessible_message_box(
                f"Delete Ollama model '{model.name}' ({size_str})?\n\n"
                "You can re-pull it later from ollama.com.",
                "Confirm Delete",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            == wx.YES
        ):
            success = self._mm.delete_ollama_model(model.model_id)
            if success:
                announce_to_screen_reader(f"Deleted {model.name}")
            else:
                accessible_message_box(
                    f"Failed to delete '{model.name}'.",
                    "Delete Failed",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
            self._populate()

    # ------------------------------------------------------------------ #
    # Download state helpers                                               #
    # ------------------------------------------------------------------ #

    def _enter_download_state(
        self,
        model_id: str,
        provider: str,
        display_name: str,
    ) -> None:
        """Switch the dialog into downloading mode.

        Args:
            model_id: Identifier of the model being downloaded.
            provider: Provider identifier (``'whisper'`` or ``'ollama'``).
            display_name: Human-readable model name.
        """
        self._downloading = True
        self._download_model_id = model_id
        self._download_provider = provider
        self._dl_btn.Disable()
        self._del_btn.Disable()
        self._close_btn.Disable()
        self._pull_btn.Disable()

        self._progress.SetValue(0)
        self._progress.Show()
        verb = "Pulling" if provider == "ollama" else "Downloading"
        self._progress_label.SetLabel(f"{verb} {display_name}\u2026 0%")
        self._progress_label.Show()
        self._desc_text.SetValue(
            f"{verb} {display_name}\u2026\nThis may take a few minutes for larger models."
        )
        self.Layout()

    def _start_progress_timer(self) -> None:
        """Start the timer that polls Whisper download directory size."""
        self._progress_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_progress_tick, self._progress_timer)
        self._progress_timer.Start(500)

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
            name = self._download_model_id or ""
            self._progress_label.SetLabel(f"Downloading {name}\u2026 {pct}%")
        except Exception:
            pass

    def _download_complete(
        self,
        model_id: str,
        display_name: str,
        success: bool,
        error: str,
    ) -> None:
        """Handle download/pull completion on the UI thread.

        Args:
            model_id: Model identifier.
            display_name: Human-readable model name.
            success: Whether the operation succeeded.
            error: Error message (empty on success).
        """
        # Stop progress timer
        if self._progress_timer:
            self._progress_timer.Stop()
            self._progress_timer = None

        self._downloading = False
        self._download_model_id = None
        self._download_provider = ""
        self._cancel_token = None

        self._progress.SetValue(100 if success else 0)
        self._progress.Hide()
        self._progress_label.Hide()
        self._close_btn.Enable()
        self._pull_btn.Enable()

        self._populate(select_model_id=model_id)

        if success:
            self._desc_text.SetValue(f"\u2713 {display_name} downloaded successfully!")
            logger.info("Model '%s' downloaded successfully.", model_id)
            announce_to_screen_reader(f"{display_name} downloaded successfully")
        else:
            accessible_message_box(
                f"Failed to download {display_name}:\n{error}",
                "Download Failed",
                wx.OK | wx.ICON_ERROR,
                self,
            )
