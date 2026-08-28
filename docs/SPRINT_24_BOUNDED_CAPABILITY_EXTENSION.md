# Sprint 24 — Bounded Capability Extension

**Contract status:** DRAFT — awaiting explicit Owner acceptance

**Active checkpoint:** none. No source change is authorized until the Owner
accepts this contract and names ARK-S24-00.

**Implementation authority:** none yet. Sprints 22 and 23 are closed and their
authority is exhausted. This document proposes scope; it grants nothing.

## Why this is a milestone, not ARK-S22-04

The Sprint 22 contract listed a conditional registry extension as a single
checkpoint. Having now done the surrounding work, that estimate was wrong and
saying so is cheaper than discovering it mid-sprint.

Each new block carries the full Sprint 16/20 obligation set: evaluator
implementation, deterministic MT5 compiler adapter, EA parsing and validation,
golden completed-candle and risk parity evidence, and exact fingerprint
lineage. `SHORT` additionally touches the Router, which currently refuses it
outright with `SHORT_CAPABILITY_UNAVAILABLE`. That is three or four checkpoints
of work per block, not one for all of them.

Sprint 22's ARK-S22-04 is therefore superseded by this contract rather than
executed inside Sprint 22.

## What Sprint 22 established, and what it did not

Sprint 22 returned `NO_EDGE_FOUND` over 384 pre-registered trials. Two
independent results agreed: survivorship depended only on stop-distance
geometry — at scale ×80 every rule combination that traded survived, including
mutually contradictory ones — and the strongest survivor was refused by the
gate with 65.9% of profit in one year and 81.0% in one regime.

That is bounded to its space: six generic blocks, XAUUSD, M1, LONG only, fixed
price-distance stops, no time filter. **It is not evidence that no edge
exists.** It is evidence that this particular space does not contain one.

Sprint 24 asks whether a deliberately widened space does.

## Evidence that shapes the priority

Three terminal readings were taken from the Owner's own MT5 during Sprint 23:

| local | UTC | session | spread |
|---|---|---|---|
| 03:50 WIB | 20:50 | rollover / NY close | **97 points** |
| ~05:00 WIB | 22:00 | early Asia | **30 points** |
| 13:00 WIB | 06:00 | pre-London | **18 points** |

The range is **5.4× within a single day**. A single constant spread is
therefore **the wrong model**, not merely an imprecise number. The campaign
assumed 0.25, which sits between best and worst; the assumption proved slightly
optimistic rather than pessimistic, which is the direction that leaves
`NO_EDGE_FOUND` intact.

### How much a session filter is actually worth

Restricting entries to the cheap window changes the assumed cost from 0.25 to
about 0.18, which lifts the zero-edge profit-factor ceiling:

| geometry | edge needed at 0.25 | at 0.18 | relief |
|---|---|---|---|
| ×10 | +0.240 | +0.202 | 15.7% |
| ×20 | +0.172 | +0.152 | 11.5% |
| ×40 | +0.137 | +0.126 | 7.4% |
| ×80 | +0.118 | +0.113 | 4.3% |

The relief is largest at narrow geometries — precisely where Sprint 22 found
nothing, and precisely where genuine rule skill rather than trend drift would
have to show itself, because a narrow trade resolves in minutes and cannot ride
a multi-year uptrend.

The backtest charges the spread-guard maximum on every trade regardless of
hour, because historical OHLC carries no spread. It therefore cannot filter by
session on its own. The only honest way to model a strategy that avoids
expensive hours is a **time filter block that restricts the trade population in
the backtest itself**.

That moves the session filter from third priority to first, with a measured
justification rather than a hunch.

Readings at 14:00 and 20:00 are still outstanding. The 20:00 London–NY overlap
reading determines how large the achievable saving is, and ARK-S24-00 should
not freeze the session policy without it.

## Product objective

Determine whether widening the executable strategy space along three specific
axes produces a strategy that survives the accepted gate — using the same
pre-registration, budget rationing, and selection-disclosure discipline that
Sprint 22 established, and without weakening any accepted boundary.

The sprint must again be able to end in either outcome:

```text
EDGE_CANDIDATE_FOUND   → enters the existing accepted chain unchanged
NO_EDGE_FOUND          → immutable, honest, and a valid sprint completion
```

## Checkpoint sequence

### ARK-S24-00 — Extension policy freeze and session evidence

Documentation and read-only analysis only; no source change.

Record the measured spread profile across sessions; decide from that evidence
which session windows are worth expressing; specify the exact contract shape,
evaluator semantics, compiler fields, and EA validation for each proposed
block; and freeze the campaign policy for the extended space.

Exit criteria:

- the spread profile is recorded per session from terminal readings, not
  assumed;
- each proposed block has an exact declared contract shape and parameter
  domain;
- the compiler wire format and EA validation rules for each block are
  specified before any code exists;
- the pre-registration grid dimensions, trial cap, and final-OOS budget for the
  extended space are frozen;
- the ARK-S22-03 verdict and its evidence remain untouched;
- no model, migration, API, UI, EA, config, deployment, order, or trade change.

### ARK-S24-01 — Session filter block

The highest-priority block, because it is the only one with measured evidence
behind it.

A `SESSION_WINDOW` no-trade block that restricts entries to declared broker-time
windows, implemented across evaluator, compiler, and EA with golden parity.

Exit criteria:

- the block is registry-declared with an explicit parameter domain;
- the evaluator restricts the trade population deterministically on completed
  candles only;
- the compiler emits exact wire fields and the EA validates and enforces them;
- golden parity proves the evaluator and EA agree on identical inputs;
- broker-time semantics are explicit, and an unverified dataset timezone is
  refused rather than assumed;
- existing accepted contracts, evidence, and fingerprints remain valid.

### ARK-S24-02 — SHORT direction

The largest single extension. `direction_eligibility` already accepts `SHORT`
in the contract schema, but the evaluator, compiler, EA, and Router are all
LONG-only, and the Router refuses `SHORT` explicitly.

Exit criteria:

- evaluator, compiler, EA, and Router all support `SHORT` end to end;
- Backtest V1 semantics are preserved exactly: completed-candle inputs,
  next-bar entry, `STOP_FIRST`, costs, chunk continuity — with `STOP_FIRST`
  meaning the short-side stop;
- golden parity evidence for both directions;
- the Router's `SHORT_CAPABILITY_UNAVAILABLE` blocker is removed only when the
  full chain supports it, never earlier;
- no second backtester.

### ARK-S24-03 — Volatility-scaled stops

Replace fixed price-distance stops with a volatility-scaled alternative,
without removing the fixed variant.

Exit criteria:

- the volatility measure is computed from completed candles only, with no
  look-ahead;
- fixed-distance contracts remain valid and produce identical results;
- compiler and EA express and enforce the scaled distance exactly;
- golden parity across both stop types.

### ARK-S24-04 — Extended campaign and honest verdict

Pre-register and execute a campaign over the extended space using the Sprint 22
machinery unchanged: immutable grid, append-only trials, rationed final-OOS
budget, mandatory selection disclosure, and an immutable verdict.

Exit criteria:

- the campaign reuses the accepted ledger and executor without modification;
- no threshold, split, or cost assumption is altered;
- the selection disclosure states the extended trial count;
- `NO_EDGE_FOUND` remains a valid and complete outcome.

### ARK-S24-05 — Verifier and closure

Materialized chain verification over the extended campaign, Owner view updates,
and documentation closure.

## Explicitly out of scope

- any LIVE endpoint, config, credential, deployment, order, or trade path;
- a DEMO campaign, which remains blocked until an eligible strategy exists;
- a second backtester or any change to Backtest V1 semantics;
- modifying the accepted gate thresholds, split ratios, or cost scenarios;
- revisiting or reinterpreting the Sprint 22 `NO_EDGE_FOUND` verdict;
- multi-instrument support, which is a separate milestone;
- automatic promotion, Router selection, or learning.

## The honest prior: this sprint is more likely to fail than to succeed

Sprint 22 measured the rule contribution directly. At ×10 the observed profit
factor was 0.8813 against a zero-edge model of 0.8601 — the entry rules
themselves contributed **+0.021**.

Set that against what is required:

| geometry | spread | edge required | measured rule contribution | gap |
|---|---|---|---|---|
| ×10 | 0.25 | +0.240 | +0.021 | **11.4×** |
| ×10 | 0.18 | +0.202 | +0.021 | **9.6×** |
| ×40 | 0.18 | +0.126 | +0.021 | 6.0× |
| ×80 | 0.18 | +0.113 | +0.021 | 5.4× |

**A session filter closes a slice of the gap, not the gap.** At ×10 it moves
the shortfall from 11.4× to 9.6× the measured rule contribution. That is real
and worth having, and it is nowhere near sufficient on its own.

For Sprint 24 to produce an edge, at least one of these must be true:

1. the new blocks raise the rule contribution by roughly an order of magnitude,
   from `+0.021` to about `+0.20`;
2. volatility-scaled stops change geometry adaptively enough to lift the
   zero-edge ceiling well beyond what any fixed distance reaches;
3. `SHORT` opens a regime that a long-only direction is structurally unable to
   capture.

None of the three is implausible. None is likely either, and the Owner should
authorize this sprint knowing that the most probable outcome is a second
`NO_EDGE_FOUND` — this time over a wider space, which is itself worth knowing
but is not what the sprint is being paid for.

A cheaper alternative exists and deserves to be named: **ARK-S24-00 alone**.
The policy-freeze checkpoint is documentation and read-only analysis. It would
specify all three blocks precisely, quantify the session profile, and stop
there — leaving the Owner to decide on implementation with the specification in
hand rather than the estimate.

## Risks the Owner should accept before authorizing

1. **This is expensive.** Three blocks × (evaluator + compiler + EA + parity) is
   the bulk of the sprint. The search itself is the cheap part.
2. **It may still find nothing.** A wider space improves the odds; it does not
   guarantee an edge. `NO_EDGE_FOUND` is a plausible outcome again.
3. **Each block widens the surface that must stay correct.** `SHORT` in
   particular touches the Router and the EA's live execution path, which is the
   most safety-sensitive code in the repository.
4. **The session filter depends on readings not yet taken.** ARK-S24-00 should
   not freeze the session policy on two data points.

## Contract acceptance and execution protocol

Accept and authorize only ARK-S24-00 with:

```text
DITERIMA — KONTRAK ARK-S24
Mulai ARK-S24-00.
```

After acceptance, this contract is committed and pushed before ARK-S24-00
begins. Every subsequent checkpoint requires its own explicit acceptance and
must be committed and pushed before the next begins.
