# ARK-S25-04 — Verifiers Judge Records Against What the Records Stored

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the three verifiers repaired below and the regression
recorded here. No record was deleted, relabelled, or edited, and no threshold
was relaxed. `strategy_router_verification` was diagnosed as a different defect
and is **not** claimed as fixed.

## The rule, stated once

> A verifier judges a record against **what the record stored**, never against
> a value the system is designed to change.

Found four times across two sprints, each time by accident:

| where | live value read | what legitimately changed it |
|---|---|---|
| ARK-S24-04a | the whole capability registry | Sprint 24 added three blocks |
| ARK-S25-01 | `dataset.fingerprint` in the campaign verifier | an MT5 sync appended 11,281 bars |
| **ARK-S25-04** | asset lineage, split bounds, artifact registry, capital walk length | the same sync |

## What was repaired

### `generic_evidence_verification` — was failing a `REAL_LINEAGE` record

Four distinct live reads, all now taken from the record:

| check | was | now |
|---|---|---|
| `completed_candle_split_alignment` | `split_bounds(m1.row_count)` | `split_bounds(recorded_rows)`, where `recorded_rows` is the record's own `final_oos.end_exclusive` |
| `assets` | asset lineage rebuilt from live rows | the lineage the record stored |
| `evaluator` | artifact re-derived from the live registry | the artifact checked **against itself** — it carries everything it fingerprints |
| `registry` | bound assessment compared to the current registry | the bound assessment compared to what the strategy recorded |
| `exact_lineage` | robustness fingerprint over the live dataset | over the recorded dataset fingerprint |

**The 60/20/20 property is still verified** — against the row count the record
itself states, so the check kept its meaning rather than being weakened.

Result, on production data:

```text
PASSED  REAL_LINEAGE        CONTRACT_VALID  S16-03 Runtime MTF OAT   failing=0
FAILED  SYNTHETIC_CHECKSUM  VALIDATED       Router ready             failing=6   (x5)
```

**The negative control is the production data itself.** The one real record now
passes; the five fixture records still fail, on checksum and lifecycle grounds
that have nothing to do with drift.

### `variant_experiment_verification` — now passes with zero failing checks

Split bounds now come from the baseline evidence's recorded row count, and the
contract fingerprint is recomputed from the **stored** assessment and the
dataset fingerprint that assessment names. `current_assessment["ready"]` is
still required, so a contract that stopped being executable under the present
registry is still refused.

**No fallback to the live asset.** A record that never stated its own row count
cannot have its split property verified, and the check fails closed rather than
silently judging it against today's partition. That deliberately broke two
existing tests whose fixture built a baseline `OosValidation` with `result={}`;
a real record always carries `cost_stress`, so **the fixture was corrected to
match reality** rather than the check weakened to accept it.

### `constrained_capital_simulations` — partially repaired

The replay walked the **whole live asset**, produced more trades than the
stored capital path has points, and reported an untouched record as
`capital path truncated at 704707`. It now walks only as far as the source
validation recorded in `bars_evaluated`.

| check | before | after |
|---|---|---|
| `exact_path_payloads` | 4 of 4 failing | **2 of 4** |
| `exact_lineage` | 4 of 4 failing | **2 of 4** |

Two simulations still fail on a recomputed-metrics mismatch and a
`frozen_snapshot_disclosure` whose fields are absent from the stored result —
plausibly older records written before those fields existed. **Not diagnosed,
not claimed as fixed.**

### `strategy_router_verification` — not this defect, not touched

`decision_identity` fails with `DECISION_PROTOCOL_INVALID`, a protocol mismatch
on stored decision records. It needs its own diagnosis and is left out rather
than lumped in.

## The test whose absence caused all four

```python
def test_no_verifier_rebuilds_split_bounds_from_a_live_row():
```

A verifier may compute canonical bounds — that is what makes 60/20/20
checkable — but it must derive the row count from the record. Writers are
exempt by name and with a reason: a writer reads the live asset by definition,
which is how a record comes to state a row count at all.

Thirteen further tests pin each repair: that the three fingerprint helpers
accept recorded values while defaulting to the live row for writers, that the
evaluator artifact is checked against itself, that the registry equality is
gone, and that drift is disclosed rather than hidden.

## Automated verification

| Scope | Result |
|---|---|
| recorded-state suite | **14 passed** |
| full backend regression | **750 passed** (736 before this checkpoint) |
| production: `REAL_LINEAGE` evidence record | **PASSED**, 0 failing checks |
| production: fixture evidence records | FAILED, correctly |
| production: variant experiment | **PASSED**, 0 failing checks |

## Known limitations

1. **Two capital simulations still fail**, undiagnosed, on metrics and on
   disclosure fields absent from their stored results.
2. **`strategy_router_verification` is untouched**, four records failing on a
   different cause.
3. **Previously materialized verification records stored `PASSED`.** They record
   a recomputation that no longer reproduces, and they are not rewritten.
4. **The guard test scans one pattern.** It catches `split_bounds` over a live
   row. A verifier reading some other live value in some other way would still
   slip past.

## Owner OAT steps

```bash
docker compose build research && docker compose up -d research
docker compose run --rm research pytest tests/test_recorded_state_verifiers.py -q
```

**ARK-S25-04 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S25-04
```
