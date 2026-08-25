# ARK-S20-00 — Post-S19 Baseline and Prerequisite Audit

**Audit date:** 2026-08-25

**Implementation status:** complete; awaiting Owner acceptance

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` here means only that the documentation-only baseline, read-only
runtime inventory, regression evidence, capability gaps, and safety boundaries
for ARK-S20-00 were verified. It is not a historically validated strategy,
DEMO activation, forward-validation result, profitability claim, LIVE
authorization, order, or trade.

## Scope and conclusion

ARK-S20-00 changed documentation only. It introduced no model, migration, API,
UI, EA, configuration, deployment, order, trade, or runtime mutation.

The post-S19 baseline is internally consistent and ready for ARK-S20-01 design,
but real generic DEMO execution is deliberately blocked:

- there are zero `VALIDATED` StrategyVersions;
- the real generic StrategyVersion remains `CONTRACT_VALID`, with historical
  decision `FAIL`, validation eligibility `INELIGIBLE`, and lifecycle claim
  `NOT_VALIDATED`;
- the generic completed-candle evaluator exists for historical evidence, but
  the current deployment compiler and MT5 EA accept only the legacy
  `BULLISH_REVERSAL_M1` envelope;
- the local Docker shared folder has no active `strategy.ini`, `telemetry.csv`,
  or `trades.csv`, so it supplies no current Owner-terminal acknowledgement or
  forward evidence.

## Accepted repository baseline

| Boundary | Exact evidence |
| --- | --- |
| S19 baseline | `6fcd85b` through `a001aa7`; Sprint 19 accepted and closed |
| S20 contract | `db0d156bf5f2c9129d1dfcbe886c4347c92dc1e8` |
| Remote | `HEAD == origin/main == db0d156` before this audit report |
| Forward migrations | 29 SQL files; runtime records versions `013` through `041`; no S20 migration exists |
| S20-00 source authority | documentation and read-only audit only |

## Runtime inventory

The inventory used read-only PostgreSQL transactions or read-only HTTP GETs.
It did not call deployment, acknowledgement, telemetry-sync, historical-sync,
promotion, retirement, Router-materialization, order, or trade endpoints.

### Strategy and historical lifecycle

| Item | Runtime truth |
| --- | --- |
| StrategyVersions | 6 total: 3 legacy/test `APPROVED`, 3 generic `CONTRACT_VALID`, 0 `VALIDATED`, 0 `RETIRED` |
| Real generic version | `37abb545-958d-4d14-a3b5-0b6f2321d8cf` / `s16-03-runtime-mtf-oat` v1 |
| Strategy checksum | `dff139b5f323578b975adb92bb1dcdb2e6b33a3e2c063e02c8708f0799d5f893` |
| Generic evidence decision | `FAIL`; fingerprint `8d99ad4cb8ba61ec9db8fa99c0dba44c4c046ada4d8c560a0490ed8a314e1e14` |
| Validation eligibility | one `INELIGIBLE`; fingerprint `064fb5672b456cc4b3ca3a41dd19b6505d5a3b753159f1f2b34e1fd4608582a9` |
| Promotion / retirement | 0 / 0 |
| Lifecycle verifier | `COMPLETED`, claim `NOT_VALIDATED`; fingerprint `1dc012671b6b5627821385e2e7c9996f9d359f0bc9dd394d1f7960be6dc74318` |

The full Owner dataset remains `UNVERIFIED_BROKER_TIME`. Its dataset ID is
`de5fa845-5397-441b-91dc-fe5f8ffc8e5b`, fingerprint is
`90607bc61349a86c17670bb5a328c58afdb2b00d828950d753eded5d878ae9bc`,
and the exact M1 asset contains 2,985,994 rows from
`2017-04-12 23:00:00` through `2026-08-20 18:00:00`. Historical sync is
`MT5_UNAVAILABLE`; the last good dataset remains active, but it is stale for a
current-decision or DEMO-readiness claim.

### Router closure

The read-only `STRATEGY_ROUTER_SAFETY_AUDITOR_V1` returns `PASSED` and
`READY_FOR_OWNER_ACCEPTANCE` with unchanged fingerprint
`5a393e82923e66ec27a571ded95b3aa6b2c107aa806e5ba3aab04427a6b7c9c5`.
All six checks pass.

| Artifact | Count / current result |
| --- | --- |
| Policies | 1 active |
| Eligibility snapshots | 2, both `INELIGIBLE` |
| Decisions | 2, both `NO_TRADE` |
| Parameter artifacts | 1, `NO_TRADE`, with no Entry/SL/TP/size |
| Verifiers | 1, `COMPLETED` / `READY_FOR_OWNER_ACCEPTANCE` |
| Existing deployments observed only | 5; unchanged by Router audit |

The latest exact Router chain is decision
`28bb2131-b0a1-4ea8-bd33-7e9eec0d27fe` → parameters
`e83e4952-02be-4e16-a735-675d5f9b8576` → verifier
`992d2fd9-6741-4e43-b8aa-c0d5932146af`. It selects no strategy and grants no
execution authority.

### Broker, capital, deployment, EA, and telemetry

| Area | Existing behavior | Generic S20 gap |
| --- | --- | --- |
| Capability registry | `STRATEGY_CAPABILITY_REGISTRY_V2`, 15 blocks, fingerprint `808d3506e7020b41d977fc8aae94f6cc6eb7a1c9e25a8093ea0bdb402a3b2bfb`; generic historical evaluator exists | no MT5 execution-capability declaration bound to an exact generic DEMO contract |
| Historical kernel | Backtest V1 remains the sole stateful kernel | no second backtester is permitted |
| Broker metadata | 2 MT5 snapshots; latest `XAUUSD.m` fingerprint `9734439f0787cbb5c9328f1e72f0d8bc29d86e86ea4d43a111dc0f4fbcf182ac` | freshness and exact binding must be checked at DEMO-contract creation |
| Capital | 5 `CAPITAL_CONTRACT_READY` rows, all for StrategyVersion `cd10121c-dffc-4b0e-9558-2abca2433298` | none is bound to the real generic StrategyVersion used by the current Router |
| Deployment records | 5 legacy DEMO rows: 3 `DEMO_ACTIVE`, 1 `AWAITING_ACK`, 1 `ROLLED_BACK` | existing records are historical legacy plumbing, not generic S20 evidence |
| Deployment API | requires legacy status `APPROVED`, emits schema v1 and fixed lot `0.01` | does not accept exact historical `VALIDATED` generic lifecycle or compile typed blocks |
| MT5 EA | DEMO guard, emergency stop, cached-last-valid config, exact symbol/checksum, local `OnTick` | accepts only `BULLISH_REVERSAL_M1`, LONG, M1, fixed `0.01`; no generic block interpreter/compiler acknowledgement |
| Shared files | only two pending historical-sync request files exist | no `strategy.ini`, `telemetry.csv`, `trades.csv`, or current Owner MT5 acknowledgement |
| Journal / trades | 6,389 historical journal rows; 0 demo trades | no separated generic forward-evidence ledger |
| LIVE / AI | deployment rejects non-DEMO; EA has no HTTP/LLM/ONNX path | must remain absent from deterministic compilation and execution |

Source hashes frozen for this audit:

- `ARKANA_ENGINE.mq5`:
  `13012ec544e10a94b965c1bf6f5790eece8498e8cfe35ba4c2492a472a422db2`;
- canonical legacy config fixture:
  `824716111335b6683a2699d1872c8615351cee9963693d25675b3be6034bbf4d`;
- disabled example config:
  `278a8d0de41abb0e5b8593c341feace79c0d8e5e9fd225da68b9553bd5a57b4a`.

## Fixture and claim policy

- An isolated test may create a synthetic historically `VALIDATED` generic
  StrategyVersion only to prove deterministic logic in S20-01/S20-02.
- Fixture IDs, acknowledgements, telemetry, trades, balances, or profits can
  never be presented as real Owner strategy or Owner MT5 evidence.
- Real runtime must remain `NO_VALIDATED_STRATEGY` until an exact real
  StrategyVersion earns historical `VALIDATED` through the accepted lifecycle.
- S20-03 through S20-05 must report `BLOCKED_EXTERNAL_EVIDENCE` until an actual
  eligible strategy and exact Owner-terminal DEMO acknowledgement exist.
- Historical validation, Router evidence, DEMO activation, and forward
  evidence remain separate claims and separate lineage.

## External OAT dependencies

ARK-S20-00 requires no Owner MT5 action. Later checkpoints may require:

1. a genuinely historically `VALIDATED` generic StrategyVersion;
2. an exact, fresh broker snapshot and capital contract;
3. Owner authorization using the displayed immutable phrase;
4. an Owner-controlled MT5 DEMO account and exact broker symbol;
5. EA compilation, config acknowledgement, heartbeat, emergency-stop,
   restart, and rollback evidence from that terminal;
6. sufficient real forward duration/trades before Owner review.

These are external evidence dependencies, not permission to fabricate data or
weaken eligibility.

## Verification evidence

Accepted evidence:

- backend: **249 passed** using the project Python 3.13 image, repository mounted
  read-only, isolated SQLite under `/tmp`, and isolated data/MT5 paths;
- web: **28 passed across 10 files**;
- TypeScript: passed;
- ESLint: passed, with the existing Next.js-plugin configuration warning;
- optimized Next.js production build: passed, 45 static pages generated;
- Docker: PostgreSQL healthy; research and web running;
- API: `/health` returned `ok`; Router safety report returned all checks PASS;
- Web HTTP: `/`, `/current-decision`, and `/deployments` returned 200;
- `git diff --check`: passed after the documentation update.

Rejected/non-evidence attempts are recorded transparently: the running research
image contains no tests and returned `no tests ran`; the host virtual
environment is Python 3.14 and is incompatible with the pinned SQLAlchemy
version during collection. Neither result was counted. The accepted backend
run used the same Python 3.13 runtime family as the research service and did not
touch PostgreSQL.

## Scope verification

- no source or migration added;
- no API, UI, EA, or config changed;
- no PostgreSQL write endpoint called;
- no deployment, acknowledgement, telemetry import, historical sync,
  promotion, retirement, Router artifact, order, or trade created;
- generated/runtime artifacts remain excluded from version control.

**ARK-S20-00 is ready for Owner acceptance with technical claim `VALIDATED`.**

Owner acceptance phrase:

```text
DITERIMA — ARK-S20-00
Lanjut ARK-S20-01.
```
