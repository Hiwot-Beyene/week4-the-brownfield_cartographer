# Contract: Embedding (Semanticist)

**Feature**: 003-semanticist-agent  
**Consumers**: `cluster_into_domains()` in `src/agents/semanticist.py`  
**Implementations**: sentence-transformers wrapper + content-hash cache

## Role

Embed **purpose statement** text (short string) into a fixed-size vector for k-means clustering. Cache MUST be content-hash keyed so unchanged text is not re-embedded.

## Interface (conceptual)

- **embed(text: str) -> list[float]**
  - Returns a vector of fixed dimension (e.g. 384 for all-MiniLM-L6-v2).
  - Implementation MUST check cache (key = hash of normalized text) first; on miss, compute and store.

- **embed_batch(texts: list[str]) -> list[list[float]]**
  - Optional; can be implemented as repeated embed() with cache. Batch may be more efficient for the underlying model.

## Cache

- **Key**: Content hash (e.g. SHA256 of text stripped and normalized).
- **Value**: Embedding vector (list of float or stored as binary).
- **Location**: `.cartography/embedding_cache/` or single file (e.g. SQLite or JSON). Format is implementation-defined; must survive process restart.

## Model

- Default: sentence-transformers **all-MiniLM-L6-v2** (or equivalent). Dimension 384.
- No env override required for Phase 3; can be added later.

## Testing

- Unit tests use **fixed embeddings** (e.g. stub vectors) so k-means output is deterministic; no real embedding model in unit tests. Cache can be tested with in-memory stub.
