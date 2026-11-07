"""Normalized relationship edges between character documents: CRUD, validation, scale filtering, cleanup."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "rel.sqlite3"))
    monkeypatch.setenv("NEXUS_NO_SEED", "1")
    with TestClient(app) as cli:
        yield cli


@pytest.fixture
def setup(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]

    def doc(title, type_="character"):
        return client.post(
            "/api/documents",
            json={"project_id": pid, "type": type_, "title": title, "body": ""},
        ).json()["id"]

    return pid, doc


def rel(client, pid, a, b, scale, nature, **kw):
    return client.post(
        "/api/relationships",
        json={
            "project_id": pid,
            "from_doc": a,
            "to_doc": b,
            "scale": scale,
            "nature": nature,
            **kw,
        },
    )


def test_create_and_read_relationship(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    r = rel(client, pid, a, b, "personal", "ally")
    assert r.status_code == 201
    body = r.json()
    assert body["from_doc"] == a and body["to_doc"] == b
    assert body["scale"] == "personal" and body["nature"] == "ally"
    assert body["direction"] == "mutual" and body["status"] == "proposed"


def test_same_pair_can_hold_multiple_scales(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    rel(client, pid, a, b, "personal", "ally")
    rel(client, pid, a, b, "organizational", "rival")
    got = client.get(f"/api/projects/{pid}/relationships").json()["relationships"]
    assert {(x["scale"], x["nature"]) for x in got} == {
        ("personal", "ally"),
        ("organizational", "rival"),
    }


def test_directed_authority_relationship(client, setup):
    pid, doc = setup
    a, b = doc("Commander"), doc("Recruit")
    r = rel(
        client,
        pid,
        a,
        b,
        "organizational",
        "authority",
        direction="from_to",
        status="decided",
    ).json()
    assert r["direction"] == "from_to" and r["from_doc"] == a and r["to_doc"] == b


def test_self_relationship_is_rejected(client, setup):
    pid, doc = setup
    a = doc("A")
    assert rel(client, pid, a, a, "personal", "ally").status_code == 400


def test_both_documents_must_be_in_the_project(client, setup):
    pid, doc = setup
    a = doc("A")
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    foreign = client.post(
        "/api/documents",
        json={"project_id": other, "type": "character", "title": "X", "body": ""},
    ).json()["id"]
    assert rel(client, pid, a, foreign, "personal", "ally").status_code == 400


def test_missing_document_is_404(client, setup):
    pid, doc = setup
    a = doc("A")
    assert rel(client, pid, a, "nope", "personal", "ally").status_code == 404


def test_invalid_vocabulary_is_rejected(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    assert rel(client, pid, a, b, "galactic", "ally").status_code == 422
    assert rel(client, pid, a, b, "personal", "frenemy").status_code == 422


def test_filter_by_scale(client, setup):
    pid, doc = setup
    a, b, c = doc("A"), doc("B"), doc("C")
    rel(client, pid, a, b, "personal", "ally")
    rel(client, pid, a, c, "organizational", "authority", direction="from_to")
    org = client.get(
        f"/api/projects/{pid}/relationships", params={"scale": "organizational"}
    ).json()["relationships"]
    assert len(org) == 1 and org[0]["to_doc"] == c


def test_relationships_for_a_document_from_either_end(client, setup):
    pid, doc = setup
    a, b, c = doc("A"), doc("B"), doc("C")
    rel(client, pid, a, b, "personal", "ally")
    rel(client, pid, c, a, "ideological", "rival")
    got = client.get(f"/api/documents/{a}/relationships").json()["relationships"]
    assert len(got) == 2


def test_patch_and_delete(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    rid = rel(client, pid, a, b, "personal", "ally").json()["id"]
    upd = client.patch(
        f"/api/relationships/{rid}", json={"status": "decided", "note": "settled"}
    ).json()
    assert upd["status"] == "decided" and upd["note"] == "settled"
    assert (
        client.patch(f"/api/relationships/{rid}", json={"scale": "bogus"}).status_code
        == 422
    )
    assert client.delete(f"/api/relationships/{rid}").status_code == 200
    assert (
        client.get(f"/api/projects/{pid}/relationships").json()["relationships"] == []
    )


def test_deleting_a_project_removes_its_relationships(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    rel(client, pid, a, b, "personal", "ally")
    p2 = client.post("/api/projects", json={"name": "Scratch"}).json()["id"]
    client.delete(f"/api/projects/{p2}", params={"confirm_name": "Scratch"})
    # the first project's relationship is untouched
    assert (
        len(client.get(f"/api/projects/{pid}/relationships").json()["relationships"])
        == 1
    )


def test_export_is_unaffected_and_relationships_queryable(client, setup):
    pid, doc = setup
    a, b = doc("A"), doc("B")
    rel(client, pid, a, b, "societal", "allegiance")
    assert client.get(f"/api/projects/{pid}/export").status_code == 200
