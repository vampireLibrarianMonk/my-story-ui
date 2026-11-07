"""Paths: turning a reply into a document, and the golden path: review an append before it is saved."""

from __future__ import annotations

import re

from playwright.sync_api import expect

from .conftest import conversations, document, documents
from .planned import known_bug, planned


def reply_text(nx):
    return nx.last_reply.locator(".message-content").inner_text()


def test_generating_a_reply_never_creates_or_changes_a_document(nx, api, pid, make_doc):
    doc = make_doc("chapter", "Chapter 5", "Original text.")
    nx.reload()
    nx.ask("Resume the scene after the argument")
    assert document(api, doc["id"])["body"] == "Original text."
    assert len(documents(api, pid)) == 1


def test_save_as_note_opens_an_editable_review_and_saves_on_confirm(nx, api, pid):
    nx.ask("Explore a thing")
    nx.reply_action("Save as note").click()
    expect(nx.doc_dialog).to_be_visible()
    expect(nx.doc_type).to_have_value("note")
    expect(nx.doc_title).to_have_value("Selected passage")
    expect(nx.doc_body).to_have_value(reply_text(nx))
    assert documents(api, pid) == []  # nothing is saved until confirmed
    nx.doc_body.fill("Edited before saving.")
    nx.doc_title.fill("My note")
    nx.save_document()
    expect(nx.toast).to_contain_text("Document saved")
    saved = documents(api, pid)
    assert [(d["type"], d["title"]) for d in saved] == [("note", "My note")]
    assert document(api, saved[0]["id"])["body"] == "Edited before saving."
    expect(nx.docs_chip).to_contain_text("1 document")


def test_cancelling_the_review_saves_nothing(nx, api, pid):
    nx.ask("Explore a thing")
    nx.reply_action("Save as note").click()
    nx.doc_dialog.get_by_role("button", name="Close").click()
    assert documents(api, pid) == []


def test_mode_specific_save_buttons(nx, api, pid):
    cases = [
        (
            "Write chapter 4 about the harbor",
            "Save as chapter",
            "chapter",
            "New chapter",
        ),
        (
            "Discuss the protagonist's motivation",
            "Save character notes",
            "character",
            "Character exploration",
        ),
        (
            "Create a religion for the kingdom",
            "Save world notes",
            "world",
            "Worldbuilding exploration",
        ),
        (
            "Research the historical accuracy of the debate",
            "Save research notes",
            "research",
            "Research notes",
        ),
    ]
    for prompt, button, kind, title in cases:
        nx.run("/new")
        nx.ask(prompt)
        nx.reply_action(button).click()
        expect(nx.doc_type).to_have_value(kind)
        expect(nx.doc_title).to_have_value(title)
        nx.doc_dialog.get_by_role("button", name="Close").click()


def test_explore_and_continue_replies_offer_only_note_and_append(nx):
    nx.ask("Explore a thing")
    expect(nx.last_reply.get_by_role("button")).to_have_count(1)
    expect(nx.reply_action("Save as note")).to_be_visible()
    nx.ask("Resume the scene")
    expect(nx.last_reply.get_by_role("button")).to_have_count(1)


def test_append_button_appears_only_when_a_chapter_exists(nx, make_doc):
    nx.ask("Explore a thing")
    expect(nx.reply_action("Append to chapter")).to_have_count(0)
    make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.ask("Explore a thing")
    expect(nx.reply_action("Append to chapter")).to_have_count(1)


# ---- the golden path
def test_golden_path_continue_review_append_save_then_research(nx, api, pid, make_doc):
    doc = make_doc("chapter", "Chapter 5", "The hall fell silent. The envoy waited.")
    nx.reload()

    nx.set_prompt("Continue Chapter 5, following the council confrontation.")
    expect(nx.mode_status).to_have_text("Suggested: Continue writing")
    nx.widget("Resume from").select_option(label="Chapter 5")
    nx.widget("Continuity").select_option("Preserve voice and facts")
    sent = nx.send_and_capture()
    assert sent["context_ids"] == [doc["id"]] and sent["mode"] == "continue"
    expect(nx.replies).to_have_count(1)

    nx.reply_action("Append to chapter").click()
    expect(nx.doc_dialog).to_be_visible()
    expect(nx.doc_status).to_have_text("Review before saving the appended text")
    expect(nx.doc_body).to_have_value(
        "The hall fell silent. The envoy waited.\n\n" + reply_text(nx)
    )
    assert (
        document(api, doc["id"])["body"] == "The hall fell silent. The envoy waited."
    )  # still unsaved

    nx.save_document()
    expect(nx.toast).to_contain_text("Document saved")
    assert document(api, doc["id"])["body"].endswith(reply_text(nx))
    assert len(conversations(api, pid)) == 1  # the conversation stays archived

    nx.set_prompt("Research historical analogues to the monarchy's response.")
    expect(nx.mode_status).to_have_text("Suggested: Research")
    expect(nx.widget("Research approach")).to_be_visible()
    nx.send()
    expect(nx.replies).to_have_count(2)
    assert len(conversations(api, pid)) == 1


def test_append_uses_the_selected_chapter(nx, api, make_doc):
    make_doc("chapter", "Chapter 4", "Four.")
    five = make_doc("chapter", "Chapter 5", "Five.")
    nx.reload()
    nx.set_prompt("Resume the scene")
    nx.widget("Resume from").select_option(label="Chapter 5")
    nx.send()
    expect(nx.replies).to_have_count(1)
    nx.reply_action("Append to chapter").click()
    expect(nx.doc_title).to_have_value("Chapter 5")
    expect(nx.doc_body).to_have_value(re.compile(r"^Five\.\n\n"))
    assert five["id"]


@known_bug(
    "Append silently picks the most recently edited chapter when none is selected, so the wrong chapter can be edited"
)
def test_append_asks_which_chapter_when_several_exist(nx, make_doc):
    make_doc("chapter", "Chapter 4", "Four.")
    make_doc("chapter", "Chapter 5", "Five.")
    nx.reload()
    nx.ask("Resume the scene")
    nx.reply_action("Append to chapter").click()
    expect(nx.page.get_by_role("dialog", name="Choose a chapter")).to_be_visible(
        timeout=1500
    )


def test_editing_an_existing_document_is_last_write_wins(nx, api, make_doc):
    doc = make_doc("note", "Shared", "v1")
    nx.reload()
    nx.run("/doc open Shared")
    nx.edit_document()
    api.patch(f"/api/documents/{doc['id']}", json={"body": "changed elsewhere"})
    nx.doc_body.fill("my edit")
    nx.save_document()
    assert document(api, doc["id"])["body"] == "my edit"


@planned(
    "Detect that a document changed since it was opened and ask before overwriting (README: last-write-wins today)"
)
def test_stale_edit_is_flagged(nx, api, make_doc):
    doc = make_doc("note", "Shared", "v1")
    nx.reload()
    nx.run("/doc open Shared")
    nx.edit_document()
    api.patch(f"/api/documents/{doc['id']}", json={"body": "changed elsewhere"})
    nx.doc_body.fill("my edit")
    nx.save_document()
    expect(nx.toast).to_contain_text("changed since you opened it")


@planned(
    "Append shows a side-by-side diff of the proposed addition (KIRO_REBUILD_BRIEF stage 5)"
)
def test_append_shows_a_diff(nx, make_doc):
    make_doc("chapter", "Chapter 5", "Five.")
    nx.reload()
    nx.ask("Resume the scene")
    nx.reply_action("Append to chapter").click()
    expect(nx.page.get_by_role("region", name="Proposed changes")).to_be_visible()


@planned("Document revision history with restore (README: no revision history)")
def test_revision_history(nx, make_doc):
    make_doc("chapter", "Chapter 5", "Five.")
    nx.reload()
    nx.run("/doc open Chapter 5")
    nx.edit_document()
    nx.doc_body.fill("Five, revised.")
    nx.save_document()
    nx.run("/doc history Chapter 5")
    expect(nx.page.get_by_role("dialog", name="Revision history")).to_be_visible()


@planned("Delete or rename a document from the prompt")
def test_delete_a_document(nx, api, pid, make_doc):
    make_doc("note", "Temp")
    nx.reload()
    nx.run("/doc delete Temp")
    expect(nx.toast).to_contain_text("Deleted")
    assert documents(api, pid) == []


@planned(
    "Autosave and recovery of an unsaved draft after a reload (KIRO_REBUILD_BRIEF stage 5)"
)
def test_unsaved_draft_is_recovered(nx):
    nx.run("/doc new note Draft")
    nx.doc_body.fill("unsaved words")
    nx.reload()
    expect(nx.page.get_by_text("Recover unsaved draft")).to_be_visible()
