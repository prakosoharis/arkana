# Sprint 25 — Regime Breadth

**Date:** 2026-09-01

**Status:** contract proposed; Owner acceptance pending

**Prerequisite measurement:** complete, recorded below

Sprint 24 closed with `NO_EDGE_FOUND` and a recommendation from me: attack
concentration. Before designing a campaign around that, I measured whether
concentration is even attackable. **The measurement changed the sprint, and
corrected my recommendation.**

## What I got wrong

At ARK-S24-05 I wrote that trial 480 "makes money in one market condition and
flat-lines elsewhere", reading its year concentration of 0.703 and regime
concentration of 0.790 as one finding. They are two findings, and only one of
them is about the strategy.

### Year concentration is largely an artifact of the measurement window

The gate merges **holdout + final_oos** — roughly 2023 to 2026, four year
buckets, two of which are net negative. With two positive buckets, exceeding
0.50 is close to unavoidable for any strategy whose years are at all uneven.

Measured over the partitions the search may read freely — train + holdout,
2017 to 2024, eight buckets — eight sampled survivors give:

| concentration | profitable years |
|---|---|
| 0.3856 – 0.5083 | **5 to 6 of 8** |

Six of the eight are **below** the 0.50 ceiling. These strategies are not
one-year wonders. The short window makes them look like one.

Note this is an observation about what the metric can resolve, **not** a
proposal to change it. The gate deliberately excludes train because train is
the data the search fitted to, and letting fitted years pad the denominator
would be contamination. That design is defensible and this sprint does not
touch it.

### Regime concentration is real, and it varies enormously

The regime axis has six buckets in **any** window, so it cannot be a
short-window artifact. Measured over train + holdout:

| trial | holdout PF rank | regime concentration | dominant regime | profitable regimes |
|---|---|---|---|---|
| 675 | **1st** | **0.8039** | TRENDING+HIGH | 5 / 6 |
| 480 | 7th — *our spent unit* | **0.8537** | TRENDING+HIGH | 4 / 6 |
| 537 | middle | 0.5153 | RANGING+HIGH | 4 / 7 |
| 715 | middle | **0.4739** | TRENDING+MEDIUM | **6 / 7** |
| 387 | **last** | **0.3079** | TRENDING+LOW | **6 / 7** |

**Concentration ranges from 0.31 to 0.85 within one campaign.** Breadth is a
property some configurations have and others do not.

## The finding that defines this sprint

**Ranking survivors by holdout profit factor selects for the most concentrated
strategies.**

A strategy that earns heavily in one regime posts a high profit factor. One
that earns modestly across six posts a lower one. The survivor criterion — the
holdout side of the accepted gate: ≥100 trades, PF > 1.10, positive net PnL —
says nothing about breadth, and the ranking that follows it actively prefers
narrowness.

So the machinery handed the Owner, in rank order, the candidates **least**
likely to survive the gate's concentration check. We spent an irreversible
budget unit on trial 480 at regime concentration 0.8537, while trial 387 sat
unspent at 0.3079.

Both `NO_EDGE_FOUND` verdicts stand. Nothing here reinterprets them: neither
campaign's ranking was wrong by its own rules, and the gate refused both
candidates correctly.

## What Sprint 25 proposes

**Select for breadth as well as profit factor, using the accepted gate
unchanged.**

This relaxes no threshold, widens no split, and alters no cost assumption. It
changes only **which survivor a budget unit is spent on** — and that choice was
never governed by anything but a profit-factor sort.

### Checkpoints

**ARK-S25-00 — Breadth measurement and policy freeze.** Measure regime
concentration over train + holdout for **every** survivor of the ARK-S24-04
campaign, not a sample of five. Freeze a breadth disclosure and a
pre-registered selection rule before any of it is used to choose.

Exit: the full distribution is recorded; the selection rule is frozen and
states how ties between profit factor and breadth are resolved.

**ARK-S25-01 — Breadth-aware survivor ranking.** Add breadth to the campaign's
survivor evidence and ranking, computed on train + holdout only. The final-OOS
partition remains unreadable outside an authorized opening; a test must prove
the breadth computation cannot reach it.

Exit: ranking exposes both axes; no threshold changes; the accepted Sprint 22
and Sprint 24 records still verify.

**ARK-S25-02 — One authorized opening on the broadest survivor.** With Owner
authorization, spend **one** of the two remaining units on the highest-breadth
survivor rather than the highest-PF one.

Exit: an immutable outcome either way. This is a genuine test of the sprint's
hypothesis, and it can falsify it.

**ARK-S25-03 — Verdict and closure.**

### The hypothesis, stated so it can fail

> A survivor whose regime concentration is ~0.31 on train + holdout is more
> likely to pass the gate's regime-concentration check than one at ~0.85.

If the broad candidate also fails, that is a real result: breadth on the
readable partitions does not transfer, and this rule family is finished. Either
outcome is worth one unit.

## What this sprint will not do

- change the gate, its thresholds, its splits, or its cost assumptions;
- reinterpret either `NO_EDGE_FOUND` verdict;
- read the final-OOS partition outside an authorized opening;
- claim that breadth implies an edge. It does not. It addresses one specific
  check that has refused every candidate so far.

## Honest prior

Trial 387 is the **lowest-ranked** survivor by profit factor. Its holdout PF is
near the 1.10 floor. Breadth may simply be what a weak-but-diffuse strategy
looks like, and a weak strategy fails the profit-factor check instead of the
concentration one — trading one refusal for another.

ARK-S24-00's arithmetic is also unchanged: measured rule contribution `+0.021`
against a required `+0.202`. Nothing in this measurement moves that. What it
moves is the odds on **one** of the seven gate checks, and only for candidates
we were not previously choosing.

Two units remain. Sprint 25 proposes spending one.

```text
DITERIMA — KONTRAK SPRINT 25
```
