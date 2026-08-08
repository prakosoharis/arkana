# Sprint 04 — Deterministic Backtest & Validation

**Status: Complete — owner acceptance pending.**

## Goal

Turn one explicit research candidate into a reproducible M1 broad backtest. The output is an auditable experiment, never an approved strategy, deployment artifact, trade signal, or MT5 instruction.

## Registered experiment

`BULLISH_REVERSAL_M1`: a bearish M1 candle followed by a bullish M1 candle; a long position enters at the next candle open. Parameters define stop distance, target distance, assumed spread, and commission. All distances are explicit XAUUSD price units.

## Execution contract

- Entry uses the next M1 open plus assumed spread (long ask); exits use recorded bar prices minus commission.
- When an M1 candle crosses both SL and TP, `STOP_FIRST` is always applied.
- Only one position is open at a time; it closes at SL, TP, or the final available bar.
- The run fingerprint includes dataset fingerprint, candidate/version, date range, cost inputs, ambiguity policy, resolution, and parameters. Identical input reuses the run.
- Results expose a trade ledger, net price PnL, win rate, profit factor, average win/loss, max drawdown, consecutive losses, MAE/MFE, split metrics, rolling windows when sufficient, and cost sensitivity.

## Scope exclusions

No Bid/Ask tick precision, short model, sizing, leverage, currency PnL, strategy lifecycle/promotion, MT5/MQL5, external data, LLM, or trading execution. Tick precision is explicitly unavailable because no registered tick dataset exists.

## Owner acceptance

1. Import the fixture or an approved M1 XAUUSD dataset.
2. Open Backtest Lab and run the default experiment with small price-unit TP/SL values suitable for the fixture.
3. Verify policy, costs, dataset, fingerprint/reuse, ledger, and metrics are visible.
4. Run again unchanged and verify reuse.
5. Confirm the result states that it is not a strategy or trade instruction.
