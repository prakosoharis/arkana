# AI Concept Resolver Contract

The concept resolver separates interpretation from evidence. It may identify a
research mode, instrument, timeframe, and unresolved concepts, but it never
creates a strategy, trade, backtest, approval, or deployment.

For an unresolved pattern-comparison concept, the configured AI provider may
return only a structured `ResearchRuleDefinition` draft. The request includes
the original owner question, instrument, timeframe, research mode, unresolved
concepts, available deterministic primitives, and any related confirmed rule
definitions. Malformed structured output is rejected before persistence.

The provider proposes; the Owner edits and confirms. A draft is not executable.
Only `OWNER_CONFIRMED` definitions are bound to a hypothesis by exact ID,
version, and fingerprint. Capability gaps are reported as
`CAPABILITY_NOT_SUPPORTED`, rather than being implied by the AI or silently
implemented.

AI provenance (provider/model) belongs to the draft audit trail only. The
registered OHLC dataset and generic deterministic evaluator produce historical
evidence.
