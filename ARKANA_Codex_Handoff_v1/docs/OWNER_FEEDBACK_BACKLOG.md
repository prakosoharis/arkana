# Owner Feedback Backlog

Deferred, non-blocking product/UX work. Do not implement automatically during Sprint 11.

- Consolidated end-of-roadmap UX refinement across Research, Discovery, and Strategy areas. Command Center empty-state review is addressed: it now distinguishes no active DEMO deployment, waiting telemetry, active telemetry, and unavailable telemetry, while retaining audit details progressively.
- Demo Validation audit review is addressed: the first detail level now explains deployment, operational health, evidence progress, and performance/risk in Owner language; raw UUIDs, checksums, enums, and JSON are retained only under per-criterion Technical Evidence.
- Historical-vs-DEMO and market-character review is addressed: validation now retains exact lineage and a versioned deterministic regime contract for new backtests, while clearly separating historical/forward samples and treating the 30-trade/7-day policy as a minimum forward-sampling gate—not proof of robustness or a LIVE criterion.
- Sprint 10 external AI provider/runtime Owner Acceptance. AI remains OFF by default.
- Owner-approved demo performance/risk governance thresholds after sufficient real DEMO evidence exists.
- Historical Bid/Ask tick, verified sessions, and external data capability decisions.
- Future persistent-host/VPS placement for 24/7 MT5 data collector operation; current implementation targets local MacBook + MT5 + Docker.
- Future realtime signal/notification channel from the independent `ARKANA_ENGINE` path. It must not depend on hourly historical synchronization.
