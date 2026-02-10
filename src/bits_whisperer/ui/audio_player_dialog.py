"""Audio preview dialog with playback controls and clip selection."""

from __future__ import annotations

import logging
from pathlib import Path

import wx

from bits_whisperer.core.audio_player import AudioPlayer, AudioPlayerError
from bits_whisperer.core.settings import AppSettings, PlaybackSettings
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)

logger = logging.getLogger(__name__)


class AudioPlayerDialog(wx.Dialog):
    """Dialog for previewing audio and selecting a clip range."""

    def __init__(
        self,
        parent: wx.Window,
        file_path: str,
        *,
        selection_start: float | None = None,
        selection_end: float | None = None,
        settings: PlaybackSettings | None = None,
    ) -> None:
        """Initialise the audio preview dialog."""
        super().__init__(
            parent,
            title="Audio Preview",
            size=(700, 480),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Audio preview dialog")
        self.SetMinSize((600, 420))
        self.CentreOnParent()

        self._file_path = file_path
        self._settings = settings or AppSettings.load().playback
        self._player = AudioPlayer()
        self._player.set_state_callback(
            lambda state: safe_call_after(
                self._on_player_state,
                state,
            ),
        )
        self._player.set_progress_callback(
            lambda pos, dur: safe_call_after(
                self._on_player_progress,
                pos,
                dur,
            ),
        )

        self._duration = 0.0
        self._selection_start = selection_start
        self._selection_end = selection_end

        self._build_ui()
        self._bind_events()
        self._load_audio()

    @property
    def selection_start(self) -> float | None:
        """Selected clip start in seconds, or None for full file."""
        return self._selection_start

    @property
    def selection_end(self) -> float | None:
        """Selected clip end in seconds, or None for full file."""
        return self._selection_end

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)

        fname = Path(self._file_path).name
        header = wx.StaticText(self, label=f"File: {fname}")
        header.SetFont(header.GetFont().Bold())
        set_accessible_name(header, "Audio preview file name")
        root.Add(header, 0, wx.ALL, 8)

        # Playback controls
        controls_box = wx.StaticBox(self, label="Playback")
        set_accessible_name(controls_box, "Playback controls")
        controls = wx.StaticBoxSizer(controls_box, wx.VERTICAL)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_play = wx.Button(self, label="&Play")
        set_accessible_name(self._btn_play, "Play audio")
        btn_row.Add(self._btn_play, 0, wx.RIGHT, 6)

        self._btn_pause = wx.Button(self, label="&Pause")
        set_accessible_name(self._btn_pause, "Pause audio")
        self._btn_pause.Enable(False)
        btn_row.Add(self._btn_pause, 0, wx.RIGHT, 6)

        self._btn_stop = wx.Button(self, label="S&top")
        set_accessible_name(self._btn_stop, "Stop audio")
        self._btn_stop.Enable(False)
        btn_row.Add(self._btn_stop, 0, wx.RIGHT, 12)

        self._btn_back = wx.Button(
            self,
            label=f"&Back {self._settings.jump_back_seconds}s",
        )
        set_accessible_name(self._btn_back, "Seek backward")
        btn_row.Add(self._btn_back, 0, wx.RIGHT, 6)

        self._btn_fwd = wx.Button(
            self,
            label=f"&Forward {self._settings.jump_forward_seconds}s",
        )
        set_accessible_name(self._btn_fwd, "Seek forward")
        btn_row.Add(self._btn_fwd, 0)

        controls.Add(btn_row, 0, wx.ALL, 6)

        pos_row = wx.BoxSizer(wx.HORIZONTAL)
        self._pos_label = wx.StaticText(self, label="00:00 / 00:00")
        set_accessible_name(self._pos_label, "Playback position")
        pos_row.Add(self._pos_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._pos_slider = wx.Slider(self, value=0, minValue=0, maxValue=100)
        set_accessible_name(self._pos_slider, "Playback position slider")
        set_accessible_help(self._pos_slider, "Seek within the audio")
        pos_row.Add(self._pos_slider, 1, wx.ALIGN_CENTER_VERTICAL)

        controls.Add(pos_row, 0, wx.ALL | wx.EXPAND, 6)

        # Speed controls
        speed_row = wx.BoxSizer(wx.HORIZONTAL)
        speed_label = wx.StaticText(self, label="Speed:")
        set_accessible_name(speed_label, "Playback speed label")
        speed_row.Add(speed_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self._speed_slider = wx.Slider(
            self,
            value=100,
            minValue=25,
            maxValue=400,
        )
        set_accessible_name(
            self._speed_slider,
            "Playback speed slider",
        )
        speed_row.Add(
            self._speed_slider,
            1,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )

        self._speed_spin = wx.SpinCtrlDouble(
            self,
            min=0.25,
            max=8.0,
            inc=self._settings.speed_step,
            initial=self._settings.default_speed,
        )
        self._speed_spin.SetDigits(2)
        set_accessible_name(self._speed_spin, "Playback speed")
        set_accessible_help(self._speed_spin, "Adjust playback speed")
        speed_row.Add(
            self._speed_spin,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            6,
        )

        self._btn_slower = wx.Button(self, label="S&lower")
        set_accessible_name(self._btn_slower, "Decrease playback speed")
        speed_row.Add(self._btn_slower, 0, wx.RIGHT, 4)

        self._btn_faster = wx.Button(self, label="&Faster")
        set_accessible_name(self._btn_faster, "Increase playback speed")
        speed_row.Add(self._btn_faster, 0)

        controls.Add(speed_row, 0, wx.ALL | wx.EXPAND, 6)
        root.Add(controls, 0, wx.ALL | wx.EXPAND, 8)

        # Selection controls
        sel_box = wx.StaticBox(self, label="Selection")
        set_accessible_name(sel_box, "Clip selection")
        sel = wx.StaticBoxSizer(sel_box, wx.VERTICAL)

        sel_grid = wx.FlexGridSizer(cols=3, vgap=6, hgap=8)
        sel_grid.AddGrowableCol(1, 1)

        lbl_start = wx.StaticText(self, label="Start (s):")
        self._start_spin = wx.SpinCtrlDouble(
            self,
            min=0.0,
            max=0.0,
            inc=0.1,
            initial=0.0,
        )
        self._start_spin.SetDigits(2)
        set_accessible_name(
            self._start_spin,
            "Selection start time",
        )
        self._btn_set_start = wx.Button(
            self,
            label="Set to &Current",
        )
        set_accessible_name(
            self._btn_set_start,
            "Set selection start to current position",
        )

        sel_grid.Add(lbl_start, 0, wx.ALIGN_CENTER_VERTICAL)
        sel_grid.Add(self._start_spin, 0, wx.EXPAND)
        sel_grid.Add(self._btn_set_start, 0)

        lbl_end = wx.StaticText(self, label="End (s):")
        self._end_spin = wx.SpinCtrlDouble(
            self,
            min=0.0,
            max=0.0,
            inc=0.1,
            initial=0.0,
        )
        self._end_spin.SetDigits(2)
        set_accessible_name(
            self._end_spin,
            "Selection end time",
        )
        self._btn_set_end = wx.Button(
            self,
            label="Set to C&urrent",
        )
        set_accessible_name(
            self._btn_set_end,
            "Set selection end to current position",
        )

        sel_grid.Add(lbl_end, 0, wx.ALIGN_CENTER_VERTICAL)
        sel_grid.Add(self._end_spin, 0, wx.EXPAND)
        sel_grid.Add(self._btn_set_end, 0)

        sel.Add(sel_grid, 0, wx.ALL | wx.EXPAND, 6)

        self._selection_label = wx.StaticText(
            self,
            label="Selection: full file",
        )
        set_accessible_name(self._selection_label, "Selection summary")
        sel.Add(self._selection_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        btn_sel_row = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_clear_selection = wx.Button(self, label="&Clear Selection")
        set_accessible_name(self._btn_clear_selection, "Clear selection")
        btn_sel_row.Add(self._btn_clear_selection, 0)
        sel.Add(btn_sel_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        root.Add(sel, 0, wx.ALL | wx.EXPAND, 8)

        # Buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        btns = wx.BoxSizer(wx.HORIZONTAL)
        btns.AddStretchSpacer()

        self._btn_use_full = wx.Button(self, label="Use &Full File")
        set_accessible_name(
            self._btn_use_full,
            "Use full file for transcription",
        )
        btns.Add(self._btn_use_full, 0, wx.RIGHT, 6)

        self._btn_use_selection = wx.Button(
            self,
            wx.ID_OK,
            label="Use &Selection",
        )
        set_accessible_name(
            self._btn_use_selection,
            "Use selection for transcription",
        )
        btns.Add(self._btn_use_selection, 0, wx.RIGHT, 6)

        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="&Cancel")
        set_accessible_name(btn_cancel, "Cancel audio preview")
        btns.Add(btn_cancel, 0)

        root.Add(btns, 0, wx.ALL | wx.EXPAND, 8)

        self.SetSizer(root)
        make_panel_accessible(self)

        self._timer = wx.Timer(self)

    def _bind_events(self) -> None:
        self._btn_play.Bind(wx.EVT_BUTTON, self._on_play)
        self._btn_pause.Bind(wx.EVT_BUTTON, self._on_pause)
        self._btn_stop.Bind(wx.EVT_BUTTON, self._on_stop)
        self._btn_back.Bind(
            wx.EVT_BUTTON,
            lambda e: self._seek_relative(
                -float(self._settings.jump_back_seconds),
            ),
        )
        self._btn_fwd.Bind(
            wx.EVT_BUTTON,
            lambda e: self._seek_relative(
                float(self._settings.jump_forward_seconds),
            ),
        )
        self._pos_slider.Bind(wx.EVT_SLIDER, self._on_seek_slider)

        self._speed_slider.Bind(wx.EVT_SLIDER, self._on_speed_slider)
        self._speed_spin.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_speed_spin)
        self._btn_slower.Bind(wx.EVT_BUTTON, lambda e: self._step_speed(-1))
        self._btn_faster.Bind(wx.EVT_BUTTON, lambda e: self._step_speed(1))

        self._btn_set_start.Bind(wx.EVT_BUTTON, self._set_start_to_current)
        self._btn_set_end.Bind(wx.EVT_BUTTON, self._set_end_to_current)
        self._start_spin.Bind(
            wx.EVT_SPINCTRLDOUBLE,
            self._on_selection_changed,
        )
        self._end_spin.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_selection_changed)
        self._btn_clear_selection.Bind(wx.EVT_BUTTON, self._on_clear_selection)

        self._btn_use_full.Bind(wx.EVT_BUTTON, self._on_use_full)
        self.Bind(wx.EVT_BUTTON, self._on_use_selection, id=wx.ID_OK)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    def _load_audio(self) -> None:
        try:
            self._player.load(
                self._file_path,
                selection_start=self._selection_start,
                selection_end=self._selection_end,
            )
        except AudioPlayerError as exc:
            accessible_message_box(
                f"Audio preview unavailable:\n\n{exc}",
                "Audio Preview Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            self.EndModal(wx.ID_CANCEL)
            return

        self._duration = self._player.duration
        self._pos_slider.SetRange(0, max(1, int(self._duration)))

        self._start_spin.SetRange(0.0, max(0.0, self._duration))
        self._end_spin.SetRange(0.0, max(0.0, self._duration))

        if self._selection_start is not None:
            self._start_spin.SetValue(self._selection_start)
        if self._selection_end is not None:
            self._end_spin.SetValue(self._selection_end)

        self._apply_speed_settings()
        self._update_selection_label()
        self._timer.Start(200)

    def _apply_speed_settings(self) -> None:
        min_speed = self._settings.min_speed
        max_speed = self._settings.max_speed
        step = self._settings.speed_step

        if max_speed < min_speed:
            max_speed = min_speed

        self._speed_spin.SetRange(min_speed, max_speed)
        self._speed_spin.SetIncrement(step)

        slider_min = int(min_speed * 100)
        slider_max = int(max_speed * 100)
        self._speed_slider.SetRange(slider_min, slider_max)
        default_speed = max(
            min_speed,
            min(self._settings.default_speed, max_speed),
        )
        self._speed_slider.SetValue(int(default_speed * 100))

        self._set_speed(default_speed)

    # ------------------------------------------------------------------ #
    # Playback                                                             #
    # ------------------------------------------------------------------ #

    def _on_play(self, _event: wx.CommandEvent) -> None:
        try:
            self._player.play()
        except AudioPlayerError as exc:
            accessible_message_box(
                f"Playback failed:\n\n{exc}",
                "Audio Preview Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_pause(self, _event: wx.CommandEvent) -> None:
        self._player.pause()

    def _on_stop(self, _event: wx.CommandEvent) -> None:
        self._player.stop()

    def _on_seek_slider(self, _event: wx.CommandEvent) -> None:
        pos = float(self._pos_slider.GetValue())
        self._player.seek(pos)

    def _seek_relative(self, delta: float) -> None:
        self._player.seek(self._player.position + delta)

    def _on_speed_slider(self, _event: wx.CommandEvent) -> None:
        value = self._speed_slider.GetValue() / 100.0
        self._speed_spin.SetValue(value)
        self._set_speed(value)

    def _on_speed_spin(self, _event: wx.CommandEvent) -> None:
        value = self._speed_spin.GetValue()
        self._speed_slider.SetValue(int(value * 100))
        self._set_speed(value)

    def _step_speed(self, direction: int) -> None:
        step = direction * self._settings.speed_step
        value = self._speed_spin.GetValue() + step
        value = max(
            self._settings.min_speed,
            min(value, self._settings.max_speed),
        )
        self._speed_spin.SetValue(value)
        self._speed_slider.SetValue(int(value * 100))
        self._set_speed(value)

    def _set_speed(self, value: float) -> None:
        self._player.set_speed(value)
        announce_status(self, f"Speed {value:.2f}x")

    # ------------------------------------------------------------------ #
    # Selection                                                            #
    # ------------------------------------------------------------------ #

    def _set_start_to_current(self, _event: wx.CommandEvent) -> None:
        self._start_spin.SetValue(self._player.position)
        self._on_selection_changed(None)

    def _set_end_to_current(self, _event: wx.CommandEvent) -> None:
        self._end_spin.SetValue(self._player.position)
        self._on_selection_changed(None)

    def _on_selection_changed(self, _event: wx.CommandEvent | None) -> None:
        start = self._start_spin.GetValue()
        end = self._end_spin.GetValue()

        if end > 0 and end <= start:
            self._selection_end = None
        else:
            self._selection_end = end if end > 0 else None

        self._selection_start = start if start > 0 else 0.0
        self._player.set_clip_range(self._selection_start, self._selection_end)
        self._update_selection_label()

    def _on_clear_selection(self, _event: wx.CommandEvent) -> None:
        self._selection_start = None
        self._selection_end = None
        self._start_spin.SetValue(0.0)
        self._end_spin.SetValue(0.0)
        self._player.set_clip_range(None, None)
        self._update_selection_label()

    def _on_use_full(self, _event: wx.CommandEvent) -> None:
        self._selection_start = None
        self._selection_end = None
        self.EndModal(wx.ID_OK)

    def _on_use_selection(self, _event: wx.CommandEvent) -> None:
        start = self._start_spin.GetValue()
        end = self._end_spin.GetValue()
        if end > 0 and end <= start:
            accessible_message_box(
                "Selection end must be after the start time.",
                "Invalid Selection",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        self._selection_start = start if start > 0 else None
        self._selection_end = end if end > 0 else None
        self.EndModal(wx.ID_OK)

    def _update_selection_label(self) -> None:
        no_end = self._selection_end is None
        no_start = (self._selection_start or 0.0) <= 0.0
        if no_end and no_start:
            self._selection_label.SetLabel("Selection: full file")
            return

        start = self._selection_start or 0.0
        end = self._selection_end
        if end is None:
            self._selection_label.SetLabel(f"Selection: from {self._fmt_time(start)} to end")
        else:
            self._selection_label.SetLabel(
                f"Selection: {self._fmt_time(start)} to {self._fmt_time(end)}"
            )

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _on_player_state(self, state: str) -> None:
        playing = state == "playing"
        finished = state == "finished"

        self._btn_play.Enable(not playing)
        self._btn_pause.Enable(playing)
        self._btn_stop.Enable(playing)

        if finished:
            self._btn_play.Enable(True)
            self._btn_pause.Enable(False)
            self._btn_stop.Enable(False)

    def _on_player_progress(self, pos: float, dur: float) -> None:
        if dur > 0:
            self._pos_slider.SetValue(min(int(pos), int(dur)))
        pos_txt = self._fmt_time(pos)
        dur_txt = self._fmt_time(dur)
        self._pos_label.SetLabel(f"{pos_txt} / {dur_txt}")

    def _on_timer(self, _event: wx.TimerEvent) -> None:
        pos = self._player.position
        pos_txt = self._fmt_time(pos)
        dur_txt = self._fmt_time(self._duration)
        self._pos_label.SetLabel(f"{pos_txt} / {dur_txt}")
        if self._duration > 0:
            self._pos_slider.SetValue(min(int(pos), int(self._duration)))

    def _on_close(self, _event: wx.CloseEvent) -> None:
        self._timer.Stop()
        self._player.close()
        self.EndModal(wx.ID_CANCEL)

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds < 0:
            seconds = 0.0
        total = int(seconds)
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
