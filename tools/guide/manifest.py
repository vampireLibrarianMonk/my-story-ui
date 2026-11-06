"""Screenshot manifest for the user guide: load, validate, hash and keep doc markers in sync.

Pure standard library so it runs anywhere. Playwright is only needed by shots.py when capturing.

Model
  * docs/user-guide/shots.json   one entry per screenshot (the source of truth)
  * docs/user-guide/*.md         pages carry  <!-- shot:SLUG --> ... <!-- /shot -->  markers
  * docs/assets/shots/SLUG.png   captured images, plus .index.json recording the spec hash of each capture

A shot is a "stub" until someone authors its actions and flips status to "ready".
Prose fields (title, caption, intent, try, notes) never affect the capture hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "user-guide"
MANIFEST = GUIDE / "shots.json"
SHOTS = ROOT / "docs" / "assets" / "shots"

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKER = re.compile(
    r"<!-- shot:(?P<slug>[^ >]+) -->(?P<body>.*?)<!-- /shot -->", re.DOTALL
)
TODO_EXAMPLE = "TODO(example)"
NOT_PAGES = {"AUTHORING.md"}  # tooling docs: no markers, no placeholders
STATUSES = ("stub", "ready")
DOC_TYPES = ("chapter", "character", "world", "research", "note")
CAPTURE_KEYS = (
    "seed",
    "env",
    "viewport",
    "actions",
    "target",
    "highlight",
    "settle_ms",
)
# Hashed only when a shot sets them, so adding an option never invalidates existing captures.
OPTIONAL_CAPTURE_KEYS = ("hold_chat",)
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}

# action -> (required keys, optional keys)
ACTIONS: dict[str, tuple[set[str], set[str]]] = {
    "type": ({"text"}, set()),  # put text in the prompt, do not send
    "send": (set(), set()),  # Ctrl+Enter, then wait until the app is idle
    "send_no_wait": (
        set(),
        set(),
    ),  # Ctrl+Enter and return at once, to capture the busy state
    "run": ({"text"}, set()),  # type + send (commands)
    "ask": ({"text"}, set()),  # type + send + wait for one more reply (chat)
    "press": ({"key"}, set()),
    "click": (set(), {"role", "name", "selector", "text"}),
    "select": ({"label", "option"}, set()),  # a widget in the context pane
    "search": ({"query"}, set()),  # Ctrl+K and type a query
    "wait": ({"ms"}, set()),
    "wait_visible": ({"selector"}, set()),
}


def load(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def spec_hash(shot: dict) -> str:
    """Hash of everything that changes the pixels. Prose is excluded on purpose."""
    spec = {k: shot.get(k) for k in CAPTURE_KEYS}
    spec.update({k: shot[k] for k in OPTIONAL_CAPTURE_KEYS if shot.get(k)})
    spec["viewport"] = spec["viewport"] or DEFAULT_VIEWPORT
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_index(shots_dir: Path = SHOTS) -> dict:
    f = shots_dir / ".index.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def state(shot: dict, index: dict, shots_dir: Path = SHOTS) -> str:
    """stub | pending (ready, never captured) | stale (spec changed since capture) | captured"""
    if shot.get("status") != "ready":
        return "stub"
    if not (shots_dir / f"{shot['slug']}.png").exists():
        return "pending"
    return "captured" if index.get(shot["slug"]) == spec_hash(shot) else "stale"


def validate_action(a: object, where: str) -> list[str]:
    if not isinstance(a, dict) or a.get("do") not in ACTIONS:
        return [f"{where}: unknown action {a!r}; allowed: {sorted(ACTIONS)}"]
    required, optional = ACTIONS[a["do"]]
    keys = set(a) - {"do"}
    errs = []
    if required - keys:
        errs.append(f"{where}: '{a['do']}' needs {sorted(required - keys)}")
    if keys - required - optional:
        errs.append(
            f"{where}: '{a['do']}' has unexpected keys {sorted(keys - required - optional)}"
        )
    if a["do"] == "click":
        forms = [
            bool(a.get("selector")),
            bool(a.get("text")),
            bool(a.get("role") and a.get("name")),
        ]
        if sum(forms) != 1:
            errs.append(
                f"{where}: click needs exactly one of selector | text | role+name"
            )
    if a["do"] == "wait" and not (
        isinstance(a.get("ms"), int) and 0 <= a["ms"] <= 2000
    ):
        errs.append(
            f"{where}: wait.ms must be an integer 0..2000 (waits hide real timing bugs)"
        )
    return errs


def validate_seed(seed: object, where: str) -> list[str]:
    if seed is None:
        return []
    if not isinstance(seed, dict) or set(seed) - {
        "documents",
        "conversations",
        "extra_projects",
    }:
        return [f"{where}: seed keys must be documents, conversations, extra_projects"]
    errs = []
    for i, d in enumerate(seed.get("documents", [])):
        if d.get("type") not in DOC_TYPES or not d.get("title"):
            errs.append(
                f"{where}: seed.documents[{i}] needs type in {DOC_TYPES} and a title"
            )
    for i, c in enumerate(seed.get("conversations", [])):
        if not c.get("prompt"):
            errs.append(f"{where}: seed.conversations[{i}] needs a prompt")
    if not all(isinstance(n, str) and n for n in seed.get("extra_projects", [])):
        errs.append(f"{where}: seed.extra_projects must be non-empty strings")
    return errs


def validate_shot(shot: dict) -> list[str]:
    slug = shot.get("slug", "<missing slug>")
    where = f"shot '{slug}'"
    errs = []
    if not SLUG.match(str(shot.get("slug", ""))):
        errs.append(f"{where}: slug must be lowercase words joined by hyphens")
    for k in ("page", "step", "caption", "intent"):
        if not str(shot.get(k, "")).strip():
            errs.append(
                f"{where}: '{k}' is required (caption doubles as the image alt text)"
            )
    if shot.get("status") not in STATUSES:
        errs.append(f"{where}: status must be one of {STATUSES}")
    if not isinstance(shot.get("actions", []), list):
        errs.append(f"{where}: actions must be a list")
    else:
        for i, a in enumerate(shot.get("actions", [])):
            errs += validate_action(a, f"{where} actions[{i}]")
    errs += validate_seed(shot.get("seed"), where)
    if set(shot.get("env", {})) - {"arc_down"}:
        errs.append(f"{where}: env only supports arc_down")
    if "target" in shot and not (
        isinstance(shot["target"], str) and shot["target"].strip()
    ):
        errs.append(f"{where}: target must be a CSS selector string")
    hl = shot.get("highlight")
    if hl is not None and not (
        isinstance(hl, str)
        or (isinstance(hl, list) and all(isinstance(x, str) for x in hl))
    ):
        errs.append(f"{where}: highlight must be a CSS selector or a list of them")
    settle = shot.get("settle_ms")
    if settle is not None and not (isinstance(settle, int) and 0 <= settle <= 2000):
        errs.append(f"{where}: settle_ms must be an integer 0..2000")
    if "hold_chat" in shot and shot["hold_chat"] is not True:
        errs.append(f"{where}: hold_chat must be true (or omitted)")
    vp = shot.get("viewport")
    if vp is not None and not (isinstance(vp, dict) and {"width", "height"} == set(vp)):
        errs.append(f"{where}: viewport needs width and height")
    return errs


def read_pages(guide: Path = GUIDE) -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(guide.glob("*.md"))
        if p.name not in NOT_PAGES
    }


def validate(manifest: dict, pages: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors mean the guide and manifest disagree."""
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("manifest: schema_version must be 1")
    shots = manifest.get("shots", [])
    seen: set[str] = set()
    for s in shots:
        errors += validate_shot(s)
        if s.get("slug") in seen:
            errors.append(f"shot '{s.get('slug')}': duplicate slug")
        seen.add(s.get("slug"))
        if s.get("page") and s["page"] not in pages:
            errors.append(f"shot '{s.get('slug')}': page '{s['page']}' does not exist")
    placed: dict[str, str] = {}
    for name, text in pages.items():
        for m in MARKER.finditer(text):
            slug = m["slug"]
            if slug in placed:
                errors.append(
                    f"marker '{slug}' appears twice ({placed[slug]} and {name})"
                )
            placed[slug] = name
            if slug not in seen:
                errors.append(f"{name}: marker '{slug}' has no manifest entry")
    for s in shots:
        slug = s.get("slug")
        if slug not in placed:
            errors.append(
                f"shot '{slug}': no marker in any page (add <!-- shot:{slug} --><!-- /shot -->)"
            )
        elif placed[slug] != s.get("page"):
            errors.append(
                f"shot '{slug}': declared on {s.get('page')} but placed in {placed[slug]}"
            )
    for name, text in pages.items():
        n = text.count(TODO_EXAMPLE)
        if n:
            warnings.append(f"{name}: {n} {TODO_EXAMPLE} placeholder(s) still to write")
    return errors, warnings


def rel_assets(guide: Path, shots_dir: Path) -> str:
    return Path(os.path.relpath(shots_dir, guide)).as_posix()


def render_block(shot: dict, st: str, rel: str = "../assets/shots") -> str:
    slug, cap = shot["slug"], shot["caption"]
    if st == "captured" or st == "stale":
        body = f"![{cap}]({rel}/{slug}.png)\n\n*{cap}*"
    elif st == "pending":
        body = f"> **Screenshot pending capture** `{slug}`: {cap}"
    else:
        body = f"> **Screenshot stub** `{slug}`: {cap}"
    return f"<!-- shot:{slug} -->\n{body}\n<!-- /shot -->"


def sync_text(
    text: str,
    by_slug: dict[str, dict],
    index: dict,
    shots_dir: Path = SHOTS,
    rel: str = "../assets/shots",
) -> str:
    def repl(m: re.Match) -> str:
        shot = by_slug.get(m["slug"])
        return (
            m.group(0)
            if shot is None
            else render_block(shot, state(shot, index, shots_dir), rel)
        )

    return MARKER.sub(repl, text)
