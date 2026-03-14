# Contract: Semanticist configuration

**Feature**: 003-semanticist-agent  
**Source**: Environment variables and optional `.env` (e.g. via python-dotenv)

## Variables

| Variable | Purpose | Example | Default (Ollama) |
|----------|---------|---------|-------------------|
| SEMANTIC_BULK_PROVIDER | Provider for bulk role | ollama | ollama |
| SEMANTIC_BULK_MODEL | Model id for bulk | codellama:7b | deepseek-coder:6.7b or codellama:7b |
| SEMANTIC_SYNTHESIS_PROVIDER | Provider for synthesis | ollama | ollama |
| SEMANTIC_SYNTHESIS_MODEL | Model id for synthesis | deepseek-r1 | deepseek-r1 or deepseek-coder:33b |
| SEMANTIC_BUDGET_CAP_TOTAL | Optional total token cap | 1000000 | None (no cap) |
| SEMANTIC_BUDGET_CAP_BULK | Optional bulk-phase token cap | 500000 | None |
| SEMANTIC_TRUNCATE_LINES | Max lines of code per module in bulk | 500 | 500 |
| OLLAMA_BASE_URL | Ollama API base (when provider=ollama) | http://localhost:11434 | http://localhost:11434 |

## Parsing

- **SEMANTIC_*_MODEL** may include provider prefix, e.g. `ollama:codellama:7b`. Parser splits on first `:`; if prefix matches provider, use remainder as model_id.
- Load order: `os.environ` (override) then `.env` from repo root or cwd.

## Validation

- If provider is `ollama`, model must be non-empty. If unset, use defaults from table.
- No hardcoded single model in code; defaults only when env is missing.
