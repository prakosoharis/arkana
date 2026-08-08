# ARKANA Product Requirements Document

**Version:** 1.0  
**Status:** Locked baseline for implementation  
**Product:** ARKANA Trading Intelligence

---

## 1. Product Vision

ARKANA is a trading research, decision-development, and command-center platform whose purpose is to discover, test, validate, deploy, and monitor trading strategies with measurable positive expectancy and controlled risk.

The end vision is an automated trading system. ARKANA itself is **not** the realtime execution engine. Approved trading logic is executed by an MT5 EA so that execution remains fast, deterministic, inexpensive, and independent of the web application.

### Product equation

```text
Market Data
+ Trading Knowledge
+ Expert Methods
+ Pattern Discovery
+ Historical Evidence
        ↓
Research Hypothesis
        ↓
Backtest + Validation
        ↓
Strategy Library
        ↓
Approved Strategy Configuration
        ↓
MT5 EA on DEMO
        ↓
Measured Demo Performance
        ↓
Manual Live Readiness Decision
```

---

## 2. Core Product Principles

1. **Evidence over opinion.** Technical theories, expert methods, and AI suggestions are hypotheses until validated against data.
2. **Deterministic trading path.** Realtime entry, exit, SL, TP, sizing, guards, and execution must not depend on an LLM.
3. **Demo first.** Newly approved strategies deploy to demo before any live consideration.
4. **No automatic live promotion.** Live promotion is a separate manual decision.
5. **Research and execution are separated.** ARKANA researches and governs; MT5 EA executes.
6. **No raw historical data to LLM.** Computation happens locally/deterministically; the LLM receives compact structured summaries.
7. **No unnecessary recomputation.** Features and research outputs are cached/fingerprinted.
8. **No blind strategy trust.** Every strategy has explicit definitions, assumptions, cost model, sample size, regimes, and validation status.
9. **No trade is a valid decision.** The system is not required to always hold a position.
10. **Every result must be inspectable.** Users can visually review detections and historical samples.

---

## 3. Primary User

Initial product target is a single owner/trader/researcher operating ARKANA for personal XAUUSD research and automated demo trading.

Future multi-user/role requirements are out of scope for the first delivery unless already present in the repository.

---

## 4. Initial Trading Scope

### Instrument

- XAUUSD first.
- Exact broker symbol is configurable and must not be hard-coded.

### Trading modes

#### Scalping
- Entry context typically M1/M5.
- Higher-timeframe context M15/H1/H4.
- Minimum preferred profit movement: approximately USD 3.
- Preferred target: approximately USD 5.
- Maximum target: dynamic, not fixed, when continuation evidence remains valid.
- SL must be strategy/structure/volatility aware, not globally fixed.

#### Intraday
- Entry context typically M5/M15.
- Higher-timeframe context H1/H4.
- Targets are adaptive using structure, volatility, probability, and strategy rules.

Trading profiles are configuration, not separate applications.

---

## 5. Product Information Architecture

```text
LIVE
├─ Live Decision
└─ Positions

RESEARCH
├─ Research Lab
│  ├─ Research Idea
│  ├─ Pattern Discovery
│  ├─ Historical Similarity
│  └─ Visual Validation
└─ Backtest Lab

STRATEGIES
├─ Strategy Library
└─ Demo Deployment

SYSTEM
├─ Trade Journal
├─ MT5 & Data
└─ Settings
```

---

# 6. Functional Requirements

## FR-01 Live Decision Cockpit

### Purpose
Display the state and decisions produced by the MT5 EA. The web page is a cockpit, not the execution engine.

### Must display
- broker symbol;
- current Bid / Ask;
- spread;
- active trading profile;
- market regime;
- active strategy/version;
- latest decision: LONG / SHORT / NO TRADE;
- entry, SL, minimum TP, preferred TP, dynamic target state;
- decision confidence or score when supported by the strategy;
- tick age;
- decision latency;
- broker/execution round-trip latency when measurable;
- EA heartbeat;
- environment badge: DEMO / LIVE;
- current risk guard state.

### Safety requirement
Loss of ARKANA web connectivity must not stop an already running EA from managing open positions according to its cached approved configuration.

### Acceptance
User can close the browser and the EA continues executing/managing its demo strategy.

---

## FR-02 Interactive Chart Analyst

### Purpose
Allow the user to ask natural-language questions about the currently displayed chart.

### Examples
- "Cari resistance terdekat."
- "Cari support terkuat dan gunakan H1 sebagai context."
- "Cari bullish order block terdekat."
- "Apakah ada liquidity sweep dalam dua jam terakhir?"
- "Jelaskan kenapa sistem memilih LONG."
- "Cari kondisi historical yang mirip dengan chart sekarang."

### Design
Common commands should route to deterministic analytics first. LLM is only needed when parsing/explanation is genuinely required.

### Output
- structured answer;
- detected levels/zones drawn on chart where relevant;
- explanation of why a level/pattern was detected;
- timeframe/context used;
- confidence or evidence count where meaningful;
- action: `Research This`.

### `Research This`
Creates a draft research hypothesis from the chart state and user question. It does not create or activate a trading strategy.

---

## FR-03 Research Idea

### Purpose
Convert a user's natural-language trading idea into an explicit deterministic hypothesis that can be verified.

### Example
User:

> Cari apakah bullish order block M5 efektif ketika trend H1 bullish untuk target minimal $3 dan $5.

ARKANA produces an editable hypothesis containing:
- instrument;
- timeframe;
- event/pattern definition;
- higher-timeframe context;
- entry trigger;
- invalidation;
- target(s);
- session/regime filters if applicable;
- historical test range;
- cost assumptions;
- ambiguous-candle policy.

### Critical rule
If a concept such as "order block" has multiple definitions, ARKANA must expose the actual deterministic definition before running research.

### Typed research hypothesis
`Question → Hypothesis → Strategy` are distinct. A hypothesis is a general research abstraction, not necessarily a trading setup. Every hypothesis has a common envelope (question, mode, instrument, period, data requirements, typed definition, outcomes, filters, status, and version) and only mode-relevant fields. `Entry Trigger`, invalidation, position, and risk fields appear only where the selected mode needs them.

Initial modes include price-event-to-pattern, pattern-to-outcome, external-event-to-market, current-state similarity, and open research. `NEEDS_CLARIFICATION` means the question is insufficiently defined; `DATA_DEPENDENCY_MISSING` means it is understood but a required dataset (for example an FOMC timeline) is unavailable.

### Question-flexible, evidence-bounded
ARKANA accepts market/trading research questions beyond strategy templates. It may create an interpretation and typed hypothesis, but may produce statistical/evidence conclusions only from registered, auditable data and supported analytical capabilities. Missing data or capability is reported honestly and is never automatically added; the owner decides whether it becomes optional future work. LLM output is never an authoritative historical data source.

---

## FR-04 Event-to-Pattern Research

### Purpose
Support questions where the user defines a market event and asks what commonly happens before, during, or after it.

### Locked example

> Apa pola yang muncul jika ada kenaikan/penurunan sekitar 500 broker points / USD-equivalent move pada candle M15?

The system must normalize ambiguous pip/point terminology into explicit price movement using broker metadata.

### Research sequence

1. Define event.
2. Find all historical occurrences.
3. Separate bullish and bearish occurrences.
4. Compute pre-event, in-event, and post-event features.
5. Rank recurring features and combinations.
6. Report prevalence **and predictive precision**.
7. Allow visual sample review.
8. Create follow-up hypothesis/backtest.

### Important statistical requirement
ARKANA must distinguish:
- `P(feature | large move)` from
- `P(large move | feature)`.

It must never present the former as if it were the latter.

### Candidate features
- candle body/range/wick ratios;
- compression;
- ATR / volatility expansion;
- momentum;
- previous high/low breaks;
- support/resistance distance;
- order block;
- liquidity sweep;
- market structure;
- H1/H4 trend;
- session;
- spread;
- volume/tick volume when available;
- sequence of prior candles;
- distance from recent swing points.

---

## FR-05 Pattern Discovery

### Purpose
Find recurring candidate market structures without requiring the user to name a known indicator or pattern.

### User inputs
- instrument;
- research period;
- trading mode;
- target movement;
- optional max adverse excursion;
- optional time horizon;
- minimum occurrences;
- optional session/regime boundaries.

### Engine output
Each candidate must include:
- deterministic feature rule;
- occurrence count;
- outcome distribution;
- positive/negative excursion;
- expected move timing;
- cost-adjusted edge estimate;
- regime/session breakdown;
- train/out-of-sample separation;
- overfit warnings;
- visual samples.

### Not allowed
The LLM may explain candidates but may not manufacture uncomputed statistics.

---

## FR-06 Historical Similarity

### Purpose
Given current or selected historical market state, retrieve similar historical states and show subsequent outcomes.

### Similarity features may include
- multi-timeframe trend;
- volatility;
- candle shape;
- momentum;
- market structure;
- support/resistance distance;
- order-block/liquidity context;
- spread;
- session;
- recent price path.

### Output
- top similar samples;
- similarity score;
- subsequent +$3/+ $5 or configured move probability;
- adverse excursion;
- time-to-target;
- chart browser.

No LLM is required for similarity calculation.

---

## FR-07 Visual Validation

Research results must not be accepted based solely on aggregate statistics.

User must be able to review:
- previous / next sample;
- winners;
- losers;
- random samples;
- false detections;
- pattern overlays;
- entry, invalidation, and outcome on chart.

This feature is mandatory for pattern definitions such as order blocks, liquidity sweeps, and support/resistance.

---

## FR-08 Backtest Lab

### Requirements
- deterministic engine;
- historical spread/cost support when available;
- M1-first broad research;
- tick Bid/Ask precision validation for promising candidates;
- conservative ambiguous intrabar policy if tick sequence is unavailable;
- separate in-sample and out-of-sample;
- walk-forward validation;
- stress/cost sensitivity;
- Monte Carlo/bootstrap where appropriate;
- trade ledger;
- reproducible run fingerprint;
- strategy/version association.

### Core metrics
- net PnL;
- expectancy per trade;
- profit factor;
- win rate;
- average win/loss;
- max drawdown;
- trade count;
- consecutive losses;
- MAE/MFE;
- target hit probability;
- time-to-target;
- results by market regime/session.

### Promotion rule
A backtest does not automatically activate a strategy.

---

## FR-09 Strategy Library

### Purpose
Repository of versioned, deterministic strategies and their evidence.

### Lifecycle

```text
DRAFT RESEARCH
  ↓
CANDIDATE
  ↓
VALIDATED / APPROVED
  ↓
DEMO DEPLOYED
  ↓
DEMO VALIDATED
  ↓
LIVE READY (manual decision only)
  ↓
ACTIVE / PAUSED / RETIRED
```

### Strategy record
- unique ID;
- name;
- version;
- symbol;
- profile;
- deterministic entry rules;
- exit rules;
- risk rules;
- allowed regimes;
- allowed sessions;
- dependency feature versions;
- backtest fingerprint;
- validation metrics;
- approval state;
- demo deployment state;
- demo metrics;
- configuration checksum;
- change history.

---

## FR-10 MT5 EA Execution Engine

### Principle
A single generic `ARKANA_ENGINE.mq5` should execute approved strategy configuration whenever practical, rather than generating one new EA source file per strategy.

### EA responsibilities
- receive tick;
- maintain required rolling feature state;
- evaluate active approved rule set;
- LONG / SHORT / NO TRADE decision;
- risk checks;
- position sizing;
- open/modify/close order;
- SL/TP/trailing logic;
- duplicate-signal guard;
- spread guard;
- exposure guard;
- daily loss guard;
- emergency stop;
- local configuration cache;
- version/checksum tracking;
- telemetry;
- trade event reporting.

### Critical requirement
EA must never call an LLM to decide a trade.

---

## FR-11 Demo Deployment

### Deployment target
Approved strategies first deploy to an MT5 demo account.

### Deployment process
1. Select approved strategy/version.
2. Validate target account is DEMO.
3. Run pre-deployment checks.
4. Generate strategy configuration artifact.
5. Compute checksum/version.
6. Sync configuration to EA through the selected adapter.
7. EA acknowledges configuration version.
8. Deployment state becomes `DEMO ACTIVE`.

### Demo validation configurable gates
Initial defaults for implementation testing:
- minimum trades: configurable (example 200);
- minimum duration: configurable (example 4 weeks);
- expectancy must remain positive above configured floor;
- drawdown below configured ceiling;
- execution errors below configured threshold;
- no unexpected strategy/config drift.

These are product configuration values, not universal trading truths.

---

## FR-12 Trade Journal

Every trade and no-trade decision relevant to validation should be attributable to:
- account environment;
- symbol;
- strategy ID/version;
- configuration checksum;
- signal timestamp;
- decision;
- decision latency;
- order timestamp;
- broker result;
- entry/exit;
- spread;
- slippage when measurable;
- SL/TP/trailing changes;
- outcome;
- exit reason;
- relevant evidence snapshot.

Purpose: compare real demo execution with backtest expectations.

---

## FR-13 MT5 & Data

### Historical data
Prefer broker-aligned MT5 data for initial XAUUSD research.

Support:
- M1 native/imported data;
- derived M5/M15/M30/H1/H4 where appropriate;
- tick Bid/Ask when available;
- broker symbol metadata;
- spread/cost metadata;
- data quality and gap checks.

### Storage policy
- columnar/partitioned files such as Parquet for large market data;
- relational DB for metadata, strategy state, job state, metrics, and journal data;
- avoid dumping every historical tick into the transactional database unless justified.

### Pip/point normalization
User-facing questions may use "pip", "point", or USD movement. Research engine must normalize them using symbol metadata and show the interpreted move before execution.

---

## FR-14 AI Gateway

### Allowed uses
- parse natural-language research idea;
- convert idea into a structured draft hypothesis;
- explain deterministic results;
- summarize backtests;
- compare strategies;
- help interpret failures;
- propose follow-up research questions.

### Cost-control routing
1. deterministic command parser first;
2. cheap model for simple intent/explanation;
3. stronger model only for complex research reasoning;
4. batch mode for non-realtime work where supported;
5. cache reusable prompts/context/results.

### Prohibited uses
- LLM on every tick;
- LLM on every candle by default;
- raw multi-million-row market data sent to model;
- autonomous activation of newly generated strategy;
- direct live-account execution decision.

---

# 7. Non-Functional Requirements

## NFR-01 Determinism
Same strategy version + same market data + same backtest parameters must reproduce the same deterministic result within defined numerical tolerance.

## NFR-02 Auditability
All strategy changes and deployments are versioned and attributable.

## NFR-03 Execution Independence
Web/API outage must not force-close or orphan active EA logic. EA follows its last valid cached config and configured safety policy.

## NFR-04 Performance
Realtime EA decision target should be measured, not assumed. Instrument:
- decision latency;
- tick age;
- order-send duration;
- broker acknowledgement where available.

No contractual millisecond number is accepted until measured on the actual environment.

## NFR-05 Cost Efficiency
Initial personal-use target:
- no GPU requirement by default;
- local research whenever practical;
- LLM on demand only;
- cache expensive feature computation;
- M1 broad scan before tick precision validation.

## NFR-06 Data Integrity
Every imported dataset records:
- source;
- symbol;
- range;
- row count;
- checksum where practical;
- timezone status;
- dedupe/gap result.

## NFR-07 Safety
- demo-first is enforced in code, not merely UI text;
- live account promotion requires explicit separately implemented policy;
- global emergency stop exists in EA;
- risk limits cannot be bypassed by a strategy rule.

## NFR-08 Testability
Every deterministic trading rule has unit tests. Every sprint has owner acceptance tests.

---

# 8. Explicit Out of Scope for Initial Delivery

- multi-broker arbitrage;
- HFT/microsecond execution;
- autonomous live-account strategy invention;
- social/copy trading;
- mobile-native app;
- dozens of instruments from day one;
- GPU-based deep learning unless simpler approaches are proven insufficient;
- fundamental/news execution automation before technical/data core is stable;
- live-account auto-promotion.

---

# 9. Success Criteria

ARKANA V1 is successful when the owner can:

1. load/reuse historical XAUUSD data;
2. ask a research question in natural language;
3. inspect the deterministic interpretation before testing;
4. run event/pattern research;
5. visually inspect historical samples;
6. backtest with reproducible results;
7. promote a strategy through explicit lifecycle gates;
8. deploy an approved version to an MT5 demo account;
9. observe EA realtime decisions and positions from ARKANA;
10. compare demo performance with backtest expectations;
11. operate the demo EA even when the ARKANA browser is closed;
12. do all of the above without using an LLM in the realtime execution path.
