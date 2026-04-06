"""Watch folder configuration dialog.

Provides a settings dialog for configuring the watch folder path,
polling interval, provider/model defaults, and behaviour options.

Accessibility
-------------
* Every control has ``SetName()`` and ``SetHelpText()``.
* Keyboard-navigable with Tab/Shift-Tab.
* Browse button for folder selection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.settings import AppSettings
from bits_whisperer.core.watch_folder import WatchFolderService
from bits_whisperer.utils.accessibility import (
    announce_status,
    label_control,
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


class WatchFolderDialog(wx.Dialog):
    """Dialog for configuring watch folder settings."""

    def __init__(self, parent: MainFrame, *, main_frame: MainFrame) -> None:
        """Initialise the watch folder settings dialog."""
        super().__init__(
            parent,
            title="Watch Folder Settings — BITS Whisperer",
            size=(580, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, "Watch folder settings dialog")
        self.SetMinSize((480, 420))
        self._main_frame = main_frame
        self._settings: AppSettings = getattr(
            main_frame,
            "app_settings",
            AppSettings.load(),
        )

        self._build_ui()
        self.CentreOnParent()
        wx.CallAfter(self._path_txt.SetFocus)

    # ================================================================== #
    # UI construction                                                      #
    # ================================================================== #

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        panel = wx.Panel(self)
        make_panel_accessible(panel)
        wf = self._settings.watch_folder

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Introduction ---
        intro = wx.StaticText(
            panel,
            label=(
                "Configure a folder to monitor for new audio files. "
                "Files placed in this folder will be automatically "
                "queued for transcription using your chosen settings."
            ),
        )
        intro.Wrap(520)
        set_accessible_name(intro, "Watch folder introduction")
        outer.Add(intro, 0, wx.ALL, 10)

        # --- Folder path ---
        folder_box = wx.StaticBox(panel, label="Watch Folder Location")
        set_accessible_name(folder_box, "Watch folder location")
        fs = wx.StaticBoxSizer(folder_box, wx.VERTICAL)

        path_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_path = wx.StaticText(panel, label="&Folder path:")
        self._path_txt = wx.TextCtrl(panel, value=wf.folder_path)
        label_control(lbl_path, self._path_txt)
        set_accessible_help(
            self._path_txt,
            "Path to the folder that will be monitored for new audio files",
        )

        btn_browse = wx.Button(panel, label="&Browse\u2026")
        set_accessible_name(btn_browse, "Browse for watch folder")
        set_accessible_help(
            btn_browse,
            "Choose the folder to monitor for new audio files",
        )
        btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)

        path_row.Add(lbl_path, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        path_row.Add(self._path_txt, 1, wx.EXPAND | wx.RIGHT, 6)
        path_row.Add(btn_browse, 0)
        fs.Add(path_row, 0, wx.ALL | wx.EXPAND, 6)

        self._cb_subfolders = wx.CheckBox(
            panel,
            label="Include &subfolders",
        )
        self._cb_subfolders.SetValue(wf.include_subfolders)
        set_accessible_name(self._cb_subfolders, "Include subfolders")
        set_accessible_help(
            self._cb_subfolders,
            "Also monitor subdirectories within the watch folder",
        )
        fs.Add(self._cb_subfolders, 0, wx.LEFT | wx.BOTTOM, 6)

        outer.Add(fs, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        # --- Transcription defaults ---
        trans_box = wx.StaticBox(panel, label="Transcription Defaults")
        set_accessible_name(trans_box, "Transcription defaults for watch folder")
        ts = wx.StaticBoxSizer(trans_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        # Provider
        lbl_prov = wx.StaticText(panel, label="&Provider:")
        providers = ["(Use app default)", "local_whisper", "vosk", "parakeet"]
        self._provider_ch = wx.Choice(panel, choices=providers)
        if wf.provider and wf.provider in providers:
            self._provider_ch.SetStringSelection(wf.provider)
        else:
            self._provider_ch.SetSelection(0)
        label_control(lbl_prov, self._provider_ch)
        set_accessible_help(
            self._provider_ch,
            "Select the transcription provider to use for watch folder jobs",
        )
        grid.Add(lbl_prov, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._provider_ch, 0, wx.EXPAND)

        # Model
        lbl_model = wx.StaticText(panel, label="&Model:")
        models = [
            "(Use app default)",
            "tiny",
            "base",
            "small",
            "medium",
            "large-v3",
            "large-v3-turbo",
        ]
        self._model_ch = wx.Choice(panel, choices=models)
        if wf.model and wf.model in models:
            self._model_ch.SetStringSelection(wf.model)
        else:
            self._model_ch.SetSelection(0)
        label_control(lbl_model, self._model_ch)
        set_accessible_help(
            self._model_ch,
            "Select the Whisper model to use for watch folder transcription",
        )
        grid.Add(lbl_model, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._model_ch, 0, wx.EXPAND)

        # Language
        lbl_lang = wx.StaticText(panel, label="&Language:")
        languages = ["(Use app default)", "auto", "en", "es", "fr", "de", "it", "pt", "zh", "ja"]
        self._lang_ch = wx.Choice(panel, choices=languages)
        if wf.language and wf.language in languages:
            self._lang_ch.SetStringSelection(wf.language)
        else:
            self._lang_ch.SetSelection(0)
        label_control(lbl_lang, self._lang_ch)
        set_accessible_help(
            self._lang_ch,
            "Language for watch folder transcription jobs",
        )
        grid.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._lang_ch, 0, wx.EXPAND)

        ts.Add(grid, 0, wx.ALL | wx.EXPAND, 6)
        outer.Add(ts, 0, wx.ALL | wx.EXPAND, 10)

        # --- Behaviour ---
        beh_box = wx.StaticBox(panel, label="Behaviour")
        set_accessible_name(beh_box, "Watch folder behaviour settings")
        bs = wx.StaticBoxSizer(beh_box, wx.VERTICAL)

        # Poll interval
        poll_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_poll = wx.StaticText(panel, label="Poll &interval (seconds):")
        self._poll_spin = wx.SpinCtrl(
            panel,
            min=1,
            max=300,
            initial=int(wf.poll_interval_seconds),
        )
        label_control(lbl_poll, self._poll_spin)
        set_accessible_help(
            self._poll_spin,
            "How often the folder is checked for new files (in seconds)",
        )
        poll_row.Add(lbl_poll, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        poll_row.Add(self._poll_spin, 0)
        bs.Add(poll_row, 0, wx.ALL, 6)

        self._cb_auto_export = wx.CheckBox(
            panel,
            label="Auto-&export transcripts on completion",
        )
        self._cb_auto_export.SetValue(wf.auto_export)
        set_accessible_name(
            self._cb_auto_export,
            "Auto-export watch folder transcripts",
        )
        set_accessible_help(
            self._cb_auto_export,
            "Automatically save completed transcripts alongside the audio file",
        )
        bs.Add(self._cb_auto_export, 0, wx.LEFT | wx.BOTTOM, 6)

        self._cb_process_existing = wx.CheckBox(
            panel,
            label="Process e&xisting files when watch starts",
        )
        self._cb_process_existing.SetValue(wf.process_existing)
        set_accessible_name(
            self._cb_process_existing,
            "Process existing files",
        )
        set_accessible_help(
            self._cb_process_existing,
            "Transcribe files already in the folder when monitoring starts. "
            "If unchecked, only new files are processed.",
        )
        bs.Add(self._cb_process_existing, 0, wx.LEFT | wx.BOTTOM, 6)

        self._cb_auto_start = wx.CheckBox(
            panel,
            label="&Start monitoring when app launches",
        )
        self._cb_auto_start.SetValue(wf.auto_start)
        set_accessible_name(self._cb_auto_start, "Auto-start watch folder")
        set_accessible_help(
            self._cb_auto_start,
            "Automatically begin monitoring the watch folder when the app opens",
        )
        bs.Add(self._cb_auto_start, 0, wx.LEFT | wx.BOTTOM, 6)

        outer.Add(bs, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        # --- Buttons ---
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        btn_ok = wx.Button(panel, wx.ID_OK, "&OK")
        set_accessible_name(btn_ok, "OK")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "&Cancel")
        set_accessible_name(btn_cancel, "Cancel")

        btn_sizer.Add(btn_ok, 0, wx.RIGHT, 6)
        btn_sizer.Add(btn_cancel, 0)
        outer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        panel.SetSizer(outer)

        # Bindings
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)
        btn_ok.SetDefault()

    # ================================================================== #
    # Event handlers                                                       #
    # ================================================================== #

    def _on_browse(self, _event: wx.CommandEvent) -> None:
        """Browse for a watch folder directory."""
        current = self._path_txt.GetValue()
        dlg = wx.DirDialog(
            self,
            message="Choose a folder to watch for audio files",
            defaultPath=current if Path(current).is_dir() else "",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            self._path_txt.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save watch folder settings and close."""
        folder_path = self._path_txt.GetValue().strip()

        # Validate folder if a path is provided
        if folder_path:
            is_valid, error = WatchFolderService.validate_folder(folder_path)
            if not is_valid:
                wx.MessageBox(
                    f"Invalid watch folder:\n\n{error}",
                    "Validation Error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return

        # Collect settings
        wf = self._settings.watch_folder
        wf.folder_path = folder_path
        wf.enabled = bool(folder_path)
        wf.include_subfolders = self._cb_subfolders.GetValue()
        wf.poll_interval_seconds = float(self._poll_spin.GetValue())
        wf.auto_export = self._cb_auto_export.GetValue()
        wf.process_existing = self._cb_process_existing.GetValue()
        wf.auto_start = self._cb_auto_start.GetValue()

        # Provider / model / language — empty string means "use app default"
        prov_sel = self._provider_ch.GetStringSelection()
        wf.provider = "" if prov_sel == "(Use app default)" else prov_sel

        model_sel = self._model_ch.GetStringSelection()
        wf.model = "" if model_sel == "(Use app default)" else model_sel

        lang_sel = self._lang_ch.GetStringSelection()
        wf.language = "" if lang_sel == "(Use app default)" else lang_sel

        # Save
        self._settings.save()
        self._main_frame.app_settings = self._settings
        announce_status(self._main_frame, "Watch folder settings saved")

        self.EndModal(wx.ID_OK)

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        """Discard changes and close."""
        self.EndModal(wx.ID_CANCEL)
