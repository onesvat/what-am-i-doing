from __future__ import annotations

from dataclasses import dataclass
import shlex

from prompt_toolkit import prompt
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    HSplit,
    Layout,
    VSplit,
    DynamicContainer,
)
from prompt_toolkit.widgets import Box, CheckboxList, Frame, Label

from .categories import CATEGORY_CATALOG, CategoryDefinition
from .config import CommandConfig


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


class CategoryTreeEditor:
    def __init__(self) -> None:
        self._top_categories = [(cat.name, cat.name) for cat in CATEGORY_CATALOG]
        self._top_list = CheckboxList(
            self._top_categories,
            default_values=[cat.name for cat in CATEGORY_CATALOG],
        )
        self._sub_lists: dict[str, CheckboxList] = {}
        for cat in CATEGORY_CATALOG:
            if cat.subcategories and cat.subcategory_selectable:
                sub_values = [(sub, sub) for sub in cat.subcategories]
                self._sub_lists[cat.name] = CheckboxList(sub_values, default_values=[])
        self._help = Label(
            "Space: toggle. Up/Down: navigate. Tab: switch panels. Enter: submit."
        )

    def run(self) -> list[str]:
        kb = KeyBindings()

        @kb.add("space")
        def _toggle_with_sync(event) -> None:
            current = event.app.layout.current_control
            if current == self._top_list:
                self._toggle_top_item()
                self._update_subcategories_from_parent()
            else:
                parent = self._find_parent_for_control(current)
                if parent:
                    self._toggle_sub_item(parent)
                    self._update_parent_from_subcategories(parent)

        @kb.add("tab")
        def _switch_panel(event) -> None:
            current = event.app.layout.current_control
            if current == self._top_list:
                sub_list = self._sub_lists.get(self._current_highlighted_parent())
                if sub_list:
                    event.app.layout.focus(sub_list)
            else:
                event.app.layout.focus(self._top_list)

        @kb.add("s-tab")
        def _switch_panel_back(event) -> None:
            current = event.app.layout.current_control
            if current != self._top_list:
                event.app.layout.focus(self._top_list)
            else:
                sub_list = self._sub_lists.get(self._current_highlighted_parent())
                if sub_list:
                    event.app.layout.focus(sub_list)

        @kb.add("enter")
        def _submit(event) -> None:
            selected_paths = self._collect_selected_paths()
            event.app.exit(result=selected_paths)

        root_content = self._build_layout()
        root = Box(body=root_content, padding=1)
        app = Application(
            layout=Layout(root, focused_element=self._top_list),
            key_bindings=kb,
            full_screen=True,
        )
        result = app.run()
        return result or []

    def _build_layout(self) -> HSplit:
        children = [
            Label("Choose categories for waid."),
            self._help,
        ]

        top_frame = Frame(self._top_list, title="Top-level Categories")

        def get_sub_frame():
            parent = self._current_highlighted_parent()
            sub_list = self._sub_lists.get(parent)
            if sub_list:
                return Frame(sub_list, title=f"Subcategories: {parent}")
            return Frame(
                Label("No subcategories for this category"), title="Subcategories"
            )

        sub_container = DynamicContainer(get_sub_frame)

        children.append(VSplit([top_frame, sub_container], padding=1))
        return HSplit(children)

    def _current_highlighted_parent(self) -> str:
        index = getattr(self._top_list, "_selected_index", 0)
        if 0 <= index < len(self._top_categories):
            return self._top_categories[index][0]
        return ""

    def _find_parent_for_control(self, control) -> str | None:
        for parent, sub_list in self._sub_lists.items():
            if control == sub_list:
                return parent
        return None

    def _toggle_top_item(self) -> None:
        index = getattr(self._top_list, "_selected_index", 0)
        if 0 <= index < len(self._top_categories):
            item_name = self._top_categories[index][0]
            current = set(self._top_list.current_values)
            if item_name in current:
                current.remove(item_name)
            else:
                current.add(item_name)
            self._top_list.current_values = list(current)

    def _toggle_sub_item(self, parent: str) -> None:
        sub_list = self._sub_lists.get(parent)
        if not sub_list:
            return
        index = getattr(sub_list, "_selected_index", 0)
        values_list = sub_list.values
        if 0 <= index < len(values_list):
            sub_name = values_list[index][0]
            current = set(sub_list.current_values)
            if sub_name in current:
                current.remove(sub_name)
            else:
                current.add(sub_name)
            sub_list.current_values = list(current)

    def _update_subcategories_from_parent(self) -> None:
        parent = self._current_highlighted_parent()
        sub_list = self._sub_lists.get(parent)
        if not sub_list:
            return

        parent_selected = parent in self._top_list.current_values
        all_subs = [sub for sub, _ in sub_list.values]

        if parent_selected:
            sub_list.current_values = all_subs
        else:
            sub_list.current_values = []

    def _update_parent_from_subcategories(self, parent: str) -> None:
        sub_list = self._sub_lists.get(parent)
        if not sub_list:
            return

        all_subs = [sub for sub, _ in sub_list.values]
        selected_subs = set(sub_list.current_values)
        current_parents = set(self._top_list.current_values)

        if selected_subs == set(all_subs):
            current_parents.add(parent)
        else:
            current_parents.discard(parent)

        self._top_list.current_values = list(current_parents)

    def _collect_selected_paths(self) -> list[str]:
        selected_paths: list[str] = []
        selected_top = set(self._top_list.current_values)

        for cat in CATEGORY_CATALOG:
            if cat.name not in selected_top:
                continue

            if cat.subcategories and not cat.subcategory_selectable:
                selected_paths.append(cat.name)
            elif cat.subcategories and cat.subcategory_selectable:
                sub_list = self._sub_lists.get(cat.name)
                if sub_list and sub_list.current_values:
                    for sub in cat.subcategories:
                        if sub in sub_list.current_values:
                            selected_paths.append(f"{cat.name}/{sub}")
                else:
                    selected_paths.append(cat.name)
            else:
                selected_paths.append(cat.name)

        return selected_paths


def run_init_wizard() -> InitAnswers:
    base_url = prompt("Model base URL: ", default="http://localhost:11434/v1").strip()
    model_name = prompt("Model name: ", default="gemma3:4b").strip()
    api_key_env = prompt("API key env var: ", default="OPENAI_API_KEY").strip()
    category_paths = CategoryTreeEditor().run()
    category_notes = {path: "" for path in category_paths}
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
