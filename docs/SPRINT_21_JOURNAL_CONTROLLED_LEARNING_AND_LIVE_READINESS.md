# Sprint 21 — Journal, Controlled Learning, and LIVE-Readiness Governance

**Contract status:** accepted by the Owner on 2026-08-26

**Active checkpoint:** ARK-S21-01 complete; awaiting Owner acceptance

**Implementation authority:** ARK-S21-01 immutable journal source/API scope
only; no incident workflow, learning proposal, readiness assessment, DEMO
action, or LIVE authority

## Product objective

Build an immutable governance layer over ARKANA's historical, Router, and
generic DEMO evidence so the Owner can answer four questions without weakening
the deterministic architecture:

1. What exactly happened, under which strategy/config/account/broker lineage?
2. Is there an unresolved safety, data-quality, or execution incident?
3. What research should be considered next, and which observations support it?
4. Is the complete evidence chain still blocked, insufficient, or ready only
   for an Owner LIVE-readiness review?

The intended bounded flow is:

```text
immutable historical / Router / generic DEMO evidence
  → lineage-preserving unified journal index
  → operational incident and recovery evidence
  → Owner-reviewed research proposal
  → new StrategyVersion/research workflow when explicitly authorized
  → immutable LIVE-readiness assessment
  → READY_FOR_OWNER_LIVE_REVIEW or fail-closed blocker
```

Sprint 21 does not implement LIVE deployment. It does not create a LIVE
configuration, endpoint, credential, order path, promotion, environment
fallback, or authorization token. `READY_FOR_OWNER_LIVE_REVIEW`, if ever
earned, means only that evidence is sufficient for a separate Owner decision
and future contract.

## Why this is the next milestone

Sprint 20 technically completes the generic DEMO compiler, publication,
acknowledgement, forward ledger, Owner UI, verifier, and restart controls. The
real runtime remains `BLOCKED_EXTERNAL_EVIDENCE`: there is no currently eligible
generic contract/publication and no Owner-terminal acknowledgement or generic
forward evidence.

It would be unsafe to add a LIVE path merely because technical plumbing exists.
ARKANA first needs a durable journal, explicit incident/recovery semantics,
controlled research feedback, and a fail-closed readiness assessment that can
honestly preserve the current blocked state.

## Locked architecture and safety boundaries

- Backtest V1 remains the sole canonical historical simulation kernel. No
  journal, learning, incident, or readiness service may replay or replace it.
- Existing historical, OOS/robustness, Router, legacy telemetry, generic DEMO
  telemetry, and frozen forward evidence remain separate domain records. The
  journal indexes exact references; it does not merge them into a synthetic
  performance dataset.
- Journal and governance artifacts are append-only and fingerprinted. Source
  evidence is never edited, deleted, relabeled, or silently superseded.
- Controlled learning means an auditable proposal for research. It is not
  online learning, automatic optimization, self-modifying code, parameter
  tuning, strategy selection, risk adjustment, or configuration publication.
- A proposal cannot become an executable strategy. Any accepted idea must
  create a new StrategyCandidate/StrategyVersion and pass the existing full
  historical evidence, promotion, Router, compiler, and DEMO gates.
- DEMO observations cannot leak into a previously frozen train/holdout/final-
  OOS result. Reusing evidence across a revision without exact new lineage
  fails closed.
- AI may summarize already-authorized research evidence or draft plain-language
  explanations. AI cannot classify incident severity, close an incident,
  confirm a learning proposal, change a strategy/risk/config, assess final
  readiness, place an order, or authorize DEMO/LIVE.
- MT5 remains the sole realtime DEMO execution owner. Web/API/database/AI never
  enter `OnTick` or position management.
- Lifecycle retirement, emergency stop, stale heartbeat, config mismatch,
  broker mismatch, corrupt telemetry, or unresolved high-severity incident
  must block readiness and preserve/trigger the existing new-entry block where
  applicable.
- Incident acknowledgement is not incident resolution. Resolution requires
  exact recovery evidence and never automatically removes an entry block.
- No LIVE endpoint, manifest, config, account credential, broker login,
  deployment, order, or trade may be introduced in Sprint 21.
- No secrets, broker credentials, personal identifiers, or raw account tokens
  may be stored in journal/readiness artifacts or exposed in UI/logs.
- Every checkpoint requires source, focused/full regression proportional to
  scope, runtime OAT, documentation, and explicit Owner acceptance.
- After acceptance, each checkpoint is committed and pushed before its
  successor begins. Generated databases, `tsbuildinfo`, FILE_COMMON payloads,
  compiled EA binaries, logs, and runtime artifacts are never committed.

## Status and claim vocabulary

- `OBSERVED`: an immutable journal item references exact source evidence. It is
  not a quality, profitability, or readiness conclusion.
- `INCIDENT_OPEN`: a deterministic policy found a safety/quality/operational
  issue that has not been resolved with evidence.
- `INCIDENT_OWNER_ACKNOWLEDGED`: the Owner has reviewed the incident; the
  blocker remains.
- `INCIDENT_RESOLVED_WITH_EVIDENCE`: an immutable recovery record proves the
  defined recovery checks. It does not erase the incident or authorize entry.
- `LEARNING_PROPOSAL_DRAFT`: evidence-backed research suggestion only.
- `LEARNING_PROPOSAL_OWNER_CONFIRMED`: permission to create a bounded research
  candidate/revision; not permission to validate, route, deploy, or trade it.
- `NOT_READY_FOR_LIVE`: one or more mandatory gates fail or are unavailable.
- `LIVE_READINESS_EVIDENCE_INSUFFICIENT`: integrity is valid but the frozen
  DEMO sufficiency policy has not genuinely been met.
- `READY_FOR_OWNER_LIVE_REVIEW`: all frozen governance checks pass. It is not
  `LIVE_AUTHORIZED`, is not a profitability promise, and creates no LIVE path.
- `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`: permanent Sprint 21 safety truth,
  including when readiness review evidence passes.
- Checkpoint claim `VALIDATED`: source, tests, required OAT, and documented
  boundaries for that checkpoint are verified. It never changes a strategy,
  DEMO, forward-evidence, or LIVE status.

## Checkpoint sequence

### ARK-S21-00 — Post-S20 baseline, source map, and policy freeze

Reconcile canonical documentation with accepted Sprint 20 and inventory the
real journal sources, evidence IDs/counts/fingerprints, incident signals,
runtime blocker, Docker/MT5 state, retention rules, privacy boundary, and
future readiness inputs. Freeze journal categories, severity policy, recovery
semantics, learning-proposal contract, readiness vocabulary, and fixture versus
real-evidence rules without adding implementation source.

Exit criteria:

- accepted S20 commit and all real runtime counts/fingerprints are exact;
- `BLOCKED_EXTERNAL_EVIDENCE` and its concrete missing prerequisites are
  preserved rather than converted into readiness;
- legacy journal, generic telemetry, Router, historical, and forward evidence
  sources are classified without merging them;
- incident severity, acknowledgement, resolution, entry-block, retention, and
  privacy policies are frozen;
- controlled-learning and readiness input/output schemas are specified;
- no model, migration, API, UI, EA, config, deployment, order, or trade change.

### ARK-S21-01 — Immutable unified journal index and lineage

Create a forward migration and an append-only journal index referencing exact
source records across historical lifecycle, Router decisions, generic DEMO
publication/acknowledgement, heartbeat, decisions/blockers, orders/deals/
positions, entry controls, and frozen forward evidence. Add deterministic
materialization and read APIs; do not copy mutable source payloads or infer
missing metrics.

Exit criteria:

- every item binds source type, source ID/fingerprint, strategy/config/account-
  reference/broker lineage where applicable, event time, observed time, and
  evidence scope;
- repeated and out-of-order ingestion is idempotent; concurrent exact writes
  have one winner; conflicting identity fails closed;
- source tampering, unknown type, cross-strategy/config linkage, invalid time,
  legacy/generic ambiguity, and missing mandatory lineage are rejected;
- historical, Router, legacy, and forward evidence remain explicitly labeled;
- pagination/filtering is deterministic and read APIs have no mutation side
  effect;
- no evidence mutation, second backtester, config/deployment/MT5 action, order,
  trade, or LIVE authority is created.

### ARK-S21-02 — Incident, acknowledgement, and recovery governance

Materialize deterministic incidents from frozen policy: stale/missing
heartbeat, lifecycle retirement/invalidation, publication/config mismatch,
telemetry conflict, emergency events, orphan order/deal lineage, cost/slippage
unavailability, broker/capital staleness, restart/recovery failure, and entry-
control failure. Add exact Owner acknowledgement and evidence-bound resolution.

Exit criteria:

- severity and reason codes are deterministic, versioned, and fingerprinted;
- exact retry/concurrency is single-winner; conflicting acknowledgement or
  recovery evidence is rejected;
- acknowledgement requires an exact Owner phrase and never closes the
  incident, changes risk/config, or removes an entry block;
- resolution requires incident-specific current recovery evidence and retains
  the immutable original incident/acknowledgement chain;
- high-severity/current lifecycle incidents keep readiness blocked and install
  or preserve the S20 fail-safe new-entry control where applicable;
- stale heartbeat, restart, corrupt control/config, retirement, rollback,
  unavailable service, and legacy isolation are regression-tested;
- no automatic unblocking, deployment, order, trade, or LIVE action exists.

### ARK-S21-03 — Controlled-learning proposal ledger

Create an immutable evidence-to-research proposal workflow. Deterministic rules
may group reviewed journal observations into a draft hypothesis, affected
contract blocks, expected validation scope, and explicit uncertainty. The
Owner may confirm a proposal only for creation of a new research candidate or
revision draft through existing Strategy Factory boundaries.

Exit criteria:

- proposals bind exact journal/incident/forward evidence fingerprints and
  never edit the observed source;
- duplicate/order-independent proposals reuse one fingerprint; divergent
  evidence or conclusions conflict;
- proposal generation cannot access hidden/final-OOS data outside an existing
  authorized evidence record and cannot reuse a prior version's acceptance;
- missing evidence, unresolved incident, unsupported block, look-ahead,
  unbounded parameter search, and untraceable AI text fail closed;
- Owner confirmation uses an exact phrase and creates at most a DRAFT
  candidate/revision with explicit provenance;
- no automatic confirmation, rule/parameter/risk mutation, `VALIDATED`
  promotion, Router selection, compilation, publication, DEMO/LIVE action,
  order, or trade occurs.

### ARK-S21-04 — Immutable LIVE-readiness assessment and verifier

Materialize a read-only readiness assessment over the exact current chain. The
frozen assessment requires current historically `VALIDATED` non-retired
lifecycle, capability/compiler/publication parity, exact Owner DEMO
acknowledgement, fresh connection health, sufficient risk-reviewed forward
evidence, current broker/capital evidence, resolved mandatory incidents, exact
entry-control state, and no legacy/LIVE contamination.

Exit criteria:

- the real runtime truth remains `NOT_READY_FOR_LIVE` while S20 external
  evidence is absent;
- `LIVE_READINESS_EVIDENCE_INSUFFICIENT` is distinct from failed integrity;
- only a fixture with every exact gate may produce
  `READY_FOR_OWNER_LIVE_REVIEW`, always accompanied by
  `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`;
- tamper, stale evidence, insufficient trades/days, missing costs/slippage,
  emergency/risk review, open incident, retirement, config mismatch, wrong
  broker/account, legacy source, and concurrent retry fail closed;
- the verifier recomputes all inputs and freezes one exact fingerprinted result;
- GET is read-only and no DELETE, promote, deploy, environment-change, or LIVE
  mutation route exists;
- no credentials, config publication, MT5 action, order, or trade is created.

### ARK-S21-05 — Owner governance UI, acceptance verifier, and closure

Expose journal timeline, exact evidence scope/lineage, open incidents,
acknowledgement versus recovery, controlled-learning proposals, real DEMO
evidence availability, readiness checks, blockers, and permanent no-LIVE-
authorization boundary in an Owner UI. Close with a complete-chain Sprint 21
verifier, full regression, migration/restart recovery, Docker/API/browser OAT,
and honest Owner MT5 evidence reporting.

Exit criteria:

- UI never displays `READY_FOR_OWNER_LIVE_REVIEW` from insufficient, fixture-
  only, stale, tampered, legacy, or unresolved-incident evidence;
- UI makes `Owner confirmed for research`, historical `VALIDATED`, DEMO active,
  forward sufficient, readiness review, and LIVE authorization unmistakably
  different;
- journal, incident, proposal, readiness, and complete-chain verifiers expose
  exact fingerprints and fail-closed checks;
- PostgreSQL/research/web restart preserves exact artifacts and does not remove
  entry controls or incident blockers;
- browser OAT has no console/network error and demonstrates blocked real state,
  acknowledgement/recovery boundaries, and no LIVE action;
- full regression covers tamper, idempotency, concurrency, restart, rollback,
  retirement, stale evidence, privacy, legacy isolation, and no-side-effects;
- real Owner-terminal evidence remains honestly available, insufficient, risk-
  reviewed, or absent; fixtures are never reported as real;
- no LIVE endpoint/config/credential/deployment/order/trade and no automatic
  learning/promotion exists.

## Frozen LIVE-readiness gates

All of the following must pass for the assessment label
`READY_FOR_OWNER_LIVE_REVIEW`. The label still grants no authority:

1. exact current non-retired historically `VALIDATED` StrategyVersion;
2. PASSED lifecycle and evaluator capability verification;
3. current broker metadata and capital contract with explicit freshness;
4. exact generic DEMO contract and deterministic compiler bytes;
5. Owner-authorized DEMO publication and exact Owner-terminal acknowledgement;
6. fresh checksum-bound heartbeat and coherent account/server/symbol/config;
7. frozen forward evidence meeting the accepted trade/day/event/cost/slippage
   policy with no required risk review;
8. no open mandatory incident or unresolved telemetry/order/deal conflict;
9. successful restart/recovery and exact entry/emergency control evidence;
10. complete journal and verifier lineage with no legacy or LIVE contamination;
11. explicit display of `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`.

Any missing, stale, failed, insufficient, unknown, or conflicting input returns
a typed blocker. No weighted score, best-effort fallback, implicit waiver, or
Owner click may override a failed deterministic gate.

## Required automated test matrix

The complete Sprint 21 acceptance regression must include at least:

1. exact source records materialize deterministic journal items;
2. duplicate/out-of-order retry and concurrent single-winner behavior;
3. source fingerprint, strategy/config/account/broker, time, and scope tamper;
4. historical/Router/legacy/generic-forward isolation;
5. missing metrics remain unavailable and never estimated;
6. every frozen incident type and severity reason;
7. acknowledgement cannot resolve or unblock an incident;
8. recovery requires current exact incident-specific evidence;
9. restart and corrupted cached config/control remain fail-safe;
10. learning proposals are evidence-bound, order-independent, and DRAFT-only;
11. no final-OOS leakage, unbounded optimization, or prior-evidence reuse;
12. AI unavailable/malformed/adversarial output cannot change deterministic
    state or governance outcome;
13. readiness positive fixture passes every gate without creating authority;
14. real absent/insufficient/stale/risk-reviewed evidence remains blocked;
15. retirement, broker/capital staleness, heartbeat, cost/slippage, emergency,
    orphan lineage, and open incidents block readiness;
16. migrations preserve all accepted historical, Router, deployment, journal,
    telemetry, forward-evidence, and verifier records;
17. PostgreSQL/API/web restart preserves exact fingerprints;
18. no DELETE of evidence and no LIVE/config/deploy/order/trade endpoint;
19. UI labels cannot collapse research confirmation, validation, DEMO,
    sufficiency, readiness review, and LIVE authorization;
20. deployment/order/trade counts and FILE_COMMON remain unchanged unless an
    explicitly authorized DEMO safety block is the checkpoint's tested action.

## Runtime and Owner OAT contract

Automated fixtures may prove journal, incident, proposal, and readiness logic,
but cannot impersonate the Owner's strategy, broker, account, MT5 terminal, or
forward performance. Every runtime report must distinguish:

- real persisted Owner evidence;
- isolated deterministic fixtures;
- historical versus forward evidence;
- unavailable external evidence;
- integrity failure versus evidence insufficiency versus risk review;
- readiness review versus LIVE authorization.

The current expected real outcome is `NOT_READY_FOR_LIVE` with
`BLOCKED_EXTERNAL_EVIDENCE`. This is a valid and required result until an
eligible strategy and genuine Owner MT5 DEMO chain exist.

Owner actions are required only when applicable evidence exists:

- review journal source lineage and incident severity;
- acknowledge an incident with the exact phrase without treating it as closed;
- review recovery evidence before any separate unblocking decision;
- confirm a controlled-learning proposal only for bounded research;
- run/observe an eligible strategy on the Owner MT5 DEMO terminal;
- verify account/server/symbol/config, heartbeat, restart, emergency control,
  costs, slippage, orders/deals/positions, and forward sufficiency;
- accept or reject checkpoint evidence. Acceptance cannot override failed
  deterministic gates or create LIVE authority.

## Definition of checkpoint completion

A checkpoint is complete only when:

- required source and forward-only migrations exist;
- focused and relevant full regressions pass;
- Docker/runtime/API/browser/MT5 OAT is proportional to the claim;
- immutable artifacts expose exact IDs, fingerprints, status, checks, inputs,
  blockers, and safety boundaries;
- real, fixture, historical, and forward evidence are labeled honestly;
- canonical documentation records commands/results, runtime counts,
  fingerprints, known limitations, and Owner OAT steps;
- `git diff --check` passes and generated/runtime artifacts are excluded;
- no second backtester, automatic learning/promotion, or LIVE action exists;
- the Owner explicitly accepts the checkpoint.

## Explicitly out of scope

- LIVE deployment, LIVE account selection, LIVE manifest/config publication;
- broker credentials, API keys, secrets, or terminal login handling;
- LIVE order/position management, canary trading, or capital allocation;
- automatic incident closure or automatic entry-control removal;
- automatic strategy/rule/parameter/risk/config mutation;
- automatic promotion, Router selection, DEMO publication, or trading;
- performance guarantees, profitability claims, or readiness scoring;
- Dynamic Discovery expansion, which remains SF-12 after governance is trusted.

## Contract acceptance and execution protocol

Accept and authorize only ARK-S21-00 with:

```text
DITERIMA — KONTRAK ARK-S21
Mulai ARK-S21-00.
```

After acceptance, this contract is committed and pushed before ARK-S21-00
begins. Every subsequent checkpoint requires its own explicit acceptance and
must be committed/pushed before the next checkpoint starts. Saying `lanjut`
after accepting a completed checkpoint authorizes full implementation of only
the named next checkpoint, not later checkpoints or LIVE behavior.

## ARK-S21-00 completion evidence

The Sprint 21 contract was accepted and pushed as `34fdd77` before work began.
ARK-S21-00 completed its documentation-only, read-only audit on 2026-08-26.
The concrete report is
[`SPRINT_21_00_BASELINE_SOURCE_MAP_AND_POLICY_FREEZE.md`](SPRINT_21_00_BASELINE_SOURCE_MAP_AND_POLICY_FREEZE.md).

The runtime remains `BLOCKED_EXTERNAL_EVIDENCE / NO_VALIDATED_STRATEGY` with
zero generic contracts, compilations, publications, acknowledgements,
telemetry events, forward evidence, or complete-chain verifiers. Six database
rows have status `VALIDATED`, but all are ineligible for the exact generic DEMO
chain and five are explicit `router-ready-*` fixtures. The current Router
safety audit also fails closed with `NO_TRADE_DECISION_NOT_EXACT` and
fingerprint
`db18ecca4d2d75ad4311e6f0972344fe489c18dbacfad5823b98dbb08098d2f4`.

The journal source map; fixture/real separation; incident severity,
acknowledgement and recovery semantics; retention/privacy policy; controlled-
learning schema; and readiness schema are frozen. No model, migration, API,
UI, EA, database row, FILE_COMMON payload, config, deployment, order, trade, or
LIVE action was changed.

**ARK-S21-00 technical claim:** `VALIDATED`, scoped only to the baseline audit
and policy freeze. Accepted by the Owner and pushed as `20cb924`.

## ARK-S21-01 completion evidence

ARK-S21-01 completed on 2026-08-26. The concrete report is
[`SPRINT_21_01_IMMUTABLE_UNIFIED_JOURNAL.md`](SPRINT_21_01_IMMUTABLE_UNIFIED_JOURNAL.md).

Migration 047, `GOVERNANCE_JOURNAL_INDEX_V1`, a closed 23-type source
registry, exact append-only materialization, source snapshot and lineage
fingerprints, fixture/legacy/unknown/real classification, account-reference
privacy, read-only verification, deterministic cursor pagination, FastAPI, and
same-origin BFF routes are implemented.

Focused regression is 11 passed, full backend regression is 304 passed, web
regression is 30 passed, TypeScript/lint/build pass, and Docker
migration/restart/API/BFF OAT pass. PostgreSQL records migration 047 once and
has zero journal items because startup/GET performs no implicit backfill.
Existing runtime counts and FILE_COMMON hashes are unchanged.

**ARK-S21-01 technical claim:** `VALIDATED`, scoped only to immutable journal
indexing and read verification. Owner acceptance remains pending.
