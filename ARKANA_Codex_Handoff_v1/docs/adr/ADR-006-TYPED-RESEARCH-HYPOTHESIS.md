# ADR-006: Typed Research Hypothesis

**Status:** Accepted

## Decision

Research hypotheses use one common versioned envelope plus a schema-validated typed definition selected by research mode. Question, hypothesis, and strategy are separate concepts.

## Why

ARKANA must support price events, technical patterns, external/calendar events, similarity, and open research without forcing every question into a trading setup.

## Consequences

- UI is dynamic by mode; entry/invalidation are never global requirements.
- Supported Sprint 02 modes are `PRICE_EVENT_TO_PATTERN`, `PATTERN_TO_OUTCOME`, `EXTERNAL_EVENT_TO_MARKET`, `CURRENT_STATE_SIMILARITY`, and `OPEN_RESEARCH`.
- `NEEDS_CLARIFICATION` differs from `DATA_DEPENDENCY_MISSING`.
- Mode-specific values live in validated JSON; PostgreSQL stores metadata/envelope only.
- A typed interpretation is not itself evidence, execution eligibility, or a strategy.
