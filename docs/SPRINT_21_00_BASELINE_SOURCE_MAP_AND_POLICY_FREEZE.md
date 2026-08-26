# ARK-S21-00 — Post-S20 Baseline, Source Map, and Policy Freeze

**Audit date:** 2026-08-26

**Implementation status:** complete; awaiting Owner acceptance

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` means only that the documentation-only baseline, read-only source
inventory, policy freeze, schemas, and safety boundaries required by
ARK-S21-00 were verified. It is not strategy validation, incident resolution,
DEMO activation, forward sufficiency, LIVE readiness, profitability, an order,
or a trade.

## Scope and conclusion

ARK-S21-00 changed documentation only. It introduced no model, migration, API,
UI, EA, configuration, deployment, acknowledgement, telemetry, incident,
entry-control action, order, trade, or runtime mutation.

The post-S20 baseline is suitable for ARK-S21-01 design, but the real runtime
must remain fail-closed:

- the generic DEMO Owner overview returns `BLOCKED_EXTERNAL_EVIDENCE` and
  eligibility returns `NO_VALIDATED_STRATEGY`;
- every generic S20 runtime table contains zero rows: no contract,
  compilation, publication, acknowledgement, event, forward evidence, or
  complete-chain verifier exists;
- six rows have database status `VALIDATED`, but five are clearly named
  `router-ready-*` regression fixtures and the sixth lacks an exact lifecycle
  and capability chain. All six are `INELIGIBLE_SOURCE` for generic DEMO;
- the latest Router safety audit is `FAILED` because its latest fixture chain
  is no longer exact (`NO_TRADE_DECISION_NOT_EXACT`);
- only legacy DEMO files and legacy journal evidence are observable, and their
  timestamps are stale. They cannot satisfy a generic or LIVE-readiness gate.

Neither fixture cleanup nor runtime repair is authorized by this checkpoint.
The journal and readiness design must preserve these facts as typed blockers.

## Accepted repository baseline

| Boundary | Exact evidence |
| --- | --- |
| Sprint 20 delivery | `9fcfc38`; ARK-S20-00 through ARK-S20-05 accepted |
| Sprint 21 contract | `34fdd77fa7993a0166c4644a6b60031854726f24` |
| Remote before this report | `HEAD == origin/main == 34fdd77` |
| Forward migrations | 34 SQL files; runtime versions `013` through `046`; no S21 migration |
| ARK-S21-00 authority | documentation and read-only audit only |
| Canonical baseline fingerprint | `8dbb9cd776ff777a4214615aa947cb79654336d791da6ce243bb2ba3744d5653` |

The baseline fingerprint is SHA-256 over the accepted commit, migration count,
key runtime counts, Router safety result/fingerprint, EA hash, and observed
legacy FILE_COMMON hashes listed below. It is an audit convenience, not a new
database artifact.

## Runtime and infrastructure inventory

Docker reported PostgreSQL healthy and research/web running. Read-only HTTP
checks returned research `/health` = `ok`, generic Owner overview =
`BLOCKED_EXTERNAL_EVIDENCE`, generic eligibility = `NO_VALIDATED_STRATEGY`,
and web `/demo-forward` = HTTP 200.

All database inventory statements ran inside `BEGIN READ ONLY` transactions.
No POST, PUT, PATCH, DELETE, sync, materialize, reconcile, publication,
acknowledgement, retirement, Router decision, or control endpoint was called.

### Core runtime counts

| Source | Count / current truth |
| --- | --- |
| schema migrations | 34, through `046_generic_demo_chain_verifier` |
| StrategyVersions | 13: 3 `APPROVED`, 4 `CONTRACT_VALID`, 6 `VALIDATED`, 0 `RETIRED` |
| StrategyCandidates | 7 |
| historical backtests / OOS validations | 8 / 10 |
| generic robustness / decisions / confirmations / verifications | 6 / 6 / 5 / 6 |
| generic validation eligibility / promotion / retirement / lifecycle verifier | 6 / 5 / 0 / 6 |
| Router policies / eligibility / decisions / parameters / verifiers | 1 / 7 / 6 / 4 / 3 |
| legacy deployments | 5: 3 `DEMO_ACTIVE`, 1 `AWAITING_ACK`, 1 `ROLLED_BACK` |
| legacy journal / demo trades | 6,389 / 0 |
| broker snapshots / capital contracts | 2 / 5 |
| generic DEMO contracts / compilations | 0 / 0 |
| generic publications / telemetry events | 0 / 0 |
| generic forward evidence / chain verifiers | 0 / 0 |

### Fixture and real-evidence classification

Database status alone is never enough to classify evidence as real:

| Observed rows | Classification | Consequence |
| --- | --- | --- |
| five `router-ready-*` StrategyVersions created on 2026-08-26 | deterministic regression fixtures | excluded from real Owner strategy, DEMO, forward, and readiness claims |
| `s13-03-passing-lineage` with status `VALIDATED` | acceptance fixture without exact current lifecycle/capability chain | `INELIGIBLE_SOURCE`; excluded |
| `s16-03-runtime-mtf-oat` | real historical OAT lineage, `CONTRACT_VALID / FAIL / INELIGIBLE` | not eligible for DEMO |
| five legacy deployments | legacy execution plumbing | never generic S20/S21 evidence |
| 6,389 `journal_events` | legacy DEMO observations | indexed only as `LEGACY_DEMO`; never mixed with generic forward evidence |
| zero generic S20 chain rows | real runtime absence | `BLOCKED_EXTERNAL_EVIDENCE` |

The currently eligible generic strategy list is empty. A future journal must
carry an explicit `evidence_origin` and `evidence_scope`; it must not infer
realness from `VALIDATED`, `DEMO_ACTIVE`, or a table name.

### Current exact blockers and signals

| Signal | Exact observation | Frozen interpretation |
| --- | --- | --- |
| Generic Owner overview | `BLOCKED_EXTERNAL_EVIDENCE` | mandatory external-evidence blocker |
| Generic eligibility | `NO_VALIDATED_STRATEGY`; 0 eligible IDs | no generic contract may be created |
| Router safety | `FAILED / NOT_READY_FOR_OWNER_ACCEPTANCE` | mandatory integrity blocker |
| Router fingerprint | `db18ecca4d2d75ad4311e6f0972344fe489c18dbacfad5823b98bb08098d2f4` | exact read-only audit result |
| Router failure code | `NO_TRADE_DECISION_NOT_EXACT` | fixture-chain inconsistency; no silent repair |
| Historical sync | `MT5_UNAVAILABLE`; last good market time `2026-08-25 09:59:00` | stale/unavailable external input |
| Latest broker snapshot | `9734439f0787cbb5c9328f1e72f0d8bc29d86e86ea4d43a111dc0f4fbcf182ac`, collected `2026.08.24 19:19:45` | not fresh for a future readiness assessment |
| Capital contracts | 5, all bound to `cd10121c-dffc-4b0e-9558-2abca2433298` | none binds an eligible generic chain |
| Generic acknowledgement/heartbeat | absent | mandatory external-evidence blocker |
| Generic cost/slippage/trades/days | unavailable | evidence unavailable, not zero and not sufficient |
| LIVE implementation | absent | `LIVE_AUTHORIZATION_NOT_IMPLEMENTED` |

No S21 incident rows exist yet. These are baseline signals and future
deterministic incident/readiness inputs, not incidents fabricated by the audit.

### EA and FILE_COMMON observation

The current EA hash is:

- `mt5/Experts/ARKANA_ENGINE.mq5`:
  `c15418e76deee4b3d3cb1c002692e1974b97a1f95334fa95dfcb1533223f53ad`.

The Owner terminal Common Files `Arkana` folder contains only legacy files:

| File | Size / observed time | SHA-256 / classification |
| --- | --- | --- |
| `strategy.ini` | 323 bytes / 2026-08-10 05:35:53 +07 | `00b5994401545542b7a9ae14151826d11dccae6b5244efd78194151999db0e08`; legacy schema v1 |
| `strategy.ini.oat-backup` | 322 bytes / 2026-08-10 05:30:15 +07 | `b1c667b9133f4b2f365664fd7023262775ac6d6275efb82078bc134e539c608b`; legacy backup |
| `telemetry.csv` | 819,385 bytes, 9,194 lines / 2026-08-12 01:18:23 +07 | `a76b793a2894cbb5a61cc435d94b9e2d276e878c0f8d7e591d381b27bd6bdddd`; legacy telemetry |

The database's latest legacy event timestamp is `2026.08.11 21:18:21` and
latest observation is `2026-08-11 18:18:31.028723`. The file/database line-count
difference is not interpreted or repaired here. No generic manifest, generic
control file, acknowledgement, or generic telemetry is present.

## Frozen journal source map

ARK-S21-01 may create only a reference index over these existing immutable or
treated-as-immutable source categories. It must never copy them into a blended
performance record.

| Source type | Physical source | Scope | Mandatory lineage / handling |
| --- | --- | --- | --- |
| `HISTORICAL_BACKTEST` | `backtest_runs` | historical | StrategyVersion, dataset, source fingerprint, event/created time |
| `HISTORICAL_OOS` | `oos_validations` | historical OOS | StrategyVersion, dataset, protocol, fingerprint |
| `HISTORICAL_ROBUSTNESS` | `generic_robustness_evidence` | historical robustness | exact OOS and dataset lineage |
| `HISTORICAL_DECISION` | `generic_evidence_decisions` and verifications | historical governance | exact decision/verification fingerprints |
| `LIFECYCLE` | eligibility, confirmation, promotion, retirement, lifecycle verifier | historical governance | exact transition chain; never infer from status alone |
| `ROUTER_ELIGIBILITY` | `strategy_router_eligibilities` | Router snapshot | policy, lifecycle, dataset, evaluated time |
| `ROUTER_DECISION` | `strategy_router_decisions` | Router current decision | selected lineage or explicit `NO_TRADE` |
| `ROUTER_PARAMETERS` | `strategy_router_decision_parameters` | Router calculation | decision, broker/capital lineage; never an order |
| `ROUTER_VERIFICATION` | `strategy_router_verifications` / safety report | Router governance | exact source fingerprints and current audit result |
| `LEGACY_DEPLOYMENT` | `deployments` | legacy DEMO | explicit `LEGACY_DEMO`; never generic |
| `LEGACY_JOURNAL` | `journal_events` | legacy DEMO | deployment when available, raw fingerprint, event/observed time |
| `LEGACY_TRADE` | `demo_trades` | legacy DEMO | deployment/config/deal lineage; currently zero |
| `GENERIC_DEMO_CONTRACT` | `generic_demo_contracts` | generic DEMO pre-compilation | exact lifecycle/capability/broker/capital lineage |
| `GENERIC_COMPILATION` | `generic_mt5_compilations` | generic DEMO compiler | contract, registry, config checksum |
| `GENERIC_PUBLICATION` | `generic_mt5_publications` | Owner-authorized generic DEMO | compilation, authorization fingerprint, redacted account reference |
| `GENERIC_TELEMETRY` | `generic_mt5_telemetry_events` | generic DEMO forward | publication, sequence, config, strategy, event/observed time |
| `GENERIC_FORWARD_EVIDENCE` | `generic_forward_evidence` | frozen generic DEMO forward | publication, event fingerprints, policy/window |
| `GENERIC_CHAIN_VERIFICATION` | `generic_demo_chain_verifications` | generic DEMO governance | publication and forward evidence fingerprints |

Broker metadata, capital contracts, datasets, entry/emergency control files,
and external connection health are supporting inputs. They may be referenced
by exact fingerprint but never exposed as credentials or silently converted to
strategy performance.

## Frozen journal item schema

The ARK-S21-01 persisted schema must represent at least:

```text
schema_version
journal_item_id
journal_fingerprint
source_type
source_id
source_fingerprint
evidence_origin = REAL_OWNER | FIXTURE_OAT | LEGACY | UNKNOWN
evidence_scope = HISTORICAL | ROUTER | LEGACY_DEMO | GENERIC_DEMO_FORWARD
strategy_version_id? / strategy_checksum?
config_checksum? / publication_id?
account_reference_hash? / broker_symbol?
event_time
observed_time
integrity_status
created_at
```

Rules:

- `source_type + source_id + source_fingerprint + scope + lineage` determines
  identity; exact retry reuses one item and divergent identity conflicts;
- event time and observed time remain distinct and use explicit UTC-normalized
  semantics while preserving the original source representation;
- missing metrics remain unavailable; zero is never substituted;
- legacy, fixture, historical, Router, and generic forward scopes cannot be
  promoted or merged by pagination/filtering;
- journal rows are append-only references. Source records remain authoritative.

## Frozen incident, acknowledgement, and recovery policy

### Severity

| Severity | Examples | Required behavior |
| --- | --- | --- |
| `CRITICAL` | LIVE contamination, emergency-control failure, corrupt active config, wrong environment/account, lifecycle invalidation while active | readiness blocked; preserve/install DEMO entry block where an exact generic publication exists |
| `HIGH` | stale/missing generic heartbeat, publication/config mismatch, unresolved order/deal lineage, retirement, restart recovery failure, Router integrity failure | readiness blocked; entry block where policy applies |
| `MEDIUM` | costs/slippage unavailable, broker/capital stale, telemetry conflict not affecting active control | readiness blocked or evidence insufficient according to typed policy; Owner review required |
| `LOW` | non-safety metadata completeness issue with intact lineage | remains visible; cannot be silently ignored or reclassified |

Severity and reason code are deterministic outputs of a versioned policy. AI,
UI text, or an Owner click cannot choose or lower severity.

### Acknowledgement

- acknowledgement is append-only and binds exact incident ID/fingerprint,
  policy version, Owner phrase fingerprint, and timestamp;
- the future exact phrase must include the incident identifier and the literal
  intent `ACKNOWLEDGED — BLOCK REMAINS`;
- acknowledgement never closes an incident, changes strategy/risk/config, or
  removes an entry block.

### Recovery and resolution

- resolution requires incident-specific current evidence created after the
  incident: exact heartbeat/config/control/restart/order lineage as applicable;
- recovery binds every source fingerprint and produces a new immutable record;
- the original incident and acknowledgement remain visible forever;
- resolution does not automatically remove a DEMO entry block. Any future
  unblocking needs a separate Owner-governed contract and exact current gates;
- retries are idempotent and conflicting recovery evidence fails closed.

## Frozen retention and privacy policy

- journal, incident, acknowledgement, recovery, proposal, and readiness
  artifacts are append-only for the lifetime of this local repository unless a
  later Owner-approved archival contract defines a longer-lived external copy;
- no DELETE endpoint or cascading application deletion is permitted for these
  governance artifacts;
- source payload retention remains owned by the source domain. Journal records
  retain IDs/fingerprints even when a source is administratively archived;
- raw account login, broker credentials, API keys, access tokens, terminal
  paths containing user identity, free-form personal identifiers, and secrets
  are prohibited in journal/UI/log output;
- account identity is represented only by an application-scoped deterministic
  reference hash plus a non-secret Owner label when required;
- raw telemetry is not duplicated into the journal; only allowlisted summary
  fields and its exact source fingerprint are exposed;
- fixture provenance is mandatory and cannot be relabeled `REAL_OWNER`.

## Frozen controlled-learning proposal schema

ARK-S21-03 may persist only an evidence-bound research proposal:

```text
schema_version / policy_version
proposal_id / proposal_fingerprint
status = LEARNING_PROPOSAL_DRAFT | LEARNING_PROPOSAL_OWNER_CONFIRMED
source_journal_item_ids_and_fingerprints[]
source_incident_ids_and_fingerprints[]
hypothesis_text
affected_contract_blocks[]
bounded_validation_scope
uncertainties[] / exclusions[]
generator = DETERMINISTIC | AI_DRAFT_ASSISTED
ai_interaction_id? / owner_confirmation_fingerprint?
created_at / confirmed_at?
```

Confirmation can create at most one new DRAFT candidate/revision through the
existing Strategy Factory. It cannot reuse final-OOS acceptance, mutate an
existing strategy, promote, route, compile, publish, deploy, or trade.

## Frozen LIVE-readiness assessment schema

ARK-S21-04 must freeze a read-only assessment containing:

```text
schema_version / verifier_version
assessment_id / assessment_fingerprint
evaluated_at
strategy_version_id / strategy_checksum
exact_input_ids_and_fingerprints{}
gates{name,status,observed,expected,reason_code}[]
status = NOT_READY_FOR_LIVE |
         LIVE_READINESS_EVIDENCE_INSUFFICIENT |
         READY_FOR_OWNER_LIVE_REVIEW
blockers[]
evidence_origin_summary
live_authorization = LIVE_AUTHORIZATION_NOT_IMPLEMENTED
```

The eleven gates frozen in the Sprint 21 contract are conjunctive. Any unknown,
fixture-only, stale, missing, failed, insufficient, or conflicting input emits
a typed blocker. There is no score, override, waiver, side effect, config,
credential, endpoint, deployment, order, or trade.

The expected assessment over the current real runtime is:

```text
status = NOT_READY_FOR_LIVE
blockers include BLOCKED_EXTERNAL_EVIDENCE,
                 NO_VALIDATED_STRATEGY,
                 ROUTER_INTEGRITY_FAILED,
                 BROKER_OR_CAPITAL_STALE_OR_UNBOUND,
                 GENERIC_ACK_HEARTBEAT_FORWARD_EVIDENCE_MISSING
live_authorization = LIVE_AUTHORIZATION_NOT_IMPLEMENTED
```

## Verification evidence

- backend regression: **297 passed** using Python 3.13, isolated SQLite under
  `/tmp`, isolated data/MT5 paths, and the repository mounted read-only;
- web regression: **30 passed across 11 files**;
- TypeScript: passed;
- ESLint: passed;
- contract commit and remote equality: passed at `34fdd77` before this audit;
- 34 forward migrations through `046`: observed read-only;
- complete public table counts: captured inside PostgreSQL read-only
  transactions;
- Docker: PostgreSQL healthy; research and web running;
- API: health, generic eligibility, generic Owner overview, and Router safety
  endpoints inspected through GET only;
- web: `/demo-forward` returned 200;
- FILE_COMMON: names, sizes, timestamps, keys/header, line count, and SHA-256
  inspected without modification;
- repository scope: only documentation changed by ARK-S21-00;
- `git diff --check`: required before handoff.

One backend attempt with the repository mounted at a path shallower than the
test suite's required workspace topology was rejected during collection with
six `Path.parents[3]` errors. It was not counted. The accepted rerun restored
the real `/workspace/services/research` depth and passed all 297 tests; neither
attempt connected to Owner PostgreSQL or FILE_COMMON.

## Scope verification

- no source or migration added;
- no database row or runtime file created, edited, deleted, or relabeled;
- no API/UI/EA/config changed;
- no acknowledgement, telemetry sync, historical sync, materialization,
  reconciliation, promotion, retirement, incident, recovery, control,
  deployment, order, or trade action called;
- generated/runtime artifacts remain excluded from version control;
- LIVE remains absent and locked.

**ARK-S21-00 is ready for Owner acceptance with technical claim `VALIDATED`.**

Owner acceptance phrase:

```text
DITERIMA — ARK-S21-00
Lanjut ARK-S21-01.
```
