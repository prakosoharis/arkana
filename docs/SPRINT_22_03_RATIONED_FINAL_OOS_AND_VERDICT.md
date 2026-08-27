# ARK-S22-03 — Rationed Final-OOS Access and the Campaign Verdict

**Date:** 2026-08-27

**Status:** implementation, automated regression, and one real final-OOS
opening complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the rationed opening path, the accepted-gate evaluation, and
the immutable verdict recorded below. No strategy was promoted, no threshold
was relaxed, and no DEMO, LIVE, capital, router, order, or trade authority was
created.

## Verdict

```text
NO_EDGE_FOUND
fingerprint 8cf4b7870f739188796b1ffaceca3aeda253cde1616e38a230de21aa0a2d84cf
```

384 of 384 trials executed, 73 holdout survivors, **one** final-OOS budget unit
spent of three, gate decision `FAIL`, two units remaining.

## What the gate did, and why it matters

One unit was spent on the strongest survivor — trial 360, `stop_scale ×80`,
`target_ratio 2.0`, `SMA_RELATION ABOVE`, `TWO_BAR_REVERSAL BEARISH`,
`CANDLE_DIRECTION BEARISH` — holdout profit factor 1.4699.

The accepted `OOS_HISTORICAL_REVIEW_V3` gate was applied unchanged across all
three splits:

| split | trades | net PnL | profit factor | win rate |
|---|---|---|---|---|
| train | 299 | +807.47 | 1.1907 | 37.46% |
| holdout | 138 | +840.46 | **1.4699** | 42.75% |
| final OOS | 1,211 | +932.38 | **1.0519** | 34.52% |

| gate check | status | observed |
|---|---|---|
| `minimum_trades` | PASS | holdout 138 · final OOS 1,211 |
| `regime_calibration` | PASS | available |
| `positive_net_pnl_after_costs` | PASS | +840.46 · +932.38 |
| `adverse_final_oos_nonnegative` | PASS | +819.06 |
| `profit_factor` | **FAIL** | final OOS 1.0519, required > 1.10 |
| `year_pnl_concentration` | **FAIL** | **0.6594**, max 0.50 |
| `regime_pnl_concentration` | **FAIL** | **0.8102**, max 0.50 |

**This strategy made money in every split, and the gate still refused it.**

A naive system would have called it a winner: positive net PnL in train,
holdout, and final OOS, and still positive under adverse costs. Three checks
disagreed, and each one names a different part of the same defect:

1. **Profit factor collapsed out of sample**, 1.4699 → 1.0519. The holdout
   figure was selection-inflated — it was the best of 384 pre-registered
   hypotheses, which is exactly what the mandatory selection disclosure exists
   to keep visible.
2. **65.9% of profit came from a single year.** The cap is 50%.
3. **81.0% came from a single regime.** The cap is 50%.

Concentration that extreme is the arithmetic signature of directional drift,
not of an edge. It is the same conclusion ARK-S22-02 reached from rule
independence — 100% survival at ×80 across every rule variant including
mutually contradictory ones — now confirmed by an independent mechanism on data
the search had never touched.

The hypothesis was recorded in the campaign's `calibration_disclosure` **before
the first trial ran**. It was then confirmed twice, by two unrelated tests. That
is the strongest form this evidence chain can produce.

## The more valuable result

The sprint set out to find an edge and did not find one. What it did establish
is arguably worth more: **the gate works.**

Twenty-two sprints built an evidence architecture on the premise that it would
refuse a plausible-looking result. Until now that premise was untested — every
prior strategy failed so badly that no gate subtlety was ever exercised. This
time the candidate was profitable in every split and was refused anyway, for
stated reasons, on the first genuine attempt.

## Implementation

Migration 053 adds two append-only ledgers:

- `edge_search_final_oos_outcomes` — one row per spent unit, binding the
  opening, trial, StrategyVersion, and the accepted `oos_validations` evidence
  row by exact ID and fingerprint;
- `edge_search_campaign_conclusions` — the terminal verdict, one per campaign,
  fingerprinted. `NO_EDGE_FOUND` is as hard to revise later as a pass would be.

A survivor receives no shortcut. It is materialised as a real
`StrategyCandidate` and immutable `StrategyVersion` through the accepted
capability path — `strategy_capabilities.materialize` then `confirm`, not the
legacy block validator, which does not know `SMA_RELATION` or
`TWO_BAR_REVERSAL` — and its provenance records the campaign, the trial, the
parameters, the pre-registered hypothesis count, and an explicit selection-bias
note. The resulting version is `CONTRACT_VALID`. The generic path never
auto-promotes, so `VALIDATED` was neither reached nor approached.

### The budget is consumed before final OOS is read

This is the one design decision worth stating plainly. If the unit were charged
after a successful evaluation, a caller could crash and retry until a favourable
result appeared, and the rationing would be worthless. The opening is therefore
committed first; a failure after that point still costs a unit. Runtime
confirmed the ordering: the opening row existed while the gate was still
executing.

## Guards

| Guard | Behaviour |
|---|---|
| authorization | the exact phrase `AUTHORIZE_EDGE_SEARCH_FINAL_OOS_OPENING_V1` is required; anything else refuses without spending |
| survivor only | a non-survivor cannot reach final OOS and spends nothing |
| single spend | repeating an opening returns the stored outcome; it never charges twice |
| exhaustion | the budget fails closed at 3 and cannot be reset |
| verdict integrity | a conclusion cannot be recorded while the grid is incomplete |
| barren grid | a campaign with no survivor concludes `NO_EDGE_FOUND` without spending budget |
| no shortcut | the accepted gate runs unchanged; no threshold, split, or cost assumption is altered |

## API and BFF boundary

- `POST /api/v1/edge-search/campaigns/{id}/final-oos-openings` — the only route
  that spends a unit;
- `GET  /api/v1/edge-search/campaigns/{id}/final-oos-openings`;
- `GET  /api/v1/edge-search/campaigns/{id}/conclusion` — read-only assessment;
- `POST /api/v1/edge-search/campaigns/{id}/conclusion` — records the immutable
  verdict.

No DELETE and no LIVE route.

## Automated verification

| Scope | Result |
|---|---|
| focused final-OOS suite | **11 passed** |
| full backend regression | **396 passed** (385 before this checkpoint) |
| migration 053 | recorded exactly once in PostgreSQL |

## Runtime state after the checkpoint

| Fact | Value |
|---|---|
| campaign conclusion | `NO_EDGE_FOUND`, fingerprint `8cf4b787…` |
| trials | 384 / 384 |
| holdout survivors | 73 |
| final-OOS openings | 1, decision `FAIL` |
| budget | 1 consumed, **2 remaining** |
| StrategyVersion created | 1, status `CONTRACT_VALID` |
| promotions, eligibilities, DEMO artifacts | 0 |

## Known limitations

1. **The spread assumption is still Owner-reported at 0.25.** Every figure in
   this campaign rests on it. The updated exporter can capture it from the
   terminal; until then this remains the largest unverified input.
2. **Two budget units remain unspent.** Nothing compels spending them. Given
   rule independence and the concentration result, a second opening would very
   likely reproduce the same refusal.
3. **`NO_EDGE_FOUND` is bounded to this space.** It states that the six
   generic blocks, over XAUUSD M1 LONG at the frozen geometry range, contain no
   edge that survives the accepted gate. It says nothing about strategy space
   in general, and it is not evidence that no edge exists.

**ARK-S22-03 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S22-03
```
