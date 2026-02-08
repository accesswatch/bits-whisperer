"""Guided agent file builder for GitHub Copilot.

Provides a form-based UI for creating and editing custom agent
configurations. Users can set the agent name, instructions,
tool permissions, model, and other settings without needing to
know the underlying metadata or markdown syntax.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.copilot_service import AgentConfig
from bits_whisperer.utils.accessibility import (
    announce_status,
    label_control,
    make_panel_accessible,
    safe_call_after,
    set_accessible_help,
    set_accessible_name,
)
from bits_whisperer.utils.constants import DATA_DIR

if TYPE_CHECKING:
    from bits_whisperer.ui.main_frame import MainFrame

logger = logging.getLogger(__name__)

_AGENTS_DIR = DATA_DIR / "agents"
_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

# Available tools that can be enabled/disabled
_AVAILABLE_TOOLS = [
    {
        "id": "search_transcript",
        "name": "Search Transcript",
        "description": "Search for specific text, keywords, or topics in the transcript",
    },
    {
        "id": "get_speakers",
        "name": "Get Speakers",
        "description": "Identify and list speakers found in the transcript",
    },
    {
        "id": "get_transcript_stats",
        "name": "Transcript Statistics",
        "description": "Get word count, line count, and other transcript statistics",
    },
]

# Preset instruction templates
_INSTRUCTION_PRESETS = {
    "General Assistant": (
        "You are a helpful transcript assistant. You help users understand, "
        "analyze, and work with audio transcripts. Be concise, clear, and helpful. "
        "When asked about the transcript, refer to specific parts and provide "
        "accurate information."
    ),
    "Meeting Summarizer": (
        "You are a meeting notes specialist. Your job is to create clear, "
        "actionable meeting summaries from transcripts. Focus on:\n"
        "- Key decisions made\n"
        "- Action items and their owners\n"
        "- Important discussion points\n"
        "- Follow-up items and deadlines\n"
        "Be concise and organized."
    ),
    "Interview Analyzer": (
        "You are an interview analysis expert. Help users extract insights "
        "from interview transcripts. Focus on:\n"
        "- Key responses and themes\n"
        "- Notable quotes\n"
        "- Candidate/interviewee strengths and areas of interest\n"
        "- Unanswered questions\n"
        "Maintain objectivity and support claims with transcript references."
    ),
    "Lecture Note Taker": (
        "You are a lecture notes assistant. Transform lecture transcripts "
        "into well-organized study notes. Focus on:\n"
        "- Main concepts and definitions\n"
        "- Key examples and explanations\n"
        "- Important formulas or processes\n"
        "- Questions raised during the lecture\n"
        "Use clear headings and bullet points."
    ),
    "Custom": "",
}


class AgentBuilderDialog(wx.Dialog):
    """Dialog for creating and editing Copilot agent configurations.

    Provides a guided, form-based experience so users can customize
    their AI assistant without needing to know markdown or metadata
    syntax. All fields are presented with clear labels and help text.
    """

    def __init__(
        self,
        parent: wx.Window,
        main_frame: MainFrame,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialise the agent builder.

        Args:
            parent: Parent window.
            main_frame: Reference to the main frame.
            config: Existing agent configuration to edit, or None for new.
        """
        super().__init__(
            parent,
            title="Agent Builder — Customize Your AI Assistant",
            size=(650, 620),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "Agent Builder")
        self.SetMinSize((540, 480))
        self.Centre()

        self._main_frame = main_frame
        self._config = config or AgentConfig()
        self._result_config: AgentConfig | None = None

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Build the dialog layout."""
        root = wx.BoxSizer(wx.VERTICAL)

        # Header
        header = wx.StaticText(
            self, label="Customize Your AI Assistant"
        )
        font = header.GetFont()
        font.SetPointSize(font.GetPointSize() + 3)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header.SetFont(font)
        set_accessible_name(header, "Agent builder")
        root.Add(header, 0, wx.ALL, 12)

        intro = wx.StaticText(
            self,
            label=(
                "Configure how your AI assistant behaves when analyzing "
                "transcripts. You can choose a preset or write custom instructions."
            ),
        )
        intro.Wrap(580)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Notebook with tabs
        notebook = wx.Notebook(self)
        set_accessible_name(notebook, "Agent configuration tabs")

        # Identity tab
        identity_panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        identity_panel.SetScrollRate(0, 20)
        make_panel_accessible(identity_panel)
        self._build_identity_tab(identity_panel)
        notebook.AddPage(identity_panel, "Identity")

        # Instructions tab
        instr_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(instr_panel)
        self._build_instructions_tab(instr_panel)
        notebook.AddPage(instr_panel, "Instructions")

        # Tools tab
        tools_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(tools_panel)
        self._build_tools_tab(tools_panel)
        notebook.AddPage(tools_panel, "Tools")

        # Welcome tab
        welcome_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(welcome_panel)
        self._build_welcome_tab(welcome_panel)
        notebook.AddPage(welcome_panel, "Welcome Message")

        root.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Bottom buttons
        root.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.TOP, 4)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        save_file_btn = wx.Button(self, label="Save to &File...")
        set_accessible_name(save_file_btn, "Save agent configuration to file")
        save_file_btn.Bind(wx.EVT_BUTTON, self._on_save_file)
        btn_sizer.Add(save_file_btn, 0, wx.RIGHT, 8)

        load_file_btn = wx.Button(self, label="&Load from File...")
        set_accessible_name(load_file_btn, "Load agent configuration from file")
        load_file_btn.Bind(wx.EVT_BUTTON, self._on_load_file)
        btn_sizer.Add(load_file_btn, 0, wx.RIGHT, 8)

        btn_sizer.AddStretchSpacer()

        ok_btn = wx.Button(self, wx.ID_OK, label="&Apply")
        cancel_btn = wx.Button(self, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(ok_btn, 0, wx.RIGHT, 4)
        btn_sizer.Add(cancel_btn, 0)

        root.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _build_identity_tab(self, parent: wx.ScrolledWindow) -> None:
        """Build the agent identity configuration tab."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Agent name
        name_box = wx.StaticBox(parent, label="Agent Name")
        set_accessible_name(name_box, "Agent name settings")
        name_sizer = wx.StaticBoxSizer(name_box, wx.VERTICAL)

        name_lbl = wx.StaticText(parent, label="&Name:")
        self._name_input = wx.TextCtrl(parent, size=(400, -1))
        set_accessible_name(self._name_input, "Agent display name")
        set_accessible_help(
            self._name_input,
            "The name shown in the chat panel header",
        )
        label_control(name_lbl, self._name_input)

        name_row = wx.BoxSizer(wx.HORIZONTAL)
        name_row.Add(name_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        name_row.Add(self._name_input, 1)
        name_sizer.Add(name_row, 0, wx.EXPAND | wx.ALL, 6)

        desc_lbl = wx.StaticText(parent, label="&Description:")
        self._desc_input = wx.TextCtrl(parent, size=(400, -1))
        set_accessible_name(self._desc_input, "Agent description")
        set_accessible_help(
            self._desc_input,
            "A short description of what this agent does",
        )
        label_control(desc_lbl, self._desc_input)

        desc_row = wx.BoxSizer(wx.HORIZONTAL)
        desc_row.Add(desc_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        desc_row.Add(self._desc_input, 1)
        name_sizer.Add(desc_row, 0, wx.EXPAND | wx.ALL, 6)

        sizer.Add(name_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # Model & parameters
        params_box = wx.StaticBox(parent, label="AI Model")
        set_accessible_name(params_box, "AI model settings")
        params_sizer = wx.StaticBoxSizer(params_box, wx.VERTICAL)

        model_row = wx.BoxSizer(wx.HORIZONTAL)
        model_lbl = wx.StaticText(parent, label="&Model:")
        models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
        ]
        self._model_choice = wx.Choice(parent, choices=models)
        set_accessible_name(self._model_choice, "Select AI model")
        label_control(model_lbl, self._model_choice)

        model_row.Add(model_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        model_row.Add(self._model_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        params_sizer.Add(model_row, 0, wx.EXPAND | wx.ALL, 6)

        temp_row = wx.BoxSizer(wx.HORIZONTAL)
        temp_lbl = wx.StaticText(parent, label="&Temperature:")
        self._temp_spin = wx.SpinCtrlDouble(
            parent, min=0.0, max=2.0, inc=0.1, initial=0.3
        )
        set_accessible_name(self._temp_spin, "AI temperature value")
        set_accessible_help(
            self._temp_spin,
            "Lower values produce focused output, higher values more creative",
        )
        label_control(temp_lbl, self._temp_spin)
        temp_row.Add(temp_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        temp_row.Add(self._temp_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        params_sizer.Add(temp_row, 0, wx.ALL, 6)

        tokens_row = wx.BoxSizer(wx.HORIZONTAL)
        tokens_lbl = wx.StaticText(parent, label="Max &Tokens:")
        self._tokens_spin = wx.SpinCtrl(parent, min=256, max=16384, initial=4096)
        set_accessible_name(self._tokens_spin, "Maximum response tokens")
        label_control(tokens_lbl, self._tokens_spin)
        tokens_row.Add(tokens_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        tokens_row.Add(self._tokens_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        params_sizer.Add(tokens_row, 0, wx.ALL, 6)

        sizer.Add(params_sizer, 0, wx.EXPAND | wx.ALL, 6)

        parent.SetSizer(sizer)

    def _build_instructions_tab(self, parent: wx.Panel) -> None:
        """Build the instructions configuration tab."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Preset selector
        preset_row = wx.BoxSizer(wx.HORIZONTAL)
        preset_lbl = wx.StaticText(parent, label="&Preset:")
        preset_names = list(_INSTRUCTION_PRESETS.keys())
        self._preset_choice = wx.Choice(parent, choices=preset_names)
        set_accessible_name(self._preset_choice, "Select instruction preset")
        set_accessible_help(
            self._preset_choice,
            "Choose a preset to auto-fill instructions, or select Custom to write your own",
        )
        label_control(preset_lbl, self._preset_choice)
        self._preset_choice.Bind(wx.EVT_CHOICE, self._on_preset_changed)

        preset_row.Add(preset_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        preset_row.Add(self._preset_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(preset_row, 0, wx.EXPAND | wx.ALL, 8)

        # Instructions text
        instr_lbl = wx.StaticText(
            parent,
            label=(
                "&Instructions (tell the AI how to behave — "
                "what to focus on, how to respond, what to include):"
            ),
        )
        instr_lbl.Wrap(560)
        sizer.Add(instr_lbl, 0, wx.LEFT | wx.RIGHT, 8)

        self._instructions_text = wx.TextCtrl(
            parent,
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
            size=(-1, 250),
        )
        set_accessible_name(self._instructions_text, "Agent instructions")
        set_accessible_help(
            self._instructions_text,
            "Write instructions that tell the AI assistant how to behave. "
            "Be specific about what you want it to focus on.",
        )
        label_control(instr_lbl, self._instructions_text)
        sizer.Add(self._instructions_text, 1, wx.EXPAND | wx.ALL, 8)

        # Tips
        tips = wx.StaticText(
            parent,
            label=(
                "Tips: Be specific about the AI's role. Mention what kind of "
                "content you typically transcribe. Include formatting preferences. "
                "Tell it what NOT to do if needed."
            ),
        )
        tips.Wrap(560)
        tips.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        sizer.Add(tips, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        parent.SetSizer(sizer)

    def _build_tools_tab(self, parent: wx.Panel) -> None:
        """Build the tools permission tab."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "Select which tools the AI assistant can use when analyzing "
                "your transcripts. More tools give the assistant more capabilities "
                "but may slow down responses slightly."
            ),
        )
        intro.Wrap(560)
        sizer.Add(intro, 0, wx.ALL, 8)

        self._tool_checks: dict[str, wx.CheckBox] = {}

        for tool in _AVAILABLE_TOOLS:
            box = wx.StaticBox(parent, label=tool["name"])
            set_accessible_name(box, tool["name"])
            box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

            cb = wx.CheckBox(parent, label=f"&Enable {tool['name']}")
            set_accessible_name(cb, f"Enable {tool['name']}")
            set_accessible_help(cb, tool["description"])
            self._tool_checks[tool["id"]] = cb
            box_sizer.Add(cb, 0, wx.ALL, 4)

            desc = wx.StaticText(parent, label=tool["description"])
            desc.Wrap(520)
            box_sizer.Add(desc, 0, wx.LEFT | wx.BOTTOM, 4)

            sizer.Add(box_sizer, 0, wx.EXPAND | wx.ALL, 4)

        parent.SetSizer(sizer)

    def _build_welcome_tab(self, parent: wx.Panel) -> None:
        """Build the welcome message configuration tab."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "Customize the message shown when the chat panel first opens. "
                "This helps users understand what the assistant can do."
            ),
        )
        intro.Wrap(560)
        sizer.Add(intro, 0, wx.ALL, 8)

        lbl = wx.StaticText(parent, label="&Welcome message:")
        sizer.Add(lbl, 0, wx.LEFT, 8)

        self._welcome_text = wx.TextCtrl(
            parent,
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
            size=(-1, 200),
        )
        set_accessible_name(self._welcome_text, "Welcome message text")
        set_accessible_help(
            self._welcome_text,
            "The message displayed when the chat panel opens",
        )
        label_control(lbl, self._welcome_text)
        sizer.Add(self._welcome_text, 1, wx.EXPAND | wx.ALL, 8)

        parent.SetSizer(sizer)

    # ------------------------------------------------------------------ #
    # Load / Save values                                                   #
    # ------------------------------------------------------------------ #

    def _load_values(self) -> None:
        """Load current configuration values into the UI."""
        c = self._config

        self._name_input.SetValue(c.name)
        self._desc_input.SetValue(c.description)

        idx = self._model_choice.FindString(c.model)
        self._model_choice.SetSelection(idx if idx != wx.NOT_FOUND else 0)

        self._temp_spin.SetValue(c.temperature)
        self._tokens_spin.SetValue(c.max_tokens)

        self._instructions_text.SetValue(c.instructions)
        self._welcome_text.SetValue(c.welcome_message)

        # Set preset to "Custom" since we loaded custom values
        custom_idx = self._preset_choice.FindString("Custom")
        self._preset_choice.SetSelection(custom_idx if custom_idx != wx.NOT_FOUND else 0)

        # Tool checkboxes
        for tool_id, cb in self._tool_checks.items():
            cb.SetValue(tool_id in c.tools_enabled)

    def _collect_values(self) -> AgentConfig:
        """Collect values from the UI into an AgentConfig."""
        tools = [
            tid for tid, cb in self._tool_checks.items() if cb.GetValue()
        ]

        model_idx = self._model_choice.GetSelection()
        model = self._model_choice.GetString(model_idx) if model_idx >= 0 else "gpt-4o"

        return AgentConfig(
            name=self._name_input.GetValue().strip() or "BITS Transcript Assistant",
            description=self._desc_input.GetValue().strip(),
            instructions=self._instructions_text.GetValue().strip(),
            model=model,
            tools_enabled=tools,
            temperature=self._temp_spin.GetValue(),
            max_tokens=self._tokens_spin.GetValue(),
            welcome_message=self._welcome_text.GetValue().strip(),
        )

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_preset_changed(self, _event: wx.CommandEvent) -> None:
        """Apply the selected instruction preset."""
        idx = self._preset_choice.GetSelection()
        if idx < 0:
            return
        preset_name = self._preset_choice.GetString(idx)
        preset_text = _INSTRUCTION_PRESETS.get(preset_name, "")
        if preset_text:
            self._instructions_text.SetValue(preset_text)

    def _on_save_file(self, _event: wx.CommandEvent) -> None:
        """Save the agent configuration to a JSON file."""
        config = self._collect_values()

        dlg = wx.FileDialog(
            self,
            message="Save Agent Configuration",
            defaultDir=str(_AGENTS_DIR),
            defaultFile=f"{config.name.lower().replace(' ', '_')}.json",
            wildcard="JSON files (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = Path(dlg.GetPath())
            try:
                config.save(path)
                announce_status(
                    self._main_frame,
                    f"Agent configuration saved to {path.name}",
                )
            except Exception as exc:
                wx.MessageBox(
                    f"Failed to save: {exc}",
                    "Save Error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
        dlg.Destroy()

    def _on_load_file(self, _event: wx.CommandEvent) -> None:
        """Load an agent configuration from a JSON file."""
        dlg = wx.FileDialog(
            self,
            message="Load Agent Configuration",
            defaultDir=str(_AGENTS_DIR),
            wildcard="JSON files (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = Path(dlg.GetPath())
            try:
                self._config = AgentConfig.load(path)
                self._load_values()
                announce_status(
                    self._main_frame,
                    f"Agent configuration loaded from {path.name}",
                )
            except Exception as exc:
                wx.MessageBox(
                    f"Failed to load: {exc}",
                    "Load Error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
        dlg.Destroy()

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        """Apply the configuration and close."""
        self._result_config = self._collect_values()
        announce_status(
            self._main_frame,
            f"Agent '{self._result_config.name}' configured",
        )
        self.EndModal(wx.ID_OK)

    @property
    def result_config(self) -> AgentConfig | None:
        """The resulting agent configuration, or None if cancelled."""
        return self._result_config
