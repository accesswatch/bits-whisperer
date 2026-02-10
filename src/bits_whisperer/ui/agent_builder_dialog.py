"""AI Action Builder — guided template builder for post-transcription AI actions.

Provides a form-based UI for creating and editing AI action templates.
Users can set the template name, instructions, model preferences,
and other settings. Templates define how AI processes a transcript
after transcription completes — generating meeting minutes, action
items, summaries, and more.

Templates work with any configured AI provider (OpenAI, Anthropic,
Google Gemini, Ollama, Azure OpenAI, or GitHub Copilot).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from bits_whisperer.core.copilot_service import AgentConfig, Attachment
from bits_whisperer.core.document_reader import (
    ATTACHMENT_WILDCARD,
    is_supported,
)
from bits_whisperer.utils.accessibility import (
    accessible_message_box,
    announce_status,
    label_control,
    make_panel_accessible,
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
    "Meeting Minutes": (
        "You are a professional meeting minutes writer. Given the transcript below, "
        "produce well-structured meeting minutes that include:\n"
        "- Date/time and attendees (if identifiable)\n"
        "- Agenda items discussed\n"
        "- Key decisions made\n"
        "- Action items with owners and deadlines (if mentioned)\n"
        "- Follow-up items\n\n"
        "Use clear headings, bullet points, and concise language suitable for "
        "sharing with team members who were not present."
    ),
    "Action Items": (
        "You are a task extraction specialist. Analyze this transcript and "
        "extract every action item, task, commitment, follow-up, and to-do "
        "mentioned. For each item include:\n"
        "- What needs to be done\n"
        "- Who is responsible (if mentioned)\n"
        "- Deadline or timeline (if mentioned)\n"
        "- Priority level (high/medium/low, inferred from context)\n\n"
        "Present them as a numbered, actionable list."
    ),
    "Executive Summary": (
        "You are an executive briefing specialist. Produce a concise executive "
        "summary of this transcript suitable for senior leadership. Include:\n"
        "- One-paragraph overview (3-4 sentences)\n"
        "- Key takeaways (bullet points)\n"
        "- Strategic implications or concerns\n"
        "- Recommended next steps\n\n"
        "Keep the tone professional and focus on what matters most."
    ),
    "Interview Notes": (
        "You are an interview analysis expert. Create detailed interview notes "
        "from this transcript, including:\n"
        "- Candidate/interviewee information\n"
        "- Key questions asked and responses\n"
        "- Notable strengths and areas of concern\n"
        "- Relevant quotes\n"
        "- Overall assessment and recommendation\n\n"
        "Maintain objectivity and support observations with evidence from "
        "the transcript."
    ),
    "Lecture Notes": (
        "You are a study notes specialist. Transform this lecture/presentation "
        "transcript into well-organized study notes that include:\n"
        "- Main topics and subtopics with clear headings\n"
        "- Key concepts and definitions\n"
        "- Important examples and explanations\n"
        "- Formulas, processes, or frameworks mentioned\n"
        "- Questions raised and any answers given\n"
        "- Summary of key takeaways\n\n"
        "Use bullet points, numbered lists, and formatting for easy review."
    ),
    "Q&A Extraction": (
        "You are a Q&A extraction specialist. Identify every question asked "
        "in this transcript and its corresponding answer. Present them as a "
        "clean Q&A format:\n\n"
        "Q: [question]\n"
        "A: [answer]\n\n"
        "If a question was not answered, note it as 'Unanswered'. Include "
        "the speaker name if identifiable."
    ),
    "General Assistant": (
        "You are a helpful transcript assistant. You help users understand, "
        "analyze, and work with audio transcripts. Be concise, clear, and helpful. "
        "When asked about the transcript, refer to specific parts and provide "
        "accurate information."
    ),
    "Custom": "",
}


class AgentBuilderDialog(wx.Dialog):
    """Dialog for creating and editing AI action templates.

    Provides a guided, form-based experience so users can create
    templates that define how AI processes transcripts after
    transcription completes. Templates work with any configured
    AI provider. All fields are presented with clear labels and help text.
    """

    def __init__(
        self,
        parent: wx.Window,
        main_frame: MainFrame,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialise the AI action builder.

        Args:
            parent: Parent window.
            main_frame: Reference to the main frame.
            config: Existing template configuration to edit, or None for new.
        """
        super().__init__(
            parent,
            title="AI Action Builder — Create Post-Transcription Templates",
            size=(650, 620),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        set_accessible_name(self, "AI Action Builder")
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
        header = wx.StaticText(self, label="AI Action Builder")
        font = header.GetFont()
        font.SetPointSize(font.GetPointSize() + 3)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        header.SetFont(font)
        set_accessible_name(header, "AI Action Builder")
        root.Add(header, 0, wx.ALL, 12)

        intro = wx.StaticText(
            self,
            label=(
                "Create a template that defines how AI processes your transcripts "
                "after transcription completes. Choose a preset or write custom "
                "instructions. Works with any configured AI provider."
            ),
        )
        intro.Wrap(580)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Notebook with tabs
        notebook = wx.Notebook(self)
        set_accessible_name(notebook, "AI action template configuration tabs")

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

        # Attachments tab
        attach_panel = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        make_panel_accessible(attach_panel)
        self._build_attachments_tab(attach_panel)
        notebook.AddPage(attach_panel, "Attachments")

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
        set_accessible_name(save_file_btn, "Save AI action template to file")
        save_file_btn.Bind(wx.EVT_BUTTON, self._on_save_file)
        btn_sizer.Add(save_file_btn, 0, wx.RIGHT, 8)

        load_file_btn = wx.Button(self, label="&Load from File...")
        set_accessible_name(load_file_btn, "Load AI action template from file")
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
        """Build the template identity configuration tab."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Template name
        name_box = wx.StaticBox(parent, label="Template Name")
        set_accessible_name(name_box, "Template name settings")
        name_sizer = wx.StaticBoxSizer(name_box, wx.VERTICAL)

        name_lbl = wx.StaticText(parent, label="&Name:")
        self._name_input = wx.TextCtrl(parent, size=(400, -1))
        set_accessible_name(self._name_input, "Template display name")
        set_accessible_help(
            self._name_input,
            "The name shown in the AI action dropdown and results",
        )
        label_control(name_lbl, self._name_input)

        name_row = wx.BoxSizer(wx.HORIZONTAL)
        name_row.Add(name_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        name_row.Add(self._name_input, 1)
        name_sizer.Add(name_row, 0, wx.EXPAND | wx.ALL, 6)

        desc_lbl = wx.StaticText(parent, label="&Description:")
        self._desc_input = wx.TextCtrl(parent, size=(400, -1))
        set_accessible_name(self._desc_input, "Template description")
        set_accessible_help(
            self._desc_input,
            "A short description of what this template produces",
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
        self._temp_spin = wx.SpinCtrlDouble(parent, min=0.0, max=2.0, inc=0.1, initial=0.3)
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
        set_accessible_name(self._preset_choice, "Select action preset")
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
        set_accessible_name(self._instructions_text, "AI action instructions")
        set_accessible_help(
            self._instructions_text,
            "Write instructions that tell the AI how to process your transcript. "
            "Be specific about what you want it to produce.",
        )
        label_control(instr_lbl, self._instructions_text)
        sizer.Add(self._instructions_text, 1, wx.EXPAND | wx.ALL, 8)

        # Tips
        tips = wx.StaticText(
            parent,
            label=(
                "Tips: Be specific about the output format you want. Mention what kind of "
                "content you typically transcribe. Include formatting preferences. "
                "Tell it what NOT to do if needed."
            ),
        )
        tips.Wrap(560)
        tips.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        sizer.Add(tips, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        parent.SetSizer(sizer)

    def _build_attachments_tab(self, parent: wx.Panel) -> None:
        """Build the attachments configuration tab.

        Lets users add external documents (spreadsheets, Word docs, PDFs,
        text files) as supplementary context for AI actions. Each attachment
        can have per-file instructions telling the AI how to use it.
        """
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            parent,
            label=(
                "Attach external documents to provide additional context alongside "
                "the transcript. The AI will use these as reference material when "
                "processing. Supported formats: text, Word (.docx), Excel (.xlsx), "
                "PDF, and more."
            ),
        )
        intro.Wrap(560)
        sizer.Add(intro, 0, wx.ALL, 8)

        # Attachment list
        list_lbl = wx.StaticText(parent, label="&Attached documents:")
        sizer.Add(list_lbl, 0, wx.LEFT | wx.TOP, 8)

        self._attach_list = wx.ListCtrl(
            parent,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            size=(-1, 140),
        )
        self._attach_list.InsertColumn(0, "File", width=260)
        self._attach_list.InsertColumn(1, "Instructions", width=260)
        set_accessible_name(self._attach_list, "Attached documents list")
        set_accessible_help(
            self._attach_list,
            "List of external documents attached to this AI action template. "
            "Select an item and use the buttons below to edit or remove it.",
        )
        label_control(list_lbl, self._attach_list)
        sizer.Add(self._attach_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # List buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        add_btn = wx.Button(parent, label="&Add File...")
        set_accessible_name(add_btn, "Add attachment file")
        set_accessible_help(add_btn, "Browse for a document to attach")
        add_btn.Bind(wx.EVT_BUTTON, self._on_attach_add)
        btn_sizer.Add(add_btn, 0, wx.RIGHT, 6)

        edit_btn = wx.Button(parent, label="&Edit Instructions...")
        set_accessible_name(edit_btn, "Edit attachment instructions")
        set_accessible_help(
            edit_btn,
            "Edit the per-file instructions for the selected attachment",
        )
        edit_btn.Bind(wx.EVT_BUTTON, self._on_attach_edit)
        btn_sizer.Add(edit_btn, 0, wx.RIGHT, 6)

        remove_btn = wx.Button(parent, label="&Remove")
        set_accessible_name(remove_btn, "Remove selected attachment")
        remove_btn.Bind(wx.EVT_BUTTON, self._on_attach_remove)
        btn_sizer.Add(remove_btn, 0)

        sizer.Add(btn_sizer, 0, wx.LEFT | wx.BOTTOM, 8)

        # Tips
        tips = wx.StaticText(
            parent,
            label=(
                "Tips: Use per-file instructions to tell the AI how each attachment "
                "should be used — e.g. 'Use this as a glossary of technical terms', "
                "'Cross-reference meeting outcomes with this project plan', or "
                "'Follow the formatting guidelines in this style guide'."
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

        # Attachments
        self._attachments_data = list(c.attachments)
        self._attach_list.DeleteAllItems()
        for att in c.attachments:
            idx = self._attach_list.GetItemCount()
            self._attach_list.InsertItem(idx, att.name)
            self._attach_list.SetItem(idx, 1, att.instructions or "(none)")

    def _collect_values(self) -> AgentConfig:
        """Collect values from the UI into an AgentConfig."""
        tools = [tid for tid, cb in self._tool_checks.items() if cb.GetValue()]

        model_idx = self._model_choice.GetSelection()
        model = self._model_choice.GetString(model_idx) if model_idx >= 0 else "gpt-4o"

        # Collect attachments from the internal list
        attachments = list(getattr(self, "_attachments_data", []))

        return AgentConfig(
            name=self._name_input.GetValue().strip() or "BITS Transcript Assistant",
            description=self._desc_input.GetValue().strip(),
            instructions=self._instructions_text.GetValue().strip(),
            model=model,
            tools_enabled=tools,
            temperature=self._temp_spin.GetValue(),
            max_tokens=self._tokens_spin.GetValue(),
            welcome_message=self._welcome_text.GetValue().strip(),
            attachments=attachments,
        )

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Attachment event handlers                                            #
    # ------------------------------------------------------------------ #

    def _on_attach_add(self, _event: wx.CommandEvent) -> None:
        """Browse for a file and add it as an attachment."""
        dlg = wx.FileDialog(
            self,
            message="Select Document to Attach",
            wildcard=ATTACHMENT_WILDCARD,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
        )
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
            for path in paths:
                if not is_supported(path):
                    accessible_message_box(
                        f"Unsupported file type: {Path(path).suffix}\n\n"
                        f"Supported formats include .txt, .md, .docx, .xlsx, .pdf, .rtf, "
                        f".csv, .json, .xml, .yaml, and more.",
                        "Unsupported File",
                        wx.OK | wx.ICON_WARNING,
                        self,
                    )
                    continue

                att = Attachment(file_path=path)

                # Prompt for optional instructions
                instr_dlg = wx.TextEntryDialog(
                    self,
                    f"Optional instructions for '{att.name}':\n\n"
                    f"Tell the AI how to use this document — e.g. "
                    f"'Use as a glossary', 'Cross-reference with transcript', etc.\n\n"
                    f"Leave blank if no special instructions are needed.",
                    "Attachment Instructions",
                    value="",
                )
                set_accessible_name(instr_dlg, f"Instructions for attachment {att.name}")
                if instr_dlg.ShowModal() == wx.ID_OK:
                    att.instructions = instr_dlg.GetValue().strip()
                instr_dlg.Destroy()

                # Add to internal list and UI
                if not hasattr(self, "_attachments_data"):
                    self._attachments_data: list[Attachment] = []
                self._attachments_data.append(att)

                idx = self._attach_list.GetItemCount()
                self._attach_list.InsertItem(idx, att.name)
                self._attach_list.SetItem(idx, 1, att.instructions or "(none)")

            announce_status(
                self._main_frame,
                f"{len(paths)} attachment(s) added",
            )
        dlg.Destroy()

    def _on_attach_edit(self, _event: wx.CommandEvent) -> None:
        """Edit per-file instructions for the selected attachment."""
        sel = self._attach_list.GetFirstSelected()
        if sel < 0:
            accessible_message_box(
                "Select an attachment first.",
                "No Selection",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        attachments = getattr(self, "_attachments_data", [])
        if sel >= len(attachments):
            return

        att = attachments[sel]
        dlg = wx.TextEntryDialog(
            self,
            f"Instructions for '{att.name}':\n\n" f"Tell the AI how to use this document.",
            "Edit Attachment Instructions",
            value=att.instructions,
        )
        set_accessible_name(dlg, f"Edit instructions for {att.name}")
        if dlg.ShowModal() == wx.ID_OK:
            att.instructions = dlg.GetValue().strip()
            self._attach_list.SetItem(sel, 1, att.instructions or "(none)")
            announce_status(self._main_frame, f"Instructions updated for {att.name}")
        dlg.Destroy()

    def _on_attach_remove(self, _event: wx.CommandEvent) -> None:
        """Remove the selected attachment."""
        sel = self._attach_list.GetFirstSelected()
        if sel < 0:
            accessible_message_box(
                "Select an attachment to remove.",
                "No Selection",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        attachments = getattr(self, "_attachments_data", [])
        if sel < len(attachments):
            removed = attachments.pop(sel)
            self._attach_list.DeleteItem(sel)
            announce_status(self._main_frame, f"Attachment '{removed.name}' removed")

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
        """Save the AI action template to a JSON file."""
        config = self._collect_values()

        dlg = wx.FileDialog(
            self,
            message="Save AI Action Template",
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
                    f"AI action template saved to {path.name}",
                )
            except Exception as exc:
                accessible_message_box(
                    f"Failed to save: {exc}",
                    "Save Error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
        dlg.Destroy()

    def _on_load_file(self, _event: wx.CommandEvent) -> None:
        """Load an AI action template from a JSON file."""
        dlg = wx.FileDialog(
            self,
            message="Load AI Action Template",
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
                    f"AI action template loaded from {path.name}",
                )
            except Exception as exc:
                accessible_message_box(
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
            f"AI action template '{self._result_config.name}' configured",
        )
        self.EndModal(wx.ID_OK)

    @property
    def result_config(self) -> AgentConfig | None:
        """The resulting template configuration, or None if cancelled."""
        return self._result_config
