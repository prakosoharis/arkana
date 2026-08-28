# ARK-S24-04 — Extended Campaign Protocol and Measured Budget

**Date:** 2026-08-28

**Status:** protocol, measured baseline, and proposed grid complete; **the grid
has deliberately not been pre-registered yet** and awaits Owner sight

**Technical checkpoint claim:** `VALIDATED` for the protocol and the
measurements below. No campaign was pre-registered, no trial was recorded, no
final OOS was opened, and no verdict was reached.

Pre-registration is immutable: once created, a grid can never be extended,
reordered, or pruned. That is precisely why the Owner should see it first.

## The first obligation: V1 did not move

V2 is a **new protocol**, not an edit. `build_contract` dispatches on the
parameter keys, and `_fingerprint` reads the protocol version **out of the
grid** rather than from a module constant — so the accepted ARK-S22-01 campaign
still expands to byte-identical contracts and recomputes to the fingerprint it
was accepted with.

A test asserts `DIMENSION_KEYS` is untouched, and the two protocols coexist in
one database with both verifying `PASSED`.

### The accepted executor was not modified

ARK-S24-04's first exit criterion. The executor reaches a contract only through
`build_contract(entry["parameters"])`, which dispatches. A test asserts the
executor source contains no mention of `PROTOCOL_VERSION_V2`, `stop_type`, or
`session_window`.

## Parity, measured against the accepted ledger

A V2 `FIXED/LONG/NONE` point was replayed against the same registered asset and
compared to the stored ARK-S22 trial with the same geometry:

| split | stored trades | fresh trades | stored PF | fresh PF | metrics identical |
|---|---|---|---|---|---|
| train | 299 | 299 | 1.173051 | 1.173051 | **yes** |
| holdout | 140 | 140 | 1.451119 | 1.451119 | **yes** |

The only difference between the two contracts is
`provenance.protocol_version`. The extension changed nothing about the path it
did not touch.

## The three new axes

| axis | values | note |
|---|---|---|
| `direction` | `LONG`, `SHORT` | ARK-S24-02 |
| `session_window` | `NONE`, `02-21` | ARK-S24-01; `02-21` is ARK-S24-00's default, excluding the rollover gap at 12.7% population cost |
| `stop_type` | `FIXED`, `ATR` | ARK-S24-03, period 14 |

`setup_direction` and `trigger_direction` collapse into one `polarity` axis.
This is not a judgement call: **all 192 contradictory-polarity trials in the
Sprint 22 ledger are `INSUFFICIENT_EVIDENCE`** — they produce too few trades to
assess. Dropping them removes measured-empty cells, not information.

### The two stop types are matched on mean distance

A scaled arm that was simply wider than the fixed arm would compare *geometry*,
not *adaptivity*. The multiplier is therefore

```text
atr_multiplier = reference_stop x stop_scale / MEAN_M1_TRUE_RANGE
```

with `MEAN_M1_TRUE_RANGE = 0.7560`, measured over all 2,985,994 bars at
ARK-S24-00. The two arms cost the same on average, so the only variable under
test is whether the distance follows volatility.

## The measured budget

ARK-S22-01 estimated 40 s per trial and was 6x optimistic. The ledger's 384
completed trials averaged 250.1 s — but that number carries the machine
contention of the night it ran (median 133.6 s, p90 770.2 s).

Neither number was inherited. A stratified read-only probe was run over
`stop_scale` x `stop_type` x `session_window` on the same registered asset:

| stop_scale | stop_type | window | seconds | train trades |
|---|---|---|---|---|
| 10 | FIXED | NONE | 82.4 | 11,090 |
| 10 | FIXED | 02-21 | 93.2 | 10,559 |
| 10 | ATR | NONE | 135.5 | 15,858 |
| 10 | ATR | 02-21 | **169.7** | 15,202 |
| 80 | FIXED | NONE | 23.2 | 299 |
| 80 | FIXED | 02-21 | 23.4 | 313 |
| 80 | ATR | NONE | **21.1** | 106 |
| 80 | ATR | 02-21 | 21.2 | 111 |

**mean 71.2 s, median 52.9 s, max 169.7 s.** Cost tracks trade count: a x10
stop costs roughly four times a x80 stop, and ATR is dearer than FIXED only
where trades are dense.

| | value | basis |
|---|---|---|
| measured seconds per trial | **72** | the stratified mean, rounded up |
| wall-clock budget | 18 h | margin over the estimate |
| operative trial cap | **900** | budget / measured cost |
| hard trial cap | 2,000 | unchanged from Sprint 22 |

## The proposed grid — 768 trials, ~15.4 hours

| axis | values | count |
|---|---|---|
| `stop_scale` | 10, 80 | 2 |
| `target_ratio` | 1.0, 1.474, 2.0 | 3 |
| `sma_fast` | 2, 5 | 2 |
| `sma_slow` | 10, 50 | 2 |
| `sma_relation` | ABOVE, BELOW | 2 |
| `polarity` | BULLISH, BEARISH | 2 |
| **`direction`** | LONG, SHORT | 2 |
| **`session_window`** | NONE, 02-21 | 2 |
| **`stop_type`** | FIXED, ATR | 2 |

768 trials x 72 s = **15.4 hours**, inside the 18 h budget and the 900 cap.
Sprint 22 spent 26.7 hours, so the extended space is *cheaper* than the
original.

Every point was checked: **768 of 768 assess as `CONTRACT_VALID` and executable
by the generic completed-candle evaluator.**

### What was left out, and why

The only performance-informed reduction is `stop_scale`, from four values to
two. The Sprint 22 holdout landscape was observed first:

| stop_scale | mean holdout PF | best PF | trades at best |
|---|---|---|---|
| 10 | 0.9085 | 0.9657 | 5,014 |
| 20 | 1.0019 | 1.0761 | 1,659 |
| 40 | 1.0967 | 1.1539 | 562 |
| 80 | **1.2712** | **1.4699** | 138 |

`10` and `80` are kept because they span the measured cost regimes — x10 is
where the spread dominates and nothing survives, x80 is where rules become
visible. Keeping both is what lets the new axes be tested at **both** ends. The
middle two are dropped to afford the three new axes.

This is selection on observed data and it is recorded in
`calibration_disclosure`, which pre-registration refuses to proceed without.

**The trend itself is not evidence of edge.** Rising PF with rising stop is
exactly what the cost model predicts — a wider stop amortises the same spread
over a larger move. ARK-S22-03 reached `NO_EDGE_FOUND` with a best holdout PF of
1.4699 already in hand.

## A corroborating spread reading

The Owner reported **25 points at 19:00 WIB**, which maps to **broker 15:00** —
the opening hour of the London–NY overlap and the highest-volatility hour of the
day.

| Owner reading | broker hour | spread | character |
|---|---|---|---|
| 03:50 WIB | 23:50 | 97 pts | immediately before the rollover gap |
| ~05:00 WIB | 01:00 | 30 pts | immediately after the gap |
| 13:00 WIB | 09:00 | 18 pts | European morning |
| **19:00 WIB** | **15:00** | **25 pts** | **London–NY overlap, peak volatility** |

This matters for the campaign: the frozen `0.25` cost assumption is **exactly
the measured spread at the busiest hour**, so it is not optimistic where most
trades occur. The assumption is unchanged, as ARK-S24-04 requires.

The 17:00–18:00 WIB reading (broker 21:00–22:00) is still outstanding; it is
the boundary of the proposed `02-21` window.

## An unrelated finding, recorded not fixed

The most recently imported XAUUSD dataset is a **fixture**
(`/tmp/s13-03-pass.parquet`), so any code path selecting "the latest XAUUSD
dataset" selects a fixture. The probe hit this and was pointed at the Sprint 22
dataset explicitly, which is also the correct choice for comparability.

This is the pending `S13-03 passing lineage` item and it now has a concrete
consequence. It is outside this checkpoint.

## Automated verification

| Scope | Result |
|---|---|
| focused V2 protocol suite | **30 passed** |
| edge-search suites | 61 passed |
| full backend regression | **643 passed** (613 before this checkpoint) |

## Known limitations

1. **Nothing has been pre-registered.** The grid above is a proposal. Creating
   it is irreversible.
2. **The prior is unchanged.** ARK-S24-00 measured a rule contribution of
   `+0.021` against a required `+0.202`. Three new axes multiply the search
   space; they do not multiply the edge. `NO_EDGE_FOUND` remains the most
   likely and a completely valid outcome.
3. **The 15.4 h estimate assumes the probe's machine conditions.** Sprint 22's
   own mean was 3.5x its median under contention.
4. **MetaEditor has still not compiled the EA.** Unchanged from ARK-S24-03 and
   unaffected by this checkpoint, which touches no MQL5.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_edge_search_v2_protocol.py -q
```

**ARK-S24-04 protocol is ready for Owner acceptance. Pre-registration and
execution follow acceptance, not precede it.**

```text
DITERIMA — ARK-S24-04 PROTOKOL
```
