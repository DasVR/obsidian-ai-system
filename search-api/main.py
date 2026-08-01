from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import glob
import hashlib
import json
import base64
import re
import time
import requests
from urllib.parse import quote
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

app = FastAPI(title="Obsidian Vault Search API")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://obsidian-ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://obsidian-qdrant:6333")
VAULT_PATH = os.getenv("VAULT_PATH", "/vault")
COUCHDB_URL = os.getenv("COUCHDB_URL", "http://obsidian-couchdb:5984")
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASSWORD = os.getenv("COUCHDB_PASSWORD", "")
COUCHDB_DB = os.getenv("COUCHDB_DB", "obsidian-livesync")
MODEL = os.getenv("MODEL", "phi4")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
COLLECTION_NAME = "obsidian_vault"
VECTOR_SIZE = 768

qdrant = QdrantClient(url=QDRANT_URL)


def _couch_auth() -> tuple:
    return (COUCHDB_USER, COUCHDB_PASSWORD)


def _couch_req(method: str, path: str, **kwargs) -> dict:
    url = f"{COUCHDB_URL}/{path.lstrip('/')}"
    resp = requests.request(method, url, auth=_couch_auth(), timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _decode_livesync_doc(doc: dict, chunks_map: dict) -> Optional[dict]:
    doc_id = doc.get("_id", "")
    if doc_id.startswith("h:") or doc_id.startswith("_") or doc_id.startswith("-"):
        return None

    content_parts = []
    for child_id in doc.get("children", []):
        chunk = chunks_map.get(child_id)
        if not chunk:
            continue
        data = chunk.get("data", "")
        if isinstance(data, str):
            content_parts.append(data)
        elif isinstance(data, dict) and "content" in data:
            content_parts.append(data["content"])

    assembled = "".join(content_parts)
    return {
        "path": doc_id,
        "content": assembled,
        "mtime": doc.get("mtime", 0),
        "size": doc.get("size", len(assembled)),
    }


def _all_docs_with_content() -> List[dict]:
    docs = []
    try:
        resp = _couch_req("GET", f"/{COUCHDB_DB}/_all_docs", params={"include_docs": "true", "limit": 10000})
        chunks_map = {}
        parent_docs = []
        for row in resp.get("rows", []):
            doc = row.get("doc")
            if not doc:
                continue
            doc_id = doc.get("_id", "")
            if doc_id.startswith("h:"):
                chunks_map[doc_id] = doc
            elif not doc_id.startswith("_") and not doc_id.startswith("-"):
                parent_docs.append(doc)
        for doc in parent_docs:
            decoded = _decode_livesync_doc(doc, chunks_map)
            if decoded and decoded["content"]:
                docs.append(decoded)
    except Exception as e:
        print(f"CouchDB fetch failed: {e}")
    return docs


def _get_doc_from_couchdb(doc_id: str) -> Optional[dict]:
    try:
        parent = _couch_req("GET", f"/{COUCHDB_DB}/{quote(doc_id, safe='')}")
        chunks_map = {}
        for child_id in parent.get("children", []):
            try:
                chunk = _couch_req("GET", f"/{COUCHDB_DB}/{quote(child_id, safe='')}")
                chunks_map[child_id] = chunk
            except Exception:
                pass
        decoded = _decode_livesync_doc(parent, chunks_map)
        return decoded
    except Exception as e:
        print(f"Failed to fetch {doc_id}: {e}")
        return None


def _write_doc_to_couchdb(doc_id: str, content: str, ctime: Optional[int] = None, mtime: Optional[int] = None) -> dict:
    now = int(time.time() * 1000)
    ctime = ctime or now
    mtime = mtime or now
    size = len(content.encode("utf-8"))

    chunk_id = f"h:{hashlib.sha256((doc_id + content).encode()).hexdigest()[:16]}"

    existing_rev = None
    try:
        existing = _couch_req("GET", f"/{COUCHDB_DB}/{quote(doc_id, safe='')}")
        existing_rev = existing.get("_rev")
    except Exception:
        pass

    chunk_doc = {"_id": chunk_id, "data": content, "type": "leaf"}
    try:
        existing_chunk = _couch_req("GET", f"/{COUCHDB_DB}/{quote(chunk_id, safe='')}")
        chunk_doc["_rev"] = existing_chunk["_rev"]
    except Exception:
        pass

    _couch_req("PUT", f"/{COUCHDB_DB}/{quote(chunk_id, safe='')}", json=chunk_doc)

    parent_doc = {
        "_id": doc_id,
        "path": doc_id,
        "children": [chunk_id],
        "ctime": ctime,
        "mtime": mtime,
        "size": size,
        "type": "plain",
        "eden": {}
    }
    if existing_rev:
        parent_doc["_rev"] = existing_rev

    return _couch_req("PUT", f"/{COUCHDB_DB}/{quote(doc_id, safe='')}", json=parent_doc)


def get_embedding(text: str) -> List[float]:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text[:4000]},
            timeout=60
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")


# ─── Qdrant ───────────────────────────────────────────────────────────

def init_collection():
    collections = qdrant.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        )

init_collection()


# ─── API models ──────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    folder: Optional[str] = None


class SearchResult(BaseModel):
    score: float
    path: str
    title: str
    snippet: str


class Note(BaseModel):
    path: str
    content: str


class NoteUpdate(BaseModel):
    content: str


# ─── Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    couch_ok = False
    try:
        _couch_req("GET", "/_up")
        couch_ok = True
    except Exception:
        pass
    return {"status": "ok", "couchdb": couch_ok, "db": COUCHDB_DB}


@app.get("/notes")
def list_notes(folder: Optional[str] = None):
    docs = _all_docs_with_content()
    out = []
    for doc in docs:
        path = doc["path"]
        if folder and not path.startswith(folder):
            continue
        out.append({"path": path, "title": os.path.basename(path).replace(".md", ""), "size": doc["size"], "mtime": doc["mtime"]})
    return out


@app.get("/notes/{path:path}")
def read_note(path: str):
    if not path.endswith(".md"):
        path = path + ".md"
    decoded = _get_doc_from_couchdb(path)
    if not decoded:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")
    return {"path": decoded["path"], "content": decoded["content"], "size": decoded["size"], "mtime": decoded["mtime"]}


@app.post("/notes/{path:path}")
def create_or_update_note(path: str, note: NoteUpdate):
    if not path.endswith(".md"):
        path = path + ".md"

    result = _write_doc_to_couchdb(path, note.content)

    try:
        title = os.path.basename(path).replace(".md", "")
        snippet = note.content[:500]
        embedding = get_embedding(note.content)
        note_id = int(hashlib.md5(path.encode()).hexdigest()[:8], 16)
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(
                id=note_id,
                vector=embedding,
                payload={"path": path, "title": title, "snippet": snippet, "content": note.content}
            )]
        )
    except Exception as e:
        print(f"Index update failed for {path}: {e}")

    return {"saved": path, "rev": result.get("rev"), "ok": True}


@app.delete("/notes/{path:path}")
def delete_note(path: str):
    if not path.endswith(".md"):
        path = path + ".md"

    try:
        doc = _couch_req("GET", f"/{COUCHDB_DB}/{quote(path, safe='')}")
        rev = doc.get("_rev")

        for child_id in doc.get("children", []):
            try:
                chunk = _couch_req("GET", f"/{COUCHDB_DB}/{quote(child_id, safe='')}")
                _couch_req("DELETE", f"/{COUCHDB_DB}/{quote(child_id, safe='')}?rev={chunk['_rev']}")
            except Exception:
                pass

        _couch_req("DELETE", f"/{COUCHDB_DB}/{quote(path, safe='')}?rev={rev}")

        try:
            note_id = int(hashlib.md5(path.encode()).hexdigest()[:8], 16)
            qdrant.delete(collection_name=COLLECTION_NAME, points_selector=[note_id])
        except Exception:
            pass

        return {"deleted": path, "ok": True}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Note not found or delete failed: {e}")


@app.post("/search", response_model=List[SearchResult])
def search(req: SearchRequest):
    embedding = get_embedding(req.query)
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME, query=embedding, limit=req.limit, with_payload=True
    ).points

    out = []
    for r in results:
        if req.folder and not r.payload["path"].startswith(req.folder):
            continue
        out.append(SearchResult(score=r.score, path=r.payload["path"], title=r.payload["title"], snippet=r.payload["snippet"]))
    return out


@app.post("/index")
def index_note(note: Note):
    title = os.path.basename(note.path).replace(".md", "")
    snippet = note.content[:500]
    embedding = get_embedding(note.content)
    note_id = int(hashlib.md5(note.path.encode()).hexdigest()[:8], 16)

    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(
            id=note_id,
            vector=embedding,
            payload={"path": note.path, "title": title, "snippet": snippet, "content": note.content}
        )]
    )
    return {"indexed": note.path, "id": note_id}


@app.post("/reindex")
def reindex_all():
    docs = _all_docs_with_content()
    indexed = 0
    for doc in docs:
        try:
            path = doc["path"]
            content = doc["content"]
            title = os.path.basename(path).replace(".md", "")
            snippet = content[:500]
            embedding = get_embedding(content)
            note_id = int(hashlib.md5(path.encode()).hexdigest()[:8], 16)
            qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[PointStruct(
                    id=note_id,
                    vector=embedding,
                    payload={"path": path, "title": title, "snippet": snippet, "content": content}
                )]
            )
            indexed += 1
        except Exception as e:
            print(f"Failed to index {doc.get('path')}: {e}")
    return {"indexed": indexed, "source": "couchdb", "db": COUCHDB_DB}


@app.post("/sync")
def sync_changes():
    return reindex_all()


@app.get("/stats")
def stats():
    collection = qdrant.get_collection(COLLECTION_NAME)
    return {"vectors_count": collection.points_count, "source": "couchdb"}
