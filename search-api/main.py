from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import glob
import hashlib
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

app = FastAPI(title="Obsidian Vault Search API")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://obsidian-ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://obsidian-qdrant:6333")
VAULT_PATH = os.getenv("VAULT_PATH", "/vault")
MODEL = os.getenv("MODEL", "phi4")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
COLLECTION_NAME = "obsidian_vault"
VECTOR_SIZE = 768  # nomic-embed-text dimension

qdrant = QdrantClient(url=QDRANT_URL)


def get_embedding(text: str) -> List[float]:
    """Generate embedding via Ollama."""
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


def init_collection():
    """Ensure collection exists."""
    collections = qdrant.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        )

init_collection()


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search", response_model=List[SearchResult])
def search(req: SearchRequest):
    """Semantic search across the vault."""
    embedding = get_embedding(req.query)
    
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=req.limit,
        with_payload=True
    ).points
    
    out = []
    for r in results:
        if req.folder and not r.payload["path"].startswith(req.folder):
            continue
        out.append(SearchResult(
            score=r.score,
            path=r.payload["path"],
            title=r.payload["title"],
            snippet=r.payload["snippet"]
        ))
    
    return out


@app.post("/index")
def index_note(note: Note):
    """Index a single note into the vector DB."""
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
    """Scan vault and index all markdown files."""
    indexed = 0
    for filepath in glob.glob(os.path.join(VAULT_PATH, "**/*.md"), recursive=True):
        try:
            with open(filepath, "r") as f:
                content = f.read()
            
            title = os.path.basename(filepath).replace(".md", "")
            snippet = content[:500]
            
            embedding = get_embedding(content)
            note_id = int(hashlib.md5(filepath.encode()).hexdigest()[:8], 16)
            
            qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[PointStruct(
                    id=note_id,
                    vector=embedding,
                    payload={"path": filepath, "title": title, "snippet": snippet, "content": content}
                )]
            )
            indexed += 1
        except Exception as e:
            print(f"Failed to index {filepath}: {e}")
    
    return {"indexed": indexed}


@app.get("/stats")
def stats():
    collection = qdrant.get_collection(COLLECTION_NAME)
    return {"vectors_count": collection.points_count}
