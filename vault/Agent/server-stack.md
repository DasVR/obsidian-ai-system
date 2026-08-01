# Server Stack

Reference for everything running on the server.

## Services
| Service | URL / Port | Purpose |
|---------|-----------|---------|
| CouchDB | http://localhost:5984 | Obsidian LiveSync backend |
| Qdrant | http://localhost:6333 | Vector DB for note search |
| Ollama | http://localhost:11434 | Local LLM + embeddings |
| Search API | http://localhost:8093 | Note search + indexing |
| ntfy | https://ntfy.dasdev.net | Push notifications |
| Obsidian Sync | https://obsidian-sync.dasdev.net | LiveSync endpoint |

## Quick Commands
```bash
# restart obsidian-ai-system stack
cd /home/das/obsidian-ai-system
docker compose restart

# sync couchdb ↔ vault
python3 scripts/sync_bidirectional.py

# reindex search
curl -X POST http://localhost:8093/reindex
```

## Important Notes
- CouchDB config at `couchdb-config/local.ini`
- ntfy iOS needs `upstream-base-url: https://ntfy.sh` in server.yml
- Search API reads directly from CouchDB now, not filesystem
