"""Paths: sending, the transcript, follow-ups in one thread, reopening history, and the busy state."""

from __future__ import annotations

from playwright.sync_api import expect

from .conftest import conversations, messages
from .planned import known_bug, planned


def test_first_send_creates_a_thread_and_archives_both_messages(nx, api, pid):
    nx.ask("Explore why the council refuses")
    expect(nx.conversation).to_be_visible()
    expect(nx.page.locator("#threadTitle")).to_have_text(
        "Explore why the council refuses"
    )
    expect(nx.user_messages).to_have_count(1)
    expect(nx.last_reply).to_contain_text("[DEMO RESPONSE")
    expect(nx.last_reply).to_contain_text("DEMO")
    convos = conversations(api, pid)
    assert len(convos) == 1
    stored = messages(api, convos[0]["id"])
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert stored[0]["content"] == "Explore why the council refuses"


def test_composer_resets_after_a_send(nx):
    nx.pill("Research").click()
    nx.ask("a plain sentence")
    expect(nx.prompt).to_have_value("")
    expect(nx.mode_status).to_have_text("Suggested: Explore")
    expect(nx.pane_title).to_have_text("Context, when needed.")


def test_follow_up_stays_in_the_same_thread(nx, api, pid):
    nx.ask("Explore why the council refuses")
    nx.ask("Resume the scene after the argument")
    nx.ask("Research historical analogues")
    expect(nx.user_messages).to_have_count(3)
    convos = conversations(api, pid)
    assert len(convos) == 1
    stored = messages(api, convos[0]["id"])
    assert [m["mode"] for m in stored if m["role"] == "user"] == [
        "explore",
        "continue",
        "research",
    ]
    assert len(stored) == 6


def test_reply_header_names_the_provider_and_mode(nx):
    nx.pill("Character").click()
    nx.ask("anything at all")
    expect(nx.last_reply.locator(".message-meta")).to_have_text("DEMO · CHARACTER")


def test_reply_text_is_rendered_as_text_not_html(nx):
    nx.ask("<img src=x onerror=window.__pwned=1> and <b>bold</b>")
    expect(nx.user_messages.first).to_contain_text("<b>bold</b>")
    assert nx.page.evaluate("window.__pwned") is None
    assert nx.page.locator(".message-content b").count() == 0


def test_blank_prompt_is_not_sent(nx, api, pid):
    nx.run("   ")
    expect(nx.prompt).to_be_focused()
    assert conversations(api, pid) == []
    expect(nx.user_messages).to_have_count(0)


def test_ctrl_enter_sends_and_plain_enter_adds_a_line(nx, api, pid):
    nx.prompt.press_sequentially("first line")
    nx.prompt.press("Enter")
    nx.prompt.press_sequentially("second line")
    expect(nx.prompt).to_have_value("first line\nsecond line")
    assert conversations(api, pid) == []
    nx.send()
    expect(nx.replies).to_have_count(1)


def test_send_button_sends(nx):
    nx.set_prompt("Explore a thing")
    nx.send_button.click()
    expect(nx.replies).to_have_count(1)


def test_title_uses_only_the_first_line_and_is_capped(nx, api, pid):
    nx.ask("L" * 100 + "\nsecond line")
    title = conversations(api, pid)[0]["title"]
    assert title == "L" * 75


def test_very_long_prompt_is_accepted_up_to_the_limit_and_rejected_beyond(nx, api, pid):
    nx.set_prompt("a" * 50001)
    nx.send()
    expect(nx.toast).to_contain_text("Request failed (422)")
    assert conversations(api, pid) == []


def test_new_thought_leaves_history_and_reopening_restores_it(nx, api, pid):
    nx.ask("Explore why the council refuses")
    nx.ask("Resume the scene after the argument")
    nx.run("/new")
    expect(nx.conversation).to_be_hidden()
    nx.run("/chat open council")
    expect(nx.user_messages).to_have_count(2)
    expect(nx.replies).to_have_count(2)
    expect(nx.page.locator("#threadTitle")).to_have_text(
        "Explore why the council refuses"
    )
    nx.ask("One more question")
    assert len(conversations(api, pid)) == 1
    assert len(messages(api, conversations(api, pid)[0]["id"])) == 6


def test_two_threads_stay_separate(nx, api, pid):
    nx.ask("Explore alpha")
    nx.run("/new")
    nx.ask("Explore beta")
    assert len(conversations(api, pid)) == 2
    expect(nx.user_messages).to_have_count(1)


def test_brand_click_starts_a_new_thought(nx):
    nx.ask("Explore alpha")
    nx.page.locator("#homeBrand").click()
    expect(nx.conversation).to_be_hidden()


def test_new_thought_button_inside_a_thread(nx):
    nx.ask("Explore alpha")
    nx.page.get_by_role("button", name="New thought").click()
    expect(nx.conversation).to_be_hidden()


def test_send_button_is_busy_and_disabled_while_waiting(nx):
    nx.page.route(
        "**/api/chat", lambda route: (nx.page.wait_for_timeout(700), route.continue_())
    )
    nx.set_prompt("Explore a thing")
    nx.send_button.click()
    expect(nx.send_button).to_be_disabled()
    expect(nx.send_button).to_contain_text("Thinking")
    expect(nx.replies).to_have_count(1)
    expect(nx.send_button).to_be_enabled()


def test_double_submit_sends_only_one_request(nx, api, pid):
    seen = []
    nx.page.on(
        "request", lambda r: seen.append(1) if r.url.endswith("/api/chat") else None
    )
    nx.set_prompt("Explore a thing")
    nx.prompt.press("Control+Enter")
    nx.prompt.press("Control+Enter")
    expect(nx.replies).to_have_count(1)
    assert len(seen) == 1
    assert len(conversations(api, pid)) == 1


@known_bug(
    "The history sent to the model is the last 12 stored messages but nothing tells the user older turns were dropped"
)
def test_long_threads_warn_when_history_is_trimmed(nx):
    for i in range(7):
        nx.ask(f"turn {i}")
    expect(nx.conversation).to_contain_text(
        "earlier messages are no longer sent", timeout=1500
    )


@planned(
    "Streaming replies with a Stop button (README: known limitation; KIRO_REBUILD_BRIEF stage 3)"
)
def test_stop_a_streaming_reply(nx):
    nx.set_prompt("Explore a thing")
    nx.send_button.click()
    expect(nx.page.get_by_role("button", name="Stop")).to_be_visible()


@planned("Regenerate the last reply (README: cancellation and retry are future work)")
def test_regenerate_last_reply(nx):
    nx.ask("Explore a thing")
    nx.reply_action("Regenerate").click()
    expect(nx.replies).to_have_count(1)


@planned("Rename or delete a conversation")
def test_rename_a_conversation(nx):
    nx.ask("Explore a thing")
    nx.run("/chat rename Better title")
    expect(nx.page.locator("#threadTitle")).to_have_text("Better title")
