"""Load the author's private corpus and the task matrix for the evaluation harness.

The corpus lives in dropbox/ (git-ignored). Documents are addressed by a short key taken from the filename,
so tasks reference "00_master" rather than a path. Nothing here writes or mutates the source files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DROPBOX = ROOT / "dropbox"


def _key(path: Path) -> str:
    m = re.match(r"(\d+)_([A-Z]+)", path.stem)
    if m:
        return f"{m.group(1)}_{m.group(2).lower()}"
    return path.stem.lower()


def available_documents() -> dict[str, Path]:
    return {_key(p): p for p in sorted(DROPBOX.glob("*.md"))}


def load_context(keys: list[str]) -> list[dict]:
    """Return storage-shaped documents (type/title/body) for the given corpus keys."""
    docs = available_documents()
    out = []
    for key in keys:
        path = docs.get(key)
        if path is None:
            raise FileNotFoundError(
                f"corpus document '{key}' not found in {DROPBOX}. Available: {sorted(docs)}"
            )
        body = path.read_text(encoding="utf-8")
        title = body.splitlines()[0].lstrip("# ").strip() if body else path.stem
        out.append({"type": "character", "title": title, "body": body})
    return out


def load_tasks(path: str | None = None) -> list[dict]:
    """Task set for the harness. Default lives in dropbox/ (git-ignored) so no story prompts are committed."""
    import os

    path = path or os.environ.get("EVAL_TASKS") or str(DROPBOX / "eval_tasks.json")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"no task file at {p}. Create one (see tools/eval/eval_tasks.example.json) or set EVAL_TASKS."
        )
    return json.loads(p.read_text(encoding="utf-8"))["tasks"]
