# Phase 0: Research — Semanticist Agent

**Feature**: 003-semanticist-agent  
**Date**: 2025-03-13

## Resolved Decisions

### Token estimation (ContextWindowBudget)

- **Decision**: Prefer **tiktoken** when the chosen model uses a known encoding (e.g. `cl100k_base` for OpenAI-compatible). Fallback to **chars/4** heuristic when tiktoken is unavailable or model is Ollama (no standard encoding).
- **Rationale**: Tiktoken gives closer-to-real counts for API cost; for local Ollama, chars/4 is simple and avoids extra dependency for default path.
- **Alternatives considered**: Tokenizers from Hugging Face (heavier); fixed 4 chars/token only (chosen as fallback).

### Embedding model for purpose statements

- **Decision**: Use **sentence-transformers** with **all-MiniLM-L6-v2** (or similar lightweight sentence model) for embedding purpose statements. Short text (2–3 sentences) does not require code-specific embeddings for clustering quality; code-style embedders (e.g. UniXcoder) can be swapped later if needed.
- **Rationale**: Lightweight, good for short descriptive text, widely used; avoids large code-model dependency for Phase 3.
- **Alternatives considered**: OpenAI embeddings (cost, network); code-only embedders (overkill for purpose text); raw k-means on token counts (weaker semantics).

### Ollama API usage

- **Decision**: Use **Ollama HTTP API** (`POST /api/generate` or `/api/chat`) with a single client (e.g. `httpx`). Model name from config (e.g. `codellama:7b`). Same pattern as code-graph-rag: one client, different `model` per role.
- **Rationale**: Keeps implementation simple; no separate orchestrator process; easy to mock in tests.
- **Alternatives considered**: Ollama Python SDK (extra dep); subprocess call to `ollama run` (harder to mock).

### Where to store purpose and domain on ModuleNode

- **Decision**: **Extend ModuleNode** in place: `purpose_statement`, `domain_cluster` (already present); add `documentation_drift: Optional[bool]`, `docstring_snippet: Optional[str]`. Persist to same `.cartography/modules.json` (or overwrite with enriched modules) so downstream (Archivist, Navigator) see one source of truth.
- **Rationale**: Single module representation; no duplicate module lists; schema stays in one place.
- **Alternatives considered**: Separate “semantic layer” JSON keyed by path (more files, sync burden).

### Domain naming LLM role

- **Decision**: Use **semantic_bulk** model for the per-cluster domain name inference (many small calls). Keeps cost and latency low; naming does not require reasoning model.
- **Rationale**: Aligns with “cheap for bulk” principle; synthesis model reserved for Day-One only.
- **Alternatives considered**: Use synthesis model for naming (overkill); no LLM, use cluster centroid labels (weaker UX).

### Embedding cache location

- **Decision**: **Content-hash keyed cache** on disk under `.cartography/` (e.g. `.cartography/embedding_cache/` with files or a single SQLite/JSON store mapping hash → vector). Cache key = hash of normalized purpose text (e.g. strip + single spaces).
- **Rationale**: Re-runs without re-embedding unchanged purposes; same pattern as file_hashes in Surveyor.
- **Alternatives considered**: In-memory only (lost across runs); no cache (slower re-runs).

### Contradiction detection (Documentation Drift)

- **Decision**: Use a **simple heuristic** for “docstring contradicts purpose”: e.g. no overlap of significant terms, or an LLM-based comparison (one extra call). For Phase 3, **simple heuristic** (e.g. high Jaccard distance or keyword mismatch) is acceptable; optional LLM-based comparison can be added later.
- **Rationale**: Reduces cost and complexity; traceability (store both) already gives user the ability to compare.
- **Alternatives considered**: Always use LLM to compare (extra cost); never flag (weaker spec compliance).
