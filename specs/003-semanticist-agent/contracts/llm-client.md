# Contract: LLM Client (Semanticist)

**Feature**: 003-semanticist-agent  
**Consumers**: `src/agents/semanticist.py`  
**Implementations**: Ollama HTTP client (e.g. `src/llm/ollama_client.py`)

## Role

The Semanticist uses two **roles**: `semantic_bulk` and `semantic_synthesis`. Each role has a configured **provider** and **model** (from env). The client MUST accept a **role** or **model_id** per call so the orchestrator can use the correct model.

## Interface (conceptual)

- **complete(prompt: str, role: Literal["semantic_bulk", "semantic_synthesis"], max_tokens: int | None = None) -> str**
  - Sends the prompt to the configured model for that role.
  - Returns the generated text (no parsing inside the client).
  - Raises on network error, timeout, or provider error (caller catches and logs/skips).

- **Optional: stream** for future use (not required for Phase 3).

## Configuration

- **SEMANTIC_BULK_PROVIDER**, **SEMANTIC_BULK_MODEL**
- **SEMANTIC_SYNTHESIS_PROVIDER**, **SEMANTIC_SYNTHESIS_MODEL**

Example: `SEMANTIC_BULK_MODEL=ollama:codellama:7b` → provider=ollama, model_id=codellama:7b. Parser strips the `ollama:` prefix when calling Ollama.

## Ollama-specific

- **Endpoint**: `http://localhost:11434/api/generate` (or configurable base URL).
- **Body**: `{ "model": "<model_id>", "prompt": "<prompt>", "stream": false }`.
- **Response**: JSON with `"response"` field containing the generated text.
- **Timeout**: Configurable (e.g. 60s bulk, 120s synthesis).

## Testing

- Unit tests MUST mock this interface (e.g. return fixed string or raise); no real HTTP in unit tests.
