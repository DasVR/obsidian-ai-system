#!/usr/bin/env python3
"""
Bidirectional CouchDB ⇄ Vault Sync for Obsidian LiveSync
- Pulls assembled notes from CouchDB → vault
- Pushes vault files → CouchDB as livesync chunks
- Keeps both sources in sync
"""
import os
import json
import hashlib
import requests
from urllib.parse import quote
from pathlib import Path

COUCHDB_URL = os.getenv("COUCHDB_URL", "http://localhost:5984")
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASSWORD = os.getenv("COUCHDB_PASSWORD", "")
COUCHDB_DB = os.getenv("COUCHDB_DB", "obsidian-livesync")
VAULT_PATH = os.getenv("VAULT_PATH", "/vault")
CHUNK_SIZE = 512000  # ~500KB chunks

def couch_req(method, path, **kwargs):
    url = f"{COUCHDB_URL}/{path.lstrip('/')}"
    resp = requests.request(method, url, auth=(COUCHDB_USER, COUCHDB_PASSWORD), timeout=60, **kwargs)
    resp.raise_for_status()
    return resp.json()


def chunk_text(text, size=CHUNK_SIZE):
    """Split text into chunks. LiveSync uses roughly 1MB-ish chunks."""
    return [text[i:i+size] for i in range(0, len(text), size)]


def make_chunk_id():
    """Simple random-ish chunk id."""
    import random
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "h:+" + "".join(random.choices(chars, k=15))


def upload_file_to_couchdb(rel_path, content):
    """Write/update a file document and its chunks in CouchDB."""
    doc_id = rel_path  # livesync uses path as doc id usually
    
    # Get existing doc if any
    try:
        old_doc = couch_req("GET", f"/{COUCHDB_DB}/{quote(doc_id, safe='')}")
        old_rev = old_doc.get("_rev")
        old_children = old_doc.get("children", [])
    except Exception:
        old_rev = None
        old_children = []
    
    # Delete old chunks if any
    for child_id in old_children:
        try:
            child = couch_req("GET", f"/{COUCHDB_DB}/{quote(child_id, safe='')}")
            couch_req("DELETE", f"/{COUCHDB_DB}/{quote(child_id, safe='')}?rev={child['_rev']}")
        except Exception as e:
            print(f"[WARN] Could not delete old chunk {child_id}: {e}")
    
    # Create new chunks
    chunks = chunk_text(content)
    child_ids = []
    for chunk in chunks:
        child_id = make_chunk_id()
        child_doc = {
            "_id": child_id,
            "data": chunk,
            "type": "leaf"
        }
        couch_req("PUT", f"/{COUCHDB_DB}/{quote(child_id, safe='')}", json=child_doc)
        child_ids.append(child_id)
    
    # Create/update parent doc
    parent_doc = {
        "_id": doc_id,
        "path": rel_path,
        "children": child_ids,
        "ctime": 0,
        "mtime": 0,
        "size": len(content.encode("utf-8")),
        "type": "plain",
        "eden": {}
    }
    
    if old_rev:
        parent_doc["_rev"] = old_rev
    
    couch_req("PUT", f"/{COUCHDB_DB}/{quote(doc_id, safe='')}", json=parent_doc)
    print(f"[UPLOAD] {rel_path}")


def assemble_notes():
    """Fetch all docs from CouchDB, assemble chunks, return {path: content}."""
    try:
        resp = couch_req("GET", f"/{COUCHDB_DB}/_all_docs", params={"include_docs": "true", "limit": 10000})
    except Exception as e:
        print(f"CouchDB fetch failed: {e}")
        return {}
    
    chunks = {}
    parents = []
    
    for row in resp.get("rows", []):
        doc = row.get("doc")
        if not doc:
            continue
        doc_id = doc.get("_id", "")
        if doc_id.startswith("h:"):
            chunks[doc_id] = doc
        elif not doc_id.startswith("_") and not doc_id.startswith("-"):
            parents.append(doc)
    
    notes = {}
    for doc in parents:
        path = doc.get("path", doc.get("_id", ""))
        
        parts = []
        for child_id in doc.get("children", []):
            chunk = chunks.get(child_id)
            if not chunk:
                continue
            data = chunk.get("data", "")
            if isinstance(data, str):
                if data.startswith("%=") or data.startswith("%$"):
                    continue  # encrypted, skip
                parts.append(data)
            elif isinstance(data, dict) and "content" in data:
                parts.append(data["content"])
        
        content = "".join(parts)
        if content:
            notes[path] = content
    
    return notes


def sync_bidirectional():
    vault = Path(VAULT_PATH)
    vault.mkdir(parents=True, exist_ok=True)
    
    # Pull from CouchDB
    couch_notes = assemble_notes()
    written_down = 0
    for rel_path, content in couch_notes.items():
        rel_path = rel_path.replace("\\", "/")
        file_path = vault / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        existing = ""
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
        
        if content != existing:
            file_path.write_text(content, encoding="utf-8")
            print(f"[DOWN] {rel_path}")
            written_down += 1
        else:
            print(f"[SKIP DOWN] {rel_path}")
    
    # Build vault file list
    vault_files = set(p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file())
    
    # Push from vault to CouchDB
    for rel_path in vault_files:
        content = (vault / rel_path).read_text(encoding="utf-8")
        if rel_path not in couch_notes or couch_notes.get(rel_path) != content:
            upload_file_to_couchdb(rel_path, content)
        else:
            print(f"[SKIP UP] {rel_path}")
    
    # Refresh couch_notes after uploads
    couch_notes = assemble_notes()
    
    # Delete server files removed from couchdb
    to_remove_files = vault_files - set(couch_notes.keys())
    for rel_path in to_remove_files:
        file_path = vault / rel_path
        if file_path.exists():
            file_path.unlink()
            print(f"[DEL] {rel_path}")
    
    # Remove empty dirs
    for dir_path in sorted(vault.rglob("*"), reverse=True):
        if dir_path.is_dir() and dir_path != vault and not any(dir_path.iterdir()):
            dir_path.rmdir()
            print(f"[RMDIR] {dir_path.relative_to(vault)}")
    
    print(f"\nSynced down {written_down} files. Pushed up {len(vault_files - set(couch_notes.keys()))} new.")


if __name__ == "__main__":
    sync_bidirectional()
