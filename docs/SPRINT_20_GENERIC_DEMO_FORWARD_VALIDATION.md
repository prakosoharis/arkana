# Sprint 20 — Generic DEMO Compiler and Forward Validation

**Contract status:** accepted by Owner on 2026-08-25

**Active checkpoint:** ARK-S20-05 — authorized by Owner; implementation pending

**Implementation authority:** ARK-S20-05 Owner DEMO UI, complete-chain verifier,
restart recovery, browser OAT, and Sprint 20 closure only; no LIVE authority

## Product objective

Build the deterministic, auditable bridge from an exact historically
`VALIDATED` generic StrategyVersion into MT5 DEMO configuration and separated
forward evidence:

```text
historically VALIDATED StrategyVersion
  + exact lifecycle/capability verification
  + broker metadata and capital contract
  + DEMO-only safety policy
  → immutable generic DEMO contract
  → deterministic MT5 configuration
  → exact EA acknowledgement
  → DEMO telemetry/trades
  → forward-validation evidence for Owner review
```

This sprint does not prove profitability, authorize LIVE, or allow AI to enter
the deterministic execution path. A valid implementation may truthfully end in
`NO_VALIDATED_STRATEGY`, `DEMO_WAITING_FOR_MT5`, or
`FORWARD_EVIDENCE_INSUFFICIENT`; those are not failed demonstrations.

## Why this is the next milestone

Sprint 19 completes deterministic Router/current-decision evidence, but the
existing MT5 EA still supports only the legacy bullish-reversal prototype and
fixed lot `0.01`. There is no generic compiler from the accepted Strategy
Contract registry into a DEMO configuration, no exact generic EA capability
acknowledgement, and no forward-evidence chain for a generic StrategyVersion.

The current real generic strategy is `CONTRACT_VALID`, not `VALIDATED`, because
its historical evidence outcome is FAIL. It must not be promoted or deployed
merely to make Sprint 20 appear successful.

## Locked architecture and safety boundaries

- Only a non-retired historically `VALIDATED` StrategyVersion with an exact
  PASSED lifecycle verifier may receive a generic DEMO contract.
- Legacy `APPROVED`, `CONTRACT_VALID`, `INELIGIBLE`, FAIL,
  `INSUFFICIENT_EVIDENCE`, and `RETIRED` records are rejected.
- Backtest V1 remains the sole historical simulation kernel. Sprint 20 creates
  no second backtester and does not replay historical acceptance in the EA.
- The compiler accepts only registry-declared blocks and an explicitly declared
  MT5 adapter capability. Unsupported block, timeframe, direction, symbol,
  size mode, or execution semantic fails before deployment.
- MT5 remains the owner of realtime DEMO evaluation, position management, and
  broker interaction. Web/API/AI never enter `OnTick`.
- The environment is DEMO-only. No LIVE endpoint, LIVE configuration, automatic
  promotion, or environment fallback may be introduced.
- AI cannot select a strategy, compile executable configuration, change risk,
  make a realtime decision, place an order, or interpret acknowledgement.
- Historical evidence, Router evidence, and DEMO forward evidence remain
  separate datasets and claims. They are never merged into one performance
  metric.
- Missing/stale broker, capital, lifecycle, Router, config, acknowledgement, or
  telemetry evidence fails closed without a hidden default.
- EA cached configuration is accepted only when its exact checksum remains
  valid; corruption or mismatch disables new entries while retaining safe
  position/emergency handling.
- Every checkpoint requires source, regression, proportional runtime OAT,
  documentation, and explicit Owner acceptance before its successor begins.
- The accepted checkpoint is committed and pushed before work begins on the
  next checkpoint. Generated databases, build metadata, FILE_COMMON payloads,
  logs, and other runtime artifacts are never committed.

## Status and claim vocabulary

- `VALIDATED`: historical evidence/lifecycle claim only.
- `DEMO_CONTRACT_READY`: immutable inputs are sufficient for compilation; no
  deployment has occurred.
- `DEMO_CONFIG_COMPILED`: deterministic configuration exists; MT5 has not
  acknowledged it.
- `AWAITING_DEMO_ACK`: exact configuration was published to the DEMO transport.
- `DEMO_ACTIVE`: the DEMO EA acknowledged the exact strategy/version/config
  checksum and broker symbol. It never means profitable or LIVE-ready.
- `FORWARD_EVIDENCE_INSUFFICIENT`: valid DEMO evidence exists but does not meet
  the frozen review thresholds.
- `READY_FOR_OWNER_REVIEW`: frozen forward-evidence sufficiency/integrity checks
  pass. It is not automatic promotion or LIVE authorization.
- Checkpoint claim `VALIDATED`: source, tests, required OAT, and documented
  boundaries for that checkpoint are verified. It never changes the domain
  meanings above.

## Checkpoint sequence

### ARK-S20-00 — Post-S19 canonical baseline and prerequisite audit

Reconcile all canonical passages with accepted Sprint 19 and inventory the
real StrategyVersion, lifecycle, Router, broker/capital, deployment, EA,
FILE_COMMON, telemetry, Docker, and MT5 state. Freeze the Sprint 20 status
vocabulary, capability boundary, test fixture policy, and exact external OAT
dependencies without adding implementation source.

Exit criteria:

- stale claims that Router is missing are removed from canonical documentation;
- accepted S19 commits and current runtime counts/fingerprints are exact;
- the real absence of a `VALIDATED` generic strategy is recorded;
- legacy EA/config/deployment/telemetry behavior and generic gaps are mapped;
- fixture evidence is explicitly labeled isolated and can never be presented as
  real Owner strategy/MT5 evidence;
- no model, migration, API, UI, EA, config, deployment, order, or trade changes.

### ARK-S20-01 — Immutable generic DEMO contract and eligibility

Create a forward migration and immutable contract that binds one exact
historically `VALIDATED` StrategyVersion to its lifecycle verifier, evaluator
capability, instrument/broker symbol, broker snapshot, capital contract, sizing,
DEMO environment, emergency policy, and compiler protocol. Add read-only
eligibility and validation APIs; do not compile or publish configuration yet.

Exit criteria:

- exact retry reuses one fingerprinted artifact and concurrent creation has one
  winner;
- legacy, non-validated, retired, stale/tampered lifecycle, unsupported
  capability, invalid broker/capital, and non-DEMO environment fail closed;
- there are no implicit leverage, volume, spread, symbol, timeframe, or risk
  defaults;
- migration recovery preserves all legacy deployment/config records;
- no configuration, FILE_COMMON write, deployment, MT5 action, order, or trade.

### ARK-S20-02 — Deterministic Strategy Contract → MT5 compiler

Compile an eligible generic DEMO contract into one versioned canonical MT5
configuration with stable serialization/checksum. Define an explicit supported
adapter registry; start with the smallest capability slice that can prove exact
parity and reject everything else.

Exit criteria:

- repeated/order-independent compilation is byte-identical;
- every output field has exact source lineage and no hidden default;
- golden completed-candle vectors prove Python/EA rule, timing, spread guard,
  Entry/SL/TP/size, and `STOP_FIRST` interpretation parity for the supported
  slice;
- unknown block, SHORT when unsupported, missing timeframe, symbol mismatch,
  invalid size, future-candle usage, and checksum tampering fail closed;
- compiler creates no historical simulation, deployment, FILE_COMMON publish,
  MT5 action, order, or trade.

### ARK-S20-03 — DEMO publication, generic EA adapter, and acknowledgement

Add explicit Owner-authorized publication of the exact compiled configuration
to the existing safe FILE_COMMON transport. Extend the EA with a bounded generic
adapter for only the compiler capability registered in S20-02. Preflight and
acknowledgement must bind environment, account, broker symbol, strategy ID,
version, compiler protocol, and checksum.

Exit criteria:

- publication is impossible without the exact authorization phrase and DEMO
  preflight;
- wrong account/environment/symbol/version/checksum, stale request, malformed
  file, unavailable MT5, and unsupported capability reject safely;
- atomic write/recovery and concurrent retry cannot create divergent configs;
- EA compiles with zero errors/warnings and keeps LIVE locked;
- cached-config restart works only for the last exact valid checksum;
- web/API outage never transfers `OnTick` ownership away from MT5;
- MT5 OAT records honest acknowledgement or `DEMO_WAITING_FOR_MT5`; no evidence
  is fabricated when the Owner terminal is unavailable.

### ARK-S20-04 — Generic DEMO telemetry and forward-evidence ledger

Record immutable heartbeat, deterministic decision, signal/blocker, order
request/result, deal, position, cost/slippage availability, and emergency events
with exact strategy/config/broker lineage. Materialize frozen forward-validation
evidence without mixing it with historical results.

Exit criteria:

- duplicate/out-of-order telemetry is idempotent and conflicting payloads are
  rejected;
- every order/deal is traceable to strategy/version/config checksum and broker;
- missing metrics remain explicitly unavailable rather than estimated;
- no-trade and blocked decisions are first-class evidence;
- frozen sufficiency/risk checks return `FORWARD_EVIDENCE_INSUFFICIENT` until
  genuinely met; zero trades is truthful, not a test failure;
- telemetry ingestion cannot deploy, change risk/config, or authorize LIVE.

### ARK-S20-05 — Owner DEMO UI, verifier, restart recovery, and closure

Expose the generic DEMO lifecycle in an Owner UI: eligibility, exact contract,
compiled config, authorization boundary, acknowledgement, connection health,
decisions, positions, forward evidence, blockers, and safety limits. Add an
immutable complete-chain verifier and close with full regression, Docker,
browser, restart, and Owner MT5 OAT.

Exit criteria:

- UI never presents `DEMO_ACTIVE` before exact EA acknowledgement;
- verifier checks contract, compiler, publication, acknowledgement, telemetry,
  forward evidence, lifecycle coherence, and no-LIVE boundary;
- tampering, lifecycle retirement, stale heartbeat, config mismatch, restart,
  rollback, concurrency, and legacy isolation are regression-tested;
- PostgreSQL/research/web restart preserves exact fingerprints and the EA
  recovers only the last valid cached config;
- browser OAT has no console/network error and makes historical vs forward
  evidence unmistakable;
- real MT5 evidence is reported honestly. Sprint 20 may close with
  `FORWARD_EVIDENCE_INSUFFICIENT`, but not without proving the generic DEMO
  transport/acknowledgement on the Owner terminal;
- no automatic LIVE promotion, LIVE endpoint, or AI/external execution path.

## Required automated test matrix

Each implementation checkpoint must add positive, negative, tamper,
idempotency, concurrency, migration/restart, legacy-isolation, API boundary,
and no-side-effect tests proportional to its scope. The complete acceptance
regression must include at least:

1. exact eligible `VALIDATED` generic fixture → deterministic config;
2. real runtime with no validated strategy → honest blocked/no-deployment state;
3. `APPROVED`, `CONTRACT_VALID`, FAIL, insufficient, and RETIRED rejection;
4. unsupported block/timeframe/direction/symbol/size rejection;
5. compiler golden-vector parity and future-candle protection;
6. authorization, DEMO account, checksum, stale-request, and acknowledgement
   mismatch rejection;
7. exact retry and concurrent single-winner behavior at every write boundary;
8. malformed/corrupt cached config and restart recovery;
9. duplicate, conflicting, and out-of-order telemetry handling;
10. no-signal/zero-trade/insufficient-forward-evidence truthfulness;
11. lifecycle invalidation and retirement disabling new entries;
12. database/service/web restart fingerprint preservation;
13. no historical evidence mutation and no second backtester;
14. no LIVE config/endpoint/promotion and no AI in deterministic execution;
15. deployment/order/trade counts unchanged in all pre-publication scopes.

## Runtime and Owner OAT contract

Automated fixtures prove deterministic logic but cannot impersonate the Owner's
broker, account, terminal, or real strategy. Runtime evidence must label:

- Docker/PostgreSQL/Web/API evidence;
- isolated fixture evidence;
- actual Owner MT5 DEMO evidence;
- unavailable external evidence and its blocker.

If no real generic StrategyVersion is historically `VALIDATED`, S20-01/S20-02
may be tested with an isolated registered fixture, while real runtime must remain
blocked. S20-03 through S20-05 cannot claim real generic DEMO activation without
an actual eligible strategy and exact Owner-terminal acknowledgement. The agent
must say `BLOCKED_EXTERNAL_EVIDENCE`, not generate fake acknowledgements,
telemetry, orders, deals, or profits.

Owner actions, only when their checkpoint is ready:

- confirm the exact authorization phrase shown by ARKANA;
- run/attach the designated EA on an MT5 DEMO account and broker symbol;
- verify account/environment/broker details before publication;
- observe acknowledgement, heartbeat, emergency stop, restart, and rollback;
- accept or reject checkpoint evidence. Owner acceptance never substitutes for
  failed deterministic checks.

## Definition of checkpoint completion

A checkpoint is complete only when:

- required source and forward migrations exist;
- focused and relevant full regressions pass;
- Docker/runtime OAT is proportional to the claim;
- MT5/browser OAT is complete where required, or the checkpoint is explicitly
  reported blocked and remains unaccepted;
- canonical documentation contains IDs, fingerprints, counts, commands/results,
  known limitations, and honest external dependencies;
- `git diff --check` passes and generated/runtime artifacts are excluded;
- the checkpoint receives explicit Owner acceptance.

## Contract acceptance phrase

```text
DITERIMA — KONTRAK ARK-S20
Mulai ARK-S20-00.
```

After acceptance, the contract documentation is committed and pushed before
ARK-S20-00 begins. No later checkpoint is authorized until its predecessor is
accepted.

## ARK-S20-00 completion evidence

ARK-S20-00 completed its documentation-only, read-only baseline audit on
2026-08-25. The concrete report is
[`SPRINT_20_00_BASELINE_AUDIT.md`](SPRINT_20_00_BASELINE_AUDIT.md).

The runtime contains zero historically `VALIDATED` StrategyVersions. The real
generic version remains `CONTRACT_VALID / FAIL / INELIGIBLE / NOT_VALIDATED`.
The S19 Router safety fingerprint remains exactly
`5a393e82923e66ec27a571ded95b3aa6b2c107aa806e5ba3aab04427a6b7c9c5`,
all six checks PASS, and its exact counts remain policy 1, eligibility 2,
decision 2, parameter 1, verifier 1, and five observed legacy deployments.

Backend regression is 249 passed; web regression is 28 passed across 10 files;
TypeScript, ESLint, optimized production build, Docker/API checks, and HTTP
checks pass. No S20 source, migration, runtime, deployment, MT5, order, or trade
mutation was introduced.

**ARK-S20-00 implementation status:** accepted and committed as `5932206`.

**Technical checkpoint claim:** `VALIDATED`, scoped only to this baseline audit
and never to strategy quality or trading authority.

## ARK-S20-01 completion evidence

ARK-S20-01 was accepted by the Owner on 2026-08-25. The
concrete report is
[`SPRINT_20_01_GENERIC_DEMO_CONTRACT.md`](SPRINT_20_01_GENERIC_DEMO_CONTRACT.md).

Migration `042_generic_demo_contract`, the immutable
`GENERIC_DEMO_CONTRACT_V1` artifact, exact eligibility/validation/create/read
APIs, and same-origin BFF routes are implemented. Exact retry and concurrency
reuse one artifact; all required negative boundaries fail closed; migration
recovery preserves legacy deployment/config records. Focused tests are 22
passed, full backend regression is 264 passed, web regression is 28 passed,
and lint/typecheck/local plus Docker production builds pass.

Runtime remains honestly `NO_VALIDATED_STRATEGY`: zero generic DEMO contracts,
five unchanged legacy deployments, and zero demo trades. A real-lineage create
attempt returned HTTP 422 and changed none of those counts. No configuration,
FILE_COMMON publication, deployment, MT5 action, order, trade, DEMO activation,
or LIVE authority was created.

**Technical checkpoint claim:** `VALIDATED`, scoped only to the immutable
pre-compilation contract foundation and never to strategy quality or trading
authority.

## ARK-S20-02 completion evidence

ARK-S20-02 was accepted by the Owner on 2026-08-26. The
concrete report is
[`SPRINT_20_02_DETERMINISTIC_MT5_COMPILER.md`](SPRINT_20_02_DETERMINISTIC_MT5_COMPILER.md).

Migration `043_generic_mt5_compilation`, one fingerprinted bounded adapter
registry, immutable canonical compiler artifacts, complete field lineage,
SHA-256 wire checksums, validation/create/read APIs, and same-origin BFF routes
are implemented. The exact registry fingerprint is
`868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea`.
Golden vectors prove completed-candle rule/timing, spread, Entry/SL/TP/size,
and `STOP_FIRST` semantics for the one supported M1 slice.

Focused regression is 33 passed, full backend regression is 280 passed, web
regression is 28 passed, and lint/typecheck/local plus Docker production builds
pass. Runtime remains zero generic DEMO contracts and zero compiler artifacts;
five legacy deployments and zero demo trades are unchanged. Missing-source
validation is honestly `INELIGIBLE`, creation returns HTTP 422, and restart
preserves the registry fingerprint. No FILE_COMMON configuration, deployment,
MT5 action, order, trade, DEMO activation, or LIVE authority was created.

**Technical checkpoint claim:** `VALIDATED`, scoped only to deterministic inert
compiler evidence and never to strategy quality or trading authority.

## ARK-S20-03 completion evidence

ARK-S20-03 was accepted by the Owner on 2026-08-26. Exact
evidence is recorded in
[`SPRINT_20_03_DEMO_PUBLICATION_AND_ACKNOWLEDGEMENT.md`](SPRINT_20_03_DEMO_PUBLICATION_AND_ACKNOWLEDGEMENT.md).

Migration `044_generic_mt5_publication`, fresh exact Owner authorization,
checksum-addressed compiler bytes, atomic publication manifest, bounded generic
EA adapter, exact DEMO account/server/symbol/protocol/checksum acknowledgement,
API lifecycle, and same-origin BFF routes are implemented. Exact retry and
concurrent publication have one winner; malformed or mismatched input fails
closed. MetaEditor64 compiles the EA with zero errors and zero warnings.

Focused regression is 28 passed, full backend regression is 286 passed, and
web regression is 28 passed; lint, typecheck, local/Docker production builds,
and restart OAT pass. Runtime truth remains zero contracts, compilations, and
publications because no historically eligible generic source exists. Five
legacy deployments and zero demo trades are unchanged; FILE_COMMON hash is
unchanged and no acknowledgement was fabricated.

**Technical checkpoint claim:** `VALIDATED`, scoped only to bounded DEMO
publication and exact acknowledgement evidence. It grants no LIVE authority
and makes no profitability or forward-performance claim.

## ARK-S20-04 completion evidence

ARK-S20-04 was accepted by the Owner on 2026-08-26. Exact
evidence is recorded in
[`SPRINT_20_04_GENERIC_FORWARD_TELEMETRY.md`](SPRINT_20_04_GENERIC_FORWARD_TELEMETRY.md).

Migration `045_generic_forward_telemetry`, checksum-bound generic MT5 event
ingestion, publication/sequence conflict protection, first-class no-trade and
blocker evidence, exact order/deal lineage, explicit cost/slippage availability,
and immutable forward-evidence snapshots are implemented. The EA persists event
sequence across restart and emits bounded local decision/order/deal/emergency
events; MetaEditor64 compiles with zero errors and zero warnings.

Focused regression is 34 passed, full backend regression is 292 passed, and
web regression is 28 passed; lint, typecheck, local/Docker builds, and restart
OAT pass. Runtime truth remains zero generic publications, events, and forward
evidence. Five legacy deployments, 6,389 separate legacy journal rows, zero
demo trades, and the FILE_COMMON hash are unchanged.

**Technical checkpoint claim:** `VALIDATED`, scoped only to immutable generic
DEMO telemetry and frozen forward-evidence semantics. It grants no LIVE
authority and makes no profitability or forward-performance claim.
