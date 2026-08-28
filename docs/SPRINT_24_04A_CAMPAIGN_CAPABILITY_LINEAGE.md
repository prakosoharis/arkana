# ARK-S24-04a — Campaign Capability Lineage

**Date:** 2026-08-28

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the restored verification of the accepted ARK-S22 campaign
and the replacement check recorded below. No campaign was run, no grid was
created, no stored row was edited, and the `NO_EDGE_FOUND` verdict is untouched.

This is a prerequisite of ARK-S24-04, not the campaign itself. ARK-S24-04's
first exit criterion is that the campaign *reuses the accepted ledger without
modification* — which could not be met while that ledger failed verification.

## The finding

Re-running the ARK-S22-05 chain verifier against the live database today gives
**`FAILED`**, on a record that was accepted as `PASSED` on 2026-08-27 and has
not been tampered with.

```text
FAIL: registry_fingerprint_current
  observed 808d3506e7020b41d977fc8aae94f6cc6eb7a1c9e25a8093ea0bdb402a3b2bfb
  expected 4a7ab4bd2245b4c9c7b189b945ddc4cdac59ec60cf66622ab3e4f8b41e7754e4
```

The check compared the **whole capability registry** for equality against the
value recorded at pre-registration. ARK-S24-01 added `SESSION_WINDOW` and
ARK-S24-03 added `ATR_SCALED_SL` / `ATR_SCALED_TP`, so the registry fingerprint
moved and the check failed.

Nothing about the Sprint 22 campaign changed. The verifier was asking the wrong
question, and Sprint 24's own extension policy guarantees that question
eventually answers "changed" for every campaign that ever existed.

It was found by reading the verifier before writing ARK-S24-04, and confirmed
against the live Postgres record rather than inferred.

## Why no test caught it

No test asserted `registry_fingerprint_current` at all. Every edge-search test
built its campaign and verified it inside the same process, where the registry
is trivially identical. The check only fails across a *registry change over
time*, which no test simulated.

## The replacement

The question that actually protects a campaign is not "has the registry changed
at all" but **"do the blocks this campaign's frozen contracts depend on still
mean what they meant?"**

| | old | new |
|---|---|---|
| scope | every block in the registry | exactly the blocks the frozen grid uses |
| fails on | any extension, forever | mutation or deletion of a *used* block |
| Sprint 22 grid | 18 blocks compared | **11 blocks compared** |

The dependency set is derived from the stored grid, so **no stored row was
edited and no migration was needed** to answer the question for the existing
campaign.

Two checks replace the one:

- `capability_dependencies_unchanged` — the used blocks fingerprint to the
  value recorded at pre-registration;
- `capability_dependencies_present` — every used block is still registered.

The registry change is **reported, not hidden**. Every verification now carries
a `registry_lineage` block stating the fingerprint then, the fingerprint now,
whether the registry was extended, and the exact blocks the campaign uses.

## The proof that Sprint 22 is intact

The claim "not one block the campaign uses changed" was **measured, not
asserted**. The pre-Sprint-24 source was extracted from commit `7b4fa21` and the
same fingerprint recomputed over the same eleven blocks:

| | value |
|---|---|
| dependency fingerprint at `7b4fa21` (pre-Sprint-24) | `f73b4bd68c5dd0b9d370d40390a81b4c4a5c60b5d2ca24662a4f584ff7a59069` |
| dependency fingerprint today | `f73b4bd68c5dd0b9d370d40390a81b4c4a5c60b5d2ca24662a4f584ff7a59069` |

Both accepted values are pinned in source as lineage and asserted by a test:

```python
ACCEPTED_V1_REGISTRY_FINGERPRINT = "808d3506..."
ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT = "f73b4bd6..."
```

Campaigns pre-registered from this checkpoint onward **record their own**
dependency fingerprint, so the constant is a one-time bridge for the single
campaign that predates the field, not a growing table.

## Negative controls

A check that cannot fail is not a check. Three tests prove it still catches
real tampering:

| scenario | result |
|---|---|
| mutate `FIXED_PRICE_DISTANCE_SL.parameters.distance` | `capability_dependencies_unchanged` **FAILS**, verification FAILED |
| delete `TWO_BAR_REVERSAL` from the registry | `capability_dependencies_present` **FAILS**, names the missing block |
| add a block no campaign uses | **PASSES** — the exact Sprint 24 case, isolated |

A fourth asserts a campaign carrying its own recorded fingerprint is held to
**that** value, not to Sprint 22's, so the fallback can never mask a future
campaign's drift.

## Restored state

```text
campaign verify: PASSED   (9 checks, all PASS)
chain verifier : PASSED   conclusion: NO_EDGE_FOUND
```

## Automated verification

| Scope | Result |
|---|---|
| focused lineage suite | **12 passed** |
| full backend regression | **613 passed** (601 before this checkpoint) |

No existing test changed. That is itself the point: the defect lived in an
uncovered branch, and the coverage is what is new.

## Known limitations

1. **One constant is pinned in source.** The single pre-existing campaign has
   no recorded dependency fingerprint, so its accepted value lives in
   `edge_search.py`. It was recomputed from git rather than trusted, and no
   future campaign will need one.
2. **This restores verification; it does not re-run Sprint 22.** The
   `NO_EDGE_FOUND` verdict and every trial are exactly as accepted.
3. **The campaign itself is still ahead.** ARK-S24-04's extended grid,
   measured trial baseline, and verdict are unchanged in scope.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_campaign_capability_lineage.py -q
```

**ARK-S24-04a is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-04a
```
