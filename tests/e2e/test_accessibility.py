"""WCAG 2.1 A/AA checks with axe-core in a real browser, across every distinct screen state.

Automated rules find only part of the problems. Screen-reader and manual keyboard review remain required.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]}
}


def found(page):
    out = Axe().run(page, options=WCAG).response["violations"]
    return [
        f"{v['id']} ({v['impact']}): {[n['target'] for n in v['nodes']][:3]}"
        for v in out
    ]


def check(page):
    problems = found(page)
    assert not problems, problems


STATES = {
    "home": lambda nx: None,
    "command menu": lambda nx: nx.set_prompt("/"),
    "project pane": lambda nx: nx.set_prompt("/project delete"),
    "model pane": lambda nx: nx.set_prompt("/model "),
    "doc list pane": lambda nx: nx.set_prompt("/doc list"),
    "chat list pane": lambda nx: nx.set_prompt("/chat list"),
    "search pane": lambda nx: nx.set_prompt("/search lighthouse"),
    "help": lambda nx: nx.set_prompt("/help"),
    "continue widgets": lambda nx: nx.set_prompt("Resume the scene"),
    "draft widgets": lambda nx: nx.set_prompt("Write chapter 4 about the harbor"),
    "research widgets": lambda nx: nx.set_prompt(
        "Research the historical accuracy of the debate"
    ),
    "explore widgets": lambda nx: nx.pill("Explore").click(),
}


@pytest.mark.parametrize("name", list(STATES))
def test_state_has_no_wcag_aa_violations(nx, make_doc, name):
    make_doc("chapter", "Chapter 5", "The lighthouse keeper counted ships.")
    nx.reload()
    STATES[name](nx)
    nx.page.wait_for_timeout(350)
    check(nx.page)


def test_conversation_with_reply_actions(nx, make_doc):
    make_doc("chapter", "Chapter 5")
    nx.reload()
    nx.ask("Write chapter 4 about the harbor")
    expect(nx.reply_action("Save as chapter")).to_be_visible()
    check(nx.page)


def test_related_material_cards(nx, make_doc):
    make_doc(
        "note", "Harbor notes", "The lighthouse keeper counted ships at the harbor."
    )
    nx.reload()
    nx.set_prompt("Explore the lighthouse keeper")
    expect(nx.related_cards).to_have_count(1)
    check(nx.page)


def test_document_dialog(nx):
    nx.run("/doc new")
    expect(nx.doc_dialog).to_be_visible()
    check(nx.page)


def test_search_dialog_with_results(nx, make_doc):
    make_doc("note", "Harbor notes", "tariffs on salt")
    nx.reload()
    nx.page.keyboard.press("Control+k")
    nx.search_input.fill("salt")
    expect(nx.search_dialog.locator(".search-result")).to_have_count(1)
    check(nx.page)


def test_toast_is_a_polite_live_region(nx):
    nx.run("/help")
    expect(nx.toast).to_have_attribute("role", "status")


def test_every_interactive_control_has_an_accessible_name(nx):
    nx.set_prompt("Resume the scene")
    nameless = nx.page.evaluate(
        """() => [...document.querySelectorAll('button, select, input, textarea, [role=button], [role=combobox]')]
            .filter(e => e.offsetParent !== null)
            .filter(e => !(e.getAttribute('aria-label') || e.labels?.length || e.textContent.trim() || e.title))
            .map(e => e.outerHTML.slice(0, 80))"""
    )
    assert nameless == []


def test_page_has_a_language_title_and_landmarks(nx):
    assert nx.page.evaluate("document.documentElement.lang") == "en"
    assert nx.page.title()
    expect(nx.page.get_by_role("banner")).to_have_count(1)
    expect(nx.page.get_by_role("main")).to_have_count(1)
    expect(nx.page.get_by_role("complementary")).to_have_count(1)
