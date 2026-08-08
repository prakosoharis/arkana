# Sprint 02 — Natural Language → Research Hypothesis

**Checkpoint:** CP2  
**Implementation status:** Complete pending owner acceptance
**Scope:** Convert a research question into an editable typed draft only. Question → Hypothesis → Strategy are separate concepts. No computation, backtest, strategy activation, MT5, or LLM call is permitted.

## Acceptance

- A user can submit the locked Order Block and large-M15-move examples.
- ARKANA returns an explicit structured hypothesis, its parser source, unresolved ambiguities, and a safe `DRAFT` status.
- Definitions are editable and persisted through the research service API.
- `broker points` stay unresolved until broker metadata exists; timestamps/data are not inferred.
- Known commands use the deterministic parser. An unrecognized prompt returns `NEEDS_CLARIFICATION`; the future LLM adapter is explicitly unconfigured, not silently invoked.
- Typed modes: `PRICE_EVENT_TO_PATTERN`, `PATTERN_TO_OUTCOME`, `EXTERNAL_EVENT_TO_MARKET`, `CURRENT_STATE_SIMILARITY`, and `OPEN_RESEARCH`.
- FOMC is represented as `EXTERNAL_EVENT_TO_MARKET` with `DATA_DEPENDENCY_MISSING` when its timeline is unavailable; it is not misclassified as unclear.
- Workstream A: typed hypothesis, requirement/availability assessment, and separate execution eligibility.
- Workstream B: dynamic UI, persistence, tests, and owner acceptance.
- Only registered/auditable data and registered analytical capabilities can make a hypothesis `READY_FOR_RESEARCH` / `ELIGIBLE`.

## Out of scope

Event scanning, pattern discovery, similarity, backtests, strategy creation/approval, AI provider integration, realtime market/MT5, and execution.

## Owner Acceptance Test

1. Price event: submit the locked M15/500 broker-points question; verify `PRICE_EVENT_TO_PATTERN`, unresolved normalization, and no setup fields.
2. Pattern: submit the Order Block question; verify `PATTERN_TO_OUTCOME`, M5/H1 context, visible/editable deterministic definition, and $3/$5 outcomes.
3. External event: submit the FOMC question; verify `EXTERNAL_EVENT_TO_MARKET`, FOMC fields, missing timeline, `DATA_DEPENDENCY_MISSING`, and `NOT_ELIGIBLE`.
4. Ambiguous: submit `Cari pola bagus.`; verify `NEEDS_CLARIFICATION` and no fabricated capability/evidence.
5. Persistence: edit a relevant field, save, reload, and verify versioned typed definition persists.
