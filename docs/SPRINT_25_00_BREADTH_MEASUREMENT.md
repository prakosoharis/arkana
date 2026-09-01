# ARK-S25-00 — Breadth Measurement and Selection Policy Freeze

**Date:** 2026-09-01

**Status:** measurement complete; policy frozen; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the measurement and the frozen selection rule. It is read
only: train and holdout were replayed, the final-OOS partition was never
touched, no budget unit was spent, and no record was created or changed.

## What was measured

Regime and year concentration over **train + holdout** for **all 101
survivors** of the ARK-S24-04 campaign — not a sample. Six sharded workers,
about eighteen minutes, using the same regime calibration the gate uses.

## The distribution

| | regime concentration |
|---|---|
| minimum | **0.2664** |
| median | 0.5547 |
| maximum | 0.8583 |
| **at or below the 0.50 ceiling** | **37 of 101** |

Breadth is not a property this rule family lacks. **Thirty-seven survivors
already sit under the gate's ceiling on the partitions the search may read.**

## A correction to the sprint contract

The Sprint 25 contract, written from a five-survivor sample, said profit-factor
ranking "actively prefers narrowness". Measured across all 101, that is
**overstated**:

| | median regime concentration |
|---|---|
| top 20 by profit factor | 0.6075 |
| bottom 20 by profit factor | 0.5417 |

correlation between rank and concentration: **−0.2868**

The relationship is real but weak. The accurate statement is not that the
ranking prefers narrow strategies — it is that the ranking is **nearly blind to
breadth**, so which of the two properties the top of the list happens to have is
close to chance. Thirty-seven broad candidates existed, and the ranking put
none of them near the top.

The consequence is unchanged, and it is the one that cost a budget unit: the
two candidates ever promoted to final OOS were at **0.8039** (Sprint 22's, rank
1) and **0.8537** (trial 480, rank 7). Both then failed the gate's regime check.

## The frozen selection rule

> Among survivors whose **train + holdout** regime concentration is at or below
> the gate's own ceiling of 0.50, take the highest holdout profit factor.

Two properties of this rule matter:

- **It is not "pick the broadest".** The broadest survivor is rank 99 of 101
  with a profit factor of 1.1655, barely above the 1.10 floor — trading a
  concentration refusal for a profit-factor one. The rule requires the
  candidate to clear the concentration ceiling and *then* be as strong as
  possible.
- **It reads no threshold that is not already the gate's.** 0.50 is the
  accepted `maximum_single_year_or_regime_pnl_concentration`, applied to
  partitions the search is allowed to see. Nothing is relaxed; a filter is
  added ahead of an existing sort.

## The rule's output, frozen before any unit is spent

| # | trial | holdout PF | regime concentration | profitable regimes | its PF rank |
|---|---|---|---|---|---|
| **1** | **488** | **1.3727** | **0.4462** | 5 / 6 | 12 / 101 |
| 2 | 699 | 1.3458 | 0.4621 | 6 / 6 | 16 / 101 |
| 3 | 659 | 1.3445 | 0.3405 | 5 / 7 | 17 / 101 |
| 4 | 689 | 1.3380 | 0.3565 | 5 / 6 | 19 / 101 |
| 5 | 753 | 1.3380 | 0.4406 | 5 / 6 | 20 / 101 |

**Selected: trial 488** — `×80 ATR LONG 02-21 r=1.0 sma=5/50 ABOVE BULLISH`

```text
regime PnL over train + holdout:
  TRENDING+HIGH    588.2      RANGING+HIGH     479.8
  TRENDING+LOW     200.4      RANGING+LOW       34.4
  RANGING+MEDIUM    15.5      TRENDING+MEDIUM  -32.4
```

Two regimes carry most of it, but neither dominates: the largest share is
0.4462 where the two spent candidates were at 0.80 and 0.85.

It is also an **ATR** contract. ARK-S24-05 recorded that the ATR candidate was
the first to hold its profit factor out of sample (1.41 → 1.34) where the fixed
one collapsed (1.47 → 1.05). Trial 488 combines that mechanism with breadth,
which no candidate spent so far has had.

## Comparison with what was already spent

| candidate | holdout PF | train+holdout concentration | gate outcome |
|---|---|---|---|
| Sprint 22 rank 1 | 1.4699 | 0.8039 | FAIL — PF and both concentrations |
| trial 480, rank 7 | 1.4141 | 0.8537 | FAIL — both concentrations only |
| **trial 488 (proposed)** | **1.3727** | **0.4462** | unknown |

## Honest prior

1. **Train+holdout concentration is not the gate's measure.** The gate merges
   **holdout + final_oos**, which this checkpoint may not read. 0.4462 on the
   readable partitions is a prediction, not the answer. Whether breadth
   transfers is exactly what ARK-S25-02 buys.
2. **The year axis will likely still fail.** ARK-S25-00's earlier measurement
   showed the gate's four-bucket year window makes >0.50 near-unavoidable, and
   this rule does not address it. A candidate could pass regime concentration
   and fail year concentration, and the gate refuses on either.
3. **The underlying arithmetic has not moved.** ARK-S24-00 measured a rule
   contribution of `+0.021` against a required `+0.202`. Breadth addresses one
   of seven gate checks. It does not manufacture an edge.
4. **Selection on 101 observed holdout results is multiple testing**, which is
   why the budget is rationed and why only one unit is proposed.

## Automated verification

No production code changed at this checkpoint. The measurement reused
`_calibrate_regime`, `generic_replay_plan` and `_evaluate` unmodified, and read
only `bounds["train"]` and `bounds["holdout"]`.

| Scope | Result |
|---|---|
| survivors measured | **101 of 101** |
| final-OOS reads | **0** |
| budget consumed | **0 of 2 remaining** |
| records created | **none** |

## Owner decision required

ARK-S25-01 will add breadth to the campaign's survivor evidence and ranking in
code, with a test proving the computation cannot reach final OOS. ARK-S25-02
then asks for one authorized opening on trial 488.

**ARK-S25-00 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S25-00
```
