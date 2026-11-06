"""Paths: the prompt's intent guess, manual override, per-mode widgets, and widgets reaching the request."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .planned import known_bug, planned

# prompt -> (status label, send button text)
DETECTION = [
    ("Resume the scene after the argument", "Continue writing", "Continue"),
    ("Write chapter 4 about the harbor", "New chapter", "Draft chapter"),
    ("Research the historical accuracy of the debate", "Research", "Research"),
    ("Discuss the protagonist's motivation", "Character", "Character"),
    ("Create a religion for the kingdom", "Worldbuilding", "Worldbuilding"),
    ("What if she refuses?", "Explore", "Explore"),
]

# mode -> widget labels the pane must show (the first entry may be a document picker)
WIDGETS = {
    "Resume the scene after the argument": ["Resume from", "Next step", "Continuity"],
    "Write chapter 4 about the harbor": [
        "Chapter context",
        "Point of view",
        "Tone",
        "Scope",
    ],
    "Research the historical accuracy of the debate": [
        "Research approach",
        "Uncertainty",
    ],
    "Discuss the protagonist's motivation": ["Focus document", "Focus", "Format"],
    "Create a religion for the kingdom": ["Focus document", "Domain", "Lens"],
}


def test_empty_state_has_no_widgets_and_a_placeholder(nx):
    expect(nx.pane_title).to_have_text("Context, when needed.")
    expect(nx.pane).to_contain_text("Start with an idea")
    expect(nx.mode_status).to_have_text("Suggested: Explore")
    expect(nx.send_button).to_contain_text("Explore")


@pytest.mark.parametrize("prompt, label, button", DETECTION)
def test_intent_is_guessed_while_typing(nx, prompt, label, button):
    nx.set_prompt(prompt)
    expect(nx.mode_status).to_have_text(f"Suggested: {label}")
    expect(nx.send_button).to_contain_text(button)


@pytest.mark.parametrize("prompt, labels", list(WIDGETS.items()))
def test_each_mode_shows_its_widgets(nx, prompt, labels):
    nx.set_prompt(prompt)
    for label in labels:
        expect(nx.widget(label)).to_be_visible()


def test_clearing_the_prompt_returns_to_the_empty_pane(nx):
    nx.set_prompt("Resume the scene")
    expect(nx.widget("Next step")).to_be_visible()
    nx.set_prompt("")
    expect(nx.pane_title).to_have_text("Context, when needed.")


def test_each_prompt_is_classified_afresh_in_one_thread(nx):
    nx.ask("Resume the scene after the argument")
    expect(nx.mode_status).to_have_text(
        "Suggested: Explore"
    )  # composer resets after a send
    nx.set_prompt("Research historical analogues to the monarchy's response")
    expect(nx.mode_status).to_have_text("Suggested: Research")
    expect(nx.widget("Research approach")).to_be_visible()
    nx.run("Research historical analogues to the monarchy's response")
    expect(nx.replies).to_have_count(2)
    expect(nx.replies.nth(0)).to_contain_text("CONTINUE WRITING")
    expect(nx.replies.nth(1)).to_contain_text("RESEARCH")


@known_bug(
    "Explore is the default mode, so typing a plain prompt never leaves the empty placeholder and its widgets stay hidden"
)
def test_explore_mode_shows_its_widgets_when_typing(nx):
    nx.set_prompt("What if she refuses?")
    expect(nx.widget("Approach")).to_be_visible(timeout=1500)
    expect(nx.widget("Deliverable")).to_be_visible(timeout=1500)


def test_explore_widgets_show_after_choosing_the_pill(nx):
    nx.pill("Explore").click()
    expect(nx.widget("Approach")).to_be_visible()
    nx.widget("Deliverable").select_option("Idea list")
    nx.set_prompt("What if she refuses?")
    sent = nx.send_and_capture()
    assert sent["options"] == {
        "approach": "Discuss possibilities",
        "output": "Idea list",
    }


# ---- manual override
def test_pill_overrides_the_guess_and_toggles_off(nx):
    nx.set_prompt("What if she refuses?")
    nx.pill("Character").click()
    expect(nx.mode_status).to_have_text("Selected: Character")
    expect(nx.pill("Character")).to_have_attribute("aria-pressed", "true")
    expect(nx.send_button).to_contain_text("Character")
    nx.pill("Character").click()
    expect(nx.mode_status).to_have_text("Suggested: Explore")
    expect(nx.pill("Character")).to_have_attribute("aria-pressed", "false")


def test_override_beats_typed_keywords_and_shows_widgets_without_text(nx):
    nx.pill("Worldbuilding").click()
    expect(nx.widget("Domain")).to_be_visible()
    nx.set_prompt("Resume the scene after the argument")
    expect(nx.mode_status).to_have_text("Selected: Worldbuilding")
    expect(nx.widget("Domain")).to_be_visible()


def test_override_is_sent_as_the_mode(nx):
    nx.set_prompt("a plain sentence")
    nx.pill("Research").click()
    sent = nx.send_and_capture()
    assert sent["mode"] == "research"


def test_override_clears_after_sending(nx):
    nx.pill("Research").click()
    nx.run("a plain sentence")
    expect(nx.replies).to_have_count(1)
    expect(nx.pill("Research")).to_have_attribute("aria-pressed", "false")
    expect(nx.mode_status).to_have_text("Suggested: Explore")


def test_example_cards_fill_the_prompt_and_pick_a_mode(nx):
    nx.page.get_by_role("button", name="Begin a chapter").click()
    expect(nx.prompt).to_have_value(
        "Start a new chapter that opens with a character arriving somewhere unfamiliar."
    )
    expect(nx.mode_status).to_have_text("Suggested: New chapter")
    nx.page.get_by_role("button", name="Investigate an idea").click()
    expect(nx.mode_status).to_have_text("Suggested: Research")
    expect(nx.pane).to_contain_text("No live web search is connected")


# ---- widgets reach the request
def test_default_widget_values_are_sent(nx):
    nx.set_prompt("Resume the scene after the argument")
    sent = nx.send_and_capture()
    assert sent["mode"] == "continue"
    assert sent["options"] == {
        "direction": "Continue directly",
        "consistency": "Preserve voice and facts",
    }


def test_changed_widget_values_are_sent(nx):
    nx.set_prompt("Write chapter 4 about the harbor")
    nx.widget("Tone").select_option("Urgent")
    nx.widget("Point of view").select_option("First person")
    nx.widget("Scope").select_option("Chapter outline")
    sent = nx.send_and_capture()
    assert sent["options"] == {
        "point_of_view": "First person",
        "tone": "Urgent",
        "length": "Chapter outline",
    }


def test_widgets_reset_when_the_mode_changes(nx):
    nx.set_prompt("Write chapter 4 about the harbor")
    nx.widget("Tone").select_option("Urgent")
    nx.set_prompt("Resume the scene after the argument")
    nx.set_prompt("Write chapter 4 about the harbor")
    expect(nx.widget("Tone")).to_have_value("Literary and restrained")


def test_research_widgets_are_sent(nx):
    nx.set_prompt("Research the historical accuracy of the debate")
    nx.widget("Uncertainty").select_option("Challenge all unsupported claims")
    sent = nx.send_and_capture()
    assert sent["options"]["rigor"] == "Challenge all unsupported claims"


def test_every_widget_choice_is_selectable(nx, api):
    boot = api.get("/api/bootstrap").json()
    for mode, widgets in boot["widgets"].items():
        nx.pill_for(mode).click()
        for w in widgets:
            sel = nx.widget(w["label"])
            for choice in w["choices"]:
                sel.select_option(choice)
                expect(sel).to_have_value(choice)
        nx.pill_for(mode).click()


# ---- planned
@planned(
    "Widget schemas become data-driven ModeDefinition/WidgetDefinition with visibility rules (DESIGN.md)"
)
def test_widget_visibility_rules(nx):
    nx.set_prompt("Resume the scene after the argument")
    expect(nx.widget("Revise which passage")).to_be_hidden()
    nx.widget("Next step").select_option("Revise last passage")
    expect(nx.widget("Revise which passage")).to_be_visible()


@planned(
    "A small optional classifier explains why a mode was suggested (KIRO_REBUILD_BRIEF: explainable, non-blocking)"
)
def test_suggestion_explains_itself(nx):
    nx.set_prompt("Resume the scene after the argument")
    expect(nx.page.get_by_role("button", name="Why this mode?")).to_be_visible()
