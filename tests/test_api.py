import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import providers
from app.intent import infer_mode
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("ARC_CHAT_URL", raising=False)
    monkeypatch.delenv("ARC_MODEL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    with TestClient(app) as cli:
        yield cli


def run_async(coro):
    """Run a coroutine on a private loop in a worker thread, so a loop already running in the main
    thread (for example Playwright's sync session) cannot break these unit tests."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def project(cli):
    return cli.get("/api/bootstrap").json()["projects"][0]["id"]


def test_first_run(client):
    b = client.get("/api/bootstrap").json()
    assert b["projects"][0]["name"] == "My first project"
    assert b["providers"]["demo"]["ready"]
    assert not b["providers"]["arc"]["ready"]
    assert "continue" in b["widgets"]


def test_mode_inference():
    assert infer_mode("Resume the scene after the war council") == "continue"
    assert infer_mode("Write chapter 4 about the king") == "draft"
    assert infer_mode("Research the historical accuracy of the debate") == "research"
    assert infer_mode("Discuss the protagonist’s character motivations") == "character"
    assert infer_mode("Create a religion for the kingdom") == "world"
    assert infer_mode("What if she refuses?") == "explore"


def test_document_creation_edit_search(client):
    pid = project(client)
    doc = client.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": "chapter",
            "title": "Chapter One",
            "body": "A dispute in the northern court",
        },
    ).json()
    assert doc["id"]
    ctx = client.get(
        f"/api/projects/{pid}/context", params={"q": "the northern court"}
    ).json()
    assert ctx["related"][0]["id"] == doc["id"]
    search = client.get(f"/api/projects/{pid}/search", params={"q": "northern"}).json()
    assert search["documents"][0]["title"] == "Chapter One"
    patched = client.patch(
        "/api/documents/" + doc["id"], json={"body": "Updated narrative"}
    ).json()
    assert patched["body"] == "Updated narrative"


def test_chat_and_canon_does_not_mutate(client):
    pid = project(client)
    doc = client.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": "character",
            "title": "Protagonist",
            "body": "The protagonist is still uncertain of their duty.",
        },
    ).json()
    response = client.post(
        "/api/chat",
        json={
            "project_id": pid,
            "prompt": "Explore the protagonist character motivation",
            "provider": "demo",
            "context_ids": [doc["id"]],
            "options": {"focus": "Motivations"},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "character"
    assert "DEMO RESPONSE" in data["assistant_message"]["content"]
    assert data["user_message"]["context_ids"] == json.dumps([doc["id"]])
    assert (
        client.get("/api/documents/" + doc["id"]).json()["body"]
        == "The protagonist is still uncertain of their duty."
    )
    c = client.get("/api/conversations/" + data["conversation_id"]).json()
    assert [m["role"] for m in c["messages"]] == ["user", "assistant"]
    assert (
        client.post(
            "/api/chat",
            json={
                "project_id": pid,
                "prompt": "Now continue it",
                "provider": "demo",
                "conversation_id": data["conversation_id"],
            },
        ).json()["mode"]
        == "continue"
    )


def test_invalid_cross_project_context(client):
    p1 = project(client)
    p2 = client.post("/api/projects", json={"name": "Other World"}).json()["id"]
    doc = client.post(
        "/api/documents",
        json={
            "project_id": p2,
            "type": "note",
            "title": "Secret",
            "body": "No leakage",
        },
    ).json()
    res = client.post(
        "/api/chat",
        json={"project_id": p1, "prompt": "hello", "context_ids": [doc["id"]]},
    )
    assert res.status_code == 400


def test_arc_unconfigured_is_not_fake_reply(client):
    pid = project(client)
    res = client.post(
        "/api/chat",
        json={"project_id": pid, "prompt": "Make a chapter", "provider": "arc"},
    )
    assert res.status_code == 400
    assert client.get(f"/api/projects/{pid}/overview").json()["conversations"] == []


def test_export(client):
    pid = project(client)
    client.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": "world",
            "title": "Order",
            "body": "First tenet",
        },
    )
    data = client.get(f"/api/projects/{pid}/export").json()
    assert data["schema_version"] == 1
    assert data["documents"][0]["body"] == "First tenet"


def test_errors_without_model_response_preserve_prompt(client, monkeypatch):
    from app import main

    async def fail(*args, **kwargs):
        raise providers.ProviderError("Connection refused")

    monkeypatch.setattr(main, "completion", fail)
    pid = project(client)
    resp = client.post(
        "/api/chat",
        json={"project_id": pid, "prompt": "A lost scene", "provider": "demo"},
    )
    assert resp.status_code == 502
    cid = resp.json()["detail"]["conversation_id"]
    messages = client.get("/api/conversations/" + cid).json()["messages"]
    assert len(messages) == 1 and messages[0]["content"] == "A lost scene"


def test_widget_values_reach_the_model(client, monkeypatch):
    from app import main

    captured = {}

    async def pretend(provider, messages):
        captured["messages"] = messages
        return "The opening passage."

    monkeypatch.setattr(main, "completion", pretend)
    pid = project(client)
    doc = client.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": "chapter",
            "title": "First chapter",
            "body": "The court has fallen silent.",
        },
    ).json()
    res = client.post(
        "/api/chat",
        json={
            "project_id": pid,
            "prompt": "Start a new chapter",
            "provider": "demo",
            "context_ids": [doc["id"]],
            "options": {"tone": "Atmospheric", "point_of_view": "Third person limited"},
        },
    )
    assert res.status_code == 200
    system = captured["messages"][0]["content"]
    assert "Atmospheric" in system and "Third person limited" in system
    assert "The court has fallen silent." in system
    assert captured["messages"][-1]["content"] == "Start a new chapter"


def test_arc_adapter_request_format(monkeypatch):
    from app import providers

    monkeypatch.setenv("ARC_CHAT_URL", "http://127.0.0.1:1/v1/chat/completions")
    monkeypatch.setenv("ARC_MODEL_ID", "arc-local-model")
    received = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Arc text response"}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            received.update({"url": url, "payload": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    answer = run_async(
        providers.completion("arc", [{"role": "user", "content": "Write a scene"}])
    )
    assert answer == "Arc text response"
    assert received["payload"]["model"] == "arc-local-model"
    assert received["payload"]["messages"][0]["role"] == "user"
    assert received["url"].endswith("/v1/chat/completions")


def test_provider_error_without_bedrock_config(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    with pytest.raises(providers.ProviderError):
        run_async(providers.completion("bedrock", [{"role": "user", "content": "hi"}]))


def test_rename_and_guarded_delete(client):
    first = client.get("/api/bootstrap").json()["projects"][0]
    assert (
        client.delete(
            f"/api/projects/{first['id']}", params={"confirm_name": first["name"]}
        ).status_code
        == 400
    )  # last project
    second = client.post("/api/projects", json={"name": "Scratch"}).json()
    doc = client.post(
        "/api/documents",
        json={"project_id": second["id"], "type": "note", "title": "n", "body": "b"},
    ).json()
    client.post(
        "/api/chat",
        json={"project_id": second["id"], "prompt": "hello", "provider": "demo"},
    )
    assert (
        client.patch(f"/api/projects/{second['id']}", json={"name": "Renamed"}).json()[
            "name"
        ]
        == "Renamed"
    )
    assert (
        client.delete(
            f"/api/projects/{second['id']}", params={"confirm_name": "wrong"}
        ).status_code
        == 400
    )
    res = client.delete(
        f"/api/projects/{second['id']}", params={"confirm_name": "Renamed"}
    )
    assert (
        res.status_code == 200
        and res.json()["documents"] == 1
        and res.json()["conversations"] == 1
    )
    assert client.get("/api/documents/" + doc["id"]).status_code == 404
    assert [p["id"] for p in client.get("/api/bootstrap").json()["projects"]] == [
        first["id"]
    ]
