# ARKANA Master Delivery Plan

This is a checkpoint/epic roadmap, not a promise to implement all detail now.

Detailed task planning is rolling: only the current sprint and next sprint should be implementation-ready.

---

## CP0 — Repository & Architecture Baseline

### Goal
Understand what already exists, get it reproducibly running, map it to the locked architecture, and eliminate duplicate planned work.

### Exit criteria
- repo boots according to documented steps;
- tests/build baseline known;
- existing features mapped to PRD;
- missing gaps identified;
- no architecture contradiction left unresolved;
- Sprint 1 scope finalized from actual repo state.

---

## CP1 — Data Foundation & Chart Shell

### Goal
Reliable XAUUSD historical dataset access and reusable multi-timeframe chart/data contract.

### Capabilities
- dataset inventory/import;
- M1 baseline;
- derived M5/M15/H1/H4;
- broker point/price normalization;
- chart shell based on UI reference;
- data quality/status.

### Exit criteria
Owner can open ARKANA and inspect actual historical XAUUSD data across supported timeframes.

---

## CP2 — Research Hypothesis Foundation

### Goal
Natural-language research idea becomes an editable structured deterministic hypothesis.

### Includes
- known command parser;
- AI fallback parser;
- hypothesis schema;
- Order Block example;
- large-M15-move event example;
- explicit pip/point normalization.

### Exit criteria
Owner can type the locked example question and verify/edit the resulting hypothesis before computation.

---

## CP3 — Event Research + Visual Validation

### Goal
Actually scan history for defined events/patterns and inspect samples visually.

### Includes
- event-to-pattern engine;
- pattern-to-outcome engine;
- occurrence indexing;
- feature summary;
- prevalence vs predictive probability;
- previous/next/winners/losers/random/false detections;
- chart overlays.

### Exit criteria
Owner can ask what commonly accompanies a large M15 move and inspect supporting/contradicting historical samples.

---

## CP4 — Deterministic Backtest & Validation

### Goal
Turn research candidates into reproducible, cost-aware trading experiments.

### Includes
- M1 broad execution model;
- conservative ambiguity policy;
- trade ledger;
- metrics;
- out-of-sample;
- walk-forward;
- cost sensitivity;
- run fingerprint/cache;
- tick precision adapter for candidates.

### Exit criteria
A candidate can be accepted/rejected using reproducible evidence.

---

## CP5 — Strategy Library & Governance

### Goal
Versioned strategy lifecycle.

### Includes
- candidate creation;
- strategy/version records;
- validation evidence;
- approval;
- regime/session policies;
- config schema;
- checksum;
- rollback metadata.

### Exit criteria
An approved strategy is immutable/versioned and ready for demo deployment artifact generation.

---

## CP6 — MT5 EA Execution Prototype

### Goal
Generic EA can load one approved strategy configuration and trade a demo account deterministically.

### Includes
- config loader/cache;
- demo-account environment guard;
- signal evaluator;
- global risk guard;
- order/position manager;
- heartbeat;
- execution telemetry;
- emergency stop.

### Exit criteria
With ARKANA browser closed, EA continues operating the approved demo strategy.

---

## CP7 — Demo Deployment End-to-End

### Goal
Deploy approved strategy from ARKANA to MT5 demo with acknowledgement and audit trail.

### Includes
- deployment preflight;
- adapter;
- checksum/version acknowledgement;
- rollback;
- deployment history;
- live deployment locked.

### Exit criteria
Owner can click Deploy to Demo, see EA acknowledge exact version, and verify live deployment remains unavailable.

---

## CP8 — Live Decision Cockpit + Journal

### Goal
Web UI monitors the EA rather than pretending to be the execution engine.

### Includes
- EA heartbeat;
- latest decision;
- active strategy/version;
- tick age;
- decision latency;
- broker RTT where measurable;
- positions;
- journal;
- backtest-vs-demo comparison.

### Exit criteria
Owner can trace a demo trade from strategy version → decision → broker execution → outcome.

---

## CP9 — Pattern Discovery & Similarity

### Goal
System can discover candidate patterns and retrieve historical analogs beyond manually named strategies.

### Includes
- feature store;
- candidate mining;
- minimum-support constraints;
- similarity vector/index;
- overfit controls;
- visual candidate inspection.

### Exit criteria
ARKANA produces candidate patterns without LLM-generated fake statistics and each candidate can be pushed into the normal research/backtest lifecycle.

---

## CP10 — AI Research Assistant Optimization

### Goal
Natural-language interface becomes useful without becoming expensive.

### Includes
- deterministic routing;
- cheap-model routing;
- strong-model escalation;
- prompt/result caching;
- compact result context;
- token/cost telemetry;
- optional batch processing.

### Exit criteria
Common chart commands incur no LLM call where deterministic intent is known, and AI cost is observable.

---

## CP11 — Demo Validation & Live Readiness Assessment

### Goal
Evaluate whether any strategy deserves consideration for live trading.

### Includes
- configurable demo validation gate;
- minimum trade/duration conditions;
- backtest-vs-demo drift analysis;
- execution quality;
- strategy pause/retire;
- explicit live-readiness report.

### Important
This checkpoint does **not** automatically enable live trading.

---

# Epic Map

| Epic | Checkpoint | Primary Outcome |
|---|---|---|
| E01 Repository Baseline | CP0 | Existing repo understood, reproducible |
| E02 Market Data | CP1 | Reliable historical/timeframe data |
| E03 Research Hypothesis | CP2 | Natural language → deterministic definition |
| E04 Event/Pattern Research | CP3 | Historical evidence + visual validation |
| E05 Backtest Engine | CP4 | Reproducible cost-aware results |
| E06 Strategy Governance | CP5 | Versioned approved strategy |
| E07 MT5 EA | CP6 | Independent demo execution |
| E08 Deployment | CP7 | Approved strategy → demo EA safely |
| E09 Cockpit & Journal | CP8 | Realtime observability/audit |
| E10 Discovery & Similarity | CP9 | Automatic candidate research |
| E11 AI Efficiency | CP10 | Low-token research interface |
| E12 Demo Validation | CP11 | Evidence-based live readiness assessment |

---

# Planning Rule

Do not detail CP2+ tasks before CP0/CP1 findings if those findings materially change implementation. Keep future checkpoints as outcome-level guidance.
