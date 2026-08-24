# Sprint 17 Contract — Generic Strategy Evidence Gate

## Status

**ACTIVE — ARK-S17-03 accepted; ARK-S17-04 is technically complete and awaiting Owner acceptance.**

Sprint 16 is complete at `9dae9ea`. It can create immutable generic
completed-candle StrategyVersions and run them through the sole Backtest V1
kernel. Sprint 17 supplies the missing historical evidence gate for those
versions. It does not promise profitability or authorize trading.

## Objective

Produce an exact, fail-closed train/holdout/final-OOS evidence chain for the
bounded generic evaluator. Every result must be replayable from its immutable
contract, capability registry, evaluator, source assets, split boundaries, and
cost semantics.

## Non-goals and immutable boundaries

- No Router/current signal, DEMO/LIVE execution, MT5 change, capital allocation,
  or trade recommendation.
- Backtest V1 remains the sole entry/exit/cost/ambiguity kernel; no second
  simulator or hidden replay path.
- Existing legacy OOS evidence and historical StrategyVersions remain readable
  and unchanged.
- A `PASS` is evidence for an explicit later Owner decision only; it does not
  automatically create `VALIDATED` for a generic StrategyVersion.
- XAUUSD, M1 execution, LONG only, fixed price SL/TP, one position, fixed demo
  lot, completed candles, and `STOP_FIRST` remain the S16/S17 envelope.

## Checkpoint sequence

1. **ARK-S17-01 — Generic split protocol and exact evaluator replay**
2. **ARK-S17-02 — Robustness and parameter-stability evidence**
3. **ARK-S17-03 — Owner-gated generic evidence decision**
4. **ARK-S17-04 — Factory evidence UI and materialized acceptance verifier**

## ARK-S17-01 — Generic split protocol and exact evaluator replay

### Objective

Run a confirmed generic StrategyVersion over chronological train, holdout, and
final-OOS bounds without leaking a future M1 or MTF context candle.

### Required artifacts

- Versioned generic OOS protocol with fixed chronological boundaries and every
  M1/M5/M15/H1 context availability rule captured in fingerprinted evidence.
- Exact replay adapter using the S16 evaluator decision path and Backtest V1
  kernel; legacy OOS path remains behaviorally unchanged.
- Tests for context boundary availability, chunking/replay invariance, missing
  asset failure, and no partial evidence on evaluator failure.

### Acceptance measurement

- No split can read a candle whose close is after its decision time.
- All split results carry exact StrategyVersion, assessment, registry,
  evaluator, asset, cost, and protocol lineage.
- Same immutable input returns the same recorded evidence or reuse, not a
  duplicate execution.

### Completion report — 2026-08-25

Implemented and verified:

- Added fingerprinted `GENERIC_OOS_EVIDENCE_V1` with frozen 60/20/20
  chronological bounds, split-isolated evaluator state, exact Backtest V1
  execution/cost semantics, and an explicit evidence-only Owner boundary.
- The S16 completed-candle evaluator now has a bounded streaming replay mode.
  It retains only each rule's required lookback, advances registered MTF assets
  by completed close time, and discards context from an earlier split. Quick
  Backtest keeps its separate bounded-snapshot mode; the legacy OOS adapter and
  protocol remain unchanged.
- Generic evidence fingerprints bind the StrategyVersion/checksum, capability
  assessment, V2 registry, evaluator artifact, required M1/MTF asset lineage,
  costs, split protocol, and dataset fingerprint. Exact retries reuse the same
  row. Evaluator failure tests prove that no partial evidence or lifecycle
  mutation is persisted.
- Generic replay always records `GENERIC_EVIDENCE_REVIEWED`; even a gate `PASS`
  cannot set `VALIDATED`. No DEMO/LIVE, capital, Router, or trade authority is
  created.

Verification evidence:

- Backend regression: **170 passed**. Python compile and diff integrity checks
  pass.
- Docker/PostgreSQL full-history OAT used StrategyVersion
  `37abb545-958d-4d14-a3b5-0b6f2321d8cf`, dataset
  `de5fa845-5397-441b-91dc-fe5f8ffc8e5b`, **2,985,994 M1** and **600,274 M5**
  bars. Observed research-service memory stayed approximately 239–253 MiB
  during the exhaustive replay.
- OAT evidence `099bfd6d-1137-45ce-adc8-53c30b2d337d`, fingerprint
  `01056345e1ce4f4eb2181f3fffe7473af3c80fe69289c4aadad0ad52b8519faf`,
  honestly returned `FAIL`: baseline holdout PnL `-1596.188`, baseline final-OOS
  PnL `-6082.086`, and adverse final-OOS PnL `-6485.645`.
- The exact repeated API request returned `reused=true` and the same ID and
  fingerprint. PostgreSQL contains one generic OOS row; the StrategyVersion
  remains `CONTRACT_VALID` with no `validation_evidence_id`.
- Legacy protocol-V3 evidence `e8fc488b-0524-4235-a46e-9e3d11f77353`
  remained byte-compatible and returned `reused=true`; PostgreSQL still
  contains exactly one row for that legacy StrategyVersion. The accepted S16
  generic Quick Backtest likewise reused its existing run and fingerprint.

**Owner decision:** ARK-S17-01 accepted on 2026-08-25. Its acceptance commit
must be pushed before ARK-S17-02 implementation begins.

## ARK-S17-02 — Robustness and parameter-stability evidence

### Objective

Evaluate generic contracts under bounded costs and fixed, declared parameter
neighborhoods without optimization leakage.

### Required artifacts

- Frozen baseline/adverse cost scenarios and minimum-support checks.
- Bounded local parameter-neighborhood policy with explicit exclusions,
  deterministic ordering, and no access to final-OOS during selection.
- Materialized robustness result with trade counts, PnL/PF, year/regime
  concentration, stability observations, and negative outcomes preserved.

### Acceptance measurement

- Parameter selection cannot inspect final-OOS.
- Missing support yields `INSUFFICIENT_EVIDENCE`; failed economics yields `FAIL`;
  neither is hidden or retried under changed semantics.
- Generic and legacy costs/timing use the same kernel definitions.

### Completion report — 2026-08-25

Implemented and verified:

- Added immutable `GENERIC_PARAMETER_STABILITY_V1` evidence and additive
  migration `030_generic_robustness_evidence`. Its fingerprint binds the exact
  StrategyVersion/checksum, dataset/fingerprint, baseline generic OOS ID and
  fingerprint, and frozen stability policy.
- The deterministic neighborhood contains exactly five ordered candidates:
  baseline, stop distance -10%/+10%, and target distance -10%/+10%. Only one
  axis changes at a time. Joint changes, indicator-period tuning, block or
  timeframe mutation, cost optimization, final-OOS selection, and best-candidate
  promotion are explicitly prohibited.
- Baseline metrics are reused from exact S17-01 evidence. Four neighbors replay
  only train and holdout under baseline/adverse costs through the same generic
  completed-candle evaluator and Backtest V1 kernel. Every row retains metrics,
  PF/PnL, trade support, year/regime breakdown, evaluator, and asset lineage.
- The materialized decision preserves `PASS`, `FAIL`, and
  `INSUFFICIENT_EVIDENCE`. Evaluator failures persist no partial row. Exact
  retries reuse one fingerprinted artifact, and no lifecycle state changes.

Verification evidence:

- Backend regression: **175 passed**. Migration recovery, API lifecycle,
  deterministic ordering, final-OOS blindness, negative outcomes, reuse,
  no-partial failure, Python compile, and diff checks pass.
- Docker/PostgreSQL OAT applied migration 030 exactly once and evaluated the
  real 2,985,994-M1/600,274-M5 lineage. Observed service memory remained
  approximately 213–293 MiB during more than 19 million bounded bar-evaluations.
- Evidence `623f8097-c6f3-4969-a51f-64f7f0dcf625`, fingerprint
  `cf44d9559533a34ca0d7898bb766e6cd39f27d8a7809456d98b157cb5ad6d116`,
  honestly returned `FAIL`: all 5/5 candidates had sufficient trade support,
  but 0/5 passed economics (required fraction 0.75).
- Holdout PnL/PF ranged from `-1894.6189`/`0.821649` to
  `-1329.9391`/`0.877593`; every adverse holdout PnL was negative. The exact
  retry returned `reused=true`, PostgreSQL contains one robustness row,
  final-OOS is `accessed=false`, selection is null, and the StrategyVersion
  remains `CONTRACT_VALID` with no validation evidence link.

**Owner decision:** ARK-S17-02 accepted on 2026-08-25. Its acceptance commit
must be pushed before ARK-S17-03 implementation begins.

## ARK-S17-03 — Owner-gated generic evidence decision

### Objective

Make PASS/FAIL/INSUFFICIENT_EVIDENCE explicit while preserving a hard Owner
boundary before any lifecycle promotion.

### Required artifacts

- Immutable decision record combining exact split and robustness evidence.
- Explicit Owner confirmation endpoint for a future promotion workflow; this
  card records no `VALIDATED` transition itself.
- Tests proving no OOS/robustness operation creates DEMO/LIVE, capital, Router,
  trade decision, or automatic `VALIDATED` state.

### Acceptance measurement

- Decision outcome and every threshold are inspectable and fingerprinted.
- Repeated requests reuse exact evidence.
- Lifecycle safety is independently asserted for PASS, FAIL, and insufficient
  evidence cases.

### Completion report — 2026-08-25

Implemented and verified:

- Added immutable `GENERIC_EVIDENCE_DECISION_V1` combining the exact S17-01
  generic OOS and S17-02 stability fingerprints. Its deterministic outcome is
  `INSUFFICIENT_EVIDENCE` if either source is insufficient, `PASS` only if both
  pass, and otherwise `FAIL`.
- Decision evidence exposes every OOS/stability threshold, source outcome,
  economic observation, split-access declaration, StrategyVersion/dataset
  lineage, and the hard Owner boundary. Exact retries reuse one materialized
  row without replaying either source.
- Added separate immutable
  `GENERIC_EVIDENCE_OWNER_ACKNOWLEDGEMENT_V1` endpoint and table. It requires the
  exact acknowledgement phrase, binds the decision ID/fingerprint/outcome, and
  explicitly records `promotion.authorized=false` and `performed=false`.
  Acknowledgement is not validation and a future separate contract would be
  required for any promotion direction.
- Additive migration `031_generic_evidence_owner_gate` creates separate
  decision and acknowledgement tables. Tampered lineage, unknown outcomes, and
  incorrect acknowledgement fail closed without a partial confirmation.

Verification evidence:

- Backend regression: **181 passed**. PASS, FAIL, and
  INSUFFICIENT_EVIDENCE paths independently prove no `VALIDATED`, DEMO/LIVE,
  capital, Router, deployment, or trade-decision state; API reuse, migration
  recovery, Python compile, and diff checks pass.
- Docker/PostgreSQL OAT applied migration 031 exactly once and materialized
  decision `2ea4139c-0b85-446a-a1f6-5912135497f6`, fingerprint
  `8d99ad4cb8ba61ec9db8fa99c0dba44c4c046ada4d8c560a0490ed8a314e1e14`,
  from S17-01 `FAIL` plus S17-02 `FAIL`; the combined outcome is honestly
  `FAIL` and the exact retry returned `reused=true`.
- PostgreSQL contains exactly one real decision row and **zero** real Owner
  acknowledgement rows. No acknowledgement was fabricated during OAT. The
  StrategyVersion remains `CONTRACT_VALID` with no `validation_evidence_id`.

**Checkpoint status:** accepted by the Owner and pushed to `origin/main` at
`ae98995` before ARK-S17-04 began.

## ARK-S17-04 — Factory evidence UI and materialized acceptance verifier

### Objective

Show the complete generic historical evidence chain to the Owner without GET
requests re-running expensive evaluation.

### Required artifacts

- Factory UI for generic split/robustness evidence, declared policy, negative
  outcomes, explicit Owner decision boundary, and no-trading disclosure.
- Materialized verifier checking contract, registry, evaluator, assets,
  completed-candle split alignment, protocol/thresholds, idempotency, and
  lifecycle safety.
- API/UI regression, migration recovery, Docker OAT, and browser OAT.

### Acceptance measurement

- The UI cannot represent a failed or insufficient result as validated.
- Verifier GET is read-only and its artifact is reused by exact fingerprint.
- Production build and all required OAT checks pass.

### Completion report

Implementation:

- Added `GENERIC_EVIDENCE_ACCEPTANCE_VERIFIER_V1` as a separately materialized,
  immutable snapshot. It reads recorded metadata/evidence only and never reads
  bar payloads or replays Backtest V1 during GET.
- The verifier checks the exact Strategy Contract checksum, bound registry
  assessment, current generic evaluator artifact, registered M1/context assets,
  isolated 60/20/20 OOS bounds, train/holdout-only stability bounds, frozen
  protocols and thresholds, recomputed OOS → robustness → decision lineage,
  one-row-per-fingerprint idempotency, and lifecycle safety.
- Additive migration `032_generic_evidence_verification` creates the verifier
  table. POST materializes or reuses an exact fingerprint; GET only returns the
  existing artifact and returns 404 before materialization.
- Strategy Factory now exposes ordered generic split, parameter-stability, and
  combined-decision controls plus a complete chain view. It renders declared
  policy, negative checks, stability support, exact lineage, the Owner boundary,
  and all verifier checks. Generic `PASS`, `FAIL`, and
  `INSUFFICIENT_EVIDENCE` are always labeled `NOT VALIDATED`; acknowledgement
  cannot promote and a separate future promotion contract remains mandatory.
- Added Next.js proxy routes for generic robustness, decisions, and verifier
  GET/POST. The preserved legacy OOS/validation presentation remains separate.

Verification evidence:

- Backend regression: **184 passed**. Focused verifier/API/migration regression
  passed `32` tests, including exact reuse, read-only GET, tampered-threshold
  failure, changed-source rejection, lifecycle neutrality, and migration
  recovery.
- Web regression: **23 passed** across 9 test files. Dedicated Factory tests
  prove both `FAIL` and `INSUFFICIENT_EVIDENCE` render as `NOT VALIDATED` with a
  separate Owner boundary. ESLint and TypeScript checks pass.
- Local and Docker production builds pass and contain all three new proxy
  routes. The only build notices are the pre-existing Next.js ESLint-plugin and
  CSS autoprefixer warnings; compilation, type checking, and static generation
  succeed.
- Docker/PostgreSQL OAT applied migration 032 exactly once and materialized real
  verifier `9dcba588-1848-41c7-8e53-5124af12fd19`, fingerprint
  `1ae9aaae0afa3c1c18e0da66bcecc34ba785755b8a347f3f9ec6dcc1e564014e`.
  Its chain-integrity status is `PASSED`, every one of nine checks is `PASS`,
  and the evidence outcome remains honestly `FAIL`; the exact retry returned
  `reused=true` and the web proxy returned the same artifact.
- Browser OAT on `/strategies` loaded the real generic chain, displayed split
  `FAIL`, stability `FAIL`, combined `FAIL`, verifier `PASSED`, all nine checks,
  `NOT VALIDATED`, the explicit Owner boundary, and the no-trading disclosure.
  Browser console errors: zero.
- The real StrategyVersion remains `CONTRACT_VALID` with no
  `validation_evidence_id`; real Owner acknowledgement rows remain zero. No
  acknowledgement, `VALIDATED`, deployment, capital, Router, order, or trade
  side effect was fabricated.

**Checkpoint status:** source, automated tests, migration recovery, Docker OAT,
and browser OAT are complete; awaiting explicit Owner acceptance. Sprint 17 is
technically 4/4 complete, ARK-S17-04 is uncommitted/unpushed, and no later
milestone has started.

## Acceptance protocol

Each checkpoint requires source, automated tests, Docker/runtime OAT, updated
report, and explicit Owner acceptance. An accepted card is committed and pushed
to `origin/main` before the next card starts.

To authorize this milestone and only its first checkpoint:

```text
DITERIMA — KONTRAK ARK-S17
Mulai ARK-S17-01.
```
