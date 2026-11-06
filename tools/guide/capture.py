"""Capture user-guide screenshots from the real app: real Chromium, real FastAPI, throwaway SQLite.

One fresh server and database per shot, so seeds never leak between shots. Nothing is mocked. Playwright is
imported lazily so the rest of the tooling works without it.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import subprocess  # nosec B404 - starts our own uvicorn with a fixed argv, shell=False
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from . import manifest as mf

ROOT = mf.ROOT
PRIMARY = "My first project"
ARC_DEAD = {
    "ARC_CHAT_URL": "http://127.0.0.1:9/v1/chat/completions",
    "ARC_MODEL_ID": "guide-unreachable",
}
FREEZE_CSS = (
    "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"
    "html{scrollbar-width:none}::-webkit-scrollbar{display:none}"
)
HIGHLIGHT_JS = """(sels) => sels.forEach(s => document.querySelectorAll(s).forEach(e => {
    e.style.outline = '3px solid #d9480f'; e.style.outlineOffset = '3px'; }))"""
IDLE_JS = "() => !document.querySelector('#sendBtn').hasAttribute('aria-busy')"


class CaptureError(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def server(shot: dict):
    port = _free_port()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("ARC_", "BEDROCK_", "AWS_"))
    }
    with tempfile.TemporaryDirectory(prefix="guide-shot-") as tmp:
        env["NEXUS_DB"] = str(Path(tmp) / "guide.sqlite3")
        if shot.get("env", {}).get("arc_down"):
            env.update(ARC_DEAD)
        proc = subprocess.Popen(  # nosec B603 - fixed argv, loopback only, no user input
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
                raise CaptureError("the app did not start")
            yield url
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def seed(url: str, spec: dict | None) -> bool:
    """Create the shot's data through the real API. Returns True when extra projects exist."""
    spec = spec or {}
    with httpx.Client(base_url=url, timeout=15) as api:
        projects = api.get("/api/bootstrap").json()["projects"]
        pid = next(p["id"] for p in projects if p["name"] == PRIMARY)
        for d in spec.get("documents", []):
            r = api.post("/api/documents", json={"project_id": pid, "body": "", **d})
            r.raise_for_status()
        for c in spec.get("conversations", []):
            api.post(
                "/api/chat", json={"project_id": pid, "provider": "demo", **c}
            ).raise_for_status()
        for name in spec.get("extra_projects", []):
            api.post("/api/projects", json={"name": name}).raise_for_status()
    return bool(spec.get("extra_projects"))


def _prompt(page):
    return page.get_by_role("combobox", name=re.compile("Write a prompt"))


def _idle(page):
    page.wait_for_function(IDLE_JS)


def _do(page, a: dict) -> None:
    kind = a["do"]
    if kind == "type":
        _prompt(page).fill(a["text"])
    elif kind == "send":
        _prompt(page).press("Control+Enter")
        _idle(page)
    elif kind == "send_no_wait":
        _prompt(page).press("Control+Enter")
    elif kind == "run":
        _prompt(page).fill(a["text"])
        _prompt(page).press("Control+Enter")
        _idle(page)
    elif kind == "ask":
        before = page.locator(".message-ai").count()
        _prompt(page).fill(a["text"])
        _prompt(page).press("Control+Enter")
        page.wait_for_function(
            f"document.querySelectorAll('.message-ai').length > {before}"
        )
        _idle(page)
    elif kind == "press":
        page.keyboard.press(a["key"])
    elif kind == "click":
        if a.get("selector"):
            page.locator(a["selector"]).first.click()
        elif a.get("text"):
            page.get_by_text(a["text"]).first.click()
        else:
            page.get_by_role(a["role"], name=a["name"]).first.click()
    elif kind == "select":
        pane = page.get_by_role("complementary", name="Contextual tools")
        pane.get_by_label(a["label"], exact=True).select_option(label=a["option"])
    elif kind == "search":
        page.keyboard.press("Control+k")
        page.get_by_role("dialog", name="Search archive").get_by_role("searchbox").fill(
            a["query"]
        )
    elif kind == "wait":
        page.wait_for_timeout(a["ms"])
    elif kind == "wait_visible":
        page.locator(a["selector"]).first.wait_for(state="visible")


def capture_one(browser, shot: dict, out_dir: Path) -> Path:
    vp = shot.get("viewport") or mf.DEFAULT_VIEWPORT
    with server(shot) as url:
        extras = seed(url, shot.get("seed"))
        ctx = browser.new_context(
            viewport=vp,
            device_scale_factor=1,
            reduced_motion="reduce",
            color_scheme="light",
            locale="en-US",
            timezone_id="UTC",
        )
        page = ctx.new_page()
        page.set_default_timeout(8000)
        held = []
        if shot.get("hold_chat"):
            # Hold the real /api/chat request open (do not answer it) so the app stays in its busy
            # state while the shot is taken. The request is aborted deliberately at teardown, which
            # is what a user cancelling or closing the tab would do. Nothing is mocked or answered.
            page.route("**/api/chat", lambda route: held.append(route))
        try:
            page.goto(url)
            page.wait_for_selector("body[data-ready=true]", state="attached")
            page.add_style_tag(content=FREEZE_CSS)
            if extras:  # boot picks a project by creation time; start every shot in the primary project
                _prompt(page).fill(f"/project switch {PRIMARY}")
                _prompt(page).press("Control+Enter")
                _idle(page)
                page.wait_for_selector("#toast[hidden]", state="attached", timeout=6000)
            for i, action in enumerate(shot.get("actions", [])):
                try:
                    _do(page, action)
                except Exception as exc:
                    raise CaptureError(
                        f"action {i} {action}: {str(exc).splitlines()[0]}"
                    ) from exc
            hl = shot.get("highlight")
            if hl:
                page.evaluate(HIGHLIGHT_JS, [hl] if isinstance(hl, str) else hl)
            page.wait_for_timeout(shot.get("settle_ms", 250))
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{shot['slug']}.png"
            if shot.get("target"):
                page.locator(shot["target"]).first.screenshot(path=str(path))
            else:
                page.screenshot(path=str(path), full_page=False)
            return path
        finally:
            for route in held:
                with contextlib.suppress(
                    Exception
                ):  # teardown: the page may already be gone
                    route.abort()
            ctx.close()


def capture_all(shots: list[dict], out_dir: Path, index: dict) -> dict[str, str]:
    """Capture each shot. Returns slug -> '' on success or an error message. Updates `index` in place."""
    from playwright.sync_api import sync_playwright

    results: dict[str, str] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for shot in shots:
                try:
                    capture_one(browser, shot, out_dir)
                    index[shot["slug"]] = mf.spec_hash(shot)
                    results[shot["slug"]] = ""
                except Exception as exc:  # noqa: BLE001 - report every failure per shot and keep going
                    results[shot["slug"]] = (
                        str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                    )
        finally:
            browser.close()
    return results
