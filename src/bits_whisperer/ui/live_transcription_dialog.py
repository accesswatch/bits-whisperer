"""Live transcription panel for real-time microphone capture.

Provides start/stop/pause controls, real-time text display, and
device selection — all fully keyboard-accessible and screen-reader
compatible.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.live_transcription import (
    LiveTranscriptionService,
)
from bits_whisperer.core.settings import AppSettings
from bits_whisperer.utils.accessibility import (
    announce_status,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)


class LiveTranscriptionDialog(wx.Dialog):
    """Dialog for live microphone transcription.

    Provides real-time speech-to-text from the microphone using
    the local faster-whisper model. The dialog shows controls for
    start/stop/pause, a device selector, and a scrolling text area
    displaying the transcription in real time.
    """

    def __init__(self, parent: wx.Window, main_frame: MainFrame) -> None:
        """Initialise the live transcription dialog.

        Args:
            parent: Parent window.
            main_frame: Reference to the main frame for settings access.
        """
        super().__init__(
            parent,
            title="Live Transcription",
            size=(700, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Live Transcription")
        self.SetMinSize((500, 350))
        self.Centre()

        self._main_frame = main_frame
        self._settings = AppSettings.load()
        self._service: LiveTranscriptionService | None = None

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------ #
    # UI Layout                                                            #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        root = wx.BoxSizer(wx.VERTICAL)

        # -- Device selection row --
        device_row = wx.BoxSizer(wx.HORIZONTAL)
        device_label = wx.StaticText(self, label="&Input Device:")
        set_accessible_name(device_label, "Input Device")
        device_row.Add(device_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._device_choice = wx.Choice(self, choices=["System Default"])
        set_accessible_name(self._device_choice, "Select audio input device")
        set_accessible_help(
            self._device_choice,
            "Choose the microphone to use for live transcription",
        )
        self._device_choice.SetSelection(0)
        device_row.Add(self._device_choice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Model selector
        model_label = wx.StaticText(self, label="&Model:")
        set_accessible_name(model_label, "Model")
        device_row.Add(model_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        from bits_whisperer.utils.constants import WHISPER_MODELS

        model_names = [f"{m.name}" for m in WHISPER_MODELS]
        self._model_choice = wx.Choice(self, choices=model_names)
        set_accessible_name(self._model_choice, "Select Whisper model for live transcription")
        # Select the model from settings
        current_model = self._settings.live_transcription.model
        for i, m in enumerate(WHISPER_MODELS):
            if m.id == current_model:
                self._model_choice.SetSelection(i)
                break
        else:
            self._model_choice.SetSelection(2)  # Default to 'base'
        device_row.Add(self._model_choice, 0, wx.ALIGN_CENTER_VERTICAL)

        root.Add(device_row, 0, wx.ALL | wx.EXPAND, 10)

        # -- Control buttons row --
        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        self._start_btn = wx.Button(self, label="&Start")
        set_accessible_name(self._start_btn, "Start live transcription")
        set_accessible_help(
            self._start_btn,
            "Begin capturing audio from the microphone and transcribing in real time",
        )
        btn_row.Add(self._start_btn, 0, wx.RIGHT, 4)

        self._pause_btn = wx.Button(self, label="&Pause")
        set_accessible_name(self._pause_btn, "Pause live transcription")
        self._pause_btn.Enable(False)
        btn_row.Add(self._pause_btn, 0, wx.RIGHT, 4)

        self._stop_btn = wx.Button(self, label="S&top")
        set_accessible_name(self._stop_btn, "Stop live transcription")
        self._stop_btn.Enable(False)
        btn_row.Add(self._stop_btn, 0, wx.RIGHT, 16)

        self._copy_btn = wx.Button(self, label="&Copy All")
        set_accessible_name(self._copy_btn, "Copy full transcript to clipboard")
        btn_row.Add(self._copy_btn, 0, wx.RIGHT, 4)

        self._clear_btn = wx.Button(self, label="C&lear")
        set_accessible_name(self._clear_btn, "Clear transcript text")
        btn_row.Add(self._clear_btn, 0)

        root.Add(btn_row, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        # -- Status indicator --
        self._status_label = wx.StaticText(self, label="Status: Ready")
        set_accessible_name(self._status_label, "Live transcription status")
        root.Add(self._status_label, 0, wx.ALL, 10)

        # -- Transcript display --
        transcript_label = wx.StaticText(self, label="&Transcript:")
        set_accessible_name(transcript_label, "Transcript label")
        root.Add(transcript_label, 0, wx.LEFT | wx.RIGHT, 10)

        self._text_ctrl = wx.TextCtrl(
            self,
            style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_WORDWRAP),
        )
        set_accessible_name(self._text_ctrl, "Live transcript text")
        set_accessible_help(
            self._text_ctrl,
            "Real-time transcript of spoken words. Text appears as you speak.",
        )
        font = wx.Font(
            11,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
        self._text_ctrl.SetFont(font)
        root.Add(self._text_ctrl, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        # -- Close button --
        close_btn = wx.Button(self, wx.ID_CLOSE, label="&Close")
        set_accessible_name(close_btn, "Close live transcription dialog")
        root.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(root)

        # Populate device list
        self._populate_devices()

    def _bind_events(self) -> None:
        """Bind all event handlers."""
        self._start_btn.Bind(wx.EVT_BUTTON, self._on_start)
        self._pause_btn.Bind(wx.EVT_BUTTON, self._on_pause)
        self._stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)
        self._copy_btn.Bind(wx.EVT_BUTTON, self._on_copy)
        self._clear_btn.Bind(wx.EVT_BUTTON, self._on_clear)
        self.Bind(wx.EVT_BUTTON, self._on_close, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ------------------------------------------------------------------ #
    # Device listing                                                       #
    # ------------------------------------------------------------------ #

    def _populate_devices(self) -> None:
        """Populate the device choice with available input devices."""
        devices = LiveTranscriptionService.list_input_devices()
        self._device_list = [None] + devices  # None = system default
        choices = ["System Default"]
        for dev in devices:
            choices.append(f"{dev['name']}")

        self._device_choice.Clear()
        for c in choices:
            self._device_choice.Append(c)
        self._device_choice.SetSelection(0)

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_start(self, _event: wx.CommandEvent) -> None:
        """Start live transcription."""
        from bits_whisperer.utils.constants import WHISPER_MODELS

        # Get selected model
        model_idx = self._model_choice.GetSelection()
        model_id = WHISPER_MODELS[model_idx].id if model_idx >= 0 else "base"

        # Get selected device
        device_idx = self._device_choice.GetSelection()
        device_name = ""
        if device_idx > 0 and device_idx < len(self._device_list):
            dev = self._device_list[device_idx]
            if dev:
                device_name = dev["name"]

        # Update settings
        settings = self._settings.live_transcription
        settings.model = model_id
        settings.input_device = device_name

        # Create and start service
        self._service = LiveTranscriptionService(settings)
        self._service.set_text_callback(self._on_text_received)

        try:
            self._service.start()
        except Exception as exc:
            wx.MessageBox(
                f"Could not start live transcription:\n\n{exc}",
                "Microphone Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        self._start_btn.Enable(False)
        self._pause_btn.Enable(True)
        self._stop_btn.Enable(True)
        self._device_choice.Enable(False)
        self._model_choice.Enable(False)
        self._status_label.SetLabel("Status: Listening...")
        self._text_ctrl.AppendText("[Live transcription started]\n\n")

    def _on_pause(self, _event: wx.CommandEvent) -> None:
        """Toggle pause/resume."""
        if not self._service:
            return

        if self._service.is_paused:
            self._service.resume()
            self._pause_btn.SetLabel("&Pause")
            self._status_label.SetLabel("Status: Listening...")
        else:
            self._service.pause()
            self._pause_btn.SetLabel("&Resume")
            self._status_label.SetLabel("Status: Paused")

    def _on_stop(self, _event: wx.CommandEvent) -> None:
        """Stop live transcription."""
        if self._service:
            self._service.stop()

        self._start_btn.Enable(True)
        self._pause_btn.Enable(False)
        self._stop_btn.Enable(False)
        self._device_choice.Enable(True)
        self._model_choice.Enable(True)
        self._pause_btn.SetLabel("&Pause")
        self._status_label.SetLabel("Status: Stopped")
        self._text_ctrl.AppendText("\n[Live transcription stopped]\n")

    def _on_copy(self, _event: wx.CommandEvent) -> None:
        """Copy full transcript to clipboard."""
        text = self._text_ctrl.GetValue()
        if text and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            announce_status(self._main_frame, "Live transcript copied to clipboard")

    def _on_clear(self, _event: wx.CommandEvent) -> None:
        """Clear the transcript display."""
        self._text_ctrl.Clear()

    def _on_close(self, _event) -> None:
        """Close the dialog, stopping transcription if running."""
        if self._service and self._service.is_running:
            self._service.stop()
        self.EndModal(wx.ID_CLOSE)

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _on_text_received(self, text: str, is_final: bool) -> None:
        """Called from the transcription worker with new text.

        Uses wx.CallAfter for thread safety.

        Args:
            text: Transcribed text.
            is_final: Whether this is a final (non-interim) result.
        """
        safe_call_after(self._append_text, text, is_final)

    def _append_text(self, text: str, is_final: bool) -> None:
        """Append text to the transcript display (UI thread).

        Args:
            text: Transcribed text.
            is_final: Whether this is a final result.
        """
        if is_final:
            self._text_ctrl.AppendText(text + "\n")
            state = self._service.get_state() if self._service else None
            if state:
                self._status_label.SetLabel(
                    f"Status: Listening... ({state.total_segments} segments)"
                )
