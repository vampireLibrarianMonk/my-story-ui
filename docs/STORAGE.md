# Storage: local now, DynamoDB later

## Where things stand

SQLite is the source of truth today. `app/storage.py` owns the schema and is the single data-access
layer the API calls. As of this change, a document is:

| column | meaning |
|---|---|
| `id`, `project_id`, `type`, `title`, `body`, `updated_at` | unchanged original fields |
| `tags` | JSON array of lowercase strings, mirrored into `document_tags` for fast filtering |
| `metadata` | JSON object for status and provenance, e.g. `{"status": "MIXED", "source_confidence": "AUTHOR-STATED", "canon": false}` |

`document_tags(document_id, tag)` is a lookup table so tag filters are index hits, not JSON scans.
Migrations in `_migrate()` are additive and idempotent: they run on every startup, add columns only if
missing, and never drop data. Existing databases keep working with empty tags and metadata.

New API:

- `POST /api/documents` and `PATCH /api/documents/{id}` accept `tags` and `metadata`.
- `GET /api/projects/{id}/tags` returns every tag with a document count (for allocation UIs).
- `GET /api/projects/{id}/documents?tags=a,b&match=any|all` filters by tag.

This is enough to tag a saved character profile (`hero`, `age-12`, `character`, `canon:false`) and later
pull "everything tagged `hero` and `allies`".

## Why DynamoDB is the right next step, and why not yet

The corpus the author handed over is the argument for structured, queryable storage: typed status, source
confidence, conflict links, and hard-count invariants that must survive export and never be silently
promoted to canon. SQLite handles that for a single-user, single-machine prototype. DynamoDB earns its
place only when we need: multi-device or multi-user access, durability beyond one laptop, and tag or
status queries at a scale where a local index is not enough.

Until then, DynamoDB is a **plan**, not a dependency. The app must keep running with zero AWS access
(the demo-mode and local-first principle). So the design is a storage backend behind the existing
`storage.py` surface, selected by configuration, not a rewrite.

## Table design (single-table)

One table, `nexus`, with a generic primary key and overloaded items. This keeps related data in one place
and lets us add entity types without new tables.

| | partition key `PK` | sort key `SK` | notable attributes |
|---|---|---|---|
| Project | `PROJECT#<pid>` | `META` | `name`, `created_at` |
| Document | `PROJECT#<pid>` | `DOC#<updated_at>#<did>` | `type`, `title`, `body`, `tags` (String Set), `status`, `source_confidence`, `canon` (Bool), `version` |
| Conversation | `PROJECT#<pid>` | `CONV#<created_at>#<cid>` | `title` |
| Message | `CONV#<cid>` | `MSG#<created_at>#<mid>` | `role`, `content`, `mode`, `provider`, `context_ids`, `options` |
| Tag edge | `PROJECT#<pid>` | `TAG#<tag>#<did>` | `title`, `type` (duplicated for list-without-fetch) |

Access patterns and how each is served:

- All documents in a project: `Query PK=PROJECT#pid, SK begins_with DOC#` (already time-ordered by the
  `updated_at` prefix in `SK`).
- Documents by tag (allocation): `Query PK=PROJECT#pid, SK begins_with TAG#<tag>#`. `match=all` is an
  application-side intersection of the per-tag result sets.
- Tag catalog with counts: `Query PK=PROJECT#pid, SK begins_with TAG#` and fold.
- A conversation's messages: `Query PK=CONV#cid, SK begins_with MSG#`.
- One document by id: carry `did` so the `SK` is reconstructable, or add **GSI1** (`GSI1PK=DOC#<did>`) for
  direct lookup. Prefer GSI1; it also serves cross-project admin reads.

Tags use a native **String Set** on the item for round-tripping, plus the `TAG#` edge items for querying.
The edge items duplicate `title` and `type` so a tag listing needs no second fetch. Writing a document is
therefore a `TransactWriteItems` of the document item plus one `TAG#` item per tag, so tags and body never
drift apart.

### Allocation and cost control

- **Capacity:** on-demand billing to start; this is bursty, single-author traffic. Switch to provisioned
  with autoscaling only if a steady high rate appears.
- **Item size:** DynamoDB caps an item at 400 KB. `body` can exceed that for a long chapter. Rule: if
  `body` is over ~300 KB, store it in S3 (`s3://.../projects/<pid>/docs/<did>.md`) and keep an `s3_ref`
  attribute; small bodies stay inline. The read layer resolves `s3_ref` transparently.
- **Hot partition:** a single project is one partition key. For one author this is fine. If a project ever
  holds tens of thousands of items, shard the `PK` (`PROJECT#pid#<bucket>`); not needed now.
- **TTL:** optional `expires_at` on scratch or eval items so throwaway data self-deletes.

### Keeping canon safe in DynamoDB

- `status`, `source_confidence`, and `canon` are first-class attributes, not buried in a blob, so a query
  can filter `canon = false` and an export carries them. This is the corpus's explicit ingestion rule.
- Promotion to canon is a deliberate write (`canon` false to true) guarded server-side, never a side
  effect of generation, matching the no-auto-canon rule already enforced in the app.
- Conflict links (e.g. L-035 early-party vs childhood timeline) are edge items
  (`SK = CONFLICT#<other_did>`), so the two versions stay linked and searchable without being merged.

## Migration path (reversible, staged)

1. **Backend seam.** Introduce a `DocumentStore` protocol with the methods the API already uses
   (`create_document`, `update_document`, `documents_by_tags`, `project_tags`, and the project and
   conversation calls). `SqliteStore` is the current code; `DynamoStore` is new. A `NEXUS_BACKEND` env var
   (`sqlite` default, `dynamo` opt-in) selects one. No endpoint changes.
2. **Dynamo implementation + Local.** Build `DynamoStore` against **DynamoDB Local** (a container) so tests
   run with no cloud and no cost. Run the existing API test suite against both backends to prove parity.
3. **One-shot importer.** `tools/migrate/sqlite_to_dynamo.py` reads the SQLite file and `TransactWriteItems`
   into the table. Idempotent on `id`, dry-run first, verify counts, keep the SQLite file as the backup.
4. **IAM and infra.** A least-privilege policy scoped to the one table and its GSI (no `Scan`, no delete on
   the table resource). Define the table in code (CDK or a committed CloudFormation template) so it is
   reviewable and reproducible; do not click it together in the console.
5. **Cutover.** Flip `NEXUS_BACKEND=dynamo` in the server environment. Because the seam preserves behavior,
   the UI and all tests are unchanged. Roll back by flipping it back; the SQLite backup is still intact.

## What stays true throughout

- The app runs with no AWS access in `sqlite` mode. DynamoDB never becomes mandatory.
- No credentials in the browser or in SQLite; the backend uses the IAM role or profile chain.
- Export stays portable JSON and carries tags, status, and provenance regardless of backend.
- Generation never writes canon. Saving and promotion are explicit, guarded, server-side actions.
