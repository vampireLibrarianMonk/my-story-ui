"""Paths: provider switching, a real upstream failure (Arc configured, nothing listening), and secrecy."""

from __future__ import annotations

from playwright.sync_api import expect

from .conftest import ARC_SECRET, conversations, messages
from .planned import known_bug, planned


# ---- /model
def test_model_commands_and_aliases(nx):
    nx.run("/model list")
    expect(nx.toast).to_contain_text("Demo · no model")
    expect(nx.toast).to_contain_text("Local · Intel Arc (not configured)")
    nx.run("/model")
    expect(nx.toast).to_contain_text("AWS · Bedrock (not configured)")
    nx.run("list models")
    expect(nx.toast).to_contain_text("Demo · no model")


def test_unconfigured_models_are_refused_with_guidance(nx):
    for text in (
        "/model arc",
        "/model bedrock",
        "switch model to aws",
        "use the local model",
    ):
        nx.run(text)
        expect(nx.toast).to_contain_text("is not configured on the server")
        expect(nx.model_chip).to_have_text("Demo · no model")


def test_unknown_model_is_refused(nx):
    nx.run("/model gpt-17")
    expect(nx.toast).to_contain_text('No model matches "gpt-17"')


def test_switching_to_demo_warns_that_replies_are_placeholders(nx):
    nx.run("/model demo")
    expect(nx.toast).to_contain_text("replies are placeholders")


def test_configured_model_can_be_selected_and_is_sent(nx_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    expect(n.model_chip).to_have_text("Local · Intel Arc")
    n.set_prompt("Explore a thing")
    assert n.send_and_capture()["provider"] == "arc"


def test_model_choice_applies_to_the_next_prompt_only_through_the_chip(nx_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.run("/model demo")
    n.set_prompt("Explore a thing")
    assert n.send_and_capture()["provider"] == "demo"


def test_model_command_does_not_start_a_conversation(nx, api, pid):
    nx.run("/model demo")
    assert conversations(api, pid) == []


def test_model_choice_survives_switching_project(nx_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.run("/project new Second")
    expect(n.model_chip).to_have_text("Local · Intel Arc")


@planned("Remember the chosen model across reloads (today every boot starts in Demo)")
def test_model_choice_survives_reload(nx_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.reload()
    expect(n.model_chip).to_have_text("Local · Intel Arc", timeout=1500)


# ---- upstream failure
def test_provider_failure_keeps_the_prompt_and_invents_no_reply(
    nx_arc_down, api_arc_down
):
    n = nx_arc_down
    n.run("/model arc")
    n.set_prompt("A lost scene that must not vanish")
    n.send()
    expect(n.toast).to_contain_text("Arc service failed")
    expect(n.prompt).to_have_value("A lost scene that must not vanish")
    expect(n.user_messages).to_have_count(1)
    expect(n.replies).to_have_count(0)
    expect(n.send_button).to_be_enabled()
    pid = api_arc_down.get("/api/bootstrap").json()["projects"][0]["id"]
    convo = conversations(api_arc_down, pid)
    assert len(convo) == 1
    stored = messages(api_arc_down, convo[0]["id"])
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "A lost scene that must not vanish")
    ]


def test_retry_after_failure_succeeds_in_the_same_thread(nx_arc_down, api_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.run("Explore a thing")
    expect(n.toast).to_contain_text("Arc service failed")
    n.run("/model demo")
    n.prompt.fill("Explore a thing")
    n.send()
    expect(n.replies).to_have_count(1)
    pid = api_arc_down.get("/api/bootstrap").json()["projects"][0]["id"]
    assert len(conversations(api_arc_down, pid)) == 1


def test_error_text_never_contains_the_api_key(nx_arc_down, api_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.run("Explore a thing")
    expect(n.toast).to_contain_text("Arc service failed")
    assert ARC_SECRET not in n.page.content()
    assert ARC_SECRET not in api_arc_down.get("/api/bootstrap").text
    pid = api_arc_down.get("/api/bootstrap").json()["projects"][0]["id"]
    assert ARC_SECRET not in api_arc_down.get(f"/api/projects/{pid}/export").text


def test_unconfigured_provider_is_rejected_server_side_without_a_trace(nx, api, pid):
    res = api.post(
        "/api/chat", json={"project_id": pid, "prompt": "hi", "provider": "bedrock"}
    )
    assert res.status_code == 400
    assert conversations(api, pid) == []


def test_invalid_mode_is_rejected_without_a_trace(nx, api, pid):
    assert (
        api.post(
            "/api/chat", json={"project_id": pid, "prompt": "hi", "mode": "nonsense"}
        ).status_code
        == 422
    )
    assert conversations(api, pid) == []


def test_cross_project_context_is_rejected(nx, api, pid, make_doc):
    other = api.post("/api/projects", json={"name": "Other"}).json()["id"]
    foreign = make_doc("note", "Secret", "no leakage", project_id=other)
    res = api.post(
        "/api/chat",
        json={"project_id": pid, "prompt": "hi", "context_ids": [foreign["id"]]},
    )
    assert res.status_code == 400


@known_bug(
    "A rejected chat request (foreign document) still leaves an empty conversation behind, because it is created before validation"
)
def test_rejected_request_leaves_no_empty_conversation(nx, api, pid, make_doc):
    other = api.post("/api/projects", json={"name": "Other"}).json()["id"]
    foreign = make_doc("note", "Secret", "no leakage", project_id=other)
    api.post(
        "/api/chat",
        json={"project_id": pid, "prompt": "hi", "context_ids": [foreign["id"]]},
    )
    assert conversations(api, pid) == []


def test_conversation_from_another_project_cannot_be_continued(nx, api, pid):
    other = api.post("/api/projects", json={"name": "Other"}).json()["id"]
    first = api.post("/api/chat", json={"project_id": other, "prompt": "hi"}).json()
    res = api.post(
        "/api/chat",
        json={
            "project_id": pid,
            "prompt": "hi",
            "conversation_id": first["conversation_id"],
        },
    )
    assert res.status_code == 400


@known_bug(
    "A failed request shows only a toast; the thread has no inline error or retry control"
)
def test_failure_is_shown_in_the_thread_with_a_retry_button(nx_arc_down):
    n = nx_arc_down
    n.run("/model arc")
    n.run("Explore a thing")
    expect(n.conversation.get_by_role("button", name="Retry")).to_be_visible(
        timeout=1500
    )


@planned(
    "Provider capability discovery: streaming, max context, label (KIRO_REBUILD_BRIEF: supports_streaming, max_context)"
)
def test_model_list_shows_capabilities(nx):
    nx.run("/model list")
    expect(nx.toast).to_contain_text("max context")


@planned(
    "Per-request token budget and cost telemetry for Bedrock (KIRO_REBUILD_BRIEF stage 4)"
)
def test_token_budget_is_visible(nx):
    nx.set_prompt("Explore a thing")
    expect(nx.pane).to_contain_text("tokens")
