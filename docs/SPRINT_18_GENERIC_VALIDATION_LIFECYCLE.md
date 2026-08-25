# Sprint 18 Contract — Generic Strategy Validation Lifecycle

## Status

**ACTIVE — ARK-S18-01 is technically complete and awaiting Owner acceptance.**

Sprint 17 provides immutable split evidence, bounded parameter-stability
evidence, a combined Owner-gated decision, and a materialized chain verifier.
The real current decision is `FAIL`; it remains negative evidence and cannot be
promoted. Sprint 18 creates an auditable historical-validation lifecycle for a
future exact `PASS` chain without authorizing execution.

## Objective

Provide a fail-closed lifecycle:

```text
CONTRACT_VALID
→ exact evidence PASS
→ Owner acknowledgement
→ verifier PASSED
→ separate explicit promotion authorization
→ VALIDATED (historical only)
→ optional RETIRED
```

`VALIDATED` never means profitable, DEMO/LIVE-ready, capital-authorized,
Router-eligible, ordered, or recommended.

## Locked boundaries

- Backtest V1 remains the only canonical simulation kernel.
- Sprint 17 evidence and decisions are immutable and are never rewritten.
- `FAIL` and `INSUFFICIENT_EVIDENCE` have no override or promotion path.
- Sprint 17 acknowledgement is not promotion authorization.
- No Router, MT5 change, deployment, capital action, order, or LIVE path.
- AI cannot determine eligibility, authorization, or lifecycle state.
- Legacy `APPROVED` lifecycle and records remain compatible and are not
  silently relabeled.
- Every mutation is explicit, atomic, fingerprint-bound, and auditable.

## Checkpoints

### ARK-S18-01 — Materialized validation eligibility

Materialize an immutable read-only assessment binding the exact strategy,
decision, Owner acknowledgement, Sprint 17 verifier, fingerprints, protocols,
and lifecycle state. Only a decision `PASS` with an exact acknowledgement and
verifier `PASSED` is `ELIGIBLE`. `FAIL`, `INSUFFICIENT_EVIDENCE`, missing
evidence, tampering, or lineage drift is `INELIGIBLE` or rejected fail-closed.
GET never recomputes historical evaluation and assessment creates no status
transition.

Acceptance requires source, forward migration, API, PASS/FAIL/INSUFFICIENT and
tamper tests, migration recovery, full regression, Docker OAT, exact reuse, and
proof that the real `FAIL` chain remains `CONTRACT_VALID` and `INELIGIBLE`.

#### Completion report

Implementation:

- Added immutable `GENERIC_VALIDATION_ELIGIBILITY_V1` snapshots. Each snapshot
  binds the StrategyVersion lifecycle state, exact Sprint 17 decision and
  source fingerprints, optional Owner acknowledgement, and materialized chain
  verifier. Identical inputs reuse one fingerprint; later acknowledgement or
  verifier state produces a new immutable snapshot without rewriting history.
- Eligibility requires all five checks: exact decision lineage, combined
  decision `PASS`, exact non-promoting Owner acknowledgement, exact `PASSED`
  evidence verifier with every check `PASS`, and untouched `CONTRACT_VALID`
  lifecycle state. There is no override for `FAIL` or
  `INSUFFICIENT_EVIDENCE`.
- Added additive migration `033_generic_validation_eligibility`, POST/list/detail
  API endpoints, and explicit promotion/lifecycle boundaries. GET reads only
  persisted eligibility rows and never replays historical evaluation.
- Assessment never changes StrategyVersion, creates authorization, or touches
  deployment, capital, Router, MT5, order, or trade state.

Verification evidence:

- Backend regression: **191 passed**. Focused API/migration/eligibility suite:
  **36 passed**. Dedicated tests prove exact `PASS → ELIGIBLE`,
  `FAIL → INELIGIBLE`, `INSUFFICIENT_EVIDENCE → INELIGIBLE`, missing-source
  snapshots, immutable state evolution, exact reuse, confirmation/verifier/
  decision tamper rejection, and lifecycle neutrality.
- Python compile and `git diff --check` pass. Migration recovery is covered by
  automated legacy-schema tests and a Docker restart.
- Docker/PostgreSQL OAT applied migration 033 exactly once and materialized the
  real assessment `7a19352e-a829-43d7-abfd-34f5c91360b8`, fingerprint
  `064fb5672b456cc4b3ca3a41dd19b6505d5a3b753159f1f2b34e1fd4608582a9`.
  It honestly returned `INELIGIBLE`: exact decision lineage, verifier, and
  lifecycle checks passed; passing-evidence and missing-acknowledgement checks
  failed. Exact retry returned `reused=true`; list/detail GET returned the same
  persisted row after service restart.
- PostgreSQL still records one migration row and one real eligibility row.
  The StrategyVersion remains `CONTRACT_VALID`, `validation_evidence_id` and
  `validated_at` remain null, and real Owner acknowledgement rows remain zero.
  No acknowledgement or promotion was fabricated.

**Checkpoint status:** source, tests, migration recovery, and runtime OAT are
complete; awaiting explicit Owner acceptance. ARK-S18-02 has not started and
ARK-S18-01 is uncommitted/unpushed.

### ARK-S18-02 — Owner-authorized atomic promotion

Add an authorization distinct from acknowledgement and allow only the atomic
`CONTRACT_VALID → VALIDATED` transition for an exact eligible assessment.
Persist immutable promotion lineage; reject negative, stale, duplicate,
concurrent, or mismatched authorization. No deployment or trading action.

### ARK-S18-03 — Retirement and lifecycle governance

Add explicit, reasoned, immutable `VALIDATED → RETIRED` governance. Retirement
does not delete evidence, cannot silently reactivate a version, and revisions
create new StrategyVersions. Preserve legacy lifecycle behavior.

### ARK-S18-04 — Strategy Library lifecycle UI and verifier

Expose eligibility, promotion lineage, historical-only status, retirement, and
safety boundaries in the Strategy Library. A materialized lifecycle verifier
checks the complete transition chain. Include API/UI regression, migration
recovery, production build, Docker OAT, and browser OAT.

## QA and acceptance protocol

Each checkpoint requires source, automated tests, runtime OAT, updated report,
and explicit Owner acceptance. An accepted checkpoint is committed and pushed
to `origin/main` before the next begins. Generated/runtime files are excluded.

The accepted contract authorizes only ARK-S18-01. Do not begin ARK-S18-02 until
the Owner explicitly accepts ARK-S18-01.
