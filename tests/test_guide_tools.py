"""Unit tests for the user-guide screenshot manifest: validation, states, sync and hashing."""

from __future__ import annotations

import copy

import pytest

from tools.guide import manifest as mf

SHOT = {
    "slug": "demo-shot",
    "page": "page.md",
    "step": "A step",
    "status": "ready",
    "caption": "A caption.",
    "intent": "Prove a thing.",
    "actions": [{"do": "type", "text": "hello"}],
}
PAGE = "# Page\n\n<!-- shot:demo-shot -->\n> **Screenshot stub** `demo-shot`: A caption.\n<!-- /shot -->\n"


def manifest_with(*shots):
    return {"schema_version": 1, "shots": [copy.deepcopy(s) for s in shots]}


def errors_for(**changes):
    shot = {**copy.deepcopy(SHOT), **changes}
    errs, _ = mf.validate(manifest_with(shot), {"page.md": PAGE})
    return errs


def test_a_valid_manifest_has_no_errors():
    assert errors_for() == []


@pytest.mark.parametrize(
    "slug", ["Bad Slug", "UPPER", "under_score", "-lead", "trail-", ""]
)
def test_bad_slugs_are_rejected(slug):
    assert any("slug" in e for e in errors_for(slug=slug))


@pytest.mark.parametrize("key", ["page", "step", "caption", "intent"])
def test_required_prose_fields(key):
    assert any(f"'{key}' is required" in e for e in errors_for(**{key: " "}))


def test_unknown_action_and_missing_and_extra_keys():
    assert any("unknown action" in e for e in errors_for(actions=[{"do": "teleport"}]))
    assert any("needs ['text']" in e for e in errors_for(actions=[{"do": "type"}]))
    assert any(
        "unexpected keys" in e
        for e in errors_for(actions=[{"do": "send", "text": "x"}])
    )


def test_click_needs_exactly_one_target_form():
    assert any("exactly one" in e for e in errors_for(actions=[{"do": "click"}]))
    assert any(
        "exactly one" in e
        for e in errors_for(actions=[{"do": "click", "text": "a", "selector": "b"}])
    )
    assert (
        errors_for(actions=[{"do": "click", "role": "button", "name": "Close"}]) == []
    )


@pytest.mark.parametrize("ms", [-1, 2001, "5", 1.5])
def test_wait_is_bounded(ms):
    assert any("wait.ms" in e for e in errors_for(actions=[{"do": "wait", "ms": ms}]))


def test_seed_validation():
    assert any(
        "seed.documents[0]" in e
        for e in errors_for(seed={"documents": [{"type": "essay", "title": "x"}]})
    )
    assert any("needs a prompt" in e for e in errors_for(seed={"conversations": [{}]}))
    assert any("seed keys" in e for e in errors_for(seed={"users": []}))
    assert (
        errors_for(
            seed={
                "documents": [{"type": "chapter", "title": "Chapter 5"}],
                "extra_projects": ["A"],
            }
        )
        == []
    )


def test_env_viewport_highlight_target_settle():
    assert any("env only supports" in e for e in errors_for(env={"bedrock_down": True}))
    assert any("viewport" in e for e in errors_for(viewport={"width": 100}))
    assert any("highlight" in e for e in errors_for(highlight=3))
    assert any("target" in e for e in errors_for(target=""))
    assert any("settle_ms" in e for e in errors_for(settle_ms=99999))
    for bad in (False, 0, 1, "true", [True]):
        assert any("hold_chat" in e for e in errors_for(hold_chat=bad))
    assert errors_for(hold_chat=True, actions=[{"do": "send_no_wait"}]) == []


def test_status_must_be_known():
    assert any("status" in e for e in errors_for(status="done"))


def test_manifest_and_pages_must_agree():
    ok = manifest_with(SHOT)
    assert mf.validate(ok, {"page.md": PAGE})[0] == []
    assert any("no marker" in e for e in mf.validate(ok, {"page.md": "# empty"})[0])
    orphan = PAGE + "<!-- shot:ghost -->\n<!-- /shot -->\n"
    assert any(
        "has no manifest entry" in e for e in mf.validate(ok, {"page.md": orphan})[0]
    )
    assert any(
        "appears twice" in e for e in mf.validate(ok, {"page.md": PAGE + PAGE})[0]
    )
    assert any("does not exist" in e for e in mf.validate(ok, {"other.md": PAGE})[0])
    assert any(
        "placed in" in e for e in mf.validate(ok, {"page.md": "x", "other.md": PAGE})[0]
    )


def test_duplicate_slugs_are_rejected():
    errs, _ = mf.validate(manifest_with(SHOT, SHOT), {"page.md": PAGE})
    assert any("duplicate slug" in e for e in errs)


def test_unresolved_examples_are_warnings_not_errors():
    errs, warns = mf.validate(
        manifest_with(SHOT), {"page.md": PAGE + "\nTODO(example): write me\n"}
    )
    assert errs == [] and any("1 TODO(example)" in w for w in warns)


def test_authoring_doc_is_not_treated_as_a_page(tmp_path):
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "AUTHORING.md").write_text("<!-- shot:nope -->\n<!-- /shot -->")
    assert list(mf.read_pages(tmp_path)) == ["a.md"]


# ---- states and hashing
def test_state_machine(tmp_path):
    shot = copy.deepcopy(SHOT)
    assert mf.state({**shot, "status": "stub"}, {}, tmp_path) == "stub"
    assert mf.state(shot, {}, tmp_path) == "pending"
    (tmp_path / "demo-shot.png").write_bytes(b"png")
    assert mf.state(shot, {"demo-shot": mf.spec_hash(shot)}, tmp_path) == "captured"
    assert mf.state(shot, {"demo-shot": "old"}, tmp_path) == "stale"
    assert mf.state(shot, {}, tmp_path) == "stale"


def test_hash_ignores_prose_but_not_capture_fields():
    base = mf.spec_hash(SHOT)
    assert (
        mf.spec_hash(
            {
                **SHOT,
                "caption": "different",
                "intent": "x",
                "try": "y",
                "notes": "z",
                "step": "s",
            }
        )
        == base
    )
    for change in (
        {"actions": []},
        {"seed": {"extra_projects": ["A"]}},
        {"viewport": {"width": 390, "height": 800}},
        {"highlight": "#x"},
        {"target": "#y"},
        {"env": {"arc_down": True}},
        {"settle_ms": 10},
    ):
        assert mf.spec_hash({**SHOT, **change}) != base


def test_default_viewport_hashes_like_an_explicit_one():
    assert mf.spec_hash(SHOT) == mf.spec_hash({**SHOT, "viewport": mf.DEFAULT_VIEWPORT})


# ---- sync
def test_sync_rewrites_only_inside_markers_and_is_idempotent(tmp_path):
    by = {"demo-shot": SHOT}
    text = "intro\n\n" + PAGE + "\nTODO(example): mine\n"
    (tmp_path / "demo-shot.png").write_bytes(b"png")
    index = {"demo-shot": mf.spec_hash(SHOT)}
    once = mf.sync_text(text, by, index, tmp_path, "../assets/shots")
    assert "![A caption.](../assets/shots/demo-shot.png)" in once
    assert once.startswith("intro\n\n") and once.endswith("TODO(example): mine\n")
    assert mf.sync_text(once, by, index, tmp_path, "../assets/shots") == once
    assert "pending capture" in mf.sync_text(text, by, {}, tmp_path / "none")
    assert "Screenshot stub" in mf.sync_text(
        text, {"demo-shot": {**SHOT, "status": "stub"}}, {}, tmp_path
    )


def test_sync_leaves_unknown_markers_alone():
    text = "<!-- shot:other -->\nkeep\n<!-- /shot -->"
    assert mf.sync_text(text, {}, {}) == text


# ---- the real guide
def test_the_committed_guide_is_consistent():
    errs, _ = mf.validate(mf.load(), mf.read_pages())
    assert errs == []


def test_every_ready_shot_has_actions_or_is_a_plain_page_load():
    for s in mf.load()["shots"]:
        if s["status"] == "ready":
            assert isinstance(s.get("actions"), list)


def test_every_stub_says_what_to_try():
    for s in mf.load()["shots"]:
        if s["status"] == "stub":
            assert s.get("try"), f"{s['slug']} is a stub without a 'try' instruction"


def test_hold_chat_changes_the_hash_only_when_set():
    assert mf.spec_hash({**SHOT, "hold_chat": True}) != mf.spec_hash(SHOT)
    assert mf.spec_hash({**SHOT, "hold_chat": None}) == mf.spec_hash(SHOT)


def test_adding_an_optional_key_does_not_invalidate_existing_captures():
    """Guards the already-captured screenshots: their recorded hashes must still match."""
    index = mf.load_index()
    for s in mf.load()["shots"]:
        if s["slug"] in index and not s.get("hold_chat"):
            assert index[s["slug"]] == mf.spec_hash(s), (
                f"{s['slug']} would be recaptured for no reason"
            )
