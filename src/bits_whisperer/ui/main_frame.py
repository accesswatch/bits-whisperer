"""Main application frame with menu bar, splitter panels, and status bar."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import wx
import wx.adv

from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    announce_status,
    safe_call_after,
    set_accessible_name,
)
from bits_whisperer.utils.constants import (
    APP_NAME,
    APP_VERSION,
    AUDIO_WILDCARD,
    DATA_DIR,
    SUPPORTED_AUDIO_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Menu / command IDs
# -----------------------------------------------------------------------
ID_ADD_FILES = wx.NewIdRef()
ID_ADD_FOLDER = wx.NewIdRef()
ID_START = wx.NewIdRef()
ID_PAUSE = wx.NewIdRef()
ID_CANCEL = wx.NewIdRef()
ID_CLEAR_QUEUE = wx.NewIdRef()
ID_EXPORT = wx.NewIdRef()
ID_SETTINGS = wx.NewIdRef()
ID_MODELS = wx.NewIdRef()
ID_ABOUT = wx.NewIdRef()
ID_HARDWARE = wx.NewIdRef()
ID_CHECK_UPDATES = wx.NewIdRef()
ID_ADVANCED_MODE = wx.NewIdRef()
ID_MINIMIZE_TRAY = wx.NewIdRef()
ID_AUTO_EXPORT = wx.NewIdRef()
ID_VIEW_LOG = wx.NewIdRef()
ID_RECENT_CLEAR = wx.NewIdRef()
ID_SETUP_WIZARD = wx.NewIdRef()
ID_LEARN_MORE = wx.NewIdRef()
ID_ADD_PROVIDER = wx.NewIdRef()

# Maximum recent-file entries
_MAX_RECENT = 10
_RECENT_FILE = DATA_DIR / "recent_files.json"


class MainFrame(wx.Frame):
    """Primary application window for BITS Whisperer.

    Layout
    ------
    Top:    Menu Bar (File, Queue, Tools, Help)
    Left:   Queue Panel (file list)
    Right:  Transcript Panel (viewer / editor)
    Bottom: Status Bar (status, progress, hardware info)
    """

    def __init__(self, parent: wx.Window | None) -> None:
        """Initialise the main frame, services, and UI."""
        super().__init__(
            parent,
            title=f"{APP_NAME} — v{APP_VERSION}",
            size=(1100, 700),
            style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL,
        )
        set_accessible_name(self, APP_NAME)
        self.SetMinSize((800, 500))
        self.Centre()

        # ---- Services (lazy-imported to keep startup lean) ----
        from bits_whisperer.core.device_probe import DeviceProbe
        from bits_whisperer.core.model_manager import ModelManager
        from bits_whisperer.core.provider_manager import ProviderManager
        from bits_whisperer.core.transcoder import Transcoder
        from bits_whisperer.core.transcription_service import TranscriptionService
        from bits_whisperer.storage.database import Database
        from bits_whisperer.storage.key_store import KeyStore

        self.database = Database()
        self.key_store = KeyStore()
        self.device_probe = DeviceProbe()
        self.device_profile = self.device_probe.probe()
        self.model_manager = ModelManager()
        self.provider_manager = ProviderManager()

        self.transcription_service = TranscriptionService(
            provider_manager=self.provider_manager,
            transcoder=Transcoder(),
            key_store=self.key_store,
        )
        self.transcription_service.set_job_update_callback(self._on_job_update)
        self.transcription_service.set_batch_complete_callback(self._on_batch_complete)

        # ---- Persistent settings ----
        self.app_settings: AppSettings = AppSettings.load()

        # ---- State flags (synced from settings) ----
        self._advanced_mode = self.app_settings.general.experience_mode == "advanced"
        self._minimize_to_tray = self.app_settings.general.minimize_to_tray
        self._auto_export = self.app_settings.general.auto_export
        self._force_quit = False
        self._recent_files: list[str] = self._load_recent_files()

        # ---- Build UI ----
        self._build_menu_bar()
        self._build_accelerators()
        self._build_status_bar()
        self._build_panels()

        # ---- System tray ----
        from bits_whisperer.ui.tray_icon import TrayIcon

        self._tray_icon = TrayIcon(self)
        self.Bind(wx.EVT_ICONIZE, self._on_iconize)

        # ---- Event bindings ----
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # ---- Initial status ----
        hw = self.device_profile
        gpu_label = hw.gpu_name if hw.gpu_name else "No GPU"
        announce_status(
            self,
            f"Ready — {hw.cpu_cores_logical} cores, {hw.ram_gb:.0f} GB RAM, {gpu_label}",
        )
        logger.info("Main frame initialised")

        # ---- Deferred startup update check ----
        self._startup_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_startup_timer, self._startup_timer)
        self._startup_timer.StartOnce(3000)  # Check 3 seconds after startup

    # =================================================================== #
    # Menu bar                                                              #
    # =================================================================== #

    def _build_menu_bar(self) -> None:
        menu_bar = wx.MenuBar()

        # -- File --
        file_menu = wx.Menu()
        file_menu.Append(ID_ADD_FILES, "&Add Files…\tCtrl+O", "Add audio files to the queue")
        file_menu.Append(
            ID_ADD_FOLDER,
            "Add &Folder…\tCtrl+Shift+O",
            "Add all audio files in a folder",
        )
        file_menu.AppendSeparator()

        # Recent files submenu
        self._recent_menu = wx.Menu()
        self._rebuild_recent_menu()
        file_menu.AppendSubMenu(self._recent_menu, "&Recent Files")
        file_menu.AppendSeparator()

        file_menu.Append(ID_EXPORT, "&Export Transcript…\tCtrl+E", "Export the selected transcript")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4", "Close the application")

        # -- Queue --
        queue_menu = wx.Menu()
        queue_menu.Append(ID_START, "&Start Transcription\tF5", "Begin processing the queue")
        queue_menu.Append(ID_PAUSE, "&Pause\tF6", "Pause the queue")
        queue_menu.Append(ID_CANCEL, "&Cancel Selected\tDel", "Cancel the selected job")
        queue_menu.AppendSeparator()
        queue_menu.Append(
            ID_CLEAR_QUEUE,
            "C&lear Queue\tCtrl+Shift+Del",
            "Remove all jobs from the queue",
        )

        # -- Tools --
        tools_menu = wx.Menu()
        tools_menu.Append(ID_SETTINGS, "&Settings…\tCtrl+,", "Open application settings")
        tools_menu.Append(ID_MODELS, "&Manage Models…\tCtrl+M", "Download or remove Whisper models")
        tools_menu.Append(ID_HARDWARE, "&Hardware Info…", "View your computer's capabilities")
        tools_menu.AppendSeparator()
        tools_menu.Append(
            ID_ADD_PROVIDER,
            "Add &Provider…",
            "Add and validate a cloud transcription provider",
        )

        # -- View --
        view_menu = wx.Menu()
        self._advanced_mode_item = view_menu.AppendCheckItem(
            ID_ADVANCED_MODE,
            "&Advanced Mode\tCtrl+Shift+A",
            "Toggle advanced controls and settings",
        )
        self._advanced_mode_item.Check(self._advanced_mode)
        view_menu.AppendSeparator()
        self._minimize_tray_item = view_menu.AppendCheckItem(
            ID_MINIMIZE_TRAY,
            "&Minimize to System Tray",
            "When checked, closing the window minimizes to the system tray instead of quitting",
        )
        self._minimize_tray_item.Check(self._minimize_to_tray)
        self._auto_export_item = view_menu.AppendCheckItem(
            ID_AUTO_EXPORT,
            "Auto-&Export on Completion",
            "Automatically export each transcript when it finishes",
        )
        self._auto_export_item.Check(self._auto_export)

        # -- Tools additions --
        tools_menu.AppendSeparator()
        tools_menu.Append(ID_VIEW_LOG, "View &Log…", "Open the application log file")

        # -- Help --
        help_menu = wx.Menu()
        help_menu.Append(
            ID_SETUP_WIZARD,
            "Setup &Wizard…",
            "Run the first-time setup wizard again",
        )
        help_menu.Append(
            ID_LEARN_MORE,
            "&Learn more about BITS",
            "Open the BITS website in your browser",
        )
        help_menu.AppendSeparator()
        help_menu.Append(
            ID_CHECK_UPDATES,
            "Check for &Updates…",
            "Check GitHub for a newer version",
        )
        help_menu.AppendSeparator()
        help_menu.Append(ID_ABOUT, "&About…\tF1", f"About {APP_NAME}")

        menu_bar.Append(file_menu, "&File")
        menu_bar.Append(queue_menu, "&Queue")
        menu_bar.Append(view_menu, "&View")
        menu_bar.Append(tools_menu, "&Tools")
        menu_bar.Append(help_menu, "&Help")
        self.SetMenuBar(menu_bar)

        # -- Bind menu events --
        self.Bind(wx.EVT_MENU, self._on_add_files, id=ID_ADD_FILES)
        self.Bind(wx.EVT_MENU, self._on_add_folder, id=ID_ADD_FOLDER)
        self.Bind(wx.EVT_MENU, self._on_export, id=ID_EXPORT)
        self.Bind(wx.EVT_MENU, self._on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_start, id=ID_START)
        self.Bind(wx.EVT_MENU, self._on_pause, id=ID_PAUSE)
        self.Bind(wx.EVT_MENU, self._on_cancel, id=ID_CANCEL)
        self.Bind(wx.EVT_MENU, self._on_clear_queue, id=ID_CLEAR_QUEUE)
        self.Bind(wx.EVT_MENU, self._on_settings, id=ID_SETTINGS)
        self.Bind(wx.EVT_MENU, self._on_models, id=ID_MODELS)
        self.Bind(wx.EVT_MENU, self._on_hardware_info, id=ID_HARDWARE)
        self.Bind(wx.EVT_MENU, self._on_check_updates, id=ID_CHECK_UPDATES)
        self.Bind(wx.EVT_MENU, self._on_about, id=ID_ABOUT)
        self.Bind(wx.EVT_MENU, self._on_setup_wizard, id=ID_SETUP_WIZARD)
        self.Bind(wx.EVT_MENU, self._on_learn_more, id=ID_LEARN_MORE)
        self.Bind(wx.EVT_MENU, self._on_toggle_advanced, id=ID_ADVANCED_MODE)
        self.Bind(wx.EVT_MENU, self._on_toggle_minimize_tray, id=ID_MINIMIZE_TRAY)
        self.Bind(wx.EVT_MENU, self._on_toggle_auto_export, id=ID_AUTO_EXPORT)
        self.Bind(wx.EVT_MENU, self._on_view_log, id=ID_VIEW_LOG)
        self.Bind(wx.EVT_MENU, self._on_add_provider, id=ID_ADD_PROVIDER)

    def _build_accelerators(self) -> None:
        accel = wx.AcceleratorTable(
            [
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("O"), ID_ADD_FILES),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("O"), ID_ADD_FOLDER),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("E"), ID_EXPORT),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F5, ID_START),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F6, ID_PAUSE),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CANCEL),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord(","), ID_SETTINGS),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("M"), ID_MODELS),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F1, ID_ABOUT),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("A"), ID_ADVANCED_MODE),
            ]
        )
        self.SetAcceleratorTable(accel)

    # =================================================================== #
    # Status bar                                                            #
    # =================================================================== #

    def _build_status_bar(self) -> None:
        sb = self.CreateStatusBar(3)
        sb.SetStatusWidths([-3, -1, -1])
        set_accessible_name(sb, "Status bar")

        # Progress gauge in the second field
        self._progress_gauge = wx.Gauge(sb, range=100, style=wx.GA_HORIZONTAL)
        self._progress_gauge.SetValue(0)
        set_accessible_name(self._progress_gauge, "Overall progress")

        self.Bind(wx.EVT_SIZE, self._on_resize_statusbar)

    def _on_resize_statusbar(self, event: wx.SizeEvent) -> None:
        event.Skip()
        sb = self.GetStatusBar()
        if sb:
            rect = sb.GetFieldRect(1)
            self._progress_gauge.SetPosition((rect.x + 2, rect.y + 2))
            self._progress_gauge.SetSize((rect.width - 4, rect.height - 4))

    # =================================================================== #
    # Panels                                                                #
    # =================================================================== #

    def _build_panels(self) -> None:
        from bits_whisperer.ui.queue_panel import QueuePanel
        from bits_whisperer.ui.transcript_panel import TranscriptPanel

        self._splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        set_accessible_name(self._splitter, "Main workspace")

        self.queue_panel = QueuePanel(self._splitter, main_frame=self)
        self.transcript_panel = TranscriptPanel(self._splitter, main_frame=self)

        self._splitter.SplitVertically(self.queue_panel, self.transcript_panel, sashPosition=360)
        self._splitter.SetMinimumPaneSize(250)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

    # =================================================================== #
    # Menu event handlers                                                   #
    # =================================================================== #

    def _on_add_files(self, _event: wx.CommandEvent) -> None:
        dlg = wx.FileDialog(
            self,
            message="Choose audio files",
            wildcard=AUDIO_WILDCARD,
            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
            self._enqueue_files(paths)
        dlg.Destroy()

    def _on_add_folder(self, _event: wx.CommandEvent) -> None:
        dlg = wx.DirDialog(
            self,
            message="Choose a folder containing audio files",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            folder = Path(dlg.GetPath())
            files = [
                str(f)
                for f in sorted(folder.rglob("*"))
                if f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            ]
            if files:
                self._enqueue_files(files)
            else:
                wx.MessageBox(
                    f"No audio files found in:\n{folder}",
                    "No Audio Files",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
        dlg.Destroy()

    def _enqueue_files(self, paths: list[str]) -> None:
        """Add file paths to the queue panel."""
        self.queue_panel.add_files(paths)
        self._add_to_recent(paths)
        count = len(paths)
        announce_status(self, f"Added {count} file{'s' if count != 1 else ''} to queue")

    def _on_start(self, _event: wx.CommandEvent) -> None:
        from bits_whisperer.core.sdk_installer import ensure_sdk

        jobs = self.queue_panel.get_pending_jobs()
        if not jobs:
            announce_status(self, "No pending jobs to process")
            return

        # Ensure SDKs are available for all providers used in this batch.
        # Deduplicate so we only prompt once per provider.
        providers_needed = dict.fromkeys(j.provider for j in jobs)
        for provider_key in providers_needed:
            if not ensure_sdk(provider_key, parent_window=self):
                announce_status(
                    self,
                    f"Transcription cancelled — {provider_key} SDK not installed",
                )
                return

        # Refresh provider availability in case an SDK was just installed
        self.provider_manager.refresh_availability()

        self.transcription_service.add_jobs(jobs)
        self.transcription_service.start()
        announce_status(self, f"Started transcription — {len(jobs)} job(s)")

    def _on_pause(self, _event: wx.CommandEvent) -> None:
        if self.transcription_service.is_paused:
            self.transcription_service.resume()
            announce_status(self, "Resumed transcription")
        else:
            self.transcription_service.pause()
            announce_status(self, "Paused transcription")

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        job_id = self.queue_panel.get_selected_job_id()
        if job_id:
            self.transcription_service.cancel_job(job_id)
            self.queue_panel.update_job_status(job_id, "Cancelled")
            announce_status(self, "Job cancelled")

    def _on_clear_queue(self, _event: wx.CommandEvent) -> None:
        self.queue_panel.clear_all()
        announce_status(self, "Queue cleared")

    def _on_export(self, _event: wx.CommandEvent) -> None:

        self.transcript_panel.export_transcript()

    def _on_settings(self, _event: wx.CommandEvent) -> None:
        from bits_whisperer.ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_models(self, _event: wx.CommandEvent) -> None:
        from bits_whisperer.ui.model_manager_dialog import ModelManagerDialog

        dlg = ModelManagerDialog(
            self,
            model_manager=self.model_manager,
            device_profile=self.device_profile,
        )
        dlg.ShowModal()
        dlg.Destroy()

    def _on_hardware_info(self, _event: wx.CommandEvent) -> None:
        hp = self.device_profile
        gpu_text = (
            f"GPU: {hp.gpu_name} ({hp.gpu_vram_gb:.1f} GB VRAM)"
            if hp.gpu_name
            else "GPU: None detected"
        )
        cuda_text = f"CUDA: {'Available' if hp.has_cuda else 'Not available'}"
        msg = (
            f"CPU cores: {hp.cpu_cores_logical}\n"
            f"RAM: {hp.ram_gb:.1f} GB\n"
            f"{gpu_text}\n"
            f"{cuda_text}\n\n"
            f"Eligible models: {len(hp.eligible_models)}\n"
            f"Models needing caution: {len(hp.warned_models)}\n"
            f"Models too demanding: {len(hp.ineligible_models)}"
        )
        wx.MessageBox(msg, "Hardware Information", wx.OK | wx.ICON_INFORMATION, self)

    def _on_check_updates(self, _event: wx.CommandEvent) -> None:
        """Check GitHub for a newer version in a background thread."""
        from bits_whisperer.core.updater import Updater
        from bits_whisperer.utils.constants import (
            APP_VERSION,
            GITHUB_REPO_NAME,
            GITHUB_REPO_OWNER,
        )

        announce_status(self, "Checking for updates…")

        import threading

        def _check() -> None:
            updater = Updater(
                repo_owner=GITHUB_REPO_OWNER,
                repo_name=GITHUB_REPO_NAME,
                current_version=APP_VERSION,
            )
            info = updater.check_for_update()

            def _show_result() -> None:
                if info:
                    msg = (
                        f"A new version is available!\n\n"
                        f"Current: v{info.current_version}\n"
                        f"Latest:  v{info.latest_version}\n\n"
                        f"{info.release_name}\n\n"
                        f"Would you like to open the download page?"
                    )
                    dlg = wx.MessageDialog(
                        self,
                        msg,
                        "Update Available",
                        wx.YES_NO | wx.ICON_INFORMATION,
                    )
                    if dlg.ShowModal() == wx.ID_YES:
                        updater.open_release_page(info)
                    dlg.Destroy()
                    announce_status(self, f"Update available: v{info.latest_version}")
                else:
                    wx.MessageBox(
                        f"You are running the latest version (v{APP_VERSION}).",
                        "No Updates",
                        wx.OK | wx.ICON_INFORMATION,
                        self,
                    )
                    announce_status(self, "No updates available")

            safe_call_after(_show_result)

        threading.Thread(target=_check, daemon=True).start()

    def _on_startup_timer(self, _event: wx.TimerEvent) -> None:
        """Silent startup update check — runs once after a short delay."""
        import threading

        from bits_whisperer.core.updater import Updater
        from bits_whisperer.utils.constants import (
            APP_VERSION,
            GITHUB_REPO_NAME,
            GITHUB_REPO_OWNER,
        )

        def _check() -> None:
            try:
                updater = Updater(
                    repo_owner=GITHUB_REPO_OWNER,
                    repo_name=GITHUB_REPO_NAME,
                    current_version=APP_VERSION,
                )
                info = updater.check_for_update()
                if info:

                    def _notify() -> None:
                        announce_status(
                            self,
                            f"Update available: v{info.latest_version} "
                            f"(Help, then Check for Updates)",
                        )

                    safe_call_after(_notify)
            except Exception:
                logger.debug("Startup update check failed (non-critical)")

        threading.Thread(target=_check, daemon=True, name="startup-update").start()

    def _on_add_provider(self, _event: wx.CommandEvent) -> None:
        """Open the Add Provider dialog for cloud provider onboarding."""
        from bits_whisperer.ui.add_provider_dialog import AddProviderDialog

        dlg = AddProviderDialog(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            # Reload settings to pick up newly activated provider
            self.app_settings = AppSettings.load()
            announce_status(
                self,
                "Provider activated — ready for transcription",
            )
        dlg.Destroy()

    def _on_toggle_advanced(self, _event: wx.CommandEvent) -> None:
        """Toggle advanced mode on/off and persist the choice."""
        self._advanced_mode = self._advanced_mode_item.IsChecked()
        mode_label = "Advanced" if self._advanced_mode else "Basic"
        # Persist to settings
        self.app_settings.general.experience_mode = "advanced" if self._advanced_mode else "basic"
        self.app_settings.save()
        announce_status(self, f"Switched to {mode_label} mode")
        logger.info("Experience mode: %s", self.app_settings.general.experience_mode)

    @property
    def is_advanced_mode(self) -> bool:
        """Whether the application is in advanced mode."""
        return self._advanced_mode

    def _on_toggle_minimize_tray(self, _event: wx.CommandEvent) -> None:
        """Toggle 'minimize to system tray' setting."""
        self._minimize_to_tray = self._minimize_tray_item.IsChecked()
        label = "enabled" if self._minimize_to_tray else "disabled"
        announce_status(self, f"Minimize to tray {label}")

    def _on_toggle_auto_export(self, _event: wx.CommandEvent) -> None:
        """Toggle auto-export on completion."""
        self._auto_export = self._auto_export_item.IsChecked()
        label = "enabled" if self._auto_export else "disabled"
        announce_status(self, f"Auto-export {label}")

    def _on_view_log(self, _event: wx.CommandEvent) -> None:
        """Open the application log file in the default text viewer."""
        from bits_whisperer.utils.constants import LOG_PATH
        from bits_whisperer.utils.platform_utils import open_file_or_folder

        if LOG_PATH.exists():
            open_file_or_folder(LOG_PATH)
        else:
            wx.MessageBox(
                "No log file found yet.",
                "View Log",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_iconize(self, event: wx.IconizeEvent) -> None:
        """Handle window minimize — optionally hide to tray."""
        if event.IsIconized() and self._minimize_to_tray:
            self.Show(False)
            self._tray_icon.update_progress(0, 0, 0)
        event.Skip()

    def _on_setup_wizard(self, _event: wx.CommandEvent) -> None:
        """Re-run the first-time setup wizard."""
        from bits_whisperer.ui.setup_wizard import SetupWizard

        dlg = SetupWizard(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            # Reload settings that the wizard may have changed
            self.app_settings = AppSettings.load()
            # Sync advanced mode toggle with experience_mode from wizard
            self._advanced_mode = self.app_settings.general.experience_mode == "advanced"
            self._advanced_mode_item.Check(self._advanced_mode)
            mode_label = "Advanced" if self._advanced_mode else "Basic"
            announce_status(self, f"Setup complete — {mode_label} mode")
        dlg.Destroy()

    def _on_learn_more(self, _event: wx.CommandEvent) -> None:
        """Open the BITS website in the default browser."""
        import webbrowser

        webbrowser.open("https://www.joinbits.org")

    def _on_about(self, _event: wx.CommandEvent) -> None:
        info = wx.adv.AboutDialogInfo()
        info.SetName(APP_NAME)
        info.SetVersion(APP_VERSION)
        info.SetDescription(
            "A consumer-grade audio transcription application.\n\n"
            "Supports 17 cloud and on-device transcription providers, "
            "14 Whisper AI models, and 7 export formats.\n"
            "Accessible, privacy-first, and easy to use."
        )
        info.SetCopyright(
            "(C) 2025 Blind Information Technology Solutions (BITS)\n" "All rights reserved."
        )
        info.AddDeveloper("Blind Information Technology Solutions (BITS)")
        info.SetWebSite("https://github.com/BITSWhisperer/bits-whisperer")
        info.SetLicence(
            "MIT License\n\n"
            "Permission is hereby granted, free of charge, to any person "
            "obtaining a copy of this software and associated documentation "
            "files, to deal in the Software without restriction.\n\n"
            "Open-Source Attributions\n"
            "========================\n\n"
            "This application is built with the following open-source "
            "libraries:\n\n"
            "  \u2022  wxPython — Cross-platform GUI toolkit (wxWindows Library Licence)\n"
            "  \u2022  faster-whisper — CTranslate2 Whisper inference (MIT)\n"
            "  \u2022  OpenAI Whisper — Speech recognition model (MIT)\n"
            "  \u2022  ffmpeg — Audio/video processing (LGPL 2.1+)\n"
            "  \u2022  keyring — Secure credential storage (MIT)\n"
            "  \u2022  psutil — System information (BSD)\n"
            "  \u2022  httpx — HTTP client (BSD)\n"
            "  \u2022  platformdirs — Platform directories (MIT)\n"
            "  \u2022  python-docx — Word document export (MIT)\n"
            "  \u2022  Jinja2 — Template engine for HTML export (BSD)\n"
            "  \u2022  Markdown — Markdown processing (BSD)\n"
            "  \u2022  pydub — Audio manipulation (MIT)\n"
            "  \u2022  boto3 — AWS SDK for Python (Apache 2.0)\n"
            "  \u2022  google-cloud-speech — Google Speech-to-Text (Apache 2.0)\n"
            "  \u2022  google-genai — Google Gemini AI (Apache 2.0)\n"
            "  \u2022  azure-cognitiveservices-speech — Azure Speech SDK (MIT)\n"
            "  \u2022  deepgram-sdk — Deepgram speech recognition (MIT)\n"
            "  \u2022  assemblyai — AssemblyAI SDK (MIT)\n"
            "  \u2022  groq — Groq LPU inference (Apache 2.0)\n"
            "  \u2022  rev-ai — Rev.ai speech recognition (MIT)\n"
            "  \u2022  speechmatics-python — Speechmatics SDK (MIT)\n"
            "  \u2022  packaging — Version parsing (Apache 2.0)\n\n"
            "We gratefully acknowledge all open-source contributors "
            "whose work makes this application possible."
        )
        wx.adv.AboutBox(info, self)

    def _on_exit(self, _event: wx.CommandEvent) -> None:
        self.Close()

    # =================================================================== #
    # Callbacks from transcription service (called from worker threads)     #
    # =================================================================== #

    def _on_job_update(self, job) -> None:
        """Called by the transcription service when a job's state changes."""
        safe_call_after(self._handle_job_update, job)

    def _on_batch_complete(self, jobs) -> None:
        """Called when all queued jobs have finished."""
        safe_call_after(self._handle_batch_complete)

    def _handle_job_update(self, job) -> None:
        self.queue_panel.update_job(job)
        self._progress_gauge.SetValue(int(job.progress_percent))
        announce_status(self, f"{job.display_name}: {job.status_text}")

        # Update tray icon progress
        summary = self.transcription_service.get_progress_summary()
        self._tray_icon.update_progress(
            completed=summary["completed"],
            total=summary["total"],
            active=summary["active"],
            current_file=job.display_name,
        )

        if job.result and job.status.value == "completed":
            self.transcript_panel.show_transcript(job)

            # Tray notification (especially useful when minimized)
            if not self.IsShown():
                self._tray_icon.notify_job_complete(job.display_name)

            # Auto-export
            if self._auto_export:
                self._auto_export_transcript(job)

        elif job.status.value == "failed" and not self.IsShown():
            self._tray_icon.notify_error(
                job.display_name,
                job.error_message or "Unknown error",
            )

    def _handle_batch_complete(self) -> None:
        self._progress_gauge.SetValue(100)
        announce_status(self, "All transcription jobs complete!")
        self._tray_icon.set_idle()

        summary = self.transcription_service.get_progress_summary()
        self._tray_icon.notify_batch_complete(
            total=summary["total"],
            failed=summary["failed"],
        )

        # Play notification sound
        if self.app_settings.general.play_sound:
            wx.Bell()

        # Restore window if hidden
        if not self.IsShown():
            self._tray_icon.show_main_window()

    def _auto_export_transcript(self, job) -> None:
        """Auto-export completed transcript to default format alongside audio file.

        Args:
            job: Completed job with result.
        """
        if not job.result:
            return
        try:
            from bits_whisperer.export.plain_text import PlainTextFormatter

            audio_dir = Path(job.file_path).parent
            stem = Path(job.file_path).stem
            out_path = audio_dir / f"{stem}.txt"

            # Avoid overwriting — append number
            counter = 1
            while out_path.exists():
                out_path = audio_dir / f"{stem}_{counter}.txt"
                counter += 1

            PlainTextFormatter().export(job.result, out_path)
            logger.info("Auto-exported: %s", out_path)
        except Exception as exc:
            logger.warning("Auto-export failed for %s: %s", job.display_name, exc)

    # =================================================================== #
    # Window close                                                          #
    # =================================================================== #

    def _on_close(self, event: wx.CloseEvent) -> None:
        # If minimize-to-tray is enabled and this isn't a forced quit,
        # hide to tray instead of actually closing.
        force = getattr(self, "_force_quit", False)
        if self._minimize_to_tray and not force and event.CanVeto():
            self.Show(False)
            event.Veto()
            return

        self.transcription_service.stop()
        if hasattr(self, "_tray_icon"):
            self._tray_icon.cleanup()
        self.Destroy()

    # =================================================================== #
    # Recent files                                                          #
    # =================================================================== #

    def _load_recent_files(self) -> list[str]:
        """Load recent file paths from disk."""
        try:
            if _RECENT_FILE.exists():
                return json.loads(_RECENT_FILE.read_text("utf-8"))[:_MAX_RECENT]
        except Exception:
            pass
        return []

    def _save_recent_files(self) -> None:
        """Persist recent file list to disk."""
        with contextlib.suppress(Exception):
            _RECENT_FILE.write_text(
                json.dumps(self._recent_files[:_MAX_RECENT]),
                encoding="utf-8",
            )

    def _add_to_recent(self, paths: list[str]) -> None:
        """Add paths to the recent files list."""
        for p in paths:
            if p in self._recent_files:
                self._recent_files.remove(p)
            self._recent_files.insert(0, p)
        self._recent_files = self._recent_files[:_MAX_RECENT]
        self._save_recent_files()
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        """Rebuild the recent files submenu."""
        # Clear existing items
        for item in list(self._recent_menu.GetMenuItems()):
            self._recent_menu.Delete(item)

        if not self._recent_files:
            empty = self._recent_menu.Append(wx.ID_ANY, "(No recent files)")
            empty.Enable(False)
        else:
            for i, path in enumerate(self._recent_files):
                name = Path(path).name
                item_id = wx.NewIdRef()
                self._recent_menu.Append(item_id, f"&{i + 1}  {name}")
                self.Bind(
                    wx.EVT_MENU,
                    lambda evt, p=path: self._on_recent_file(p),
                    id=item_id,
                )
            self._recent_menu.AppendSeparator()
            self._recent_menu.Append(ID_RECENT_CLEAR, "&Clear Recent Files")
            self.Bind(wx.EVT_MENU, self._on_clear_recent, id=ID_RECENT_CLEAR)

    def _on_recent_file(self, path: str) -> None:
        """Open a file from the recent files list."""
        if Path(path).exists():
            self._enqueue_files([path])
        else:
            wx.MessageBox(
                f"File not found:\n{path}",
                "File Not Found",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            self._recent_files = [p for p in self._recent_files if p != path]
            self._save_recent_files()
            self._rebuild_recent_menu()

    def _on_clear_recent(self, _event: wx.CommandEvent) -> None:
        """Clear the recent files list."""
        self._recent_files.clear()
        self._save_recent_files()
        self._rebuild_recent_menu()
        announce_status(self, "Recent files cleared")
