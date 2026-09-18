# Phase 14 — Engineering Memory

**Status:** COMPLETE / CLOSED

Phase 14 implements the canonical roadmap requirements without making memory an authority layer.

## Scope

### 14A — Failure Memory

EngineeringMemory.remember_failure() stores provenance-bound failure signatures, categories, outcomes, Run/Step/Attempt identity, repository state, and source references. Failure memory is historical input only; it cannot authorize recovery or completion.

### 14B — Repository Memory

remember_repository() records recurring architecture, conventions, structured decisions, and verification history together with repository revision/digest and provenance references. validate_repository() requires current repository revision and, when supplied, digest to match. A changed repository therefore makes historical repository memory stale instead of trusted.

### 14C — Context Memory

remember_context() stores bounded context items with context digest, repository revision, and source references. validate_context() rejects stale context when either the repository revision or context digest changes. Context memory preserves item-level provenance supplied by the Context Engine and remains informational.

### 14D — Conflict Awareness

Historical memory never outranks current authoritative reality. Repository and context validation return an explicit MemoryConflict with CURRENT_TRUTH_WINS when current state differs. Supersession is append-only: a correction is a new immutable record linked with supersedes; superseded records are hidden from normal queries but remain auditable.

## Storage and integrity

- Dependency-free JSONL persistent store.
- Append-only records with fsync() before append returns.
- Immutable records protected by deterministic SHA-256 record digests.
- Tampered journal records fail closed during load.
- Provenance source references are mandatory for all memory.
- Memory identity binds Run/Step/Attempt/repository/source identity to avoid cross-run accidental deduplication.
- Deterministic filtering/search; no vector database dependency.
- Query results are bounded and deterministically ordered.

## Authority boundary

Current repository and verifier truth always outrank historical memory.

Memory MUST NOT:

- mutate canonical Run state;
- authorize intents or execution;
- redefine acceptance criteria;
- establish verification proof;
- bypass Policy, Broker, fencing, sandbox, or human gates;
- be treated as current truth without validation.

## Final validation

The final local Phase 14 gate passed:
- Dedicated memory tests: **8 passed**
- Portable full suite: **643 passed, 4 deselected**
- Python compilation: **PASS**
- `git diff --check`: **PASS**

The GitHub Actions workflow remains configured for the same checks. The available workflow connector does not expose push-triggered runs for the final main revision, so no unsupported hosted-CI result is claimed.

Phase 14 is closed. No vector database, embeddings, autonomous memory rewriting, model-controlled memory authority, or paid infrastructure was introduced.
