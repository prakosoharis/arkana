# ADR-002: Demo-First Strategy Deployment

**Status:** Accepted

## Decision
A newly approved strategy/version may initially deploy only to an MT5 demo account.

Lifecycle:

```text
Research → Backtest → Approved → Demo → Demo Validated → Manual Live Readiness Decision
```

## Rules
- Live deployment is locked in initial implementation.
- Demo performance is compared with backtest expectations.
- Live promotion is never automatic.
- Demo validation thresholds are configurable product policy.
