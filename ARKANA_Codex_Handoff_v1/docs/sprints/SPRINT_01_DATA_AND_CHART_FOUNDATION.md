# Sprint 01 — Data & Chart Foundation

**Checkpoint:** CP1  
**Status after Sprint 0 audit:** Implementation blocked pending the actual ARKANA application repository and an approved XAUUSD historical dataset/source. This handoff package has no application module to extend and no existing task qualifies as `SKIP — EXISTING/PASS`.

## Sprint 00 audit anchors

- Baseline inventory and exact unavailable components: `docs/CURRENT_STATE.md`.
- Product/UI intent only: `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` (static prototype; all data is dummy).
- Locked data/architecture decisions: `docs/01_PRD.md` §FR-13, `docs/02_TECHNICAL_ARCHITECTURE.md` §2.3, and ADR-005.
- There are **no existing application file/module pointers** in this workspace: no `src/`, `app/`, backend, API, data pipeline, package manifest, test suite, or dataset exists. When the actual repository is supplied, update the task pointers below before implementation rather than creating parallel modules by assumption.

---

## Sprint Goal

The owner can open ARKANA locally, select XAUUSD and a supported timeframe, and inspect **real historical market data from the repository's validated dataset** with clear data-range/quality metadata.

No AI research and no auto-trading are required in this sprint.

---

## Primary Owner Story

> Saya membuka ARKANA, memilih XAUUSD dan M1/M5/M15/H1/H4, melihat candlestick real, melihat range data yang tersedia, dan tahu datanya valid atau ada gap.

---

# Tasks

## S1-T01 Canonical Symbol Configuration

Create/reuse a symbol configuration abstraction in the actual backend/domain layer so broker-specific symbol names are not hard-coded throughout the app. **Repository pointer to add after handoff:** existing domain/config module; none exists in this package.

Must represent at minimum:
- canonical symbol: XAUUSD;
- broker symbol/name;
- digits;
- point size;
- contract metadata if known;
- point/pip/price-move normalization helpers.

### Acceptance
A test proves that a user research threshold can be represented as explicit price movement and broker-point equivalent without ambiguous hard-coded assumptions.

---

## S1-T02 Historical Dataset Registry

Create/reuse a dataset registry API/model exposing the approved dataset actually supplied to the implementation repository. **Repository pointer to add after handoff:** existing persistence/import metadata module; none exists in this package.
- source;
- symbol;
- resolution;
- date range;
- row count;
- timezone status;
- quality/gap status;
- storage location reference, not raw file contents.

### Acceptance
UI/API can show actual available range for XAUUSD.

---

## S1-T03 Timeframe Data Service

Create/reuse a single backend service for reading/resampling supported OHLC data. **Repository pointer to add after handoff:** existing market-data reader/resampler; none exists in this package.

Required initial TFs:
- M1;
- M5;
- M15;
- H1;
- H4.

Rules:
- do not implement duplicate resampling logic in frontend;
- resampling must be deterministic;
- existing native TF may be reused if verified;
- otherwise derive from canonical lower-resolution source.

### Acceptance
Same requested range returns stable candles across repeated calls.

---

## S1-T04 Chart Data API

Provide/reuse a paged/range-based chart data API. **Repository pointer to add after handoff:** existing API route/controller and data service; none exists in this package.

Input:
- canonical symbol;
- timeframe;
- start/end or window;

Output:
- time;
- O/H/L/C;
- optional volume;
- metadata including source/timezone status.

Do not return the entire multi-year dataset to the browser.

### Acceptance
Chart can request a bounded window quickly and navigate to another period.

---

## S1-T05 ARKANA UI Shell Alignment

Using existing frontend components in the actual application repository wherever possible, implement/adjust only the initial shell needed for:
- navigation consistent with target IA;
- Live Decision placeholder state clearly labeled as not yet wired to EA if CP6 is not complete;
- Research navigation placeholder;
- MT5 & Data screen;
- chart component.

Do not fake live execution state.

**Reference pointer:** preserve the information architecture in `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` (sidebar/top bar and `data` view) but do not reuse its generated prices, EA status, positions, backtest, deployment, or chart data as application state.

### Acceptance
Any placeholder is visibly labelled `Not connected / future sprint`, not filled with misleading fake execution data in normal development mode.

---

## S1-T06 Historical Chart

Implement/reuse candlestick rendering with real API data (not the seeded `draw()` prototype function in `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`) and:
- XAUUSD;
- TF switcher M1/M5/M15/H1/H4;
- zoom/pan or equivalent navigation;
- current viewed range;
- loading/error state;
- data source/timezone indicator.

Advanced trading overlays are out of scope.

### Acceptance
Owner can visually inspect real candles across all supported TFs.

---

## S1-T07 Data Health Panel

Display real registry/import output from S1-T02:
- dataset start/end;
- data source;
- row count or appropriate summary;
- missing-gap status;
- timezone status;
- tick Bid/Ask availability status;
- last import/sync state if available.

### Acceptance
The user can distinguish `READY`, `PARTIAL`, and `UNKNOWN` rather than being shown a fabricated 99.99% quality score.

---

## S1-T08 Automated Tests

In the actual repository's established test convention, add at minimum:
- symbol normalization unit tests;
- timeframe resampling tests;
- data API tests;
- boundary date/range test;
- invalid symbol/timeframe test;
- frontend component test where repo convention supports it.

Run the full lint/typecheck/test/build suite that exists in the supplied implementation repository. Sprint 00 found no suite in this handoff package; do not invent a parallel test runner here.

---

# Out of Scope

- AI Chart Analyst;
- order-block detector;
- support/resistance detector;
- Research Hypothesis engine;
- Pattern Discovery;
- Historical Similarity;
- backtest changes beyond what is needed for data reuse;
- MT5 EA execution;
- Demo Deployment;
- live account support.

---

# Owner Acceptance Test

## OAT-S1-01 Open real historical chart

1. Start ARKANA using documented local procedure.
2. Open market/data or chart screen.
3. Select XAUUSD.
4. Select M1.
5. Verify candles render from actual repository data.
6. Switch to M5, M15, H1, H4.
7. Verify chart changes and no request returns all years unnecessarily.

Expected: all supported TFs render without frontend resampling duplication.

## OAT-S1-02 Verify dataset metadata

1. Open MT5 & Data.
2. Verify actual start/end date.
3. Verify source and timezone status.
4. Verify tick availability state.

Expected: unknown/partial states are explicit.

## OAT-S1-03 Verify movement normalization

Use a test utility/API/UI field created in this sprint to represent a configured price move.

Expected: ARKANA can distinguish an explicit USD price move from broker points and does not silently assume universal "pip" semantics.

---

# Definition of Done

- [ ] Existing functionality reused where possible.
- [ ] Real XAUUSD historical candles visible.
- [ ] M1/M5/M15/H1/H4 supported.
- [ ] Dataset metadata visible.
- [ ] Point/price normalization implemented/tested.
- [ ] No fake realtime trade execution shown as real.
- [ ] Automated checks pass.
- [ ] Owner manual tests documented.

## Entry prerequisites (confirmed by Sprint 00)

- [ ] Actual ARKANA application repository is available in the workspace, including its package/build/test configuration.
- [ ] Approved XAUUSD historical source/dataset location is available, with permission to inspect/import it.
- [ ] Existing repository module pointers above have been replaced with concrete paths after inspection.
