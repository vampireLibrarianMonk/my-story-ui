# Authoring the user guide

Every screenshot in the guide is a **slug**. A slug has one entry in `shots.json` (how to capture it) and one marker in a page (where it shows up). The tool captures from the real app, so screenshots cannot drift from the product.

## The loop

```bash
.venv/bin/python -m tools.guide.shots todo            # what needs work, with instructions
.venv/bin/python -m tools.guide.shots show SLUG       # one shot in full
# edit docs/user-guide/shots.json: fill in seed + actions, set "status": "ready"
.venv/bin/python -m tools.guide.shots check           # manifest and pages agree
.venv/bin/python -m tools.guide.shots capture SLUG    # or with no slug: every pending and stale shot
.venv/bin/python -m tools.guide.shots list            # progress
```

`todo --json` prints the same information for scripts and for Kiro. To have Kiro pick up the work, say: *"Run `shots.py todo --page 03-commands.md` and author those stubs."*

## States

| State | Meaning | Next step |
|---|---|---|
| stub | Described but not authored | Fill in `seed` and `actions`, set `status` to `ready` |
| pending | Authored, never captured | `capture` |
| captured | Image exists and matches the spec | nothing |
| stale | The capture fields changed after the image was taken | `capture` again |

Only fields that change pixels (`seed`, `env`, `viewport`, `actions`, `target`, `highlight`, `settle_ms`) mark a shot stale. Editing a caption or note does not.

## A shot entry

```json
{
  "slug": "mode-continue-detected",
  "page": "02-modes-and-widgets.md",
  "step": "Continue is suggested",
  "status": "ready",
  "caption": "Typing a 'resume' style prompt switches the pane to the continue controls.",
  "intent": "Show Resume from, Next step and Continuity appearing without any click.",
  "seed": {"documents": [{"type": "chapter", "title": "Chapter 5", "body": "The hall fell silent."}]},
  "actions": [
    {"do": "type", "text": "Resume the scene after the argument"},
    {"do": "select", "label": "Resume from", "option": "Chapter 5"}
  ],
  "highlight": "#contextTitle"
}
```

`caption` is shown under the image and used as its alt text, so write it as a sentence that describes what is visible. `intent` says what the screenshot must prove and is for authors only. `try` and `notes` are free text for the person authoring the stub.

## Actions

| `do` | Fields | What it does |
|---|---|---|
| `type` | `text` | Put text in the prompt without sending |
| `send` | | Ctrl+Enter, then wait until the app is idle |
| `send_no_wait` | | Ctrl+Enter and return at once. Pair with `hold_chat` and `wait_visible` to capture the busy state |
| `run` | `text` | Type and send a command |
| `ask` | `text` | Type and send a chat prompt, wait for one more reply |
| `press` | `key` | Press a key, for example `ArrowDown` or `Escape` |
| `click` | `role`+`name`, or `text`, or `selector` | Click one thing |
| `select` | `label`, `option` | Choose a value in a context-pane widget |
| `search` | `query` | Open the archive search and type |
| `wait` | `ms` (0 to 2000) | Short pause; prefer waiting for a state |
| `wait_visible` | `selector` | Wait for an element |

Other fields: `viewport` (`{"width":390,"height":800}`, default 1440 by 900), `target` (a CSS selector to crop to one element), `highlight` (a selector or list; draws an orange outline), `env` (`{"arc_down": true}` points Arc at a port nothing listens on, so a real connection failure is shown), `settle_ms`, `hold_chat` (`true`: the chat request is left pending so the busy state stays on screen; nothing is answered or mocked).

## Seeds

Each shot starts with a fresh server and an empty database, so a seed is the only data it has.

```json
"seed": {
  "documents": [{"type": "chapter", "title": "Chapter 5", "body": "..."}],
  "conversations": [{"prompt": "Explore trade routes"}],
  "extra_projects": ["Atlas", "Scratch"]
}
```

Seeds are created through the real API. Conversations are created with the demo model. Document types are `chapter`, `character`, `world`, `research`, `note`.

## Rules

- **Use invented, abstract content.** No real names, no private text, no secrets. Screenshots are committed.
- **One idea per shot.** If a caption needs "and", split it.
- **Highlight sparingly.** One outline, on the thing the reader should look at.
- **Never edit the PNGs.** Change the spec and recapture.
- **Do not fake state.** If a shot needs something the tool cannot do (for example a slow response), leave it a stub and say why in `notes`.

## Adding a new shot

```bash
.venv/bin/python -m tools.guide.shots new my-new-slug --page 03-commands.md --step "Name the step"
```

This appends a stub to the manifest and its marker to the end of the page. Move the marker where you want it. Then run the loop above.

## Prose

Each section has a `TODO(example)` line for the worked example. `shots.py check` warns about them, and `check --strict` fails while any remain, so it can be used as a release gate once the writing is done.

`shots.py capture` and `shots.py sync` rewrite only the text between `<!-- shot:SLUG -->` and `<!-- /shot -->`. Everything outside the markers is yours.
