"""Real-browser-to-real-backend harness: a fresh server and SQLite file per test, loopback only, no mocks."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from .pages import NexusPage

ROOT = Path(__file__).resolve().parents[2]
ARC_SECRET = "sk-e2e-not-a-real-key-7f3a9c"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def run_server(tmp_path, extra_env=None):
    port = _free_port()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ARC_", "BEDROCK_", "AWS_"))
    }
    env["NEXUS_DB"] = str(tmp_path / "e2e.sqlite3")
    # The command/document e2e tests assert on otherwise-empty projects; template seeding is
    # covered separately in tests/test_templates.py.
    env["NEXUS_NO_SEED"] = "1"
    env.update(extra_env or {})
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                if httpx.get(url + "/api/bootstrap", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("E2E server did not become ready")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def server_url(tmp_path):
    """Demo-only server (no Arc or Bedrock configured)."""
    with run_server(tmp_path) as url:
        yield url


@pytest.fixture
def server_url_arc_down(tmp_path):
    """Arc is 'configured' but nothing listens on the port: a real connection failure, not a mock."""
    env = {
        "ARC_CHAT_URL": "http://127.0.0.1:9/v1/chat/completions",
        "ARC_MODEL_ID": "e2e-unreachable",
        "ARC_API_KEY": ARC_SECRET,
    }
    with run_server(tmp_path, env) as url:
        yield url


@pytest.fixture
def api(server_url):
    with httpx.Client(base_url=server_url, timeout=10) as client:
        yield client


@pytest.fixture
def api_arc_down(server_url_arc_down):
    with httpx.Client(base_url=server_url_arc_down, timeout=10) as client:
        yield client


@pytest.fixture
def pid(api):
    return api.get("/api/bootstrap").json()["projects"][0]["id"]


@pytest.fixture
def nx(page, server_url):
    n = NexusPage(page, server_url)
    n.open()
    return n


@pytest.fixture
def nx_arc_down(page, server_url_arc_down):
    n = NexusPage(page, server_url_arc_down)
    n.open()
    return n


@pytest.fixture
def make_doc(api, pid):
    def make(
        type_="chapter",
        title="Chapter 5",
        body="The hall fell silent. The envoy waited.",
        project_id=None,
    ):
        res = api.post(
            "/api/documents",
            json={
                "project_id": project_id or pid,
                "type": type_,
                "title": title,
                "body": body,
            },
        )
        assert res.status_code == 201, res.text
        return res.json()

    return make


def documents(api, project_id):
    return api.get(f"/api/projects/{project_id}/overview").json()["documents"]


def document(api, doc_id):
    return api.get(f"/api/documents/{doc_id}").json()


def conversations(api, project_id):
    return api.get(f"/api/projects/{project_id}/overview").json()["conversations"]


def messages(api, conversation_id):
    return api.get(f"/api/conversations/{conversation_id}").json()["messages"]


@pytest.fixture(autouse=True)
def _fast_failure_for_planned(request, page):
    """Planned specs must fail quickly (strict xfail) instead of waiting out the default timeouts."""
    if request.node.get_closest_marker("planned") or request.node.get_closest_marker(
        "known_bug"
    ):
        page.set_default_timeout(1000)
        expect.set_options(timeout=1000)
        yield
        expect.set_options(timeout=5000)
    else:
        yield
