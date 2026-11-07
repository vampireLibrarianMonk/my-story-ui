# Backlog

Working list for Prompt Nexus. Grouped by theme, newest priorities near the top of each group. Items marked
with a test id are already specified as strict expected-failure tests (`planned` or `known_bug`); when the
work lands, the marker is removed. Run `pytest -q -rx` to list them.

Status key: `[ ]` todo · `[~]` in progress · `[x]` done (kept briefly for context)

## Done recently
- [x] Character-profile reference template seeded into every project.
- [x] Normalized relationships (standalone edges, five scales, directed ties); two contrasting example characters linked across every scale; relationships rendered in the document view.
- [x] Prompt-first UI: slash commands, autocomplete, status strip replacing the sidebar.
- [x] Real-browser e2e suite + axe WCAG 2.1 AA across every state; `planned`/`known_bug` stubs.
- [x] Security: pre-commit (Ruff, hygiene, Gitleaks) + independent gate (Gitleaks, Semgrep, Bandit, Trivy, Grype, OSV).
- [x] User-guide screenshot pipeline (`tools/guide/shots.py`), manifest-driven, 41 slugs.
- [x] Bedrock eval harness driving the app's own prompt assembly; token/latency/cost logging.
- [x] Document tags + metadata (status/provenance/canon) in SQLite, with tag filtering API.
- [x] DynamoDB design (`docs/STORAGE.md`).

## Model integration (AWS Bedrock)
- [ ] Record token usage and cost in the Bedrock adapter itself, not just the eval harness, and surface it per reply.
- [ ] Per-mode default model (overridable by `/model`): character/world vs research vs prose. Confirm the DESIGN.md tradeoff first.
- [ ] Full task x model matrix run; pick a model per mode with evidence; write up the comparison.
- [ ] Confirm real per-1K pricing; replace estimates in `tools/eval/pricing.json`.
- [ ] Evaluate cheaper prose models (Qwen3, DeepSeek) against Mistral Large 3 for draft/continue.
- [ ] Provider capability discovery (streaming, max context) — `test_model_list_shows_capabilities`.
- [ ] Per-request token budget / cost telemetry surfaced in the UI — `test_token_budget_is_visible`.
- [ ] Real Arc inference path: test against an actual OpenAI-compatible endpoint (never validated).

## Assisted "flesh-out" mode
- [x] Backend `assist` flag + system instruction (ask 2-3 questions before a long artifact).
- [ ] UI: composer checkbox and a `/assist` command; carry the flag through the request.
- [ ] Tests: assist on vs off changes the system prompt and the reply shape; never answers its own questions.

## Storage
- [ ] `DocumentStore` protocol seam; `NEXUS_BACKEND=sqlite|dynamo` (see `docs/STORAGE.md`).
- [ ] `DynamoStore` against DynamoDB Local; run the API suite against both backends for parity.
- [ ] `tools/migrate/sqlite_to_dynamo.py` one-shot importer (dry-run first, keep SQLite backup).
- [ ] S3 spill for document bodies over ~300 KB (`s3_ref`).
- [ ] Tags in the frontend: a tag field in the document dialog; `/doc list #tag` filtering.
- [ ] Surface status/provenance/canon in the document view; guard canon promotion server-side.
- [ ] Conflict-link edge items so two drafts of a fact stay linked without being merged.
- [ ] Relationship editing UI (add/edit/delete ties from the character view; filter by scale).
- [ ] Relationship records map to DynamoDB edge items (REL#<from>#<to>#<scale>) per docs/STORAGE.md.

## Known bugs (each has a strict xfail test)
- [ ] Duplicate project names accepted — `test_duplicate_project_names_are_rejected`.
- [ ] Reload forgets the active project (unordered boot) — `test_reload_keeps_the_active_project`.
- [ ] Dialogs: no focus trap — `test_focus_stays_inside_an_open_dialog`.
- [ ] Dialogs: focus not returned to prompt on close — `test_focus_returns_to_the_prompt_after_closing_a_dialog`.
- [ ] Rejected chat request leaves an empty conversation — `test_rejected_request_leaves_no_empty_conversation`.
- [ ] Conversation search lists one thread per matching message — `test_search_lists_each_conversation_once`.
- [ ] Append silently picks the newest chapter when none selected — `test_append_asks_which_chapter_when_several_exist`.
- [ ] Explore widgets hidden while typing (default mode) — `test_explore_mode_shows_its_widgets_when_typing`.
- [ ] Open suggestion menu covers the status chips — `test_menu_does_not_hide_the_status_chips`.
- [ ] Failed request has no inline retry in the thread — `test_failure_is_shown_in_the_thread_with_a_retry_button`.
- [ ] History trim past 12 messages is silent — `test_long_threads_warn_when_history_is_trimmed`.

## Editing and generation (each has a planned test)
- [ ] Streaming replies with Stop — `test_stop_a_streaming_reply`.
- [ ] Regenerate last reply — `test_regenerate_last_reply`.
- [ ] Rename/delete a conversation — `test_rename_a_conversation`.
- [ ] Append shows a side-by-side diff — `test_append_shows_a_diff`.
- [ ] Document revision history with restore — `test_revision_history`.
- [ ] Delete/rename a document from the prompt — `test_delete_a_document`.
- [ ] Autosave + recover unsaved draft — `test_unsaved_draft_is_recovered`.
- [ ] Stale-edit detection (last-write-wins today) — `test_stale_edit_is_flagged`.
- [ ] Attach an excerpt, not a whole document — `test_attach_an_excerpt`.
- [ ] Context budget visible (what was truncated) — `test_context_budget_is_visible`.
- [ ] Data-driven widget registry with visibility rules — `test_widget_visibility_rules`.
- [ ] Explainable mode suggestion — `test_suggestion_explains_itself`.

## Research and retrieval
- [ ] Source retrieval with checkable citations, web vs archive labelled — `test_research_sources_can_be_attached`.
- [ ] Semantic + keyword hybrid search — `test_search_finds_synonyms`.

## Security and ops
- [ ] Resolve the OSV gate failure: Semgrep pins `mcp`/`opentelemetry-api` with known advisories in the scanner venv.
- [ ] CI: run pre-commit, pytest, and the security gate on push with branch protection.
- [ ] Firefox and WebKit in the browser suite after the Chromium baseline is stable.

## Docs and guide
- [ ] Author the 37 remaining screenshot stubs (`shots.py todo`); write the `TODO(example)` prose.
- [ ] Refresh `preview-*.png` (currently show the pre-redesign UI) or drop them.

## Privacy note
Story/canon content stays out of git. The private corpus lives in `dropbox/` (ignored); eval tasks and
canon rules live there too (`dropbox/eval_tasks.json`, `dropbox/canon_rules.json`). The committed harness,
rubric engine, and example files contain no character-specific content.
