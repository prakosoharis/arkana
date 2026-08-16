# Research Rule Definition Contract

`ResearchRuleDefinition` represents a deterministic input for historical
research—not a `StrategyVersion` and never executable trading configuration.

Required fields: canonical name, display name, aliases, rule type, structured
definition, version, status, source, fingerprint, and timestamps. The stored
fingerprint is SHA-256 over canonical name, rule type, structured definition,
and version.

The supported generic types are `OHLC_SEQUENCE_V1` and `DERIVED_OUTCOME_V1`.
Rules declare their visible parameters, required primitives, events, sequence
constraints, relative comparisons, and optional derived levels as data. The
current primitives are candle direction, local swing high/low, ordered
sequences, relative price comparisons, derived levels, close crossing, forward
outcomes, and exact base-rule references.

`DERIVED_OUTCOME_V1` freezes the exact ID/version/fingerprint of its confirmed
base rule at confirmation. A later base-rule version therefore cannot silently
change the meaning of an existing dependent rule or research run. Unsupported
primitives remain `CAPABILITY_NOT_SUPPORTED`. If an AI draft declares
ambiguities, the Owner must select a recorded resolution before confirmation.

AI can draft rules only. It cannot confirm, count occurrences, create evidence,
create a strategy, backtest, deploy, or trade. The deterministic execution
engine produces the evidence only after owner confirmation and eligibility.
