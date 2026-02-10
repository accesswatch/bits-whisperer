"""Main application frame with menu bar, splitter panels, and status bar."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import wx
import wx.adv

from bits_whisperer.core.job import JobStatus
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    announce_to_screen_reader,
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
ID_LIVE_TRANSCRIPTION = wx.NewIdRef()
ID_AI_SETTINGS = wx.NewIdRef()
ID_TRANSLATE = wx.NewIdRef()
ID_SUMMARIZE = wx.NewIdRef()
ID_PLUGINS = wx.NewIdRef()
ID_COPILOT_SETUP = wx.NewIdRef()
ID_COPILOT_CHAT = wx.NewIdRef()
ID_AGENT_BUILDER = wx.NewIdRef()
ID_TRANSLATE_MULTI = wx.NewIdRef()
ID_AUDIO_PREVIEW = wx.NewIdRef()
ID_AUDIO_PREVIEW_SELECTED = wx.NewIdRef()

# Queue batch operation IDs
ID_CLEAR_COMPLETED = wx.NewIdRef()
ID_RETRY_FAILED = wx.NewIdRef()
ID_RENAME = wx.NewIdRef()

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
        from bits_whisperer.core.registration_service import BITS_RegistrationService
        from bits_whisperer.core.transcoder import Transcoder
        from bits_whisperer.core.transcription_service import TranscriptionService
        from bits_whisperer.storage.database import Database
        from bits_whisperer.storage.key_store import KeyStore

        self.database = Database()
        self.key_store = KeyStore()
        self.registration_service = BITS_RegistrationService(self.key_store)
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

        # ---- Plugin manager ----
        from bits_whisperer.core.plugin_manager import PluginManager

        # ---- Persistent settings ----
        self.app_settings: AppSettings = AppSettings.load()

        self.plugin_manager = PluginManager(self.app_settings.plugins, self.provider_manager)
        self.plugin_manager.load_all()

        # ---- Copilot service (lazy start) ----
        self._copilot_service = None

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

        # ---- Registration update ----
        self._update_window_title()

        # ---- Initial status ----
        hw = self.device_profile
        gpu_label = hw.gpu_name if hw.gpu_name else "No GPU"
        announce_status(
            self,
            f"Ready — {hw.cpu_cores_logical} cores, {hw.ram_gb:.0f} GB RAM, {gpu_label}",
        )
        logger.info("Main frame initialised")

        # Disable transcript-dependent menu items initially
        self._update_menu_state()

        # ---- Deferred startup update check ----
        self._startup_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_startup_timer, self._startup_timer)
        self._startup_timer.StartOnce(3000)  # Check 3 seconds after startup

    def _update_window_title(self) -> None:
        """Update window title based on version and membership status."""
        status_msg = self.registration_service.get_status_message()
        self.SetTitle(f"{APP_NAME} v{APP_VERSION} — {status_msg}")

    # =================================================================== #
    # Menu bar                                                              #
    # =================================================================== #

    def _build_menu_bar(self) -> None:
        menu_bar = wx.MenuBar()

        # -- File --
        file_menu = wx.Menu()
        file_menu.Append(
            ID_ADD_FILES,
            "Add File to &Transcribe…\tCtrl+O",
            "Choose audio files and configure transcription settings",
        )
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
        queue_menu.Append(ID_PAUSE, "&Pause\tCtrl+P", "Pause the queue")
        queue_menu.Append(ID_CANCEL, "&Cancel Selected\tDel", "Cancel the selected job")
        queue_menu.Append(
            ID_AUDIO_PREVIEW_SELECTED,
            "Audio &Preview Selected…\tCtrl+Alt+P",
            "Preview the selected audio file in the queue",
        )
        queue_menu.AppendSeparator()
        queue_menu.Append(ID_RENAME, "Re&name Selected\tF2", "Rename the selected queue item")
        queue_menu.AppendSeparator()
        queue_menu.Append(
            ID_CLEAR_COMPLETED,
            "Clear C&ompleted",
            "Remove all completed jobs from the queue",
        )
        queue_menu.Append(
            ID_RETRY_FAILED,
            "&Retry All Failed\tCtrl+Shift+R",
            "Re-queue all failed jobs for another attempt",
        )
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
        tools_menu.Append(
            ID_AUDIO_PREVIEW,
            "Audio &Preview…\tCtrl+Shift+P",
            "Listen to an audio file and select a range",
        )
        tools_menu.AppendSeparator()
        tools_menu.Append(
            ID_ADD_PROVIDER,
            "Add &Provider…",
            "Add and validate a cloud transcription provider",
        )
        tools_menu.Append(
            ID_AI_SETTINGS,
            "&AI Provider Settings…",
            "Configure AI providers for translation and summarization",
        )
        tools_menu.Append(
            ID_PLUGINS,
            "P&lugins…",
            "View and manage installed plugins",
        )
        tools_menu.AppendSeparator()
        tools_menu.Append(
            ID_LIVE_TRANSCRIPTION,
            "&Live Transcription…\tCtrl+L",
            "Start real-time microphone transcription",
        )

        # -- AI --
        ai_menu = wx.Menu()
        ai_menu.Append(
            ID_TRANSLATE,
            "&Translate Transcript…\tCtrl+T",
            "Translate the current transcript using AI",
        )
        ai_menu.Append(
            ID_TRANSLATE_MULTI,
            "Translate to &Multiple Languages…",
            "Translate the transcript to all configured target languages",
        )
        ai_menu.AppendSeparator()
        ai_menu.Append(
            ID_SUMMARIZE,
            "&Summarize Transcript…\tCtrl+Shift+S",
            "Summarize the current transcript using AI",
        )
        ai_menu.AppendSeparator()
        self._copilot_chat_item = ai_menu.AppendCheckItem(
            ID_COPILOT_CHAT,
            "&Chat with Transcript…\tCtrl+Shift+C",
            "Toggle the AI chat panel for interactive transcript analysis",
        )
        ai_menu.Append(
            ID_COPILOT_SETUP,
            "Copilot &Setup…",
            "Set up GitHub Copilot CLI and authentication",
        )
        ai_menu.Append(
            ID_AGENT_BUILDER,
            "&Agent Builder…",
            "Design a custom AI agent for transcript analysis",
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
        menu_bar.Append(ai_menu, "&AI")
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
        self.Bind(wx.EVT_MENU, self._on_audio_preview_selected, id=ID_AUDIO_PREVIEW_SELECTED)
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
        self.Bind(wx.EVT_MENU, self._on_live_transcription, id=ID_LIVE_TRANSCRIPTION)
        self.Bind(wx.EVT_MENU, self._on_ai_settings, id=ID_AI_SETTINGS)
        self.Bind(wx.EVT_MENU, self._on_translate, id=ID_TRANSLATE)
        self.Bind(wx.EVT_MENU, self._on_summarize, id=ID_SUMMARIZE)
        self.Bind(wx.EVT_MENU, self._on_plugins, id=ID_PLUGINS)
        self.Bind(wx.EVT_MENU, self._on_audio_preview, id=ID_AUDIO_PREVIEW)
        self.Bind(wx.EVT_MENU, self._on_copilot_setup, id=ID_COPILOT_SETUP)
        self.Bind(wx.EVT_MENU, self._on_copilot_chat, id=ID_COPILOT_CHAT)
        self.Bind(wx.EVT_MENU, self._on_agent_builder, id=ID_AGENT_BUILDER)
        self.Bind(wx.EVT_MENU, self._on_translate_multi, id=ID_TRANSLATE_MULTI)
        self.Bind(wx.EVT_MENU, self._on_clear_completed, id=ID_CLEAR_COMPLETED)
        self.Bind(wx.EVT_MENU, self._on_retry_failed, id=ID_RETRY_FAILED)
        self.Bind(wx.EVT_MENU, self._on_rename_selected, id=ID_RENAME)

    def _build_accelerators(self) -> None:
        # Panel-navigation IDs (not in the menu bar)
        self._id_next_tab = wx.NewIdRef()
        self._id_prev_tab = wx.NewIdRef()
        self._id_next_pane = wx.NewIdRef()
        self._id_prev_pane = wx.NewIdRef()

        accel = wx.AcceleratorTable(
            [
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("O"), ID_ADD_FILES),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("O"), ID_ADD_FOLDER),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("E"), ID_EXPORT),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F5, ID_START),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("P"), ID_PAUSE),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_CANCEL),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord(","), ID_SETTINGS),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("M"), ID_MODELS),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F1, ID_ABOUT),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("A"), ID_ADVANCED_MODE),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("L"), ID_LIVE_TRANSCRIPTION),
                wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("T"), ID_TRANSLATE),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("S"), ID_SUMMARIZE),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("C"), ID_COPILOT_CHAT),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F2, ID_RENAME),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("R"), ID_RETRY_FAILED),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("P"), ID_AUDIO_PREVIEW),
                wx.AcceleratorEntry(
                    wx.ACCEL_CTRL | wx.ACCEL_ALT, ord("P"), ID_AUDIO_PREVIEW_SELECTED
                ),
                # Tab / pane navigation
                wx.AcceleratorEntry(wx.ACCEL_CTRL, wx.WXK_TAB, self._id_next_tab),
                wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_TAB, self._id_prev_tab),
                wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F6, self._id_next_pane),
                wx.AcceleratorEntry(wx.ACCEL_SHIFT, wx.WXK_F6, self._id_prev_pane),
            ]
        )
        self.SetAcceleratorTable(accel)

        # Bind navigation handlers
        self.Bind(wx.EVT_MENU, self._on_next_tab, id=self._id_next_tab)
        self.Bind(wx.EVT_MENU, self._on_prev_tab, id=self._id_prev_tab)
        self.Bind(wx.EVT_MENU, self._on_next_pane, id=self._id_next_pane)
        self.Bind(wx.EVT_MENU, self._on_prev_pane, id=self._id_prev_pane)

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
        from bits_whisperer.ui.copilot_chat_panel import CopilotChatPanel
        from bits_whisperer.ui.queue_panel import QueuePanel
        from bits_whisperer.ui.transcript_panel import TranscriptPanel

        # Main notebook — one tab per workspace area
        self._notebook = wx.Notebook(self, style=wx.NB_TOP)
        set_accessible_name(self._notebook, "Main workspace tabs")

        self.queue_panel = QueuePanel(self._notebook, main_frame=self)
        self.transcript_panel = TranscriptPanel(self._notebook, main_frame=self)
        self.chat_panel = CopilotChatPanel(self._notebook, main_frame=self)

        self._notebook.AddPage(self.queue_panel, "Queue")
        self._notebook.AddPage(self.transcript_panel, "Transcript")

        # Track which tabs are open
        self._TAB_QUEUE = 0
        self._TAB_TRANSCRIPT = 1
        self._TAB_CHAT = 2  # index when visible

        # Chat tab — only shown when at least one AI chat provider is configured
        self._chat_visible = False
        self._refresh_chat_tab_visibility()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._notebook, 1, wx.EXPAND)
        self.SetSizer(sizer)

        # Notebook page change event — update state management
        self._notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_tab_changed)

    def _refresh_chat_tab_visibility(self) -> None:
        """Show or hide the Chat tab based on AI provider availability.

        The Chat tab is only visible when at least one AI chat provider
        is configured (has an API key or is otherwise enabled).  This
        should be called on startup and after AI settings change.
        """
        from bits_whisperer.core.ai_service import AIService

        ai_service = AIService(self.key_store, self.app_settings.ai)
        has_provider = ai_service.is_configured()

        if has_provider and not self._chat_visible:
            # Add the Chat tab
            self._notebook.AddPage(self.chat_panel, "Chat")
            self._chat_visible = True
            self._TAB_CHAT = self._notebook.GetPageCount() - 1
        elif not has_provider and self._chat_visible:
            # Remove the Chat tab
            for idx in range(self._notebook.GetPageCount()):
                if self._notebook.GetPage(idx) is self.chat_panel:
                    self._notebook.RemovePage(idx)
                    break
            self._chat_visible = False

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
            dlg.Destroy()
            self._show_add_wizard(paths)
        else:
            dlg.Destroy()

    def _on_add_folder(self, _event: wx.CommandEvent) -> None:
        dlg = wx.DirDialog(
            self,
            message="Choose a folder containing audio files",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            folder = dlg.GetPath()
            dlg.Destroy()
            self._process_folder(folder)
        else:
            dlg.Destroy()

    def _process_folder(self, folder: str) -> None:
        """Discover audio files in *folder*, estimate costs, and enqueue.

        For paid (cloud) providers the user is shown a cost estimate
        dialog and must confirm before files are queued.  Local / free
        providers skip the estimate and go straight to the wizard.

        Args:
            folder: Absolute path of the selected folder.
        """
        folder_path = Path(folder)
        files = [
            str(f)
            for f in sorted(folder_path.rglob("*"))
            if f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        ]
        if not files:
            accessible_message_box(
                f"No audio files found in:\n{folder}",
                "No Audio Files",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Show the add-file wizard so the user can pick provider/model
        from bits_whisperer.ui.add_file_wizard import AddFileWizard

        wizard = AddFileWizard(self, main_frame=self, paths=files)
        if wizard.ShowModal() != wx.ID_OK or not wizard.result_jobs:
            wizard.Destroy()
            return

        jobs = wizard.result_jobs
        wizard.Destroy()

        # Ensure cost estimates are populated on jobs (wizard may
        # have already set them, but fill any gaps)
        provider_key = jobs[0].provider if jobs else ""
        caps = self.provider_manager.get_capabilities(provider_key) if provider_key else None
        is_paid = (
            caps is not None
            and getattr(caps, "provider_type", "local") == "cloud"
            and getattr(caps, "rate_per_minute_usd", 0) > 0
        )

        if is_paid:
            for job in jobs:
                if job.cost_estimate <= 0:
                    dur = job.duration_seconds or 0.0
                    if dur <= 0:
                        dur = max(60.0, job.file_size_bytes / (10 * 1024 * 1024) * 60)
                    job.cost_estimate = self.provider_manager.estimate_cost(provider_key, dur)

        # Add jobs as a folder branch in the tree
        self.queue_panel.add_folder(folder, jobs)
        self._add_to_recent([str(f) for f in files[:5]])  # keep recent list manageable
        announce_status(
            self,
            f"Added folder with {len(jobs)} file{'s' if len(jobs) != 1 else ''} to queue",
        )
        self._notebook.SetSelection(self._TAB_QUEUE)

    def _enqueue_files(self, paths: list[str]) -> None:
        """Add file paths to the queue panel."""
        self.queue_panel.add_files(paths)
        self._add_to_recent(paths)
        count = len(paths)
        announce_status(self, f"Added {count} file{'s' if count != 1 else ''} to queue")
        # Switch to Queue tab so the user sees the new items
        self._notebook.SetSelection(self._TAB_QUEUE)

    def _show_add_wizard(self, paths: list[str]) -> None:
        """Open the Add File wizard to configure and enqueue files.

        Args:
            paths: List of absolute audio file paths.
        """
        from bits_whisperer.ui.add_file_wizard import AddFileWizard

        wizard = AddFileWizard(self, main_frame=self, paths=paths)
        if wizard.ShowModal() == wx.ID_OK and wizard.result_jobs:
            jobs = wizard.result_jobs
            for job in jobs:
                self.queue_panel.add_job(job)
            self._add_to_recent(paths)
            count = len(jobs)
            announce_status(self, f"Added {count} file{'s' if count != 1 else ''} to queue")
            # Switch to Queue tab
            self._notebook.SetSelection(self._TAB_QUEUE)
        wizard.Destroy()

    # ------------------------------------------------------------------ #
    # Tab navigation                                                       #
    # ------------------------------------------------------------------ #

    def _on_tab_changed(self, event: wx.BookCtrlEvent) -> None:
        """Respond to tab selection changes for state management."""
        event.Skip()
        self._update_menu_state()

    def _on_next_tab(self, _event: wx.CommandEvent) -> None:
        """Ctrl+Tab — switch to the next tab."""
        sel = self._notebook.GetSelection()
        count = self._notebook.GetPageCount()
        self._notebook.SetSelection((sel + 1) % count)

    def _on_prev_tab(self, _event: wx.CommandEvent) -> None:
        """Ctrl+Shift+Tab — switch to the previous tab."""
        sel = self._notebook.GetSelection()
        count = self._notebook.GetPageCount()
        self._notebook.SetSelection((sel - 1) % count)

    def _on_next_pane(self, _event: wx.CommandEvent) -> None:
        """F6 — move focus into the current tab's main control."""
        page = self._notebook.GetCurrentPage()
        if page:
            page.SetFocus()
            tab_name = self._notebook.GetPageText(self._notebook.GetSelection())
            announce_status(self, f"Focus: {tab_name} tab")

    def _on_prev_pane(self, _event: wx.CommandEvent) -> None:
        """Shift+F6 — move focus back to the tab strip."""
        self._notebook.SetFocus()
        tab_name = self._notebook.GetPageText(self._notebook.GetSelection())
        announce_status(self, f"Tab strip — {tab_name}")

    # ------------------------------------------------------------------ #
    # Menu / button state management                                       #
    # ------------------------------------------------------------------ #

    def _update_menu_state(self) -> None:
        """Enable or disable menu items based on whether a transcript is loaded.

        Called on tab changes, job completions, and other state transitions.
        """
        has_transcript = (
            self.transcript_panel._current_job is not None
            and self.transcript_panel._current_job.result is not None
        )
        has_pending = bool(self.queue_panel.get_pending_jobs())
        has_jobs = bool(self.queue_panel._jobs)
        has_completed = any(
            j.status == JobStatus.COMPLETED for j in self.queue_panel._jobs.values()
        )
        has_failed = any(j.status == JobStatus.FAILED for j in self.queue_panel._jobs.values())
        is_queue_tab = self._notebook.GetSelection() == self._TAB_QUEUE

        menu_bar = self.GetMenuBar()
        if not menu_bar:
            return

        # Export / AI items require a loaded transcript
        menu_bar.Enable(ID_EXPORT, has_transcript)
        menu_bar.Enable(ID_TRANSLATE, has_transcript)
        menu_bar.Enable(ID_TRANSLATE_MULTI, has_transcript)
        menu_bar.Enable(ID_SUMMARIZE, has_transcript)
        menu_bar.Enable(ID_COPILOT_CHAT, has_transcript)
        # AI Action Builder is always accessible — users create templates anytime

        # Queue actions need pending jobs
        menu_bar.Enable(ID_START, has_pending)

        # Batch operations
        menu_bar.Enable(ID_CLEAR_COMPLETED, has_completed)
        menu_bar.Enable(ID_RETRY_FAILED, has_failed)
        menu_bar.Enable(ID_RENAME, is_queue_tab and has_jobs)

        # Update transcript panel button states
        self.transcript_panel.update_button_state(has_transcript)

    def _on_start(self, _event: wx.CommandEvent) -> None:
        from bits_whisperer.core.sdk_installer import ensure_sdk

        jobs = self.queue_panel.get_pending_jobs()
        if not jobs:
            announce_status(self, "No pending jobs — add files first with Ctrl+O")
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

        # Reset old completed jobs so batch-complete fires cleanly
        self.transcription_service.reset_for_new_batch()

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

    def _on_audio_preview_selected(self, _event: wx.CommandEvent) -> None:
        """Preview the audio file for the selected queue item."""
        job_id = self.queue_panel.get_selected_job_id()
        if not job_id:
            accessible_message_box(
                "Select a file in the queue to preview it.",
                "No File Selected",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        job = self.queue_panel.get_job(job_id)
        if not job:
            accessible_message_box(
                "The selected item is no longer available.",
                "Preview Not Available",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        from bits_whisperer.ui.audio_player_dialog import AudioPlayerDialog

        dlg = AudioPlayerDialog(
            self,
            job.file_path,
            settings=self.app_settings.playback,
        )
        dlg.ShowModal()
        dlg.Destroy()

    def _on_clear_queue(self, _event: wx.CommandEvent) -> None:
        self.queue_panel.clear_all()
        announce_status(self, "Queue cleared")

    def _on_clear_completed(self, _event: wx.CommandEvent) -> None:
        """Remove all completed jobs from the queue."""
        self.queue_panel._on_clear_completed(None)

    def _on_retry_failed(self, _event: wx.CommandEvent) -> None:
        """Retry all failed jobs in the queue."""
        self.queue_panel._on_retry_all_failed(None)

    def _on_rename_selected(self, _event: wx.CommandEvent) -> None:
        """Rename the selected item in the queue panel."""
        if self._notebook.GetSelection() == self._TAB_QUEUE:
            self.queue_panel._on_rename_item()
        else:
            announce_status(self, "Switch to the Queue tab to rename items")

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
        accessible_message_box(msg, "Hardware Information", wx.OK | wx.ICON_INFORMATION, self)

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
                    accessible_message_box(
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
            # Also verify registration key
            if (
                self.key_store.has_key("registration_key")
                and self.registration_service.verify_key()
            ):
                safe_call_after(self._update_window_title)

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

    def _on_live_transcription(self, _event: wx.CommandEvent) -> None:
        """Open the live transcription dialog."""
        from bits_whisperer.ui.live_transcription_dialog import LiveTranscriptionDialog

        dlg = LiveTranscriptionDialog(self, main_frame=self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_ai_settings(self, _event: wx.CommandEvent) -> None:
        """Open the AI provider settings dialog."""
        from bits_whisperer.ui.ai_settings_dialog import AISettingsDialog

        dlg = AISettingsDialog(self, main_frame=self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            self.app_settings = AppSettings.load()
            self._refresh_chat_tab_visibility()
            announce_status(self, "AI settings updated")
        dlg.Destroy()

    def _on_audio_preview(self, _event: wx.CommandEvent) -> None:
        """Open the audio preview dialog for a selected file."""
        from bits_whisperer.ui.audio_player_dialog import AudioPlayerDialog

        dlg = wx.FileDialog(
            self,
            message="Choose an audio file to preview",
            wildcard=AUDIO_WILDCARD,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            dlg.Destroy()
            preview = AudioPlayerDialog(
                self,
                path,
                settings=self.app_settings.playback,
            )
            preview.ShowModal()
            preview.Destroy()
        else:
            dlg.Destroy()

    def _on_translate(self, _event: wx.CommandEvent) -> None:
        """Translate the current transcript using AI."""
        self._run_ai_action("translate")

    def _on_translate_multi(self, _event: wx.CommandEvent) -> None:
        """Translate the transcript to all configured target languages."""
        import threading

        from bits_whisperer.core.ai_service import AIService

        job = self.transcript_panel._current_job
        if not job or not job.result:
            accessible_message_box(
                "No transcript loaded. Transcribe a file first.",
                "No Transcript",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        text = job.result.full_text
        if not text:
            text = "\n".join(s.text for s in job.result.segments)
        if not text.strip():
            accessible_message_box(
                "The transcript is empty.",
                "Empty Transcript",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        ai_service = AIService(self.key_store, self.app_settings.ai)
        if not ai_service.is_configured():
            result = accessible_message_box(
                "No AI provider is configured.\n\n"
                "Would you like to open AI Settings to add an API key?",
                "AI Not Configured",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            if result == wx.YES:
                self._on_ai_settings(None)
            return

        targets = self.app_settings.ai.multi_target_languages
        if not targets:
            accessible_message_box(
                "No target languages configured.\n\n"
                "Go to AI > AI Provider Settings > Multi-Language tab "
                "and select target languages.",
                "No Languages Selected",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        announce_status(
            self,
            f"Translating transcript to {len(targets)} language(s)\u2026",
        )

        def _do_multi_translate() -> None:
            results = ai_service.translate_multi(text, targets)

            def _show_results() -> None:
                # Build combined output
                parts = []
                errors = []
                for lang, resp in results.items():
                    if resp.error:
                        errors.append(f"{lang}: {resp.error}")
                    else:
                        parts.append(f"=== {lang} ===\n{resp.text}\n")

                if errors:
                    accessible_message_box(
                        "Some translations failed:\n\n" + "\n".join(errors),
                        "Translation Errors",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )

                if parts:
                    combined = "\n".join(parts)
                    dlg = wx.Dialog(
                        self,
                        title="Multi-Language Translation",
                        size=(700, 500),
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                    )
                    dlg.SetMinSize((400, 300))
                    sizer = wx.BoxSizer(wx.VERTICAL)

                    info = wx.StaticText(
                        dlg,
                        label=f"Translated to {len(parts)} language(s)",
                    )
                    sizer.Add(info, 0, wx.ALL, 10)

                    txt = wx.TextCtrl(
                        dlg,
                        value=combined,
                        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
                    )
                    sizer.Add(txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

                    btn_row = wx.BoxSizer(wx.HORIZONTAL)
                    copy_btn = wx.Button(dlg, label="&Copy")
                    copy_btn.Bind(
                        wx.EVT_BUTTON,
                        lambda e: self._copy_text(combined),
                    )
                    btn_row.Add(copy_btn, 0, wx.RIGHT, 8)

                    close_btn = wx.Button(dlg, wx.ID_CLOSE, label="&Close")
                    btn_row.Add(close_btn, 0)

                    sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

                    dlg.SetSizer(sizer)
                    dlg.Bind(
                        wx.EVT_BUTTON,
                        lambda e: dlg.EndModal(wx.ID_CLOSE),
                        id=wx.ID_CLOSE,
                    )
                    dlg.ShowModal()
                    dlg.Destroy()

                announce_status(
                    self,
                    f"Multi-language translation complete ({len(parts)} languages)",
                )

            safe_call_after(_show_results)

        threading.Thread(target=_do_multi_translate, daemon=True).start()

    def _on_summarize(self, _event: wx.CommandEvent) -> None:
        """Summarize the current transcript using AI."""
        self._run_ai_action("summarize")

    def _run_ai_action(self, action: str) -> None:
        """Run an AI action (translate or summarize) on the current transcript.

        Args:
            action: Either 'translate' or 'summarize'.
        """
        import threading

        from bits_whisperer.core.ai_service import AIService

        # Check for transcript
        job = self.transcript_panel._current_job
        if not job or not job.result:
            accessible_message_box(
                "No transcript loaded. Transcribe a file first.",
                "No Transcript",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Build text from transcript
        text = job.result.full_text
        if not text:
            text = "\n".join(s.text for s in job.result.segments)

        if not text.strip():
            accessible_message_box(
                "The transcript is empty.",
                "Empty Transcript",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Check AI service is configured
        ai_service = AIService(self.key_store, self.app_settings.ai)
        if not ai_service.is_configured():
            result = accessible_message_box(
                "No AI provider is configured.\n\n"
                "Would you like to open AI Settings to add an API key?",
                "AI Not Configured",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            )
            if result == wx.YES:
                self._on_ai_settings(None)
            return

        # Run in background thread
        announce_status(
            self,
            f"{'Translating' if action == 'translate' else 'Summarizing'} transcript…",
        )

        def _do_action() -> None:
            if action == "translate":
                response = ai_service.translate(text)
            else:
                response = ai_service.summarize(text)

            def _show_result() -> None:
                if response.error:
                    accessible_message_box(
                        f"AI {action} failed:\n\n{response.error}",
                        f"{action.title()} Error",
                        wx.OK | wx.ICON_ERROR,
                        self,
                    )
                    return

                # Show result in a dialog
                dlg = wx.Dialog(
                    self,
                    title=f"{action.title()} Result",
                    size=(700, 500),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                )
                dlg.SetMinSize((400, 300))
                sizer = wx.BoxSizer(wx.VERTICAL)

                info = wx.StaticText(
                    dlg,
                    label=f"Provider: {response.provider} | Model: {response.model} "
                    f"| Tokens: {response.tokens_used}",
                )
                sizer.Add(info, 0, wx.ALL, 10)

                txt = wx.TextCtrl(
                    dlg,
                    value=response.text,
                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
                )
                font = wx.Font(
                    11,
                    wx.FONTFAMILY_DEFAULT,
                    wx.FONTSTYLE_NORMAL,
                    wx.FONTWEIGHT_NORMAL,
                )
                txt.SetFont(font)
                sizer.Add(txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

                btn_row = wx.BoxSizer(wx.HORIZONTAL)
                copy_btn = wx.Button(dlg, label="&Copy")
                copy_btn.Bind(
                    wx.EVT_BUTTON,
                    lambda e: self._copy_text(response.text),
                )
                btn_row.Add(copy_btn, 0, wx.RIGHT, 8)

                close_btn = wx.Button(dlg, wx.ID_CLOSE, label="&Close")
                btn_row.Add(close_btn, 0)

                sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

                dlg.SetSizer(sizer)
                dlg.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
                dlg.ShowModal()
                dlg.Destroy()

                announce_status(
                    self,
                    f"Transcript {action}d successfully",
                )

            safe_call_after(_show_result)

        threading.Thread(target=_do_action, daemon=True).start()

    def _copy_text(self, text: str) -> None:
        """Copy text to clipboard.

        Args:
            text: Text to copy.
        """
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            announce_status(self, "Copied to clipboard")

    def _on_plugins(self, _event: wx.CommandEvent) -> None:
        """Open the plugins management dialog."""
        from bits_whisperer.core.plugin_manager import PluginManager

        plugin_mgr = PluginManager(self.app_settings.plugins, self.provider_manager)
        plugins = plugin_mgr.discover()

        if not plugins:
            plugin_dir = plugin_mgr.get_plugin_dir()
            accessible_message_box(
                f"No plugins found.\n\n"
                f"To add plugins, place Python files in:\n{plugin_dir}\n\n"
                f"Each plugin must define a register(manager) function.",
                "No Plugins",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Show simple plugin list dialog
        items = []
        for p in plugins:
            status = "Loaded" if p.is_loaded else ("Disabled" if not p.is_enabled else "Available")
            items.append(f"{p.name} v{p.version} [{status}]")

        dlg = wx.SingleChoiceDialog(
            self,
            f"Found {len(plugins)} plugin(s).\n" "Select a plugin to toggle enabled/disabled:",
            "Plugins",
            items,
        )
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            plugin = plugins[idx]
            if plugin.is_enabled:
                plugin_mgr.disable_plugin(plugin.module_name)
                announce_status(self, f"Disabled plugin: {plugin.name}")
            else:
                plugin_mgr.enable_plugin(plugin.module_name)
                plugin_mgr.load_plugin(plugin.module_name)
                announce_status(self, f"Enabled plugin: {plugin.name}")
            self.app_settings.save()
        dlg.Destroy()

    # =================================================================== #
    # Copilot / AI chat handlers                                            #
    # =================================================================== #

    def _ensure_copilot_service(self) -> None:
        """Lazily create and configure the Copilot service."""
        if self._copilot_service is not None:
            return
        from bits_whisperer.core.copilot_service import CopilotService

        self._copilot_service = CopilotService(self.key_store, self.app_settings.copilot)
        self.chat_panel.connect(self._copilot_service)

    def _on_copilot_setup(self, _event: wx.CommandEvent) -> None:
        """Open the Copilot Setup wizard."""
        from bits_whisperer.ui.copilot_setup_dialog import CopilotSetupDialog

        dlg = CopilotSetupDialog(self, main_frame=self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            self.app_settings = AppSettings.load()
            # Reinitialise the service with new settings.
            # Stop old service if running.
            if self._copilot_service is not None:
                with contextlib.suppress(Exception):
                    self._copilot_service.stop()
            self._copilot_service = None
            # Only eagerly start the service if the chat panel is visible;
            # otherwise it will start on demand when the user opens chat.
            if self._chat_visible:
                self._ensure_copilot_service()
            announce_status(self, "Copilot setup saved")
        dlg.Destroy()

    def _on_copilot_chat(self, _event: wx.CommandEvent) -> None:
        """Toggle focus to / from the AI chat tab."""
        if not self._chat_visible:
            accessible_message_box(
                "No AI chat provider is configured.\n\n"
                "Go to AI > AI Provider Settings to set up an "
                "AI provider, then try again.",
                "Chat Not Available",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        current = self._notebook.GetSelection()
        if current == self._TAB_CHAT:
            # Already on chat — toggle back to transcript
            self._notebook.SetSelection(self._TAB_TRANSCRIPT)
            self._copilot_chat_item.Check(False)
            announce_status(self, "Switched to Transcript tab")
        else:
            # Switch to chat tab
            self._notebook.SetSelection(self._TAB_CHAT)
            self._copilot_chat_item.Check(True)

            # Only start CopilotService if Copilot is the selected provider
            settings = AppSettings.load()
            if settings.ai.selected_provider == "copilot":
                self._ensure_copilot_service()

            # Inject current transcript context if available
            job = self.transcript_panel._current_job
            if job and job.result:
                text = job.result.full_text
                if not text:
                    text = "\n".join(s.text for s in job.result.segments)
                if text.strip():
                    self.chat_panel.set_transcript_context(text)

            self.chat_panel._input_text.SetFocus()
            announce_status(self, "AI chat tab \u2014 ask anything about your transcript")

    def _on_agent_builder(self, _event: wx.CommandEvent) -> None:
        """Open the AI Action Builder dialog."""
        from bits_whisperer.ui.agent_builder_dialog import AgentBuilderDialog

        self._ensure_copilot_service()

        dlg = AgentBuilderDialog(
            self,
            main_frame=self,
            config=self._copilot_service.agent_config,
        )
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            new_config = dlg.result_config
            if new_config:
                self._copilot_service.agent_config = new_config
                announce_status(
                    self,
                    f"AI action template '{new_config.name}' configured",
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
            accessible_message_box(
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
        """Handle explicit exit (File > Exit or Alt+F4) — always truly quit."""
        self._request_exit()

    # =================================================================== #
    # Callbacks from transcription service (called from worker threads)     #
    # =================================================================== #

    def _on_job_update(self, job) -> None:
        """Called by the transcription service when a job's state changes."""
        safe_call_after(self._handle_job_update, job)

    def _on_batch_complete(self, jobs) -> None:
        """Called when all queued jobs have finished."""
        safe_call_after(self._handle_batch_complete, jobs)

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
            # Auto-switch to the Transcript tab
            self._notebook.SetSelection(self._TAB_TRANSCRIPT)
            self._update_menu_state()

            # Tray notification (especially useful when minimized)
            if not self.IsShown():
                self._tray_icon.notify_job_complete(job.display_name)

            # Auto-export
            if self._auto_export:
                self._auto_export_transcript(job)

        elif job.status.value == "failed":
            error_msg = job.error_message or "Unknown error"
            announce_to_screen_reader(f"Transcription failed for {job.display_name}: {error_msg}")
            if not self.IsShown():
                self._tray_icon.notify_error(
                    job.display_name,
                    error_msg,
                )

        # Handle AI action status updates
        if job.ai_action_status == "running":
            announce_status(
                self,
                f"{job.display_name}: Running AI action\u2026",
            )
        elif job.ai_action_status == "completed":
            # Refresh transcript display with AI action results
            self.transcript_panel.show_transcript(job)
            self._notebook.SetSelection(self._TAB_TRANSCRIPT)
            announce_status(
                self,
                f"{job.display_name}: AI action completed",
            )
            announce_to_screen_reader(
                f"AI action completed for {job.display_name}. "
                "Results are shown below the transcript."
            )
        elif job.ai_action_status == "failed":
            error_msg = job.ai_action_error or "Unknown error"
            announce_status(
                self,
                f"{job.display_name}: AI action failed \u2014 {error_msg}",
            )
            announce_to_screen_reader(f"AI action failed for {job.display_name}: {error_msg}")

    def _handle_batch_complete(self, jobs: list | None = None) -> None:
        self._progress_gauge.SetValue(100)

        # Build a meaningful summary based on actual job outcomes
        if jobs:
            from bits_whisperer.core.job import JobStatus

            completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
            failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
            cancelled = sum(1 for j in jobs if j.status == JobStatus.CANCELLED)
            total = len(jobs)

            if failed == total:
                msg = f"All {total} job(s) failed"
                announce_status(self, msg)
                announce_to_screen_reader(msg)
                # Collect first error for extra context
                first_err = next(
                    (j.error_message for j in jobs if j.error_message), "Unknown error"
                )
                announce_to_screen_reader(f"Error: {first_err}")
            elif failed > 0:
                msg = (
                    f"Batch finished: {completed} completed, "
                    f"{failed} failed, {cancelled} cancelled"
                )
                announce_status(self, msg)
                announce_to_screen_reader(msg)
            elif cancelled == total:
                msg = f"All {total} job(s) cancelled"
                announce_status(self, msg)
                announce_to_screen_reader(msg)
            else:
                msg = f"All {completed} transcription job(s) complete!"
                announce_status(self, msg)
                announce_to_screen_reader(msg)
        else:
            announce_status(self, "All transcription jobs complete!")
            announce_to_screen_reader("All transcription jobs complete!")

        self._tray_icon.set_idle()

        summary = self.transcription_service.get_progress_summary()
        self._tray_icon.notify_batch_complete(
            total=summary["total"],
            failed=summary["failed"],
        )

        # Play notification sound only for successful completions
        if self.app_settings.general.play_sound:
            has_success = jobs and any(j.status.value == "completed" for j in jobs)
            if has_success or not jobs:
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

    def _request_exit(self) -> None:
        """Initiate a true application exit with optional confirmation.

        Called from File > Exit, Alt+F4, and tray Quit. Uses a
        confirmation dialog controlled by the ``confirm_before_quit``
        setting, with a "Don't ask me again" checkbox.
        """
        if self.app_settings.general.confirm_before_quit:
            dlg = wx.RichMessageDialog(
                self,
                "Are you sure you want to exit BITS Whisperer?",
                "Confirm Exit",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            )
            dlg.ShowCheckBox("Don't ask me again")
            set_accessible_name(dlg, "Confirm exit dialog")
            announce_to_screen_reader("Are you sure you want to exit BITS Whisperer?")
            result = dlg.ShowModal()

            if dlg.IsCheckBoxChecked():
                self.app_settings.general.confirm_before_quit = False
                self.app_settings.save()

            dlg.Destroy()

            if result != wx.ID_YES:
                return

        # Proceed with real shutdown
        self._force_quit = True
        self.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        """Handle the window close event.

        - If ``_force_quit`` is set (from ``_request_exit``, tray Quit,
          or the OS forcing shutdown), perform a full cleanup and exit.
        - Otherwise, the close was triggered by the window manager's X
          button. If minimize-to-tray is enabled, hide to tray instead
          of quitting; otherwise, route through ``_request_exit`` for
          the confirmation dialog.
        """
        force = getattr(self, "_force_quit", False)

        if not force:
            # X button / system close — decide whether to minimize or confirm exit
            if self._minimize_to_tray and event.CanVeto():
                self.Show(False)
                announce_to_screen_reader("BITS Whisperer minimized to system tray")
                event.Veto()
                return
            else:
                # No minimize-to-tray: show confirmation dialog
                event.Veto()
                self._request_exit()
                return

        # ---- True shutdown path ----
        logger.info("Shutting down — stopping services")

        # 1. Stop transcription workers and clean up their temp files
        try:
            self.transcription_service.stop()
        except Exception as exc:
            logger.debug("Error stopping transcription service: %s", exc)

        # 2. Stop Copilot SDK (session + event loop + thread join)
        if self._copilot_service:
            try:
                self._copilot_service.stop()
            except Exception as exc:
                logger.debug("Error stopping Copilot service: %s", exc)

        # 3. Save settings to persist any unsaved changes
        try:
            self.app_settings.save()
        except Exception as exc:
            logger.debug("Error saving settings on exit: %s", exc)

        # 4. Remove tray icon
        if hasattr(self, "_tray_icon"):
            try:
                self._tray_icon.cleanup()
            except Exception as exc:
                logger.debug("Error cleaning up tray icon: %s", exc)

        # 5. Clean up stale temp files from prior runs
        self._cleanup_stale_temp_files()

        logger.info("Shutdown cleanup complete")
        self.Destroy()

    @staticmethod
    def _cleanup_stale_temp_files() -> None:
        """Remove leftover temp files from prior BITS Whisperer runs.

        Scans the system temp directory for files matching the known
        prefixes used by the transcoder (``bw_transcode_``),
        preprocessor (``bw_preprocess_``), and updater (``bw_update_``).
        Files older than 1 hour are deleted to avoid removing files
        from a concurrent instance.
        """
        import tempfile
        import time

        tmp_dir = Path(tempfile.gettempdir())
        cutoff = time.time() - 3600  # 1 hour ago
        prefixes = ("bw_transcode_", "bw_preprocess_")
        dir_prefixes = ("bw_update_",)
        removed = 0

        # Clean stale temp files
        for prefix in prefixes:
            for p in tmp_dir.glob(f"{prefix}*"):
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff:
                        p.unlink()
                        removed += 1
                except Exception:
                    pass

        # Clean stale update directories
        import shutil

        for prefix in dir_prefixes:
            for p in tmp_dir.glob(f"{prefix}*"):
                try:
                    if p.is_dir() and p.stat().st_mtime < cutoff:
                        shutil.rmtree(p, ignore_errors=True)
                        removed += 1
                except Exception:
                    pass

        if removed:
            logger.info("Cleaned up %d stale temp file(s) from prior runs", removed)

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
            self._show_add_wizard([path])
        else:
            accessible_message_box(
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
