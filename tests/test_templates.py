"""Reference templates are seeded into every project and marked as guidance, not canon."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "tpl.sqlite3"))
    with TestClient(app) as cli:
        yield cli


def docs(client, pid):
    return client.get(f"/api/projects/{pid}/overview").json()["documents"]


def test_first_run_project_has_the_character_template(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]
    titles = [d["title"] for d in docs(client, pid)]
    assert "Character profile - how to fill this in" in titles


def test_template_is_marked_as_reference_not_canon(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]
    tpl = next(
        d for d in docs(client, pid) if d["title"].startswith("Character profile")
    )
    meta = json.loads(tpl["metadata"])
    assert (
        meta["template"] is True
        and meta["canon"] is False
        and meta["status"] == "REFERENCE"
    )
    assert set(json.loads(tpl["tags"])) == {"reference", "template", "character"}


def test_template_body_has_the_guidance_sections(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]
    tpl = next(
        d for d in docs(client, pid) if d["title"].startswith("Character profile")
    )
    body = client.get("/api/documents/" + tpl["id"]).json()["body"]
    for heading in (
        "Identity",
        "Want versus need",
        "Wound, lie, and fear",
        "Open questions and status",
    ):
        assert heading in body
    assert "OPEN" in body  # the uncertainty rule is stated


def test_new_projects_also_get_the_template(client):
    pid = client.post("/api/projects", json={"name": "Second"}).json()["id"]
    assert any(d["title"].startswith("Character profile") for d in docs(client, pid))


def test_seeding_is_idempotent(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]
    before = len(docs(client, pid))
    assert storage.seed_reference_docs(pid) == 0
    assert len(docs(client, pid)) == before


def test_deleting_a_project_removes_its_templates(client):
    pid = client.post("/api/projects", json={"name": "Scratch"}).json()["id"]
    assert (
        client.delete(
            f"/api/projects/{pid}", params={"confirm_name": "Scratch"}
        ).status_code
        == 200
    )
