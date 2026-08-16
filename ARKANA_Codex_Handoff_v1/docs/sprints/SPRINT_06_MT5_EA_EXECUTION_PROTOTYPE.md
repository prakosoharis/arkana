# Sprint 06 — MT5 EA Execution Prototype

**Status: ACCEPTED / COMPLETE.**

## Delivered

- One generic `mt5/Experts/ARKANA_ENGINE.mq5` with cached local config reload.
- Strict DEMO account guard, configuration schema checks, M1 bullish-reversal evaluator, one-position guard, spread guard, SL/TP order submission, heartbeat/event telemetry CSV, and new-entry emergency stop.
- Safe `enabled=false`, DEMO-only local configuration example.

## Not delivered

No terminal compilation was possible here because MetaEditor is unavailable. No ARKANA API dependency, remote config pull, config deployment/sync, telemetry ingestion, live account path, LLM, or automatic strategy activation exists.

## Owner acceptance

Use the exact steps in [mt5/README.md](../../../mt5/README.md): compile on MetaEditor, attach only to a demo XAUUSD M1 chart, verify telemetry/config behavior and emergency stop, and verify live-account initialization is rejected.
