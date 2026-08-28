# ARK-S24-02 — SHORT Direction

**Date:** 2026-08-28

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers SHORT support across the kernel, evaluator, capability
registry, compiler, EA, and Router, and the parity evidence recorded below. It
is not a claim that SHORT produces an edge. No campaign was run and no DEMO,
LIVE, order, or trade authority exists.

## The first obligation: LONG did not move

`SHORT` is implemented as a **sign flip inside the sole Backtest V1 kernel**,
not as a second code path. Direction is read as `config.get("direction",
"LONG")`, so an absent key means LONG.

That absence is the load-bearing detail. `DEFAULT_CONFIG` declares no
direction, and `kernel_config` adds the key **only when the contract is SHORT**.
Every stored LONG config, its evidence, and its fingerprint therefore stay
byte-identical, and no historical evidence was invalidated.

With `sign = 1`, every expression reduces to exactly what was there before:

| quantity | expression | at `sign = 1` |
|---|---|---|
| entry | `open + sign*spread` | `open + spread` |
| stop | `entry - sign*stop_distance` | `entry - stop_distance` |
| target | `entry + sign*target_distance` | `entry + target_distance` |
| gross | `sign*(exit - entry)` | `exit - entry` |

Tests assert that an explicit `direction="LONG"` and an absent key produce
identical ledgers, and that `DEFAULT_CONFIG` still declares no direction.

## SHORT is a mirror, not an approximation

| behaviour | LONG | SHORT |
|---|---|---|
| entry | `open + spread` (buy the ask) | `open - spread` (sell the bid) |
| stop | below entry | above entry |
| target | above entry | below entry |
| stop hit | `low <= stop` | `high >= stop` |
| target hit | `high >= target` | `low <= target` |
| `STOP_FIRST` | long-side stop wins | **short-side stop wins** |
| adverse excursion | `min_low - entry` | `entry - max_high` |
| favourable excursion | `max_high - entry` | `entry - min_low` |

In both directions the spread makes the entry **worse**, which is what keeps
the cost model symmetric.

### The mirror property

The strongest parity check available without a second kernel: reflect every
price about a pivot, swap high and low, and run SHORT over the mirrored bars.
The resulting ledger reproduces the LONG ledger on `gross_pnl_price`,
`net_pnl_price`, `mae_price`, `mfe_price`, and `exit_reason`.

## A restriction removed that was not about SHORT

The MT5 adapter required `setup.direction == "BULLISH"` and
`trigger.direction == "BULLISH"`. That was never only a LONG constraint — it
also blocked the **`BEARISH` LONG variant that Sprint 22 found survives at ×80**.

The rule is now that setup and trigger must **agree with each other**, in
either polarity. A contradictory pair produces no trades at all — Sprint 22
measured exactly that — so requiring coherence loses nothing real while
unblocking two legitimate variants. Two tests assert the newly accepted cases
and one asserts the contradictory pair still fails closed.

## The EA sells, it does not merely label

| concern | implementation |
|---|---|
| entry price | `tick.bid` for a sell, `tick.ask` for a buy |
| order | `trade.Sell(...)` mirroring `trade.Buy(...)` |
| stop / target | `entry + stop` and `entry - target` when short |
| setup polarity | follows `setup_direction`, which the validator forces to equal `trigger_direction` |
| slippage | signed against the position, so a worse fill is negative either way |
| events | `SELL_REQUEST`, `SHORT_SIGNAL`, and `side` on every deal and cost event |

A test asserts the source contains `trade.Sell`, `tick.bid`, `SELL_REQUEST`,
and the bearish reversal expression — the terminal must genuinely sell, not
record a `SHORT` label on a buy.

## The Router blocker was removed last

`SHORT_CAPABILITY_UNAVAILABLE` is gone and `supported_directions` is now
`["LONG", "SHORT"]` with an empty `declared_but_unsupported_directions`.

The order mattered: the blocker was removed **only after** the kernel,
evaluator, capability registry, compiler, and EA all supported SHORT. Removing
it earlier would have let the Router emit a decision the execution chain could
not honour.

## Capability versioning

The adapter registry fingerprint changed again because `direction` is now a
bounded enum rather than a frozen constant:

| | value |
|---|---|
| accepted V1 (ARK-S20-02) | `868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea` |
| V2 after ARK-S24-01 | `8838ee05bb0df4b3bf1c5591ee387ddf42e56ac865f308ab4c6e90d2d94077a7` |
| V2 after ARK-S24-02 | `f267c5b0de3d635dc77e6a3ccc45fdca0a29ef2b24bdfcdb98f14844672477a8` |

The V1 fingerprint remains asserted in source as history. The wire checksum for
a LONG contract is **unchanged**, because a LONG config serialises exactly as
before.

## Automated verification

| Scope | Result |
|---|---|
| focused SHORT suite | **21 passed** |
| session window suite | 68 passed |
| compiler suite | 18 passed |
| kernel, evaluator, adapter, OOS suites | 35 passed |
| full backend regression | **542 passed** (519 before this checkpoint) |

Three pre-existing tests failed during development and each was correct to
fail: the adapter golden checksum, the frozen `supported_directions == ["LONG"]`
assertion, and a capability-mutation case asserting SHORT is refused. The last
was replaced by a `direction_mismatch` case that must still fail closed.

## An unrelated defect observed, not fixed

`test_strategy_router_acceptance.py::test_restart_recovery_and_safety_api_are_exact`
and `test_strategy_router_decisions.py::test_decision_api_requires_utc_and_exposes_artifact`
fail when run in isolation but pass in the full suite. They use the global
`SessionLocal` before the `TestClient` startup event creates the tables, so
they depend on an earlier test having created them.

This predates ARK-S24-02 and was verified as pre-existing rather than assumed.
It is recorded rather than fixed, because fixing it is outside this checkpoint.

## Known limitations

1. **MetaEditor has still not compiled the EA.** Two checkpoints of MQL5
   changes are now unverified by the MQL5 toolchain: ARK-S24-01's session
   parsing and ARK-S24-02's sell path. An Owner compile is required before any
   publication, and a compile failure would now span two checkpoints.
2. **No campaign has run.** Whether SHORT helps is ARK-S24-04's question.
3. **The prior is unchanged.** SHORT doubles the searchable direction space; it
   does not obviously raise the rule contribution by the order of magnitude
   ARK-S24-00 showed is required.
4. **SHORT has never executed against a broker.** The sell path is validated by
   mirrored logic and source assertions only.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_short_direction.py -q
```

Then open `ARKANA_ENGINE.mq5` in MetaEditor and confirm 0 errors and 0
warnings.

**ARK-S24-02 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-02
```
