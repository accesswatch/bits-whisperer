"""Add Provider dialog — cloud provider onboarding workflow.

Guides the user through selecting a cloud transcription provider,
entering their API key, and validating it. Only once the key is
validated does the provider become 'activated' and available for
use in transcription jobs.

The dialog enforces a three-step process:
  1. **Select** a cloud provider from the list
  2. **Enter** the required API key (and any auxiliary credentials)
  3. **Validate** the key with a live test call

On successful validation, the provider is added to the user's
``activated_providers`` list in settings and its key is stored
in the OS credential vault.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import wx
import wx.adv

from bits_whisperer.storage.key_store import KeyStore
from bits_whisperer.utils.accessibility import (
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

# Cloud provider definitions:
# (keystore_id, display_name, provider_manager_key, key_url, description, aux_keys)
# aux_keys is a list of (keystore_id, label, help_text) for providers that
# need more than one credential field (e.g. AWS needs secret key + region).
_CLOUD_PROVIDERS: list[tuple[str, str, str, str, str, list[tuple[str, str, str]]]] = [
    (
        "openai",
        "OpenAI (Whisper API)",
        "openai_whisper",
        "https://platform.openai.com/api-keys",
        "Fast, reliable cloud transcription. $0.006 per minute. "
        "Supports 100+ languages with high accuracy.",
        [],
    ),
    (
        "groq",
        "Groq (LPU Whisper)",
        "groq_whisper",
        "https://console.groq.com/keys",
        "Blazing fast — 188x real-time speed on Groq's LPU hardware. "
        "$0.003 per minute. Great for large batches.",
        [],
    ),
    (
        "gemini",
        "Google Gemini",
        "gemini",
        "https://makersuite.google.com/app/apikey",
        "Most affordable cloud option at $0.0002 per minute. " "Powered by Google's Gemini models.",
        [],
    ),
    (
        "deepgram",
        "Deepgram (Nova-2)",
        "deepgram",
        "https://console.deepgram.com/",
        "Smart formatting, punctuation, and paragraphing. "
        "$0.013 per minute. Excellent for meetings.",
        [],
    ),
    (
        "assemblyai",
        "AssemblyAI",
        "assemblyai",
        "https://www.assemblyai.com/app/account",
        "Speaker labels, auto-chapters, and content moderation. "
        "$0.011 per minute. Best for detailed transcripts.",
        [],
    ),
    (
        "elevenlabs",
        "ElevenLabs (Scribe)",
        "elevenlabs",
        "https://elevenlabs.io/app/settings/api-keys",
        "Ultra-reliable with 99+ language support. " "$0.005 per minute. Excellent accuracy.",
        [],
    ),
    (
        "auphonic",
        "Auphonic",
        "auphonic",
        "https://auphonic.com/accounts/settings/#api-key",
        "Audio post-production plus Whisper transcription. "
        "2 free hours per month. Great for podcasts.",
        [],
    ),
    (
        "google",
        "Google Cloud Speech-to-Text",
        "google_speech",
        "https://console.cloud.google.com/apis/credentials",
        "Enterprise-grade speech recognition by Google. "
        "$0.006 per minute. Supports 125+ languages.",
        [],
    ),
    (
        "azure",
        "Microsoft Azure Speech",
        "azure_speech",
        "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices",
        "Microsoft's speech service with real-time and batch modes. "
        "$0.01 per minute. Free tier: 5 hours/month.",
        [
            (
                "azure_region",
                "Azure Region:",
                "Azure region (e.g. eastus, westeurope)",
            ),
        ],
    ),
    (
        "aws_access_key",
        "Amazon Transcribe",
        "aws_transcribe",
        "https://console.aws.amazon.com/iam/home#/security_credentials",
        "AWS speech-to-text with custom vocabulary support. "
        "$0.024 per minute. Free tier: 60 minutes/month.",
        [
            (
                "aws_secret_key",
                "AWS Secret Key:",
                "Your AWS Secret Access Key",
            ),
            (
                "aws_region",
                "AWS Region:",
                "AWS region (e.g. us-east-1, eu-west-1)",
            ),
        ],
    ),
    (
        "rev_ai",
        "Rev.ai",
        "rev_ai",
        "https://www.rev.ai/access-token",
        "High-accuracy transcription from Rev. " "$0.02 per minute. Specializes in English.",
        [],
    ),
    (
        "speechmatics",
        "Speechmatics",
        "speechmatics",
        "https://portal.speechmatics.com/manage-access/",
        "Enterprise speech recognition with 50+ languages. " "Pay-as-you-go pricing.",
        [],
    ),
]

# ---------------------------------------------------------------------------
# Per-provider configurable settings
# Each tuple: (setting_id, label, control_type, default, extra)
#   control_type: "check" = checkbox, "choice" = dropdown, "spin" = numeric,
#                 "text" = free text
#   extra: for "choice" -> list[str]; for "spin" -> (min, max); else None
# ---------------------------------------------------------------------------
_PROVIDER_SETTINGS_DEFS: dict[str, list[tuple[str, str, str, Any, Any]]] = {
    "auphonic": [
        ("leveler", "Adaptive Leveler", "check", True, None),
        ("loudness_normalization", "Loudness Normalization", "check", True, None),
        ("loudness_target", "Loudness Target (LUFS)", "spin", -16, (-31, -9)),
        ("noise_reduction", "Noise Reduction", "check", True, None),
        ("filtering", "Filtering && Auto-EQ", "check", True, None),
        ("hum_reduction", "Hum Reduction (50/60 Hz)", "check", False, None),
        ("silence_cutting", "Remove Silence", "check", False, None),
        ("filler_cutting", "Remove Filler Words", "check", False, None),
        ("cough_cutting", "Remove Coughs", "check", False, None),
        ("speech_service", "Speech Engine", "choice", "whisper",
         ["whisper", "google", "amazon", "speechmatics"]),
        ("output_format", "Output Format", "choice", "mp3",
         ["mp3", "aac", "flac", "wav", "opus", "ogg"]),
    ],
    "deepgram": [
        ("model", "Model", "choice", "nova-2",
         ["nova-2", "nova", "enhanced", "base"]),
        ("smart_format", "Smart Format", "check", True, None),
        ("punctuate", "Auto Punctuation", "check", True, None),
        ("paragraphs", "Auto Paragraphs", "check", True, None),
        ("utterances", "Utterance Detection", "check", False, None),
    ],
    "assemblyai": [
        ("punctuate", "Auto Punctuation", "check", True, None),
        ("format_text", "Format Text", "check", True, None),
        ("auto_chapters", "Auto Chapters", "check", False, None),
        ("content_safety", "Content Safety Detection", "check", False, None),
        ("sentiment_analysis", "Sentiment Analysis", "check", False, None),
        ("entity_detection", "Entity Detection", "check", False, None),
    ],
    "google": [
        ("model", "Recognition Model", "choice", "default",
         ["default", "latest_long", "latest_short", "phone_call", "video",
          "command_and_search", "medical_conversation"]),
        ("max_speaker_count", "Max Speakers (diarization)", "spin", 6, (2, 20)),
    ],
    "azure": [
        ("endpoint_id", "Custom Endpoint ID", "text", "", None),
    ],
    "aws_access_key": [
        ("max_speaker_labels", "Max Speaker Labels", "spin", 10, (2, 20)),
    ],
    "rev_ai": [
        ("custom_vocabulary", "Custom Vocabulary (comma-separated)", "text", "", None),
    ],
    "speechmatics": [
        ("operating_point", "Operating Point", "choice", "enhanced",
         ["enhanced", "standard"]),
    ],
    "elevenlabs": [
        ("timestamps_granularity", "Timestamp Granularity", "choice", "segment",
         ["segment", "word"]),
    ],
    "openai": [
        ("model", "Model", "choice", "whisper-1", ["whisper-1"]),
        ("temperature", "Temperature", "spin", 0, (0, 100)),
    ],
    "groq": [
        ("model", "Model", "choice", "whisper-large-v3-turbo",
         ["whisper-large-v3-turbo", "whisper-large-v3",
          "distil-whisper-large-v3-en"]),
    ],
    "gemini": [
        ("model", "Model", "choice", "gemini-2.0-flash",
         ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]),
    ],
}


class AddProviderDialog(wx.Dialog):
    """Step-by-step dialog for adding a cloud transcription provider.

    Walks the user through provider selection, credential entry,
    and validation before activating the provider for use.
    """

    def __init__(self, parent: MainFrame) -> None:
        """Initialise the Add Provider dialog.

        Args:
            parent: The main application frame.
        """
        super().__init__(
            parent,
            title="Add Cloud Provider — BITS Whisperer",
            size=(620, 680),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Add cloud transcription provider")
        self.SetMinSize((560, 560))
        self.Centre()

        self._main_frame: MainFrame = parent
        self._key_store: KeyStore = parent.key_store
        self._settings = parent.app_settings
        self._selected_provider: int = -1
        self._activated_provider: str | None = None  # set on successful validation

        self._build_ui()

    # ================================================================== #
    # UI construction                                                      #
    # ================================================================== #

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        root = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(self, label="Add a Cloud Provider")
        hfont = header.GetFont()
        hfont.SetPointSize(hfont.GetPointSize() + 4)
        hfont.SetWeight(wx.FONTWEIGHT_BOLD)
        header.SetFont(hfont)
        set_accessible_name(header, "Add a cloud provider")
        root.Add(header, 0, wx.ALL, 12)

        intro = wx.StaticText(
            self,
            label=(
                "Select a cloud provider, enter your API key, and validate it. "
                "Once validated, the provider will be available for transcription."
            ),
        )
        intro.Wrap(540)
        set_accessible_name(intro, "Instructions")
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Content panel
        self._content_panel = wx.Panel(self)
        make_panel_accessible(self._content_panel)
        self._content_sizer = wx.BoxSizer(wx.VERTICAL)
        self._content_panel.SetSizer(self._content_sizer)
        root.Add(self._content_panel, 1, wx.EXPAND | wx.ALL, 8)

        # Build the provider selection + credentials form
        self._build_provider_list()

        # Bottom buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        self._btn_validate = wx.Button(self, label="&Validate && Activate")
        set_accessible_name(self._btn_validate, "Validate and activate provider")
        set_accessible_help(
            self._btn_validate,
            "Test your API key and activate this provider for use",
        )
        self._btn_validate.Disable()

        self._btn_close = wx.Button(self, wx.ID_CLOSE, "&Close")
        set_accessible_name(self._btn_close, "Close dialog")

        btn_sizer.Add(self._btn_validate, 0, wx.RIGHT, 6)
        btn_sizer.Add(self._btn_close, 0)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)

        # Bindings
        self._btn_validate.Bind(wx.EVT_BUTTON, self._on_validate)
        self._btn_close.Bind(wx.EVT_BUTTON, self._on_close)

    def _build_provider_list(self) -> None:
        """Build the provider selection list and credential fields."""
        panel = self._content_panel
        sizer = self._content_sizer

        # Filter out already-activated providers
        activated = set(self._settings.general.activated_providers)

        # Provider choice dropdown
        prov_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="&Provider:")
        self._available_providers: list[tuple[str, str, str, str, str, list]] = []
        names: list[str] = []
        for prov in _CLOUD_PROVIDERS:
            kid, name, _pm_key, _url, _desc, _aux = prov
            status = " (already activated)" if kid in activated else ""
            names.append(f"{name}{status}")
            self._available_providers.append(prov)

        self._provider_choice = wx.Choice(panel, choices=names)
        label_control(lbl, self._provider_choice)
        set_accessible_help(
            self._provider_choice,
            "Choose which cloud transcription provider to add",
        )
        prov_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        prov_row.Add(self._provider_choice, 1, wx.EXPAND)
        sizer.Add(prov_row, 0, wx.EXPAND | wx.ALL, 4)

        # Description area
        self._desc_text = wx.TextCtrl(
            panel,
            value="Select a provider above to see its description.",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.BORDER_NONE,
            size=(-1, 50),
        )
        self._desc_text.SetBackgroundColour(panel.GetBackgroundColour())
        set_accessible_name(self._desc_text, "Provider description")
        sizer.Add(self._desc_text, 0, wx.EXPAND | wx.ALL, 4)

        # Credential fields box
        self._cred_box = wx.StaticBox(panel, label="Credentials")
        set_accessible_name(self._cred_box, "API credentials")
        self._cred_sizer = wx.StaticBoxSizer(self._cred_box, wx.VERTICAL)

        # Primary API key row
        key_row = wx.BoxSizer(wx.HORIZONTAL)
        self._key_lbl = wx.StaticText(panel, label="API &Key:")
        self._key_txt = wx.TextCtrl(panel, style=wx.TE_PASSWORD, size=(320, -1))
        label_control(self._key_lbl, self._key_txt)
        set_accessible_help(self._key_txt, "Enter the API key for the selected provider")
        key_row.Add(self._key_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        key_row.Add(self._key_txt, 1, wx.EXPAND)
        self._cred_sizer.Add(key_row, 0, wx.EXPAND | wx.ALL, 4)

        # Auxiliary fields container (shown/hidden per provider)
        self._aux_panel = wx.Panel(panel)
        make_panel_accessible(self._aux_panel)
        self._aux_sizer = wx.BoxSizer(wx.VERTICAL)
        self._aux_panel.SetSizer(self._aux_sizer)
        self._aux_fields: dict[str, wx.TextCtrl] = {}
        self._cred_sizer.Add(self._aux_panel, 0, wx.EXPAND)

        # Get key link
        self._get_key_link = wx.adv.HyperlinkCtrl(
            panel, label="Get an API key", url="https://example.com"
        )
        set_accessible_name(self._get_key_link, "Open provider key page")
        self._cred_sizer.Add(self._get_key_link, 0, wx.ALL, 4)

        # Pre-fill indicator
        self._prefill_lbl = wx.StaticText(panel, label="")
        set_accessible_name(self._prefill_lbl, "Key status")
        self._cred_sizer.Add(self._prefill_lbl, 0, wx.LEFT | wx.BOTTOM, 4)

        sizer.Add(self._cred_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Provider-specific settings box
        self._settings_box = wx.StaticBox(panel, label="Provider Settings")
        set_accessible_name(self._settings_box, "Provider-specific settings")
        self._prov_settings_sizer = wx.StaticBoxSizer(self._settings_box, wx.VERTICAL)

        self._prov_settings_panel = wx.Panel(panel)
        make_panel_accessible(self._prov_settings_panel)
        self._prov_settings_inner = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        self._prov_settings_inner.AddGrowableCol(1, 1)
        self._prov_settings_panel.SetSizer(self._prov_settings_inner)
        self._prov_settings_sizer.Add(
            self._prov_settings_panel, 1, wx.EXPAND | wx.ALL, 4
        )
        self._settings_controls: dict[str, wx.Control] = {}

        sizer.Add(self._prov_settings_sizer, 0, wx.EXPAND | wx.ALL, 4)
        # Initially hidden — shown when a provider with settings is selected
        self._prov_settings_sizer.ShowItems(False)

        # Validation status
        self._status_box = wx.StaticBox(panel, label="Status")
        set_accessible_name(self._status_box, "Validation status")
        status_sizer = wx.StaticBoxSizer(self._status_box, wx.VERTICAL)

        self._status_text = wx.TextCtrl(
            panel,
            value="Select a provider and enter your API key, then click Validate.",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.BORDER_NONE,
            size=(-1, 45),
        )
        self._status_text.SetBackgroundColour(panel.GetBackgroundColour())
        set_accessible_name(self._status_text, "Validation result")
        status_sizer.Add(self._status_text, 0, wx.EXPAND | wx.ALL, 4)

        # Progress gauge (hidden until validating)
        self._progress = wx.Gauge(panel, range=100)
        self._progress.Hide()
        set_accessible_name(self._progress, "Validation progress")
        status_sizer.Add(self._progress, 0, wx.EXPAND | wx.ALL, 4)

        sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # Bind provider selection change
        self._provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_selected)

        # Enable validate button when text is entered
        self._key_txt.Bind(wx.EVT_TEXT, self._on_key_changed)

    # ================================================================== #
    # Event handlers                                                       #
    # ================================================================== #

    def _on_provider_selected(self, _event: wx.CommandEvent) -> None:
        """Handle provider selection change."""
        idx = self._provider_choice.GetSelection()
        if idx < 0:
            return

        self._selected_provider = idx
        kid, name, _pm_key, url, desc, aux_keys = self._available_providers[idx]

        # Update description
        self._desc_text.SetValue(desc)
        set_accessible_name(self._desc_text, f"{name}: {desc}")

        # Update "Get key" link
        self._get_key_link.SetURL(url)
        self._get_key_link.SetLabel(f"Get a {name} API key")

        # Clear and rebuild auxiliary fields
        self._aux_sizer.Clear(delete_windows=True)
        self._aux_fields.clear()

        for aux_kid, aux_label, aux_help in aux_keys:
            row = wx.BoxSizer(wx.HORIZONTAL)
            lbl = wx.StaticText(self._aux_panel, label=aux_label)
            txt = wx.TextCtrl(self._aux_panel, style=wx.TE_PASSWORD, size=(250, -1))
            label_control(lbl, txt)
            set_accessible_help(txt, aux_help)

            # Pre-fill from keystore
            existing = self._key_store.get_key(aux_kid)
            if existing:
                txt.SetValue(existing)

            row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
            row.Add(txt, 1, wx.EXPAND)
            self._aux_sizer.Add(row, 0, wx.EXPAND | wx.ALL, 4)
            self._aux_fields[aux_kid] = txt

        self._aux_panel.Layout()

        # Pre-fill primary key if stored
        existing_key = self._key_store.get_key(kid)
        if existing_key:
            self._key_txt.SetValue("\u2022" * 8)
            self._key_txt.SetModified(False)
            activated = set(self._settings.general.activated_providers)
            if kid in activated:
                self._prefill_lbl.SetLabel("\u2713 Already activated — re-validate to update")
            else:
                self._prefill_lbl.SetLabel("Key found in credential store — validate to activate")
        else:
            self._key_txt.SetValue("")
            self._prefill_lbl.SetLabel("")

        # Reset status
        self._status_text.SetValue("Enter your API key, then click Validate && Activate.")
        self._btn_validate.Enable(bool(self._key_txt.GetValue().strip()))

        # Build provider-specific settings
        self._build_provider_settings(kid)

        self._content_panel.Layout()
        self.Layout()

    def _on_key_changed(self, _event: wx.CommandEvent) -> None:
        """Enable/disable validate button based on key input."""
        has_key = bool(self._key_txt.GetValue().strip())
        has_provider = self._selected_provider >= 0
        self._btn_validate.Enable(has_key and has_provider)

    def _on_validate(self, _event: wx.CommandEvent) -> None:
        """Validate the entered API key and activate the provider."""
        if self._selected_provider < 0:
            return

        kid, name, pm_key, _url, _desc, aux_keys = self._available_providers[
            self._selected_provider
        ]

        # Get primary key
        raw = self._key_txt.GetValue().strip()
        if not raw or raw == "\u2022" * 8:
            raw = self._key_store.get_key(kid) or ""
        if not raw:
            self._status_text.SetValue("\u2717 No API key entered.")
            return

        # Build validation key string (handle multi-key providers)
        api_key = raw
        if kid == "aws_access_key":
            secret = self._aux_fields.get("aws_secret_key")
            region = self._aux_fields.get("aws_region")
            secret_val = secret.GetValue().strip() if secret else ""
            region_val = region.GetValue().strip() if region else ""
            if not secret_val or not region_val:
                self._status_text.SetValue("\u2717 Please enter the AWS Secret Key and Region.")
                return
            api_key = f"{raw}:{secret_val}:{region_val}"

        # Disable controls during validation
        self._btn_validate.Disable()
        self._provider_choice.Disable()
        self._key_txt.Disable()
        for txt in self._aux_fields.values():
            txt.Disable()
        self._progress.Show()
        self._progress.Pulse()
        self._status_text.SetValue(f"\u2026 Validating {name} credentials\u2026")
        self.Layout()

        def _do_validate() -> None:
            try:
                from bits_whisperer.core.provider_manager import ProviderManager

                pm = ProviderManager()

                # Special handling for Azure (needs region)
                if kid == "azure":
                    from bits_whisperer.providers.azure_speech import AzureSpeechProvider

                    region_field = self._aux_fields.get("azure_region")
                    region = region_field.GetValue().strip() if region_field else "eastus"
                    provider = AzureSpeechProvider(region=region)
                else:
                    provider = pm.get_provider(pm_key)

                if provider is None:
                    safe_call_after(
                        self._on_validate_result,
                        kid,
                        name,
                        raw,
                        False,
                        "Provider SDK not installed. Install it from "
                        "Tools > Manage Models, then try again.",
                    )
                    return

                result = provider.validate_api_key(api_key)
                safe_call_after(self._on_validate_result, kid, name, raw, result, "")
            except Exception as exc:
                safe_call_after(self._on_validate_result, kid, name, raw, False, str(exc))

        threading.Thread(target=_do_validate, daemon=True, name=f"validate-{kid}").start()

    def _on_validate_result(
        self,
        kid: str,
        name: str,
        raw_key: str,
        success: bool,
        error: str,
    ) -> None:
        """Handle validation result on the UI thread.

        Args:
            kid: KeyStore provider identifier.
            name: Human-readable provider name.
            raw_key: The raw API key value.
            success: Whether validation succeeded.
            error: Error message if failed.
        """
        # Re-enable controls
        self._btn_validate.Enable()
        self._provider_choice.Enable()
        self._key_txt.Enable()
        for txt in self._aux_fields.values():
            txt.Enable()
        self._progress.Hide()
        self.Layout()

        if success:
            # Store the key
            if raw_key != "\u2022" * 8:
                self._key_store.store_key(kid, raw_key)

            # Store auxiliary keys
            if self._selected_provider >= 0:
                _kid, _name, _pm, _url, _desc, aux_keys = self._available_providers[
                    self._selected_provider
                ]
                for aux_kid, _lbl, _hlp in aux_keys:
                    field = self._aux_fields.get(aux_kid)
                    if field:
                        val = field.GetValue().strip()
                        if val and val != "\u2022" * 8:
                            self._key_store.store_key(aux_kid, val)

            # Add to activated providers
            activated = list(self._settings.general.activated_providers)
            if kid not in activated:
                activated.append(kid)
                self._settings.general.activated_providers = activated

            # Save provider-specific settings
            prov_settings = self._collect_provider_settings(kid)
            if prov_settings:
                self._settings.provider_settings.set(kid, prov_settings)

            self._settings.save()
            logger.info("Provider '%s' activated", kid)

            self._activated_provider = kid
            self._status_text.SetValue(
                f"\u2713 {name} validated and activated!\n"
                f"You can now use {name} for transcription."
            )
            self._prefill_lbl.SetLabel("\u2713 Activated")

            # Update the choice text
            idx = self._provider_choice.GetSelection()
            if idx >= 0:
                # Rebuild choice to show updated status
                self._provider_choice.SetString(idx, f"{name} (already activated)")

            logger.info("Provider '%s' (%s) validated successfully", name, kid)
        else:
            detail = f": {error}" if error else ""
            self._status_text.SetValue(
                f"\u2717 Validation failed for {name}{detail}\n\n"
                "Please check your API key and try again. "
                "You can get a new key from the link above."
            )
            logger.warning("Provider '%s' validation failed%s", name, detail)

    def _build_provider_settings(self, provider_id: str) -> None:
        """Build provider-specific settings controls for the selected provider.

        Dynamically creates checkboxes, dropdowns, spin controls, or text
        fields based on ``_PROVIDER_SETTINGS_DEFS``. Pre-fills values from
        stored ``ProviderDefaultSettings`` in app settings.

        Args:
            provider_id: KeyStore identifier for the provider.
        """
        # Clear existing controls
        self._prov_settings_inner.Clear(delete_windows=True)
        self._settings_controls.clear()

        defs = _PROVIDER_SETTINGS_DEFS.get(provider_id, [])
        if not defs:
            self._prov_settings_sizer.ShowItems(False)
            self._content_panel.Layout()
            self.Layout()
            return

        # Load previously saved settings
        saved: dict[str, Any] = self._settings.provider_settings.get(provider_id)

        panel = self._prov_settings_panel
        for sid, label_text, ctype, default, extra in defs:
            saved_val = saved.get(sid, default) if saved else default

            lbl = wx.StaticText(panel, label=label_text)

            ctrl: wx.Control
            if ctype == "check":
                ctrl = wx.CheckBox(panel)
                ctrl.SetValue(bool(saved_val))
                set_accessible_name(ctrl, label_text)
            elif ctype == "choice":
                choices: list[str] = extra or []
                ctrl = wx.Choice(panel, choices=choices)
                idx = 0
                if isinstance(saved_val, str) and saved_val in choices:
                    idx = choices.index(saved_val)
                ctrl.SetSelection(idx)
                set_accessible_name(ctrl, label_text)
            elif ctype == "spin":
                lo, hi = extra if extra else (-100, 100)
                ctrl = wx.SpinCtrl(
                    panel, min=lo, max=hi, initial=int(saved_val)
                )
                set_accessible_name(ctrl, label_text)
            elif ctype == "text":
                ctrl = wx.TextCtrl(panel, value=str(saved_val), size=(200, -1))
                set_accessible_name(ctrl, label_text)
            else:
                continue

            label_control(lbl, ctrl)
            self._prov_settings_inner.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            self._prov_settings_inner.Add(ctrl, 1, wx.EXPAND)
            self._settings_controls[sid] = ctrl

        self._prov_settings_sizer.ShowItems(True)
        self._prov_settings_panel.Layout()
        self._content_panel.Layout()
        self.Layout()

    def _collect_provider_settings(self, provider_id: str) -> dict[str, Any]:
        """Collect current values from provider settings controls.

        Args:
            provider_id: KeyStore identifier for the provider.

        Returns:
            Dict mapping setting IDs to their current values.
        """
        defs = _PROVIDER_SETTINGS_DEFS.get(provider_id, [])
        result: dict[str, Any] = {}
        for sid, _label, ctype, _default, extra in defs:
            ctrl = self._settings_controls.get(sid)
            if ctrl is None:
                continue
            if ctype == "check" and isinstance(ctrl, wx.CheckBox):
                result[sid] = ctrl.GetValue()
            elif ctype == "choice" and isinstance(ctrl, wx.Choice):
                idx = ctrl.GetSelection()
                choices: list[str] = extra or []
                result[sid] = choices[idx] if 0 <= idx < len(choices) else ""
            elif ctype == "spin" and isinstance(ctrl, wx.SpinCtrl):
                result[sid] = ctrl.GetValue()
            elif ctype == "text" and isinstance(ctrl, wx.TextCtrl):
                result[sid] = ctrl.GetValue().strip()
        return result

    def _on_close(self, _event: wx.CommandEvent) -> None:
        """Close the dialog."""
        if self._activated_provider:
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)

    @property
    def activated_provider_id(self) -> str | None:
        """Return the keystore ID of the most recently activated provider."""
        return self._activated_provider
