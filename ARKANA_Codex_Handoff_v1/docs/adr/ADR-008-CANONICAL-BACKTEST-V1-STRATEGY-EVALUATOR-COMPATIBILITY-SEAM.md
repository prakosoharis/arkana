# ADR-008: Canonical Backtest V1 Strategy Evaluator Compatibility Seam

**Status:** Accepted
**Date:** 2026-08-24
**Decision scope:** Documentation decision in ARK-S12-01; no adapter is
implemented by this ADR.

## Context

Backtest V1 is the only implemented stateful simulation kernel
(`services/research/app/backtesting.py`). Its current configuration validation
accepts only the legacy `BULLISH_REVERSAL_M1` XAUUSD/M1/LONG contract. The
current `StrategyVersion` is created after a `BacktestRun`, so it cannot yet
represent a target strategy before simulation.

Strategy Factory requires an immutable, deterministic StrategyVersion to exist
before it is backtested. Creating another backtester to satisfy that direction
would duplicate semantics and threaten the established legacy evidence.

## Decision

1. Backtest V1 remains ARKANA's sole canonical simulation kernel. A second
   simulator/backtester must not be created.
2. Existing legacy semantics remain regression obligations: next-bar entry,
   `STOP_FIRST`, stateful chunk continuity, cost treatment, and recorded legacy
   results.
3. A future generic deterministic Strategy Evaluator/Adapter may be added
   **in front of** the canonical kernel. It compiles an accepted StrategyVersion
   into the kernel's supported inputs/callback boundary; it does not recreate
   the trade lifecycle, SL/TP, cost, or ambiguity engine.
4. The legacy `BULLISH_REVERSAL_M1` contract must route through that future
   adapter and reproduce exact golden trade-ledger and aggregate-metric parity
   with the existing legacy path, including chunked and non-chunked execution.
5. Strategy Factory's future lifecycle requires StrategyVersion creation before
   a BacktestRun. Historical post-backtest StrategyVersion records remain
   readable and are not relabeled or migrated by this ADR.
6. Any internal change at the seam requires regression tests. Tests must cover
   legacy parity, next-bar timing, entry-candle `STOP_FIRST`, exit-candle signal
   handling, chunk boundaries, and result fingerprint semantics.
7. The adapter and kernel remain deterministic. AI may not enter deterministic
   strategy evaluation or execution.

## Consequences

- Sprint 12 may add a Strategy Contract and evaluator adapter without breaking
  the canonical kernel boundary.
- A parity result proves compatibility only. It does not make the legacy
  prototype `VALIDATED`, profitable, DEMO-ready, or LIVE-ready.
- Multi-timeframe semantics, indicators, OOS policy, capital simulation,
  Strategy Router, and DEMO compiler evolution remain separate future work.
- This ADR records authorization and constraints only. ARK-S12-01 does not add
  an adapter, migration, evaluator callback, API, UI, database status, or MT5
  behavior.

## Evidence

- `services/research/app/backtesting.py`: `simulate_kernel`, strict
  `validate_backtest_config`, legacy parity path, and supplemental chunked
  validation.
- `services/research/app/strategies.py` and `services/research/app/models.py`:
  post-backtest legacy StrategyVersion lifecycle.
- `mt5/Experts/ARKANA_ENGINE.mq5`: DEMO-only legacy rule-set support.
