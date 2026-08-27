# Sprint 22 — Bounded Edge Search and Honest Exhaustion

**Contract status:** accepted by the Owner on 2026-08-27

**Sprint status:** COMPLETE at ARK-S22-05. Verdict **`NO_EDGE_FOUND`**,
fingerprint `8cf4b7870f739188796b1ffaceca3aeda253cde1616e38a230de21aa0a2d84cf`.
ARK-S22-00 accepted at `b64f951`, ARK-S22-01 at `7c501b2`, ARK-S22-02 at
`9663190`, ARK-S22-03 at `4e91d46`, and ARK-S22-05 pending acceptance.

**Implementation authority:** exhausted for ARK-S22-00 through ARK-S22-05.
ARK-S22-04's conditional registry extension is unlocked by the verdict but
remains unauthorized, and its honest scope is a milestone rather than a
checkpoint.

## Why this milestone, and why not a DEMO campaign

The prior handover recommended an Owner-operated DEMO evidence campaign as the
next milestone. That recommendation cannot execute today, and the reason is not
a missing feature.

A generic DEMO contract requires a historically `VALIDATED` and currently
eligible StrategyVersion. Real runtime has none:

| StrategyVersion | Status | Generic evidence | Eligibility |
|---|---|---|---|
| `S16-03 Runtime MTF OAT` — the only real generic strategy | `CONTRACT_VALID` | **`FAIL`** | **`INELIGIBLE`** |
| `Router ready` × 5 | `VALIDATED` | `PASS` | `ELIGIBLE`, but `capability_exact: false` |
| `S13-03 passing lineage` | `VALIDATED` | none | none |
| legacy and other contract-valid rows (6) | mixed | none | none |

`GET /api/v1/generic-demo/eligibility` returns `NO_VALIDATED_STRATEGY` with an
empty `eligible_strategy_version_ids`. The five `ELIGIBLE` rows are explicit
Sprint 19 Router fixtures with synthetic checksums of the form
`router-ready-checksum-*`; they are correctly refused by generic DEMO
eligibility and must never be published.

A DEMO campaign therefore has no cargo. The binding blocker is a research
result, not an operational one: **ARKANA has never produced a strategy that
survives its own evidence gate.** Sprint 22 addresses exactly that, and nothing
else.

## Product objective

Determine, with auditable evidence, whether the currently executable strategy
space contains any strategy that survives the accepted historical evidence
gate — and if it does not, say so as a first-class, immutable result rather
than quietly widening the gate.

The sprint must be able to end in either outcome without embarrassment:

```text
EDGE_CANDIDATE_FOUND   → feeds the existing accepted evidence chain unchanged
NO_EDGE_FOUND          → immutable, honest, and a valid sprint completion
```

`NO_EDGE_FOUND` is an explicitly acceptable and valuable result. No checkpoint
may relax a threshold, widen a split, retry a failed trial with new parameters
outside the pre-registered grid, or reinterpret a `FAIL` in order to avoid it.

## The exact space that is searchable today

Only six blocks carry the `GENERIC_COMPLETED_CANDLE_V1` execution envelope and
are therefore actually executable by the accepted evaluator:

| Block | Category | Varying parameters |
|---|---|---|
| `SMA_RELATION` | CONTEXT | `fast_period`, `slow_period`, `relation` ∈ {ABOVE, BELOW} |
| `TWO_BAR_REVERSAL` | SETUP | `direction` ∈ {BULLISH, BEARISH} |
| `CANDLE_DIRECTION` | TRIGGER | `direction` ∈ {BULLISH, BEARISH} |
| `ALL_OF` / `ANY_OF` / `NOT` | BOOLEAN | composition of the above |

Everything else is structurally fixed by the accepted legacy-compatible
envelope and is **not** a search dimension in this sprint:

- instrument `XAUUSD`, execution timeframe `M1`, direction eligibility `LONG`;
- entry `NEXT_BAR_OPEN`; ambiguity `STOP_FIRST`; sizing `FIXED_LOT_DEMO` 0.01;
- `FIXED_PRICE_DISTANCE_SL` / `FIXED_PRICE_DISTANCE_TP` — distance is a
  positive finite parameter and **is** searchable; the rule shape is not;
- `FIXED_SPREAD_GUARD` maximum — searchable as a cost/selectivity parameter;
- `MAX_OPEN_POSITIONS` fixed at 1; context timeframes limited to M1/M5/M15/H1.

The gate that must be cleared is the accepted `OOS_HISTORICAL_REVIEW_V3` /
generic protocol, unchanged:

- chronological split `train 0.60 / holdout 0.20 / final_oos 0.20`;
- ≥ 100 trades in **both** holdout and final OOS;
- profit factor strictly greater than `1.10`;
- positive nominal net PnL after costs;
- adverse-cost final OOS net PnL ≥ 0 at spread ×1.50 and commission ×2.00;
- single-year and single-regime PnL concentration ≤ 0.50, calibrated on train
  bars only.

A first analytic observation that ARK-S22-00 must confirm or refute with
evidence, not assume: at the legacy geometry of `stop 0.10 / target 0.10 /
spread 0.02`, the spread consumes roughly one fifth of the gross target on
every trade. Clearing `PF > 1.10` under an additional ×1.50 spread stress may
be arithmetically implausible for *any* entry rule at that geometry. If so, the
binding constraint is the cost-to-target ratio, not the entry logic, and the
sweep must prioritise SL/TP and spread-guard geometry over entry-rule variety.

## The central risk of this sprint: searching until something passes

Sweeping a parameter grid and then reporting the best survivor is how research
platforms lie to themselves. One strategy clearing `PF > 1.10` out of 500
trials is an expected artefact of multiple testing, not an edge. This sprint is
therefore designed so that the search cannot flatter itself:

1. **Pre-registration.** The complete parameter grid and its exact trial count
   are declared and fingerprinted *before* the first trial executes. A trial
   outside the pre-registered grid cannot be recorded.
2. **Final-OOS rationing.** Trials may read train and holdout only. Final OOS
   is opened at most `N` times for the whole campaign, where `N` is small and
   frozen at ARK-S22-00, and the counter is immutable and non-resettable.
3. **Mandatory selection disclosure.** Every result carries the number of
   hypotheses tested. A survivor from a 500-trial grid is labelled as such and
   is never presented with the same weight as a pre-specified single
   hypothesis.
4. **Complete trial recording.** Failures are recorded with the same rigour as
   survivors. Dropping, re-running, or re-parameterising a failed trial outside
   the pre-registered grid is prohibited.

## Checkpoint sequence

### ARK-S22-00 — Search-space enumeration and anti-overfitting policy freeze

Documentation and read-only analysis only; no source change.

Enumerate the exact executable search space from the accepted registry
fingerprint; record why `S16-03 Runtime MTF OAT` failed by naming the precise
gate checks that returned `FAIL` or `INSUFFICIENT_EVIDENCE`; test the
cost-geometry hypothesis above against the existing stored evidence; and freeze
the campaign policy.

Exit criteria:

- the searchable and structurally fixed dimensions are stated exactly, bound to
  the accepted `STRATEGY_CAPABILITY_REGISTRY_V2` fingerprint;
- the failure mode of the one real generic strategy is recorded per gate check
  with its observed values, not summarised as `FAIL`;
- the cost-to-target arithmetic is evaluated and its implication for grid
  design is stated;
- the pre-registration schema, grid-size bound, final-OOS budget `N`, selection
  disclosure format, and the exact definition of `NO_EDGE_FOUND` are frozen;
- no model, migration, API, UI, EA, config, deployment, order, or trade change.

### ARK-S22-01 — Immutable pre-registered campaign ledger

Forward migration adding append-only `edge_search_campaigns` and
`edge_search_trials`. A campaign records its complete parameter grid, trial
count, dataset fingerprint, registry fingerprint, split policy, and final-OOS
budget, and is fingerprinted at creation. Trials bind their campaign, their
exact contract fingerprint, and their split scope.

Exit criteria:

- a campaign is immutable after creation; its grid cannot be extended,
  reordered, or reduced;
- a trial whose contract fingerprint is not derivable from the pre-registered
  grid is rejected;
- repeated and concurrent identical writes have exactly one winner; conflicting
  identity fails closed;
- the final-OOS budget counter is immutable, monotonic, and non-resettable;
- read APIs and BFF routes have no mutation side effect;
- no second backtester, no evidence mutation, no lifecycle change, no MT5
  action, order, trade, or LIVE authority.

### ARK-S22-02 — Deterministic bounded sweep over train and holdout

Execute the pre-registered grid through the existing generic completed-candle
evaluator and the sole canonical Backtest V1 kernel. Train and holdout only.

Exit criteria:

- every pre-registered trial is executed and recorded, including failures and
  insufficient-evidence outcomes;
- execution is deterministic, idempotent, and resumable after interruption
  without duplicating or skipping a trial;
- no trial reads final-OOS bars, and an attempt to do so fails closed;
- a second backtester is not introduced; the evaluator and kernel are reused
  unchanged;
- survivors are ranked by stored holdout evidence but **nothing is selected,
  promoted, or labelled validated**;
- runtime cost, wall time, and chunk continuity are recorded honestly.

### ARK-S22-03 — Rationed final-OOS access and honest outcome

One explicit Owner authorization opens final OOS for at most the frozen budget
`N` of pre-declared survivors. Each opening decrements the immutable counter.
Surviving candidates enter the **existing accepted chain unchanged** — generic
OOS evidence, stability, decision, eligibility, and explicit promotion — and
bypass none of it.

Exit criteria:

- final-OOS access requires a fresh explicit Owner authorization naming the
  exact survivor and consumes exactly one budget unit;
- the recorded result carries the total hypotheses tested and an explicit
  selection-bias disclosure;
- a survivor that clears the gate is passed to the accepted evidence chain and
  receives no shortcut to `VALIDATED`;
- if no survivor clears the gate, an immutable `NO_EDGE_FOUND` result is
  recorded with its exact campaign fingerprint, and this closes the checkpoint
  successfully;
- no threshold, split, cost assumption, or gate is modified to produce a pass.

### ARK-S22-04 — Conditional bounded registry extension

**Conditional.** Authorized only if ARK-S22-03 records `NO_EDGE_FOUND` and the
Owner then explicitly authorizes an extension. It is not authorized by
accepting this contract.

Extend the block registry with a small, individually justified set. Candidates,
in the order the Owner should consider them:

1. `SHORT` direction eligibility — currently the platform can only express half
   of the market;
2. a session or time-of-day `NO_TRADE` block — XAUUSD M1 cost and behaviour
   differ sharply across sessions;
3. volatility-scaled stop/target distances, replacing fixed price distance.

Each new block carries the full Sprint 16/20 obligation set and no less:
evaluator implementation, deterministic MT5 compiler adapter, EA parsing and
validation, golden completed-candle and risk parity evidence, and exact
fingerprint lineage. This is where the real cost of this sprint sits, which is
precisely why it is conditional rather than assumed.

Exit criteria:

- each added block is registry-declared, evaluator-executable, compiler-mapped,
  EA-validated, and parity-proven before any campaign uses it;
- existing accepted contracts, evidence, and fingerprints remain valid and
  unchanged;
- legacy Backtest V1 semantics — completed-candle inputs, next-bar entry,
  `STOP_FIRST`, costs, chunk continuity — are preserved exactly;
- no second backtester and no LIVE path.

### ARK-S22-05 — Campaign verifier, Owner UI, and closure

A materialized read-only verifier recomputing the entire campaign chain by
exact ID and fingerprint, plus an Owner view that makes the search legible:
pre-registered grid, trials executed, survivor ranking, final-OOS budget
consumed and remaining, selection disclosure, and the honest outcome.

Exit criteria:

- the verifier recomputes every campaign, trial, and final-OOS access exactly
  and fails closed on any mismatch or tampering;
- the Owner view never presents a survivor without its selection disclosure,
  and never presents `NO_EDGE_FOUND` as a failure of the platform;
- full backend and web regression, TypeScript, ESLint, production build, Docker
  restart recovery, and browser OAT pass;
- canonical documentation records commands, results, runtime counts,
  fingerprints, known limitations, and Owner OAT steps;
- `git diff --check` passes and generated/runtime artifacts are excluded;
- the Owner explicitly accepts the checkpoint.

## Explicitly out of scope

- any LIVE endpoint, config, credential, deployment, order, trade, or
  authorization path;
- a DEMO evidence campaign, publication, or MT5 activation — these remain
  blocked until an eligible strategy exists, and are a separate contract;
- a second backtester, or any change to Backtest V1 semantics;
- modifying the accepted OOS gate thresholds, split ratios, or cost scenarios
  to make a strategy pass;
- automatic promotion, automatic Router selection, or automatic learning;
- AI participation in any deterministic search, evaluation, selection, or gate
  decision; AI may draft or explain research text only;
- cleaning, relabelling, or deleting the five Sprint 19 Router fixture rows —
  that is a separate hygiene decision, not part of this search;
- profitability claims, performance guarantees, or readiness scoring.

## Known risks the Owner should accept before authorizing

1. **The search may find nothing.** The executable space is six blocks over one
   instrument, one timeframe, and one direction. `NO_EDGE_FOUND` is a plausible
   and legitimate outcome of ARK-S22-03.
2. **The sweep is computationally expensive.** Each trial replays a share of
   2,985,994 M1 bars through Backtest V1. Grid size must be bounded at
   ARK-S22-00 against measured per-trial cost, not chosen optimistically.
3. **ARK-S22-04 is where the cost concentrates.** Extending the registry means
   evaluator, compiler, EA, and parity work for every new block. It is
   deliberately conditional and separately authorized.
4. **A survivor is not an edge.** Clearing the gate once, out of a large grid,
   on one instrument, is weak evidence. The selection disclosure exists to keep
   that visible, and DEMO forward evidence would still be required afterwards.

## Contract acceptance and execution protocol

Accept and authorize only ARK-S22-00 with:

```text
DITERIMA — KONTRAK ARK-S22
Mulai ARK-S22-00.
```

After acceptance, this contract is committed and pushed before ARK-S22-00
begins. Every subsequent checkpoint requires its own explicit acceptance and
must be committed and pushed before the next checkpoint starts. Saying
`lanjut` after accepting a completed checkpoint authorizes full implementation
of only the named next checkpoint — never a later checkpoint, ARK-S22-04's
conditional extension, a DEMO campaign, or any LIVE behaviour.
