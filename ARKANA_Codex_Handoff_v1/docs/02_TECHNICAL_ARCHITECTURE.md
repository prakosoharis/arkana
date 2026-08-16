# ARKANA Technical Architecture Blueprint

**Version:** 1.0  
**Purpose:** Implementation boundary and component contract.  
**Important:** Reuse the existing repository stack. Do not rewrite working components merely because this document names a logical service differently.

---

## 1. Architectural Principle

ARKANA uses a **split-brain architecture by responsibility**:

- **ARKANA Research/Command Plane**: research, historical analytics, backtest, strategy governance, UI, AI assistance, telemetry.
- **MT5 Execution Plane**: realtime tick evaluation, risk, order execution, position management.

The execution plane is intentionally independent of the browser.

```text
                              ┌──────────────────────────┐
                              │      ARKANA WEB UI       │
                              │ research / cockpit / UX  │
                              └─────────────┬────────────┘
                                            │
                              ┌─────────────▼────────────┐
                              │    ARKANA APPLICATION    │
                              │ API / jobs / governance  │
                              └──────┬───────────┬───────┘
                                     │           │
                       ┌─────────────▼───┐   ┌───▼──────────────┐
                       │ Research Engine │   │ Strategy Registry │
                       │ / Backtest      │   │ version/config    │
                       └─────────┬───────┘   └────────┬──────────┘
                                 │                    │
                       ┌─────────▼─────────┐          │ config sync
                       │ Historical /      │          │ non-critical
                       │ Feature Store     │          ▼
                       └───────────────────┘   ┌───────────────────┐
                                             │   ARKANA MT5 EA    │
BROKER TICKS ───────────────────────────────►│ Strategy + Risk    │
                                             │ Execution Engine   │
                                             └─────────┬─────────┘
                                                       │
                                                       ▼
                                                     BROKER
```

---

# 2. Logical Components

## 2.1 Web UI

Responsibilities:
- Live Decision cockpit;
- chart + overlays;
- AI Chart Analyst input;
- Research Lab;
- Visual Validation browser;
- Backtest Lab;
- Strategy Library;
- Demo Deployment;
- Trade Journal;
- MT5/Data health;
- settings.

UI implementation should follow the reference HTML information architecture but reuse existing framework/components.

---

## 2.2 Application/API Layer

Responsibilities:
- REST/API contracts;
- research request lifecycle;
- strategy lifecycle;
- configuration generation;
- deployment state;
- telemetry ingestion;
- journal APIs;
- AI gateway orchestration;
- authorization if/when needed.

Do not perform tick-by-tick trading decisions in this layer.

---

## 2.3 Market Data Layer

### Historical
Recommended logical storage split:

```text
Parquet / columnar store
├─ OHLC M1
├─ derived bars
├─ optional Bid/Ask tick partitions
└─ precomputed feature partitions

Relational DB
├─ dataset metadata
├─ imports
├─ data-quality results
├─ research jobs
├─ backtest runs
├─ strategy versions
├─ deployments
└─ trade journal / telemetry summary
```

Exact storage engine may reuse the repository's existing choices.

### Incremental MT5 historical synchronization

The initial MT5 snapshot remains an explicit recovery/bootstrap action. Normal
research freshness is a distinct non-trading path:

```text
Research service hourly scheduler or Sync Now
→ FILE_COMMON/ARKANA/historical/requests/<request-id>.ini
→ ARKANA_DATA_COLLECTOR OnTimer + CopyRates(XAUUSD.m, M1)
→ FILE_COMMON/.../increments/<request-id>.csv + manifest
→ validation / exact-overlap reconciliation / Parquet append fragments
→ dataset registry and freshness state
```

The request starts at the last successfully imported completed M1 plus one
minute. The collector excludes the currently forming M1 candle. Existing
single-file assets are converted once into retained base fragments; subsequent
syncs append immutable fragments and recompute only the affected M1 tail and
complete M5/M15/M30/H1/H4 buckets. Readers deterministically deduplicate by
timestamp. Conflicting same-timestamp OHLC is a data-integrity failure, never a
last-row-wins update. Broker timestamps stay `UNVERIFIED_BROKER_TIME`.

This path has no dependency on `ARKANA_ENGINE.OnTick`, Web/API requests from
the EA, AI, trading configuration, or order actions. It is local single-
instance scheduling only; a future persistent host/VPS is separate work.

### DEMO forward evidence

Sprint 11 adds an idempotent `demo_trades` relational journal populated from MT5 `OnTradeTransaction` Common-Files events. It is an observability path, not an execution dependency: the EA writes local files, then the adapter ingests them after the fact. Each record carries exact deployment/version/checksum identity when available; costs/slippage remain unavailable unless MT5 reports them.

### Requirements
- partition by symbol/date where appropriate;
- idempotent import;
- dedupe;
- gap detection;
- timezone status explicit;
- broker metadata snapshot;
- reproducible resampling rules.

---

## 2.4 Feature Engine

Responsibilities:
- derive reusable deterministic features;
- cache them;
- fingerprint feature versions;
- expose them to research/backtest/similarity.

Candidate feature groups:
- OHLC shape;
- wick/body ratios;
- ATR/volatility;
- trend/slope;
- swing points;
- support/resistance;
- order block detector;
- liquidity sweep detector;
- market structure;
- session;
- spread;
- compression/expansion;
- multi-timeframe context.

### Design rule
A feature should be calculated once for a given dataset+version whenever practical, rather than recomputed for every backtest.

---

## 2.5 Research Engine

Research engine accepts a structured `ResearchHypothesis`, never free text directly.

### Flow

```text
User free text
  ↓
Intent / AI parser
  ↓
ResearchHypothesis draft
  ↓
User-visible deterministic definition
  ↓
Research Engine
  ↓
Structured statistics + samples
```

### Research modes

#### A. Event-to-pattern
Input defines outcome event, engine finds recurring preceding/current/post features.

#### B. Pattern-to-outcome
Input defines pattern, engine measures subsequent outcome.

#### C. Current-state similarity
Input is a snapshot/vector, engine retrieves historical analogs.

---

## 2.6 Pattern Discovery Engine

Start simple. Avoid premature deep learning.

Recommended progression:

1. deterministic feature extraction;
2. event mining and conditional frequency;
3. rule combinations with minimum-support constraints;
4. nearest-neighbor/similarity;
5. tree/boosting models only if they add measurable value;
6. clustering only where interpretable output is retained.

### Overfit controls
- minimum occurrence count;
- train/test temporal split;
- walk-forward validation;
- multiple-testing awareness;
- rule complexity penalty/limit;
- holdout period never used during candidate discovery where possible.

---

## 2.7 Backtest Engine

### Required execution models

#### Broad research model
- M1-based;
- conservative handling if both SL and TP occur inside unresolved bar;
- fast enough for many candidates.

#### Precision model
- historical Bid/Ask tick when available;
- used only after candidate survives broad research;
- spread/cost aware.

### Backtest run fingerprint
Hash or equivalent deterministic identifier based on:
- dataset/version;
- strategy version;
- feature versions;
- date range;
- cost assumptions;
- ambiguity policy;
- execution resolution;
- parameter set.

If fingerprint already exists and underlying inputs are unchanged, reuse cached results unless explicitly forced.

---

## 2.8 AI Gateway

### Responsibilities
- intent parsing fallback;
- hypothesis drafting;
- result explanation;
- research discussion;
- strategy comparison.

### Routing

```text
Prompt
  ↓
Known command parser?
  ├─ yes → deterministic command, no LLM
  └─ no
       ↓
    lightweight model
       ↓ complex?
       └─ stronger model
```

### Context sent to model
Send compact structured summaries such as:

```json
{
  "research_id": "...",
  "event_count": 4382,
  "tp3_rate": 0.64,
  "tp5_rate": 0.49,
  "sl_first_rate": 0.27,
  "regimes": [...],
  "warnings": [...]
}
```

Never send millions of raw candles.

---

# 3. Strategy Configuration Contract

Use a versioned, schema-validated strategy configuration. Sprint 07 uses the strict line-based `deployment_config_v1` contract in `services/research/app/deployment_contract.py`, mirrored by `mt5/Experts/ARKANA_ENGINE.mq5` and fixture `mt5/contracts/deployment_config_v1.ini`: canonical research instrument and exact broker execution symbol are distinct, decimal risk values have eight fractional digits, and checksum input order is fixed. Unknown, duplicate, and missing fields are rejected.

Conceptual example:

```json
{
  "schema_version": 1,
  "strategy_id": "order_block_first_retest",
  "strategy_version": "1.0.0",
  "symbol": "BROKER_CONFIGURED_SYMBOL",
  "profile": "SCALPING",
  "enabled": true,
  "allowed_environment": "DEMO",
  "entry": {
    "rule_set": "..."
  },
  "risk": {
    "risk_per_trade_pct": 0.35,
    "daily_loss_limit_pct": 2.0,
    "max_exposure_pct": 1.0
  },
  "exit": {
    "min_target_usd_move": 3.0,
    "preferred_target_usd_move": 5.0,
    "max_target_mode": "DYNAMIC_TRAILING"
  },
  "guards": {
    "max_spread": "BROKER_NORMALIZED_VALUE",
    "duplicate_signal": true
  },
  "backtest_fingerprint": "...",
  "checksum": "..."
}
```

Do not expose arbitrary executable source from an LLM to the EA.

---

# 4. Configuration Sync to MT5 EA

The exact adapter should be chosen after repository/environment audit.

Supported architectural options:

### Option A: Local/common file adapter
Best for local demo development.

```text
ARKANA generates config
  ↓
known local/shared folder
  ↓
EA reloads on timer / explicit signal
```

### Option B: Periodic HTTPS config pull
Useful when EA runs remotely.

EA fetches configuration on a low-frequency timer, validates checksum/schema/environment, caches locally, and continues using the last valid config if the endpoint is unavailable.

**Never pull configuration synchronously inside the per-tick decision path.**

### Telemetry
Event-driven or low-frequency batched telemetry:
- heartbeat;
- active config/version;
- latest decision summary;
- position state;
- execution events;
- errors.

The web does not need every raw tick.

---

# 5. Realtime MT5 EA Architecture

```text
OnTick
  ↓
Update rolling state
  ↓
Evaluate active strategy eligibility
  ↓
Signal evaluation
  ↓
Global risk guard
  ↓
LONG / SHORT / NONE
  ↓
Order/Position manager
  ↓
Broker
```

Independent timer/events handle:
- config reload;
- telemetry batch;
- heartbeat;
- non-critical sync.

### Hard rule
AI, web page, database availability, and research engine are not dependencies for `OnTick → decision → order`.

---

# 6. Suggested Domain Models

Names are logical; adapt to existing repo conventions.

## Dataset
- id
- symbol
- source
- timeframe/resolution
- start/end
- timezone_status
- checksum
- row_count
- quality_status

## ResearchHypothesis
- id
- source_prompt
- mode
- symbol
- event_definition
- pattern_definition
- context_rules
- outcome_definition
- cost_policy
- status
- version

### Typed hypothesis contract
The Research Engine receives a structured common envelope, never free text: original question, `research_mode`, instrument, optional historical period, data requirements, typed `definition`, outcomes/measures, optional filters/context, status, and version. Mode-specific definitions are schema-validated JSON (or equivalent), avoiding a table of nullable trading-setup columns. The UI renders fields dynamically by mode; a structured hypothesis remains distinct from a strategy.

Before execution, the application compares declared data and analytical-capability requirements with simple in-service registries. The assessment records availability, reasons, and separate `execution_eligibility`; only `READY_FOR_RESEARCH` + `ELIGIBLE` reaches a future Research Engine.

## ResearchRun
- id
- hypothesis_id
- fingerprint
- dataset_id
- output_summary
- sample_index
- warnings
- created_at

## BacktestRun
- id
- strategy_draft_id
- fingerprint
- execution_resolution
- metrics
- ledger_location
- validation_gates

## Strategy
- id
- canonical_name

## StrategyVersion
- strategy_id
- version
- schema_version
- deterministic_config
- status
- backtest_fingerprint
- approved_at
- checksum

## Deployment
- strategy_version
- environment
- account_reference
- status
- config_checksum
- deployed_at
- acknowledged_at

## TradeJournal
- environment
- strategy_version
- decision_timestamp
- execution_timestamp
- side
- entry/exit
- costs
- slippage
- latency
- outcome
- exit_reason
- evidence_snapshot

---

# 7. API Boundary Examples

These are semantic contracts, not mandatory URL names.

### Research
- create hypothesis draft;
- update/approve definition;
- run research;
- read research result;
- list samples;
- fetch sample chart data.

### Backtest
- start/reuse run;
- read progress/result;
- read metrics;
- read ledger;
- compare runs.

### Strategy
- create candidate from validated research/backtest;
- read strategy/version;
- approve version;
- pause/retire;

### Deployment
- preflight demo deployment;
- deploy approved version to demo;
- read EA acknowledgement;
- rollback config;

### Telemetry
- ingest heartbeat;
- ingest decision/execution event;
- read latest EA state.

---

# 8. Observability

At minimum instrument:
- API errors;
- research job failures;
- backtest runtime;
- cache hit/miss;
- EA heartbeat age;
- config version mismatch;
- strategy checksum mismatch;
- decision latency from EA;
- order execution latency;
- broker errors;
- telemetry queue failures;
- demo PnL/validation metrics.

---

# 9. Security / Safety Boundaries

- Never commit MT5 credentials.
- Never put trading credentials in frontend code.
- Demo/live account type must be detected/validated server-side and in the EA adapter where possible.
- Deployment payloads require checksum/signature strategy appropriate to the environment.
- Live account deployment path remains disabled until a later explicit milestone.
- Strategy configuration is allow-listed schema, not arbitrary code execution.

---

# 10. Deployment Topology for Initial Development

Prefer minimum moving parts.

```text
Developer machine
├─ existing ARKANA web/backend
├─ historical files / feature store
├─ relational metadata DB
├─ research/backtest engine
└─ MT5 terminal + ARKANA_ENGINE EA (demo)
```

Only introduce cloud services when a validated requirement cannot be met locally.

---

# 11. Architecture Acceptance Criteria

Architecture is correctly implemented when:

1. repository components can be mapped to the logical architecture;
2. browser closure does not terminate EA decision/position management;
3. LLM provider outage does not stop demo trading;
4. historical research never requires sending raw dataset to the LLM;
5. strategy config is versioned and checksum-verifiable;
6. only approved DEMO-compatible config can be deployed in initial releases;
7. demo trade events are attributable to exact strategy version/config;
8. duplicate computation is avoided using feature/run fingerprints where practical.
