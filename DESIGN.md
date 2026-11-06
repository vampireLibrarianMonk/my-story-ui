# Prompt Nexus: interaction design

## Product statement

A blank prompt is the primary interface. **The prompt is the nexus of an action**, not merely a message box. The application starts with a Google-like blank slate, then reveals the smallest relevant controls as the user writes and their work grows.

## Three independent things

1. **Intent (per prompt):** explore, draft, continue, character, world, research. Intent can change between any two consecutive messages.
2. **Model (per request):** demo, local Arc service, AWS Bedrock; future providers adhere to a common completion interface.
3. **Materials (per project):** conversation history and explicitly selected documents; only the user decides what gets committed to an artifact.

Don't conflate mode, model, or document status.

## Progressive-disclosure sequence

### Empty state

- Big centered prompt with no mandatory forms.
- Tiny action pills for choosing an intent manually.
- Quiet placeholder panel: “Context, when needed.”
- A status strip above the prompt shows project, model and counts. Projects, models, documents and conversations are managed with slash commands in the prompt itself; there are no menus.

### Typing state

- Local regex intent guess runs immediately. No network request or model latency.
- Pane reveals mode-specific controls and available documents.
- Related documents load after a debounce and appear as optional checkboxes.
- User can change suggested mode via one click. Choice is visible and reversible.

### Submitting state

- The prompt, explicit document IDs, widget selections and model selection form a typed API request.
- Backend validates document ownership, constructs system context, preserves message history, invokes provider.
- Provider errors remain errors, never synthetic AI completions.

### Reply state

- A readable conversational transcript replaces hero copy.
- The same composer stays available and can detect a *different* activity next turn.
- Action buttons on a reply allow saving a new chapter, note, character/world material, or reviewing an append to an existing chapter.

## Why not hard-wire a six-tab application?

A user may move from plot drafting → researching medieval institutions → exploring character motives → writing dialogue in one uninterrupted session. Those are *turn-level actions*, not necessarily permanent workspace sections.

## Widget contract (future direction)

Widget schemas currently come from `app/intent.py` and are rendered by JavaScript. In the next iteration, make the registry data-driven:

```
ModeDefinition {id, title, description, matchSignals, widgets[]}
WidgetDefinition {id, inputType, label, values, dataSource?, validation?, visibilityRule?}
PromptAction {text, mode, modelId, widgetValues, selectedSources[], targetArtifact?}
```

Widget outputs must affect the submitted action. A selector that doesn't change the model request or the stored artifact should not exist.

## Product safeguards

- **No automatic canon**: creative outputs become persisted documents only on an explicit save.
- **Source boundaries**: retrieval references are designated as reference data, not higher-priority instructions.
- **Honest research**: no source claims without retrievable, checkable evidence.
- **No stranded prompt**: upstream model errors retain the user's text in the archive.
- **No vendor lock-in**: chats and documents can be exported as portable JSON.

## Suggestions for the subsequent version

- Stream tokens and support cancel/retry/regenerate.
- Chapter editor with save version history and patch/diff preview.
- Research retrieval service with sourced results, selection toggles and citations.
- Search-over-project context selection, semantic + keyword hybrid search.
- Per-project style guides and reference collections.
- More expressive intent interpretation: a small classifier can **suggest** widgets without directly modifying project content.
- Configurable local inference profiles for GPU memory and latency awareness.
