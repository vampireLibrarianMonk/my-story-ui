"""Paths: /project new, switch, rename, delete, list, natural phrasing, guards and isolation between projects."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .conftest import conversations, documents
from .planned import known_bug, planned


def names(api):
    return [p["name"] for p in api.get("/api/bootstrap").json()["projects"]]


def test_create_switches_to_the_new_project(nx, api):
    nx.run("/project new Atlas")
    expect(nx.project_chip).to_have_text("Atlas")
    expect(nx.toast).to_contain_text('Created and switched to "Atlas"')
    assert "Atlas" in names(api)
    expect(nx.prompt).to_have_value("")


def test_rename_current_project(nx, api):
    nx.run("/project rename Renamed")
    expect(nx.project_chip).to_have_text("Renamed")
    assert names(api) == ["Renamed"]


def test_missing_arguments_show_usage_and_change_nothing(nx, api):
    nx.run("/project new")
    expect(nx.toast).to_contain_text("Usage: /project new <name>")
    nx.run("/project rename")
    expect(nx.toast).to_contain_text("Usage: /project rename <new name>")
    nx.run("/project switch")
    expect(nx.toast).to_contain_text("Usage: /project switch <name>")
    assert names(api) == ["My first project"]


def test_list_and_help(nx, api):
    api.post("/api/projects", json={"name": "Beta"})
    nx.reload()
    nx.run("/project list")
    expect(nx.toast).to_contain_text("Projects:")
    expect(nx.toast).to_contain_text("Beta")
    nx.run("/project")
    expect(nx.toast).to_contain_text("Try /project new")
    nx.run("/project bogus")
    expect(nx.toast).to_contain_text("Try /project new")


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("new project: Gamma", "Gamma"),
        ("create project Delta", "Delta"),
        ("/project create Epsilon", "Epsilon"),
        ("/project add Zeta", "Zeta"),
    ],
)
def test_create_phrasings(nx, phrase, expected):
    nx.run(phrase)
    expect(nx.project_chip).to_have_text(expected)


def test_switch_by_exact_partial_and_natural_phrase(nx, api):
    api.post("/api/projects", json={"name": "Northern Atlas"})
    api.post("/api/projects", json={"name": "Southern Reach"})
    nx.reload()
    nx.run("/project switch north")
    expect(nx.project_chip).to_have_text("Northern Atlas")
    nx.run("switch to project my first project")
    expect(nx.project_chip).to_have_text("My first project")
    nx.run("/project open Southern Reach")
    expect(nx.project_chip).to_have_text("Southern Reach")


def test_switch_refuses_ambiguous_and_unknown_names(nx, api):
    api.post("/api/projects", json={"name": "Atlas One"})
    api.post("/api/projects", json={"name": "Atlas Two"})
    nx.reload()
    nx.run("/project switch atlas")
    expect(nx.toast).to_contain_text('No single project matches "atlas"')
    expect(nx.project_chip).to_have_text("My first project")
    nx.run("/project switch zebra")
    expect(nx.toast).to_contain_text("No single project matches")


def test_rename_phrasing(nx):
    nx.run("rename this project to Fresh Name")
    expect(nx.project_chip).to_have_text("Fresh Name")


def test_projects_are_isolated(nx, api, make_doc):
    make_doc("chapter", "Only in first")
    nx.reload()
    nx.ask("Explore something in the first project")
    expect(nx.docs_chip).to_contain_text("1 document")
    nx.run("/project new Second")
    expect(nx.docs_chip).to_contain_text("0 documents")
    expect(nx.chats_chip).to_contain_text("0 conversations")
    expect(nx.conversation).to_be_hidden()
    nx.run("/doc open Only in first")
    expect(nx.toast).to_contain_text("No single document matches")
    nx.run("/chat open Explore")
    expect(nx.toast).to_contain_text("No single conversation matches")
    nx.run("/project switch first")
    expect(nx.docs_chip).to_contain_text("1 document")


def test_switching_project_clears_the_open_thread_and_draft(nx):
    nx.run("/project new Second")
    nx.ask("Explore something here")
    nx.run("/project switch first")
    expect(nx.conversation).to_be_hidden()
    expect(nx.replies).to_have_count(0)
    expect(nx.prompt).to_have_value("")


# ---- delete
def test_delete_requires_the_exact_name(nx, api):
    nx.run("/project new Scratch")
    nx.run("/project delete")
    expect(nx.toast).to_contain_text("To delete, send: /project delete Scratch")
    nx.run("/project delete scratch")
    expect(nx.toast).to_contain_text("To delete, send: /project delete Scratch")
    nx.run("/project delete Something else")
    assert "Scratch" in names(api)


def test_delete_pane_warns_with_counts(nx, make_doc):
    make_doc("note", "n")
    nx.reload()
    nx.set_prompt("/project delete")
    alert = nx.pane.get_by_role("alert")
    expect(alert).to_contain_text("permanently removes")
    expect(alert).to_contain_text("1 document(s)")
    expect(alert).to_contain_text("/project delete My first project")


def test_delete_removes_everything_in_the_project(nx, api):
    nx.run("/project new Scratch")
    nx.ask("Explore a throwaway idea")
    nx.run("/doc new note Temp")
    nx.save_document()
    pid = next(
        p["id"]
        for p in api.get("/api/bootstrap").json()["projects"]
        if p["name"] == "Scratch"
    )
    assert documents(api, pid) and conversations(api, pid)
    nx.run("/project delete Scratch")
    expect(nx.toast).to_contain_text("Deleted")
    expect(nx.toast).to_contain_text("1 documents, 1 conversations")
    expect(nx.project_chip).to_have_text("My first project")
    assert api.get(f"/api/projects/{pid}/overview").status_code == 404
    assert names(api) == ["My first project"]


def test_the_last_project_cannot_be_deleted(nx, api):
    nx.run("/project delete My first project")
    expect(nx.toast).to_contain_text("The last remaining project cannot be deleted")
    expect(nx.project_chip).to_have_text("My first project")
    assert names(api) == ["My first project"]


@planned(
    "Reload forgets the active project. Boot picks the first row of an unordered created_at-DESC list, so it is a coin flip when projects share a second"
)
def test_reload_keeps_the_active_project(nx):
    nx.run("/project new Second")
    expect(nx.project_chip).to_have_text("Second")
    nx.reload()
    expect(nx.project_chip).to_have_text("Second", timeout=1500)


# ---- input limits and hostile text
def test_overlong_project_name_is_rejected(nx, api):
    nx.run("/project new " + "x" * 121)
    expect(nx.toast).to_contain_text("Request failed (422)")
    assert names(api) == ["My first project"]


def test_html_in_a_project_name_is_displayed_as_text(nx):
    nx.run("/project new <img src=x onerror=window.__pwned=1>")
    expect(nx.project_chip).to_have_text("<img src=x onerror=window.__pwned=1>")
    assert nx.page.evaluate("window.__pwned") is None


@known_bug(
    "Duplicate project names are accepted, which makes '/project switch <name>' ambiguous and unusable"
)
def test_duplicate_project_names_are_rejected(nx, api):
    nx.run("/project new My first project")
    expect(nx.toast).to_contain_text("already exists", timeout=1500)
    assert names(api) == ["My first project"]
