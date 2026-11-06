"""Path: typing a leading slash. Suggestions, keyboard, mouse, typos and refusal of unknown commands."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import conversations


def labels(nx):
    return nx.options.locator(".cmd-label").all_inner_texts()


def test_slash_lists_every_command(nx):
    nx.set_prompt("/")
    expect(nx.options).to_have_count(8)
    assert labels(nx) == [
        "/project",
        "/model",
        "/new",
        "/doc",
        "/chat",
        "/search",
        "/export",
        "/help",
    ]
    expect(nx.prompt).to_have_attribute("aria-expanded", "true")


def test_prefix_filters_commands(nx):
    nx.set_prompt("/d")
    expect(nx.options).to_have_count(1)
    assert labels(nx) == ["/doc"]


def test_tab_completes_and_adds_a_space(nx):
    nx.set_prompt("/")
    nx.prompt.press("Tab")
    expect(nx.prompt).to_have_value("/project ")


def test_enter_accepts_the_suggestion_and_does_not_send(nx, api, pid):
    nx.set_prompt("/pro")
    nx.prompt.press("Enter")
    expect(nx.prompt).to_have_value("/project ")
    assert conversations(api, pid) == []


def test_arrow_keys_wrap_and_escape_closes(nx):
    nx.set_prompt("/")
    expect(nx.options.nth(0)).to_have_attribute("aria-selected", "true")
    nx.prompt.press("ArrowUp")
    expect(nx.options.nth(7)).to_have_attribute("aria-selected", "true")
    nx.prompt.press("ArrowDown")
    expect(nx.options.nth(0)).to_have_attribute("aria-selected", "true")
    nx.prompt.press("Escape")
    expect(nx.suggestions).to_be_hidden()
    expect(nx.prompt).to_have_attribute("aria-expanded", "false")
    expect(nx.prompt).to_have_value("/")


def test_mouse_click_accepts_a_suggestion(nx):
    nx.set_prompt("/")
    nx.options.nth(3).click()
    expect(nx.prompt).to_have_value("/doc ")


def test_menu_closes_on_blur(nx):
    nx.set_prompt("/")
    expect(nx.suggestions).to_be_visible()
    nx.prompt.blur()
    expect(nx.suggestions).to_be_hidden()


def test_no_menu_for_multiline_or_ordinary_prompts(nx):
    nx.set_prompt("/doc\nnew")
    expect(nx.suggestions).to_be_hidden()
    nx.set_prompt("What if the project failed?")
    expect(nx.suggestions).to_be_hidden()


def test_typo_in_command_and_subcommand_gets_did_you_mean(nx):
    nx.set_prompt("/projct")
    expect(nx.options.first).to_contain_text("Did you mean")
    nx.set_prompt("/doc opne")
    expect(nx.options.first).to_contain_text("Did you mean")
    assert labels(nx) == ["/doc open"]


def test_subcommands_for_project_doc_and_chat(nx):
    nx.set_prompt("/project ")
    assert labels(nx) == [
        "/project new",
        "/project switch",
        "/project rename",
        "/project delete",
        "/project list",
    ]
    nx.set_prompt("/doc ")
    assert labels(nx) == ["/doc new", "/doc open", "/doc list"]
    nx.set_prompt("/chat ")
    assert labels(nx) == ["/chat open", "/chat list"]


def test_doc_new_suggests_types(nx):
    nx.set_prompt("/doc new c")
    assert labels(nx) == ["chapter", "character"]
    nx.options.nth(1).click()
    expect(nx.prompt).to_have_value("/doc new character ")


def test_doc_open_and_chat_open_suggest_saved_items(nx, api, make_doc):
    make_doc("chapter", "Chapter 5")
    make_doc("note", "Loose idea")
    nx.reload()
    nx.set_prompt("/doc open ")
    assert sorted(labels(nx)) == ["Chapter 5", "Loose idea"]
    nx.set_prompt("/doc open chap")
    assert labels(nx) == ["Chapter 5"]
    nx.ask("A first exploration about trade routes")
    nx.set_prompt("/chat open ")
    assert labels(nx) == ["A first exploration about trade routes"]


def test_project_switch_and_delete_suggestions(nx, api):
    api.post("/api/projects", json={"name": "Beta"})
    nx.reload()
    nx.set_prompt("/project switch ")
    assert sorted(labels(nx)) == ["Beta", "My first project"]
    nx.set_prompt("/project delete ")
    assert labels(nx) == ["My first project"]
    expect(nx.options.first).to_contain_text("Permanent")


def test_model_suggestions_dim_unconfigured_models(nx):
    nx.set_prompt("/model ")
    assert labels(nx) == ["/model demo", "/model arc", "/model bedrock", "/model list"]
    expect(nx.options.nth(0)).not_to_have_attribute("aria-disabled", "true")
    expect(nx.options.nth(1)).to_have_attribute("aria-disabled", "true")
    expect(nx.options.nth(2)).to_have_attribute("aria-disabled", "true")


def test_arc_is_not_dimmed_when_the_server_configures_it(nx_arc_down):
    nx_arc_down.set_prompt("/model ")
    expect(nx_arc_down.options.nth(1)).not_to_have_attribute("aria-disabled", "true")


def test_unknown_command_is_refused_locally_and_never_sent_to_a_model(nx, api, pid):
    chat_calls = []
    nx.page.on(
        "request",
        lambda r: chat_calls.append(r.url) if r.url.endswith("/api/chat") else None,
    )
    nx.run("/frobnicate the plot")
    expect(nx.toast).to_contain_text("Unknown command /frobnicate")
    assert chat_calls == []
    assert conversations(api, pid) == []


@pytest.mark.parametrize(
    "text", ["/etc/hosts file: explain what it does", "/ explain this"]
)
def test_path_like_prompts_are_ordinary_chat(nx, api, pid, text):
    nx.ask(text)
    assert len(conversations(api, pid)) == 1
