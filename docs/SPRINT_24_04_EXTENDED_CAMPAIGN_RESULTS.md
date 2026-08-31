# ARK-S24-04 — Extended Campaign Results

**Date:** 2026-09-01

**Status:** grid complete and verified; **terminal verdict pending an Owner
budget decision**

**Technical checkpoint claim:** `VALIDATED` for the execution and the analysis
below. The campaign verdict is `IN_PROGRESS` by the protocol's own rule, and
this document does not declare one.

## Execution

| | |
|---|---|
| campaign | `18f878ab-2f50-49fe-9412-55da21a707d5` |
| fingerprint | `2e54857cbecddc043fd39aac597be454e103df969d9bd5999ab6d7f107629f60` |
| trials | **768 / 768**, zero `FAILED` |
| chain verification | **PASSED** |
| holdout survivors | **101** (13.2% of the grid) |
| final-OOS budget | **0 of 3 consumed** |

The grid ran through the accepted ARK-S22-02 executor without modification.
Docker stopped once mid-run and cost zero recorded trials; the ledger is
append-only and every trial commits on the spot.

## The question Sprint 24 asked

> Do `direction`, `session_window`, and `stop_type` change the verdict?

### Paired effect, every other axis held fixed

A survivor count alone confounds axes. Each pair below is the **same
configuration** differing in one axis only, so the difference is the axis.

| axis | pairs | mean ΔPF | median ΔPF | wins |
|---|---|---|---|---|
| `session_window` 02-21 vs NONE | 384 | **−0.0169** | −0.0043 | 180 / 384 |
| `stop_type` ATR vs FIXED | 384 | +0.0484 | **−0.0115** | 142 / 384 |
| `direction` SHORT vs LONG | 384 | **−0.4505** | −0.2433 | **3 / 384** |
| `stop_scale` ×80 vs ×10 | 384 | **+0.2180** | +0.1506 | 201 / 384 |

### Survivors by axis

| axis | survivors |
|---|---|
| `direction` | LONG **101** / 384 · SHORT **0** / 384 |
| `stop_type` | FIXED **96** / 384 · ATR **5** / 384 |
| `session_window` | 02-21 **52** / 384 · NONE **49** / 384 |
| `stop_scale` | ×80 **101** / 384 · ×10 **0** / 384 |

### The answer

**None of the three new axes helped.**

- **SHORT is decisively worse.** Zero survivors from 384 trials, and it beats
  its LONG twin in **3 of 384** paired comparisons. This is not noise.
- **ATR does not help.** Its mean is positive only because a few outliers pull
  it; the median is negative and it wins under half its pairs. It also produces
  fewer trades, which pushes candidates toward the 100-trade floor.
- **The session filter is neutral.** 52 versus 49 survivors, a paired median of
  −0.004, and a 47% win rate. ARK-S24-00 predicted it would close a slice of
  the gap; measured, it closes none of it.

What does matter is the axis Sprint 22 already identified: stop size. ×80
produced every survivor and ×10 produced none, exactly as the cost model
predicts — a wider stop amortises the same spread over a larger move.

## The finding that settles it

The best survivor of this 768-trial extended campaign is **the same
configuration as Sprint 22's best**:

| | Sprint 22 best | Sprint 24 best |
|---|---|---|
| stop_scale | 80 | 80 |
| target_ratio | 2.0 | 2.0 |
| sma | 2 / 50 ABOVE | 2 / 50 ABOVE |
| polarity | BEARISH | BEARISH |
| direction | (LONG only) | **LONG** |
| session_window | (none) | **NONE** |
| stop_type | (fixed only) | **FIXED** |
| holdout PF | **1.469909** | **1.469909** |
| holdout trades | **138** | **138** |

All three Sprint 24 axes are at their legacy setting. Three new axes, 768
trials, and the ceiling did not move by one digit.

## That configuration has already been through the gate

Sprint 22 spent one final-OOS unit on this exact configuration (trial 360):

| check | result |
|---|---|
| minimum trades | PASS — holdout 138, final OOS 1,211 |
| regime calibration | PASS |
| positive net PnL after costs | PASS — holdout 840.46, final OOS 932.38 |
| **profit factor** | **FAIL — holdout 1.4699, final OOS 1.0519**, required > 1.10 |

The holdout number did not hold out of sample. It collapsed from 1.47 to 1.05
on data the search had never seen — the signature of selection, not edge.

## Why this document declares no verdict

The frozen policy defines `NO_EDGE_FOUND` as every trial executed **and**
either no survivor, or every authorized final-OOS opening failing the gate.

There are 101 survivors and no opening has been authorized, so
`assess_conclusion` returns **`IN_PROGRESS`**. That is the protocol refusing to
let anyone declare "no edge" while declining to look, and it is correct.

Closing the campaign therefore requires the Owner to spend at least one
irreversible unit. **That decision is not mine and I have not made it.**

## The choice, stated plainly

| | spend on trial 675 (top-ranked) | spend on trial 480 (best new-axis) |
|---|---|---|
| configuration | identical to Sprint 22's | `×80 r=1.0` **ATR** LONG `02-21` BEARISH 5/50 ABOVE |
| holdout PF | 1.469909, n=138 | 1.414063, n=112 |
| final-OOS answer | **already in the ledger: PF 1.0519, FAIL** | unknown |
| what the unit buys | a duplicate record | the sprint's own question, answered out of sample |

**Recommendation: spend exactly one unit, on trial 480.**

Trial 675's out-of-sample answer is already recorded, so a unit spent there is
a unit spent to re-learn a known result. Trial 480 is the strongest candidate
that actually uses a Sprint 24 axis, and it is the only remaining way to learn
whether volatility scaling survives out of sample when fixed distances did not.
It will most likely also fail — but a recorded failure is evidence, and a
prediction is not.

Choosing rank 7 over rank 1 is a deliberate departure from holdout ranking and
is disclosed here as one. It relaxes no threshold, widens no split, alters no
cost assumption, and extends no grid.

One unit either way. Two would be waste: the top survivors are one family.

## Known limitations

1. **`stop_scale` was narrowed to two values**, disclosed at pre-registration.
   The campaign cannot see whether an effect peaks at ×20 or ×40.
2. **101 survivors from 768 pre-registered hypotheses is multiple testing.** A
   holdout pass here is weak evidence by construction, which is exactly why the
   final-OOS budget is rationed to three.
3. **The prior was right.** ARK-S24-00 measured a rule contribution 9.6× short
   of what the geometry requires, and predicted the new axes would not close
   it. They did not.
4. **A clean EA compile is not a working EA.** ARK-S24-04d closed the compile
   limitation; DEMO behaviour remains unproven.

## Owner decision required

To authorize one final-OOS opening, reply with the checkpoint acceptance and
the exact phrase:

```text
AUTHORIZE_EDGE_SEARCH_FINAL_OOS_OPENING_V1
```

naming the trial index. To close the sprint without spending, say so and the
campaign stays `IN_PROGRESS` on the record, with ARK-S24-05 documenting exactly
that state.

**ARK-S24-04 execution and analysis are ready for Owner acceptance.**

```text
DITERIMA — ARK-S24-04
```
