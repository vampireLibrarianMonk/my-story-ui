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
        docs = con.execute("DELETE FROM documents WHERE project_id=?", (pid,)).rowcount
        con.execute("DELETE FROM conversations WHERE project_id=?", (pid,))
        con.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"documents": docs, "conversations": len(convo_ids)}


def create_document(pid: str, doc_type: str, title: str, body: str):
    did = new_id()
    with connect() as con:
        con.execute(
            "INSERT INTO documents(id,project_id,type,title,body) VALUES (?,?,?,?,?)",
            (did, pid, doc_type, title, body),
        )
    return one("SELECT * FROM documents WHERE id=?", (did,))


def update_document(did: str, title: str | None, body: str | None):
    with connect() as con:
        con.execute(
            """UPDATE documents SET title=COALESCE(?,title), body=COALESCE(?,body),
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (title, body, did),
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
