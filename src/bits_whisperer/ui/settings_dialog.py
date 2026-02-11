"""Comprehensive settings dialog with 7 accessible tabs.

Tabs
----
1. **General** — language, provider, behaviour, startup options
2. **Transcription** — timestamps, speakers, confidence, word-level,
   segmentation, prompts, VAD, temperature, beam size, compute type
3. **Output** — default format, directory, filename template, encoding,
   header/metadata, overwrite policy
4. **Providers & Keys** — per-provider API key entry with validation status
5. **Audio Processing** — 7-filter ffmpeg preprocessing chain with
   individual parameter controls (Advanced Mode only)
6. **Paths & Storage** — output dir, models dir, temp dir, log location
7. **Advanced** — file/batch limits, concurrency, chunking, background
   processing, GPU index, CPU threads, log level (Advanced Mode only)

Accessibility
-------------
* ``wx.Notebook`` with ``wx.TAB_TRAVERSAL`` — Tab/Shift-Tab moves between
  controls; Ctrl-Tab / Ctrl-Shift-Tab switches tabs.
* Every control has ``SetName()``, ``SetHelpText()``, and a label association.
* OK / Apply / Cancel button row at the bottom.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.audio_preprocessor import PreprocessorSettings
from bits_whisperer.core.settings import AppSettings, PlaybackSettings
from bits_whisperer.storage.key_store import KeyStore
from bits_whisperer.utils.accessibility import (
    announce_status,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import EXPORT_FORMATS

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Mapping from KeyStore provider IDs to ProviderManager keys for validation
_KEYSTORE_TO_PROVIDER: dict[str, str] = {
    "openai": "openai_whisper",
    "google": "google_speech",
    "azure": "azure_speech",
    "deepgram": "deepgram",
    "assemblyai": "assemblyai",
    "gemini": "gemini",
    "aws_access_key": "aws_transcribe",
    "groq": "groq_whisper",
    "rev_ai": "rev_ai",
    "speechmatics": "speechmatics",
    "elevenlabs": "elevenlabs",
    "auphonic": "auphonic",
}

# Keys that are secondary/auxiliary — no standalone test button
_AUXILIARY_KEYS: set[str] = {"aws_secret_key", "aws_region", "azure_region"}

# Languages shown in the General dropdown
_LANGUAGES: list[str] = [
    "Auto-detect",
    "English",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Chinese",
    "Japanese",
    "Korean",
    "Arabic",
    "Russian",
    "Hindi",
    "Dutch",
    "Polish",
    "Turkish",
    "Swedish",
    "Danish",
    "Norwegian",
    "Finnish",
    "Czech",
    "Greek",
    "Hebrew",
    "Thai",
    "Ukrainian",
    "Vietnamese",
    "Indonesian",
    "Malay",
]

# Timestamp format choices
_TS_FORMATS: list[str] = [
    "hh:mm:ss",
    "mm:ss",
    "Seconds only",
]

# Compute type choices
_COMPUTE_TYPES: list[str] = [
    "auto",
    "float16",
    "int8",
    "float32",
]

# Log-level choices
_LOG_LEVELS: list[str] = [
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
]

_JUMP_SECONDS: list[int] = [1, 2, 3, 5, 10, 15, 30, 60]


class SettingsDialog(wx.Dialog):
    """Seven-tab settings dialog for BITS Whisperer.

    Provides OK (save + close), Apply (save), and Cancel buttons.
    Ctrl-Tab / Ctrl-Shift-Tab switch between tabs.
    """

    def __init__(self, parent: MainFrame) -> None:
        """Initialise the settings dialog."""
        super().__init__(
            parent,
            title="Settings — BITS Whisperer",
            size=(720, 640),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Settings dialog")
        self.SetMinSize((640, 520))
        self._main_frame: MainFrame = parent
        self._key_store: KeyStore = parent.key_store
        self._settings: AppSettings = getattr(
            parent,
            "app_settings",
            AppSettings.load(),
        )

        self._build_ui()
        self.CentreOnParent()

    # ================================================================== #
    # UI construction                                                      #
    # ================================================================== #

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)

        # --- Notebook (Ctrl-Tab accessible) ---
        self._notebook = wx.Notebook(
            self,
            style=wx.NB_TOP,
        )
        set_accessible_name(self._notebook, "Settings tabs")

        # Always-visible tabs
        self._notebook.AddPage(self._build_general_tab(), "G&eneral")
        self._notebook.AddPage(
            self._build_transcription_tab(),
            "&Transcription",
        )
        self._notebook.AddPage(self._build_output_tab(), "&Output")
        self._notebook.AddPage(self._build_playback_tab(), "&Playback")
        self._notebook.AddPage(self._build_budget_tab(), "&Budget")
        self._notebook.AddPage(
            self._build_providers_tab(),
            "P&roviders && Keys",
        )
        self._notebook.AddPage(
            self._build_paths_tab(),
            "Pa&ths && Storage",
        )

        # Advanced-mode-only tabs
        is_advanced = getattr(self._main_frame, "is_advanced_mode", False)
        self._audio_proc_panel = self._build_audio_processing_tab()
        self._advanced_panel = self._build_advanced_tab()
        if is_advanced:
            self._notebook.AddPage(
                self._audio_proc_panel,
                "Audio &Processing",
            )
            self._notebook.AddPage(self._advanced_panel, "Ad&vanced")

        root.Add(self._notebook, 1, wx.ALL | wx.EXPAND, 8)

        # --- Buttons: OK / Apply / Cancel ---
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        self._btn_ok = wx.Button(self, wx.ID_OK, "&OK")
        set_accessible_name(self._btn_ok, "OK")
        set_accessible_help(
            self._btn_ok,
            "Save all settings and close",
        )

        self._btn_apply = wx.Button(self, wx.ID_APPLY, "&Apply")
        set_accessible_name(self._btn_apply, "Apply")
        set_accessible_help(
            self._btn_apply,
            "Save all settings without closing the dialog",
        )

        self._btn_cancel = wx.Button(self, wx.ID_CANCEL, "&Cancel")
        set_accessible_name(self._btn_cancel, "Cancel")

        btn_sizer.Add(self._btn_ok, 0, wx.RIGHT, 6)
        btn_sizer.Add(self._btn_cancel, 0, wx.RIGHT, 6)
        btn_sizer.Add(self._btn_apply, 0)

        root.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizer(root)

        # --- Button bindings ---
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_apply, id=wx.ID_APPLY)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)

        self._btn_ok.SetDefault()

    # ================================================================== #
    # Tab 1: General                                                       #
    # ================================================================== #

    def _build_general_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        s = self._settings.general

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Provider & language ---
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        grid.AddGrowableCol(1, 1)

        lbl_lang = wx.StaticText(panel, label="Default &language:")
        self._lang_ch = wx.Choice(panel, choices=_LANGUAGES)
        self._lang_ch.SetStringSelection(
            "Auto-detect" if s.language == "auto" else s.language,
        )
        label_control(lbl_lang, self._lang_ch)
        set_accessible_help(
            self._lang_ch,
            "Default language for transcription",
        )
        grid.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._lang_ch, 0, wx.EXPAND)

        lbl_prov = wx.StaticText(panel, label="Default &provider:")

        # Build provider list: always show local providers.
        # In Basic mode, only show activated cloud providers.
        # In Advanced mode, show all cloud providers.
        is_advanced = getattr(self._main_frame, "is_advanced_mode", False)
        activated = set(s.activated_providers)
        supported = KeyStore.get_supported_providers()

        # Local providers are always available
        provider_names = [
            "Local Whisper (auto)",
            "Vosk (lightweight offline)",
            "Parakeet (NVIDIA NeMo)",
        ]
        self._provider_keys = ["local_whisper", "vosk", "parakeet"]

        # Cloud providers: filter by activation status in Basic mode
        _keystore_to_pm = {
            "openai": ("openai_whisper", "OpenAI Whisper API"),
            "google": ("google_speech", "Google Cloud Speech"),
            "azure": ("azure_speech", "Azure Speech"),
            "azure_region": (None, None),
            "deepgram": ("deepgram", "Deepgram Nova-2"),
            "assemblyai": ("assemblyai", "AssemblyAI"),
            "gemini": ("gemini", "Google Gemini"),
            "aws_access_key": ("aws_transcribe", "Amazon Transcribe"),
            "aws_secret_key": (None, None),
            "aws_region": (None, None),
            "groq": ("groq_whisper", "Groq Whisper"),
            "rev_ai": ("rev_ai", "Rev.ai"),
            "speechmatics": ("speechmatics", "Speechmatics"),
            "elevenlabs": ("elevenlabs", "ElevenLabs Scribe"),
            "auphonic": ("auphonic", "Auphonic"),
        }

        for kid, pname in supported.items():
            pm_info = _keystore_to_pm.get(kid)
            if pm_info is None or pm_info[0] is None:
                continue  # Skip auxiliary keys

            pm_key, _display_name = pm_info
            if is_advanced or kid in activated:
                provider_names.append(pname)
                if pm_key is not None:
                    self._provider_keys.append(pm_key)

        self._provider_ch = wx.Choice(panel, choices=provider_names)
        # Select current default provider
        try:
            prov_idx = self._provider_keys.index(s.default_provider)
        except ValueError:
            prov_idx = 0
        self._provider_ch.SetSelection(prov_idx)
        label_control(lbl_prov, self._provider_ch)
        set_accessible_help(
            self._provider_ch,
            "Which provider to use by default for new transcription jobs",
        )
        grid.Add(lbl_prov, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._provider_ch, 0, wx.EXPAND)

        # Hint for Basic mode users
        if not is_advanced and len(provider_names) <= 3:
            hint = wx.StaticText(
                panel,
                label=(
                    "Only local providers are shown. "
                    "Use Tools > Add Provider to activate cloud services, "
                    "or switch to Advanced mode in View > Advanced Mode."
                ),
            )
            hint.Wrap(580)
            hint.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            set_accessible_name(hint, "Provider availability hint")
            grid.Add((0, 0))
            grid.Add(hint, 0, wx.EXPAND)

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 12)

        # --- BITS Registration Section ---
        reg_box = wx.StaticBox(panel, label="BITS Registration (All Products)")
        reg_sizer = wx.StaticBoxSizer(reg_box, wx.VERTICAL)

        status_msg = self._main_frame.registration_service.get_status_message()
        self._reg_status_lbl = wx.StaticText(panel, label=f"Status: {status_msg}")
        reg_sizer.Add(self._reg_status_lbl, 0, wx.ALL, 5)

        key_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_key = wx.StaticText(panel, label="&Registration Key:")
        self._reg_key_txt = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self._reg_key_txt.SetValue(self._key_store.get_key("registration_key") or "")
        label_control(lbl_key, self._reg_key_txt)

        btn_verify = wx.Button(panel, label="&Verify Key")
        self.Bind(wx.EVT_BUTTON, self._on_verify_reg_key, btn_verify)

        key_sizer.Add(lbl_key, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        key_sizer.Add(self._reg_key_txt, 1, wx.EXPAND | wx.RIGHT, 5)
        key_sizer.Add(btn_verify, 0)

        reg_sizer.Add(key_sizer, 0, wx.EXPAND | wx.ALL, 5)
        outer.Add(reg_sizer, 0, wx.ALL | wx.EXPAND, 12)

        # --- Behaviour ---
        beh_box = wx.StaticBox(panel, label="Behaviour")
        set_accessible_name(beh_box, "Behaviour settings")
        beh = wx.StaticBoxSizer(beh_box, wx.VERTICAL)

        def _cb(parent_widget, lbl, val, name, hlp=""):
            c = wx.CheckBox(parent_widget, label=lbl)
            c.SetValue(val)
            set_accessible_name(c, name)
            if hlp:
                set_accessible_help(c, hlp)
            beh.Add(c, 0, wx.ALL, 4)
            return c

        self._cb_prefer_local = _cb(
            panel,
            "&Prefer on-device models when available",
            s.prefer_local,
            "Prefer on-device models",
            "Use local Whisper models instead of cloud when hardware allows",
        )
        self._cb_minimize_tray = _cb(
            panel,
            "&Minimize to system tray on close",
            s.minimize_to_tray,
            "Minimize to tray",
            "Closing the window hides to the tray; processing continues",
        )
        self._cb_auto_export = _cb(
            panel,
            "Auto-&export transcripts on completion",
            s.auto_export,
            "Auto-export on completion",
            "Automatically save each transcript when it finishes",
        )
        self._cb_notification = _cb(
            panel,
            "Show &notifications on job completion",
            s.show_notifications,
            "Show notifications",
            "Show balloon/toast notifications on completion or failure",
        )
        self._cb_sound = _cb(
            panel,
            "Play &sound on batch completion",
            s.play_sound,
            "Play completion sound",
        )
        self._cb_start_minimized = _cb(
            panel,
            "Start &minimized to tray",
            s.start_minimized,
            "Start minimized",
        )
        self._cb_check_updates = _cb(
            panel,
            "Check for &updates on startup",
            s.check_updates_on_start,
            "Check for updates on startup",
        )
        self._cb_confirm_quit = _cb(
            panel,
            "Confirm before &quitting",
            s.confirm_before_quit,
            "Confirm quit",
        )
        self._cb_restore_queue = _cb(
            panel,
            "&Restore queue on startup",
            s.restore_queue_on_start,
            "Restore queue on startup",
        )

        outer.Add(beh, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)
        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 2: Transcription                                                 #
    # ================================================================== #

    def _build_transcription_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        t = self._settings.transcription

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Content options ---
        content_box = wx.StaticBox(panel, label="Transcript Content")
        set_accessible_name(content_box, "Transcript content options")
        cs = wx.StaticBoxSizer(content_box, wx.VERTICAL)

        self._cb_timestamps = wx.CheckBox(
            panel,
            label="Include &timestamps",
        )
        self._cb_timestamps.SetValue(t.include_timestamps)
        set_accessible_name(self._cb_timestamps, "Include timestamps")
        set_accessible_help(
            self._cb_timestamps,
            "Prefix each segment with its start time",
        )
        cs.Add(self._cb_timestamps, 0, wx.ALL, 4)

        ts_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_ts_fmt = wx.StaticText(panel, label="Timestamp &format:")
        self._ts_fmt_ch = wx.Choice(panel, choices=_TS_FORMATS)
        sel = _TS_FORMATS.index(t.timestamp_format) if t.timestamp_format in _TS_FORMATS else 0
        self._ts_fmt_ch.SetSelection(sel)
        label_control(lbl_ts_fmt, self._ts_fmt_ch)
        ts_row.Add(lbl_ts_fmt, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        ts_row.Add(self._ts_fmt_ch, 0)
        cs.Add(ts_row, 0, wx.LEFT | wx.BOTTOM, 20)

        self._cb_speakers = wx.CheckBox(
            panel,
            label="Include &speaker labels (diarization)",
        )
        self._cb_speakers.SetValue(t.include_speakers)
        set_accessible_name(self._cb_speakers, "Include speaker labels")
        set_accessible_help(
            self._cb_speakers,
            "Show speaker identification when the provider supports it",
        )
        cs.Add(self._cb_speakers, 0, wx.ALL, 4)

        self._cb_confidence = wx.CheckBox(
            panel,
            label="Include &confidence scores",
        )
        self._cb_confidence.SetValue(t.include_confidence)
        set_accessible_name(self._cb_confidence, "Include confidence scores")
        set_accessible_help(
            self._cb_confidence,
            "Append model confidence percentage to each segment",
        )
        cs.Add(self._cb_confidence, 0, wx.ALL, 4)

        self._cb_lang_tag = wx.CheckBox(
            panel,
            label="Include detected &language tag",
        )
        self._cb_lang_tag.SetValue(t.include_language_tag)
        set_accessible_name(self._cb_lang_tag, "Include language tag")
        cs.Add(self._cb_lang_tag, 0, wx.ALL, 4)

        self._cb_word_level = wx.CheckBox(
            panel,
            label="Include &word-level timestamps",
        )
        self._cb_word_level.SetValue(t.include_word_level)
        set_accessible_name(self._cb_word_level, "Word-level timestamps")
        set_accessible_help(
            self._cb_word_level,
            "Record start/end time for every word (increases output size)",
        )
        cs.Add(self._cb_word_level, 0, wx.ALL, 4)

        self._cb_paragraphs = wx.CheckBox(
            panel,
            label="&Paragraph segmentation",
        )
        self._cb_paragraphs.SetValue(t.paragraph_segmentation)
        set_accessible_name(
            self._cb_paragraphs,
            "Paragraph segmentation",
        )
        set_accessible_help(
            self._cb_paragraphs,
            "Group related sentences into paragraphs in the output",
        )
        cs.Add(self._cb_paragraphs, 0, wx.ALL, 4)

        self._cb_merge_short = wx.CheckBox(
            panel,
            label="&Merge short segments",
        )
        self._cb_merge_short.SetValue(t.merge_short_segments)
        set_accessible_name(self._cb_merge_short, "Merge short segments")
        cs.Add(self._cb_merge_short, 0, wx.ALL, 4)

        outer.Add(cs, 0, wx.ALL | wx.EXPAND, 8)

        # --- Model parameters ---
        model_box = wx.StaticBox(panel, label="Model Parameters")
        set_accessible_name(model_box, "Model parameters")
        ms = wx.StaticBoxSizer(model_box, wx.VERTICAL)
        mg = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        mg.AddGrowableCol(1, 1)

        # Prompt
        lbl_prompt = wx.StaticText(panel, label="Initial &prompt:")
        self._prompt_txt = wx.TextCtrl(panel, value=t.prompt)
        label_control(lbl_prompt, self._prompt_txt)
        set_accessible_help(
            self._prompt_txt,
            "Vocabulary hint or context for the model " "(names, acronyms, technical terms)",
        )
        mg.Add(lbl_prompt, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add(self._prompt_txt, 1, wx.EXPAND)

        # Temperature
        lbl_temp = wx.StaticText(panel, label="T&emperature:")
        self._temp_spin = wx.SpinCtrlDouble(
            panel,
            min=0.0,
            max=1.0,
            inc=0.1,
            initial=t.temperature,
        )
        label_control(lbl_temp, self._temp_spin)
        set_accessible_help(
            self._temp_spin,
            "0 = deterministic; higher values add randomness",
        )
        mg.Add(lbl_temp, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add(self._temp_spin, 0, wx.EXPAND)

        # Beam size
        lbl_beam = wx.StaticText(panel, label="&Beam size:")
        self._beam_spin = wx.SpinCtrl(
            panel,
            min=1,
            max=20,
            initial=t.beam_size,
        )
        label_control(lbl_beam, self._beam_spin)
        set_accessible_help(
            self._beam_spin,
            "Higher = more accurate but slower (5 recommended)",
        )
        mg.Add(lbl_beam, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add(self._beam_spin, 0, wx.EXPAND)

        # VAD filter
        self._cb_vad = wx.CheckBox(panel, label="&VAD filter:")
        self._cb_vad.SetValue(t.vad_filter)
        set_accessible_name(self._cb_vad, "Voice Activity Detection filter")
        set_accessible_help(
            self._cb_vad,
            "Filter out non-speech segments before transcription",
        )
        mg.Add(self._cb_vad, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add((0, 0))

        # VAD threshold
        lbl_vad_thr = wx.StaticText(panel, label="V&AD threshold:")
        self._vad_thr_spin = wx.SpinCtrlDouble(
            panel,
            min=0.0,
            max=1.0,
            inc=0.05,
            initial=t.vad_threshold,
        )
        label_control(lbl_vad_thr, self._vad_thr_spin)
        mg.Add(lbl_vad_thr, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add(self._vad_thr_spin, 0, wx.EXPAND)

        # Compute type
        lbl_compute = wx.StaticText(panel, label="&Compute type:")
        self._compute_ch = wx.Choice(panel, choices=_COMPUTE_TYPES)
        sel_ct = _COMPUTE_TYPES.index(t.compute_type) if t.compute_type in _COMPUTE_TYPES else 0
        self._compute_ch.SetSelection(sel_ct)
        label_control(lbl_compute, self._compute_ch)
        set_accessible_help(
            self._compute_ch,
            "Precision for model inference — auto selects best for your hardware",
        )
        mg.Add(lbl_compute, 0, wx.ALIGN_CENTER_VERTICAL)
        mg.Add(self._compute_ch, 0, wx.EXPAND)

        ms.Add(mg, 0, wx.ALL | wx.EXPAND, 4)
        outer.Add(ms, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 3: Output                                                        #
    # ================================================================== #

    def _build_output_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        o = self._settings.output

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Format & directory ---
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        grid.AddGrowableCol(1, 1)

        lbl_fmt = wx.StaticText(panel, label="Default export &format:")
        self._out_fmt_ch = wx.Choice(
            panel,
            choices=list(EXPORT_FORMATS.values()),
        )
        fmt_keys = list(EXPORT_FORMATS.keys())
        idx = fmt_keys.index(o.default_format) if o.default_format in fmt_keys else 0
        self._out_fmt_ch.SetSelection(idx)
        label_control(lbl_fmt, self._out_fmt_ch)
        grid.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._out_fmt_ch, 0, wx.EXPAND)

        lbl_dir = wx.StaticText(panel, label="Output &directory:")
        dir_row = wx.BoxSizer(wx.HORIZONTAL)
        self._out_dir_txt = wx.TextCtrl(panel, value=o.output_directory)
        label_control(lbl_dir, self._out_dir_txt)
        set_accessible_help(
            self._out_dir_txt,
            "Default folder for saved transcripts",
        )
        btn_browse = wx.Button(panel, label="&Browse…")
        set_accessible_name(btn_browse, "Browse for output directory")
        btn_browse.Bind(
            wx.EVT_BUTTON,
            lambda e: self._browse_dir(self._out_dir_txt),
        )
        dir_row.Add(self._out_dir_txt, 1, wx.RIGHT, 4)
        dir_row.Add(btn_browse, 0)
        grid.Add(lbl_dir, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(dir_row, 1, wx.EXPAND)

        # Auto-export location
        lbl_ae = wx.StaticText(panel, label="Auto-export &location:")
        self._ae_loc_ch = wx.Choice(
            panel,
            choices=[
                "Alongside audio file",
                "Output directory",
                "Custom directory",
            ],
        )
        ae_map = {"alongside": 0, "output_dir": 1, "custom": 2}
        self._ae_loc_ch.SetSelection(
            ae_map.get(o.auto_export_location, 0),
        )
        label_control(lbl_ae, self._ae_loc_ch)
        grid.Add(lbl_ae, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._ae_loc_ch, 0, wx.EXPAND)

        # Custom export dir
        lbl_custom = wx.StaticText(
            panel,
            label="Custom export &folder:",
        )
        custom_row = wx.BoxSizer(wx.HORIZONTAL)
        self._custom_dir_txt = wx.TextCtrl(
            panel,
            value=o.custom_export_dir,
        )
        label_control(lbl_custom, self._custom_dir_txt)
        btn_custom = wx.Button(panel, label="Bro&wse…")
        set_accessible_name(btn_custom, "Browse for custom export folder")
        btn_custom.Bind(
            wx.EVT_BUTTON,
            lambda e: self._browse_dir(self._custom_dir_txt),
        )
        custom_row.Add(self._custom_dir_txt, 1, wx.RIGHT, 4)
        custom_row.Add(btn_custom, 0)
        grid.Add(lbl_custom, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(custom_row, 1, wx.EXPAND)

        # Filename template
        lbl_tpl = wx.StaticText(
            panel,
            label="Filename &template:",
        )
        self._tpl_txt = wx.TextCtrl(panel, value=o.filename_template)
        label_control(lbl_tpl, self._tpl_txt)
        set_accessible_help(
            self._tpl_txt,
            "Use {stem} for filename, {date} for date, " "{provider} for provider name",
        )
        grid.Add(lbl_tpl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._tpl_txt, 1, wx.EXPAND)

        # Encoding
        lbl_enc = wx.StaticText(panel, label="Text &encoding:")
        self._enc_ch = wx.Choice(
            panel,
            choices=["utf-8", "utf-8-sig", "ascii", "latin-1", "utf-16"],
        )
        self._enc_ch.SetStringSelection(o.encoding)
        label_control(lbl_enc, self._enc_ch)
        grid.Add(lbl_enc, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._enc_ch, 0, wx.EXPAND)

        # Line ending
        lbl_le = wx.StaticText(panel, label="Line e&nding:")
        self._le_ch = wx.Choice(
            panel,
            choices=["Auto (OS default)", "LF (Unix)", "CRLF (Windows)"],
        )
        le_map = {"auto": 0, "lf": 1, "crlf": 2}
        self._le_ch.SetSelection(le_map.get(o.line_ending, 0))
        label_control(lbl_le, self._le_ch)
        grid.Add(lbl_le, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._le_ch, 0, wx.EXPAND)

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 12)

        # --- Content toggles ---
        opt_box = wx.StaticBox(panel, label="Content Options")
        set_accessible_name(opt_box, "Content options")
        opts = wx.StaticBoxSizer(opt_box, wx.VERTICAL)

        self._cb_overwrite = wx.CheckBox(
            panel,
            label="&Overwrite existing files",
        )
        self._cb_overwrite.SetValue(o.overwrite_existing)
        set_accessible_name(self._cb_overwrite, "Overwrite existing files")
        set_accessible_help(
            self._cb_overwrite,
            "If unchecked, a numeric suffix is appended to avoid overwrites",
        )
        opts.Add(self._cb_overwrite, 0, wx.ALL, 4)

        self._cb_header = wx.CheckBox(
            panel,
            label="Include file &header",
        )
        self._cb_header.SetValue(o.include_header)
        set_accessible_name(self._cb_header, "Include header")
        set_accessible_help(
            self._cb_header,
            "Add a header line with source file name and date",
        )
        opts.Add(self._cb_header, 0, wx.ALL, 4)

        self._cb_metadata = wx.CheckBox(
            panel,
            label="Include &metadata block",
        )
        self._cb_metadata.SetValue(o.include_metadata)
        set_accessible_name(self._cb_metadata, "Include metadata")
        set_accessible_help(
            self._cb_metadata,
            "Add provider, model, language, and duration info to the output",
        )
        opts.Add(self._cb_metadata, 0, wx.ALL, 4)

        outer.Add(
            opts,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            12,
        )

        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 3b: Playback                                                    #
    # ================================================================== #

    def _build_playback_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        p = self._settings.playback

        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Configure audio preview speed controls used in the Add File Wizard. "
                "These settings affect the playback slider range and step size."
            ),
        )
        intro.Wrap(640)
        set_accessible_name(intro, "Playback settings introduction")
        outer.Add(intro, 0, wx.ALL, 8)

        grid = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        grid.AddGrowableCol(1, 1)

        def _spin(lbl_text, value, min_v, max_v, inc, name, help_text):
            lbl = wx.StaticText(panel, label=lbl_text)
            sp = wx.SpinCtrlDouble(
                panel,
                min=min_v,
                max=max_v,
                inc=inc,
                initial=value,
            )
            sp.SetDigits(2)
            label_control(lbl, sp)
            set_accessible_name(sp, name)
            set_accessible_help(sp, help_text)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(sp, 0, wx.EXPAND)
            return sp

        self._playback_default_speed = _spin(
            "Default &speed:",
            p.default_speed,
            0.25,
            8.0,
            0.05,
            "Default playback speed",
            "Default speed for audio preview playback",
        )
        self._playback_min_speed = _spin(
            "&Minimum speed:",
            p.min_speed,
            0.25,
            8.0,
            0.05,
            "Minimum playback speed",
            "Lowest speed available on the playback slider",
        )
        self._playback_max_speed = _spin(
            "Ma&ximum speed:",
            p.max_speed,
            0.25,
            8.0,
            0.05,
            "Maximum playback speed",
            "Highest speed available on the playback slider",
        )
        self._playback_step = _spin(
            "Speed &step:",
            p.speed_step,
            0.01,
            1.0,
            0.01,
            "Playback speed step",
            "Increment used by the speed step buttons",
        )

        jump_box = wx.StaticBox(panel, label="Jump Timing")
        set_accessible_name(jump_box, "Jump timing")
        jump_sizer = wx.StaticBoxSizer(jump_box, wx.VERTICAL)

        self._jump_back_label = wx.StaticText(panel, label="Back jump: 5 seconds")
        set_accessible_name(self._jump_back_label, "Back jump summary")
        jump_sizer.Add(self._jump_back_label, 0, wx.ALL, 4)

        self._jump_back_slider = wx.Slider(
            panel,
            value=0,
            minValue=0,
            maxValue=len(_JUMP_SECONDS) - 1,
            style=wx.SL_HORIZONTAL | wx.SL_AUTOTICKS,
        )
        set_accessible_name(self._jump_back_slider, "Back jump selector")
        set_accessible_help(
            self._jump_back_slider,
            "Select how many seconds to jump backward during preview playback",
        )
        jump_sizer.Add(self._jump_back_slider, 0, wx.ALL | wx.EXPAND, 4)

        self._jump_forward_label = wx.StaticText(panel, label="Forward jump: 5 seconds")
        set_accessible_name(self._jump_forward_label, "Forward jump summary")
        jump_sizer.Add(self._jump_forward_label, 0, wx.ALL, 4)

        self._jump_forward_slider = wx.Slider(
            panel,
            value=0,
            minValue=0,
            maxValue=len(_JUMP_SECONDS) - 1,
            style=wx.SL_HORIZONTAL | wx.SL_AUTOTICKS,
        )
        set_accessible_name(self._jump_forward_slider, "Forward jump selector")
        set_accessible_help(
            self._jump_forward_slider,
            "Select how many seconds to jump forward during preview playback",
        )
        jump_sizer.Add(self._jump_forward_slider, 0, wx.ALL | wx.EXPAND, 4)

        outer.Add(jump_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

        self._sync_jump_controls(p)

        self._jump_back_slider.Bind(wx.EVT_SLIDER, self._on_jump_slider)
        self._jump_forward_slider.Bind(wx.EVT_SLIDER, self._on_jump_slider)

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 12)

        panel.SetSizer(outer)
        return panel

    def _sync_jump_controls(self, settings: PlaybackSettings) -> None:
        back_idx = self._nearest_jump_index(settings.jump_back_seconds)
        fwd_idx = self._nearest_jump_index(settings.jump_forward_seconds)
        self._jump_back_slider.SetValue(back_idx)
        self._jump_forward_slider.SetValue(fwd_idx)
        self._update_jump_labels()

    def _on_jump_slider(self, _event: wx.CommandEvent) -> None:
        self._update_jump_labels()

    def _update_jump_labels(self) -> None:
        back_val = _JUMP_SECONDS[self._jump_back_slider.GetValue()]
        fwd_val = _JUMP_SECONDS[self._jump_forward_slider.GetValue()]
        self._jump_back_label.SetLabel(f"Back jump: {back_val} seconds")
        self._jump_forward_label.SetLabel(f"Forward jump: {fwd_val} seconds")

    @staticmethod
    def _nearest_jump_index(value: int) -> int:
        closest = min(_JUMP_SECONDS, key=lambda v: abs(v - value))
        return _JUMP_SECONDS.index(closest)

    # ================================================================== #
    # Tab 4: Budget                                                        #
    # ================================================================== #

    def _build_budget_tab(self) -> wx.Panel:
        """Build the spending-limits / budget configuration tab.

        Allows the user to set a master budget toggle, a default limit,
        always-confirm-paid preference, and per-provider dollar limits.
        """
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        b = self._settings.budget

        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Set spending limits for paid transcription providers. "
                "When a transcription's estimated cost exceeds a limit "
                "you will be warned before it is queued."
            ),
        )
        intro.Wrap(640)
        set_accessible_name(intro, "Budget settings introduction")
        outer.Add(intro, 0, wx.ALL, 8)

        # --- Master switches ---
        switches_box = wx.StaticBox(panel, label="Budget Controls")
        set_accessible_name(switches_box, "Budget controls")
        sw_sizer = wx.StaticBoxSizer(switches_box, wx.VERTICAL)

        self._cb_budget_enabled = wx.CheckBox(
            panel,
            label="&Enable spending-limit warnings",
        )
        self._cb_budget_enabled.SetValue(b.enabled)
        set_accessible_name(
            self._cb_budget_enabled,
            "Enable spending limit warnings",
        )
        set_accessible_help(
            self._cb_budget_enabled,
            "When enabled, you will be warned if a transcription " "exceeds your spending limit",
        )
        sw_sizer.Add(self._cb_budget_enabled, 0, wx.ALL, 4)

        self._cb_always_confirm = wx.CheckBox(
            panel,
            label="Always &confirm before using a paid provider",
        )
        self._cb_always_confirm.SetValue(b.always_confirm_paid)
        set_accessible_name(
            self._cb_always_confirm,
            "Always confirm paid provider usage",
        )
        set_accessible_help(
            self._cb_always_confirm,
            "Ask for confirmation every time a paid cloud provider "
            "is selected, even if within budget",
        )
        sw_sizer.Add(self._cb_always_confirm, 0, wx.ALL, 4)

        # Default limit
        def_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_def = wx.StaticText(panel, label="Default spending &limit (USD):")
        self._budget_default_spin = wx.SpinCtrlDouble(
            panel,
            min=0.0,
            max=1000.0,
            inc=0.50,
            initial=b.default_limit_usd,
        )
        self._budget_default_spin.SetDigits(2)
        label_control(lbl_def, self._budget_default_spin)
        set_accessible_help(
            self._budget_default_spin,
            "Default maximum cost in USD for any single transcription "
            "job. Set to 0 for no limit.",
        )
        def_row.Add(lbl_def, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        def_row.Add(self._budget_default_spin, 0)
        sw_sizer.Add(def_row, 0, wx.ALL, 4)

        outer.Add(sw_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        # --- Per-provider limits ---
        prov_box = wx.StaticBox(
            panel,
            label="Per-Provider Spending Limits",
        )
        set_accessible_name(prov_box, "Per-provider spending limits")
        prov_sizer = wx.StaticBoxSizer(prov_box, wx.VERTICAL)

        prov_intro = wx.StaticText(
            panel,
            label=(
                "Set a maximum dollar amount per transcription for each "
                "paid provider. Leave at 0 to use the default limit above."
            ),
        )
        prov_intro.Wrap(600)
        set_accessible_name(prov_intro, "Per-provider limits explanation")
        prov_sizer.Add(prov_intro, 0, wx.ALL, 4)

        # Scrolled area for provider rows
        sw = wx.ScrolledWindow(panel)
        sw.SetScrollRate(0, 10)
        make_panel_accessible(sw)

        grid = wx.FlexGridSizer(cols=3, vgap=6, hgap=10)
        grid.AddGrowableCol(0, 1)

        # Build rows for each paid cloud provider
        self._budget_provider_spins: dict[str, wx.SpinCtrlDouble] = {}
        _paid_providers: list[tuple[str, str]] = [
            ("openai_whisper", "OpenAI Whisper API"),
            ("google_speech", "Google Cloud Speech"),
            ("azure_speech", "Azure Speech"),
            ("deepgram", "Deepgram Nova-2"),
            ("assemblyai", "AssemblyAI"),
            ("gemini", "Google Gemini"),
            ("aws_transcribe", "Amazon Transcribe"),
            ("groq_whisper", "Groq Whisper"),
            ("rev_ai", "Rev.ai"),
            ("speechmatics", "Speechmatics"),
            ("elevenlabs", "ElevenLabs Scribe"),
            ("auphonic", "Auphonic"),
        ]

        for pkey, pname in _paid_providers:
            lbl = wx.StaticText(sw, label=f"{pname}:")
            current_limit = b.provider_limits.get(pkey, 0.0)
            spin = wx.SpinCtrlDouble(
                sw,
                min=0.0,
                max=1000.0,
                inc=0.50,
                initial=current_limit,
            )
            spin.SetDigits(2)
            label_control(lbl, spin)
            set_accessible_help(
                spin,
                f"Maximum cost in USD per transcription for {pname}. " f"0 = use default limit.",
            )
            unit = wx.StaticText(sw, label="USD")
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(spin, 0)
            grid.Add(unit, 0, wx.ALIGN_CENTER_VERTICAL)
            self._budget_provider_spins[pkey] = spin

        sw.SetSizer(grid)
        prov_sizer.Add(sw, 1, wx.ALL | wx.EXPAND, 4)
        outer.Add(
            prov_sizer,
            1,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            8,
        )

        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 5: Providers & Keys                                              #
    # ================================================================== #

    def _build_providers_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Enter API keys for cloud transcription providers. "
                "Keys are stored securely in your system's credential "
                "manager — never in plain text on disk. "
                "Use the Test button to verify each key works."
            ),
        )
        intro.Wrap(640)
        set_accessible_name(intro, "Provider keys introduction")
        sizer.Add(intro, 0, wx.ALL, 8)

        # Scrolled window for many providers
        sw = wx.ScrolledWindow(panel)
        sw.SetScrollRate(0, 10)
        make_panel_accessible(sw)

        providers = KeyStore.get_supported_providers()
        self._key_fields: dict[str, wx.TextCtrl] = {}
        self._key_status_labels: dict[str, wx.StaticText] = {}
        self._key_test_btns: dict[str, wx.Button] = {}

        grid = wx.FlexGridSizer(cols=4, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        for pid, pname in providers.items():
            lbl = wx.StaticText(sw, label=f"{pname}:")
            txt = wx.TextCtrl(sw, style=wx.TE_PASSWORD, size=(220, -1))
            label_control(lbl, txt)
            set_accessible_help(
                txt,
                f"Enter your {pname}. Leave blank to disable.",
            )

            existing = self._key_store.get_key(pid)
            if existing:
                txt.SetValue("\u2022" * 8)
                txt.SetModified(False)

            # Test button — only for primary keys that have a provider mapping
            if pid in _KEYSTORE_TO_PROVIDER:
                test_btn = wx.Button(sw, label="Te&st", size=(60, -1))
                set_accessible_name(test_btn, f"Test {pname}")
                set_accessible_help(
                    test_btn,
                    f"Validate your {pname} by making a test API call",
                )
                test_btn.Bind(
                    wx.EVT_BUTTON,
                    lambda e, p=pid, n=pname: self._on_test_key(p, n),
                )
                self._key_test_btns[pid] = test_btn
            else:
                # Auxiliary keys (aws_secret_key, aws_region, azure_region)
                test_btn = wx.StaticText(sw, label="")
                test_btn.SetMinSize((60, -1))

            status = wx.StaticText(
                sw,
                label="\u2713 Saved" if existing else "Not set",
            )
            set_accessible_name(status, f"{pname} status")
            self._key_status_labels[pid] = status

            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(txt, 1, wx.EXPAND)
            grid.Add(test_btn, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(status, 0, wx.ALIGN_CENTER_VERTICAL)
            self._key_fields[pid] = txt

        sw.SetSizer(grid)
        sizer.Add(sw, 1, wx.ALL | wx.EXPAND, 8)
        panel.SetSizer(sizer)
        return panel

    # ================================================================== #
    # Tab 5: Paths & Storage                                               #
    # ================================================================== #

    def _build_paths_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        p = self._settings.paths

        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        grid.AddGrowableCol(1, 1)

        def _dir_row(label_text, value, help_text):
            lbl = wx.StaticText(panel, label=label_text)
            row = wx.BoxSizer(wx.HORIZONTAL)
            txt = wx.TextCtrl(panel, value=value)
            label_control(lbl, txt)
            set_accessible_help(txt, help_text)
            btn = wx.Button(panel, label="Browse…")
            set_accessible_name(btn, f"Browse for {label_text}")
            btn.Bind(
                wx.EVT_BUTTON,
                lambda e, t=txt: self._browse_dir(t),
            )
            row.Add(txt, 1, wx.RIGHT, 4)
            row.Add(btn, 0)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(row, 1, wx.EXPAND)
            return txt

        self._path_output = _dir_row(
            "&Transcript output folder:",
            p.output_directory,
            "Default folder where transcripts are saved",
        )
        self._path_models = _dir_row(
            "&Models folder:",
            p.models_directory,
            "Folder for downloaded Whisper model files",
        )
        self._path_temp = _dir_row(
            "Te&mporary files folder:",
            p.temp_directory or "(system default)",
            "Folder for temporary transcoding files — leave blank for system default",
        )
        self._path_log = _dir_row(
            "&Log file location:",
            p.log_file,
            "Path to the application log file",
        )

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 12)

        # Open-in-Explorer buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_open_data = wx.Button(
            panel,
            label="Open &Data Folder",
        )
        set_accessible_name(btn_open_data, "Open data folder")
        set_accessible_help(
            btn_open_data,
            "Open the application data directory in File Explorer",
        )
        btn_open_data.Bind(wx.EVT_BUTTON, self._on_open_data_dir)
        btn_row.Add(btn_open_data, 0, wx.RIGHT, 8)

        btn_open_models = wx.Button(
            panel,
            label="Open &Models Folder",
        )
        set_accessible_name(btn_open_models, "Open models folder")
        btn_open_models.Bind(wx.EVT_BUTTON, self._on_open_models_dir)
        btn_row.Add(btn_open_models, 0)

        outer.Add(btn_row, 0, wx.LEFT | wx.BOTTOM, 12)

        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 6: Audio Processing (Advanced)                                   #
    # ================================================================== #

    def _build_audio_processing_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        a = self._settings.audio_processing

        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Configure audio preprocessing filters applied before "
                "transcription. These filters can significantly improve "
                "accuracy for noisy or low-quality recordings."
            ),
        )
        intro.Wrap(640)
        set_accessible_name(intro, "Audio processing introduction")
        outer.Add(intro, 0, wx.ALL, 8)

        # Master toggle
        self._cb_pp_enabled = wx.CheckBox(
            panel,
            label="&Enable audio preprocessing",
        )
        self._cb_pp_enabled.SetValue(a.enabled)
        set_accessible_name(
            self._cb_pp_enabled,
            "Enable audio preprocessing",
        )
        set_accessible_help(
            self._cb_pp_enabled,
            "When enabled, audio is cleaned up before transcription",
        )
        outer.Add(self._cb_pp_enabled, 0, wx.ALL, 8)

        # Filters with parameter controls
        sw = wx.ScrolledWindow(panel)
        sw.SetScrollRate(0, 10)
        make_panel_accessible(sw)
        fg = wx.FlexGridSizer(cols=3, vgap=6, hgap=8)
        fg.AddGrowableCol(2, 1)

        def _filter_row(lbl_text, enabled, name, value=None, unit="", min_v=0, max_v=20000):
            cb = wx.CheckBox(sw, label=lbl_text)
            cb.SetValue(enabled)
            set_accessible_name(cb, name)
            fg.Add(cb, 0, wx.ALIGN_CENTER_VERTICAL)
            if value is not None:
                spin = wx.SpinCtrl(
                    sw,
                    min=min_v,
                    max=max_v,
                    initial=int(value),
                )
                set_accessible_name(spin, f"{name} value")
                fg.Add(spin, 0, wx.EXPAND)
                unit_lbl = wx.StaticText(sw, label=unit)
                fg.Add(unit_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
                return cb, spin
            fg.Add((0, 0))
            fg.Add((0, 0))
            return cb, None

        self._f_hp_cb, self._f_hp_val = _filter_row(
            "&High-pass filter",
            a.highpass_enabled,
            "High-pass filter",
            a.highpass_freq,
            "Hz",
            min_v=20,
            max_v=500,
        )
        self._f_lp_cb, self._f_lp_val = _filter_row(
            "&Low-pass filter",
            a.lowpass_enabled,
            "Low-pass filter",
            a.lowpass_freq,
            "Hz",
            min_v=2000,
            max_v=20000,
        )
        self._f_ng_cb, self._f_ng_val = _filter_row(
            "&Noise gate",
            a.noise_gate_enabled,
            "Noise gate",
            int(a.noise_gate_threshold_db),
            "dB",
            min_v=-80,
            max_v=0,
        )
        self._f_de_cb, self._f_de_val = _filter_row(
            "&De-esser",
            a.deesser_enabled,
            "De-esser",
            a.deesser_freq,
            "Hz",
            min_v=1000,
            max_v=12000,
        )
        self._f_comp_cb, self._f_comp_val = _filter_row(
            "&Compressor",
            a.compressor_enabled,
            "Compressor",
            int(a.compressor_threshold_db),
            "dB",
            min_v=-60,
            max_v=0,
        )
        self._f_ln_cb, self._f_ln_val = _filter_row(
            "Loud&norm (EBU R128)",
            a.loudnorm_enabled,
            "Loudness normalization",
            int(a.loudnorm_target_i),
            "LUFS",
            min_v=-30,
            max_v=-5,
        )
        self._f_trim_cb, _ = _filter_row(
            "&Trim leading/trailing silence",
            a.trim_silence_enabled,
            "Trim silence",
        )

        sw.SetSizer(fg)
        outer.Add(sw, 1, wx.ALL | wx.EXPAND, 8)
        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # Tab 7: Advanced                                                      #
    # ================================================================== #

    def _build_advanced_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        make_panel_accessible(panel)
        v = self._settings.advanced

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Limits ---
        lim_box = wx.StaticBox(panel, label="File && Batch Limits")
        set_accessible_name(lim_box, "File and batch limits")
        lg = wx.StaticBoxSizer(lim_box, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        grid.AddGrowableCol(1, 1)

        def _spin(lbl_text, value, min_v, max_v, hlp):
            lbl = wx.StaticText(panel, label=lbl_text)
            sp = wx.SpinCtrl(
                panel,
                min=min_v,
                max=max_v,
                initial=value,
            )
            label_control(lbl, sp)
            set_accessible_help(sp, hlp)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(sp, 0, wx.EXPAND)
            return sp

        self._sp_max_file = _spin(
            "Max file size (&MB):",
            v.max_file_size_mb,
            10,
            5000,
            "Maximum individual file size in megabytes",
        )
        self._sp_max_batch = _spin(
            "Max files per &batch:",
            v.max_batch_files,
            1,
            1000,
            "Maximum number of files in a single batch",
        )
        self._sp_concurrent = _spin(
            "Concurrent &jobs:",
            v.max_concurrent_jobs,
            1,
            16,
            "Number of jobs to process simultaneously",
        )
        self._sp_chunk = _spin(
            "Chunk length (m&inutes):",
            v.chunk_minutes,
            1,
            120,
            "Length of audio chunks for long files",
        )
        self._sp_overlap = _spin(
            "Chunk &overlap (seconds):",
            v.chunk_overlap_seconds,
            0,
            30,
            "Overlap between chunks to avoid losing words",
        )
        lg.Add(grid, 0, wx.ALL | wx.EXPAND, 4)
        outer.Add(lg, 0, wx.ALL | wx.EXPAND, 8)

        # --- Processing ---
        proc_box = wx.StaticBox(panel, label="Processing")
        set_accessible_name(proc_box, "Processing settings")
        ps = wx.StaticBoxSizer(proc_box, wx.VERTICAL)
        pg = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        pg.AddGrowableCol(1, 1)

        self._cb_background = wx.CheckBox(
            panel,
            label="Enable &background processing",
        )
        self._cb_background.SetValue(v.background_processing)
        set_accessible_name(
            self._cb_background,
            "Background processing",
        )
        set_accessible_help(
            self._cb_background,
            "Continue transcribing when the window is hidden to tray",
        )
        pg.Add(self._cb_background, 0, wx.ALIGN_CENTER_VERTICAL)
        pg.Add((0, 0))

        lbl_gpu = wx.StaticText(panel, label="&GPU device index:")
        self._sp_gpu = wx.SpinCtrl(
            panel,
            min=0,
            max=7,
            initial=v.gpu_device_index,
        )
        label_control(lbl_gpu, self._sp_gpu)
        set_accessible_help(
            self._sp_gpu,
            "Which GPU to use (0 = first GPU, 1 = second, etc.)",
        )
        pg.Add(lbl_gpu, 0, wx.ALIGN_CENTER_VERTICAL)
        pg.Add(self._sp_gpu, 0, wx.EXPAND)

        lbl_cpu = wx.StaticText(panel, label="CPU &threads:")
        self._sp_cpu = wx.SpinCtrl(
            panel,
            min=0,
            max=64,
            initial=v.cpu_threads,
        )
        label_control(lbl_cpu, self._sp_cpu)
        set_accessible_help(
            self._sp_cpu,
            "Number of CPU threads (0 = auto-detect)",
        )
        pg.Add(lbl_cpu, 0, wx.ALIGN_CENTER_VERTICAL)
        pg.Add(self._sp_cpu, 0, wx.EXPAND)

        lbl_log = wx.StaticText(panel, label="&Log level:")
        self._log_ch = wx.Choice(panel, choices=_LOG_LEVELS)
        sel_ll = _LOG_LEVELS.index(v.log_level) if v.log_level in _LOG_LEVELS else 1
        self._log_ch.SetSelection(sel_ll)
        label_control(lbl_log, self._log_ch)
        pg.Add(lbl_log, 0, wx.ALIGN_CENTER_VERTICAL)
        pg.Add(self._log_ch, 0, wx.EXPAND)

        ps.Add(pg, 0, wx.ALL | wx.EXPAND, 4)
        outer.Add(ps, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        panel.SetSizer(outer)
        return panel

    # ================================================================== #
    # API key validation                                                   #
    # ================================================================== #

    def _on_test_key(self, pid: str, pname: str) -> None:
        """Test an API key by calling the provider's validate_api_key method.

        For multi-key providers (AWS, Azure), the auxiliary keys are
        combined automatically from the key fields.

        Args:
            pid: KeyStore provider identifier (e.g. "openai").
            pname: Human-readable provider name for status messages.
        """
        # Get the key value — use entered text, or fall back to stored key
        txt = self._key_fields.get(pid)
        if not txt:
            return
        raw = txt.GetValue().strip()
        if not raw or raw == "\u2022" * 8:
            # Try using the stored key
            raw = self._key_store.get_key(pid) or ""
        if not raw:
            self._set_key_status(pid, "\u2717 No key entered")
            return

        provider_key = _KEYSTORE_TO_PROVIDER.get(pid)
        if not provider_key:
            return

        # Build the validation key string
        api_key = raw
        if pid == "aws_access_key":
            # AWS needs ACCESS_KEY:SECRET_KEY:REGION
            secret = self._get_field_value("aws_secret_key")
            region = self._get_field_value("aws_region")
            if not secret or not region:
                self._set_key_status(pid, "\u2717 Enter Secret Key and Region too")
                return
            api_key = f"{raw}:{secret}:{region}"

        # Disable the test button during validation
        btn = self._key_test_btns.get(pid)
        if btn:
            btn.Disable()
        self._set_key_status(pid, "\u2026 Testing\u2026")

        def _validate() -> None:
            try:
                from bits_whisperer.core.provider_manager import ProviderManager

                pm = ProviderManager()

                # For Azure, construct provider with the entered region
                if pid == "azure":
                    from bits_whisperer.providers.azure_speech import AzureSpeechProvider

                    region = self._get_field_value("azure_region") or "eastus"
                    provider = AzureSpeechProvider(region=region)
                else:
                    provider = pm.get_provider(provider_key)  # type: ignore[assignment]

                if provider is None:
                    safe_call_after(
                        self._on_test_result, pid, pname, False, "Provider SDK not installed"
                    )
                    return

                result = provider.validate_api_key(api_key)
                safe_call_after(self._on_test_result, pid, pname, result, "")
            except Exception as exc:
                safe_call_after(self._on_test_result, pid, pname, False, str(exc))

        threading.Thread(target=_validate, daemon=True, name=f"test-{pid}").start()

    def _on_test_result(self, pid: str, pname: str, success: bool, error: str) -> None:
        """Handle API key validation result on the UI thread.

        Args:
            pid: Provider identifier.
            pname: Human-readable provider name.
            success: Whether the key validated successfully.
            error: Error message if validation failed.
        """
        btn = self._key_test_btns.get(pid)
        if btn:
            btn.Enable()

        if success:
            self._set_key_status(pid, "\u2713 Valid")
            logger.info("API key for %s validated successfully", pname)
        else:
            detail = f": {error}" if error else ""
            self._set_key_status(pid, f"\u2717 Failed{detail}")
            logger.warning("API key validation failed for %s%s", pname, detail)

    def _set_key_status(self, pid: str, text: str) -> None:
        """Update the status label for a provider key.

        Args:
            pid: Provider identifier.
            text: Status text to display.
        """
        lbl = self._key_status_labels.get(pid)
        if lbl:
            lbl.SetLabel(text)
            lbl.GetParent().Layout()

    def _get_field_value(self, pid: str) -> str:
        """Get the current value from a key field, falling back to stored key.

        Args:
            pid: Provider identifier.

        Returns:
            The key value, or empty string.
        """
        txt = self._key_fields.get(pid)
        if not txt:
            return ""
        raw = txt.GetValue().strip()
        if not raw or raw == "\u2022" * 8:
            return self._key_store.get_key(pid) or ""
        return str(raw)

    # ================================================================== #
    # Directory browser helper                                             #
    # ================================================================== #

    @staticmethod
    def _browse_dir(text_ctrl: wx.TextCtrl) -> None:
        """Show a directory picker and set the text control value."""
        current = text_ctrl.GetValue()
        dlg = wx.DirDialog(
            text_ctrl.GetTopLevelParent(),
            "Choose a directory",
            defaultPath=current if Path(current).is_dir() else "",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            text_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_open_data_dir(self, _event: wx.CommandEvent) -> None:
        """Open the application data directory in the file manager."""
        from bits_whisperer.utils.constants import DATA_DIR
        from bits_whisperer.utils.platform_utils import open_file_or_folder

        open_file_or_folder(DATA_DIR)

    def _on_open_models_dir(self, _event: wx.CommandEvent) -> None:
        """Open the models directory in the file manager."""
        from bits_whisperer.utils.platform_utils import open_file_or_folder

        path = self._path_models.GetValue()
        if Path(path).is_dir():
            open_file_or_folder(path)

    # ================================================================== #
    # Collect values from all tabs                                         #
    # ================================================================== #

    def _collect_settings(self) -> AppSettings:
        """Read all controls and return a populated AppSettings."""
        s = self._settings

        # --- General ---
        g = s.general
        lang_sel = self._lang_ch.GetStringSelection()
        g.language = "auto" if lang_sel == "Auto-detect" else lang_sel
        prov_sel = self._provider_ch.GetSelection()
        if 0 <= prov_sel < len(self._provider_keys):
            g.default_provider = self._provider_keys[prov_sel]
        g.prefer_local = self._cb_prefer_local.GetValue()
        g.minimize_to_tray = self._cb_minimize_tray.GetValue()
        g.auto_export = self._cb_auto_export.GetValue()
        g.show_notifications = self._cb_notification.GetValue()
        g.play_sound = self._cb_sound.GetValue()
        g.start_minimized = self._cb_start_minimized.GetValue()
        g.check_updates_on_start = self._cb_check_updates.GetValue()
        g.confirm_before_quit = self._cb_confirm_quit.GetValue()
        g.restore_queue_on_start = self._cb_restore_queue.GetValue()

        # --- Transcription ---
        t = s.transcription
        t.include_timestamps = self._cb_timestamps.GetValue()
        t.timestamp_format = _TS_FORMATS[self._ts_fmt_ch.GetSelection()]
        t.include_speakers = self._cb_speakers.GetValue()
        t.include_confidence = self._cb_confidence.GetValue()
        t.include_language_tag = self._cb_lang_tag.GetValue()
        t.include_word_level = self._cb_word_level.GetValue()
        t.paragraph_segmentation = self._cb_paragraphs.GetValue()
        t.merge_short_segments = self._cb_merge_short.GetValue()
        t.prompt = self._prompt_txt.GetValue()
        t.temperature = self._temp_spin.GetValue()
        t.beam_size = self._beam_spin.GetValue()
        t.vad_filter = self._cb_vad.GetValue()
        t.vad_threshold = self._vad_thr_spin.GetValue()
        t.compute_type = _COMPUTE_TYPES[self._compute_ch.GetSelection()]

        # --- Output ---
        o = s.output
        fmt_keys = list(EXPORT_FORMATS.keys())
        o.default_format = fmt_keys[self._out_fmt_ch.GetSelection()]
        o.output_directory = self._out_dir_txt.GetValue()
        ae_map = {0: "alongside", 1: "output_dir", 2: "custom"}
        o.auto_export_location = ae_map.get(
            self._ae_loc_ch.GetSelection(),
            "alongside",
        )
        o.custom_export_dir = self._custom_dir_txt.GetValue()
        o.filename_template = self._tpl_txt.GetValue()
        o.encoding = self._enc_ch.GetStringSelection()
        le_map = {0: "auto", 1: "lf", 2: "crlf"}
        o.line_ending = le_map.get(self._le_ch.GetSelection(), "auto")
        o.overwrite_existing = self._cb_overwrite.GetValue()
        o.include_header = self._cb_header.GetValue()
        o.include_metadata = self._cb_metadata.GetValue()

        # --- Playback ---
        pb = s.playback
        pb.default_speed = self._playback_default_speed.GetValue()
        pb.min_speed = self._playback_min_speed.GetValue()
        pb.max_speed = self._playback_max_speed.GetValue()
        pb.speed_step = self._playback_step.GetValue()
        pb.jump_back_seconds = _JUMP_SECONDS[self._jump_back_slider.GetValue()]
        pb.jump_forward_seconds = _JUMP_SECONDS[self._jump_forward_slider.GetValue()]

        if pb.max_speed < pb.min_speed:
            pb.max_speed = pb.min_speed
        if pb.default_speed < pb.min_speed:
            pb.default_speed = pb.min_speed
        if pb.default_speed > pb.max_speed:
            pb.default_speed = pb.max_speed

        # --- Paths ---
        p = s.paths
        p.output_directory = self._path_output.GetValue()
        p.models_directory = self._path_models.GetValue()
        temp_val = self._path_temp.GetValue()
        p.temp_directory = "" if temp_val == "(system default)" else temp_val
        p.log_file = self._path_log.GetValue()

        # --- Budget ---
        bgt = s.budget
        bgt.enabled = self._cb_budget_enabled.GetValue()
        bgt.always_confirm_paid = self._cb_always_confirm.GetValue()
        bgt.default_limit_usd = self._budget_default_spin.GetValue()
        new_limits: dict[str, float] = {}
        for pkey, spin in self._budget_provider_spins.items():
            val = spin.GetValue()
            if val > 0:
                new_limits[pkey] = val
        bgt.provider_limits = new_limits

        # --- Audio Processing (only if controls exist) ---
        a = s.audio_processing
        a.enabled = self._cb_pp_enabled.GetValue()
        a.highpass_enabled = self._f_hp_cb.GetValue()
        if self._f_hp_val:
            a.highpass_freq = self._f_hp_val.GetValue()
        a.lowpass_enabled = self._f_lp_cb.GetValue()
        if self._f_lp_val:
            a.lowpass_freq = self._f_lp_val.GetValue()
        a.noise_gate_enabled = self._f_ng_cb.GetValue()
        if self._f_ng_val:
            a.noise_gate_threshold_db = float(self._f_ng_val.GetValue())
        a.deesser_enabled = self._f_de_cb.GetValue()
        if self._f_de_val:
            a.deesser_freq = self._f_de_val.GetValue()
        a.compressor_enabled = self._f_comp_cb.GetValue()
        if self._f_comp_val:
            a.compressor_threshold_db = float(self._f_comp_val.GetValue())
        a.loudnorm_enabled = self._f_ln_cb.GetValue()
        if self._f_ln_val:
            a.loudnorm_target_i = float(self._f_ln_val.GetValue())
        a.trim_silence_enabled = self._f_trim_cb.GetValue()

        # --- Advanced ---
        v = s.advanced
        v.max_file_size_mb = self._sp_max_file.GetValue()
        v.max_batch_files = self._sp_max_batch.GetValue()
        v.max_concurrent_jobs = self._sp_concurrent.GetValue()
        v.chunk_minutes = self._sp_chunk.GetValue()
        v.chunk_overlap_seconds = self._sp_overlap.GetValue()
        v.background_processing = self._cb_background.GetValue()
        v.gpu_device_index = self._sp_gpu.GetValue()
        v.cpu_threads = self._sp_cpu.GetValue()
        v.log_level = _LOG_LEVELS[self._log_ch.GetSelection()]

        return s

    # ================================================================== #
    # Apply settings to the running application                            #
    # ================================================================== #

    def _apply_to_app(self, settings: AppSettings) -> None:
        """Push settings values into the live application state."""
        mf = self._main_frame

        # Save registration key
        reg_key = self._reg_key_txt.GetValue().strip()
        if reg_key != self._key_store.get_key("registration_key"):
            self._key_store.store_key("registration_key", reg_key)
            # Re-verify in background when key is changed
            threading.Thread(target=mf.registration_service.verify_key, daemon=True).start()

        # General / behaviour flags
        mf._minimize_to_tray = settings.general.minimize_to_tray
        mf._auto_export = settings.general.auto_export

        # Sync View menu check items
        if hasattr(mf, "_minimize_tray_item"):
            mf._minimize_tray_item.Check(mf._minimize_to_tray)
        if hasattr(mf, "_auto_export_item"):
            mf._auto_export_item.Check(mf._auto_export)

        # Audio preprocessing
        svc = getattr(mf, "transcription_service", None)
        if svc and hasattr(svc, "_preprocessor"):
            ap = settings.audio_processing
            pp = PreprocessorSettings(
                enabled=ap.enabled,
                highpass_enabled=ap.highpass_enabled,
                highpass_freq=ap.highpass_freq,
                lowpass_enabled=ap.lowpass_enabled,
                lowpass_freq=ap.lowpass_freq,
                noise_gate_enabled=ap.noise_gate_enabled,
                noise_gate_threshold_db=ap.noise_gate_threshold_db,
                deesser_enabled=ap.deesser_enabled,
                deesser_freq=ap.deesser_freq,
                compressor_enabled=ap.compressor_enabled,
                compressor_threshold_db=ap.compressor_threshold_db,
                compressor_ratio=ap.compressor_ratio,
                compressor_attack_ms=ap.compressor_attack_ms,
                compressor_release_ms=ap.compressor_release_ms,
                loudnorm_enabled=ap.loudnorm_enabled,
                loudnorm_target_i=ap.loudnorm_target_i,
                loudnorm_target_tp=ap.loudnorm_target_tp,
                loudnorm_target_lra=ap.loudnorm_target_lra,
                trim_silence_enabled=ap.trim_silence_enabled,
                silence_threshold_db=ap.silence_threshold_db,
                silence_duration_s=ap.silence_duration_s,
            )
            svc._preprocessor.settings = pp
            logger.info("Applied audio preprocessing settings")

        # Save API keys
        for pid, txt in self._key_fields.items():
            if txt.IsModified():
                value = txt.GetValue().strip()
                if value and value != "\u2022" * 8:
                    self._key_store.store_key(pid, value)
                    logger.info("Saved API key for %s", pid)

        # Persist settings and store on MainFrame
        settings.save()
        mf.app_settings = settings
        logger.info("Settings applied and saved")

    # ================================================================== #
    # Button handlers                                                      #
    # ================================================================== #

    def _on_verify_reg_key(self, _event: wx.CommandEvent) -> None:
        """Verify the registration key immediately."""
        key = self._reg_key_txt.GetValue().strip()
        if not key:
            wx.MessageBox("Please enter a registration key.", "Error", wx.OK | wx.ICON_ERROR)
            return

        self._key_store.store_key("registration_key", key)
        if self._main_frame.registration_service.verify_key():
            msg = self._main_frame.registration_service.get_status_message()
            self._reg_status_lbl.SetLabel(f"Status: {msg}")
            self._main_frame._update_window_title()
            wx.MessageBox(
                f"Key verified successfully!\n{msg}",
                "Success",
                wx.OK | wx.ICON_INFORMATION,
            )
        else:
            self._reg_status_lbl.SetLabel("Status: Verification Failed")
            wx.MessageBox(
                "Key verification failed. Please check your key or internet connection.",
                "Error",
                wx.OK | wx.ICON_ERROR,
            )

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Save settings and close."""
        settings = self._collect_settings()
        self._apply_to_app(settings)
        announce_status(self._main_frame, "Settings saved")
        self.EndModal(wx.ID_OK)

    def _on_apply(self, _event: wx.CommandEvent) -> None:
        """Save settings without closing."""
        settings = self._collect_settings()
        self._apply_to_app(settings)
        announce_status(self._main_frame, "Settings applied")

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        """Discard changes and close."""
        self.EndModal(wx.ID_CANCEL)
