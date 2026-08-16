# Sprint 08 — Demo Decision Cockpit & Journal

**Status: Implementation complete — Owner acceptance required.**

## Confirmed baseline

Sprint 07 owner acceptance confirmed the local shared-file adapter, compact `ARKANA/telemetry.csv` output, exact deployment acknowledgement, checksum rejection, and rollback on a DEMO terminal. The EA remains the only realtime execution owner. This sprint consumes local telemetry after it is written; it does not move API, database, or web work into `OnTick`, alter entry/risk rules, add a LIVE path, or expose raw ticks.

## Delivered scope

- Read-only, idempotent telemetry ingestion from the existing shared-file adapter into a persisted journal.
- Command Center snapshot: adapter availability, last observed telemetry, heartbeat state, emergency-stop state, active DEMO deployment, strategy/version/checksum/broker symbol, latest decision, and reported position count.
- Searchable recent decision journal with raw compact detail retained for audit and a link to the matching deployment where deterministically identifiable.
- A clear comparison panel: deployment/strategy identity is comparable; historical backtest-vs-demo performance and trade outcome are **NOT_REPORTED** until the EA publishes exit/outcome telemetry.
- No LIVE selector, LIVE API endpoint, automatic promotion, order placement, or change to EA trading decisions.

## Honest availability semantics

The Sprint 07 telemetry format reports timestamp, strategy ID/version when a config is available, broker symbol, environment, decision, detail, open-position count, and emergency-stop state. The adapter reads the historic `symbol` header as a header-level alias for `broker_symbol`; it never performs value-level symbol matching. It does not report tick age, decision latency, broker RTT, deal ticket, fills, commissions, slippage, or closed-trade outcome. The cockpit must label those fields `NOT_REPORTED`; it must never estimate them from unrelated clocks or data.

## Acceptance

1. With a valid DEMO EA attached, owner can open Command Center and see `CONNECTED`, latest heartbeat/decision, active strategy/version/checksum, broker symbol, position count, and emergency-stop state.
2. Refreshing does not duplicate journal rows.
3. Missing or unreadable telemetry shows `TELEMETRY_UNAVAILABLE` without changing EA state or deployment state.
4. The journal never invents tick age, latency, broker RTT, fill, or outcome.
5. UI visibly states `DEMO ONLY` and `LIVE LOCKED`.
6. Existing Sprint 07 deployment/rollback acceptance remains valid.

MetaEditor/real MT5 validation remains an OWNER ACCEPTANCE step; workspace tests cover parsing, persistence, idempotency, API, and UI rendering.

## Owner acceptance

1. Keep the accepted Sprint 07 DEMO deployment active on the exact broker chart and keep `ARKANA_EMERGENCY_STOP=1` for this observability test.
2. Run `docker compose up --build -d`, then wait for an EA `HEARTBEAT` in MT5 Experts.
3. Open `http://localhost:3000/command-center`.
4. Confirm `Adapter = CONNECTED`, `Emergency stop = ACTIVE`, the current broker symbol, active deployment checksum, a heartbeat/latest decision, and a populated journal.
5. Click **Refresh telemetry** twice. Confirm the journal does not duplicate the same telemetry rows.
6. Confirm tick age, decision latency, broker RTT, and trade outcome are visibly `NOT_REPORTED`.
7. Confirm the page says `LIVE LOCKED` and contains no deployment, trading, or promotion control.
8. Stop the EA or temporarily make `telemetry.csv` unavailable, refresh, and confirm `TELEMETRY_UNAVAILABLE` is shown without changing deployment state. Restore the file/EA afterwards.
