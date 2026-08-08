# ADR-007: Question-Flexible, Evidence-Bounded Research Eligibility

**Status:** Accepted

## Decision

ARKANA accepts broad market-research questions, but generates evidence only when all required registered/auditable data and analytical capabilities are available. Hypothesis status and execution eligibility are separate.

## Consequences

- Missing data/capabilities are explicit and never trigger automatic integrations.
- The owner decides whether optional data/capability work is developed.
- LLM output is not an authoritative historical data source.
- Existing research service contains the simple data/capability registries; no new microservice or infrastructure is introduced.
