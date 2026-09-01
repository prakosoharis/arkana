# ARK-S24-05 — Verifier and Closure

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the recorded terminal verdict, the materialized chain
verification, the Owner-view confirmation, and the closure below. No strategy
was promoted, no deployment was created, and no LIVE path exists.

## The terminal verdict, recorded

| | |
|---|---|
| campaign | `18f878ab-2f50-49fe-9412-55da21a707d5` |
| conclusion | **`NO_EDGE_FOUND`** |
| conclusion fingerprint | `69fc25438dfccf9c28528ccb978e1b6adec744e5c74944c71055c725b82c9f74` |
| chain verification | **`PASSED`**, zero failing checks |
| verification fingerprint | `92b9a5ddab0f59cc757af4497b2be4ad6628e6c34365452f23932b0961845aca` |
| final-OOS budget | **1 of 3 consumed**, 2 unspent |
| strategy status | `CONTRACT_VALID` — never `VALIDATED` |

The accepted Sprint 22 record was re-verified after every Sprint 24 change and
still returns `PASSED` / `NO_EDGE_FOUND`.

## The Owner view needed no change

The console renders trial parameters through `Object.entries(parameters)`, so
the three new axes appear without a code change. `gateObservation` already reads
`check.observed ?? check.maximum_observed`, which is what makes the two
concentration numbers visible rather than blank.

That detail matters: while reading the result I printed `check["observed"]` in
a throwaway script and reported `null` for both concentration checks. **The
script was wrong, not the system.** The correction is recorded here because the
first reading was shown to the Owner.

Four tests now pin the closure path: a V2 campaign reaches a recorded verdict,
the verification record is immutable and reused, the overview exposes all three
axes on both the grid and the outcome, and the concentration checks stay
readable by the console's accessor.

## The result of Sprint 24, stated plainly

Sprint 24 asked one question: **do `direction`, `session_window`, and
`stop_type` change the verdict?**

**They do not.** The extended 768-trial campaign concluded `NO_EDGE_FOUND`, the
same verdict Sprint 22 reached over 384 trials, and its single best survivor is
Sprint 22's best configuration to the digit — with all three new axes at their
legacy setting.

| axis | measured effect |
|---|---|
| SHORT | **0 survivors of 384**; beats its LONG twin in 3 of 384 paired comparisons |
| session window | neutral — 52 survivors against 49, paired median −0.004 |
| ATR | 5 survivors against FIXED's 96; negative paired median on holdout |

ARK-S24-00 predicted this. It measured a rule contribution of `+0.021` against
a required `+0.202` and said a session filter closes a slice of the gap, not the
gap. Three axes later, that arithmetic is unchanged.

## The one finding worth carrying forward

The single final-OOS unit was spent, on the Owner's authorization, on trial 480
— the strongest survivor that actually uses a Sprint 24 axis, rather than the
top-ranked one whose out-of-sample answer was already in the ledger.

That choice paid for the only genuinely new information in the sprint:

| | Sprint 22 best (FIXED) | trial 480 (ATR) |
|---|---|---|
| holdout PF | 1.4699 | 1.4141 |
| **final-OOS PF** | **1.0519 → FAIL** | **1.3445 → PASS** |
| year concentration | 0.6594 FAIL | 0.7034 FAIL |
| regime concentration | 0.8102 FAIL | 0.7903 FAIL |

**Trial 480 is the first candidate in this project's history to pass the
profit-factor check out of sample.** The fixed-distance candidate collapsed
from 1.47 to 1.05; the ATR candidate held from 1.41 to 1.34.

This contradicts the holdout analysis in ARK-S24-04, which found ATR neutral to
slightly negative. On holdout it is. Out of sample, on this one observation, it
degraded far less. The mechanism is plausible — a distance that follows
volatility re-scales when the regime shifts, and a fixed distance does not.

**It is n = 1.** One final-OOS observation is not evidence that ATR
generalises, and it must not be read as one. It is a reason to look, not a
result.

## What actually refused the strategy

Not the profit factor. **Concentration.**

Trial 480 earned 70.3% of its positive PnL in a single year (2025) and 79.0% in
a single regime (`TRENDING+HIGH`), against a ceiling of 50%. Sprint 22's
candidate failed the same way (65.9% and 81.0%).

Both campaigns found the same thing: a rule that makes money in one market
condition and flat-lines elsewhere. The gate refused it for the right reason.
**The binding constraint has moved from profit factor to concentration**, and
that is a more informative place to be stuck.

## Sprint 24 checkpoint record

| checkpoint | claim | note |
|---|---|---|
| ARK-S24-00 | `VALIDATED` | broker clock derived; policy frozen |
| ARK-S24-01 | `VALIDATED` | session window — **EA did not compile**, found at 24-03 |
| ARK-S24-02 | `VALIDATED` | SHORT — **EA did not compile**, found at 24-03 |
| ARK-S24-03 | `VALIDATED` | ATR stops; fixed the struct defect; found two 24-02 defects |
| ARK-S24-04a | `VALIDATED` | unplanned — Sprint 22's verdict had stopped verifying |
| ARK-S24-04b | `VALIDATED` | unplanned — Quick Backtest was broken in production |
| ARK-S24-04c | `VALIDATED` | unplanned — the OAT command wrote into production |
| ARK-S24-04d | `VALIDATED` | unplanned — MetaEditor compile, finally run |
| ARK-S24-04 | `VALIDATED` | 768 trials, `NO_EDGE_FOUND` |
| ARK-S24-05 | `VALIDATED` | this document |

Four of the ten checkpoints were unplanned defect fixes. Three of those four
were defects **introduced or exposed by Sprint 24's own work**, and the fourth
was a limitation three checkpoints had recorded without checking whether it was
true.

## Automated verification

| Scope | Result |
|---|---|
| ARK-S24-05 closure suite | **22 passed** |
| full backend regression | **685 passed** (681 before this checkpoint) |
| web regression | **44 passed** |

## Known limitations

1. **Zero real strategies still exist.** All six `VALIDATED` records are
   fixture lineage. Sprint 24 did not change that and was never going to.
2. **Nothing runs on DEMO.** Three `DEMO_ACTIVE` deployments have no telemetry
   and remain the Owner's decision.
3. **The production database still holds nine XAUUSD datasets, one real.**
   ARK-S24-04b and -04c stopped the pollution spreading and stopped its cause;
   removing it remains the Owner's decision.
4. **The test suite still depends on a persistent schema file**, recorded at
   ARK-S24-04c.
5. **Two final-OOS units remain unspent** on this campaign. They cannot be
   carried to a future campaign; each campaign rations its own.
6. **A clean EA compile is not a working EA.**

## The decision Sprint 24 hands to the Owner

Two `NO_EDGE_FOUND` verdicts now exist over the same rule family — SMA relation
plus two-bar reversal on M1 — across 1,152 pre-registered trials and nine
search axes. The honest options are:

- **Stop extending this family.** The measured shortfall has not moved across
  two sprints, and the second campaign's best result equalled the first's
  exactly. A different strategy family is a larger decision but a defensible
  one.
- **Attack concentration specifically.** The binding constraint is no longer
  profit factor; it is that profit arrives in one regime. ATR held up out of
  sample where fixed distances did not, on one observation. A campaign designed
  around regime robustness rather than around geometry would test that
  directly — and would be the first sprint to target the constraint that is
  actually binding.

Recommendation: the second, and only if it is pre-registered as narrowly as the
first two were. `n = 1` justifies a hypothesis, not a strategy.

**ARK-S24-05 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-05
DITERIMA — SPRINT 24
```
