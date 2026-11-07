"""Document reference images: upload, serve, replace, remove, validation, and cleanup."""

from __future__ import annotations

import json
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app


def _png(width=2, height=2) -> bytes:
    """A tiny valid PNG built in-memory (no Pillow dependency)."""

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "img.sqlite3"))
    with TestClient(app) as cli:
        yield cli


@pytest.fixture
def doc(client):
    pid = client.get("/api/bootstrap").json()["projects"][0]["id"]
    return client.post(
        "/api/documents",
        json={"project_id": pid, "type": "character", "title": "Hero", "body": "b"},
    ).json()


def test_upload_serve_and_metadata(client, doc):
    png = _png()
    r = client.put(
        f"/api/documents/{doc['id']}/image",
        content=png,
        headers={"content-type": "image/png"},
    )
    assert r.status_code == 201
    meta = json.loads(r.json()["metadata"])["image"]
    assert meta["ext"] == "png" and meta["bytes"] == len(png)
    g = client.get(f"/api/documents/{doc['id']}/image")
    assert g.status_code == 200 and g.headers["content-type"].startswith("image/png")
    assert g.content == png


def test_missing_image_is_404(client, doc):
    assert client.get(f"/api/documents/{doc['id']}/image").status_code == 404


def test_unsupported_type_is_rejected(client, doc):
    r = client.put(
        f"/api/documents/{doc['id']}/image",
        content=b"%PDF-1.4",
        headers={"content-type": "application/pdf"},
    )
    assert r.status_code == 415
    assert client.get(f"/api/documents/{doc['id']}/image").status_code == 404


def test_empty_body_is_rejected(client, doc):
    r = client.put(
        f"/api/documents/{doc['id']}/image",
        content=b"",
        headers={"content-type": "image/png"},
    )
    assert r.status_code == 400


def test_oversize_image_is_rejected(client, doc, monkeypatch):
    monkeypatch.setattr(storage, "MAX_IMAGE_BYTES", 10)
    r = client.put(
        f"/api/documents/{doc['id']}/image",
        content=_png(8, 8),
        headers={"content-type": "image/png"},
    )
    assert r.status_code == 413


def test_replacing_keeps_exactly_one_file(client, doc):
    client.put(
        f"/api/documents/{doc['id']}/image",
        content=_png(),
        headers={"content-type": "image/png"},
    )
    client.put(
        f"/api/documents/{doc['id']}/image",
        content=_png(),
        headers={"content-type": "image/webp"},
    )
    files = list(storage._images_dir().glob(f"{doc['id']}.*"))
    assert len(files) == 1 and files[0].suffix == ".webp"


def test_remove_clears_file_and_metadata(client, doc):
    client.put(
        f"/api/documents/{doc['id']}/image",
        content=_png(),
        headers={"content-type": "image/png"},
    )
    updated = client.delete(f"/api/documents/{doc['id']}/image").json()
    assert "image" not in json.loads(updated["metadata"])
    assert client.get(f"/api/documents/{doc['id']}/image").status_code == 404
    assert not list(storage._images_dir().glob(f"{doc['id']}.*"))


def test_image_on_missing_document_is_404(client):
    assert (
        client.put(
            "/api/documents/nope/image",
            content=_png(),
            headers={"content-type": "image/png"},
        ).status_code
        == 404
    )
    assert client.delete("/api/documents/nope/image").status_code == 404
