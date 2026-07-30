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

## Status

Building incrementally. See commits for phase breakdown.

---
