"""Tags and metadata on documents: storage migration, API round-trip, filtering and cleanup."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "tags.sqlite3"))
    with TestClient(app) as cli:
        yield cli


def project(cli):
    return cli.get("/api/bootstrap").json()["projects"][0]["id"]


def make(cli, pid, title, tags=None, metadata=None, type_="character"):
    return cli.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": type_,
            "title": title,
            "body": "b",
            "tags": tags or [],
            "metadata": metadata or {},
        },
    ).json()


def test_migration_is_idempotent_and_additive(tmp_path):
    db = str(tmp_path / "m.sqlite3")
    storage.setup(db)
    storage.setup(db)  # second run must not fail or duplicate columns
    with storage.connect() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(documents)")}
    assert {"tags", "metadata"}.issubset(cols)


def test_tags_and_metadata_round_trip(client):
    pid = project(client)
    meta = {"status": "MIXED", "source_confidence": "AUTHOR-STATED", "canon": False}
    doc = make(client, pid, "Protagonist", ["hero", "lead", "age-12"], meta)
    assert json.loads(doc["tags"]) == ["hero", "lead", "age-12"]
    assert json.loads(doc["metadata"]) == meta
    fetched = client.get("/api/documents/" + doc["id"]).json()
    assert json.loads(fetched["metadata"])["source_confidence"] == "AUTHOR-STATED"


def test_tags_are_normalized(client):
    pid = project(client)
    doc = make(client, pid, "Protagonist", ["Hero", " HERO ", "Lead", "", "lead"])
    assert json.loads(doc["tags"]) == ["hero", "lead"]


def test_patch_updates_tags_and_metadata_without_touching_body(client):
    pid = project(client)
    doc = make(client, pid, "Protagonist", ["hero"], {"canon": False})
    client.patch(
        "/api/documents/" + doc["id"],
        json={
            "tags": ["hero", "allies"],
            "metadata": {"canon": True, "status": "RATIFIED"},
        },
    )
    after = client.get("/api/documents/" + doc["id"]).json()
    assert json.loads(after["tags"]) == ["hero", "allies"]
    assert json.loads(after["metadata"]) == {"canon": True, "status": "RATIFIED"}
    assert after["body"] == "b"


def test_filter_by_tag_any_and_all(client):
    pid = project(client)
    make(client, pid, "A", ["hero", "allies"])
    make(client, pid, "B", ["hero", "faith"])
    make(client, pid, "C", ["setting"])
    any_hero = client.get(
        f"/api/projects/{pid}/documents", params={"tags": "hero"}
    ).json()["documents"]
    assert {d["title"] for d in any_hero} == {"A", "B"}
    both = client.get(
        f"/api/projects/{pid}/documents", params={"tags": "hero,allies", "match": "all"}
    ).json()["documents"]
    assert {d["title"] for d in both} == {"A"}
    union = client.get(
        f"/api/projects/{pid}/documents",
        params={"tags": "allies,setting", "match": "any"},
    ).json()["documents"]
    assert {d["title"] for d in union} == {"A", "C"}


def test_project_tag_counts(client):
    pid = project(client)
    make(client, pid, "A", ["hero", "allies"])
    make(client, pid, "B", ["hero"])
    tags = {
        t["tag"]: t["count"]
        for t in client.get(f"/api/projects/{pid}/tags").json()["tags"]
    }
    # The project also carries the seeded reference template's tags; assert only the ones we added.
    assert tags["hero"] == 2 and tags["allies"] == 1


def test_tags_are_scoped_to_their_project(client):
    p1 = project(client)
    p2 = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    make(client, p1, "A", ["hero"])
    make(client, p2, "B", ["hero"])
    assert (
        len(
            client.get(f"/api/projects/{p1}/documents", params={"tags": "hero"}).json()[
                "documents"
            ]
        )
        == 1
    )


def test_deleting_a_project_removes_its_tag_rows(client):
    project(client)
    p2 = client.post("/api/projects", json={"name": "Scratch"}).json()["id"]
    doc = make(client, p2, "A", ["hero", "allies"])
    client.delete(f"/api/projects/{p2}", params={"confirm_name": "Scratch"})
    with storage.connect() as con:
        # No tag rows should remain for any document that belonged to the deleted project.
        leftover = con.execute(
            "SELECT COUNT(*) AS n FROM document_tags WHERE document_id=?", (doc["id"],)
        ).fetchone()["n"]
    assert leftover == 0


def test_existing_documents_without_tags_still_work(client):
    pid = project(client)
    doc = client.post(
        "/api/documents",
        json={"project_id": pid, "type": "note", "title": "Plain", "body": "x"},
    ).json()
    assert json.loads(doc["tags"]) == [] and json.loads(doc["metadata"]) == {}


def test_export_includes_tags_and_metadata(client):
    pid = project(client)
    make(client, pid, "Protagonist", ["hero"], {"canon": False})
    data = client.get(f"/api/projects/{pid}/export").json()
    doc = data["documents"][0]
    assert json.loads(doc["tags"]) == ["hero"]
    assert "metadata" in doc
