<!--
Sync Impact Report

- Version change: N/A (unfilled template) → 1.0.0
- Modified principles:
  - Template placeholder → I. Challenge Fidelity (TRP 1 Week 4)
  - Template placeholder → II. Typed Schemas via Pydantic
  - Template placeholder → III. Graceful Degradation (Never Crash the Pipeline)
  - Template placeholder → IV. Scale Discipline (Ignores + Incremental Updates)
  - Template placeholder → V. Evidence-Backed Intelligence (Citations + Tiered LLM)
- Added sections:
  - Non-Negotiable Implementation Constraints
  - Workflow & Quality Gates
- Removed sections: None (filled template placeholders)
- Templates requiring updates:
  - ✅ /home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.specify/templates/plan-template.md
  - ✅ /home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.specify/templates/spec-template.md
  - ✅ /home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.specify/templates/tasks-template.md
  - ⚠ pending: None
- Deferred TODOs:
  - TODO(RATIFICATION_DATE): Unknown adoption date for constitution; set when first ratified.
-->

# The Brownfield Cartographer Constitution

## Core Principles

### I. Challenge Fidelity (TRP 1 Week 4)
All implementation MUST follow the TRP 1 Week 4 challenge document exactly for:
- Phases, deliverables, and demo protocol
- Knowledge graph schema (node/edge types and required metadata)
- Required artifacts (e.g., `.cartography/*`, `CODEBASE.md`, `onboarding_brief.md`)

If there is ambiguity, the system MUST default to the strictest interpretation that preserves
deliverable compatibility with the challenge rubric and evidence requirements.

### II. Typed Schemas via Pydantic
All node types, edge types, and tool outputs MUST be defined as Pydantic models.
- Do not pass around untyped dicts as the primary contract between components.
- Serialization formats (JSON/JSONL) MUST be derived from these models.
- Any persisted graph artifact MUST have a schema-defined shape, not ad-hoc fields.

### III. Graceful Degradation (Never Crash the Pipeline)
The pipeline MUST be resilient to real-world repo messiness.
- Per-file analysis MUST be wrapped in try/except; failures MUST be logged and skipped.
- A single bad file MUST NOT fail the full run.
- When a reference cannot be resolved (dynamic SQL, f-strings, indirect imports), the system
  MUST record the limitation explicitly rather than guessing.

### IV. Scale Discipline (Ignores + Incremental Updates)
The system MUST be practical on large brownfield repos.
- The analyzer MUST support ignore patterns (e.g., `.cartographyignore` or `.cgrignore`-style)
  to exclude vendor/build/generated paths.
- The system SHOULD support incremental updates (content hashing and/or git) and MUST prefer
  re-analyzing only changed files when possible.

### V. Evidence-Backed Intelligence (Citations + Tiered LLM)
All agent outputs MUST cite evidence and clearly separate signal sources.
- Every claim MUST include: source file, line range, and analysis method (static vs LLM).
- LLM usage MUST be tiered: use a cheap/fast model for bulk extraction, and a stronger model
  only for synthesis/briefing tasks.
- Outputs MUST remain grounded in code evidence; speculative language MUST be flagged.

## Non-Negotiable Implementation Constraints

The Brownfield Cartographer implementation MUST include:
- **Phases & deliverables compliance**: Match the TRP 1 Week 4 phases and required artifacts.
- **Pydantic-first contracts**: Pydantic models for nodes/edges/graph artifacts/tool I/O.
- **Graceful degradation**: Per-file try/except; log + skip unparseable inputs; never crash run.
- **Ignore patterns**: Respect `.cartographyignore` (or `.cgrignore` equivalent) for exclusions.
- **Incremental updates**: Detect changes via content hash and/or git; avoid full re-analysis.
- **Evidence citations**: File + line range + method (static vs LLM) in all agent outputs.
- **Tiered LLM strategy**: Cheap model for bulk extraction; expensive model for synthesis only.
- **Sequential checklist tasks**: Tasks MUST be a checklist; each item independently completable
  and independently testable.

## Workflow & Quality Gates

To keep the system trustworthy and maintainable:
- **Checklist execution**: Work is planned and executed as a sequential checklist; each task
  ends with a clear verification step.
- **Structured logging**: Failures, skips, and unresolved references MUST be logged with file
  context so runs are debuggable.
- **Determinism where possible**: Prefer static analysis and deterministic extraction; use LLMs
  only where semantics are required.
- **Schema compatibility**: Changes to node/edge schemas MUST include migration notes for
  existing `.cartography/*` artifacts.

## Governance

This constitution supersedes all other project practices and templates.

- **Amendment process**:
  - Any change MUST update this file, bump the version, and record rationale in the Sync Impact
    Report at the top.
  - Any change that affects deliverables/schemas MUST also update relevant templates and any
    generated artifact contract expectations.
- **Versioning policy (SemVer)**:
  - MAJOR: Backward-incompatible governance/principle changes or schema breaks.
  - MINOR: New principle/section or material expansions that add enforceable requirements.
  - PATCH: Clarifications and wording changes that do not change obligations.
- **Compliance review**:
  - Plans/specs/tasks MUST include a constitution check gate before implementation.
  - Outputs MUST be rejected if evidence citations or method labels are missing.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): set upon adoption | **Last Amended**: 2026-03-10
