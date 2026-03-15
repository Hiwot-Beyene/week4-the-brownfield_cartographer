# Cartographer Workflows and Edge Cases

This document describes typical usage workflows and how to handle edge cases (e.g. shallow clones, monorepos) when running the Brownfield Cartographer.

## Typical Workflows

### Cold start (first-time analysis)

1. Point Cartographer at a repo (local path or GitHub URL):
   ```bash
   python -m src.cli analyze https://github.com/owner/repo
   ```
2. Wait for the pipeline: Surveyor → Hydrologist → Semanticist → Archivist.
3. Outputs appear under `.cartography/`: `CODEBASE.md`, `onboarding_brief.md`, `lineage_graph.json`, `semantic_index/`, `cartography_trace.jsonl`.
4. Use `query` to ask the Navigator:
   ```bash
   python -m src.cli query . "Where is the revenue calculation?"
   ```

### Re-run (incremental)

- With `analyze` (default), only files changed since the last run are re-analyzed when a prior analysis exists for the same repo. Use `--no-incremental` to force a full re-scan.

### Lineage-only

- To run only Surveyor + Hydrologist (no Semanticist/Archivist), use the `lineage` subcommand or a custom flow. The main `analyze` command always runs all four stages.

### Programmatic use (Navigator tools)

- Scripts or IDE plugins can call Navigator tools without the full agent loop:
  ```python
  from pathlib import Path
  from src.agents.navigator import find_implementation, trace_lineage, blast_radius, explain_module

  repo_root = Path(".")
  artifacts_dir = Path(".cartography")
  out = find_implementation(analysis_id=1, concept="auth", repo_root=repo_root, artifacts_dir=artifacts_dir)
  # out["answer"], out["citations"], out["confidence"]
  ```

## Edge Cases

### Shallow clones

- When cloning with `--depth 1` (default), git history is limited. **Git velocity** (commits per file, high-velocity files) may be empty or incomplete. CODEBASE.md and the onboarding brief will note “no git history for counts” when appropriate. For accurate velocity, clone with `--depth 0` (full history) or a larger depth.

### Monorepos

- Cartographer treats the resolved repo root as one codebase. For a monorepo, run `analyze` with the repo root; the module graph and lineage will span the whole tree. To analyze a subdirectory only, run from a workspace that contains only that subtree (e.g. a sparse checkout or a path that is the root of the sub-project).

### Individual agent failures

- If Surveyor fails, no later stages run; you get no artifacts.
- If Hydrologist or Semanticist fails, earlier artifacts (e.g. `module_graph.json`, `survey_summary.json`) are still written. The pipeline reports the failed stage and exits with a non-zero code. Use `-v` / `--verbose` to see which step failed and any partial outputs.

### Partial artifacts and exit codes

- **0**: Success; all stages completed.
- **1**: Input or usage error (e.g. invalid repo, resolve failure).
- **2**: An agent (Surveyor, Hydrologist, Semanticist, or Archivist) failed; partial artifacts may exist under `.cartography/`.
- **3**: Partial success (e.g. Surveyor and Hydrologist succeeded, Semanticist or Archivist failed); artifacts up to the last successful stage are still written.

When an agent fails, check the log for the failed stage and inspect `.cartography/` for any files already written (e.g. `module_graph.json`, `lineage_graph.json`) to debug or reuse partial results.

### Verbose logging

- Pass `-v` / `--verbose` to `analyze` (or `lineage`) for progress and per-stage timing. This helps debug long runs and identify which stage is slow or failing in real FDE engagements.
