# Phase 1: Data Model — Semanticist Agent

**Feature**: 003-semanticist-agent  
**Date**: 2025-03-13

## Entity overview

| Entity | Purpose |
|--------|--------|
| ModuleNode (extended) | Carries purpose_statement, domain_cluster, documentation_drift, docstring_snippet |
| PurposeResult | Return type of generate_purpose_statement (purpose, drift, snippet) |
| Citation | File path + optional line for Day-One evidence |
| DayOneAnswer | One of five answers: question_id, answer, citations[] |
| DayOneOutput | Top-level list of DayOneAnswer (five items) |
| DomainArchitectureMap | module path → domain name; cluster_id → domain name |
| ContextWindowBudget | Cumulative tokens, caps, truncation policy (runtime only, not persisted) |

---

## ModuleNode (extensions)

Existing in `src/models/module.py`: `path`, `language`, `purpose_statement`, `domain_cluster`, `complexity_score`, `change_velocity_30d`, `is_dead_code_candidate`, `last_modified`, `imports`, `public_functions`, `classes`, etc.

**New fields**:

| Field | Type | Validation |
|-------|------|------------|
| documentation_drift | Optional[bool] = None | True when docstring contradicts LLM-generated purpose |
| docstring_snippet | Optional[str] = None | When drift is True, store docstring (or first N chars) for traceability |

---

## PurposeResult

Return type from `generate_purpose_statement()` before attaching to ModuleNode.

| Field | Type | Validation |
|-------|------|------------|
| purpose_statement | str | Non-empty; 2–3 sentences |
| documentation_drift | bool | True if docstring contradicts purpose |
| docstring_snippet | Optional[str] = None | Present when documentation_drift is True |

---

## Citation

Evidence for a Day-One answer.

| Field | Type | Validation |
|-------|------|------------|
| file | str | Path (relative to repo or absolute) |
| line | Optional[int] = None | Line number when available |

---

## DayOneAnswer

One of the Five FDE Day-One answers.

| Field | Type | Validation |
|-------|------|------------|
| question_id | str | e.g. "q1" .. "q5" |
| answer | str | Free-text answer |
| citations | list[Citation] | At least one when evidence exists |

---

## DayOneOutput

Top-level output of `answer_day_one_questions()`.

| Field | Type | Validation |
|-------|------|------------|
| answers | list[DayOneAnswer] | Length 5; order matches question_id |

---

## DomainArchitectureMap

Produced by `cluster_into_domains()`.

| Field | Type | Validation |
|-------|------|------------|
| module_to_domain | dict[str, str] | path → domain name |
| cluster_to_domain | dict[int, str] | cluster index → domain name |
| skipped_modules | list[str] | Paths skipped (e.g. embedding failure) |

---

## ContextWindowBudget (runtime)

Not persisted; used during a single run.

| Field / concept | Type / behavior |
|-----------------|-----------------|
| cumulative_input_tokens | int, incremented before each LLM call |
| cumulative_output_tokens | int | optional, if available from provider |
| cap_total | Optional[int] | Log warning when exceeded or at 80% |
| cap_bulk_phase | Optional[int] | Truncate module code when bulk would exceed |
| estimate_tokens(text) | Method: tiktoken or len(text)//4 |
| truncate_module_code(lines, max_lines) | Return first max_lines for bulk |

---

## Serialization

- **modules** (with purpose, domain, drift): `.cartography/modules.json` (same schema as Surveyor output, enriched).
- **domain_architecture_map**: `.cartography/domain_architecture_map.json` — JSON object with `module_to_domain`, `cluster_to_domain`, `skipped_modules`.
- **day_one_answers**: `.cartography/day_one_answers.json` — JSON array of `{ "question_id", "answer", "citations": [ { "file", "line" } ] }`.
- **embedding_cache**: `.cartography/embedding_cache/` (or single file) — key = content hash of purpose text; value = embedding list (or path to npy). Format is implementation-defined.

All persisted shapes MUST be derivable from the Pydantic models (e.g. `.model_dump(mode="json")`).
