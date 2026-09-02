# ARK-S25-01 — Breadth Evidence, and Two Lineage Defects a Sync Exposed

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the breadth ledger, the corrected measurement, and the two
lineage fixes below. The final-OOS partition was never read, no budget unit was
spent, and no accepted record was edited.

**This checkpoint supersedes the concentration figures in ARK-S25-00.** Those
were measured on the wrong partitions. The selection is unchanged, but that is
luck rather than method, and the reason is recorded below.

## What was built

`edge_search_breadth.py` and an immutable ledger, `edge_search_trial_breadth`
(migration 057), holding one fingerprinted record per survivor.

Three properties are enforced structurally rather than by intention:

- **It cannot read final OOS.** `READABLE_SPLITS` is `("train", "holdout")`,
  the name `final_oos` appears nowhere in executable code, and a spy test
  asserts every partition actually read is one the trial recorded.
- **It declares no threshold.** `CEILING` is read from the accepted gate's own
  `maximum_single_year_or_regime_pnl_concentration`, so the two cannot drift.
  A test fails if `0.5` appears anywhere in executable code.
- **It uses the gate's concentration definition**, including that losing
  buckets never dilute a concentration.

**101 of 101 survivors are now recorded in the ledger.**

## The first defect: my own guard refused, and it was right

Recording the evidence failed immediately:

```text
ValueError: the campaign dataset fingerprint changed;
            breadth cannot be measured against different data
```

The Owner had synced MT5, appending **11,281 bars**. That is not corruption —
it is the system working — but it broke two things.

### ARK-S25-00 measured partitions the campaign never ran on

The measurement recomputed `split_bounds` from the **current** row count:

| | train | holdout |
|---|---|---|
| what the trials recorded | `[0, 1791596)` | `[1791596, 2388795)` |
| what recomputation gives now | `[0, 1798410)` | `[1798410, 2397880)` |

**A 6,814-row shift**, and it would have been silent.

`measure()` now reads the `index_range` each trial recorded, and — because
"growth appends, so old indices still address the same bars" is an assumption
rather than evidence — it verifies that those indices still yield the
`timestamp_range` the trial recorded, refusing if they do not.

### Re-measured on exact lineage

| | ARK-S25-00 (wrong bounds) | corrected |
|---|---|---|
| range | 0.2664 – 0.8583 | **0.2728 – 0.8659** |
| median | 0.5547 | 0.5610 |
| within the 0.50 ceiling | 37 / 101 | **38 / 101** |

Per-trial shift: median **0.0243**, maximum **0.1458**. **Five trials changed
side of the ceiling.**

The frozen rule's output is unchanged — trial 488 remains first, at 0.4619
where the flawed run said 0.4462, and the top five are the same in the same
order. **The error did not change the decision. It could have.**

| # | trial | holdout PF | regime concentration | profitable regimes | PF rank |
|---|---|---|---|---|---|
| **1** | **488** | **1.3727** | **0.4619** | 5 / 6 | 12 / 101 |
| 2 | 699 | 1.3458 | 0.4628 | 6 / 6 | 16 / 101 |
| 3 | 659 | 1.3445 | 0.3674 | 5 / 7 | 17 / 101 |
| 4 | 689 | 1.3380 | 0.3736 | 5 / 6 | 19 / 101 |
| 5 | 753 | 1.3380 | 0.4567 | 5 / 6 | 20 / 101 |

## The second defect: both accepted verdicts had stopped verifying

```text
V1 320d1159: FAILED   immutable_grid_recomputation
V2 18f878ab: FAILED   immutable_grid_recomputation
```

`_fingerprint` read `dataset.fingerprint` **live off the Dataset row**. The sync
rewrote it, so neither campaign recomputed to its stored fingerprint — although
no campaign record had been touched.

This is **the ARK-S24-04a defect one field over**. There, a verifier compared
the live capability registry and a legitimate extension broke an accepted
record. Here, a verifier reads a live dataset fingerprint and a legitimate sync
does the same. The pattern is a verifier recomputing from a value the system is
designed to change.

The fix is the same principle: **what a record was registered against is what
the record itself stored.** `verify()` now passes `campaign.dataset_fingerprint`
and `campaign.dataset_id`, and reports the drift in a `dataset_lineage` block
rather than hiding it. The chain verifier carries both lineage blocks, since it
is the Owner-facing surface.

```text
V1 320d1159: PASSED / NO_EDGE_FOUND | failing: none
V2 18f878ab: PASSED / NO_EDGE_FOUND | failing: none
    dataset grew since pre-registration: True | frozen grid replayable: True
```

Four tests pin it, including one asserting the live row is no longer passed in.

## Automated verification

| Scope | Result |
|---|---|
| breadth suite | **22 passed** |
| campaign lineage suite | 16 passed |
| full backend regression | **736 passed** (729 before, 710 before this sprint) |
| survivors with recorded breadth evidence | **101 / 101** |
| final-OOS reads | **0** |
| budget consumed | **0 of 2 remaining** |

## Known limitations

1. **Train+holdout concentration is not the gate's measure.** The gate merges
   holdout and final OOS. 0.4619 is a prediction about a check this checkpoint
   may not run.
2. **The year axis is untouched.** ARK-S25-00 showed the gate's four-bucket year
   window makes >0.50 near-unavoidable. A candidate can pass regime
   concentration and still be refused on years.
3. **Two verifier defects of the same shape have now been found in one sprint
   pair.** Others may exist wherever a verifier recomputes from live state
   instead of recorded state. No systematic audit was performed.
4. **The underlying arithmetic has not moved.** ARK-S24-00's `+0.021` against a
   required `+0.202` is unchanged. Breadth addresses one of seven gate checks.

## Owner OAT steps

```bash
docker compose build research && docker compose up -d research
docker compose run --rm research pytest tests/test_edge_search_breadth.py -q
```

ARK-S25-02 asks for one authorized opening on trial 488. That decision, and the
irreversible unit it costs, remains the Owner's.

**ARK-S25-01 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S25-01
```
