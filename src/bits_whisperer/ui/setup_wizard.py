"""First-run setup wizard for BITS Whisperer.

A multi-page startup wizard that guides new users through:
  1. Welcome & overview
  2. Experience mode selection (Basic vs Advanced)
  3. Hardware detection & display
  4. Model recommendation & selection (with async download)
  5. Provider selection & API key entry
  6. Quick preferences
  7. Summary & finish

The wizard creates a warm, guided experience so users feel supported
from the very first launch.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import wx
import wx.adv

from bits_whisperer.core.device_probe import DeviceProbe
from bits_whisperer.core.model_manager import ModelManager
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.storage.key_store import KeyStore
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import (
    APP_NAME,
    DATA_DIR,
    MODELS_DIR,
    WHISPER_MODELS,
)
from bits_whisperer.utils.platform_utils import (
    get_free_disk_space_mb,
    has_sufficient_disk_space,
)

if TYPE_CHECKING:
    from bits_whisperer.core.device_probe import DeviceProfile

logger = logging.getLogger(__name__)

_WIZARD_DONE_FILE = DATA_DIR / ".wizard_complete"

# Page indices
PAGE_WELCOME = 0
PAGE_MODE = 1
PAGE_HARDWARE = 2
PAGE_MODELS = 3
PAGE_PROVIDERS = 4
PAGE_AI_COPILOT = 5
PAGE_BUDGET = 6
PAGE_PREFERENCES = 7
PAGE_SUMMARY = 8
_TOTAL_PAGES = 9


def needs_wizard() -> bool:
    """Check whether the first-run wizard should be shown.

    Returns:
        True if the wizard has not been completed before.
    """
    return not _WIZARD_DONE_FILE.exists()


def mark_wizard_complete() -> None:
    """Mark the wizard as completed so it won't show again."""
    try:
        _WIZARD_DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WIZARD_DONE_FILE.write_text("done", encoding="utf-8")
    except Exception:
        logger.debug("Could not write wizard completion marker")


class SetupWizard(wx.Dialog):
    """Multi-page first-run setup wizard.

    Guides the user through hardware detection, model selection,
    provider setup, and initial preferences with a friendly,
    handholding experience.
    """

    def __init__(self, parent: wx.Window | None) -> None:
        super().__init__(
            parent,
            title=f"Welcome to {APP_NAME}",
            size=(700, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, f"{APP_NAME} setup wizard")
        self.SetMinSize((640, 500))
        self.Centre()

        # --- Services ---
        self._device_probe = DeviceProbe()
        self._device_profile: DeviceProfile | None = None
        self._model_manager = ModelManager()
        self._key_store = KeyStore()
        self._settings = AppSettings()

        # --- State ---
        self._current_page = PAGE_WELCOME
        self._selected_models: list[str] = []
        self._download_threads: dict[str, threading.Thread] = {}
        self._download_status: dict[str, str] = {}  # model_id -> status text
        self._provider_keys: dict[str, str] = {}

        # --- Build UI ---
        self._build_ui()
        self._show_page(PAGE_WELCOME)

    # ================================================================== #
    # UI construction                                                      #
    # ================================================================== #

    def _build_ui(self) -> None:
        """Build the wizard layout with page panel and navigation."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Header banner ---
        self._header = wx.StaticText(self, label=f"Welcome to {APP_NAME}")
        header_font = self._header.GetFont()
        header_font.SetPointSize(header_font.GetPointSize() + 6)
        header_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._header.SetFont(header_font)
        set_accessible_name(self._header, "Wizard page title")
        main_sizer.Add(self._header, 0, wx.ALL, 16)

        # --- Subtitle ---
        self._subtitle = wx.StaticText(self, label="")
        sub_font = self._subtitle.GetFont()
        sub_font.SetPointSize(sub_font.GetPointSize() + 1)
        self._subtitle.SetFont(sub_font)
        set_accessible_name(self._subtitle, "Wizard page description")
        main_sizer.Add(self._subtitle, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        # --- Separator ---
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # --- Page container ---
        self._page_panel = wx.Panel(self)
        make_panel_accessible(self._page_panel)
        self._page_sizer = wx.BoxSizer(wx.VERTICAL)
        self._page_panel.SetSizer(self._page_sizer)
        main_sizer.Add(self._page_panel, 1, wx.EXPAND | wx.ALL, 12)

        # --- Progress indicator ---
        self._step_label = wx.StaticText(self, label="Step 1 of 6")
        set_accessible_name(self._step_label, "Wizard progress")
        main_sizer.Add(self._step_label, 0, wx.LEFT | wx.RIGHT, 16)

        # --- Navigation buttons ---
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_back = wx.Button(self, label="< &Back")
        self._btn_next = wx.Button(self, label="&Next >")
        self._btn_skip = wx.Button(self, label="&Skip Setup")
        self._btn_finish = wx.Button(self, label="&Finish")

        set_accessible_name(self._btn_back, "Go to previous step")
        set_accessible_name(self._btn_next, "Go to next step")
        set_accessible_name(self._btn_skip, "Skip setup wizard")
        set_accessible_name(self._btn_finish, "Complete setup")

        btn_sizer.Add(self._btn_skip, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._btn_back, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._btn_next, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._btn_finish, 0)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizer(main_sizer)

        # --- Event bindings ---
        self._btn_back.Bind(wx.EVT_BUTTON, self._on_back)
        self._btn_next.Bind(wx.EVT_BUTTON, self._on_next)
        self._btn_skip.Bind(wx.EVT_BUTTON, self._on_skip)
        self._btn_finish.Bind(wx.EVT_BUTTON, self._on_finish)

    # ================================================================== #
    # Page display                                                         #
    # ================================================================== #

    def _show_page(self, page_idx: int) -> None:
        """Display the specified wizard page.

        Args:
            page_idx: Zero-based page index.
        """
        self._current_page = page_idx

        # Clear previous page content
        self._page_sizer.Clear(delete_windows=True)

        # Build the requested page
        page_names = {
            PAGE_WELCOME: "Welcome page",
            PAGE_MODE: "Experience mode page",
            PAGE_HARDWARE: "Hardware detection page",
            PAGE_MODELS: "Model selection page",
            PAGE_PROVIDERS: "Cloud services setup page",
            PAGE_AI_COPILOT: "AI and Copilot setup page",
            PAGE_BUDGET: "Spending limits page",
            PAGE_PREFERENCES: "Preferences page",
            PAGE_SUMMARY: "Setup summary page",
        }
        builders = {
            PAGE_WELCOME: self._build_welcome_page,
            PAGE_MODE: self._build_mode_page,
            PAGE_HARDWARE: self._build_hardware_page,
            PAGE_MODELS: self._build_models_page,
            PAGE_PROVIDERS: self._build_providers_page,
            PAGE_AI_COPILOT: self._build_ai_copilot_page,
            PAGE_BUDGET: self._build_budget_page,
            PAGE_PREFERENCES: self._build_preferences_page,
            PAGE_SUMMARY: self._build_summary_page,
        }
        builders[page_idx]()

        # Update navigation state
        self._update_nav_buttons()
        step_text = f"Step {page_idx + 1} of {_TOTAL_PAGES}"
        self._step_label.SetLabel(step_text)
        set_accessible_name(self._step_label, step_text)
        set_accessible_name(
            self._page_panel,
            f"{page_names.get(page_idx, 'Wizard page')} — {step_text}",
        )
        self._page_panel.Layout()
        self.Layout()

        # Set focus to first interactive control
        wx.CallAfter(self._focus_first_control)

    def _create_info_text(self, parent: wx.Window, text: str, name: str) -> wx.TextCtrl:
        """Create a focusable read-only text control for informational text.

        Screen readers can read this control when it receives focus via Tab,
        unlike wx.StaticText which is skipped in focus-mode navigation.

        Args:
            parent: Parent window.
            text: The informational text to display.
            name: Accessible name for screen readers.

        Returns:
            A read-only, borderless, focusable wx.TextCtrl.
        """
        ctrl = wx.TextCtrl(
            parent,
            value=text,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.BORDER_NONE,
        )
        ctrl.SetBackgroundColour(parent.GetBackgroundColour())
        set_accessible_name(ctrl, name)
        # Estimate the needed height based on text length
        dc = wx.ClientDC(ctrl)
        dc.SetFont(ctrl.GetFont())
        line_h = dc.GetCharHeight()
        avg_char_w = dc.GetCharWidth()
        available_w = max(400, 600)
        chars_per_line = max(1, available_w // avg_char_w)
        total_lines = 0
        for line in text.split("\n"):
            total_lines += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        ctrl.SetMinSize((-1, total_lines * line_h + 10))
        return ctrl

    def _focus_first_control(self) -> None:
        """Set focus to the first interactive control on the current page."""
        for child in self._page_panel.GetChildren():
            if isinstance(child, (wx.Button, wx.CheckBox, wx.TextCtrl, wx.Choice, wx.ListCtrl)):
                child.SetFocus()
                return
        self._btn_next.SetFocus()

    def _update_nav_buttons(self) -> None:
        """Show/hide navigation buttons based on current page."""
        self._btn_back.Show(self._current_page > PAGE_WELCOME)
        self._btn_next.Show(self._current_page < PAGE_SUMMARY)
        self._btn_finish.Show(self._current_page == PAGE_SUMMARY)
        self._btn_skip.Show(self._current_page < PAGE_SUMMARY)

    # ================================================================== #
    # Page 1: Welcome                                                      #
    # ================================================================== #

    def _build_welcome_page(self) -> None:
        """Build the welcome / introduction page."""
        self._header.SetLabel(f"Welcome to {APP_NAME}!")
        self._subtitle.SetLabel(
            "Let's get you set up in just a few steps. This will only take a minute."
        )

        panel = self._page_panel
        sizer = self._page_sizer

        intro_text = (
            f"{APP_NAME} turns your audio files into text using the latest AI technology. "
            "You can use free on-device models that keep your data private, or connect "
            "to cloud services for maximum accuracy.\n\n"
            "This setup wizard will:\n"
            "  1.  Let you choose Basic or Advanced mode\n"
            "  2.  Detect your computer's hardware\n"
            "  3.  Recommend AI models that work best on your machine\n"
            "  4.  Let you download models for offline use\n"
            "  5.  Help you connect cloud services (optional)\n"
            "  6.  Set up AI features and spending limits\n"
            "  7.  Set your preferences\n\n"
            "You can always change these settings later from the Tools menu."
        )
        intro = self._create_info_text(panel, intro_text, "Setup wizard introduction")
        sizer.Add(intro, 0, wx.EXPAND | wx.ALL, 8)

        # Feature highlights
        features_box = wx.StaticBox(panel, label="What you get")
        set_accessible_name(features_box, "Feature highlights")
        fb_sizer = wx.StaticBoxSizer(features_box, wx.VERTICAL)

        highlights = [
            "16 transcription engines — cloud and local",
            "14 AI models matched to your hardware",
            "7 export formats (Text, Word, SRT, and more)",
            "Full keyboard navigation and screen reader support",
            "Your audio stays on your computer with local models",
        ]
        highlights_text = "\n".join(f"  \u2022  {h}" for h in highlights)
        highlights_ctrl = self._create_info_text(panel, highlights_text, "Feature highlights")
        fb_sizer.Add(highlights_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        sizer.Add(fb_sizer, 0, wx.EXPAND | wx.ALL, 8)

    # ================================================================== #
    # Page 2: Experience Mode                                              #
    # ================================================================== #

    def _build_mode_page(self) -> None:
        """Build the experience mode selection page (Basic vs Advanced)."""
        self._header.SetLabel("Choose Your Experience")
        self._subtitle.SetLabel(
            "Pick the interface style that suits you best. "
            "You can switch at any time from the View menu."
        )

        panel = self._page_panel
        sizer = self._page_sizer

        intro_text = (
            f"{APP_NAME} offers two experience modes to match your comfort level. "
            "Choose Basic for a streamlined experience, or Advanced for full control."
        )
        intro = self._create_info_text(panel, intro_text, "Mode selection introduction")
        sizer.Add(intro, 0, wx.EXPAND | wx.ALL, 8)

        # Basic mode box
        basic_box = wx.StaticBox(panel, label="Basic Mode (Recommended)")
        set_accessible_name(basic_box, "Basic mode description")
        basic_sizer = wx.StaticBoxSizer(basic_box, wx.VERTICAL)

        self._mode_basic = wx.RadioButton(panel, label="&Basic Mode", style=wx.RB_GROUP)
        set_accessible_name(self._mode_basic, "Basic mode")
        set_accessible_help(
            self._mode_basic,
            "Simplified interface with essential features only",
        )
        basic_sizer.Add(self._mode_basic, 0, wx.ALL, 4)

        basic_features = (
            "What you get in Basic mode:\n"
            "  \u2022  Simple settings: General, Output, and Provider tabs\n"
            "  \u2022  Only activated cloud providers appear for use\n"
            "  \u2022  Guided provider setup via Add Provider wizard\n"
            "  \u2022  Recommended defaults applied automatically\n"
            "  \u2022  Clean, focused interface with fewer options\n\n"
            "Best for: First-time users, accessibility-focused workflows, "
            "and anyone who prefers simplicity."
        )
        basic_ctrl = self._create_info_text(panel, basic_features, "Basic mode features")
        basic_sizer.Add(basic_ctrl, 0, wx.EXPAND | wx.ALL, 4)
        sizer.Add(basic_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Advanced mode box
        adv_box = wx.StaticBox(panel, label="Advanced Mode")
        set_accessible_name(adv_box, "Advanced mode description")
        adv_sizer = wx.StaticBoxSizer(adv_box, wx.VERTICAL)

        self._mode_advanced = wx.RadioButton(panel, label="&Advanced Mode")
        set_accessible_name(self._mode_advanced, "Advanced mode")
        set_accessible_help(
            self._mode_advanced,
            "Full interface with all settings and provider controls",
        )
        adv_sizer.Add(self._mode_advanced, 0, wx.ALL, 4)

        adv_features = (
            "What you get in Advanced mode (everything in Basic, plus):\n"
            "  \u2022  All 7 settings tabs including Audio Processing and Advanced\n"
            "  \u2022  All cloud providers visible regardless of activation\n"
            "  \u2022  Audio preprocessing chain (noise gate, EQ, compressor)\n"
            "  \u2022  Concurrency, chunking, and GPU configuration\n"
            "  \u2022  CPU thread and compute type controls\n"
            "  \u2022  Log level and debug settings\n\n"
            "Best for: Power users, audio professionals, and developers."
        )
        adv_ctrl = self._create_info_text(panel, adv_features, "Advanced mode features")
        adv_sizer.Add(adv_ctrl, 0, wx.EXPAND | wx.ALL, 4)
        sizer.Add(adv_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Set current selection from settings
        if self._settings.general.experience_mode == "advanced":
            self._mode_advanced.SetValue(True)
        else:
            self._mode_basic.SetValue(True)

        # Tip
        tip_text = (
            "Tip: You can switch between Basic and Advanced mode at any time "
            "using View > Advanced Mode (Ctrl+Shift+A) in the menu bar."
        )
        tip = self._create_info_text(panel, tip_text, "Mode switching tip")
        sizer.Add(tip, 0, wx.EXPAND | wx.ALL, 8)

    # ================================================================== #
    # Page 3: Hardware Detection                                           #
    # ================================================================== #

    def _build_hardware_page(self) -> None:
        """Build the hardware detection results page."""
        self._header.SetLabel("Your Computer")
        self._subtitle.SetLabel("We've scanned your hardware to find the best AI models for you.")

        panel = self._page_panel
        sizer = self._page_sizer

        # Run hardware probe if not done yet
        if self._device_profile is None:
            self._device_profile = self._device_probe.probe()

        dp = self._device_profile

        # Hardware summary
        hw_box = wx.StaticBox(panel, label="Hardware Detected")
        set_accessible_name(hw_box, "Hardware detection results")
        hw_sizer = wx.StaticBoxSizer(hw_box, wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, hgap=16, vgap=6)
        grid.AddGrowableCol(1)

        items = [
            ("Operating System:", f"{dp.os_name} {dp.os_version}"),
            ("Processor:", dp.cpu_name),
            ("CPU Cores:", f"{dp.cpu_cores_physical} physical, {dp.cpu_cores_logical} logical"),
            ("Memory (RAM):", f"{dp.ram_gb:.1f} GB"),
        ]

        if dp.gpu_name:
            items.append(("Graphics Card:", dp.gpu_name))
            items.append(("Video Memory:", f"{dp.gpu_vram_gb:.1f} GB"))
            items.append(("CUDA:", "Available" if dp.has_cuda else "Not available"))
        else:
            items.append(("Graphics Card:", "None detected (CPU-only mode)"))

        # Disk space
        free_gb = get_free_disk_space_mb(MODELS_DIR) / 1024
        items.append(("Free Disk Space:", f"{free_gb:.1f} GB"))

        for label_text, value_text in items:
            lbl = wx.StaticText(panel, label=label_text)
            font = lbl.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            lbl.SetFont(font)
            val = wx.StaticText(panel, label=value_text)
            grid.Add(lbl, 0, wx.ALIGN_RIGHT)
            grid.Add(val, 0)

        hw_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 8)

        # Focusable hardware summary for screen readers
        hw_summary_parts = [f"{lbl}: {val}" for lbl, val in items]
        hw_summary_text = "\n".join(hw_summary_parts)
        hw_info_ctrl = self._create_info_text(panel, hw_summary_text, "Hardware details")
        hw_sizer.Add(hw_info_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(hw_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Recommendation summary
        n_eligible = len(dp.eligible_models)
        n_warned = len(dp.warned_models)
        n_ineligible = len(dp.ineligible_models)

        if dp.has_cuda and dp.gpu_vram_gb >= 4:
            verdict = (
                "Great news! Your GPU can handle most AI models. "
                "We recommend Large v3 Turbo for the best balance of speed and accuracy."
            )
        elif dp.ram_gb >= 8:
            verdict = (
                "Your computer has enough memory for medium-sized models. "
                "We recommend the Small model for a good balance of speed and accuracy."
            )
        else:
            verdict = (
                "Your computer works best with lightweight models. "
                "The Tiny or Base model will run quickly and give you good results."
            )

        verdict_full = (
            f"{verdict}\n\n"
            f"Models ready to use: {n_eligible}  |  "
            f"Usable but may be slow: {n_warned}  |  "
            f"Too demanding: {n_ineligible}"
        )
        verdict_ctrl = self._create_info_text(panel, verdict_full, "Hardware recommendation")
        sizer.Add(verdict_ctrl, 0, wx.EXPAND | wx.ALL, 8)

    # ================================================================== #
    # Page 3: Model Selection & Download                                   #
    # ================================================================== #

    def _build_models_page(self) -> None:
        """Build the model selection page with download capabilities."""
        self._header.SetLabel("Choose Your AI Models")
        self._subtitle.SetLabel(
            "Select which models to download for offline transcription. "
            "You can always download more later."
        )

        panel = self._page_panel
        sizer = self._page_sizer
        dp = self._device_profile

        # Disk space warning
        free_mb = get_free_disk_space_mb(MODELS_DIR)
        if free_mb < 1000:
            warn = wx.StaticText(
                panel,
                label=(
                    f"\u26a0 Low disk space: {free_mb:.0f} MB free. "
                    "Large models may not fit. Consider freeing up space first."
                ),
            )
            warn.SetForegroundColour(wx.Colour(200, 80, 0))
            set_accessible_name(warn, "Low disk space warning")
            sizer.Add(warn, 0, wx.ALL, 4)

        # Recommended model callout
        recommended = self._device_probe.get_recommended_model()
        rec_info = None
        for m in WHISPER_MODELS:
            if m.id == recommended:
                rec_info = m
                break

        if rec_info:
            rec_box = wx.StaticBox(panel, label="Recommended for Your Hardware")
            set_accessible_name(rec_box, "Recommended model")
            rec_sizer = wx.StaticBoxSizer(rec_box, wx.VERTICAL)
            rec_text = wx.StaticText(
                panel,
                label=(
                    f"{rec_info.name} - {rec_info.description}\n"
                    f"Size: {rec_info.disk_size_mb} MB  |  "
                    f"Speed: {rec_info.speed_stars} of 5  |  "
                    f"Accuracy: {rec_info.accuracy_stars} of 5"
                ),
            )
            rec_text.Wrap(580)
            rec_sizer.Add(rec_text, 0, wx.ALL, 6)
            sizer.Add(rec_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Scrolled panel for model checkboxes
        scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 10)
        set_accessible_name(scroll, "Available models list")
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        self._model_checks: dict[str, wx.CheckBox] = {}
        self._model_status_labels: dict[str, wx.StaticText] = {}

        for mi in WHISPER_MODELS:
            if not dp or mi.id in dp.ineligible_models:
                continue

            row = wx.BoxSizer(wx.HORIZONTAL)

            # Checkbox
            already_downloaded = self._model_manager.is_downloaded(mi.id)
            cb = wx.CheckBox(scroll, label="")
            set_accessible_name(
                cb,
                f"{'Downloaded' if already_downloaded else 'Select'} {mi.name}",
            )

            # Pre-check recommended model
            if mi.id == recommended and not already_downloaded:
                cb.SetValue(True)
                self._selected_models.append(mi.id)
            elif already_downloaded:
                cb.SetValue(True)
                cb.Disable()

            self._model_checks[mi.id] = cb
            row.Add(cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

            # Model info
            eligibility = ""
            if mi.id in (dp.warned_models if dp else []):
                eligibility = " (Warning: May be slow)"

            info_text = (
                f"{mi.name} - {mi.disk_size_mb} MB  |  "
                f"Speed: {mi.speed_stars} of 5  "
                f"Accuracy: {mi.accuracy_stars} of 5"
                f"{eligibility}"
            )
            info_lbl = wx.StaticText(scroll, label=info_text)
            row.Add(info_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

            # Status label
            status_text = "Downloaded" if already_downloaded else ""
            status_lbl = wx.StaticText(scroll, label=status_text)
            self._model_status_labels[mi.id] = status_lbl
            row.Add(status_lbl, 0, wx.ALIGN_CENTER_VERTICAL)

            scroll_sizer.Add(row, 0, wx.EXPAND | wx.ALL, 3)

            # Checkbox event
            cb.Bind(wx.EVT_CHECKBOX, lambda e, mid=mi.id: self._on_model_toggle(mid))

        scroll.SetSizer(scroll_sizer)
        sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 4)

        # Total download size — focusable so screen readers can read it
        self._size_label = wx.TextCtrl(
            panel,
            value="",
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        self._size_label.SetBackgroundColour(panel.GetBackgroundColour())
        set_accessible_name(self._size_label, "Total download size")
        self._update_download_size()
        sizer.Add(self._size_label, 0, wx.EXPAND | wx.ALL, 4)

        # Download all button
        self._dl_all_btn = wx.Button(panel, label="&Download Selected Models Now")
        set_accessible_name(self._dl_all_btn, "Download all selected models")
        set_accessible_help(
            self._dl_all_btn,
            "Downloads will run in the background. You'll be notified when each model is ready.",
        )
        self._dl_all_btn.Bind(wx.EVT_BUTTON, self._on_download_selected)
        sizer.Add(self._dl_all_btn, 0, wx.ALL, 4)

        # Download progress gauge
        self._dl_gauge = wx.Gauge(panel, range=100)
        self._dl_gauge.Hide()
        set_accessible_name(self._dl_gauge, "Download progress")
        sizer.Add(self._dl_gauge, 0, wx.EXPAND | wx.ALL, 4)

    def _on_model_toggle(self, model_id: str) -> None:
        """Handle model checkbox toggle."""
        cb = self._model_checks.get(model_id)
        if cb and cb.GetValue():
            if model_id not in self._selected_models:
                self._selected_models.append(model_id)
        else:
            if model_id in self._selected_models:
                self._selected_models.remove(model_id)
        self._update_download_size()

    def _update_download_size(self) -> None:
        """Update the total download size label."""
        total_mb = 0
        count = 0
        for mid in self._selected_models:
            if not self._model_manager.is_downloaded(mid):
                for m in WHISPER_MODELS:
                    if m.id == mid:
                        total_mb += m.disk_size_mb
                        count += 1
                        break

        if count == 0:
            text = "No new models to download."
        elif total_mb > 1024:
            text = f"{count} model(s) selected — {total_mb / 1024:.1f} GB to download"
        else:
            text = f"{count} model(s) selected — {total_mb} MB to download"

        # Disk space check
        free_mb = get_free_disk_space_mb(MODELS_DIR)
        if total_mb > 0 and total_mb > free_mb * 0.9:
            text += f"  \u26a0 Not enough disk space! ({free_mb:.0f} MB free)"

        if hasattr(self, "_size_label"):
            self._size_label.SetValue(text)
            set_accessible_name(self._size_label, f"Download summary: {text}")

    def _on_download_selected(self, _event: wx.CommandEvent) -> None:
        """Start downloading all selected models asynchronously."""
        # Pre-check: is faster-whisper installed?
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            accessible_message_box(
                "The faster-whisper library is not installed.\n\n"
                "Install it with:\n"
                "  pip install faster-whisper\n\n"
                "Then restart the application and try again.",
                "Missing Dependency",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        to_download = [
            mid for mid in self._selected_models if not self._model_manager.is_downloaded(mid)
        ]
        if not to_download:
            accessible_message_box(
                "All selected models are already downloaded!",
                "Nothing to Download",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Disk space pre-check
        total_mb = 0
        for mid in to_download:
            for m in WHISPER_MODELS:
                if m.id == mid:
                    total_mb += m.disk_size_mb
                    break

        if not has_sufficient_disk_space(MODELS_DIR, total_mb * 1.1):
            free_mb = get_free_disk_space_mb(MODELS_DIR)
            accessible_message_box(
                f"Not enough disk space!\n\n"
                f"Required: {total_mb} MB\n"
                f"Available: {free_mb:.0f} MB\n\n"
                "Please free up disk space and try again.",
                "Insufficient Disk Space",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._dl_all_btn.Disable()
        self._dl_gauge.Show()
        self._dl_gauge.Pulse()
        self.Layout()

        # Download each model in a background thread
        self._downloads_total = len(to_download)
        self._downloads_done = 0

        for model_id in to_download:
            self._download_status[model_id] = "Downloading..."
            self._update_model_status(model_id, "Downloading...")

            t = threading.Thread(
                target=self._download_model_async,
                args=(model_id,),
                daemon=True,
                name=f"dl-{model_id}",
            )
            self._download_threads[model_id] = t
            t.start()

    def _download_model_async(self, model_id: str) -> None:
        """Download a model in a background thread.

        Args:
            model_id: The model identifier to download.
        """
        try:
            self._model_manager.download_model(model_id)
            safe_call_after(self._on_model_downloaded, model_id, True, "")
        except Exception as exc:
            safe_call_after(self._on_model_downloaded, model_id, False, str(exc))

    def _on_model_downloaded(self, model_id: str, success: bool, error: str) -> None:
        """Handle model download completion on the main thread.

        Args:
            model_id: The model that finished downloading.
            success: Whether the download succeeded.
            error: Error message if failed.
        """
        self._downloads_done += 1

        if success:
            self._download_status[model_id] = "Downloaded"
            self._update_model_status(model_id, "Downloaded")

            # Disable checkbox for downloaded model
            cb = self._model_checks.get(model_id)
            if cb:
                cb.SetValue(True)
                cb.Disable()

            logger.info("Wizard: model '%s' downloaded successfully", model_id)
        else:
            self._download_status[model_id] = f"Failed: {error}"
            self._update_model_status(model_id, f"Failed: {error[:50]}")
            logger.warning("Wizard: model '%s' download failed: %s", model_id, error)

        # Update progress
        if self._downloads_total > 0:
            pct = int(self._downloads_done / self._downloads_total * 100)
            self._dl_gauge.SetValue(pct)

        # All done?
        if self._downloads_done >= self._downloads_total:
            self._dl_gauge.Hide()
            self._dl_all_btn.Enable()
            self._dl_all_btn.SetLabel("&Download Selected Models Now")
            self.Layout()

            # Show completion notification
            failed = sum(1 for s in self._download_status.values() if s.startswith("Failed"))
            if failed == 0:
                accessible_message_box(
                    f"All {self._downloads_total} model(s) downloaded successfully!\n\n"
                    "You're all set for offline transcription.",
                    "Downloads Complete",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            else:
                accessible_message_box(
                    f"Downloaded: {self._downloads_total - failed}\n"
                    f"Failed: {failed}\n\n"
                    "You can retry failed downloads later from Tools, then Manage Models.",
                    "Downloads Complete",
                    wx.OK | wx.ICON_WARNING,
                    self,
                )

    def _update_model_status(self, model_id: str, status: str) -> None:
        """Update the status label for a model.

        Args:
            model_id: Model identifier.
            status: Status text to display.
        """
        lbl = self._model_status_labels.get(model_id)
        if lbl:
            lbl.SetLabel(status)
            self._page_panel.Layout()

    # ================================================================== #
    # Page 4: Provider Selection & API Keys                                #
    # ================================================================== #

    def _build_providers_page(self) -> None:
        """Build the cloud provider setup page."""
        self._header.SetLabel("Cloud Services (Optional)")
        self._subtitle.SetLabel(
            "Connect cloud transcription services for maximum accuracy. "
            "You can skip this and use free local models."
        )

        panel = self._page_panel
        sizer = self._page_sizer

        intro_text = (
            "Cloud services are optional — local models work great for most uses."
            " If you have API keys for any of these services, enter them below."
            " Your keys are stored securely in your operating system's credential vault"
            " and never sent anywhere except the provider's own service."
        )
        intro = self._create_info_text(panel, intro_text, "Cloud services introduction")
        sizer.Add(intro, 0, wx.EXPAND | wx.ALL, 4)

        # Scrolled panel for provider keys
        scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 10)
        set_accessible_name(scroll, "Cloud provider API keys")
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        # Provider info: (key_id, display_name, help_url, description)
        providers = [
            (
                "openai",
                "OpenAI (Whisper API)",
                "https://platform.openai.com/api-keys",
                "Fast and reliable. $0.006/min.",
            ),
            (
                "groq",
                "Groq (LPU Whisper)",
                "https://console.groq.com/keys",
                "188x real-time speed. $0.003/min.",
            ),
            (
                "gemini",
                "Google Gemini",
                "https://makersuite.google.com/app/apikey",
                "Cheapest cloud option. $0.0002/min.",
            ),
            (
                "deepgram",
                "Deepgram (Nova-2)",
                "https://console.deepgram.com/",
                "Smart formatting. $0.013/min.",
            ),
            (
                "assemblyai",
                "AssemblyAI",
                "https://www.assemblyai.com/app/account",
                "Speaker labels, auto-chapters. $0.011/min.",
            ),
            (
                "elevenlabs",
                "ElevenLabs (Scribe)",
                "https://elevenlabs.io/app/settings/api-keys",
                "99+ languages. $0.005/min.",
            ),
            (
                "auphonic",
                "Auphonic",
                "https://auphonic.com/accounts/settings/#api-key",
                "Audio post-production + Whisper. 2 free hours/month.",
            ),
        ]

        self._provider_inputs: dict[str, wx.TextCtrl] = {}

        for key_id, name, url, desc in providers:
            box = wx.StaticBox(scroll, label=name)
            set_accessible_name(box, f"{name} configuration")
            box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

            desc_lbl = wx.StaticText(scroll, label=desc)
            box_sizer.Add(desc_lbl, 0, wx.ALL, 2)

            row = wx.BoxSizer(wx.HORIZONTAL)
            lbl = wx.StaticText(scroll, label="API Key:")
            txt = wx.TextCtrl(scroll, style=wx.TE_PASSWORD, size=(350, -1))
            set_accessible_name(txt, f"{name} API key")
            set_accessible_help(txt, f"Enter your {name} API key. Get one at {url}")

            # Pre-fill from keystore
            existing = self._key_store.get_key(key_id)
            if existing:
                txt.SetValue(existing)

            self._provider_inputs[key_id] = txt
            label_control(lbl, txt)
            row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
            row.Add(txt, 1, wx.RIGHT, 4)

            # Link to get key
            link = wx.adv.HyperlinkCtrl(scroll, label="Get key", url=url)
            set_accessible_name(link, f"Open {name} key page")
            row.Add(link, 0, wx.ALIGN_CENTER_VERTICAL)

            box_sizer.Add(row, 0, wx.EXPAND | wx.ALL, 2)

            # Status indicator
            if existing:
                status = wx.StaticText(scroll, label="  Key saved")
            else:
                status = wx.StaticText(scroll, label="  Not configured (optional)")
            box_sizer.Add(status, 0, wx.LEFT | wx.BOTTOM, 2)

            scroll_sizer.Add(box_sizer, 0, wx.EXPAND | wx.BOTTOM, 6)

        scroll.SetSizer(scroll_sizer)
        sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 4)

    # ================================================================== #
    # Page 5: AI & Copilot Setup                                           #
    # ================================================================== #

    def _build_ai_copilot_page(self) -> None:
        """Build the AI provider and GitHub Copilot configuration page."""
        self._header.SetLabel("AI Features (Optional)")
        self._subtitle.SetLabel(
            "Enhance your transcripts with AI-powered summarization, "
            "translation, and interactive Q&A."
        )

        panel = self._page_panel
        sizer = self._page_sizer

        intro_text = (
            "BITS Whisperer can use AI services to summarize, translate, and "
            "answer questions about your transcripts. Configure one or more "
            "providers below, or skip this step and set them up later from "
            "AI > AI Provider Settings."
        )
        intro = self._create_info_text(panel, intro_text, "AI features introduction")
        sizer.Add(intro, 0, wx.EXPAND | wx.ALL, 4)

        scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 10)
        set_accessible_name(scroll, "AI provider configuration")
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        # Gemini — easiest to get started
        gemini_box = wx.StaticBox(scroll, label="Google Gemini (Recommended)")
        set_accessible_name(gemini_box, "Google Gemini AI setup")
        gemini_sizer = wx.StaticBoxSizer(gemini_box, wx.VERTICAL)

        gemini_desc = wx.StaticText(
            scroll,
            label=(
                "Most affordable option. Free tier available. "
                "Get an API key from Google AI Studio."
            ),
        )
        gemini_sizer.Add(gemini_desc, 0, wx.ALL, 4)

        g_row = wx.BoxSizer(wx.HORIZONTAL)
        g_lbl = wx.StaticText(scroll, label="Gemini API Key:")
        self._wizard_gemini_key = wx.TextCtrl(scroll, style=wx.TE_PASSWORD, size=(300, -1))
        set_accessible_name(self._wizard_gemini_key, "Google Gemini API key")
        label_control(g_lbl, self._wizard_gemini_key)

        existing_gemini = self._key_store.get_key("gemini")
        if existing_gemini:
            self._wizard_gemini_key.SetValue(existing_gemini)

        g_link = wx.adv.HyperlinkCtrl(
            scroll,
            label="Get key",
            url="https://makersuite.google.com/app/apikey",
        )
        set_accessible_name(g_link, "Open Google AI Studio to get API key")
        g_row.Add(g_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        g_row.Add(self._wizard_gemini_key, 1, wx.RIGHT, 4)
        g_row.Add(g_link, 0, wx.ALIGN_CENTER_VERTICAL)
        gemini_sizer.Add(g_row, 0, wx.EXPAND | wx.ALL, 4)
        scroll_sizer.Add(gemini_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)

        # GitHub Copilot
        copilot_box = wx.StaticBox(scroll, label="GitHub Copilot")
        set_accessible_name(copilot_box, "GitHub Copilot setup")
        copilot_sizer = wx.StaticBoxSizer(copilot_box, wx.VERTICAL)

        copilot_desc = wx.StaticText(
            scroll,
            label=(
                "Interactive AI chat for transcript analysis. Requires GitHub "
                "Copilot subscription. Full setup available via AI > Copilot Setup."
            ),
        )
        copilot_desc.Wrap(560)
        copilot_sizer.Add(copilot_desc, 0, wx.ALL, 4)

        # SDK detection status
        from bits_whisperer.core.sdk_installer import is_sdk_available

        sdk_ok = is_sdk_available("copilot_sdk")
        if sdk_ok:
            sdk_status = "Copilot SDK: Installed (includes CLI)"
        else:
            sdk_status = "Copilot SDK not installed. Install later via AI > Copilot Setup."

        sdk_label = wx.StaticText(scroll, label=sdk_status)
        sdk_label.Wrap(560)
        set_accessible_name(sdk_label, "Copilot SDK status")
        copilot_sizer.Add(sdk_label, 0, wx.ALL, 4)

        # Enable Copilot checkbox
        self._wizard_copilot_enable = wx.CheckBox(scroll, label="&Enable GitHub Copilot features")
        set_accessible_name(
            self._wizard_copilot_enable,
            "Enable GitHub Copilot for transcript AI features",
        )
        self._wizard_copilot_enable.SetValue(self._settings.copilot.enabled if sdk_ok else False)
        copilot_sizer.Add(self._wizard_copilot_enable, 0, wx.ALL, 4)

        scroll_sizer.Add(copilot_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)

        # OpenAI for AI services
        openai_box = wx.StaticBox(scroll, label="OpenAI")
        set_accessible_name(openai_box, "OpenAI AI setup")
        openai_sizer = wx.StaticBoxSizer(openai_box, wx.VERTICAL)

        openai_desc = wx.StaticText(
            scroll,
            label="GPT-4o models for summarization and translation.",
        )
        openai_sizer.Add(openai_desc, 0, wx.ALL, 4)

        o_row = wx.BoxSizer(wx.HORIZONTAL)
        o_lbl = wx.StaticText(scroll, label="OpenAI API Key:")
        self._wizard_openai_key = wx.TextCtrl(scroll, style=wx.TE_PASSWORD, size=(300, -1))
        set_accessible_name(self._wizard_openai_key, "OpenAI API key for AI features")
        label_control(o_lbl, self._wizard_openai_key)

        existing_openai = self._key_store.get_key("openai")
        if existing_openai:
            self._wizard_openai_key.SetValue(existing_openai)

        o_link = wx.adv.HyperlinkCtrl(
            scroll,
            label="Get key",
            url="https://platform.openai.com/api-keys",
        )
        set_accessible_name(o_link, "Open OpenAI API keys page")
        o_row.Add(o_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        o_row.Add(self._wizard_openai_key, 1, wx.RIGHT, 4)
        o_row.Add(o_link, 0, wx.ALIGN_CENTER_VERTICAL)
        openai_sizer.Add(o_row, 0, wx.EXPAND | wx.ALL, 4)
        scroll_sizer.Add(openai_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)

        scroll.SetSizer(scroll_sizer)
        sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 4)

    # ================================================================== #
    # Page 7: Spending Limits / Budget                                     #
    # ================================================================== #

    def _build_budget_page(self) -> None:
        """Build the spending-limits / budget configuration page."""
        self._header.SetLabel("Spending Limits")
        self._subtitle.SetLabel("Control how much you spend on paid cloud transcription services.")

        panel = self._page_panel
        sizer = self._page_sizer
        b = self._settings.budget

        intro_text = (
            "Cloud transcription providers charge per minute of audio. "
            "Setting a spending limit helps you stay in control. "
            "When a transcription's estimated cost exceeds your limit, "
            "you'll be warned before it is queued.\n\n"
            "Tip: You can set detailed per-provider limits later in "
            "Settings \u2192 Budget."
        )
        intro = self._create_info_text(panel, intro_text, "Spending limits introduction")
        sizer.Add(intro, 0, wx.EXPAND | wx.ALL, 8)

        # --- Main controls ---
        ctrl_box = wx.StaticBox(panel, label="Budget Controls")
        set_accessible_name(ctrl_box, "Budget controls")
        ctrl_sizer = wx.StaticBoxSizer(ctrl_box, wx.VERTICAL)

        self._wiz_budget_enabled = wx.CheckBox(
            panel,
            label="&Enable spending-limit warnings",
        )
        self._wiz_budget_enabled.SetValue(b.enabled)
        set_accessible_name(
            self._wiz_budget_enabled,
            "Enable spending limit warnings",
        )
        set_accessible_help(
            self._wiz_budget_enabled,
            "Show a warning when a transcription's estimated cost " "exceeds your spending limit",
        )
        ctrl_sizer.Add(self._wiz_budget_enabled, 0, wx.ALL, 6)

        self._wiz_always_confirm = wx.CheckBox(
            panel,
            label="Always &confirm before using a paid provider",
        )
        self._wiz_always_confirm.SetValue(b.always_confirm_paid)
        set_accessible_name(
            self._wiz_always_confirm,
            "Always confirm paid provider usage",
        )
        set_accessible_help(
            self._wiz_always_confirm,
            "Ask for confirmation every time you queue audio with a "
            "paid cloud provider, even if within budget",
        )
        ctrl_sizer.Add(self._wiz_always_confirm, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Default limit
        lim_row = wx.BoxSizer(wx.HORIZONTAL)
        lim_lbl = wx.StaticText(panel, label="Default spending &limit (USD):")
        self._wiz_budget_limit = wx.SpinCtrlDouble(
            panel,
            min=0.0,
            max=1000.0,
            inc=0.50,
            initial=b.default_limit_usd,
        )
        self._wiz_budget_limit.SetDigits(2)
        label_control(lim_lbl, self._wiz_budget_limit)
        set_accessible_help(
            self._wiz_budget_limit,
            "Maximum cost in USD per transcription. " "Set to 0 for no limit.",
        )
        lim_row.Add(lim_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        lim_row.Add(self._wiz_budget_limit, 0)
        ctrl_sizer.Add(lim_row, 0, wx.ALL, 6)

        sizer.Add(ctrl_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # --- Pricing reference ---
        pricing_box = wx.StaticBox(panel, label="Cloud Provider Pricing Reference")
        set_accessible_name(pricing_box, "Provider pricing reference")
        pr_sizer = wx.StaticBoxSizer(pricing_box, wx.VERTICAL)

        pricing_lines = [
            "Gemini:            ~$0.0002/min  (cheapest)",
            "Groq Whisper:      ~$0.003/min",
            "ElevenLabs Scribe: ~$0.005/min",
            "OpenAI Whisper:    ~$0.006/min",
            "AssemblyAI:        ~$0.011/min",
            "Deepgram Nova-2:   ~$0.013/min",
            "Azure Speech:      ~$0.017/min",
            "Auphonic:          2 free hours/month, then paid",
            "Local models:      Always free",
        ]
        pricing_text = "\n".join(pricing_lines)
        pricing_ctrl = self._create_info_text(panel, pricing_text, "Provider pricing reference")
        pr_sizer.Add(pricing_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        sizer.Add(pr_sizer, 0, wx.EXPAND | wx.ALL, 8)

    # ================================================================== #
    # Page 8: Quick Preferences                                            #
    # ================================================================== #

    def _build_preferences_page(self) -> None:
        """Build the quick preferences page."""
        self._header.SetLabel("Your Preferences")
        self._subtitle.SetLabel("Customize how BITS Whisperer works for you.")

        panel = self._page_panel
        sizer = self._page_sizer

        s = self._settings

        # Language preference
        lang_box = wx.StaticBox(panel, label="Language")
        set_accessible_name(lang_box, "Language preferences")
        lang_sizer = wx.StaticBoxSizer(lang_box, wx.VERTICAL)

        lang_row = wx.BoxSizer(wx.HORIZONTAL)
        lang_lbl = wx.StaticText(panel, label="Primary &language:")
        self._pref_language = wx.Choice(
            panel,
            choices=[
                "Auto-detect",
                "English",
                "Spanish",
                "French",
                "German",
                "Italian",
                "Portuguese",
                "Dutch",
                "Russian",
                "Chinese",
                "Japanese",
                "Korean",
                "Arabic",
                "Hindi",
            ],
        )
        label_control(lang_lbl, self._pref_language)
        self._pref_language.SetSelection(0)
        lang_row.Add(lang_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        lang_row.Add(self._pref_language, 0)
        lang_sizer.Add(lang_row, 0, wx.ALL, 6)
        sizer.Add(lang_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Output preferences
        out_box = wx.StaticBox(panel, label="Output")
        set_accessible_name(out_box, "Output preferences")
        out_sizer = wx.StaticBoxSizer(out_box, wx.VERTICAL)

        fmt_row = wx.BoxSizer(wx.HORIZONTAL)
        fmt_lbl = wx.StaticText(panel, label="Default export &format:")
        self._pref_format = wx.Choice(
            panel,
            choices=["Plain Text (.txt)", "Markdown (.md)", "Word (.docx)", "SRT Subtitles (.srt)"],
        )
        label_control(fmt_lbl, self._pref_format)
        self._pref_format.SetSelection(0)
        fmt_row.Add(fmt_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        fmt_row.Add(self._pref_format, 0)
        out_sizer.Add(fmt_row, 0, wx.ALL, 6)

        self._pref_auto_export = wx.CheckBox(
            panel, label="Automatically save transcripts when &done"
        )
        set_accessible_name(self._pref_auto_export, "Auto-export transcripts")
        self._pref_auto_export.SetValue(s.general.auto_export)
        out_sizer.Add(self._pref_auto_export, 0, wx.ALL, 4)

        self._pref_timestamps = wx.CheckBox(panel, label="Include &timestamps in transcripts")
        set_accessible_name(self._pref_timestamps, "Include timestamps")
        self._pref_timestamps.SetValue(s.transcription.include_timestamps)
        out_sizer.Add(self._pref_timestamps, 0, wx.ALL, 4)

        sizer.Add(out_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Behaviour preferences
        beh_box = wx.StaticBox(panel, label="Behaviour")
        set_accessible_name(beh_box, "Behaviour preferences")
        beh_sizer = wx.StaticBoxSizer(beh_box, wx.VERTICAL)

        self._pref_minimize = wx.CheckBox(panel, label="&Minimize to system tray when closing")
        set_accessible_name(self._pref_minimize, "Minimize to tray on close")
        self._pref_minimize.SetValue(s.general.minimize_to_tray)
        beh_sizer.Add(self._pref_minimize, 0, wx.ALL, 4)

        self._pref_notifications = wx.CheckBox(
            panel, label="Show &notifications when transcription completes"
        )
        set_accessible_name(self._pref_notifications, "Show completion notifications")
        self._pref_notifications.SetValue(s.general.show_notifications)
        beh_sizer.Add(self._pref_notifications, 0, wx.ALL, 4)

        self._pref_updates = wx.CheckBox(panel, label="Check for &updates on startup")
        set_accessible_name(self._pref_updates, "Auto-check for updates")
        self._pref_updates.SetValue(s.general.check_updates_on_start)
        beh_sizer.Add(self._pref_updates, 0, wx.ALL, 4)

        sizer.Add(beh_sizer, 0, wx.EXPAND | wx.ALL, 4)

    # ================================================================== #
    # Page 9: Summary & Finish                                             #
    # ================================================================== #

    def _build_summary_page(self) -> None:
        """Build the final summary page."""
        self._header.SetLabel("You're All Set!")
        self._subtitle.SetLabel(
            "Here's a summary of your setup. Click Finish to start using " f"{APP_NAME}."
        )

        panel = self._page_panel
        sizer = self._page_sizer

        # Hardware summary
        dp = self._device_profile
        hw_text = "Unknown hardware"
        if dp:
            gpu_text = dp.gpu_name if dp.gpu_name else "CPU only"
            hw_text = f"{dp.cpu_name}  |  {dp.ram_gb:.0f} GB RAM  |  {gpu_text}"

        # Models summary
        downloaded = self._model_manager.list_downloaded_models()
        model_names = [m.name for m in downloaded]
        models_text = ", ".join(model_names) if model_names else "None (use cloud services)"

        # Providers summary — use saved keys, not destroyed TextCtrl refs
        providers_configured = list(self._provider_keys.keys())
        # Also check keystore for keys set before this wizard session
        if not providers_configured:
            for key_id in [
                "openai",
                "groq",
                "gemini",
                "deepgram",
                "assemblyai",
                "elevenlabs",
                "auphonic",
            ]:
                if self._key_store.get_key(key_id):
                    providers_configured.append(key_id)
        providers_text = (
            ", ".join(providers_configured) if providers_configured else "None (using local models)"
        )

        # Experience mode summary
        mode = self._settings.general.experience_mode
        mode_display = "Advanced" if mode == "advanced" else "Basic"

        # Budget summary
        bgt = self._settings.budget
        if bgt.enabled and bgt.default_limit_usd > 0:
            budget_text = f"Enabled \u2014 ${bgt.default_limit_usd:.2f} default limit"
        elif bgt.enabled:
            budget_text = "Enabled \u2014 no default limit"
        else:
            budget_text = "Disabled"
        if bgt.always_confirm_paid:
            budget_text += " (always confirm paid)"

        summary_items = [
            ("Experience Mode:", mode_display),
            ("Your Hardware:", hw_text),
            ("Downloaded Models:", models_text),
            ("Cloud Services:", providers_text),
            ("Spending Limits:", budget_text),
        ]

        summary_box = wx.StaticBox(panel, label="Setup Summary")
        set_accessible_name(summary_box, "Setup summary")
        sb_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)

        # Build a focusable text summary so screen readers can read it
        summary_text_parts = []
        grid = wx.FlexGridSizer(cols=2, hgap=16, vgap=8)
        grid.AddGrowableCol(1)

        for label_text, value_text in summary_items:
            lbl = wx.StaticText(panel, label=label_text)
            font = lbl.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            lbl.SetFont(font)
            val = wx.StaticText(panel, label=value_text)
            val.Wrap(400)
            grid.Add(lbl, 0, wx.ALIGN_RIGHT | wx.ALIGN_TOP)
            grid.Add(val, 0)
            summary_text_parts.append(f"{label_text} {value_text}")

        sb_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 8)

        # Focusable summary for screen readers
        summary_full = "\n".join(summary_text_parts)
        summary_ctrl = self._create_info_text(panel, summary_full, "Setup summary details")
        sb_sizer.Add(summary_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(sb_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Quick tips
        tips_box = wx.StaticBox(panel, label="Quick Tips to Get Started")
        set_accessible_name(tips_box, "Getting started tips")
        tips_sizer = wx.StaticBoxSizer(tips_box, wx.VERTICAL)

        tips = [
            "Drag and drop audio files onto the window, or use File, then Add Files (Ctrl+O)",
            "Press F5 to start transcription",
            "Use Ctrl+E to export your transcript",
            "Press Ctrl+, to open Settings at any time",
            "Press Ctrl+M to manage AI models",
            "Toggle View, then Advanced Mode (Ctrl+Shift+A) for power-user settings",
        ]
        tips_text = "\n".join(f"  \u2022  {tip}" for tip in tips)
        tips_ctrl = self._create_info_text(panel, tips_text, "Getting started tips")
        tips_sizer.Add(tips_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        sizer.Add(tips_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Reassurance
        reassure_text = (
            "All these settings can be changed later from the Tools and View menus. "
            "If you need help, check the User Guide in the Help menu."
        )
        reassure = self._create_info_text(panel, reassure_text, "Additional information")
        sizer.Add(reassure, 0, wx.EXPAND | wx.ALL, 8)

    # ================================================================== #
    # Navigation events                                                    #
    # ================================================================== #

    def _on_back(self, _event: wx.CommandEvent) -> None:
        """Navigate to the previous page."""
        if self._current_page > PAGE_WELCOME:
            self._show_page(self._current_page - 1)

    def _on_next(self, _event: wx.CommandEvent) -> None:
        """Navigate to the next page, saving state from current page."""
        self._save_current_page_state()
        if self._current_page < PAGE_SUMMARY:
            self._show_page(self._current_page + 1)

    def _on_skip(self, _event: wx.CommandEvent) -> None:
        """Skip the wizard entirely."""
        dlg = wx.MessageDialog(
            self,
            "Skip the setup wizard?\n\n"
            "You can always configure settings later from the Tools menu.\n"
            "The wizard won't show again on next startup.",
            "Skip Setup",
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if dlg.ShowModal() == wx.ID_YES:
            mark_wizard_complete()
            self.EndModal(wx.ID_CANCEL)
        dlg.Destroy()

    def _on_finish(self, _event: wx.CommandEvent) -> None:
        """Finish the wizard, apply all settings."""
        self._save_current_page_state()
        self._apply_all_settings()
        mark_wizard_complete()
        self.EndModal(wx.ID_OK)

    # ================================================================== #
    # Settings persistence                                                 #
    # ================================================================== #

    def _save_current_page_state(self) -> None:
        """Save state from the current page's controls."""
        if self._current_page == PAGE_MODE:
            # Save experience mode
            if hasattr(self, "_mode_advanced") and self._mode_advanced.GetValue():
                self._settings.general.experience_mode = "advanced"
            else:
                self._settings.general.experience_mode = "basic"

        elif self._current_page == PAGE_PROVIDERS:
            # Save API keys
            if hasattr(self, "_provider_inputs"):
                for key_id, txt in self._provider_inputs.items():
                    value = txt.GetValue().strip()
                    if value:
                        self._key_store.store_key(key_id, value)
                        self._provider_keys[key_id] = value

        elif self._current_page == PAGE_AI_COPILOT:
            # Save Gemini key
            if hasattr(self, "_wizard_gemini_key"):
                gemini_key = self._wizard_gemini_key.GetValue().strip()
                if gemini_key:
                    self._key_store.store_key("gemini", gemini_key)
                    self._provider_keys["gemini"] = gemini_key
            # Save OpenAI key for AI features
            if hasattr(self, "_wizard_openai_key"):
                openai_key = self._wizard_openai_key.GetValue().strip()
                if openai_key:
                    self._key_store.store_key("openai", openai_key)
                    self._provider_keys["openai"] = openai_key
            # Save Copilot setting
            if hasattr(self, "_wizard_copilot_enable"):
                self._settings.copilot.enabled = self._wizard_copilot_enable.GetValue()

        elif self._current_page == PAGE_BUDGET:
            if hasattr(self, "_wiz_budget_enabled"):
                self._settings.budget.enabled = self._wiz_budget_enabled.GetValue()
            if hasattr(self, "_wiz_always_confirm"):
                self._settings.budget.always_confirm_paid = self._wiz_always_confirm.GetValue()
            if hasattr(self, "_wiz_budget_limit"):
                self._settings.budget.default_limit_usd = self._wiz_budget_limit.GetValue()

        elif self._current_page == PAGE_PREFERENCES:
            if hasattr(self, "_pref_language"):
                lang_map = {
                    0: "auto",
                    1: "en",
                    2: "es",
                    3: "fr",
                    4: "de",
                    5: "it",
                    6: "pt",
                    7: "nl",
                    8: "ru",
                    9: "zh",
                    10: "ja",
                    11: "ko",
                    12: "ar",
                    13: "hi",
                }
                sel = self._pref_language.GetSelection()
                self._settings.general.language = lang_map.get(sel, "auto")

            if hasattr(self, "_pref_format"):
                fmt_map = {0: "txt", 1: "md", 2: "docx", 3: "srt"}
                sel = self._pref_format.GetSelection()
                self._settings.output.default_format = fmt_map.get(sel, "txt")

            if hasattr(self, "_pref_auto_export"):
                self._settings.general.auto_export = self._pref_auto_export.GetValue()
            if hasattr(self, "_pref_timestamps"):
                self._settings.transcription.include_timestamps = self._pref_timestamps.GetValue()
            if hasattr(self, "_pref_minimize"):
                self._settings.general.minimize_to_tray = self._pref_minimize.GetValue()
            if hasattr(self, "_pref_notifications"):
                self._settings.general.show_notifications = self._pref_notifications.GetValue()
            if hasattr(self, "_pref_updates"):
                self._settings.general.check_updates_on_start = self._pref_updates.GetValue()

    def _apply_all_settings(self) -> None:
        """Apply and save all wizard settings."""
        # Set recommended model as default if one was selected
        if self._selected_models:
            # Pick the best selected model as default
            for m in reversed(WHISPER_MODELS):
                if m.id in self._selected_models and self._model_manager.is_downloaded(m.id):
                    self._settings.general.default_model = m.id
                    break

        self._settings.save()
        logger.info("Wizard settings applied and saved")

    @property
    def settings(self) -> AppSettings:
        """Return the settings configured by the wizard."""
        return self._settings
