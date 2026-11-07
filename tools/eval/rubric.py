"""Deterministic canon-safety checks driven by an external rule file.

The engine here is generic. The actual rules (regex patterns, the facts they protect, hard-count
invariants) live in a project's own rule file so no story content is committed to this repository.
Point it at a JSON rules file with CANON_RULES or --rules; see tools/eval/rules.example.json.

Rule file shape:
  {
    "forbid": [{"id": "...", "pattern": "regex", "message": "...", "severity": "block|warn"}],
    "require_counts": [{"id": "...", "when_any": ["regex", ...], "needs": "regex", "message": "..."}],
    "hedge_pattern": "regex of uncertainty markers (optional)"
  }
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HEDGE = r"\b(unknown|unconfirmed|not established|possibl[ey]|may have|proposed|allegation)\b"


@dataclass
class Finding:
    rule: str
    severity: str  # "block" or "warn"
    detail: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocks(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def ok(self) -> bool:
        return not self.blocks

    def add(self, rule: str, severity: str, detail: str) -> None:
        self.findings.append(Finding(rule, severity, detail))


def load_rules(path: str | None = None) -> dict:
    """Load a rule file. Returns an empty ruleset if none is configured, so the engine still runs."""
    path = path or os.environ.get("CANON_RULES")
    if not path:
        return {"forbid": [], "require_counts": [], "hedge_pattern": DEFAULT_HEDGE}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.setdefault("forbid", [])
    data.setdefault("require_counts", [])
    data.setdefault("hedge_pattern", DEFAULT_HEDGE)
    return data


def check(text: str, rules: dict, *, context_titles: tuple[str, ...] = ()) -> Report:
    r = Report()
    low = text.lower()

    for rule in rules["forbid"]:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            r.add(rule["id"], rule.get("severity", "block"), rule["message"])

    for rule in rules["require_counts"]:
        triggered = any(re.search(p, low) for p in rule["when_any"])
        if triggered and not re.search(rule["needs"], low):
            r.add(rule["id"], "block", rule["message"])

    hedges = len(re.findall(rules["hedge_pattern"], low))
    r.add(
        "hedging",
        "warn",
        f"{hedges} uncertainty marker(s) present."
        if hedges
        else "No uncertainty markers; check nothing OPEN was asserted.",
    )

    if context_titles:
        used = [t for t in context_titles if t and t.lower() in low]
        r.add(
            "context-use",
            "warn",
            f"References {len(used)}/{len(context_titles)} selected document title(s).",
        )
    return r
