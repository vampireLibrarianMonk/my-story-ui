"""Paths: keyboard-only use, responsive layout, and the sidebar's removal."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from .planned import known_bug, planned


def test_there_is_no_sidebar_and_nothing_is_lost(nx):
    expect(nx.page.get_by_role("navigation", name="Navigation")).to_have_count(0)
    expect(nx.page.locator("aside.rail")).to_have_count(0)
    expect(nx.page.get_by_role("navigation", name="Workspace status")).to_be_visible()
    expect(nx.page.get_by_role("button", name="Export this project")).to_have_count(0)


def test_top_bar_has_no_project_or_model_controls(nx):
    banner = nx.page.get_by_role("banner")
    expect(banner.get_by_role("combobox")).to_have_count(0)
    expect(banner.get_by_role("button")).to_have_count(1)  # the brand


def test_whole_workflow_is_reachable_by_keyboard_alone(nx, api, pid, make_doc):
    make_doc("chapter", "Chapter 5", "Original.")
    nx.reload()
    nx.prompt.focus()
    nx.prompt.press_sequentially("/doc open chapter 5")
    nx.prompt.press("Control+Enter")
    expect(nx.doc_dialog).to_be_visible()
    nx.page.keyboard.press("Escape")
    nx.prompt.focus()
    nx.prompt.press_sequentially("/m")
    nx.prompt.press("Tab")
    nx.prompt.press("Tab")
    expect(nx.prompt).to_have_value("/model demo")


def test_tab_order_starts_with_the_brand_then_chips_then_prompt(nx):
    order = []
    nx.page.locator("body").click(position={"x": 2, "y": 2})
    for _ in range(7):
        nx.page.keyboard.press("Tab")
        order.append(
            nx.page.evaluate(
                "document.activeElement.id || document.activeElement.tagName"
            )
        )
    assert order[:6] == [
        "homeBrand",
        "chipProject",
        "chipModel",
        "chipDocs",
        "chipChats",
        "promptInput",
    ]


def test_brand_is_keyboard_operable(nx):
    nx.ask("Explore alpha")
    nx.page.locator("#homeBrand").focus()
    nx.page.keyboard.press("Enter")
    expect(nx.conversation).to_be_hidden()


def test_focus_ring_is_visible_on_the_prompt(nx):
    nx.prompt.focus()
    outline = nx.page.evaluate(
        "getComputedStyle(document.querySelector('#promptInput')).outlineStyle"
    )
    box = nx.page.evaluate(
        "getComputedStyle(document.querySelector('.composer-card')).borderColor"
    )
    assert outline != "none" or box


@pytest.mark.parametrize(
    "width, height", [(1600, 1000), (1180, 800), (950, 800), (720, 900), (390, 800)]
)
def test_no_horizontal_scroll_at_common_widths(nx, width, height):
    nx.page.set_viewport_size({"width": width, "height": height})
    nx.set_prompt("Resume the scene")
    overflow = nx.page.evaluate(
        "document.documentElement.scrollWidth - window.innerWidth"
    )
    assert overflow <= 0


def test_commands_work_at_phone_width(nx):
    nx.page.set_viewport_size({"width": 390, "height": 800})
    nx.run("/project new Mobile")
    expect(nx.project_chip).to_have_text("Mobile")
    nx.set_prompt("/")
    expect(nx.options).to_have_count(8)
    box = nx.suggestions.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390


def test_context_pane_stacks_below_on_a_phone(nx):
    nx.page.set_viewport_size({"width": 390, "height": 800})
    nx.set_prompt("Resume the scene")
    expect(nx.widget("Next step")).to_be_visible()


def test_text_can_be_zoomed_to_200_percent_without_losing_the_prompt(nx):
    nx.page.set_viewport_size({"width": 640, "height": 800})
    nx.page.evaluate("document.documentElement.style.fontSize='200%'")
    expect(nx.prompt).to_be_visible()
    expect(nx.send_button).to_be_visible()


@known_bug("The open suggestion menu is drawn over the status chips")
def test_menu_does_not_hide_the_status_chips(nx):
    nx.set_prompt("/")
    expect(nx.suggestions).to_be_visible()
    chips = nx.page.locator("#statusStrip").bounding_box()
    menu = nx.suggestions.bounding_box()
    assert (
        menu["y"] + menu["height"] <= chips["y"]
        or menu["y"] >= chips["y"] + chips["height"]
    )


def test_reduced_motion_is_respected(nx):
    nx.page.emulate_media(reduced_motion="reduce")
    dur = nx.page.evaluate(
        "getComputedStyle(document.querySelector('.mode-pulse')).animationName"
    )
    assert dur == "none"


@planned("Dark theme following prefers-color-scheme")
def test_dark_theme(nx):
    nx.page.emulate_media(color_scheme="dark")
    bg = nx.page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg != "rgb(251, 252, 250)"
