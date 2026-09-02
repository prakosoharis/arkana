# ARK-S25-02 / ARK-S25-03 — The Breadth Opening, and Sprint 25's Verdict

**Date:** 2026-09-01

**Status:** complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

One irreversible final-OOS unit was spent on trial 488, on the Owner's exact
authorization phrase. The gate returned **FAIL**. The terminal verdict remains
`NO_EDGE_FOUND` and the chain verifies `PASSED`.

## What was authorized and what it bought

Sprint 25 asked one question, framed so it could fail:

> A survivor whose regime concentration is ~0.31 on train + holdout is more
> likely to pass the gate's regime-concentration check than one at ~0.85.

**The answer is: partially, and not enough.**

## The measurement

| | trial 480 (ARK-S24-04) | **trial 488 (ARK-S25-02)** |
|---|---|---|
| selection rule | highest holdout profit factor among ATR survivors | **breadth filter, then profit factor** |
| predicted regime concentration (train+holdout) | 0.8537 | **0.4619** |
| **gate regime concentration** (holdout+final OOS) | **0.7903** | **0.6403** |
| gate year concentration | 0.7034 | 0.7287 |
| profit factor, holdout → final OOS | 1.4141 → 1.3445 | 1.3330 → **1.2020** |
| trades, holdout / final OOS | 112 / 121 | 102 / 135 |
| gate decision | FAIL | **FAIL** |

**Breadth transfers, and the effect is real but insufficient.** The excess over
the 0.50 ceiling roughly halved — 0.2903 for trial 480, **0.1403** for trial
488 — which is the direction the hypothesis predicted and about half the
distance needed.

Selecting for breadth on the readable partitions therefore does move the check
it targets. It does not move it far enough, and the sprint's own framing said
that outcome would be a real result rather than a failure.

## The year axis was never addressed, and it decided the outcome anyway

Trial 488's year concentration is **0.7287**, slightly worse than trial 480's
0.7034. ARK-S25-00 predicted exactly this: the gate merges holdout and final
OOS into a four-bucket year window with two negative buckets, and the breadth
rule does not touch that axis.

**Even a perfect regime score would have failed this candidate**, because the
gate refuses on either concentration check. That is a limitation of the
sprint's design, and it was recorded before the unit was spent rather than
discovered after.

## The profit factor held out of sample again

1.3330 → **1.2020**, above the 1.10 threshold. Trial 488 is the **second**
candidate in this project's history to pass the profit-factor check out of
sample, and both are ATR contracts. The fixed-distance candidate collapsed
1.4699 → 1.0519.

Two observations is still not evidence that ATR generalises. It is now a
pattern worth naming rather than a single point.

## Terminal state

| | |
|---|---|
| conclusion | **`NO_EDGE_FOUND`** — `69fc25438dfccf9c…`, reused, unchanged |
| chain verification | **`PASSED`**, zero failing checks — `22b6bcc937981af1…` |
| gate decisions | `['FAIL', 'FAIL']` |
| final-OOS budget | **2 of 3 consumed, 1 remaining** |
| strategy status | `CONTRACT_VALID` — never `VALIDATED` |

The recorded conclusion is the same immutable record from ARK-S24-05: a second
failing opening does not change `NO_EDGE_FOUND`, so nothing was rewritten.

## One pre-flight worry that proved unfounded

Trial 488's stored holdout showed exactly **100 trades**, the gate's minimum. I
flagged before spending that a final OOS below 100 would fail on trade count
before concentration was ever reached. The gate's own replay found **102 and
135**, and the check passed. The concern was right to raise and wrong in fact.

## What Sprint 25 established

1. **Breadth is measurable before a unit is spent**, on the partitions the
   search may read, and it is now recorded immutably for all 101 survivors.
2. **Breadth transfers partially.** Predicted 0.4619, measured 0.6403 — the
   direction holds, the magnitude does not suffice.
3. **The binding constraint is now the year axis**, which is substantially an
   artifact of a four-bucket window and which no rule in this family addresses.
4. **ATR held its profit factor out of sample twice.** That is the only
   mechanism in three sprints that has repeatedly survived the transition.
5. **Four verifiers still report FAILED on untouched records** (ARK-S25-01a),
   unfixed and documented.

## The honest position after three sprints

| | Sprint 22 | Sprint 24 | Sprint 25 |
|---|---|---|---|
| trials | 384 | 768 | — (reused ARK-S24-04) |
| verdict | `NO_EDGE_FOUND` | `NO_EDGE_FOUND` | `NO_EDGE_FOUND` |
| units spent | 1 of 3 | 1 of 3 | **1 more, 2 of 3** |
| what failed | profit factor **and** both concentrations | both concentrations | both concentrations |

The failure mode has narrowed twice: from three failing checks to two, and the
regime excess has halved. Nothing has yet cleared the gate, and ARK-S24-00's
arithmetic — a measured rule contribution of `+0.021` against a required
`+0.202` — has not moved across any of it.

## What I would not do next

Spend the last unit on another survivor from this campaign. The breadth rule
has been tested; a third candidate from the same 101 tests nothing new, and the
year axis would refuse it regardless.

## The decision this hands to the Owner

- **Stop this rule family.** Three campaigns, 1,152 pre-registered trials, nine
  axes, three `NO_EDGE_FOUND` verdicts, and a shortfall that has not moved.
  This is now the best-evidenced option.
- **Fix the four verifiers first** (ARK-S25-01a). Independent of strategy work,
  and the Owner's evidence surfaces are currently showing failures that belong
  to the verifiers rather than the evidence.
- **Investigate the year window itself.** Not by relaxing it — that is
  forbidden — but by asking whether a four-bucket measure can express what it
  intends. That is a governance question, not a code change, and it must be
  decided before rather than after seeing a result it would rescue.

**ARK-S25-02 and ARK-S25-03 are ready for Owner acceptance with technical claim
`VALIDATED`.**

```text
DITERIMA — ARK-S25-02
DITERIMA — SPRINT 25
```
