from __future__ import annotations

from dataclasses import dataclass
import shlex

from prompt_toolkit import prompt
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit
from prompt_toolkit.widgets import Box, CheckboxList, Frame, Label, TextArea

from .config import CommandConfig
from .defaults import DEFAULT_CATEGORY_CHOICES


@dataclass(slots=True)
class InitAnswers:
    base_url: str
    model_name: str
    api_key_env: str
    category_notes: dict[str, str]
    context_tools: dict[str, CommandConfig]
    action_tools: dict[str, CommandConfig]
    generator_instructions: str
    classifier_instructions: str
    classifier_params: dict[str, str]


class CategoryEditor:
    def __init__(self, choices: list[tuple[str, str]]) -> None:
        self._notes = {name: note for name, note in choices}
        self._values = [(name, name) for name, _note in choices]
        self._list = CheckboxList(self._values, default_values=[name for name, _note in choices])
        self._note_area = TextArea(multiline=True, scrollbar=True)
        self._help = Label(
            "Space select. Tab edit note for highlighted category. Tab again to save. Enter submit."
        )
        self._result: dict[str, str] | None = None
        self._current_note_target = choices[0][0]

    def run(self) -> dict[str, str]:
        self._load_current_note()
        kb = KeyBindings()

        @kb.add("tab")
        def _toggle_note_focus(event) -> None:
            if event.app.layout.has_focus(self._list):
                self._load_current_note()
                event.app.layout.focus(self._note_area)
                return
            self._save_current_note()
            event.app.layout.focus(self._list)

        @kb.add("s-tab")
        def _back_to_list(event) -> None:
            self._save_current_note()
            event.app.layout.focus(self._list)

        @kb.add("enter")
        def _submit(event) -> None:
            self._save_current_note()
            selected = {name: self._notes.get(name, "") for name in self._list.current_values}
            event.app.exit(result=selected)

        root = Box(
            body=HSplit(
                [
                    Label("Choose broad categories for waid."),
                    self._help,
                    VSplit(
                        [
                            Frame(self._list, title="Categories"),
                            Frame(self._note_area, title="Optional note"),
                        ],
                        padding=1,
                    ),
                ]
            ),
            padding=1,
        )
        app = Application(
            layout=Layout(root, focused_element=self._list),
            key_bindings=kb,
            full_screen=True,
        )
        result = app.run()
        return result or {}

    def _selected_name(self) -> str:
        index = self._list._selected_index
        return self._values[index][0]

    def _load_current_note(self) -> None:
        self._current_note_target = self._selected_name()
        self._note_area.text = self._notes.get(self._current_note_target, "")

    def _save_current_note(self) -> None:
        self._notes[self._current_note_target] = self._note_area.text.strip()


def run_init_wizard() -> InitAnswers:
    base_url = prompt("Model base URL: ", default="http://localhost:11434/v1").strip()
    model_name = prompt("Model name: ", default="gemma3:4b").strip()
    api_key_env = prompt("API key env var: ", default="OPENAI_API_KEY").strip()
    category_notes = CategoryEditor(list(DEFAULT_CATEGORY_CHOICES)).run()
    context_tools = _collect_tools("context")
    action_tools = _collect_tools("action")
    generator_instructions = prompt(
        "Generator extra instructions: ",
        default="Prefer matching today's planned tasks when possible.",
    ).strip()
    classifier_instructions = prompt(
        "Classifier extra instructions: ",
        default="Prefer the most specific category. Use unclassified when no category fits.",
    ).strip()
    classifier_params = _collect_params()
    return InitAnswers(
        base_url=base_url,
        model_name=model_name,
        api_key_env=api_key_env,
        category_notes=category_notes,
        context_tools=context_tools,
        action_tools=action_tools,
        generator_instructions=generator_instructions,
        classifier_instructions=classifier_instructions,
        classifier_params=classifier_params,
    )


def _collect_tools(kind: str) -> dict[str, CommandConfig]:
    print(f"Add {kind} tools. Leave the name blank to finish.")
    tools: dict[str, CommandConfig] = {}
    while True:
        name = prompt(f"{kind} tool name: ").strip()
        if not name:
            break
        command = prompt(f"{kind} command (argv, space separated): ").strip()
        if not command:
            continue
        tools[name] = CommandConfig(run=shlex.split(command))
    return tools


def _collect_params() -> dict[str, str]:
    print("Add optional classifier params. Leave the name blank to finish.")
    params: dict[str, str] = {}
    while True:
        name = prompt("classifier param name: ").strip()
        if not name:
            break
        value = prompt(f"value for {name}: ").strip()
        params[name] = value
    return params
