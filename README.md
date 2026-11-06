# Prompt Nexus · Story Studio

A **prompt-first** writing workspace. Start with a thought; the interface suggests a mode and reveals small controls appropriate to that prompt. Conversations, draft chapters, character notes, worldbuilding notes, and research notes live in a local SQLite project archive. AI generation can use a local OpenAI-compatible server (e.g., one eventually exposed by the Intel Arc A770 project) or AWS Bedrock's Converse API.

This is an **independently runnable, functional UI prototype**, not an update to the existing `story-writer` GitHub repository. No production authentication, external web search, vector index, streaming responses, or agent framework are included.

## Run locally

Prerequisites: Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765**. It works in explicit **Demo · no model** mode, enabling you to test the entire UI and save ideas without GPU or AWS access. Data is stored in `./nexus.sqlite3` by default. To set a different path, use `NEXUS_DB=/path/to/data.sqlite3`.

## Connect to the Arc inference service

This app **does not** install, configure, or claim compatibility with any particular Arc GPU driver. It expects your Arc project to expose an HTTP service supporting the familiar OpenAI-style non-streaming `POST /v1/chat/completions` contract. If that project currently exposes a different API, implement a small adapter in `app/providers.py`.

```bash
export ARC_CHAT_URL='http://127.0.0.1:8080/v1/chat/completions'
export ARC_MODEL_ID='your-actual-served-model-id'
# Optional if your service requires a token:
# export ARC_API_KEY='...'
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Reload the browser and type `/model arc` in the prompt. The app sends `model`, `messages`, `temperature`, `max_tokens`, `stream:false` and reads `choices[0].message.content`. If your Arc server runs on another machine, point `ARC_CHAT_URL` at its reachable service URL and secure the network path. The local endpoint in `.env.example` is **illustrative, not an assertion that the Arc repository has reached that API milestone**.

## Connect to AWS Bedrock

```bash
pip install -r requirements-bedrock.txt
export AWS_PROFILE='your-named-profile'   # or use a machine IAM role
export AWS_REGION='us-east-1'
export BEDROCK_MODEL_ID='your-available-bedrock-model-or-inference-profile-id'
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Type `/model bedrock` in the prompt. The backend uses Boto3 `bedrock-runtime.converse` for supported models. No AWS keys are sent to the browser or persisted in SQLite. Your credentials must grant the right Bedrock model/inference-profile invocation permissions in your AWS account/region. Cost and quota are dependent on the configured Bedrock resource.

## The UI: type first, tools second

| What you type | Suggested mode | Controls shown |
|---|---|---|
| “Start a new chapter where a character arrives…” | New chapter | Chapter context, POV, tone, scope |
| “Continue the scene from Chapter 4…” | Continue | Existing chapter, next step, continuity |
| “Explore the character's motivations…” | Character | Character document, focus, format |
| “Build the factions opposing the change…” | Worldbuilding | World document, domain, lens |
| “Research the historical precedent…” | Research | Research method, uncertainty threshold |
| “What if the ruler refuses?” | Explore | Approach, deliverable |

The suggestion is deterministic and instantaneous; click a mode pill to override it. **Each subsequent prompt is classified afresh.** The selected widgets become actual AI instructions; selected documents are included as reference text. If no relevant document exists, the selector stays empty rather than inventing one.

### Commands: the prompt is the whole interface

There is no sidebar and no top-bar menu. Start a prompt with `/` to run a command locally (no model is called). A suggestion menu appears; Tab or Enter accepts, arrow keys move, Escape closes. A status strip above the prompt shows the project, model and counts, and each chip pre-fills its command.

| Command | What it does |
|---|---|
| `/project new\|switch\|rename\|delete\|list` | Manage projects. Delete needs the exact project name and cannot be undone. |
| `/model demo\|arc\|bedrock\|list` | Choose the AI model. Unconfigured models are refused with guidance. |
| `/new` | Start a new thought. |
| `/doc new\|open\|list` | Create, edit or list documents. |
| `/chat open\|list` | Reopen or list conversations. |
| `/search <text>` | Search saved documents and conversations. |
| `/export` | Download the project as JSON. |
| `/help` | List the commands. |

An unknown command such as `/frobnicate` is refused locally and never sent to a model.

### Working with generated content

* Chat replies are archived automatically in the selected project.
* Replies are **not** automatically inserted into a chapter or promoted to canon.
* Click **Save as note**, **Save as chapter**, or the mode-appropriate save button to open the editable document view, then confirm the save.
* For an existing chapter, **Append to chapter** opens a reviewable edit; nothing changes until **Save document**.
* **Search** (Ctrl/Cmd+K or `/search <text>`) searches saved document and conversation text. This is a local text search, not live internet research.
* **Export** (`/export`) downloads all documents and conversations as JSON.
* The initial `My first project` project is an **empty workspace**, not pre-populated canon. Create more with `/project new <name>`.

### Known prototype limitations

- The app sends completed responses, not streamed tokens. Cancellation and retry are future work.
- Deterministic keyword intent suggestions are deliberately simple, not a trained intent model.
- Local search uses indexed SQLite tables and `LIKE` matching, not embeddings or online sources. Related-material suggestions use keyword overlap.
- A `research` mode guides response style but **cannot independently verify facts, browse current sources, or generate reliable citations** without a separate retrieval integration.
- The server uses a SQLite database and has no authentication: **keep it bound to 127.0.0.1**, or use an SSH tunnel. Do not expose the API publicly.
- API use is capped to 12 previous chat messages and selected document excerpts. This is a basic context policy, not sophisticated long-context management.
- Editing documents is currently last-write-wins; there is no revision history, multi-user collaboration, or autosave.

## API overview

- `GET /api/bootstrap` — available modes, widget schemas, projects, configured providers.
- `POST /api/projects` — create a project.
- `GET /api/projects/{id}/overview` — document and conversation inventory.
- `POST /api/documents`, `PATCH /api/documents/{id}` — create/edit source material.
- `GET /api/projects/{id}/context?q=...` — suggest mode and related documents.
- `GET /api/projects/{id}/search?q=...` — local text search.
- `POST /api/chat` — one prompt + mode + provider + widget selections + explicit context IDs.
- `GET /api/conversations/{id}` — persisted thread and messages.
- `GET /api/projects/{id}/export` — portable JSON export.

Example chat request:

```json
{
  "project_id": "<project-id>",
  "prompt": "Continue the chapter from the final paragraph",
  "mode": "continue",
  "provider": "demo",
  "conversation_id": null,
  "context_ids": ["<chapter-document-id>"],
  "options": {"direction": "Continue directly", "consistency": "Preserve voice and facts"}
}
```

## Test

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
pytest -q            # API, tooling and browser tests (about 4 minutes)
pytest -q tests/test_api.py tests/test_guide_tools.py   # fast, no browser
```

The browser tests in `tests/e2e/` drive real Chromium against a real server with a throwaway SQLite file per test. Nothing is mocked. They include WCAG 2.1 AA checks (axe-core) across every screen state.

Tests marked `planned` are specifications for features that are not built yet, and tests marked `known_bug` describe defects that exist today. Both are strict expected failures: they fail now, and when the work lands they pass, which flags the marker for removal. List them with `pytest -q -rx`.

Not yet exercised: an actual Arc model call, an actual AWS Bedrock call, Firefox and WebKit, and CI.

## Security and quality checks

Fast checks run on every commit through pre-commit (Ruff, file hygiene, private-key detection, Gitleaks on staged changes): `pip install pre-commit && pre-commit install`.

Independent scans run on demand: `python3 tools/ai-sec/security_gate.py --scope code` (Gitleaks, Semgrep with project rules in `.semgrep/`, Bandit, Trivy, Grype, OSV-Scanner). Scanner binaries are installed separately (see `requirements-security.txt` for the Python ones). A missing scanner makes the gate incomplete, never green. Known open item: OSV-Scanner flags Semgrep's own pinned dependencies in the scanner environment.

Read `KIRO_REBUILD_BRIEF.md` for the integration and follow-on build spec. See `DESIGN.md` for interaction principles and state transitions.

## User guide

The guide lives in `docs/user-guide/`. Its screenshots are captured from the running app by `tools/guide/shots.py`; see `docs/user-guide/AUTHORING.md`.
