# ARK-S22-01 — Immutable Pre-Registered Campaign Ledger

**Date:** 2026-08-27

**Status:** implementation, automated regression, migration/restart recovery,
Docker/API/BFF OAT, and concrete report complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` is limited to the pre-registration ledger, its guards, the measured
baselines, and the recorded results below. It executes no trial, proves no
edge, and creates no `VALIDATED` strategy, DEMO, LIVE, capital, router, order,
or trade authority.

## Outcome

Migration 052 adds three append-only tables and
`BOUNDED_EDGE_SEARCH_CAMPAIGN_V1` records what will be searched before anything
is searched:

- `edge_search_campaigns` — the frozen grid, fingerprinted at creation;
- `edge_search_trials` — one row per grid point, recorded whether it survives
  or fails;
- `edge_search_final_oos_openings` — the budget itself.

The budget is an append-only ledger rather than a mutable integer. A counter
can be set back to zero; an accumulating ledger cannot. Consumed budget is
`COUNT(*)`, and the verifier rejects any gap in the opening sequence.

## Measured baselines that bounded the grid

ARK-S22-00 could not set an operative cap without measurement. Both required
numbers were measured against the registered 2,985,994-bar dataset.

**Per-trial wall clock.** One train+holdout trial costs about **40 s**
(train 1,791,596 bars ≈ 16 s, holdout 597,199 bars ≈ 12 s, plus plan setup).
Against the Owner-approved **8-hour** budget this yields an operative cap of
**720 trials**, well inside the frozen hard cap of 2,000.

**Trade-count scaling.** ARK-S22-00 assumed trades fall as `1/k²` and derived a
geometry ceiling of ×24. That assumption was wrong, and the contract's
requirement to measure it rather than assume it is what caught the error.
Measured on holdout at spread 0.25:

| stop scale | trades | win rate | profit factor |
|---|---|---|---|
| ×1 | 49,881 | 9.64% | 0.157 |
| ×5 | 17,561 | 33.98% | 0.759 |
| ×10 | 7,424 | 37.43% | 0.881 |
| ×20 | 2,504 | 40.58% | 1.005 |
| ×40 | 766 | 42.95% | 1.112 |
| ×80 | 219 | 45.66% | 1.236 |

The measured exponent is **1.24**, not 2.0. Trade counts stay above the
100-trade minimum far beyond ×24, so the geometry ceiling assumed at
ARK-S22-00 was needlessly tight and the grid now extends to ×80.

## Calibration disclosure, and why it is recorded in the campaign

Measuring the scaling law required reading holdout metrics for six
configurations before the grid could be pre-registered. That is information
leakage into grid design, and hiding it would defeat the purpose of
pre-registration.

The campaign therefore stores a mandatory `calibration_disclosure`, and
creation fails closed without one. It records the exact rule probed, the six
observed configurations with their metrics, the split read (`holdout only`),
and `final_oos_read: false`. **Final OOS was never touched**, so the decisive
test remains uncontaminated.

The disclosure also records the leading alternative explanation, because the
numbers above are not evidence of an edge. XAUUSD rose from roughly 1,250 in
2017 to roughly 4,600 in 2026. A LONG-only strategy with wide targets profits
from that drift with no rule skill whatsoever. The residual lift over the
zero-edge model is only **1.7–2.0 sigma** and is uniform across geometries,
which is the signature of drift rather than skill. The accepted year and regime
PnL concentration checks exist to test exactly this, and ARK-S22-02/03 must let
them do so.

## Guards implemented

| Guard | Behaviour |
|---|---|
| grid immutability | the grid is fingerprinted at creation; it cannot be extended, reordered, or pruned |
| declaration order | dimensions are canonically sorted, so re-declaring in a different order returns the same campaign rather than forking it |
| off-grid trials | a trial whose contract fingerprint is not in the frozen grid is refused |
| failure recording | `EXECUTED`, `INSUFFICIENT_EVIDENCE`, and `FAILED` are all first-class; nothing may be silently dropped |
| split isolation | every trial is `TRAIN_AND_HOLDOUT_ONLY` |
| final-OOS authorization | requires the exact phrase `AUTHORIZE_EDGE_SEARCH_FINAL_OOS_OPENING_V1` and an `EXECUTED` trial |
| budget | append-only, monotonic, one unit per survivor, exhaustion fails closed |
| double spend | re-opening the same trial returns the existing opening instead of consuming a second unit |
| concurrency | repeated and concurrent identical writes resolve to exactly one winner |
| spread | not a search dimension; fixed at the Owner-reported 0.25 |
| context timeframe | M1 only, so any survivor is deployable through the generic MT5 adapter |

## Broker spread capture

The exporter never read the spread, which is why the most leveraged number in
the evidence chain rested on an assumption that proved to be off by 12.5×.
[`ARKANA_BROKER_METADATA_EXPORTER.mq5`](../mt5/Scripts/ARKANA_BROKER_METADATA_EXPORTER.mq5)
now additionally exports `spread_points`, `spread_float`, `spread_price`,
`ask`, and `bid`. The fields are additive and are not added to the ingest
`REQUIRED` list, so previously exported snapshots remain valid.

The 0.25 assumption is still Owner-reported, not yet terminal-measured. It
becomes evidence with lineage the first time the Owner runs the updated
exporter.

## API and BFF boundary

Research API and same-origin BFF provide:

- `GET /api/v1/edge-search/policy-contract`;
- `POST /api/v1/edge-search/campaigns/validate` — read-only, creates nothing;
- `POST /api/v1/edge-search/campaigns` — the only write, idempotent;
- `GET /api/v1/edge-search/campaigns`, `.../{id}`, `.../{id}/trials`,
  `.../{id}/verification`.

There is no DELETE, no execution route, and no LIVE route; `/api/v1/live`
returns HTTP `404`.

## Automated verification

| Scope | Result |
|---|---|
| focused edge-search suite | **17 passed** |
| full backend regression | **356 passed** (339 before this checkpoint) |
| web Vitest | **31 passed across 12 files** |
| TypeScript | passed |
| ESLint | passed |
| Next production build | passed; **68** generated pages/routes, all six edge-search routes present |

## Runtime OAT — real, not fixture

Docker research/web rebuilt and restarted. PostgreSQL records migration 052
exactly once. One real campaign was pre-registered:

| Fact | Value |
|---|---|
| campaign ID | `320d1159-de1f-4a15-924b-7731933287d8` |
| fingerprint | `9c679ecda501991052d1749b632068e150a6f4a5a8a8d39f5a8572d2a7a973d4` |
| status | `PRE_REGISTERED` |
| pre-registered trials | **384** |
| estimated wall clock | 4.27 h, inside the 8 h budget |
| spread assumption | `0.25` |
| final-OOS budget | `3`, consumed `0` |
| verifier | `PASSED`, all 8 checks |
| repeated creation | `reused: true`, one row, no duplicate |
| after `docker compose restart research` | identical fingerprint, identical trial count |
| BFF policy / list / verification / trials | `200 / 200 / 200 / 200` |
| `/api/v1/live` | HTTP `404` |

Grid: stop scale {10, 20, 40, 80} × target ratio {1.0, 1.474, 2.0} × SMA fast
{2, 5} × SMA slow {10, 50} × relation {ABOVE, BELOW} × setup direction
{BULLISH, BEARISH} × trigger direction {BULLISH, BEARISH} = 384 trials.

Nothing else changed. Executed trials `0`, final-OOS openings `0`, and every
prior count is exact: 13 StrategyVersions, 10 OOS validations, 8 backtest runs,
5 legacy deployments, 6,389 legacy journal rows, 0 demo trades, and 2
FILE_COMMON files.

## Known limitations

1. **The 0.25 spread is Owner-reported, not measured.** The exporter can now
   capture it; until the Owner runs it, the campaign rests on a stated value.
2. **Six holdout configurations were observed before pre-registration.** This
   is disclosed in the campaign rather than concealed. Holdout is no longer
   fully independent for those points; final OOS is untouched and remains the
   decisive test.
3. **The promising profit factors above are most likely gold drift.** They are
   recorded as calibration, never as a result.
4. **No trial has executed.** Trial and opening counts are honestly zero.

## Owner OAT steps

```bash
docker compose up -d --build research web
curl -fsS http://localhost:8001/api/v1/edge-search/policy-contract
curl -fsS http://localhost:8001/api/v1/edge-search/campaigns
curl -fsS http://localhost:8001/api/v1/edge-search/campaigns/320d1159-de1f-4a15-924b-7731933287d8/verification
curl -fsS http://localhost:3000/api/v1/edge-search/campaigns
```

**ARK-S22-01 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S22-01
```
