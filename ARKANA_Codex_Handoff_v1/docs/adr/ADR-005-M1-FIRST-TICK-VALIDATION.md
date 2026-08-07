# ADR-005: M1-First Research, Tick Precision Validation

**Status:** Accepted

## Decision
Use M1/derived bars for broad pattern research and candidate screening. Use historical Bid/Ask tick data for precision validation only after a candidate shows promise.

## Why
- dramatically lower compute/storage cost for discovery;
- faster iteration;
- tick ordering is still available where it materially affects SL/TP/execution accuracy.

## Consequence
Backtest results must clearly state execution resolution and ambiguity policy.
