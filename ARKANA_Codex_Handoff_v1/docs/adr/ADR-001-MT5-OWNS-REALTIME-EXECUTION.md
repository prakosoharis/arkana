# ADR-001: MT5 EA Owns Realtime Execution

**Status:** Accepted

## Decision
Realtime signal evaluation, risk guard, order execution, SL/TP/trailing, and position management run inside the MT5 EA execution plane.

ARKANA Web is a research and command center. It monitors and explains realtime state but is not required in the per-tick execution path.

## Why
- lower latency;
- fewer network dependencies;
- lower infrastructure cost;
- resilience when web/API is unavailable;
- natural integration with broker/MT5 order lifecycle.

## Consequence
Research results must eventually become deterministic, versioned strategy configuration understood by the EA.
