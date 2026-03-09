# Quickstart: Semanticist Agent (Phase 3)

**Feature**: 003-semanticist-agent  
**Prerequisites**: Phase 1 (Surveyor) and Phase 2 (Hydrologist) outputs in `.cartography/`

## 1. Ensure Surveyor and Hydrologist have run

You need:

- `.cartography/module_graph.json` or `.cartography/modules.json`
- `.cartography/lineage_graph.json`
- `.cartography/survey_summary.json` (or equivalent)

Run the full pipeline (Surveyor → Hydrologist) first, or point the Semanticist at an existing `.cartography/` directory.

## 2. Configure LLM (env)

Set at least the synthesis model if using Ollama:

```bash
export SEMANTIC_BULK_MODEL=ollama:codellama:7b
export SEMANTIC_SYNTHESIS_MODEL=ollama:deepseek-r1
```

Or create a `.env` in the repo root:

```env
SEMANTIC_BULK_PROVIDER=ollama
SEMANTIC_BULK_MODEL=codellama:7b
SEMANTIC_SYNTHESIS_PROVIDER=ollama
SEMANTIC_SYNTHESIS_MODEL=deepseek-r1
```

Defaults (if unset): bulk = `deepseek-coder:6.7b` or `codellama:7b`, synthesis = `deepseek-r1` (or `deepseek-coder:33b`). Choose based on local hardware.

## 3. Run Semanticist

From repo root:

```bash
uv run python -m src.agents.semanticist --repo . --artifacts-dir .cartography
```

Or via orchestrator (when integrated):

```bash
uv run python -m src.cli analyze /path/to/repo
```

## 4. Outputs

The Semanticist run writes enriched modules back to `.cartography/modules.json` (same file as Surveyor; fields added by Semanticist).

- **.cartography/modules.json** — Updated with `purpose_statement`, `domain_cluster`, `documentation_drift`, `docstring_snippet`.
- **.cartography/domain_architecture_map.json** — Module path → domain name; cluster → domain name.
- **.cartography/day_one_answers.json** — Five answers with citations (file, line).
- **.cartography/embedding_cache/** — Cache for purpose-statement embeddings (reused on re-run).

## 5. Unit tests (no real Ollama)

```bash
uv run pytest tests/unit/test_context_window_budget.py tests/unit/test_generate_purpose_statement.py tests/unit/test_cluster_into_domains.py tests/unit/test_answer_day_one_questions.py -v
```

All use mocks; no network calls.

## 6. Manual e2e with Ollama

1. Start Ollama and pull models: `ollama pull codellama:7b`, `ollama pull deepseek-r1`.
2. Run Surveyor + Hydrologist on a small repo (or use existing artifacts).
3. Set env (step 2) and run Semanticist (step 3).
4. Inspect `.cartography/day_one_answers.json` and `modules.json` for purpose/domain/drift.

No separate e2e script is required; the same CLI entrypoint with real config is the e2e. Document in README: “For a quick e2e, run the pipeline against a small repo with Ollama running and the env vars set.”
