# ADR-003: No LLM in Live Trading Path

**Status:** Accepted

## Decision
No LLM call is permitted between incoming MT5 tick and realtime trading decision/order execution.

## Allowed AI Uses
- parse research prompts;
- draft hypotheses;
- explain deterministic analysis;
- compare research/backtest results;
- propose follow-up experiments.

## Prohibited
- LLM deciding LONG/SHORT on every tick;
- raw historical dataset upload to an LLM;
- LLM-generated strategy automatically becoming active.
