from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage as store
from .intent import (
    MODE_LABELS,
    MODES,
    WIDGETS,
    build_references,
    build_system_prompt,
    build_turns,
    infer_mode,
)
from .providers import ProviderError, availability, completion

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    store.setup()
    yield


app = FastAPI(title="Prompt Nexus", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/bootstrap")
def bootstrap():
    projects = store.all_rows("SELECT * FROM projects ORDER BY created_at DESC")
    return {
        "projects": projects,
        "providers": availability(),
        "modes": MODE_LABELS,
        "widgets": WIDGETS,
    }


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.post("/api/projects", status_code=201)
def new_project(payload: ProjectInput):
    return store.create_project(payload.name.strip())


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.patch("/api/projects/{project_id}")
def rename_project(project_id: str, payload: ProjectUpdate):
    require_project(project_id)
    return store.rename_project(project_id, payload.name.strip())


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, confirm_name: str = Query(default="")):
    """Destructive. The caller must echo the exact project name; the last project cannot be removed."""
    p = require_project(project_id)
    if confirm_name != p["name"]:
        raise HTTPException(400, "Type the exact project name to confirm deletion.")
    if len(store.all_rows("SELECT id FROM projects")) <= 1:
        raise HTTPException(400, "The last remaining project cannot be deleted.")
    return {"deleted": project_id, **store.delete_project(project_id)}


@app.get("/api/projects/{project_id}/overview")
def project_overview(project_id: str):
    require_project(project_id)
    return {
        "documents": store.all_rows(
            "SELECT id,project_id,type,title,substr(body,1,160) AS excerpt,updated_at FROM documents WHERE project_id=? ORDER BY updated_at DESC",
            (project_id,),
        ),
        "conversations": store.all_rows(
            "SELECT * FROM conversations WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ),
    }


class DocumentInput(BaseModel):
    project_id: str
    type: Literal["chapter", "character", "world", "research", "note"]
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=200000)
    tags: list[str] = Field(default_factory=list, max_length=40)
    metadata: dict = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, max_length=200000)
    tags: list[str] | None = Field(default=None, max_length=40)
    metadata: dict | None = None


@app.post("/api/documents", status_code=201)
def new_document(payload: DocumentInput):
    require_project(payload.project_id)
    return store.create_document(
        payload.project_id,
        payload.type,
        payload.title.strip(),
        payload.body,
        payload.tags,
        payload.metadata,
    )


@app.get("/api/documents/{document_id}")
def get_document(document_id: str):
    return require_document(document_id)


@app.patch("/api/documents/{document_id}")
def patch_document(document_id: str, payload: DocumentUpdate):
    require_document(document_id)
    return store.update_document(
        document_id, payload.title, payload.body, payload.tags, payload.metadata
    )


@app.get("/api/projects/{project_id}/tags")
def list_tags(project_id: str):
    require_project(project_id)
    return {"tags": store.project_tags(project_id)}


@app.get("/api/projects/{project_id}/documents")
def documents_by_tags(
    project_id: str, tags: str = Query(default=""), match: Literal["any", "all"] = "any"
):
    """Filter a project's documents by tag. tags is a comma-separated list."""
    require_project(project_id)
    wanted = [t for t in tags.split(",") if t.strip()]
    return {"documents": store.documents_by_tags(project_id, wanted, match)}


@app.put("/api/documents/{document_id}/image", status_code=201)
async def upload_document_image(document_id: str, request: Request):
    """Attach a reference image to a document. Body is the raw image bytes; type from Content-Type."""
    require_document(document_id)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in store.IMAGE_TYPES:
        raise HTTPException(
            415, f"Unsupported image type. Allowed: {sorted(store.IMAGE_TYPES)}."
        )
    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty image.")
    if len(data) > store.MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds the 8 MB limit.")
    return store.save_document_image(document_id, data, content_type)


@app.get("/api/documents/{document_id}/image")
def get_document_image(document_id: str):
    found = store.document_image_path(document_id)
    if not found:
        raise HTTPException(404, "No image for this document.")
    path, content_type = found
    return FileResponse(path, media_type=content_type)


@app.delete("/api/documents/{document_id}/image")
def remove_document_image(document_id: str):
    require_document(document_id)
    return store.delete_document_image(document_id)


@app.get("/api/projects/{project_id}/context")
def context(project_id: str, q: str = "", limit: int = 6):
    require_project(project_id)
    return {
        "mode": infer_mode(q),
        "related": store.related(project_id, q, min(max(limit, 1), 10)),
    }


@app.get("/api/projects/{project_id}/search")
def search(project_id: str, q: str = ""):
    require_project(project_id)
    if not q.strip():
        return {"documents": [], "conversations": []}
    return store.search(project_id, q.strip()[:200])


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: str):
    c = require_conversation(conversation_id)
    return {"conversation": c, "messages": store.conversation_messages(conversation_id)}


class ChatInput(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1, max_length=50000)
    mode: str = "auto"
    provider: Literal["demo", "arc", "bedrock"] = "demo"
    conversation_id: str | None = None
    context_ids: list[str] = Field(default_factory=list, max_length=12)
    options: dict[str, str] = Field(default_factory=dict)
    assist: bool = False


@app.post("/api/chat")
async def chat(payload: ChatInput):
    require_project(payload.project_id)
    mode = infer_mode(payload.prompt) if payload.mode == "auto" else payload.mode
    if mode not in MODES:
        raise HTTPException(422, "Invalid writing mode.")
    if not availability()[payload.provider]["ready"]:
        raise HTTPException(400, f"{payload.provider} is not configured.")
    if payload.conversation_id:
        c = require_conversation(payload.conversation_id)
        if c["project_id"] != payload.project_id:
            raise HTTPException(400, "Conversation belongs to a different project.")
    else:
        c = store.create_conversation(
            payload.project_id, payload.prompt.strip().splitlines()[0][:75]
        )

    valid_ids = []
    docs = []
    for did in dict.fromkeys(payload.context_ids):
        d = require_document(did)
        if d["project_id"] != payload.project_id:
            raise HTTPException(400, "Document belongs to a different project.")
        valid_ids.append(did)
        docs.append(d)
    opts = {
        key: value[:200]
        for key, value in payload.options.items()
        if isinstance(key, str) and isinstance(value, str) and len(key) < 50
    }
    # Never silently mutate project documents. Widget choices become AI constraints only.
    references = build_references(docs)
    system = build_system_prompt(mode, opts, references, assist=payload.assist)
    history = store.conversation_messages(c["id"])
    turns = build_turns(system, history, payload.prompt)
    user_msg = store.save_message(
        c["id"], "user", payload.prompt, mode, payload.provider, valid_ids, opts
    )
    try:
        answer = await completion(payload.provider, turns)
    except ProviderError as exc:
        # Preserve user input and avoid fabricating an assistant reply.
        raise HTTPException(
            502,
            detail={
                "error": str(exc),
                "conversation_id": c["id"],
                "message_id": user_msg["id"],
            },
        ) from exc
    assistant = store.save_message(
        c["id"], "assistant", answer, mode, payload.provider, valid_ids, opts
    )
    return {
        "conversation_id": c["id"],
        "mode": mode,
        "user_message": user_msg,
        "assistant_message": assistant,
    }


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str):
    p = require_project(project_id)
    docs = store.all_rows(
        "SELECT * FROM documents WHERE project_id=? ORDER BY updated_at", (project_id,)
    )
    conversations = store.all_rows(
        "SELECT * FROM conversations WHERE project_id=? ORDER BY created_at",
        (project_id,),
    )
    for c in conversations:
        c["messages"] = store.conversation_messages(c["id"])
    blob = json.dumps(
        {
            "schema_version": 1,
            "project": p,
            "documents": docs,
            "conversations": conversations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return Response(
        content=blob,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="prompt-nexus-{project_id}.json"'
        },
    )


def require_project(pid):
    p = store.one("SELECT * FROM projects WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Project not found.")
    return p


def require_document(did):
    d = store.one("SELECT * FROM documents WHERE id=?", (did,))
    if not d:
        raise HTTPException(404, "Document not found.")
    return d


def require_conversation(cid):
    c = store.one("SELECT * FROM conversations WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Conversation not found.")
    return c
