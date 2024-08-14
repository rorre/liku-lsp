from jedi.api import Script
from liku_parser import SuggestComponent, SuggestProps
from lsprotocol.types import CompletionItem
from jedi.api.classes import Name


def suggest_components(script: Script, action: SuggestComponent):
    search_text = action.cursor
    is_closing_tag = search_text.startswith("/")
    if is_closing_tag:
        search_text = search_text[1:]

    completions = map(
        lambda x: CompletionItem(
            label=x.name,
            insert_text=((f"{x.name}></" if not is_closing_tag else "") + f"{x.name}>"),
        ),
        filter(
            lambda x: x.type in ("function", "class"),
            script.complete_search(search_text),
        ),
    )
    return list(completions)


def suggest_props(script: Script, action: SuggestProps):
    func: Name = script.search(action.component)[0]  # type: ignore
    all_completions: list[CompletionItem] = []

    for sig in func.get_signatures():
        if len(sig.params) == 0:
            continue

        search_text = action.cursor
        is_prog_props = search_text.startswith(":")

        if is_prog_props:
            search_text = search_text[1:]

        for param in filter(
            lambda param: param.name and param.name.startswith(search_text),
            sig.params,
        ):
            prefix = ":" if is_prog_props else ""

            all_completions.append(
                CompletionItem(
                    label=f"{param.name}=",
                    insert_text=f'{prefix}{param.name}=""',
                )
            )

    return all_completions
