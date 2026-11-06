#!/usr/bin/env python3
"""User-guide screenshot tool.

  shots.py list [--state S] [--page P]    every shot with its state
  shots.py todo [--page P] [--json]       what still needs authoring or capturing, with instructions
  shots.py show SLUG                      one shot in full
  shots.py check                          manifest and pages agree (exit 1 on errors; --strict fails on placeholders)
  shots.py capture [SLUG...|--all]        capture ready/stale shots (--force to redo captured ones)
  shots.py sync                           rewrite page blocks so they match what is captured
  shots.py new SLUG --page P --step "..." add a stub to the manifest and its marker to the page

States: stub (not authored) -> pending (authored, not captured) -> captured -> stale (spec changed since capture)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import manifest as mf

ICON = {"stub": "·", "pending": "○", "captured": "●", "stale": "◐"}


def _load():
    m = mf.load()
    return m, {s["slug"]: s for s in m["shots"]}, mf.load_index()


def _states(m, index):
    return {s["slug"]: mf.state(s, index) for s in m["shots"]}


def cmd_list(args) -> int:
    m, _, index = _load()
    st = _states(m, index)
    rows = [
        s
        for s in m["shots"]
        if (not args.page or s["page"] == args.page)
        and (not args.state or st[s["slug"]] == args.state)
    ]
    for s in rows:
        print(
            f"{ICON[st[s['slug']]]} {st[s['slug']]:9} {s['slug']:36} {s['page']}  step: {s['step']}"
        )
    counts = {k: sum(1 for v in st.values() if v == k) for k in ICON}
    print(
        f"\n{len(m['shots'])} shots: "
        + ", ".join(f"{n} {k}" for k, n in counts.items() if n)
    )
    return 0


def todo_item(s: dict, st: str) -> dict:
    out = {
        "slug": s["slug"],
        "state": st,
        "page": s["page"],
        "step": s["step"],
        "intent": s["intent"],
        "caption": s["caption"],
    }
    if s.get("try"):
        out["try"] = s["try"]
    if s.get("notes"):
        out["notes"] = s["notes"]
    return out


def cmd_todo(args) -> int:
    m, _, index = _load()
    st = _states(m, index)
    items = [
        todo_item(s, st[s["slug"]])
        for s in m["shots"]
        if st[s["slug"]] != "captured" and (not args.page or s["page"] == args.page)
    ]
    if args.json:
        print(json.dumps(items, indent=2))
        return 0
    if not items:
        print("Nothing to do: every shot is captured and current.")
        return 0
    groups = {
        "stub": "AUTHOR  (fill in seed + actions, set status to 'ready')",
        "pending": "CAPTURE  (authored, run: shots.py capture)",
        "stale": "RECAPTURE  (the spec changed after the last capture)",
    }
    for key, title in groups.items():
        part = [i for i in items if i["state"] == key]
        if not part:
            continue
        print(f"\n== {title} — {len(part)}")
        for i in part:
            print(f"\n  {i['slug']}   [{i['page']}]")
            print(f"    step:    {i['step']}")
            print(f"    intent:  {i['intent']}")
            if key == "stub":
                print(f"    caption: {i['caption']}")
                if i.get("try"):
                    print(f"    try:     {i['try']}")
            if i.get("notes"):
                print(f"    notes:   {i['notes']}")
    print(f"\n{len(items)} open. Authoring guide: docs/user-guide/AUTHORING.md")
    return 0


def cmd_show(args) -> int:
    _, by, index = _load()
    if args.slug not in by:
        print(f"unknown slug '{args.slug}'. Try: shots.py list", file=sys.stderr)
        return 2
    s = by[args.slug]
    print(json.dumps(s, indent=2, ensure_ascii=False))
    print(f"\nstate: {mf.state(s, index)}   spec hash: {mf.spec_hash(s)}")
    return 0


def cmd_check(args) -> int:
    m = mf.load()
    errors, warnings = mf.validate(m, mf.read_pages())
    for w in warnings:
        print(f"warn  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors or (args.strict and warnings):
        print(
            f"\n{len(errors)} error(s)"
            + (f", {len(warnings)} unresolved placeholder(s)" if args.strict else "")
        )
        return 1
    print(
        f"ok: {len(m['shots'])} shots, {len(mf.read_pages())} pages"
        + (f", {len(warnings)} placeholder warning(s)" if warnings else "")
    )
    return 0


def cmd_sync(_args) -> int:
    _, by, index = _load()
    changed = []
    for name, text in mf.read_pages().items():
        new = mf.sync_text(text, by, index)
        if new != text:
            (mf.GUIDE / name).write_text(new, encoding="utf-8")
            changed.append(name)
    print("updated: " + ", ".join(changed) if changed else "pages already in sync")
    return 0


def cmd_capture(args) -> int:
    m, by, index = _load()
    errors, _ = mf.validate(m, mf.read_pages())
    if errors:
        print(
            "Fix these first (shots.py check):\n  " + "\n  ".join(errors),
            file=sys.stderr,
        )
        return 1
    st = _states(m, index)
    if args.slugs:
        unknown = [s for s in args.slugs if s not in by]
        if unknown:
            print(f"unknown slug(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        chosen = [by[s] for s in args.slugs]
        stubs = [s["slug"] for s in chosen if st[s["slug"]] == "stub"]
        if stubs:
            print(
                f"cannot capture stubs (author them first): {', '.join(stubs)}",
                file=sys.stderr,
            )
            return 2
    else:
        chosen = [
            s
            for s in m["shots"]
            if st[s["slug"]]
            in (
                ("pending", "stale", "captured") if args.force else ("pending", "stale")
            )
        ]
    chosen = [
        s for s in chosen if args.force or st[s["slug"]] != "captured" or args.slugs
    ]
    if not chosen:
        print("nothing to capture (no ready shots are pending or stale)")
        return 0
    from . import capture

    results = capture.capture_all(chosen, mf.SHOTS, index)
    mf.SHOTS.mkdir(parents=True, exist_ok=True)
    (mf.SHOTS / ".index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for slug, err in results.items():
        print(
            f"{'ok  ' if not err else 'FAIL'} {slug}" + (f"\n     {err}" if err else "")
        )
    cmd_sync(args)
    return 1 if any(results.values()) else 0


def cmd_new(args) -> int:
    m = mf.load()
    if any(s["slug"] == args.slug for s in m["shots"]):
        print(f"slug '{args.slug}' already exists", file=sys.stderr)
        return 2
    if not mf.SLUG.match(args.slug):
        print("slug must be lowercase words joined by hyphens", file=sys.stderr)
        return 2
    page = mf.GUIDE / args.page
    if not page.exists():
        print(f"page '{args.page}' does not exist", file=sys.stderr)
        return 2
    m["shots"].append(
        {
            "slug": args.slug,
            "page": args.page,
            "step": args.step,
            "status": "stub",
            "caption": args.caption or f"TODO caption for {args.slug}",
            "intent": args.intent or "TODO: what should this shot prove?",
            "actions": [],
        }
    )
    mf.MANIFEST.write_text(
        json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    block = mf.render_block(m["shots"][-1], "stub")
    with page.open("a", encoding="utf-8") as f:
        f.write(f"\n{block}\n")
    print(
        f"added stub '{args.slug}' to the manifest and appended its marker to {args.page}"
    )
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--state", choices=list(ICON))
    a.add_argument("--page")
    a.set_defaults(fn=cmd_list)
    a = sub.add_parser("todo")
    a.add_argument("--page")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_todo)
    a = sub.add_parser("show")
    a.add_argument("slug")
    a.set_defaults(fn=cmd_show)
    a = sub.add_parser("check")
    a.add_argument("--strict", action="store_true")
    a.set_defaults(fn=cmd_check)
    a = sub.add_parser("sync")
    a.set_defaults(fn=cmd_sync)
    a = sub.add_parser("capture")
    a.add_argument("slugs", nargs="*")
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_capture)
    a = sub.add_parser("new")
    a.add_argument("slug")
    a.add_argument("--page", required=True)
    a.add_argument("--step", required=True)
    a.add_argument("--caption")
    a.add_argument("--intent")
    a.set_defaults(fn=cmd_new)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
