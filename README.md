# Obsidian AI System

Self-hosted Obsidian vault with real-time multi-device sync, local AI-powered daily note enhancement, and vectorized knowledge base for agent-assisted research.

## Quick Start

```bash
cd /home/das/obsidian-ai-system
sudo docker compose up -d
```

## Components

| Service | Port | Purpose |
|---------|------|---------|
| CouchDB | 5984 | Real-time sync for Obsidian LiveSync |
| Ollama | 11434 | Local AI (phi4 for generation, nomic-embed-text for embeddings) |
| Qdrant | 6333 | Vector database for semantic search |
| Search API | 8093 | FastAPI endpoint for agent queries |
| Enhancer | — | Docker image for AI daily note processing |

## Architecture

```
Phone/Laptop (Obsidian + LiveSync plugin)
         │
         ▼
Cloudflare Tunnel → Caddy → CouchDB (obsidian-sync.dasdev.net)
         │
    Vault Storage (.md files in ./vault/)
         │
    Ollama (phi4 + nomic-embed-text)
         │
    Search API + Qdrant (semantic search)
         │
    Enhancer (AI daily note enhancement)
```

## Vault Structure

```
vault/
├── Daily/                    # Daily notes — auto-enhanced by AI
├── Projects/
│   ├── Portfolio/            # Active work
│   └── Server/               # Homelab docs
├── Research/                 # Things you looked up, learned
├── Creativity/              # Ideas, lyrics, sketches
├── People/                    # Contacts, context
├── Resources/               # Bookmarks, tools
├── Templates/               # Note templates
└── Agent/                   # Stuff for Finn
    ├── context.md            # Persistent context for agent
    ├── preferences.md        # User preferences
    └── skills/               # Extracted learnings
```

## Setup

### 1. Install Obsidian + LiveSync Plugin
- Download Obsidian: https://obsidian.md
- Install "Self-hosted LiveSync" plugin
- Configure:
  - URL: `https://obsidian-sync.dasdev.net`
  - Database: `obsidian-livesync`
  - Username: `admin`
  - Password: (see `.env`)

### 2. Sync Your First Note
- Create a daily note in `vault/Daily/`
- The sync plugin will push it to CouchDB
- Other devices will pull it automatically

### 3. Semantic Search
```bash
# Reindex all notes
curl -X POST http://localhost:8093/reindex

# Search
curl -X POST http://localhost:8093/search \
  -H "Content-Type: application/json" \
  -d '{"query":"what was I stressed about","limit":5}'
```

### 4. AI Enhancement
```bash
# Run once (takes ~2-4 min on CPU for phi4)
docker compose run --rm enhancer

# Or let it run on a schedule via cron
cd /home/das/obsidian-ai-system && docker compose run --rm enhancer >> /var/log/enhancer.log 2>&1
```

## Agent Integration

I can query your vault via the Search API. Example skill call:
```
User: "What was I working on last week?"
→ Search API: POST /search {"query":"working on last week","limit":5}
→ Returns: Relevant daily notes with snippets
→ I respond with actual context
```

## Known Limitations

- **AI enhancement speed**: phi4 takes ~2-4 minutes per daily note on CPU. This is expected on your hardware. For faster enhancement, use OpenRouter API (see `enhancer/enhancer.py` — set `OLLAMA_URL` to API endpoint).
- **DNS propagation**: `obsidian-sync.dasdev.net` may take a few minutes to resolve after Cloudflare tunnel restart.
- **Embedding speed**: nomic-embed-text is fast (~1-2s per note), so reindexing is quick.

## Cost

**$0/month** — everything runs locally on your existing server.

## Status

| Phase | Status |
|-------|--------|
| Phase 1: CouchDB + Vault | ✅ |
| Phase 2: Ollama (phi4 + nomic-embed-text) | ✅ |
| Phase 3: Note Enhancer | ✅ (slow on CPU, functional) |
| Phase 4: Vector Search (Qdrant + API) | ✅ |
| Phase 5: Caddy + Cloudflare Tunnel | ✅ |
| Phase 6: End-to-end Test | ✅ |

## Next Steps

- Install Obsidian + LiveSync on your devices
- Drop context into `vault/Agent/context.md`
- Tell me to create the `obsidian-vault-query` skill
- Optional: Add OpenRouter API key for faster AI enhancement

---
