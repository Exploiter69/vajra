# VAJRA Phase 8 — Engineering Context + Workspace

**Status:** COMPLETE / VALIDATED
**Baseline:** Phase 7 Gate F passed at `d2786be`
**Closure evidence:** Phase 9 records Phase 8 complete at 565 tests
**Operating-cost constraint:** ₹0.00

## Scope

Phase 8 implements the bounded information/workspace substrate required by the Controller without enabling the autonomous engineering loop.

The implementation follows the roadmap requirements. The original pending-gate wording in this document is historical; the later Phase 9 closure record establishes Phase 8 as the completed baseline:

1. operational Git worktree lifecycle;
2. deterministic `ContextBundle` construction;
3. repository indexing and structural retrieval;
4. provenance/trust tagging;
5. context freshness and invalidation;
6. workspace/repository serialization and recovery integration;
7. executable prerequisites/gates before broader model reasoning.

## Implemented

### Workspace lifecycle

`src/vajra/control/workspace.py` adds:

- durable workspace records;
- VAJRA-owned workspace identity and ownership token;
- explicit `OWNED` / `IN_USE` / `RELEASED` / `REMOVED` lifecycle states;
- bounded `use()` ownership context;
- checkpoint association;
- current-state inspection and reconciliation;
- missing, dirty, and revision-diverged recovery dispositions;
- safe cleanup refusal for dirty workspaces unless explicit discard is requested;
- atomic record replacement;
- cross-process Git serialization using OS advisory locks.

The existing `WorktreeManager` remains the Git worktree boundary. The worktree is not treated as a security boundary; sandbox isolation remains separate.

### Repository index

`src/vajra/context/index.py` provides a deterministic, dependency-light index with:

- sorted repository traversal;
- generated/cache directory exclusion;
- bounded file size;
- binary-file exclusion;
- UTF-8 text extraction;
- language classification;
- Python AST symbol extraction;
- lexical symbol/reference extraction for other supported text languages;
- import/dependency extraction;
- local dependency edges where resolvable;
- symbol-to-file locations;
- bounded Git history;
- content/revision-derived index digest.

No vector database or paid service is required.

### Deterministic retrieval

`src/vajra/context/retrieval.py` ranks exact path, path, symbol, reference, dependency, and history matches deterministically. Ties are resolved by stable path ordering.

Embeddings and advanced recursive retrieval remain research options rather than Phase 8 foundations.

### ContextBundle

`src/vajra/context/contracts.py` and `engine.py` provide an immutable, digest-checked bundle containing the roadmap-defined context surface:

- objective;
- acceptance criteria;
- repository summary;
- relevant files;
- relevant symbols;
- dependencies;
- recent changes;
- relevant history;
- current reconciliation;
- constraints;
- allowed capabilities;
- budget.

Each concrete context item carries source kind, provenance/trust class, locator, source revision, content digest, and freshness.

Repository instructions are explicitly repository observations (`INSTRUCTION` source kind plus `OBSERVED_REPOSITORY` provenance). They do not become VAJRA authority.

### Freshness and invalidation

`src/vajra/context/freshness.py` rejects stale or invalid bundles. Index caching is keyed by workspace, current Git revision, and filesystem digest. Workspace mutation or revision change therefore forces reconstruction rather than reuse of stale context.

### Provenance

The provenance vocabulary includes the roadmap's required classes:

- `TRUSTED_SYSTEM`;
- `TRUSTED_POLICY`;
- `TRUSTED_VERIFICATION`;
- `OBSERVED_REPOSITORY`;
- `MODEL_OUTPUT`;
- `WORKER_OUTPUT`;
- `EXTERNAL_CONTENT`;
- `HISTORICAL_MEMORY`;
- `UNKNOWN`.

Additional compatibility values are retained for the broader VAJRA control vocabulary.

## Test coverage added

- deterministic repository indexing;
- Python symbol extraction;
- local dependency graph extraction;
- deterministic retrieval;
- bounded ContextBundle construction;
- complete roadmap context sections;
- repository-instruction non-authority;
- bundle determinism;
- cache invalidation;
- freshness rejection;
- generated/binary content exclusion;
- workspace lifecycle;
- checkpoint association;
- ownership enforcement;
- dirty workspace protection;
- revision divergence;
- durable workspace-record integrity;
- Git serialization contention.

## Safety boundary

Phase 8 does **not** enable model reasoning, direct model execution, autonomous completion, or a Phase 10 engineering loop.

The Phase 7 Gate F boundaries remain mandatory:

```text
fresh reality
  -> bounded context
  -> reasoning proposal
  -> intent
  -> policy
  -> broker
  -> sandbox/workspace
  -> artifact
  -> independent verification
  -> evidence
  -> progress
  -> controller decision
```

Context remains informational. Repository instructions remain untrusted repository content. Worktree isolation remains distinct from sandbox security isolation.

## Validation / closure

Phase 8 is closed by the later Phase 9 baseline record, which explicitly records **Phase 8 complete at 565 tests**. The earlier validation-gate wording above was an implementation-time checkpoint and is historical; Phase 9 proceeded only after the Phase 8 substrate was treated as complete.
