# ARK-S24-01 — Session Filter Block

**Date:** 2026-08-28

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the `SESSION_WINDOW` block across registry, evaluator,
compiler, and EA, and the parity evidence recorded below. It is not a claim
that a session filter produces an edge. No campaign was run, no strategy
created, and no DEMO, LIVE, order, or trade authority exists.

## Outcome

`SESSION_WINDOW` is a `NO_TRADE` block that restricts entries to declared
broker-hour windows. It is implemented end to end: registry declaration,
deterministic evaluator semantics, canonical compiler wire format, and EA
parsing, validation, and **enforcement**.

The clock is broker time throughout. ARK-S24-00 established that the broker
observes DST in step with the market, so a window expressed in broker time
stays on the same market session all year — and broker time is the same clock
`TimeCurrent()` reports, so the terminal performs no offset conversion.

## The decision that shaped the semantics

A window governs **entry only**. A position opened inside a window is managed
to its stop or target regardless of the hour.

Closing on a clock would be a second execution rule, and Backtest V1 has
exactly one. The alternative would have silently changed exit semantics for
every contract, which is precisely the kind of change this project forbids.

The filter is judged on the **completed signal bar**, never on the entry bar,
matching every other rule in the evaluator and matching what the EA can know at
decision time.

## Backward compatibility

A contract without the block behaves identically to before — the evaluator
returns no `session_window` key at all, and the compiler writes the explicit
absence `NONE` rather than an empty string so the EA can distinguish "no filter
declared" from "field lost in transport".

A test asserts the filter **can only subtract, never add**: it may refuse an
otherwise-eligible signal but can never create one.

## The capability was versioned rather than edited

Adding the block changed the adapter's declared capability, which changed the
adapter registry fingerprint. That broke the ARK-S20-02 golden checksum test —
correctly, because that is what a golden checksum is for.

Editing the frozen value in place would have made the accepted ARK-S20-02
record untrue. Instead the capability was **versioned**:

| | value |
|---|---|
| accepted V1 fingerprint | `868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea` |
| new capability | `GENERIC_SMA_REVERSAL_LONG_M1_V2` |
| new registry | `GENERIC_MT5_ADAPTER_REGISTRY_V2` |
| V2 fingerprint | `8838ee05bb0df4b3bf1c5591ee387ddf42e56ac865f308ab4c6e90d2d94077a7` |

V1's fingerprint is retained in source as `ACCEPTED_V1_REGISTRY_FINGERPRINT`
and asserted by a test, so the accepted record stays verifiable. The EA now
accepts V2 and a test asserts it no longer accepts V1. Runtime holds zero
compilations and zero publications, so nothing depended on V1.

## Validation, at every layer

| Layer | Refuses |
|---|---|
| registry | empty list, malformed entries, hours outside 0..23, non-integer hours, windows wrapping past 23, overlapping windows, any clock but `BROKER_TIME` |
| compiler | a clock/windows pair that is half-present, non-canonical `HH-HH`, unsorted, overlapping, wrapping |
| EA | the same set, re-derived independently in MQL5, before the config is accepted |

A wrapping window such as `22-02` is refused rather than normalised, because it
would silently span the broker's rollover gap — the hour with no bars and the
widest measured spread.

## Golden parity

The EA's `ParseSessionWindows` is mirrored literally in the test suite, so a
divergence between the MQL5 validator and the compiler's wire format fails a
test rather than a publication on the Owner's terminal.

- the EA accepts exactly what the compiler emits, for single, multiple, and
  full-day windows;
- ten malformed wire values are each refused;
- declaration order does not matter: `[14-21, 02-10]` compiles to
  `02-10,14-21` and parses back in ascending order;
- **evaluator and EA agree on all 24 hours of the day**, parameterised
  hour by hour.

Enforcement placement is asserted structurally: `SessionAllows` is called
inside `GenericOnNewBar` and **before** `trade.Buy`, so a closed window blocks
the order rather than being recorded after it.

## Automated verification

| Scope | Result |
|---|---|
| focused session suite | **68 passed** |
| full backend regression | **519 passed** (450 before this checkpoint) |
| compiler and MT5 contract suites | 46 passed |

Two pre-existing tests failed during development and both were correct to fail:
the adapter golden checksum, resolved by versioning rather than by editing the
frozen value; and the EA source assertion, updated to V2 and strengthened to
require the enforcement symbols.

## Known limitations

1. **No campaign has been run.** This checkpoint makes the filter expressible
   and enforceable. Whether it helps is ARK-S24-04's question.
2. **The prior is unchanged.** ARK-S24-00 measured the relief at 15.7% of the
   required edge at ×10 geometry, against a measured rule contribution roughly
   ten times too small. A session filter remains necessary-but-not-sufficient.
3. **MetaEditor has not compiled the EA.** The MQL5 changes are validated by
   mirrored logic and source assertions, not by the MetaEditor toolchain, which
   is not available in this environment. An Owner compile is required before
   any publication.
4. **The broker offset remains derived, not declared.** Windows are stable in
   broker time regardless, but an exporter field stating the server offset
   would remove the inference.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_session_window.py -q
```

Then open `ARKANA_ENGINE.mq5` in MetaEditor and confirm it compiles with
0 errors and 0 warnings before any publication is attempted.

**ARK-S24-01 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-01
```
