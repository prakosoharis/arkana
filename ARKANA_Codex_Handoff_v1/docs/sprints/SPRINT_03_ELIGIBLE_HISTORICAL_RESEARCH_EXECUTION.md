# Sprint 03 — Eligible Historical Research Execution & Visual Validation

**Status: Complete — owner acceptance pending.**

## Goal

Execute only `READY_FOR_RESEARCH` / `ELIGIBLE` XAUUSD hypotheses against registered Parquet bars, produce reproducible structured results, and let the owner inspect supporting samples.

## Included capabilities

- `PRICE_EVENT_TO_PATTERN` where movement uses explicit price units and required timeframe data exists;
- `PATTERN_TO_OUTCOME` with a completed deterministic candle-pattern definition;
- run fingerprint/reuse, occurrence count, directional/outcome summary, and visual sample browser;
- bounded result/sample APIs and chart overlays.

## Eligibility gate

The runner rejects every hypothesis other than `READY_FOR_RESEARCH` + `ELIGIBLE`. FOMC/external events remain `DATA_DEPENDENCY_MISSING`; no event-calendar ingestion is added.

## Out of scope

Backtest, strategy promotion, external data, similarity computation, pattern discovery, LLM, MT5, and trading.

## Owner Acceptance

1. Import the fixture or an approved XAUUSD dataset.
2. Complete an eligible price/pattern hypothesis in Research Lab.
3. Run research and verify fingerprint, occurrence summary, and samples.
4. Review the stored contextual samples and their source candles.
5. Verify FOMC remains not executable and receives no fabricated result.
