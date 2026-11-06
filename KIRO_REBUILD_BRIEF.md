# Kiro build brief — rebuild `story-writer` around Prompt Nexus

## Scope

Do not migrate the old aggressive agent architecture by default. Inspect the actual current branch before overwriting anything. Use this project as a **reference scaffold**, not a mandate to preserve its exact folder structure.

Create a lightweight, prompt-first research/writing application with contextual widgets, selectable model provider, explicit saved materials, and portable local persistence. Optimize the user workflow for conversations that shift rapidly among fictional drafting, historical research, characters, institutional design, and alternative-history speculation.

## Golden path: first feature to preserve

1. User opens a project and sees one large blank prompt.
2. User types “Continue Chapter 5, following the council confrontation.”
3. UI suggests **Continue** and populates **Resume from** chapter dropdown, **Next step** and **Continuity** controls.
4. User chooses Chapter 5 and “Preserve voice and facts,” then sends to local Arc or Bedrock.
5. Backend combines explicit source excerpt + recent history + widget values, invokes provider, and archives both messages.
6. User reviews the answer and chooses **Append to chapter**; the editor shows the proposed addition *without auto-saving*.
7. User clicks Save. The chapter changes. The conversation remains archived.
8. User next types “Research historical analogues to the monarchy's response.” Without leaving the thread, the UI changes to **Research**.

## Backend integration boundaries

### Provider adapter

`generate(messages, provider_config, max_tokens) -> response_text`.

Existing scaffold: `app/providers.py`.

- Arc service: only assume OpenAI-compatible `POST /v1/chat/completions` after the Arc repo confirms the exact endpoint/contract. Its server may have a different adapter; don't infer it from the GPU hardware.
- Bedrock: Boto3 `bedrock-runtime.converse` using environment/IAM chain and configured model/profile ID.
- Future service: add a new provider without changing UI widgets, message schema, or project archive.
- Next: streaming and explicit provider capability discovery (`supports_streaming`, `max_context`, etc.).

### Prompt planner

Current: transparent deterministic keyword rules (`app/intent.py`) and matching client-side regex. Future: one centralized server-defined mode registry with a fast local suggestion layer. A model-based suggestion is optional, explainable, non-blocking and user-overridable. Never allow a classifier to automatically save output.

### Material archive

Current: SQLite projects, documents, conversations, messages. Future: document revisions, user-approved excerpts, source provenance, citation records, scene/chapter ordering, optional FTS5 and vector retrieval. Do not design a global knowledge graph before validating retrieval tasks.

### Research provider (not included yet)

Add an explicit retrieval contract `search(query, provider, filters) -> results[{title,url,snippet,published_at,retrieved_at}]` with checkable source citations. Choose whether queries use the external web or project archive; label the distinction in the UI. **Do not imply Bedrock or a local model has live web access by default.**

## Implementation stages

**Stage 1 — Baseline and cleanup:** Fork/branch the existing `story-writer`; inventory reusable code, remove dead modules/unused pipeline stages; preserve any existing manuscript data; incorporate prompt UI as feature flag.

**Stage 2 — Stabilize request contract:** Single `PromptAction` schema, consistent backend/client intent inference, restore message and context state after provider failures. Add typed API models and tests. Ensure saved chapters aren't affected by mere chat completion.

**Stage 3 — Arc integration:** Inspect the actual Arc repo's model-serving endpoint, auth, streaming, model IDs, batching, and GPU availability. Run a conformance suite against real service; profile one 16GB A770 before adding multi-GPU tuning.

**Stage 4 — Bedrock integration:** Verify region, inference profiles, IAM permissions, quotas, streaming, and cost telemetry. Test against a real authorized model with a low token budget. Keep credentials server-side.

**Stage 5 — Text operations:** Add Markdown editing, passage selection, save-as, append-with-diff, auto-recovery of unsaved drafts, document version history.

**Stage 6 — Research and retrieval:** Integrate source search (web and archive separately); allow manually attaching sources; store retrieved metadata/citation provenance, optimize FTS5 and hybrid retrieval.

**Stage 7 — Usability and safety:** Playwright E2E, keyboard navigation, responsive layout, graceful errors, prompt injection boundaries, sensible context budgets, local backup/restore. Never expose an unauthenticated writable service to the public internet.

## Acceptance criteria

- Fresh install starts in demo mode, no network secret required.
- Creating a chapter, resuming it, branching into character or world exploration are accomplishable in the same conversation using turn-level modes.
- Intent suggestions are visible but easy to override.
- Each widget has a functional effect on prompt generation or target selection.
- Changing provider doesn't change how projects and documents are stored.
- Local inference failures never result in fake assistant messages.
- Project exports remain readable without any AI service.
- A missing chapter/source is **not** fabricated for the model.

## Baseline verification

`pytest -q` runs the API, tooling and real-browser suites (see README). Features not built yet are specified as strict expected-failure tests marked `planned`. Real Arc/Bedrock integration remains untested until configured.
