"""SQLite storage: intentionally limited to projects, documents, sessions, messages."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

DB_PATH = None


def setup(db_path: str | None = None) -> None:
    global DB_PATH
    DB_PATH = db_path or os.environ.get("NEXUS_DB", "nexus.sqlite3")
    db = Path(DB_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role TEXT NOT NULL, content TEXT NOT NULL, mode TEXT NOT NULL,
            provider TEXT NOT NULL, context_ids TEXT NOT NULL DEFAULT '[]',
            options TEXT NOT NULL DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS doc_by_project ON documents(project_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS message_by_convo ON messages(conversation_id, created_at);
        """)
        if not con.execute("SELECT id FROM projects LIMIT 1").fetchone():
            con.execute(
                "INSERT INTO projects(id,name) VALUES (?,?)",
                (new_id(), "My first project"),
            )
    _migrate()


def _columns(con, table: str) -> set[str]:
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}


def _migrate() -> None:
    """Idempotent, additive migrations. Safe to run on every startup; never drops data.

    tags:     comma-free JSON array of lowercase strings, for allocation and filtering.
    metadata: JSON object for status/provenance/canon labels the corpus requires
              (e.g. {"status": "MIXED", "source_confidence": "AUTHOR-STATED", "canon": false}).
    """
    with connect() as con:
        cols = _columns(con, "documents")
        if "tags" not in cols:
            con.execute(
                "ALTER TABLE documents ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
            )
        if "metadata" not in cols:
            con.execute(
                "ALTER TABLE documents ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'"
            )
        # Tag lookup table keeps filtering fast and avoids LIKE scans over the JSON blob.
        con.executescript("""
        CREATE TABLE IF NOT EXISTS document_tags (
            document_id TEXT NOT NULL REFERENCES documents(id),
            tag TEXT NOT NULL,
            PRIMARY KEY (document_id, tag)
        );
        CREATE INDEX IF NOT EXISTS tag_by_name ON document_tags(tag, document_id);
        """)


def normalize_tags(tags) -> list[str]:
    """Lowercase, trimmed, de-duplicated, order-preserving. Rejects empties and overlong tags."""
    seen: dict[str, None] = {}
    for t in tags or []:
        if not isinstance(t, str):
            continue
        key = t.strip().lower()
        if key and len(key) <= 60:
            seen.setdefault(key, None)
    return list(seen)


def _sync_tags(con, did: str, tags: list[str]) -> None:
    con.execute("DELETE FROM document_tags WHERE document_id=?", (did,))
    con.executemany(
        "INSERT OR IGNORE INTO document_tags(document_id, tag) VALUES (?, ?)",
        [(did, t) for t in tags],
    )


def new_id() -> str:
    return uuid4().hex[:16]


@contextmanager
def connect():
    if not DB_PATH:
        setup()
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def all_rows(sql: str, params=()):
    with connect() as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def one(sql: str, params=()):
    with connect() as con:
        result = con.execute(sql, params).fetchone()
    return dict(result) if result else None


def create_project(name: str):
    pid = new_id()
    with connect() as con:
        con.execute("INSERT INTO projects(id,name) VALUES (?,?)", (pid, name))
    return one("SELECT * FROM projects WHERE id=?", (pid,))


def rename_project(pid: str, name: str):
    with connect() as con:
        con.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))
    return one("SELECT * FROM projects WHERE id=?", (pid,))


def delete_project(pid: str) -> dict:
    """Permanently remove a project and everything in it. Returns removed counts."""
    with connect() as con:
        convo_ids = [
            r["id"]
            for r in con.execute(
                "SELECT id FROM conversations WHERE project_id=?", (pid,)
            )
        ]
        for cid in convo_ids:
            con.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        con.execute(
            "DELETE FROM document_tags WHERE document_id IN (SELECT id FROM documents WHERE project_id=?)",
            (pid,),
        )
        docs = con.execute("DELETE FROM documents WHERE project_id=?", (pid,)).rowcount
        con.execute("DELETE FROM conversations WHERE project_id=?", (pid,))
        con.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"documents": docs, "conversations": len(convo_ids)}


def create_document(
    pid: str,
    doc_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
):
    did = new_id()
    tag_list = normalize_tags(tags)
    with connect() as con:
        con.execute(
            "INSERT INTO documents(id,project_id,type,title,body,tags,metadata) VALUES (?,?,?,?,?,?,?)",
            (
                did,
                pid,
                doc_type,
                title,
                body,
                json.dumps(tag_list),
                json.dumps(metadata or {}),
            ),
        )
        _sync_tags(con, did, tag_list)
    return one("SELECT * FROM documents WHERE id=?", (did,))


def update_document(
    did: str,
    title: str | None,
    body: str | None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
):
    with connect() as con:
        con.execute(
            """UPDATE documents SET title=COALESCE(?,title), body=COALESCE(?,body),
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (title, body, did),
        )
        if tags is not None:
            tag_list = normalize_tags(tags)
            con.execute(
                "UPDATE documents SET tags=? WHERE id=?", (json.dumps(tag_list), did)
            )
            _sync_tags(con, did, tag_list)
        if metadata is not None:
            con.execute(
                "UPDATE documents SET metadata=? WHERE id=?",
                (json.dumps(metadata), did),
            )
    return one("SELECT * FROM documents WHERE id=?", (did,))


def documents_by_tags(pid: str, tags: list[str], match: str = "any", limit: int = 100):
    """Documents in a project carrying the given tags. match='any' (union) or 'all' (intersection)."""
    wanted = normalize_tags(tags)
    if not wanted:
        return []
    placeholders = ",".join("?" for _ in wanted)
    having = "" if match == "any" else f"HAVING COUNT(DISTINCT dt.tag) = {len(wanted)}"
    return all_rows(
        f"""SELECT d.id, d.project_id, d.type, d.title, substr(d.body,1,160) AS excerpt,
                   d.tags, d.metadata, d.updated_at
            FROM documents d JOIN document_tags dt ON dt.document_id = d.id
            WHERE d.project_id=? AND dt.tag IN ({placeholders})
            GROUP BY d.id {having}
            ORDER BY d.updated_at DESC LIMIT ?""",
        (pid, *wanted, limit),
    )


def project_tags(pid: str):
    """Every tag used in a project with its document count, most-used first (for allocation UIs)."""
    return all_rows(
        """SELECT dt.tag AS tag, COUNT(*) AS count
           FROM document_tags dt JOIN documents d ON d.id = dt.document_id
           WHERE d.project_id=? GROUP BY dt.tag ORDER BY count DESC, tag ASC""",
        (pid,),
    )


# --- Document images: bytes live on disk beside the database, referenced from metadata. ---
# This is the local-first backend. The storage plan (docs/STORAGE.md) swaps this for S3 behind the
# same two functions without touching the API.

IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _images_dir() -> Path:
    d = Path(DB_PATH).resolve().parent / "nexus_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_document_image(did: str, data: bytes, content_type: str) -> dict:
    """Persist an image for a document and record a reference in its metadata. Returns the updated doc."""
    ext = IMAGE_TYPES[content_type]
    path = _images_dir() / f"{did}.{ext}"
    # Remove any prior image in a different format so there is exactly one per document.
    for old in _images_dir().glob(f"{did}.*"):
        if old != path:
            old.unlink()
    path.write_bytes(data)
    doc = one("SELECT metadata FROM documents WHERE id=?", (did,))
    meta = json.loads(doc["metadata"]) if doc and doc["metadata"] else {}
    meta["image"] = {"ext": ext, "content_type": content_type, "bytes": len(data)}
    with connect() as con:
        con.execute(
            "UPDATE documents SET metadata=? WHERE id=?", (json.dumps(meta), did)
        )
    return one("SELECT * FROM documents WHERE id=?", (did,))


def document_image_path(did: str):
    """(path, content_type) for a document's image, or None. Reads the reference from metadata."""
    doc = one("SELECT metadata FROM documents WHERE id=?", (did,))
    if not doc:
        return None
    meta = json.loads(doc["metadata"]) if doc["metadata"] else {}
    img = meta.get("image")
    if not img:
        return None
    path = _images_dir() / f"{did}.{img['ext']}"
    return (path, img["content_type"]) if path.exists() else None


def delete_document_image(did: str) -> dict:
    for old in _images_dir().glob(f"{did}.*"):
        old.unlink()
    doc = one("SELECT metadata FROM documents WHERE id=?", (did,))
    meta = json.loads(doc["metadata"]) if doc and doc["metadata"] else {}
    meta.pop("image", None)
    with connect() as con:
        con.execute(
            "UPDATE documents SET metadata=? WHERE id=?", (json.dumps(meta), did)
        )
    return one("SELECT * FROM documents WHERE id=?", (did,))


def create_conversation(pid: str, title: str):
    cid = new_id()
    with connect() as con:
        con.execute(
            "INSERT INTO conversations(id,project_id,title) VALUES (?,?,?)",
            (cid, pid, title),
        )
    return one("SELECT * FROM conversations WHERE id=?", (cid,))


def save_message(
    cid: str,
    role: str,
    content: str,
    mode: str,
    provider: str,
    context_ids: list[str],
    options: dict,
):
    mid = new_id()
    with connect() as con:
        con.execute(
            """INSERT INTO messages(id,conversation_id,role,content,mode,provider,context_ids,options)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                mid,
                cid,
                role,
                content,
                mode,
                provider,
                json.dumps(context_ids),
                json.dumps(options),
            ),
        )
    return one("SELECT * FROM messages WHERE id=?", (mid,))


def conversation_messages(cid: str):
    return all_rows(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC, rowid ASC",
        (cid,),
    )


def search(pid: str, q: str, limit=12):
    """Small initial local search, intentionally without a vector DB."""
    term = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    docs = all_rows(
        """SELECT id, type, title, substr(body,1,250) AS excerpt,updated_at
             FROM documents WHERE project_id=? AND (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')
             ORDER BY CASE WHEN title LIKE ? ESCAPE '\\' THEN 0 ELSE 1 END, updated_at DESC LIMIT ?""",
        (pid, term, term, term, limit),
    )
    chats = all_rows(
        """SELECT DISTINCT c.id AS id, 'conversation' AS type, c.title AS title,
             substr(m.content,1,250) AS excerpt, c.created_at AS updated_at
             FROM conversations c JOIN messages m ON m.conversation_id=c.id
             WHERE c.project_id=? AND (c.title LIKE ? ESCAPE '\\' OR m.content LIKE ? ESCAPE '\\')
             ORDER BY c.created_at DESC LIMIT ?""",
        (pid, term, term, limit),
    )
    return {"documents": docs, "conversations": chats}


def related(pid: str, prompt: str, limit: int = 6):
    """Explanatory keyword overlap; no faux semantic/AI search."""
    import re

    words = set(re.findall(r"[a-zA-Z]{4,}", prompt.lower())) - {
        "what",
        "with",
        "that",
        "this",
        "from",
        "there",
        "about",
        "would",
        "could",
        "should",
        "chapter",
        "write",
        "create",
        "continue",
        "research",
        "character",
        "world",
        "into",
        "them",
    }
    docs = all_rows(
        "SELECT id,type,title,substr(body,1,220) AS excerpt FROM documents WHERE project_id=? ORDER BY updated_at DESC LIMIT 120",
        (pid,),
    )
    scored = []
    for doc in docs:
        title = doc["title"].lower()
        body = doc["excerpt"].lower()
        score = sum(3 if word in title else 1 if word in body else 0 for word in words)
        if score:
            scored.append((score, doc))
    return [doc for _, doc in sorted(scored, key=lambda x: -x[0])[:limit]]
