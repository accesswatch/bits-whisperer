"""Add File to Transcribe — guided file-addition wizard.

A two-step dialog:
1. Choose one or more audio files (standard file picker).
2. Configure provider, model, language, and options on a single page.

All jobs created here receive the user-chosen settings and are enqueued
into the main queue panel.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.job import Job
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    label_control,
    make_panel_accessible,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import DATA_DIR, WHISPER_MODELS

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Common languages for the language picker
_COMMON_LANGUAGES: list[tuple[str, str]] = [
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
    ("tr", "Turkish"),
    ("vi", "Vietnamese"),
    ("th", "Thai"),
]


def get_models_for_provider(provider_key: str) -> list[tuple[str, str]]:
    """Return a list of ``(model_id, display_label)`` pairs for *provider_key*.

    Args:
        provider_key: Provider identifier (e.g. ``local_whisper``).

    Returns:
        List of ``(id, label)`` tuples.  Empty list means the provider
        only has a single implicit model.
    """
    if provider_key in ("local_whisper",):
        return [(m.id, f"{m.name} — {m.description[:60]}") for m in WHISPER_MODELS]
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


class AddFileWizard(wx.Dialog):
    """Two-step guided dialog for files and transcription.

    After the user clicks *Add to Queue*, the dialog stores the
    configured :class:`list[Job]` in :attr:`result_jobs` and returns
    ``wx.ID_OK``.
    """

    def __init__(
        self,
        parent: wx.Window,
        main_frame: MainFrame,
        paths: list[str],
    ) -> None:
        """Initialise the add-file wizard."""
        super().__init__(
            parent,
            title="Add Files to Transcribe",
            size=(580, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Add files to transcribe dialog")
        self.SetMinSize((480, 420))
        self.Centre()

        self._main_frame = main_frame
        self._paths = paths
        self.result_jobs: list[Job] = []
        self._clip_start: float | None = None
        self._clip_end: float | None = None

        self._build_ui()
        self._apply_defaults()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)

        # ---- File summary ----
        file_count = len(self._paths)
        if file_count == 1:
            summary = f"File: {Path(self._paths[0]).name}"
        else:
            summary = f"{file_count} files selected"
        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(summary_label.GetFont().Bold())
        set_accessible_name(summary_label, summary)
        root.Add(summary_label, 0, wx.ALL, 12)

        if file_count > 1:
            names = ", ".join(Path(p).name for p in self._paths[:5])
            if file_count > 5:
                names += f", … and {file_count - 5} more"
            detail = wx.StaticText(self, label=names)
            detail.SetForegroundColour(
                wx.SystemSettings.GetColour(
                    wx.SYS_COLOUR_GRAYTEXT,
                ),
            )
            set_accessible_name(detail, f"Files: {names}")
            root.Add(detail, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # ---- Audio preview ----
        preview_box = wx.StaticBox(self, label="Audio Preview")
        set_accessible_name(preview_box, "Audio preview")
        preview_sizer = wx.StaticBoxSizer(preview_box, wx.VERTICAL)

        self._preview_label = wx.StaticText(self, label="Selection: full file")
        set_accessible_name(self._preview_label, "Preview selection summary")
        preview_sizer.Add(self._preview_label, 0, wx.ALL, 4)

        self._preview_btn = wx.Button(self, label="&Preview / Select Range…")
        set_accessible_name(self._preview_btn, "Preview audio and select range")
        set_accessible_help(
            self._preview_btn,
            "Listen to the audio and optionally select a time range to transcribe",
        )
        preview_sizer.Add(self._preview_btn, 0, wx.ALL, 4)

        if file_count > 1:
            hint = wx.StaticText(
                self,
                label="Preview is available for single-file imports only.",
            )
            hint.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            set_accessible_name(hint, "Preview availability hint")
            preview_sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
            self._preview_btn.Enable(False)

        root.Add(preview_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- Settings panel (scrollable for small screens) ----
        settings_panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(settings_panel)
        sp_sizer = wx.BoxSizer(wx.VERTICAL)

        heading = wx.StaticText(settings_panel, label="Transcription Settings")
        heading.SetFont(heading.GetFont().Bold())
        set_accessible_name(heading, "Transcription settings")
        sp_sizer.Add(heading, 0, wx.ALL, 8)

        grid = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        grid.AddGrowableCol(1, 1)

        # -- Provider --
        prov_lbl = wx.StaticText(settings_panel, label="&Provider:")
        self._provider_choice = wx.Choice(settings_panel)
        set_accessible_name(self._provider_choice, "Transcription provider")
        set_accessible_help(
            self._provider_choice,
            "Select which transcription engine to use. "
            "Local providers are free; cloud providers need an API key.",
        )
        label_control(prov_lbl, self._provider_choice)
        grid.Add(prov_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._provider_choice, 1, wx.EXPAND)

        # -- Model --
        model_lbl = wx.StaticText(settings_panel, label="&Model:")
        self._model_choice = wx.Choice(settings_panel)
        set_accessible_name(self._model_choice, "AI model")
        set_accessible_help(
            self._model_choice,
            "Choose the AI model. Larger models are more accurate but slower.",
        )
        label_control(model_lbl, self._model_choice)
        grid.Add(model_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._model_choice, 1, wx.EXPAND)

        # -- Language --
        lang_lbl = wx.StaticText(settings_panel, label="&Language:")
        self._language_choice = wx.Choice(settings_panel)
        set_accessible_name(self._language_choice, "Audio language")
        set_accessible_help(
            self._language_choice,
            "Select the language spoken in the audio. " "Auto-Detect works for most files.",
        )
        label_control(lang_lbl, self._language_choice)
        grid.Add(lang_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._language_choice, 1, wx.EXPAND)

        sp_sizer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sp_sizer.AddSpacer(8)

        # -- Custom name --
        name_box = wx.StaticBox(settings_panel, label="Custom Name (optional)")
        set_accessible_name(name_box, "Custom name for this transcription run")
        name_sizer = wx.StaticBoxSizer(name_box, wx.VERTICAL)

        self._custom_name_input = wx.TextCtrl(settings_panel)
        set_accessible_name(self._custom_name_input, "Custom name")
        set_accessible_help(
            self._custom_name_input,
            "Give this transcription a custom name. "
            "It will appear in the queue instead of the file name. "
            "Leave blank to use the original file name.",
        )
        name_sizer.Add(self._custom_name_input, 0, wx.EXPAND | wx.ALL, 4)

        name_hint = wx.StaticText(
            settings_panel,
            label="Appears in the queue tree view instead of the file name.",
        )
        name_hint.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        set_accessible_name(name_hint, "Custom name hint")
        name_sizer.Add(name_hint, 0, wx.LEFT | wx.BOTTOM, 4)

        sp_sizer.Add(name_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # -- AI Action (post-transcription) --
        action_box = wx.StaticBox(settings_panel, label="AI Action (after transcription)")
        set_accessible_name(action_box, "AI action to run after transcription completes")
        action_sizer = wx.StaticBoxSizer(action_box, wx.VERTICAL)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        action_lbl = wx.StaticText(settings_panel, label="A&ction:")
        self._ai_action_choice = wx.Choice(settings_panel)
        set_accessible_name(self._ai_action_choice, "AI action template")
        set_accessible_help(
            self._ai_action_choice,
            "Select an AI action to run automatically after transcription. "
            "For example, generate meeting minutes, extract action items, "
            "or create a summary. Requires an AI provider to be configured.",
        )
        label_control(action_lbl, self._ai_action_choice)
        action_row.Add(action_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        action_row.Add(self._ai_action_choice, 1, wx.EXPAND)
        action_sizer.Add(action_row, 0, wx.EXPAND | wx.ALL, 4)

        action_hint = wx.StaticText(
            settings_panel,
            label=(
                "The transcript will be processed by your configured AI provider "
                "using the selected template. Create custom templates via "
                "AI > AI Action Builder."
            ),
        )
        action_hint.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        action_hint.Wrap(480)
        set_accessible_name(action_hint, "AI action hint")
        action_sizer.Add(action_hint, 0, wx.LEFT | wx.BOTTOM, 4)

        sp_sizer.Add(action_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # -- Options checkboxes --
        opts_box = wx.StaticBox(settings_panel, label="Options")
        set_accessible_name(opts_box, "Transcription options")
        opts_sizer = wx.StaticBoxSizer(opts_box, wx.VERTICAL)

        self._timestamps_cb = wx.CheckBox(settings_panel, label="Include &timestamps")
        set_accessible_name(self._timestamps_cb, "Include timestamps")
        set_accessible_help(
            self._timestamps_cb,
            "Add time markers to each line of the transcript.",
        )
        opts_sizer.Add(self._timestamps_cb, 0, wx.ALL, 4)

        self._diarization_cb = wx.CheckBox(settings_panel, label="Include speaker &diarization")
        set_accessible_name(self._diarization_cb, "Include speaker diarization")
        set_accessible_help(
            self._diarization_cb,
            "Identify and label different speakers in the audio.",
        )
        opts_sizer.Add(self._diarization_cb, 0, wx.ALL, 4)

        sp_sizer.Add(opts_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # -- Cost estimate display --
        cost_box = wx.StaticBox(settings_panel, label="Cost Estimate")
        set_accessible_name(cost_box, "Cost estimate")
        cost_sizer = wx.StaticBoxSizer(cost_box, wx.VERTICAL)

        self._cost_label = wx.StaticText(settings_panel, label="Free — local provider")
        set_accessible_name(self._cost_label, "Estimated transcription cost")
        cost_sizer.Add(self._cost_label, 0, wx.ALL, 4)

        self._budget_label = wx.StaticText(settings_panel, label="")
        self._budget_label.SetForegroundColour(wx.Colour(200, 80, 0))
        set_accessible_name(self._budget_label, "Budget warning")
        self._budget_label.Hide()
        cost_sizer.Add(self._budget_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        sp_sizer.Add(cost_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # -- Provider info / tip area --
        self._info_label = wx.StaticText(settings_panel, label="")
        self._info_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        self._info_label.Wrap(480)
        set_accessible_name(self._info_label, "Provider information")
        sp_sizer.Add(self._info_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        settings_panel.SetSizer(sp_sizer)
        root.Add(settings_panel, 1, wx.EXPAND)

        # ---- Buttons ----
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._add_btn = wx.Button(self, wx.ID_OK, label="&Add to Queue")
        set_accessible_name(self._add_btn, "Add files to transcription queue")
        cancel_btn = wx.Button(self, wx.ID_CANCEL, label="&Cancel")
        set_accessible_name(cancel_btn, "Cancel")

        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, 8)
        btn_sizer.Add(self._add_btn, 0)

        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizer(root)
        self._add_btn.SetDefault()

        # Events
        self._provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)
        self._add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self._preview_btn.Bind(wx.EVT_BUTTON, self._on_preview)

    # ------------------------------------------------------------------ #
    # Defaults / population                                                #
    # ------------------------------------------------------------------ #

    def _apply_defaults(self) -> None:
        """Populate dropdowns from settings and available providers."""
        settings = self._main_frame.app_settings
        pm = self._main_frame.provider_manager

        # -- Providers --
        enabled = pm.list_enabled_providers()
        self._provider_keys: list[str] = list(enabled)
        provider_labels: list[str] = []
        for pk in self._provider_keys:
            caps = pm.get_capabilities(pk)
            label = caps.name if caps else pk
            # Tag local/free providers
            if pk in ("local_whisper", "vosk", "windows_speech", "parakeet"):
                label += " (free, local)"
            provider_labels.append(label)

        self._provider_choice.Set(provider_labels)

        # Select the default provider
        default_prov = settings.general.default_provider or "local_whisper"
        if default_prov in self._provider_keys:
            self._provider_choice.SetSelection(self._provider_keys.index(default_prov))
        elif self._provider_keys:
            self._provider_choice.SetSelection(0)

        # -- Languages --
        lang_labels = [name for _, name in _COMMON_LANGUAGES]
        self._language_choice.Set(lang_labels)
        default_lang = settings.general.language or "auto"
        lang_codes = [code for code, _ in _COMMON_LANGUAGES]
        if default_lang in lang_codes:
            self._language_choice.SetSelection(lang_codes.index(default_lang))
        else:
            self._language_choice.SetSelection(0)  # auto

        # -- Checkboxes --
        self._timestamps_cb.SetValue(settings.transcription.include_timestamps)
        self._diarization_cb.SetValue(settings.diarization.enabled)

        # -- AI Action templates --
        self._populate_ai_actions()

        # -- Models (depends on provider) --
        self._refresh_models()

    def _refresh_models(self) -> None:
        """Repopulate the model dropdown for the currently selected provider."""
        sel = self._provider_choice.GetSelection()
        if sel < 0 or sel >= len(self._provider_keys):
            return
        provider_key = self._provider_keys[sel]
        models = get_models_for_provider(provider_key)

        if models:
            self._model_ids = [mid for mid, _ in models]
            self._model_choice.Set([mlabel for _, mlabel in models])
            # Select default if it matches
            settings = self._main_frame.app_settings
            if (
                provider_key == settings.general.default_provider
                and settings.general.default_model in self._model_ids
            ):
                self._model_choice.SetSelection(
                    self._model_ids.index(settings.general.default_model)
                )
            else:
                self._model_choice.SetSelection(0)
            self._model_choice.Enable(True)
        else:
            self._model_ids = [""]
            self._model_choice.Set(["(default)"])
            self._model_choice.SetSelection(0)
            self._model_choice.Enable(False)

        # Update info tip
        self._update_info(provider_key)

    def _update_info(self, provider_key: str) -> None:
        """Display a helpful tip about the selected provider.

        Args:
            provider_key: The currently selected provider key.
        """
        tips: dict[str, str] = {
            "local_whisper": (
                "Free, runs locally on your computer. "
                "Larger models are more accurate but need more RAM and time."
            ),
            "openai_whisper": "Cloud service by OpenAI. Requires an API key. Fast and accurate.",
            "google_speech": "Google Cloud Speech-to-Text. Requires an API key.",
            "azure_speech": "Microsoft Azure Speech Services. Requires an API key.",
            "deepgram": "Deepgram Nova-2. Fast and accurate cloud transcription.",
            "assemblyai": "AssemblyAI cloud transcription with advanced features.",
            "groq_whisper": "Groq LPU — extremely fast cloud Whisper inference.",
            "gemini": "Google Gemini multimodal AI. Supports large audio files.",
            "vosk": "Free offline speech recognition using Kaldi. Lightweight.",
            "parakeet": "NVIDIA Parakeet NeMo ASR. English only, very accurate.",
            "windows_speech": "Built-in Windows speech recognition. Free, offline.",
        }
        tip = tips.get(provider_key, "Select a provider to see transcription options.")
        self._info_label.SetLabel(tip)
        self._info_label.Wrap(480)
        self.Layout()

    def _populate_ai_actions(self) -> None:
        """Populate the AI action dropdown with built-in presets and saved templates."""
        from bits_whisperer.core.transcription_service import TranscriptionService

        labels: list[str] = ["None (transcribe only)"]
        self._ai_action_keys: list[str] = [""]

        # Built-in presets
        for preset_name in TranscriptionService._BUILTIN_PRESETS:
            labels.append(preset_name)
            self._ai_action_keys.append(preset_name)

        # Saved custom templates from agents directory
        agents_dir = DATA_DIR / "agents"
        if agents_dir.is_dir():
            for f in sorted(agents_dir.glob("*.json")):
                try:
                    from bits_whisperer.core.copilot_service import AgentConfig

                    config = AgentConfig.load(f)
                    display = f"\u2605 {config.name}" if config.name else f.stem
                    labels.append(display)
                    self._ai_action_keys.append(str(f))
                except Exception:
                    pass

        self._ai_action_choice.Set(labels)
        self._ai_action_choice.SetSelection(0)

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_provider_changed(self, _event: wx.CommandEvent) -> None:
        """User changed the provider — update models and info tip."""
        self._refresh_models()
        self._update_cost_estimate()

    def _on_preview(self, _event: wx.CommandEvent) -> None:
        """Open the audio preview dialog for a single file."""
        if len(self._paths) != 1:
            return

        from bits_whisperer.ui.audio_player_dialog import AudioPlayerDialog

        dlg = AudioPlayerDialog(
            self,
            self._paths[0],
            selection_start=self._clip_start,
            selection_end=self._clip_end,
            settings=self._main_frame.app_settings.playback,
        )
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            self._clip_start = dlg.selection_start
            self._clip_end = dlg.selection_end
            self._update_preview_label()
        dlg.Destroy()

    def _update_preview_label(self) -> None:
        if self._clip_start is None and self._clip_end is None:
            self._preview_label.SetLabel("Selection: full file")
            return

        start = self._clip_start or 0.0
        if self._clip_end is None:
            self._preview_label.SetLabel(f"Selection: from {start:.2f}s to end")
        else:
            self._preview_label.SetLabel(f"Selection: {start:.2f}s to {self._clip_end:.2f}s")

    def _update_cost_estimate(self) -> None:
        """Recalculate and display the estimated cost for the current selection."""
        sel = self._provider_choice.GetSelection()
        if sel < 0 or sel >= len(self._provider_keys):
            return

        provider_key = self._provider_keys[sel]
        pm = self._main_frame.provider_manager
        caps = pm.get_capabilities(provider_key)

        if not caps or caps.rate_per_minute_usd <= 0:
            self._cost_label.SetLabel("Free — no charge for this provider")
            self._budget_label.Hide()
            self.Layout()
            return

        # Estimate total cost across all files
        total_cost = 0.0
        total_duration = 0.0
        for path in self._paths:
            p = Path(path)
            size_bytes = p.stat().st_size if p.exists() else 0
            # Estimate duration: ~10 MB/min for WAV audio
            dur = max(60.0, size_bytes / (10 * 1024 * 1024) * 60)
            cost = pm.estimate_cost(provider_key, dur)
            total_cost += cost
            total_duration += dur

        minutes = total_duration / 60.0
        cost_text = (
            f"~${total_cost:.4f} USD for {len(self._paths)} file(s), "
            f"~{minutes:.1f} min total "
            f"(${caps.rate_per_minute_usd:.4f}/min)"
        )
        self._cost_label.SetLabel(cost_text)

        # Check budget limit
        budget = self._main_frame.app_settings.budget
        model_sel = self._model_choice.GetSelection()
        model_id = self._model_ids[model_sel] if model_sel >= 0 else ""
        exceeds, limit = budget.exceeds_limit(provider_key, model_id, total_cost)

        if exceeds:
            self._budget_label.SetLabel(
                f"\u26a0 Over budget! Limit: ${limit:.2f} — " f"Estimated: ${total_cost:.4f}"
            )
            self._budget_label.Show()
        elif limit > 0:
            self._budget_label.SetLabel(f"Within budget (${total_cost:.4f} of ${limit:.2f} limit)")
            self._budget_label.SetForegroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
            )
            self._budget_label.Show()
        else:
            self._budget_label.Hide()

        self.Layout()

    def _on_add(self, _event: wx.CommandEvent) -> None:
        """Validate, check budget, and create jobs for the selected files."""
        import uuid

        sel = self._provider_choice.GetSelection()
        if sel < 0 or sel >= len(self._provider_keys):
            accessible_message_box(
                "Please select a transcription provider.",
                "No Provider Selected",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        provider_key = self._provider_keys[sel]
        model_sel = self._model_choice.GetSelection()
        model_id = self._model_ids[model_sel] if model_sel >= 0 else ""

        lang_sel = self._language_choice.GetSelection()
        language = (
            _COMMON_LANGUAGES[lang_sel][0] if 0 <= lang_sel < len(_COMMON_LANGUAGES) else "auto"
        )

        include_timestamps = self._timestamps_cb.GetValue()
        include_diarization = self._diarization_cb.GetValue()

        # --- Cost estimation & budget check for paid providers ---
        pm = self._main_frame.provider_manager
        caps = pm.get_capabilities(provider_key)
        is_paid = (
            caps is not None
            and getattr(caps, "provider_type", "local") == "cloud"
            and getattr(caps, "rate_per_minute_usd", 0) > 0
        )

        total_cost = 0.0
        job_costs: list[float] = []
        total_duration = 0.0

        if is_paid:
            for path in self._paths:
                p = Path(path)
                size_bytes = p.stat().st_size if p.exists() else 0
                dur = max(60.0, size_bytes / (10 * 1024 * 1024) * 60)
                cost = pm.estimate_cost(provider_key, dur)
                job_costs.append(cost)
                total_cost += cost
                total_duration += dur

            # Budget limit check
            budget = self._main_frame.app_settings.budget
            exceeds, limit = budget.exceeds_limit(provider_key, model_id, total_cost)

            if exceeds:
                result = accessible_message_box(
                    f"\u26a0 Budget Warning\n\n"
                    f"The estimated cost (${total_cost:.4f}) exceeds your "
                    f"budget limit of ${limit:.2f} for this provider.\n\n"
                    f"Provider: {caps.name if caps else provider_key}\n"
                    f"Files: {len(self._paths)}\n"
                    f"Estimated audio: {total_duration / 60:.1f} minutes\n"
                    f"Estimated cost: ~${total_cost:.4f}\n"
                    f"Budget limit: ${limit:.2f}\n\n"
                    f"Do you want to proceed anyway?",
                    "Over Budget",
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                    self,
                )
                if result != wx.YES:
                    return

            # Always confirm paid transcription if setting is on
            elif budget.always_confirm_paid:
                minutes = total_duration / 60.0
                result = accessible_message_box(
                    f"This transcription will use a paid provider.\n\n"
                    f"Provider: {caps.name if caps else provider_key}\n"
                    f"Files: {len(self._paths)}\n"
                    f"Estimated audio: {minutes:.1f} minutes\n"
                    f"Estimated cost: ~${total_cost:.4f} USD\n\n"
                    f"Do you want to proceed?",
                    "Cost Confirmation",
                    wx.YES_NO | wx.ICON_QUESTION,
                    self,
                )
                if result != wx.YES:
                    return
        else:
            job_costs = [0.0] * len(self._paths)

        jobs: list[Job] = []
        custom_name = self._custom_name_input.GetValue().strip()
        clip_start = self._clip_start if len(self._paths) == 1 else None
        clip_end = self._clip_end if len(self._paths) == 1 else None
        ai_action_sel = self._ai_action_choice.GetSelection()
        ai_action_template = (
            self._ai_action_keys[ai_action_sel]
            if 0 <= ai_action_sel < len(self._ai_action_keys)
            else ""
        )
        for i, path in enumerate(self._paths):
            p = Path(path)
            # For single files, use the custom name directly.
            # For multiple files, append a number suffix if a custom name is set.
            if custom_name:
                if len(self._paths) == 1:
                    job_custom_name = custom_name
                else:
                    job_custom_name = f"{custom_name} ({i + 1})"
            else:
                job_custom_name = ""
            jobs.append(
                Job(
                    id=str(uuid.uuid4()),
                    file_path=str(p),
                    file_name=p.name,
                    file_size_bytes=p.stat().st_size if p.exists() else 0,
                    provider=provider_key,
                    model=model_id,
                    language=language,
                    include_timestamps=include_timestamps,
                    include_diarization=include_diarization,
                    cost_estimate=job_costs[i],
                    clip_start_seconds=clip_start,
                    clip_end_seconds=clip_end,
                    custom_name=job_custom_name,
                    ai_action_template=ai_action_template,
                )
            )

        self.result_jobs = jobs
        self.EndModal(wx.ID_OK)
