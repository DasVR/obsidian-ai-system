# Obsidian AI System

Self-hosted Obsidian vault with real-time multi-device sync, local AI-powered daily note enhancement, and vectorized knowledge base for agent-assisted research.

## Components

- **CouchDB** — Real-time sync engine for Obsidian LiveSync plugin
- **Ollama** — Local AI (CPU-based) for note enhancement and embeddings
- **Note Enhancer** — Processes daily notes with AI, restructures, adds creativity
- **Qdrant** — Vector database for semantic search across the entire vault
- **Vector Indexer** — Watches vault changes and indexes into Qdrant
- **FastAPI** — Search endpoint for agent queries

## Architecture

```
Phone/Laptop (Obsidian + LiveSync)
         │
         ▼
CouchDB ←──→ Vault Storage (.md files)
         │
    Ollama (AI + Embeddings)
         │
Enhancer + Indexer + Qdrant
```

## Quick Start

```bash
cd /opt/stacks/obsidian-ai-system
docker compose up -d
```

## Vault Structure

```
vault/
├── Daily/                    # Daily notes — auto-enhanced by AI
├── Projects/
│   ├── Portfolio/            # Active work
│   ├── Server/               # Homelab docs
│   └── ...
├── Research/                 # Things you looked up, learned
├── Creativity/              # Ideas, lyrics, sketches, prompts
├── People/                    # Contacts, context, relationships
├── Resources/               # Bookmarks, tools, references
├── Templates/               # Daily note template, project template
└── Agent/                   # Stuff for Finn
    ├── context.md            # "Finn, here's what I'm working on rn"
    ├── preferences.md        # "I hate long paragraphs" etc.
    └── skills/               # Extracted learnings → reusable
```

## Status

Building incrementally. See commits for phase breakdown.

### Phase 1: CouchDB + Vault ✅
- CouchDB running on port 5984
- CORS enabled for LiveSync
- `obsidian-livesync` database created
- Vault folder structure created

### Phase 2: Ollama (In Progress)
### Phase 3: Note Enhancer (Pending)
### Phase 4: Vector Search (Pending)
### Phase 5: Caddy Proxy (Pending)

---
