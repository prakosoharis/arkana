# ARK-S23-03 — Runtime Fixture Hygiene

**Date:** 2026-08-27

**Status:** implementation, automated regression, and real runtime
classification complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the lineage classifier, its immutable ledger, and the gate
integration recorded below. **No StrategyVersion was deleted, retired, or
relabelled.** History is exactly as it was written.

## What was actually wrong

The runtime holds five `StrategyVersion` rows named `Router ready`, all
`VALIDATED`, each with a real promotion record. Their checksums are 54
characters of the form `router-ready-checksum-…`; a real contract checksum is a
64-character SHA-256 digest.

They were already refused by the generic DEMO gate — but **only because their
synthetic checksum could not match a real contract fingerprint**. That is an
accident of arithmetic, not a rule. A fixture whose checksum happened to look
real would have passed.

### A second anomaly, of a different kind

Surveying the table surfaced something the contract did not anticipate.
`S13-03 passing lineage` is `VALIDATED` with a legitimate 64-hex checksum and a
real candidate — but **no promotion record at all**. Since Sprint 18,
`VALIDATED` may only arise from an explicit atomic promotion. This row predates
or bypassed that, and it is a different problem from a fixture: the lineage is
not fabricated, it is unverifiable.

Conflating the two would have been the easy mistake. They are recorded
separately.

## Why not retirement

Retirement was the obvious disposition and is the wrong one. Retiring a row
means "this validated strategy is withdrawn", which concedes that it was once
legitimately `VALIDATED`. For a fixture the truth is stronger: **it was never
real evidence.**

So nothing is retired and nothing is relabelled. The judgement lives in a
separate immutable record, and the original rows stay exactly as history wrote
them.

## The classifier

Migration 055 adds append-only `strategy_lineage_classifications`.
`STRATEGY_LINEAGE_CLASSIFIER_V1` derives its judgement only from stored
evidence:

| Classification | Rule | May satisfy a generic gate |
|---|---|---|
| `SYNTHETIC_CHECKSUM` | checksum is not a SHA-256 digest | **no** — this is a fixture |
| `UNVERIFIED_PROMOTION` | `VALIDATED` with no promotion record | **no** — anomaly, not a fixture |
| `LEGACY_PRE_GENERIC` | no contract and no candidate | **no** — genuine history that predates the generic contract |
| `REAL_LINEAGE` | none of the above | yes |

The distinction between `SYNTHETIC_CHECKSUM` and `LEGACY_PRE_GENERIC` is
deliberate and load-bearing. A legacy row is not a fake; it simply cannot
satisfy a generic gate. Labelling honest history as a fixture would be its own
falsification, and a test asserts that a legacy row reports `is_fixture: false`.

## Gate integration — refusal by rule, not by coincidence

`eligibility_overview` now computes `lineage_ok` and requires it alongside
status, retirement, lifecycle, and capability. Each candidate carries its
`lineage` classification, and the payload exposes
`fixture_strategy_version_ids`.

### Behaviour is unchanged, which was the requirement

| | Before | After |
|---|---|---|
| status | `NO_VALIDATED_STRATEGY` | `NO_VALIDATED_STRATEGY` |
| eligible strategy versions | `[]` | `[]` |
| candidates listed | 8 | 8 |

What changed is *why* each refusal happens:

```text
INELIGIBLE_SOURCE  CONTRACT_VALID  REAL_LINEAGE          ok=True
INELIGIBLE_SOURCE  VALIDATED       UNVERIFIED_PROMOTION  ok=False
INELIGIBLE_SOURCE  VALIDATED       SYNTHETIC_CHECKSUM    ok=False   ×5
INELIGIBLE_SOURCE  CONTRACT_VALID  REAL_LINEAGE          ok=True
```

## Runtime classification

All 14 StrategyVersions were classified:

| Classification | Count |
|---|---|
| `REAL_LINEAGE` | 5 |
| `SYNTHETIC_CHECKSUM` | **5** |
| `LEGACY_PRE_GENERIC` | 3 |
| `UNVERIFIED_PROMOTION` | **1** |

The five fixtures are recorded with their exact checksums and lengths. A second
materialization recorded `0` and reused `14`, so the ledger is idempotent.

**Nothing was mutated:** 14 StrategyVersions before and after, 6 still
`VALIDATED`, 0 retired.

## API and BFF

- `GET  /api/v1/strategy-lineage` — read-only overview;
- `POST /api/v1/strategy-lineage/classifications` — materializes the immutable
  record for every version; mutates no strategy;
- `GET  /api/v1/strategy-versions/{id}/lineage` — latest stored classification;
- same-origin BFF proxy for the overview.

## Automated verification

| Scope | Result |
|---|---|
| focused lineage suite | **11 passed** |
| full backend regression | **431 passed** (420 before this checkpoint) |
| web Vitest / TypeScript / ESLint / build | 44 passed / passed / passed / passed |

Tests cover each classification, that a real promotion cannot rescue a
synthetic checksum, that classification never mutates or deletes a strategy,
that materialization is idempotent and single-winner, and that legacy history
is never mislabelled as a fixture.

## Known limitations

1. **The five fixtures remain `VALIDATED` in the strategy table.** That is
   deliberate: the classification refuses them, and rewriting history to make a
   table look tidy is precisely what this project forbids. Anything reading
   `status` alone without consulting lineage would still see them as validated.
2. **`UNVERIFIED_PROMOTION` is reported, not resolved.** Whether
   `S13-03 passing lineage` should be investigated, retired, or left as history
   is an Owner decision that this checkpoint does not take.
3. **No Owner UI page.** Lineage is visible through the generic DEMO
   eligibility payload wherever that is rendered, but has no page of its own.
4. **The classifier is heuristic on one axis.** A fabricated row carrying a
   genuine-looking SHA-256 and a real promotion would classify as
   `REAL_LINEAGE`. Defending against that requires provenance signing, which is
   out of scope here.

## Owner OAT steps

```bash
curl -fsS -H "Authorization: Bearer $RESEARCH_API_TOKEN" \
  http://localhost:8001/api/v1/strategy-lineage
curl -fsS -H "Authorization: Bearer $RESEARCH_API_TOKEN" \
  http://localhost:8001/api/v1/generic-demo/eligibility
```

Confirm five `SYNTHETIC_CHECKSUM` rows are reported, that eligibility still
returns `NO_VALIDATED_STRATEGY` with an empty eligible list, and that the
StrategyVersion count and statuses are unchanged.

**ARK-S23-03 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S23-03
```
