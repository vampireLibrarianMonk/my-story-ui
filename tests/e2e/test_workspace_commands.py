"""Paths: the sidebar's jobs, now typed in the prompt. /new /doc /chat /search /export /help and the status chips."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from .conftest import conversations, document, documents, messages
from .planned import known_bug


# ---- status strip
def test_empty_workspace_status(nx):
    expect(nx.project_chip).to_have_text("My first project")
    expect(nx.model_chip).to_have_text("Demo · no model")
    expect(nx.docs_chip).to_contain_text("0 documents")
    expect(nx.chats_chip).to_contain_text("0 conversations")


def test_chips_prefill_their_commands(nx):
    # The open suggestion menu overlaps the chips, so close it between clicks (see test_open_menu_does_not_cover_chips).
    nx.page.locator("#chipProject").click()
    expect(nx.prompt).to_have_value("/project ")
    nx.prompt.press("Escape")
    nx.page.locator("#chipModel").click()
    expect(nx.prompt).to_have_value("/model ")
    nx.prompt.press("Escape")
    nx.docs_chip.click()
    expect(nx.prompt).to_have_value("/doc list")
    expect(nx.pane_title).to_have_text("Run a command")
    nx.chats_chip.click()
    expect(nx.prompt).to_have_value("/chat list")


@known_bug(
    "The open suggestion menu is drawn over the status chips, so clicking a chip accepts a menu item instead"
)
def test_open_menu_does_not_cover_chips(nx):
    nx.page.locator("#chipProject").click()
    expect(nx.suggestions).to_be_visible()
    nx.page.locator("#chipModel").click(timeout=1500)
    expect(nx.prompt).to_have_value("/model ")


def test_counts_update_and_singularize(nx, make_doc):
    nx.run("/doc new note Scratch idea")
    nx.save_document()
    expect(nx.docs_chip).to_contain_text("1 document")
    expect(nx.docs_chip).not_to_contain_text("documents")
    nx.ask("Explore a first idea")
    expect(nx.chats_chip).to_contain_text("1 conversation")
    expect(nx.chats_chip).not_to_contain_text("conversations")


def test_data_survives_reload(nx, api, pid, make_doc):
    make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.ask("Explore a first idea")
    nx.reload()
    expect(nx.docs_chip).to_contain_text("1 document")
    expect(nx.chats_chip).to_contain_text("1 conversation")
    nx.run("/chat open Explore a first")
    expect(nx.replies).to_have_count(1)


# ---- /help and unknown
def test_help_lists_every_command(nx):
    nx.run("/help")
    for cmd in (
        "/project",
        "/model",
        "/new",
        "/doc",
        "/chat",
        "/search",
        "/export",
        "/help",
    ):
        expect(nx.toast).to_contain_text(cmd)


# ---- /new
def test_new_returns_to_a_blank_thought_and_keeps_the_archive(nx, api, pid):
    nx.ask("Explore a first idea")
    expect(nx.conversation).to_be_visible()
    nx.run("/new")
    expect(nx.conversation).to_be_hidden()
    expect(nx.prompt).to_have_value("")
    expect(nx.prompt).to_be_focused()
    expect(nx.chats_chip).to_contain_text("1 conversation")
    assert len(conversations(api, pid)) == 1


def test_n_key_starts_a_new_thought_only_outside_inputs(nx):
    nx.ask("Explore a first idea")
    nx.prompt.press_sequentially("no")
    expect(nx.prompt).to_have_value("no")
    expect(nx.conversation).to_be_visible()
    nx.prompt.fill("")
    nx.prompt.blur()
    nx.page.keyboard.press("n")
    expect(nx.conversation).to_be_hidden()


# ---- /doc
def test_doc_new_opens_a_blank_chapter_dialog(nx):
    nx.run("/doc new")
    expect(nx.doc_dialog).to_be_visible()
    expect(nx.doc_type).to_have_value("chapter")
    expect(nx.doc_title).to_have_value("")
    expect(nx.prompt).to_have_value("")


def test_doc_new_with_type_and_title(nx, api, pid):
    nx.run("/doc new character Maya Okafor")
    expect(nx.doc_type).to_have_value("character")
    expect(nx.doc_title).to_have_value("Maya Okafor")
    nx.doc_body.fill("Cautious. Keeps ledgers.")
    nx.save_document()
    expect(nx.toast).to_contain_text("Document saved")
    docs = documents(api, pid)
    assert [(d["type"], d["title"]) for d in docs] == [("character", "Maya Okafor")]
    assert document(api, docs[0]["id"])["body"] == "Cautious. Keeps ledgers."


def test_doc_new_title_only_defaults_to_chapter(nx):
    nx.run("/doc new The Long Road")
    expect(nx.doc_type).to_have_value("chapter")
    expect(nx.doc_title).to_have_value("The Long Road")


def test_document_requires_a_title(nx, api, pid):
    nx.run("/doc new")
    nx.doc_body.fill("body without a title")
    nx.save_document()
    expect(nx.toast).to_contain_text("A title is required")
    expect(nx.doc_dialog).to_be_visible()
    assert documents(api, pid) == []


def test_doc_open_edits_an_existing_document(nx, api, make_doc):
    doc = make_doc("chapter", "Chapter 5", "Original text.")
    nx.reload()
    nx.run("/doc open chapter 5")
    expect(nx.doc_dialog).to_be_visible()
    expect(nx.doc_title).to_have_value("Chapter 5")
    expect(nx.doc_type).to_be_disabled()
    nx.edit_document()
    expect(nx.doc_body).to_have_value("Original text.")
    nx.doc_body.fill("Edited text.")
    nx.save_document()
    expect(nx.toast).to_contain_text("Document saved")
    assert document(api, doc["id"])["body"] == "Edited text."


def test_doc_open_rejects_missing_and_ambiguous_titles(nx, make_doc):
    make_doc("chapter", "Chapter 5")
    make_doc("chapter", "Chapter 6")
    nx.reload()
    nx.run("/doc open")
    expect(nx.toast).to_contain_text("Usage: /doc open")
    nx.run("/doc open zebra")
    expect(nx.toast).to_contain_text('No single document matches "zebra"')
    nx.run("/doc open chapter")
    expect(nx.toast).to_contain_text("No single document matches")
    expect(nx.doc_dialog).to_be_hidden()


def test_doc_list_toast_and_pane(nx, make_doc):
    nx.run("/doc list")
    expect(nx.toast).to_contain_text("No documents yet")
    make_doc("chapter", "Chapter 5")
    make_doc("note", "Loose idea")
    nx.reload()
    nx.run("/doc list")
    expect(nx.toast).to_contain_text("2 document(s)")
    nx.set_prompt("/doc list")
    expect(nx.pane.get_by_role("button", name="Chapter 5")).to_be_visible()
    nx.pane.get_by_role("button", name="Loose idea").click()
    expect(nx.doc_title).to_have_value("Loose idea")


def test_doc_unknown_subcommand_is_refused(nx):
    nx.run("/doc frobnicate")
    expect(nx.toast).to_contain_text('Unknown option "frobnicate" for /doc')
    nx.run("/doc")
    expect(nx.toast).to_contain_text("No documents yet")


def test_document_dialog_closes_three_ways(nx):
    for how in ("button", "escape", "backdrop"):
        nx.run("/doc new")
        expect(nx.doc_dialog).to_be_visible()
        if how == "button":
            nx.doc_dialog.get_by_role("button", name="Close").click()
        elif how == "escape":
            nx.page.keyboard.press("Escape")
        else:
            nx.page.locator("#documentModal").click(position={"x": 5, "y": 5})
        expect(nx.doc_dialog).to_be_hidden()


# ---- /chat
def test_chat_list_and_open(nx, api, pid):
    nx.run("/chat list")
    expect(nx.toast).to_contain_text("No conversations yet")
    nx.ask("Explore trade routes through the mountains")
    nx.run("/new")
    nx.run("/chat list")
    expect(nx.toast).to_contain_text("1 conversation(s)")
    nx.set_prompt("/chat list")
    nx.pane.get_by_role(
        "button", name="Explore trade routes through the mountains"
    ).click()
    expect(nx.conversation).to_be_visible()
    expect(nx.user_messages).to_have_count(1)
    expect(nx.replies).to_have_count(1)


def test_chat_open_by_partial_title_and_rejections(nx):
    nx.ask("Explore trade routes through the mountains")
    nx.ask("Explore harbor taxes")
    nx.run("/new")
    nx.run("/chat open")
    expect(nx.toast).to_contain_text("Usage: /chat open")
    nx.run("/chat open zebra")
    expect(nx.toast).to_contain_text('No single conversation matches "zebra"')
    nx.run("/chat open Explore")
    expect(nx.toast).to_contain_text("No single conversation matches")
    nx.run("/chat open harbor")
    expect(nx.conversation).to_be_visible()


def test_chat_unknown_subcommand_is_refused(nx):
    nx.run("/chat frobnicate")
    expect(nx.toast).to_contain_text('Unknown option "frobnicate" for /chat')


# ---- /search
def test_search_command_opens_the_archive_with_the_query(nx, make_doc):
    make_doc("chapter", "Chapter 5", "The lighthouse keeper counted ships.")
    nx.reload()
    nx.run("/search lighthouse")
    expect(nx.search_dialog).to_be_visible()
    expect(nx.search_input).to_have_value("lighthouse")
    nx.search_dialog.get_by_role("button", name="Chapter 5").click()
    expect(nx.doc_title).to_have_value("Chapter 5")


def test_search_pane_previews_results_while_typing(nx, make_doc):
    make_doc("note", "Harbor notes", "tariffs on salt")
    nx.reload()
    nx.set_prompt("/search salt")
    expect(nx.pane.get_by_role("button", name="Harbor notes")).to_be_visible()
    nx.set_prompt("/search zebra")
    expect(nx.pane).to_contain_text("Nothing found")
    nx.set_prompt("/search")
    expect(nx.pane).to_contain_text("Type after /search")


# ---- /export
def test_export_downloads_portable_json(nx, api, pid, make_doc):
    make_doc("note", "Loose idea", "export me")
    nx.reload()
    nx.ask("Explore a first idea")
    with nx.page.expect_download() as info:
        nx.run("/export")
    dl = info.value
    assert dl.suggested_filename.startswith(
        "prompt-nexus-"
    ) and dl.suggested_filename.endswith(".json")
    data = json.loads(Path(dl.path()).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert [d["title"] for d in data["documents"]] == ["Loose idea"]
    assert (
        len(data["conversations"]) == 1
        and len(messages(api, data["conversations"][0]["id"])) == 2
    )
