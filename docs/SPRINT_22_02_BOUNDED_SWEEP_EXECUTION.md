# ARK-S22-02 — Deterministic Bounded Sweep Over Train and Holdout

**Date:** 2026-08-27

**Status:** implementation, automated regression, and full pre-registered sweep
complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the executor, its guards, and the completed sweep recorded
below. It is not a claim that an edge was found. Final OOS was never read, no
strategy was selected or promoted, and no DEMO, LIVE, capital, router, order,
or trade authority was created.

## Outcome

All **384** pre-registered trials executed and recorded. The budget of three
final-OOS openings remains untouched at `0 / 3`.

| Fact | Value |
|---|---|
| trials recorded | **384 / 384**, `complete: true` |
| `EXECUTED` | 192 |
| `INSUFFICIENT_EVIDENCE` | 192 |
| `FAILED` | 0 |
| holdout survivors | **73** |
| total compute | 26.68 hours across parallel workers, mean 250 s/trial |
| final-OOS consumed | **0 / 3** |

The 192 `INSUFFICIENT_EVIDENCE` rows are exactly the grid points whose setup and
trigger directions contradict each other. They open no position and are
therefore also the most expensive trials to run, because the evaluator
re-evaluates every bar and never skips ahead inside a position.

## The result: geometry decides everything, the rules decide nothing

Survivors by stop-distance scale:

| scale | stop distance | survivors | executed | total |
|---|---|---|---|---|
| ×10 | 2.83 | **0** | 48 | 96 |
| ×20 | 5.66 | **0** | 48 | 96 |
| ×40 | 11.32 | 25 | 48 | 96 |
| ×80 | 22.64 | **48** | 48 | 96 |

At ×80 the survival rate is **100%**. Every rule combination that trades at all
clears the holdout criterion:

| relation | setup | trigger | survivors | executed |
|---|---|---|---|---|
| ABOVE | BEARISH | BEARISH | 12 | 12 |
| ABOVE | BULLISH | BULLISH | 12 | 12 |
| BELOW | BEARISH | BEARISH | 12 | 12 |
| BELOW | BULLISH | BULLISH | 12 | 12 |
| (mismatched setup/trigger) | | | 0 | 0 |

Profit factor across those 48 survivors ranges 1.1556 to 1.4699, mean 1.2712.

This is the decisive observation of the sprint. `SMA_RELATION` `ABOVE` and
`BELOW` are opposite market conditions. A `BEARISH` two-bar reversal and a
`BULLISH` one are opposite setups. **All of them survive at identical rates.**
If any rule carried predictive information, some variants would clear the gate
and their opposites would not. Instead the rule is irrelevant and only the
stop-distance scale separates survivors from non-survivors.

## Interpretation: this is drift exposure, not an edge

The mechanism is the one recorded in the campaign's `calibration_disclosure`
before the sweep began, now confirmed by the structure of the results rather
than asserted.

At ×80 the stop is 22.64 and the target 45.28. Reaching either barrier requires
holding a position for days to weeks. XAUUSD rose from roughly 1,250 in 2017 to
roughly 4,600 in 2026. A LONG-only position held over that horizon captures the
secular uptrend regardless of when it opened. The strategy is not predicting
anything; it is buying time in a rising market, and the entry rule only decides
which minute it starts.

The zero-edge barrier model predicts a profit factor of about 0.98 at that
geometry. The observed 1.27 mean is the drift the driftless model does not
contain. Narrow geometries (×10, ×20) resolve within minutes to hours, capture
no meaningful drift, and produce zero survivors — exactly as the mechanism
predicts.

**No survivor in this campaign should be read as a discovered edge.**

## What this means for ARK-S22-03

The accepted gate already contains the instrument that tests this
interpretation: `year_pnl_concentration` and `regime_pnl_concentration`, both
capped at 0.50 and calibrated on train bars only. A strategy whose profit comes
from a bull run should concentrate its PnL in the rising years and be rejected.

Two defensible options for the Owner, both honest:

1. **Spend zero budget.** The rule-independence result is already conclusive on
   its own terms; final OOS cannot make a rule-independent result into an edge.
   Record `NO_EDGE_FOUND` and move to ARK-S22-04's conditional registry
   extension.
2. **Spend exactly one unit** on the single best survivor, not to look for a
   pass but to confirm that the concentration checks reject a drift artifact.
   Demonstrating that the gate correctly refuses a plausible-looking result is
   itself worth recording, and it leaves two units unspent.

The choice belongs to the Owner. This checkpoint takes neither.

## Executor guards, proven in practice rather than only in tests

The sweep survived three unplanned failures during its run, and the ledger came
through each one exact:

- a Postgres container recreation, triggered when `docker compose` detected an
  edited Compose file, which killed two workers mid-query;
- a full Docker Desktop shutdown that stopped every container;
- deliberate worker termination during a rebalance.

After each, the recorded trial count was intact with no loss and no duplicate,
and workers resumed from the ledger. Append-only rows with a per-trial commit,
plus the `(campaign_id, contract_fingerprint)` unique constraint, are what made
that true. Resumability was designed and tested before it was needed; it was
then needed three times.

Guards enforced by the executor:

| Guard | Behaviour |
|---|---|
| final-OOS isolation | `_permitted_bounds` returns train and holdout only; a test asserts every recorded `end_exclusive` precedes the final-OOS boundary |
| survivor criterion | not a new threshold; asserted equal to the accepted `OOS_HISTORICAL_REVIEW_V3` gate's holdout side |
| failure recording | failures and thin evidence are recorded, never dropped |
| dataset drift | a changed dataset fingerprint fails closed |
| idempotence | re-running a completed trial returns the stored row, never a second replay |
| no second backtester | the existing generic evaluator and the sole Backtest V1 kernel are reused unchanged |
| selection | ranking orders survivors and selects nothing |

## API and BFF boundary

- `POST /api/v1/edge-search/campaigns/{id}/execution` — runs pending trials,
  optional `max_trials`, safe to call again to resume;
- `GET  /api/v1/edge-search/campaigns/{id}/execution` — progress;
- `GET  /api/v1/edge-search/campaigns/{id}/survivors` — ranking with mandatory
  selection disclosure.

No DELETE, no final-OOS route, no LIVE route.

## Automated verification

| Scope | Result |
|---|---|
| focused executor suite | **12 passed** |
| full backend regression | **385 passed** |
| web Vitest / typecheck / lint / build | 31 passed / passed / passed / 68 routes |
| GitHub Actions CI | first real run **green** across all three jobs |

## Known limitations

1. **The spread assumption is still Owner-reported.** Every number here rests
   on 0.25. The updated exporter can capture it from the terminal; until then
   the campaign answers a question whose cost input is stated, not measured.
2. **Holdout is not fully independent** for the six configurations observed
   during ARK-S22-01 calibration. This is recorded in the campaign. Final OOS
   remains untouched.
3. **Year and regime concentration were not computed during the sweep.** They
   are final-gate inputs and were deliberately skipped to avoid a full train
   calibration pass per trial. They apply at ARK-S22-03.
4. **The measured cost far exceeded the ARK-S22-01 estimate**, 250 s/trial
   against 40 s. The estimate came from one warm-cache configuration; wide
   geometries with few trades are far slower. The frozen operative cap of 720
   trials would not have fitted the eight-hour budget at the true rate.

**ARK-S22-02 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S22-02
```
