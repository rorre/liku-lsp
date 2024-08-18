from typing import cast
import typing
from jedi.api import Script
from liku_parser import (
    SuggestComponent,
    SuggestProps,
    SuggestPython,
)
from lsprotocol.types import CompletionItem, CompletionItemKind
from liku import __all__ as liku_elements
from liku.elements import h as h_func

mapping: dict[str, dict[str, type]] = {}
for overload in typing.get_overloads(h_func):
    hints = typing.get_type_hints(overload)
    tag_name = typing.get_args(hints["tag_name"])[0]
    if tag_name not in liku_elements:
        continue

    prop_types = typing.get_args(hints["props"])[0]
    assert typing.is_typeddict(prop_types), "Unexpected non-typeddict"
    mapping[tag_name] = typing.get_type_hints(prop_types)


def suggest_components(script: Script, action: SuggestComponent):
    search_text = action.cursor
    is_closing_tag = search_text.startswith("/")
    if is_closing_tag:
        search_text = search_text[1:]

    candidates = list(
        map(
            lambda x: cast(str, x.name),
            filter(
                lambda x: x.type in ("function", "class"),
                script.complete_search(search_text),
            ),
        )
    )
    candidates.extend(filter(lambda x: x.startswith(search_text), liku_elements))

    completions = map(
        lambda x: CompletionItem(
            label=x,
            insert_text=((f"{x}></" if not is_closing_tag else "") + f"{x}>"),
        ),
        candidates,
    )

    return list(completions)


def _suggest_from_liku(component: str, search_text: str) -> list[str]:
    if component not in liku_elements:
        return []

    props = mapping[component]
    return list(filter(lambda x: x.startswith(search_text), props.keys()))


def _suggest_from_custom_component(script: Script, component: str, search_text: str):
    search_result = list(script.search(component))
    if len(search_result) == 0:
        # NOTE: wtf?
        return []

    func = search_result[0]
    names: list[str] = []

    for sig in func.get_signatures():
        if len(sig.params) == 0:
            continue

        for param in filter(
            lambda param: param.name and param.name.startswith(search_text),
            sig.params,
        ):
            names.append(param.name)
    return names


def suggest_props(script: Script, action: SuggestProps):
    search_text = action.cursor
    is_prog_props = search_text.startswith(":")
    prefix = ":" if is_prog_props else ""

    if is_prog_props:
        search_text = search_text[1:]

    completions = _suggest_from_liku(
        action.component, search_text
    ) or _suggest_from_custom_component(script, action.component, search_text)

    return list(
        map(
            lambda x: CompletionItem(
                label=f"{prefix}{x}=",
                insert_text=f'{prefix}{x}=""',
            ),
            completions,
        )
    )


# module, class, instance, function, param, path, keyword, property and statement
CompletionItemKindMap = {
    "module": CompletionItemKind.Module,
    "class": CompletionItemKind.Class,
    "instance": CompletionItemKind.Variable,
    "function": CompletionItemKind.Function,
    "param": CompletionItemKind.Variable,
    "path": CompletionItemKind.Variable,
    "keyword": CompletionItemKind.Keyword,
    "property": CompletionItemKind.Property,
    "statement": CompletionItemKind.Variable,
}


def suggest_python(script: Script, action: SuggestPython):
    search_text = action.cursor
    # Is there a way we can avoid this?
    completions = script.complete_search(search_text, all_scopes=True)
    completions_unique = set(map(lambda c: (c.name, c.type), completions))

    return sorted(
        list(
            map(
                lambda x: CompletionItem(
                    label=x[0],
                    kind=CompletionItemKindMap.get(x[1]),
                ),
                completions_unique,
            )
        ),
        key=lambda x: x.label,
    )
