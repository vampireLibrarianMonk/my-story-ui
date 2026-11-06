"""Paths: documents offered to the model as explicit reference context. Nothing is included silently."""

from __future__ import annotations

from playwright.sync_api import expect

from .conftest import messages
from .planned import known_bug, planned


def test_target_selector_stays_empty_without_a_chapter(nx):
    nx.set_prompt("Resume the scene after the argument")
    picker = nx.widget("Resume from")
    expect(picker.locator("option")).to_have_count(1)
    expect(picker).to_have_value("")


def test_chapters_populate_the_resume_picker(nx, make_doc):
    make_doc("chapter", "Chapter 5")
    make_doc("chapter", "Chapter 6")
    make_doc("note", "Not a chapter")
    nx.reload()
    nx.set_prompt("Resume the scene after the argument")
    options = nx.widget("Resume from").locator("option").all_inner_texts()
    assert options == ["Select a chapter...", "Chapter 6", "Chapter 5"] or sorted(
        options[1:]
    ) == ["Chapter 5", "Chapter 6"]
    assert "Not a chapter" not in options


def test_character_mode_offers_character_documents_only(nx, make_doc):
    make_doc("character", "Maya Okafor")
    make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.set_prompt("Discuss the protagonist's motivation")
    options = nx.widget("Focus document").locator("option").all_inner_texts()
    assert "Maya Okafor" in options and "Chapter 5" not in options


def test_selected_target_is_sent_and_archived(nx, api, make_doc):
    doc = make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.set_prompt("Resume the scene after the argument")
    nx.widget("Resume from").select_option(label="Chapter 5")
    sent = nx.send_and_capture()
    assert sent["context_ids"] == [doc["id"]]
    expect(nx.replies).to_have_count(1)
    stored = messages(
        api,
        api.get(f"/api/projects/{doc['project_id']}/overview").json()["conversations"][
            0
        ]["id"],
    )
    assert doc["id"] in stored[0]["context_ids"]


def test_nothing_is_sent_as_context_unless_chosen(nx, make_doc):
    make_doc("chapter", "Chapter 5", "The lighthouse keeper counted ships.")
    nx.reload()
    nx.set_prompt("Resume the lighthouse scene")
    sent = nx.send_and_capture()
    assert sent["context_ids"] == []


def test_related_material_appears_after_a_pause_and_is_opt_in(nx, make_doc):
    doc = make_doc(
        "note", "Harbor notes", "The lighthouse keeper counted ships at the harbor."
    )
    nx.reload()
    nx.set_prompt("Explore the lighthouse keeper")
    expect(nx.related_cards).to_have_count(1)
    card = nx.related_cards.first
    expect(card).to_contain_text("Harbor notes")
    expect(card).to_contain_text("Include as context")
    box = card.get_by_role("checkbox")
    expect(box).not_to_be_checked()
    box.check()
    expect(box).to_be_checked()
    sent = nx.send_and_capture()
    assert sent["context_ids"] == [doc["id"]]


@known_bug(
    "The related-material card keeps saying 'Include as context' after the box is ticked"
)
def test_related_card_label_reflects_inclusion(nx, make_doc):
    make_doc(
        "note", "Harbor notes", "The lighthouse keeper counted ships at the harbor."
    )
    nx.reload()
    nx.set_prompt("Explore the lighthouse keeper")
    card = nx.related_cards.first
    card.get_by_role("checkbox").check()
    expect(card).to_contain_text("Included in prompt", timeout=1500)


def test_unrelated_prompt_shows_no_related_material(nx, make_doc):
    make_doc("note", "Harbor notes", "The lighthouse keeper counted ships.")
    nx.reload()
    nx.set_prompt("Explore volcanic islands")
    nx.page.wait_for_timeout(600)
    expect(nx.related_cards).to_have_count(0)


def test_related_material_is_per_project(nx, api, make_doc):
    make_doc("note", "Harbor notes", "The lighthouse keeper counted ships.")
    nx.run("/project new Elsewhere")
    nx.set_prompt("Explore the lighthouse keeper")
    nx.page.wait_for_timeout(600)
    expect(nx.related_cards).to_have_count(0)


def test_command_prompts_never_search_for_related_material(nx, make_doc):
    make_doc("note", "Harbor notes", "The lighthouse keeper counted ships.")
    nx.reload()
    requests = []
    nx.page.on(
        "request", lambda r: requests.append(r.url) if "/context" in r.url else None
    )
    nx.set_prompt("/doc open lighthouse")
    nx.page.wait_for_timeout(700)
    assert requests == []


def test_context_selection_clears_on_new_thought(nx, make_doc):
    make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.set_prompt("Resume the scene after the argument")
    nx.widget("Resume from").select_option(label="Chapter 5")
    nx.run("/new")
    nx.set_prompt("Resume the scene after the argument")
    expect(nx.widget("Resume from")).to_have_value("")


@planned(
    "Include a selected passage or excerpt instead of a whole document (KIRO_REBUILD_BRIEF: user-approved excerpts)"
)
def test_attach_an_excerpt(nx, make_doc):
    make_doc("chapter", "Chapter 5", "First paragraph.\n\nSecond paragraph.")
    nx.reload()
    nx.set_prompt("Resume the scene")
    nx.page.get_by_role("button", name="Attach excerpt").click()
    expect(nx.page.get_by_role("dialog", name="Choose an excerpt")).to_be_visible()


@planned(
    "Show the model's context budget and what was truncated (README: 12 messages, 4500 chars per document)"
)
def test_context_budget_is_visible(nx, make_doc):
    make_doc("chapter", "Chapter 5", "x" * 9000)
    nx.reload()
    nx.set_prompt("Resume the scene")
    nx.widget("Resume from").select_option(label="Chapter 5")
    expect(nx.pane).to_contain_text("truncated")
