# Sprint 11 — DEMO Validation & Live Readiness

**Status: Implementation complete — real MT5 DEMO Owner Acceptance and forward evidence pending.**

## Historical vs forward DEMO context amendment

Thirty completed DEMO trades and seven observation days are a minimum forward-sampling gate for Owner review, not a robustness claim or a LIVE criterion. Historical backtest evidence and forward DEMO evidence remain separate. New recorded backtests persist `MARKET_REGIME_V1`: volatility is current M1 range; market structure is a 20-bar close efficiency ratio; quantile thresholds are frozen from the chronological first 70% of that exact backtest. No sessions, timezone conversion, AI, or financial pass threshold is used. A legacy recorded backtest without this contract is explicitly `REGIME_NOT_AVAILABLE` rather than reconstructed.

## Scope delivered

Sprint 11 extends the existing Common-Files telemetry adapter without moving Web/API/database work into `OnTick`.

- `ARKANA_ENGINE` writes exact MT5 deal events to `FILE_COMMON/ARKANA/trades.csv` from `OnTradeTransaction`, separate from its heartbeat/decision CSV.
- The event contains active strategy/version/checksum, broker symbol, DEMO environment, deal ticket/position ID, side, price, volume, realized P&L, commission/swap when MT5 reports them, and execution reason. It is not an inferred fill.
- The Research service ingests event and trade CSVs idempotently into `journal_events` and the new `demo_trades` journal. A trade record is linked only by exact config checksum to its versioned deployment.
- Command Center adds a DEMO Validation panel: observation period, completed trades, net realized P&L, realized drawdown, explicit criteria, and traceable trade journal.
- Readiness is deterministic and explainable only: `NOT_READY`, `NEEDS_MORE_EVIDENCE`, or `READY_FOR_OWNER_REVIEW`. There is no automatic promotion or LIVE action.

## Readiness policy

Safe visible defaults are 30 completed DEMO trades and 7 observation days. Financial/risk thresholds are intentionally `OWNER_CONFIGURATION_REQUIRED`, not invented. Therefore a strategy with enough trades/days remains `NEEDS_MORE_EVIDENCE` until the owner sets an explicit performance/risk governance policy in a later approved change. This prevents a current strategy from being tuned to pass.

Required checks are:

1. Deployment integrity: acknowledged `DEMO_ACTIVE`, exact deployment/version/checksum.
2. Operational health: current deployment-linked heartbeat and telemetry availability; emergency stop is recorded, never changed.
3. Evidence sufficiency: visible completed-trade and observation-period counts.
4. Performance/risk: actual deterministic metrics only; policy is pending owner configuration by default.

Zero trades is valid: a healthy heartbeat with no eligible signal is operationally healthy but has insufficient forward evidence. It is not an application error.

## Availability limits

No spread, slippage, or cost value is invented. Costs are `NOT_REPORTED` unless MT5 deal commission/swap are reported. Historical backtest evidence and forward DEMO evidence are displayed as distinct evidence classes; a small forward sample never invalidates historical evidence automatically.

## Part B — supplemental exhaustive historical validation

The original `StrategyVersion.backtest_run_id` is immutable approval evidence and is never replaced. A separate `SupplementalHistoricalValidation` record may exhaustively traverse 100% of the registered real M1 Parquet asset using the same stateful execution kernel as Quick Backtest. Quick remains bounded to its latest 5,000-bar interactive slice.

Before any full run, the shared kernel must exactly match the legacy Sprint 04 simulator per trade on the same 5,000 bars, including the legacy rule that an exit candle is consumed by the completed trade and scanning resumes from the following candle. The v1 strategy identity (rule, M1, SL/TP, spread, costs, `STOP_FIRST`, `M1_BROAD`, and lineage fingerprint) must also match exactly. Full traversal is chunked for memory safety, never sampled; chunk boundaries retain lookback and position state.

The full evidence is historical analysis only. It cannot approve, deploy, modify a strategy, satisfy DEMO forward-sampling criteria, or enable LIVE. `MARKET_REGIME_V1` is persisted only against the supplemental result using the same frozen chronological-first-70%-percent threshold contract.

## Owner Acceptance

1. Compile the updated `mt5/Experts/ARKANA_ENGINE.mq5` in MetaEditor and attach it to the accepted DEMO `XAUUSD.m` chart. Keep `ARKANA_EMERGENCY_STOP=1` initially.
2. Rebuild services: `docker compose up --build -d`, then open `http://localhost:3000/command-center`.
3. Confirm `LIVE LOCKED`, a DEMO-active deployment checksum, heartbeat, emergency-stop state, and DEMO Validation `NEEDS_MORE_EVIDENCE` with zero trades. This is expected while stop is active/no signal exists.
4. Confirm `FILE_COMMON/ARKANA/trades.csv` is created only after a real MT5 deal. Do not manually edit it.
5. After owner-controlled DEMO trading is permitted, allow a real eligible entry and close it normally. Refresh Command Center; confirm deal ticket, strategy/version, exact checksum, entry/exit, actual realized P&L, and execution state are visible.
6. Refresh twice; confirm no duplicate journal/trade rows.
7. Confirm missing commission/swap/spread/slippage remain `NOT_REPORTED`, not zero.
8. Confirm a new strategy version/deployment produces separate evidence by checksum/version; no aggregation occurs.
9. Re-enable emergency stop whenever desired. Confirm the UI records it and does not modify it.
10. Confirm no LIVE deployment, promotion, account switch, or AI dependency/action exists.

MetaEditor compilation and real broker deal lifecycle are **OWNER ACCEPTANCE REQUIRED**. Workspace verification does not claim real forward performance evidence.
