# ARK-S25-01a — Audit: Verifiers That Recompute From Live State

**Date:** 2026-09-01

**Status:** audit complete; **no code changed**; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED` for the audit only

This is a read-only diagnosis. Nothing was fixed, no record was created or
edited, and no budget unit was spent. It exists because ARK-S25-01 recorded a
limitation — *"others may exist wherever a verifier recomputes from live state
instead of recorded state; no systematic audit was performed"* — and that
sentence was a promise, not a disclaimer.

## The defect class, stated once

A verifier recomputes an immutable record's fingerprint or bounds from a value
the system is **designed to change**, then reports the untouched record as
`FAILED`.

Two instances were already found and fixed:

| checkpoint | live value read | what legitimately changed it |
|---|---|---|
| ARK-S24-04a | the whole capability registry | Sprint 24 added three blocks |
| ARK-S25-01 | `dataset.fingerprint` | an MT5 sync appended 11,281 bars |

The audit asked whether there are more. **There are.**

## Method

Every verifier in `services/research/app` was run against the **real records in
the production database**, and each failing check was read rather than
inferred. Reading code would not have distinguished a verifier that is broken
from a record that correctly fails.

## Findings

| verifier | records | status | same defect class? |
|---|---|---|---|
| `edge_search` / chain | 2 | **PASSED** | fixed at ARK-S25-01 |
| `generic_evidence_verification` | 6 | FAILED | **yes — two mechanisms** |
| `constrained_capital_simulations` | 4 | FAILED | **likely** |
| `variant_experiment_verification` | 1 | FAILED | **yes** |
| `strategy_router_verification` | 6 | FAILED / ERROR | **no — different cause** |

### `generic_evidence_verification` — the clearest case

The decision inspected belongs to **`S16-03 Runtime MTF OAT`**, whose lineage
classifies as **`REAL_LINEAGE`**. This is not a fixture failing correctly.

```text
FAIL registry
     stored_registry_fingerprint: 808d3506e7020b41d977…
     expected: "bound assessment equals current immutable registry assessment"

FAIL completed_candle_split_alignment
     expected: train {start_inclusive: 0, end_exclusive: 1798728}
```

Two distinct mechanisms, both already diagnosed elsewhere:

- `808d3506…` is the **pre-Sprint-24 registry fingerprint** — the identical
  value ARK-S24-04a pinned as `ACCEPTED_V1_REGISTRY_FINGERPRINT`. This check
  compares a bound assessment against the *current* registry. **Third instance
  of the ARK-S24-04a defect.**
- `end_exclusive: 1798728` is a bound **recomputed from the grown dataset**;
  the record was written against `1791596`. **Fourth instance, and the same
  mechanism ARK-S25-01 fixed in the breadth module.**

`evaluator`, `assets` and `exact_lineage` also fail, and each recomputes an OOS
fingerprint that includes the dataset fingerprint — consistent with a cascade
from the same two causes, though that was not separately proven.

### `variant_experiment_verification`

```text
FAIL train_split_isolation
     train {accessed: true, start_inclusive: 0, end_exclusive: 1791596}
```

The recorded bound is `1791596`; recomputation now yields `1798410`. Same
mechanism.

### `constrained_capital_simulations`

```text
FAIL exact_path_payloads
     {"scanned": 704707, "issue": "capital path truncated at 704707"}
FAIL exact_lineage
     {"simulation_fingerprint_and_protocol": false}
```

A stored capital path no longer covers a dataset that has grown past it.
Consistent with the class, but the truncation could have another cause and was
**not** proven. Recorded as *likely*, not confirmed.

### `strategy_router_verification` — not this defect

```text
FAIL decision_identity
     {"code": "DECISION_PROTOCOL_INVALID"}
```

A protocol mismatch on stored decision records, unrelated to dataset or
registry drift. It needs its own diagnosis and is explicitly **out of scope**
here rather than lumped in to inflate the finding.

## What this means

Four verifiers now report `FAILED` on records nobody touched, and at least one
of those records is real lineage rather than a fixture. The Owner's Governance
and evidence surfaces are therefore showing failures that are **artifacts of
the verifiers, not of the evidence**.

That is the same category of harm as ARK-S24-09's permanently-stale dataset
indicator: a signal that cries wolf gets muted, and then it protects nothing.

## Why no code changed here

Each verifier recomputes something different, so there is no single shared
fix — each needs its own "use what the record stored" change, its own negative
controls proving it still catches real tampering, and its own regression. That
is a checkpoint's worth of work per verifier, against **accepted** verifiers.

Half-fixing four accepted verifiers in one pass would be worse than a precise
diagnosis. The audit is the deliverable; the repair is proposed below.

## Proposed repair, in priority order

1. **`generic_evidence_verification`** — highest value: it fails a
   `REAL_LINEAGE` record today. Bind the registry check to the recorded
   assessment's dependencies (the ARK-S24-04a pattern) and the split check to
   the recorded bounds (the ARK-S25-01 pattern).
2. **`variant_experiment_verification`** — single mechanism, smallest change.
3. **`constrained_capital_simulations`** — confirm the truncation's cause first;
   it may be a different defect wearing the same clothes.
4. **`strategy_router_verification`** — separate diagnosis, separate checkpoint.

A shared regression test should then assert the property directly: **simulate
dataset growth and registry extension, and require every verifier to still pass
an untouched record.** That test is what would have caught all four at once,
and its absence is why they were found one at a time across two sprints.

## Known limitations

1. **Nothing is fixed.** Four verifiers still fail on untouched records.
2. **The `constrained_capital_simulations` diagnosis is unconfirmed.**
3. **Previously materialized verification records stored `PASSED`.** They are
   historical records of a recomputation that no longer reproduces — the same
   shape as the campaign case, and they are not rewritten.
4. **ARK-S25-02 is unaffected.** The edge-search chain verifies `PASSED` for
   both campaigns, so the breadth selection and any authorized opening rest on
   a verified chain.

**ARK-S25-01a is ready for Owner acceptance with technical claim `VALIDATED`
for the audit.**

```text
DITERIMA — ARK-S25-01a
```
