# Sprint 18 Contract — Generic Strategy Validation Lifecycle

## Status

**ACTIVE — ARK-S18-01 accepted; ARK-S18-02 is technically complete and awaiting Owner acceptance.**

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

**Checkpoint status:** accepted by the Owner and pushed to `origin/main` at
`6df078e` before ARK-S18-02 began.

### ARK-S18-02 — Owner-authorized atomic promotion

Add an authorization distinct from acknowledgement and allow only the atomic
`CONTRACT_VALID → VALIDATED` transition for an exact eligible assessment.
Persist immutable promotion lineage; reject negative, stale, duplicate,
concurrent, or mismatched authorization. No deployment or trading action.

#### Completion report

Implementation:

- Added explicit `GENERIC_HISTORICAL_VALIDATION_PROMOTION_V1` with the exact
  separate phrase `AUTHORIZE_GENERIC_HISTORICAL_VALIDATION_V1`. The Sprint 17
  acknowledgement phrase is rejected and cannot authorize promotion.
- Promotion requires an exact current `ELIGIBLE` assessment bound to a `PASS`
  decision. It re-evaluates the eligibility snapshot fingerprint/result before
  mutation and rejects stale, tampered, negative, missing, or inconsistent
  lineage.
- One database transaction inserts an immutable promotion record and performs
  a compare-and-set `CONTRACT_VALID → VALIDATED` transition. It binds the exact
  OOS evidence in `validation_evidence_id`, the promotion in
  `generic_validation_promotion_id`, and one `validated_at` timestamp. A lost
  race rolls back; an exact concurrent/repeated request reuses the sole row.
- `VALIDATED` is explicitly `HISTORICAL_VALIDATION_ONLY`. Promotion creates no
  deployment, DEMO/LIVE authority, capital authority, Router/current decision,
  order, or trade action. Strategy API serialization exposes promotion lineage.
- Additive migration 034 creates promotion storage and StrategyVersion lineage.
  Docker OAT exposed PostgreSQL `authorization` keyword portability and a
  partial table left by `create_all` before the failed migration rolled back.
  Storage now uses `authorization_phrase`; forward recovery migration 035
  detects and renames the partial quoted column without manual database edits.

Verification evidence:

- Backend regression: **198 passed**. Focused API/promotion/migration suite:
  **36 passed**. Dedicated tests cover valid atomic promotion, wrong phrase,
  exact retry, `FAIL`/`INSUFFICIENT_EVIDENCE` rejection, stale eligibility,
  decision tampering, lifecycle neutrality, and two synchronized concurrent
  writers producing exactly one promotion and one transition.
- Migration tests cover legacy schema preservation, migrations 034/035 exactly
  once, the new StrategyVersion column, and explicit recovery of an orphaned
  quoted `authorization` column. Python compile and `git diff --check` pass.
- Docker/PostgreSQL OAT applies migrations 034 and 035 exactly once and exposes
  only `authorization_phrase`. The wrong acknowledgement-as-authorization is
  rejected; the correct promotion phrase is also rejected against real
  eligibility `7a19352e-a829-43d7-abfd-34f5c91360b8` because it is
  `INELIGIBLE`. Promotion GET returns 404 and promotion-row count remains zero.
- After service restart, both migrations remain one row, the real strategy
  remains `CONTRACT_VALID`, and `validation_evidence_id`, `validated_at`, and
  `generic_validation_promotion_id` remain null. No accepted authorization,
  promotion, deployment, or trading side effect was fabricated.

**Checkpoint status:** accepted by the Owner and pushed to `origin/main` at
`9d7ddcb` before ARK-S18-03 began.

### ARK-S18-03 — Retirement and lifecycle governance

Add explicit, reasoned, immutable `VALIDATED → RETIRED` governance. Retirement
does not delete evidence, cannot silently reactivate a version, and revisions
create new StrategyVersions. Preserve legacy lifecycle behavior.

#### Completion report

Implementation:

- Added explicit `GENERIC_STRATEGY_RETIREMENT_V1` with the distinct exact
  authorization `AUTHORIZE_GENERIC_STRATEGY_RETIREMENT_V1`. A normalized
  reason of 10–500 characters is mandatory; promotion or acknowledgement
  phrases cannot authorize retirement.
- Retirement accepts only a `VALIDATED` StrategyVersion whose exact generic
  promotion, eligibility, PASS decision, OOS evidence, fingerprint, protocol,
  authorization, and historical-only result remain mutually consistent.
  Legacy `APPROVED`, non-promoted, missing, or tampered lineage fails closed.
- One database transaction inserts the immutable retirement record and applies
  a compare-and-set `VALIDATED → RETIRED`. Exact retry/concurrent requests reuse
  the single record; a different reason or inconsistent retry is rejected.
  Validation evidence, promotion lineage, and `validated_at` are retained, and
  `generic_validation_retirement_id` plus `retired_at` provide explicit lineage.
- There is no delete, update, or reactivation endpoint. A revision creates a
  new DRAFT candidate and, after contract confirmation, a new `CONTRACT_VALID`
  StrategyVersion linked through `supersedes_strategy_version_id`; the retired
  version remains unchanged and the new version inherits no validation or
  retirement authority.
- Retirement creates no deployment, DEMO/LIVE authority, capital authority,
  Router/current decision, order, or trade action. Additive migration 036
  creates retirement storage and the StrategyVersion retirement columns.

Verification evidence:

- Backend regression: **203 passed**. Focused API/promotion/retirement/migration
  suite: **41 passed**. Dedicated coverage proves required reason and exact
  phrase, atomic transition, exact reuse, conflicting-reason rejection,
  tampered/legacy rejection, retained evidence, lifecycle neutrality, revision
  versioning, and two synchronized writers producing one record/transition.
- Python compilation and `git diff --check` pass. Migration tests preserve the
  legacy lifecycle, expose both retirement columns, and prove migration 036 is
  recorded exactly once.
- Docker/PostgreSQL OAT applied migration 036 exactly once. The real strategy
  `37abb545-958d-4d14-a3b5-0b6f2321d8cf` remains honestly `CONTRACT_VALID` with
  no promotion or retirement lineage. The promotion phrase is rejected as the
  wrong retirement authorization; the exact retirement phrase is then rejected
  because the strategy has no exact generic historical promotion. GET returns
  404 and the retirement table remains empty.
- After service restart, migration 036 remains one row, retirement count remains
  zero, and the real StrategyVersion remains `CONTRACT_VALID` with null promotion
  and retirement ids. No validated state, retirement, reactivation, deployment,
  or trading side effect was fabricated for OAT.

**Checkpoint status:** accepted by the Owner and pushed to `origin/main` at
`25899dc` before ARK-S18-04 began.

### ARK-S18-04 — Strategy Library lifecycle UI and verifier

Expose eligibility, promotion lineage, historical-only status, retirement, and
safety boundaries in the Strategy Library. A materialized lifecycle verifier
checks the complete transition chain. Include API/UI regression, migration
recovery, production build, Docker OAT, and browser OAT.

#### Completion report

Implementation:

- Added materialized `GENERIC_VALIDATION_LIFECYCLE_VERIFIER_V1`. Each immutable
  lifecycle snapshot receives a fingerprinted verifier artifact; a changed
  source produces a new result instead of overwriting prior evidence.
- The verifier handles all three generic states. `CONTRACT_VALID` requires an
  exact current eligibility snapshot and no transition. `VALIDATED` requires
  exact eligible PASS decision, historical promotion, OOS evidence, timestamp,
  and promotion fingerprint. `RETIRED` additionally requires exact reasoned
  retirement fingerprint, retained evidence, ordered timestamps, and the
  no-reactivation/new-version revision policy.
- Seven materialized checks cover StrategyVersion identity, eligibility,
  promotion, retirement, forward-only transition coherence, retirement
  immutability, and safety boundaries. PASSED never claims profitability or
  DEMO/LIVE, capital, Router, deployment, order, or trading authority.
- Additive migration 037 creates lifecycle-verifier storage. POST materializes
  or exactly reuses a snapshot; StrategyVersion GET and verifier-id GET are
  read-only. There are no PATCH or DELETE verifier endpoints.
- Strategy Library now exposes `NOT_VALIDATED`,
  `HISTORICAL_VALIDATION_ONLY`, and `RETIRED_IMMUTABLE` distinctly. It renders
  eligibility, promotion, retirement, verifier fingerprints/checks, mandatory
  safety text, explicit historical promotion, reasoned retirement, immutable
  retired badges, and revision-as-new-version guidance. Retired versions cannot
  rerun the evidence pipeline; legacy cards keep their existing lifecycle.

Verification evidence:

- Backend regression: **206 passed**. Focused lifecycle/promotion/retirement/
  migration suite: **16 passed**. Tests cover exact three-state snapshots,
  INELIGIBLE no-transition validity, snapshot reuse, tamper detection producing
  FAILED evidence, API read/materialize behavior, and absent mutation routes.
- Web regression: **26 passed across 9 files**, including eight Strategy Library
  tests and explicit UI fixtures for all three lifecycle states. TypeScript
  typecheck and ESLint pass. The optimized Next.js build compiles all **43**
  pages/routes successfully; Docker builds both research and web images.
- Docker/PostgreSQL OAT applies migration 037 exactly once and materializes real
  verifier `f5cc9062-068a-44d8-a383-50ab395d6eee`, fingerprint
  `1dc012671b6b5627821385e2e7c9996f9d359f0bc9dd394d1f7960be6dc74318`.
  All seven checks PASS, but the honest claim remains `NOT_VALIDATED`: real
  eligibility is `INELIGIBLE`, promotion and retirement are null, and the
  StrategyVersion remains `CONTRACT_VALID`. The web proxy exactly reuses it.
- In-app browser OAT opens the production Docker Strategy Library, clicks
  **Verify lifecycle governance**, and visibly confirms PASSED,
  CONTRACT_VALID/NOT_VALIDATED, INELIGIBLE, no promotion/retirement, all seven
  checks, and the complete execution safety warning. Full-page visual inspection
  shows a readable panel and registry without overlap; browser console errors
  are empty.
- After research/web restart, migration and verifier counts remain one, the
  fingerprint and `NOT_VALIDATED` claim persist, the StrategyVersion retains
  null promotion/retirement ids, and browser interaction returns the same panel
  with no console errors. No lifecycle or trading state was fabricated.

**Checkpoint status:** accepted by the Owner. Source, backend/API/UI tests,
production build, migration, Docker OAT, restart recovery, and browser OAT are
complete with technical claim **VALIDATED**. This checkpoint closes all four
ARK-S18 checkpoints and is committed/pushed as the final Sprint 18 delivery.

## QA and acceptance protocol

Each checkpoint requires source, automated tests, runtime OAT, updated report,
and explicit Owner acceptance. An accepted checkpoint is committed and pushed
to `origin/main` before the next begins. Generated/runtime files are excluded.

Do not begin the next checkpoint until the Owner explicitly accepts the current
checkpoint. An accepted checkpoint is pushed before its successor begins.
