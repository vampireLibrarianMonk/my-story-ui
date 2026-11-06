"""Paths: archive search (Ctrl+K and /search), dialogs, keyboard shortcuts and the research boundary."""

from __future__ import annotations

from playwright.sync_api import expect

from .planned import known_bug, planned


def seed(nx, make_doc):
    make_doc("chapter", "Chapter 5", "The lighthouse keeper counted ships.")
    make_doc("note", "Harbor notes", "tariffs on salt")
    nx.reload()


def test_ctrl_k_opens_search_and_escape_closes_it(nx):
    nx.page.keyboard.press("Control+k")
    expect(nx.search_dialog).to_be_visible()
    expect(nx.search_input).to_be_focused()
    expect(nx.search_dialog).to_contain_text("not the internet")
    nx.page.keyboard.press("Escape")
    expect(nx.search_dialog).to_be_hidden()


def test_search_finds_documents_and_conversations(nx, make_doc):
    seed(nx, make_doc)
    nx.ask("Explore the lighthouse legend")
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("lighthouse")
    results = nx.search_dialog.locator(".search-result")
    expect(results.filter(has_text="CHAPTER")).to_have_count(1)
    expect(results.filter(has_text="CONVERSATION").first).to_be_visible()


@known_bug(
    "Conversation search returns one row per matching message, so a single thread appears twice"
)
def test_search_lists_each_conversation_once(nx, make_doc):
    seed(nx, make_doc)
    nx.ask("Explore the lighthouse legend")
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("lighthouse")
    expect(
        nx.search_dialog.locator(".search-result").filter(has_text="CONVERSATION")
    ).to_have_count(1, timeout=1500)


def test_search_result_opens_the_document_or_the_thread(nx, make_doc):
    seed(nx, make_doc)
    nx.ask("Explore the lighthouse legend")
    nx.run("/new")
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("lighthouse")
    nx.search_dialog.locator(".search-result").filter(
        has_text="CONVERSATION"
    ).first.click()
    expect(nx.conversation).to_be_visible()
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("salt")
    nx.search_dialog.get_by_role("button", name="Harbor notes").click()
    expect(nx.doc_title).to_have_value("Harbor notes")


def test_search_empty_and_no_match_messages(nx, make_doc):
    seed(nx, make_doc)
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("zebra")
    expect(nx.search_dialog).to_contain_text("Nothing found in this project yet")
    nx.search_input.fill("")
    expect(nx.search_dialog).to_contain_text(
        "Type to search chapters, notes, and conversations"
    )


def test_search_treats_wildcards_literally(nx, make_doc):
    make_doc("note", "Percent", "grew 50% in a year")
    make_doc("note", "Plain", "nothing special here")
    nx.reload()
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("%")
    expect(nx.search_dialog.locator(".search-result")).to_have_count(1)
    nx.search_input.fill("_")
    expect(nx.search_dialog).to_contain_text("Nothing found")


def test_search_is_scoped_to_the_current_project(nx, make_doc):
    seed(nx, make_doc)
    nx.run("/project new Elsewhere")
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("lighthouse")
    expect(nx.search_dialog).to_contain_text("Nothing found")


def test_search_dialog_closes_by_button_and_backdrop(nx):
    nx.page.keyboard.press("Control+k")
    nx.search_dialog.get_by_role("button", name="×").click()
    expect(nx.search_dialog).to_be_hidden()
    nx.page.keyboard.press("Control+k")
    nx.page.locator("#searchModal").click(position={"x": 5, "y": 5})
    expect(nx.search_dialog).to_be_hidden()


def test_rapid_typing_shows_results_for_the_final_query_only(nx, make_doc):
    seed(nx, make_doc)
    nx.page.keyboard.press("Control+k")
    nx.search_input.press_sequentially("harbor", delay=20)
    expect(nx.search_dialog.locator(".search-result")).to_have_count(1)
    expect(nx.search_dialog).to_contain_text("Harbor notes")


def test_dialogs_are_modal_to_assistive_tech(nx):
    nx.run("/doc new")
    expect(nx.doc_dialog).to_have_attribute("aria-modal", "true")
    nx.page.keyboard.press("Escape")
    nx.page.keyboard.press("Control+k")
    expect(nx.search_dialog).to_have_attribute("aria-modal", "true")


def open_doc_dialog(nx):
    nx.run("/doc new")
    expect(
        nx.doc_title
    ).to_be_focused()  # the app moves focus into the dialog after a short delay


@known_bug(
    "Focus is not trapped in dialogs, so Tab leaves the dialog and reaches the page behind it"
)
def test_focus_stays_inside_an_open_dialog(nx):
    open_doc_dialog(nx)
    for _ in range(12):
        nx.page.keyboard.press("Tab")
        assert nx.page.evaluate("!!document.activeElement.closest('#documentModal')"), (
            "focus left the dialog"
        )


@known_bug(
    "Closing a dialog does not return focus to the prompt, so keyboard users land on the page body"
)
def test_focus_returns_to_the_prompt_after_closing_a_dialog(nx):
    open_doc_dialog(nx)
    nx.page.keyboard.press("Escape")
    expect(nx.doc_dialog).to_be_hidden()
    expect(nx.prompt).to_be_focused(timeout=1500)


def test_research_mode_never_claims_live_web_access(nx):
    nx.set_prompt("Research the historical accuracy of the debate")
    expect(nx.pane).to_contain_text("No live web search is connected")
    expect(nx.pane).to_contain_text(
        "independently verified citations require a separate retrieval connector"
    )


@planned(
    "Research retrieval with checkable citations, labelled web vs project archive (KIRO_REBUILD_BRIEF stage 6)"
)
def test_research_sources_can_be_attached(nx):
    nx.set_prompt("Research the historical accuracy of the debate")
    expect(nx.pane.get_by_role("button", name="Search sources")).to_be_visible()


@planned("Semantic plus keyword hybrid search (README: LIKE matching only)")
def test_search_finds_synonyms(nx, make_doc):
    make_doc("note", "Ships", "The vessel left the port at dawn.")
    nx.reload()
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("boat")
    expect(nx.search_dialog.locator(".search-result")).to_have_count(1)
