# ARK-S24-03 — Volatility-Scaled Stops

**Date:** 2026-08-28

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers `ATR_SCALED_SL` / `ATR_SCALED_TP` across the registry,
evaluator, kernel, compiler, and EA, plus the two ARK-S24-02 defects this
checkpoint found and fixed. It is not a claim that scaled stops produce an
edge. No campaign was run and no DEMO, LIVE, order, or trade authority exists.

## The first obligation: the fixed path did not move

A scaled distance is **the same single kernel reading a different number**, not
a second execution model. The kernel gained exactly one helper:

```python
def distance(rule_evaluation, key):
    if not rule_evaluation or key not in rule_evaluation:
        return config[key]
    ...
```

An absent key means the config's fixed distance. Every fixed-distance contract
therefore produces a **byte-identical ledger**, and the trade record gained no
new field at all — a test pins the exact key set, because one extra key on
every trade would have changed every stored ledger in the project.

The same absence rule runs through the evaluator: a fixed contract's decision
carries no `scaled_distances` key and no distance override, so its decisions
are unchanged too.

## No look-ahead, by construction

ATR is a mean true range over **completed candles ending at the signal bar**,
which is closed before the entry bar opens.

| layer | history it sees |
|---|---|
| evaluator | `self._available("M1", signal_m1)` — bars whose close is at or before the decision close |
| EA | `rates[1..period+1]`, series-ordered; **index 0, the forming bar, is never read** |

Two tests hold this: one shows an outlier in the last bar changes the answer
only if that bar is included, and one poisons the EA's forming bar with
`high=9999, low=-9999` and asserts the ATR is unchanged.

## Insufficient history refuses; it never defaults

If ATR cannot be computed, the evaluator marks the decision ineligible and
emits **no** distance, and the EA emits an `ATR_UNAVAILABLE` blocker and
returns before the order. A scaled contract that silently fell back to a
default distance would be a second, undeclared execution rule.

The kernel also refuses a non-positive or non-numeric override rather than
coercing it — five malformed values are asserted.

## The placeholder that is never used

The kernel's config validation requires positive distances, so a scaled
contract still needs a value in `stop_distance`. It carries
`SCALED_DISTANCE_PLACEHOLDER = 1.0`, and a test simulates a real signal and
asserts the distance actually used is the ATR-scaled one, not the placeholder.

More important, `kernel_config` now carries the declared scaling:

```python
extra["distance_scaling"] = {"stop_distance": {"block_id": ..., "period": 14, "multiplier": 1.5}, ...}
```

Without it, two ATR contracts differing only in period or multiplier would
compile to **identical kernel configs** and therefore collide on the
`BacktestRun` fingerprint — the second would silently return the first's
result. The key is added only when a side is scaled, so fixed configs stay
byte-identical.

## A bounded adapter restriction, stated

The evaluator and kernel accept a scaled stop with a fixed target. The **MT5
adapter does not**: it requires both distances fixed, or both ATR-scaled on one
shared period.

ARK-S24-00 froze the wire fields as `atr_period` and `atr_multiplier`. Two
multipliers are unavoidable — the stop and the target are different distances —
so the wire carries `atr_period`, `stop_atr_multiplier`, and
`target_atr_multiplier`. One period keeps the terminal to a single ATR series,
which is what the golden vectors can hold it to. A mixed pair would put two
distance models in one EA with no golden vector covering the combination, so it
is refused rather than shipped.

Wire form, following the `NONE` convention ARK-S24-01 established:

| | fixed contract | scaled contract |
|---|---|---|
| `stop_rule` | `FIXED_PRICE_DISTANCE_SL` | `ATR_SCALED_SL` |
| `stop_distance` | `2.83000000` | `NONE` |
| `atr_period` | `NONE` | `14` |
| `stop_atr_multiplier` | `NONE` | `1.50000000` |

Nine malformed wire values are each refused, including a non-canonical
`014` period, a `1.5` multiplier that is not 8-decimal canonical, and a
`stop_distance` set while the scaled model is in force.

## Two ARK-S24-02 defects found and fixed

Both were found by writing this checkpoint's tests, not by reading the code.

### 1. Every SHORT and BEARISH config was refused by its own parser

ARK-S24-02 widened `_adapter_issues` to accept either polarity and widened the
EA to accept either. It left `parse_config`'s frozen enum table pinned at
`setup_direction == "BULLISH"`.

`validation_report` calls `parse_config` on the text it just compiled, so every
coherent BEARISH or SHORT contract compiled and was then rejected by the same
module — including the **BEARISH LONG variant Sprint 22 found survives at ×80**,
which ARK-S24-02 was explicitly written to unblock.

Verified before fixing: a hand-built coherent SHORT config was refused with
`MT5 configuration safety enum differs`. The rule is now coherence — declared
polarity, setup equal to trigger — which is what the EA already enforced.

### 2. The EA would not have compiled

ARK-S24-01 added `session_clock` and `session_windows` to the EA's payload
builder, its field parser, and its required-field list — but **never declared
them in the `GenericConfig` struct**. `ARKANA_ENGINE.mq5` would have failed to
compile in MetaEditor, and both ARK-S24-01 and ARK-S24-02 were reported as
`VALIDATED` over that source.

Nothing in the suite could see it, because every EA assertion was a substring
match on the source text and the substrings were all present.

Three structural tests now exist that would have caught it:

- every `cfg.<field>` and `active_generic.<field>` reference must resolve to a
  declared struct member;
- the EA's payload builder must emit **exactly** `WIRE_FIELDS`, in order — a
  mismatch means every published config fails its checksum on the terminal;
- the EA's required-field list must equal `WIRE_FIELDS` plus `checksum`.

This is the concrete cost of the un-run MetaEditor compile, and it is the
second checkpoint in a row where the limitation was recorded rather than
resolved. The structural tests reduce the exposure; they do not replace a
compile.

### 3. The golden vector was still LONG-only

`evaluate_golden_vector` — the shared Python/EA semantics — still hardcoded a
bullish reversal, a bullish trigger, `side: "LONG"`, and a long-side barrier
resolution. Asserting EA parity against it would have proved parity with
semantics the EA no longer has. It now follows `setup_direction`, `direction`,
and the distance model, and reuses the evaluator's `_atr` rather than
reimplementing it, so a research/golden divergence is impossible by
construction.

## Golden parity

The EA's `CompletedAtr` is transcribed literally into the test suite in
series order, and asserted equal to the evaluator's `_atr` **for every period
in 1, 2, 3, 5, 14**. A divergence between MQL5 and research fails a test rather
than a live position on the Owner's terminal.

## Capability versioning

The registry gained `ATR_SCALED_SL`, `ATR_SCALED_TP`, and a `distance_units`
declaration, so the fingerprint moved again. Consistent with ARK-S24-02, the
capability stays `..._V2` — runtime holds zero compilations and zero
publications, so nothing depends on the intermediate values.

| | value |
|---|---|
| accepted V1 (ARK-S20-02) | `868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea` |
| V2 after ARK-S24-01 | `8838ee05bb0df4b3bf1c5591ee387ddf42e56ac865f308ab4c6e90d2d94077a7` |
| V2 after ARK-S24-02 | `f267c5b0de3d635dc77e6a3ccc45fdca0a29ef2b24bdfcdb98f14844672477a8` |
| **V2 after ARK-S24-03** | **`4ede222b059686a03ded9d0854d1a4fe7a701b75e9fea86134eca76587304b46`** |

The wire golden also moved, because three fields were added:

| | value |
|---|---|
| config checksum | `0bbf1916f7ad6dffb6eb7940c22226c0c2770290505603359c5c0db8dec72503` |
| `sha256(config_text)` | `b26884cf4ce1c73dfc8cf535821e4633eec9eae14437eb301206c98de97ad6c0` |

## Automated verification

| Scope | Result |
|---|---|
| focused ARK-S24-03 suite | **59 passed** |
| full backend regression | **601 passed** (542 before this checkpoint) |
| web regression | 44 passed |

One pre-existing test failed during development and was correct to fail: the
wire golden checksum, which is exactly what a golden checksum is for.

## Known limitations

1. **MetaEditor has still not compiled the EA.** Three checkpoints of MQL5
   changes are now unverified by the MQL5 toolchain, and this checkpoint proved
   that at least one of them did not compile. The structural tests close the
   specific hole found; an Owner compile remains required before any
   publication.
2. **No campaign has run.** Whether volatility scaling helps is ARK-S24-04's
   question.
3. **The prior is unchanged.** ARK-S24-00 measured a rule contribution of
   `+0.021` against a required `+0.202` — 9.6× short. Scaling stops to
   volatility changes the geometry per trade; it does not obviously supply an
   order of magnitude.
4. **Mixed fixed/scaled pairs are unreachable on MT5.** They remain expressible
   in research and are refused at the adapter, by design and with the reason
   stated above.
5. **ATR is a simple mean, not Wilder's smoothing.** It is the definition
   ARK-S24-00 froze, and both layers implement the same one; a different
   definition would be a new block, not an edit.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_volatility_scaled_stops.py -q
```

Then open `ARKANA_ENGINE.mq5` in MetaEditor and confirm 0 errors and 0
warnings. This compile now matters more than at the previous two checkpoints:
a defect that would have failed it has already been found and fixed here.

**ARK-S24-03 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-03
```
