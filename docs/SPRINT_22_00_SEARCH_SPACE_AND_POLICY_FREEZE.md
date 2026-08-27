# ARK-S22-00 — Search-Space Enumeration and Anti-Overfitting Policy Freeze

**Date:** 2026-08-27

**Status:** documentation and read-only analysis complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` is limited to the enumeration, forensics, arithmetic, and frozen
policy recorded below. It is not a claim that an edge exists, that any strategy
is tradable, or that a sweep will succeed. No model, migration, API, UI, EA,
configuration, deployment, order, or trade was created or changed.

## Headline finding

The dominant obstacle to passing the evidence gate is **not** the entry rule.
It is the assumed transaction cost — and that cost has never been measured
against the Owner's real broker.

Three facts, each verified below:

1. Spread explains **75–76%** of the per-trade loss of the only real generic
   strategy on train and holdout.
2. The system's assumed spread of `0.02` equals **2 points** at the broker's
   own `digits=2 / point=0.01`. Retail XAUUSD spreads are typically 15–40
   points.
3. **No spread evidence exists anywhere in ARKANA.** The broker metadata
   exporter never captures it, and the stored snapshot has no spread field.

If the real spread is 0.20 rather than 0.02, then at the current SL/TP geometry
the arithmetic ceiling for profit factor from a zero-edge strategy falls from
`0.887` to `0.198`. No entry rule recovers that. Running a large sweep before
establishing the real spread would burn compute against an unknown.

## 1. Exact executable search space

Bound to accepted registry `STRATEGY_CAPABILITY_REGISTRY_V2`, fingerprint
`808d3506e7020b41d977fc8aae94f6cc6eb7a1c9e25a8093ea0bdb402a3b2bfb`.

Only six blocks carry the `GENERIC_COMPLETED_CANDLE_V1` envelope and are
therefore searchable rule dimensions:

| Block | Category | Searchable parameters |
|---|---|---|
| `SMA_RELATION` | CONTEXT | `fast_period`, `slow_period`, `relation` ∈ {ABOVE, BELOW} |
| `TWO_BAR_REVERSAL` | SETUP | `direction` ∈ {BULLISH, BEARISH} |
| `CANDLE_DIRECTION` | TRIGGER | `direction` ∈ {BULLISH, BEARISH} |
| `ALL_OF`, `ANY_OF`, `NOT` | BOOLEAN | composition of the above |

Nine blocks carry `LEGACY_BULLISH_REVERSAL_M1_V1` and are structurally fixed:
`ALWAYS`, `SEQUENCE_PREVIOUS_THEN_CURRENT`, `NEXT_BAR_OPEN`,
`FIXED_PRICE_DISTANCE_SL`, `FIXED_PRICE_DISTANCE_TP`, `FIXED_SPREAD_GUARD`,
`MAX_OPEN_POSITIONS`, `FIXED_LOT_DEMO`, `STOP_FIRST`.

Three of those fixed blocks nevertheless expose **numeric** parameters that are
legitimate search dimensions, and they carry far more leverage than the rule
blocks:

- `FIXED_PRICE_DISTANCE_SL.distance` — positive finite;
- `FIXED_PRICE_DISTANCE_TP.distance` — positive finite;
- `FIXED_SPREAD_GUARD.maximum` — see §4, this is the assumed cost.

Hard structural limits that are **not** searchable in Sprint 22:
instrument `XAUUSD` only ([strategy_contracts.py:35](../services/research/app/strategy_contracts.py)),
direction `LONG` only in the executable path, execution timeframe `M1`,
`MAX_OPEN_POSITIONS = 1`, sizing `FIXED_LOT_DEMO = 0.01`, entry
`NEXT_BAR_OPEN`, ambiguity `STOP_FIRST`.

### 1.1 Evaluator and MT5 adapter disagree on context timeframe

The completed-candle evaluator accepts M1/M5/M15/H1 context. The generic MT5
compiler adapter rejects anything except M1
([generic_mt5_compiler.py:124-126](../services/research/app/generic_mt5_compiler.py)).

The consequence is a trap in the pipeline: a strategy using M5, M15, or H1
context can be historically evaluated and can pass the gate, yet can **never be
compiled, published, or deployed**. The only real generic strategy is already
in this state — its context rule declares `timeframe: M5`.

**Frozen decision:** the Sprint 22 grid is restricted to **M1 context** so that
any survivor is deployable. Extending the adapter to M5/M15/H1 is deferred to
ARK-S22-04 and is not authorized here.

## 2. Forensics — why the only real generic strategy failed

StrategyVersion `37abb545-958d-4d14-a3b5-0b6f2321d8cf` (`S16-03 Runtime MTF
OAT`), contract: SMA_RELATION fast 2 / slow 5 / ABOVE on M5, TWO_BAR_REVERSAL
BULLISH on M1, ALL_OF(CANDLE_DIRECTION BULLISH, NOT CANDLE_DIRECTION BEARISH)
on M1, SL `0.283`, TP `0.417`, spread guard `0.02`, commission `0.0`.

Gate decision `FAIL`, per check with observed values:

| Check | Status | Observed |
|---|---|---|
| `minimum_trades` | **PASS** | holdout 59,936 · final_oos 73,242 (minimum 100 each) |
| `regime_calibration` | **PASS** | `AVAILABLE` |
| `positive_net_pnl_after_costs` | **FAIL** | holdout −1,596.188 · final_oos −6,082.086 |
| `profit_factor` | **FAIL** | holdout 0.8515 · final_oos 0.5892 (required > 1.10) |
| `adverse_final_oos_nonnegative` | **FAIL** | −6,485.645 (required ≥ 0) |
| `year_pnl_concentration` | `FAIL_NO_POSITIVE_PNL` | 2023 −501.6 · 2024 −1,152.2 · 2025 −2,592.1 · 2026 −3,432.4 |
| `regime_pnl_concentration` | `FAIL_NO_POSITIVE_PNL` | all six buckets negative |

Two observations matter for grid design:

- **Trade sufficiency is not a constraint.** The strategy produced ~60k–73k
  trades where 100 are required. There is enormous headroom to trade far less
  often, which §5 exploits.
- **It loses in every year and every regime.** This is not a regime-specific
  failure that a filter could repair. It is a systematic per-trade deficit.

## 3. Cost arithmetic, validated against the stored evidence

Under a driftless-walk barrier model, the probability of hitting the upper
barrier first is `d_down / (d_up + d_down)`. Entry sits `s` above the bar open,
so the market-relative barriers are `TP + s` up and `SL − s` down.

For SL `0.283`, TP `0.417`, s `0.02`:

| Quantity | Model | Observed (holdout) |
|---|---|---|
| breakeven win rate, zero spread | 40.43% | — |
| win rate | 37.57% | **36.62%** |
| profit factor | 0.8868 | **0.8515** |
| expected PnL per trade | **−0.02000** | **−0.02663** |

The model's predicted per-trade loss is `−0.02000`, which is exactly the spread.
Against the observed `−0.02663`, spread accounts for **75.1%** of the loss on
holdout and **76.3%** on train. The entry rule contributes the residual
`−0.0066` — it is slightly *worse* than random.

Final OOS behaves differently: win rate 28.57%, per-trade `−0.08304`, of which
spread is only 24.1%. There the rule has genuinely negative skill, not merely
cost drag.

**Honest statement of the failure mode:** cost is the dominant structural
handicap on train and holdout; on final OOS this specific rule additionally has
real negative skill. "It is only the spread" would be an overclaim.

## 4. The spread assumption is unvalidated, and it is the highest-leverage number in the system

`FIXED_SPREAD_GUARD.maximum` is not merely a filter. It is fed directly into
the kernel as the per-trade cost
([completed_candle_evaluator.py:193](../services/research/app/completed_candle_evaluator.py)):

```python
"spread_price": guards["FIXED_SPREAD_GUARD"]["maximum"],
```

Historical OHLC carries no spread, so in backtest this value filters nothing —
it is purely an assumption. In live MT5 the EA does filter on real spread, so
the two meanings diverge.

The stored broker snapshot for `XAUUSD.m` contains `digits=2`, `point=0.01`,
`tick_size=0.01`, `contract_size=100`, volumes and margins — **and no spread
field of any kind**. The exporter
[`ARKANA_BROKER_METADATA_EXPORTER.mq5`](../mt5/Scripts/ARKANA_BROKER_METADATA_EXPORTER.mq5)
never reads `SYMBOL_SPREAD` or `SYMBOL_ASK`/`SYMBOL_BID`.

Sensitivity of the zero-edge profit-factor ceiling, with the edge required to
reach 1.10 in parentheses:

| spread | points | ×1 geometry | ×5 | ×10 | ×20 |
|---|---|---|---|---|---|
| 0.02 | 2 | 0.8868 (+0.213) | 0.9765 (+0.124) | 0.9882 (+0.112) | 0.9941 (+0.106) |
| 0.05 | 5 | 0.7352 (+0.365) | 0.9421 (+0.158) | 0.9707 (+0.129) | 0.9853 (+0.115) |
| 0.10 | 10 | 0.5216 (+0.578) | 0.8868 (+0.213) | 0.9421 (+0.158) | 0.9707 (+0.129) |
| 0.15 | 15 | 0.3456 (+0.754) | 0.8340 (+0.266) | 0.9141 (+0.186) | 0.9563 (+0.144) |
| 0.20 | 20 | 0.1982 (+0.902) | 0.7835 (+0.316) | 0.8868 (+0.213) | 0.9421 (+0.158) |
| 0.30 | 30 | invalid | 0.6889 (+0.411) | 0.8340 (+0.266) | 0.9141 (+0.186) |
| 0.40 | 40 | invalid | 0.6019 (+0.498) | 0.7835 (+0.316) | 0.8868 (+0.213) |

"invalid" means the stop sits above the entry once spread exceeds the stop
distance — the geometry cannot exist.

**Frozen decision:** spread is **not** a free search dimension. Optimising it
would manufacture an edge by assumption. Instead every trial is evaluated at a
fixed pre-registered set of exactly three spread assumptions, and each result
publishes the whole curve rather than the best point.

**Prerequisite raised to the Owner:** the real spread of the DEMO broker must
be established before ARK-S22-02 consumes significant compute. The cheapest
path is for the Owner to read the current XAUUSD.m spread from MT5 across a few
sessions and report it; the durable path is a scoped addition of
`SYMBOL_SPREAD` and ask/bid capture to the broker metadata exporter, which is a
source change and therefore not authorized by this checkpoint.

## 5. Geometry is the highest-leverage searchable dimension

Because the spread cost is a fixed price amount per trade while the PnL swing
scales with SL/TP, enlarging the geometry dilutes the handicap. From §4 at
spread 0.02, the edge required for PF > 1.10 falls from `+0.213` at ×1 to
`+0.112` at ×10, then flattens.

The 100-trade minimum bounds how far this can go. Observed trade counts at ×1
are 59,936 holdout and 73,242 final OOS. Under a random-walk approximation the
time to reach a barrier scales with the square of its width, so trade count
falls as `1/k²`:

| scale | SL | TP | holdout ≈ | final_oos ≈ | status |
|---|---|---|---|---|---|
| ×1 | 0.28 | 0.42 | 59,936 | 73,242 | ok |
| ×5 | 1.41 | 2.08 | 2,397 | 2,930 | ok |
| ×10 | 2.83 | 4.17 | 599 | 732 | ok |
| ×15 | 4.24 | 6.25 | 266 | 326 | ok |
| ×20 | 5.66 | 8.34 | 150 | 183 | ok |
| ×24 | 6.79 | 10.01 | 104 | 127 | ok, at the limit |
| ×25 | 7.07 | 10.42 | 96 | 117 | below minimum |

**The `1/k²` relation is a theoretical estimate and must be measured
empirically in ARK-S22-02, not assumed.** The frozen geometry ceiling is
therefore `×20`, one step inside the estimated `×24` limit, and ARK-S22-02 must
abort any trial whose realised holdout trade count falls below 100 rather than
extrapolating.

## 6. Frozen campaign policy

### 6.1 Pre-registration schema

A campaign is immutable at creation and records: registry fingerprint, dataset
fingerprint, split policy, the complete enumerated parameter grid, the exact
trial count, the three spread assumptions, the final-OOS budget, and the
survivor criterion. A trial whose contract fingerprint is not derivable from
the stored grid is rejected.

### 6.2 Grid dimensions and size bound

Searchable: SL/TP scale, TP:SL ratio, SMA fast/slow periods, SMA relation,
setup direction, trigger direction, and boolean composition — all at M1 context
per §1.1, all within the `×20` ceiling per §5.

**Hard cap: 2,000 trials per campaign.** The operative bound is stricter and is
set in ARK-S22-01 from a measured single-trial wall-clock baseline against a
wall-clock budget the Owner approves. No campaign may be created before that
baseline is measured and recorded.

### 6.3 Final-OOS budget

**`N = 3`** for the entire sprint. Each opening requires a fresh explicit Owner
authorization naming one exact survivor, and decrements an immutable,
monotonic, non-resettable counter. Trials read train and holdout only; an
attempt to read final OOS outside an authorized opening fails closed.

### 6.4 Selection disclosure

Every reported result carries: total trials pre-registered, total executed,
survivor rank, the spread-sensitivity curve, and the final-OOS budget consumed
and remaining. A survivor is never presented without them. A single survivor
from a 2,000-trial grid is explicitly labelled as weak evidence consistent with
multiple testing.

### 6.5 Definition of `NO_EDGE_FOUND`

`NO_EDGE_FOUND` is recorded when the complete pre-registered grid has executed,
every trial is recorded including failures, and no trial met the pre-registered
survivor criterion on holdout — **or** every authorized final-OOS opening
failed the accepted gate. It is an immutable, successful checkpoint outcome
bound to its campaign fingerprint.

It may **never** be avoided by relaxing a threshold, widening a split, altering
a cost assumption, re-parameterising a failed trial outside the grid, or
extending the grid after results are visible.

## 7. Verification performed

Read-only. Every figure above is derived from the running Docker runtime and
committed source, not from documentation:

- registry fingerprint via `GET /api/v1/strategy-capabilities`;
- gate checks and cost-stress matrix from the stored `oos_validations` row for
  `37abb545-…`, read directly from PostgreSQL;
- contract parameters from `strategy_versions.strategy_contract`;
- broker fields from `broker_metadata_snapshots`;
- cost model recomputed independently and reconciled to the observed win rate,
  profit factor, and per-trade PnL.

Runtime state is unchanged: no row was written, no evidence materialized, no
FILE_COMMON artifact touched.

## 8. Owner decisions required before ARK-S22-01

1. **Real spread.** What is the actual XAUUSD.m spread on the DEMO broker? Any
   observation is better than none. Without it the sweep runs against an
   assumption that §4 shows may be off by an order of magnitude.
2. **Wall-clock budget.** How long may one campaign run? ARK-S22-01 will
   measure a single-trial baseline and derive the operative grid cap from it.
3. **Exporter extension.** May a scoped addition of spread capture to the
   broker metadata exporter be included in ARK-S22-01, or should it remain a
   separate authorization?

**ARK-S22-00 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S22-00
```
