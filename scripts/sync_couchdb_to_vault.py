#!/usr/bin/env python3
"""
CouchDB → Vault Sync for Obsidian LiveSync
Pulls assembled notes from CouchDB and writes them to the filesystem vault.
"""
import os
import json
import requests
import base64
from pathlib import Path

COUCHDB_URL = os.getenv("COUCHDB_URL", "http://localhost:5984")
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASSWORD = os.getenv("COUCHDB_PASSWORD", "")
COUCHDB_DB = os.getenv("COUCHDB_DB", "obsidian-livesync")
VAULT_PATH = os.getenv("VAULT_PATH", "/vault")

def couch_req(method, path, **kwargs):
    url = f"{COUCHDB_URL}/{path.lstrip('/')}"
    resp = requests.request(method, url, auth=(COUCHDB_USER, COUCHDB_PASSWORD), timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json()


def assemble_notes():
    """Fetch all docs from CouchDB, assemble chunks, return {path: content}."""
    resp = couch_req("GET", f"/{COUCHDB_DB}/_all_docs", params={"include_docs": "true", "limit": 10000})
    
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
        doc_id = doc.get("_id", "")
        path = doc.get("path", doc_id)
        
        parts = []
        for child_id in doc.get("children", []):
            chunk = chunks.get(child_id)
            if not chunk:
                continue
            data = chunk.get("data", "")
            if isinstance(data, str):
                # skip encrypted chunks
                if data.startswith("%=") or data.startswith("%$"):
                    continue
                parts.append(data)
            elif isinstance(data, dict) and "content" in data:
                parts.append(data["content"])
        
        content = "".join(parts)
        if content:
            notes[path] = content
    
    return notes


def sync_to_vault():
    vault = Path(VAULT_PATH)
    vault.mkdir(parents=True, exist_ok=True)
    
    notes = assemble_notes()
    written = 0
    
    for rel_path, content in notes.items():
        # Clean path — livesync uses forward slashes
        rel_path = rel_path.replace("\\", "/")
        file_path = vault / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Only write if content changed
        existing = ""
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
        
        if content != existing:
            file_path.write_text(content, encoding="utf-8")
            print(f"[SYNC] {rel_path}")
            written += 1
        else:
            print(f"[SKIP] {rel_path}")
    
    # Clean up files that no longer exist in couchdb
    existing_files = set(p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file())
    current_files = set(notes.keys())
    to_remove = existing_files - current_files
    
    for rel_path in to_remove:
        file_path = vault / rel_path
        if file_path.exists():
            file_path.unlink()
            print(f"[DEL] {rel_path}")
    
    # Remove empty dirs
    for dir_path in sorted(vault.rglob("*"), reverse=True):
        if dir_path.is_dir() and dir_path != vault and not any(dir_path.iterdir()):
            dir_path.rmdir()
            print(f"[RMDIR] {dir_path.relative_to(vault)}")
    
    print(f"\nSynced {written} files. Total notes: {len(notes)}")
    return written


if __name__ == "__main__":
    sync_to_vault()
