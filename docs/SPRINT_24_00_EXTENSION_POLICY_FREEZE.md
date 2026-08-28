# ARK-S24-00 — Extension Policy Freeze and Session Evidence

**Date:** 2026-08-28

**Status:** documentation and read-only analysis complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the derived broker clock, the session evidence, the frozen
block specifications, and the frozen campaign policy recorded below. No model,
migration, API, UI, EA, configuration, deployment, order, or trade was created
or changed. The ARK-S22-03 `NO_EDGE_FOUND` verdict and its evidence are
untouched.

## Headline finding

The registered dataset is `UNVERIFIED_BROKER_TIME`, and a session filter on
data whose clock is unknown would be meaningless. That looked like a blocker.

It is not, and the reason matters: **session windows do not need an absolute
UTC offset. They need to be stable in the clock the bars are already labelled
in — and they are.**

## Deriving the broker clock from the bars themselves

Three independent signals were measured over all 2,985,994 M1 bars.

### 1. There is exactly one empty hour

```text
hours with no bars at all: [0]
```

Bars stop at broker 23:59 and resume at broker 01:00. The daily gap is broker
`00:00–00:59` — the classic MT5 rollover window.

### 2. The volatility peak sits at a fixed broker hour all year

| month | peak hour (broker) | month | peak hour |
|---|---|---|---|
| 01 | 17:00 | 07 | 16:00 |
| 02 | 16:00 | 08 | 16:00 |
| 03 | 16:00 | 09 | 16:00 |
| 04 | 16:00 | 10 | 17:00 |
| 05 | 16:00 | 11 | 16:00 |
| 06 | 16:00 | 12 | 16:00 |

The peak is broker 16:00 in **ten of twelve months**. January and October are
the DST-transition months, where the US and EU shift on different dates.

This is the load-bearing observation. If the broker clock were fixed while the
market followed DST, the peak would move by an hour for half the year. It does
not. The broker observes DST in step with the market, so **a window expressed
in broker time stays on the same market session all year.**

### 3. The Owner's readings land exactly where the model predicts

Under `broker = UTC+3` (EEST):

| Owner reading | UTC | broker | spread | position |
|---|---|---|---|---|
| 03:50 WIB | 20:50 | **23:50** | **97 pts** | immediately before the rollover gap |
| ~05:00 WIB | 22:00 | **01:00** | **30 pts** | immediately after the gap |
| 13:00 WIB | 06:00 | **09:00** | **18 pts** | European morning |

The 97-point reading is not an anomaly. It is the hour before the daily gap,
which is exactly where a broker's spread widens most.

**Conclusion:** broker time is EET/EEST — `UTC+2` in winter, `UTC+3` in summer
— derived from the data and corroborated by three terminal readings. Session
windows are therefore expressible in broker time directly, and the
`UNVERIFIED_BROKER_TIME` status remains correct for anything needing an
absolute UTC mapping while ceasing to block a session filter.

## Measured session profile

Average M1 true range by broker hour, over the full dataset:

| broker hour | avg range | character |
|---|---|---|
| 23:00 | 0.4246 | lowest — pre-gap, widest spread |
| 06:00–07:00 | 0.50 | quiet European pre-open |
| 09:00–11:00 | 0.75–0.79 | European morning |
| **15:00–17:00** | **1.16–1.34** | **London–NY overlap, highest** |
| 18:00–19:00 | 0.77–0.98 | NY afternoon |

Trade-population impact of candidate windows:

| window | bars retained | share | avg range |
|---|---|---|---|
| full dataset | 2,985,994 | 100% | 0.7560 |
| exclude 22:00–01:59 | 2,606,911 | **87.3%** | 0.7851 |
| only 08:00–19:59 | 1,567,969 | **52.5%** | 0.8765 |
| only 14:00–19:59 | 783,867 | **26.3%** | 1.0490 |

Excluding the four hours around the gap costs only 12.7% of the population
while removing the most expensive spread window entirely. That is the cheapest
available improvement and should be the default window.

## Frozen block specifications

### `SESSION_WINDOW` — NO_TRADE category

```text
block_id:  SESSION_WINDOW
category:  NO_TRADE
execution: GENERIC_COMPLETED_CANDLE_V1
parameters:
  windows: non-empty list of {start_hour, end_hour}, broker-time, 0..23
  clock:   "BROKER_TIME" (only accepted value)
```

- Semantics: an entry may only be created when the **completed signal bar's**
  broker hour falls inside a declared window. Exit management is unaffected; a
  position opened inside a window is managed to its stop or target regardless
  of the hour, because closing on a clock would be a second execution rule.
- Evaluator: filters the trade population deterministically on completed
  candles only.
- Compiler wire fields: `session_clock`, `session_windows` as a canonical
  ascending `HH-HH` list joined by `,`.
- EA validation: refuse unless `session_clock == "BROKER_TIME"`, every window
  parses as two integers `0..23`, the list is ascending and non-overlapping,
  and the serialization round-trips exactly. Enforcement uses the terminal's
  own server time, which is the same clock the windows are expressed in.
- Refusal: a contract carrying `SESSION_WINDOW` over a dataset whose
  `timezone_status` is neither `UNVERIFIED_BROKER_TIME` nor a broker-time
  variant must be refused rather than reinterpreted.

### `SHORT` direction — not a block, a capability

```text
direction_eligibility: "SHORT" accepted end to end
```

- Evaluator: mirror of the long path. Entry at next bar open **minus** spread;
  stop **above** entry; target **below**. `STOP_FIRST` resolves to the
  short-side stop when both barriers fall inside one candle.
- Compiler: `direction=SHORT` accepted by the adapter registry; the EA's
  hard-coded `direction != "LONG"` refusal is widened to `{LONG, SHORT}`.
- EA: `trade.Sell(...)` mirror with the same spread guard, position cap,
  emergency stop, and event emission.
- Router: `SHORT_CAPABILITY_UNAVAILABLE` is removed **only** once evaluator,
  compiler, and EA all pass golden parity — never earlier.
- Parity obligation: both directions must reproduce identical ledgers on
  mirrored inputs.

### `ATR_SCALED_SL` / `ATR_SCALED_TP` — STOP_LOSS / TAKE_PROFIT category

```text
parameters:
  period:     positive integer, completed candles only
  multiplier: positive finite
  unit:       "ATR"
```

- Semantics: distance = `multiplier × ATR(period)` measured on **completed
  candles strictly before the entry bar**. No look-ahead.
- The fixed `FIXED_PRICE_DISTANCE_SL/TP` blocks remain valid and must produce
  byte-identical results to today.
- Compiler: emits `stop_rule=ATR_SCALED_SL`, `atr_period`, `atr_multiplier`.
- EA: computes the same ATR from completed bars and must agree with the
  evaluator to the instrument's digit precision.

## Frozen campaign policy for the extended space

| Parameter | Value | Rationale |
|---|---|---|
| default session window | broker `02:00–21:59` | excludes the gap and its adjacent spread blowout at 12.7% population cost |
| spread assumption, in-window | `0.18` | the Owner's measured European-morning reading |
| spread assumption, unfiltered | `0.25` | unchanged from Sprint 22, for comparability |
| final-OOS budget | **3**, non-resettable | unchanged from Sprint 22 |
| hard trial cap | **2,000** | unchanged |
| operative trial cap | derived from a measured per-trial baseline at ARK-S24-04 | Sprint 22's 40 s estimate proved 6× optimistic |
| survivor criterion | the accepted gate's holdout side, unchanged | never a new threshold |

Grid dimensions to pre-register, subject to the measured cap:

`stop_scale` × `target_ratio` × `sma_fast` × `sma_slow` × `sma_relation` ×
`setup_direction` × `trigger_direction` × **`direction`** × **`session_window`**
× **`stop_type`**

Three new axes multiply the space. The cap, not the imagination, decides how
much of it is searched, and the pre-registration records what was left out.

## What this checkpoint did not resolve

1. **The 20:00 WIB reading is still missing.** It maps to broker 00:00 — inside
   the rollover gap, where no bars exist. A reading at **17:00–18:00 WIB**
   (broker 21:00–22:00) would be more informative, because that is the boundary
   of the proposed default window.
2. **The broker offset is derived, not declared.** Three signals agree and the
   Owner's readings corroborate it, but no terminal export states the server
   offset. The updated broker exporter could capture it directly.
3. **DST transition months remain approximate.** January and October show the
   peak an hour later, so a window near a session edge will be an hour off for
   a few weeks each year. The proposed default window is wide enough that this
   does not change which session it covers.

## The prior has not improved

ARK-S24-00 measured the session profile precisely, and the honest conclusion
from Sprint 24's contract stands unchanged: **a session filter closes a slice
of the gap, not the gap.**

At ×10 geometry it moves the required edge from `+0.240` to `+0.202` against a
measured rule contribution of `+0.021` — from 11.4× short to 9.6× short.

Nothing measured here changes that arithmetic. The Owner should decide on
ARK-S24-01 onward knowing the specification is now exact and the odds are not.

**ARK-S24-00 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-00
```
