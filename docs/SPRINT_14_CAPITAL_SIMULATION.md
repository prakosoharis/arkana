# Sprint 14 — Broker-Realistic Historical Capital Simulation

## Milestone objective

Translate canonical historical trade evidence into an auditable account-capital
path without creating a second backtest kernel or overstating a strategy's
validation state. Sprint 14 has five Owner checkpoints:

1. **ARK-S14-01:** immutable capital and broker contract foundation;
2. **ARK-S14-02:** deterministic fixed-lot equity engine;
3. **ARK-S14-03:** fractional risk, compounding, and volume rounding;
4. **ARK-S14-04:** margin, unable-to-trade, and broker constraints;
5. **ARK-S14-05:** Owner UI, full-history verification, and acceptance.

The legacy compatibility strategy failed protocol V3. Capital simulation may
describe its account consequences, but it cannot relabel it `VALIDATED` or
authorize DEMO/LIVE.

## ARK-S14-01 implemented contract

`CAPITAL_BROKER_CONTRACT_V1` freezes the assumptions required by later capital
simulation:

- exact StrategyVersion id and checksum;
- exact MT5 broker metadata snapshot id and fingerprint;
- starting capital amount and three-letter account currency;
- `FIXED_LOT` or `FRACTIONAL_RISK` sizing policy;
- explicit compounding flag;
- leverage with mandatory `OWNER_INPUT` provenance because the current broker
  snapshot does not provide account leverage;
- maximum margin fraction and deterministic `REJECT_TRADE` behavior;
- explicit failure behavior for invalid volume, missing broker metadata, and
  unverified profit conversion;
- the matching MT5 `OrderCalcProfit` parity report.

The validator checks strategy-contract availability, canonical symbol,
currency, required broker fields, fixed-volume min/max/step, MT5 provenance,
and parity against the exact selected snapshot. The importer verifies the
selected database fingerprint against the exact `latest.ini` file and binds
the parity artifact to the same metadata collection time. Validator artifact
schema V2 carries `metadata_collected_at`; legacy V1 is accepted only when its
timestamp exactly equals the snapshot collection time. Identical normalized inputs
reuse one immutable row; any material input or evidence change changes the
fingerprint.

The only statuses introduced are:

- `CAPITAL_CONTRACT_READY`: all frozen inputs and exact broker parity are
  available for a future simulator;
- `BROKER_METADATA_INSUFFICIENT`: assumptions are recorded but the future
  simulator must remain blocked.

Neither status is an equity result, acceptance decision, StrategyVersion
promotion, deployment state, or trade instruction. ARK-S14-01 implements no
equity traversal, compounding, margin calculation, DEMO/LIVE action, or UI.

## API contract

- `POST /api/v1/capital-contracts/validate` returns the normalized contract and
  broker readiness assessment without persistence.
- `POST /api/v1/strategy-versions/{id}/capital-contracts` records or reuses the
  immutable contract.
- `GET /api/v1/strategy-versions/{id}/capital-contracts` returns its history.

## Owner Acceptance Test — ARK-S14-01

Automated verification:

```bash
DATABASE_URL=sqlite:////tmp/arkana-s14-01-oat.db \
DATA_ROOT=/tmp/arkana-s14-01-oat-data \
PYTHONPATH=services/research \
/path/to/python3.13-environment/bin/pytest services/research/tests -q

cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

API scenario:

1. Select a confirmed contract StrategyVersion and exact broker metadata
   snapshot.
2. Validate a V1 contract with explicit starting capital, sizing, leverage,
   margin, and failure policies.
3. Verify the assessment carries broker snapshot/parity lineage and returns
   `CAPITAL_CONTRACT_READY` only when all checks pass.
4. Confirm it, then repeat the same request and verify the same id/fingerprint
   with `reused: true`.
5. Verify a missing snapshot is explicitly insufficient and a non-V1 or
   implicit assumption is rejected.
6. Verify the StrategyVersion status and OOS lineage remain unchanged.

## Verification report — 2026-08-24

Implementation status: **COMPLETE, awaiting Owner acceptance**.

- focused broker/capital/API/migration OAT: 29 passed;
- complete research-service regression: 108 passed;
- web regression: lint passed, typecheck passed, 15 tests passed, and the
  production build completed successfully;
- migration 017: applied and recorded in the live PostgreSQL runtime; legacy
  rows were not rewritten;
- runtime broker snapshot: `a5a1dd90-b1dc-4c0a-86cb-81ca16bb88f6`,
  fingerprint
  `e25d9ba1aa8c2af0551948e795625ccefc1504c1bfda10b272158851c2e9c8ef`,
  `XAUUSD.m → XAUUSD`, account currency USD;
- MT5 OrderCalcProfit parity: PASSED for the exact snapshot, maximum absolute
  difference `5.457023721788801e-13` against tolerance `1e-8`; the existing V1
  artifact is bound through exact `latest.ini` fingerprint plus matching
  collection timestamp, and the updated MT5 validator script writes schema
  V2 with explicit `metadata_collected_at`;
- runtime contract: `cb7c739b-0961-4b94-b555-ede84ccd638e`, fingerprint
  `c05aed65f8f5ca3b5ceece3e44af522a52e12d2de82747dc8697bc0f7d8d436e`,
  starting USD 10,000, fixed 0.01 lot, leverage 500 owner input, maximum margin
  fraction 0.8;
- persistence: repeat confirmation reused the exact hardened contract; the
  earlier pre-hardening contract remains immutable rather than being rewritten;
- failure-safe evidence: missing snapshot returned
  `BROKER_METADATA_INSUFFICIENT`; schema version 2 returned HTTP 422; fixed lot
  0.015 is rejected against the broker's 0.01 step in regression;
- lifecycle safety: the failed compatibility StrategyVersion remains
  `CONTRACT_VALID`, with null validation evidence/timestamp and no DEMO/LIVE
  action;
- review hardening: a capital contract now requires a fully valid Strategy
  Contract, eligible lifecycle status, and matching checksum/config
  fingerprint; concurrent identical inserts recover the winning immutable row
  instead of returning an unhandled uniqueness error.

Existing FastAPI/naive-UTC/SQLite and frontend tooling deprecation warnings
remain non-failing. ARK-S14-02 has not started.
