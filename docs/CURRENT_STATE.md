# ARKANA Current State

## Research Concept Resolver

Implemented: natural-language pattern-comparison questions are interpreted as
`PATTERN_COMPARISON`. Unsupported concepts now enter `NEEDS_RULE_DEFINITION`,
not the owner-facing dead end `OPEN_RESEARCH / NOT_SUPPORTED`.

Research rule definitions are independent of strategies and deployment. They
are versioned, fingerprinted, auditable, and have the lifecycle `DRAFT →
OWNER_CONFIRMED` (with prior confirmed versions becoming `SUPERSEDED`). Only an
owner-confirmed rule can be used by deterministic research.

The rule evaluator is now generic rather than concept-named: supported OHLC
concepts are expressed as `OHLC_SEQUENCE_V1` data, with optional
`DERIVED_OUTCOME_V1` rules referencing an exact confirmed base rule. The
Research Lab exposes visible, editable proposed parameters and technical detail
under progressive disclosure. A new concept needs source code only if it asks
for a missing analytical primitive or unavailable data.

The evaluator has no HNS-named detector. HNS is merely the first owner-facing
example composed from the generic swing, sequence, relative-price, level,
close-cross, forward-outcome, and base-rule-reference primitives. It is
deliberately limited to OHLC and registered timeframes. Missing data remains
`DATA_DEPENDENCY_MISSING`; concepts requiring unavailable primitives remain
`CAPABILITY_NOT_SUPPORTED`.

`PATTERN_COMPARISON` visits the full registered timeframe asset through the
bulk iterator, not the bounded chart endpoint. Results retain the source
question, dataset fingerprint, rule IDs/versions/fingerprints, scope, coverage,
occurrence totals, yearly totals, and visual occurrence samples. It creates no
trade, backtest, strategy, approval, deployment, DEMO, or LIVE action.

## Locked boundaries

Backtest V1 remains COMPLETE / LOCKED. MT5 execution, DEMO deployment, LIVE
guardrails, and broker monetary contracts were not modified by this work.

## AI Research Assistant provider

The AI gateway is provider-agnostic. It supports OpenAI-compatible APIs (for
example Tencent TokenHub, Z.AI, and OpenAI) plus the native Anthropic Messages
protocol through explicit server-side configuration. The selected provider and
models are optional: deterministic interpretation and research remain usable
without AI.

Each provider has a bounded request guard and successful-response cache.
Monetary cost is `NOT_REPORTED` unless an explicit, maintainable pricing policy
is configured. Provider errors such as quota exhaustion are surfaced honestly.
