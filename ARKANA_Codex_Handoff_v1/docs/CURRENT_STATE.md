# ARKANA Current State

**Audit date:** 2026-08-08  
**Sprint:** 00 — Repository & Architecture Baseline  
**Repository state:** This workspace is an ARKANA *handoff package*, not an implementation repository. The audit found no application source code, project manifest, Git metadata, data files, or runnable ARKANA service.

## Audit scope and evidence

Read in full before this document was written:

- `CODEX_BOOTSTRAP_PROMPT.md`, `README.md`, and `MANIFEST.txt`;
- `docs/01_PRD.md`, `docs/02_TECHNICAL_ARCHITECTURE.md`, `docs/03_DEVELOPMENT_RULES.md`, and `docs/04_MASTER_DELIVERY_PLAN.md`;
- all five accepted ADRs in `docs/adr/`;
- `docs/sprints/SPRINT_00_REPOSITORY_BASELINE.md` and the pre-audit Sprint 01 plan;
- `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`.

The filesystem inventory contains only these documentation/reference assets plus Finder metadata (`.DS_Store`). There is no `.git` directory in this workspace or its parent path.

## Component inventory

| Area | Actual finding | Status |
|---|---|---|
| Frontend | No frontend application, package manifest, or component source. `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` is a standalone static prototype with inline CSS/JS and generated canvas candles. | Existing reference only |
| Backend/API | No source, API contract implementation, server configuration, or environment file. | Missing |
| Languages/frameworks | No repository implementation language/framework can be identified. The reference uses plain HTML/CSS/JavaScript only. | Unknown / not selected |
| Database/storage | No DB schema, migrations, ORM, database file, or object/columnar storage. | Missing |
| Historical-data pipeline | No importer, registry, resampler, quality check, broker metadata, or data directory. | Missing |
| Research/backtest | No research, feature, similarity, or backtest module. | Missing |
| MT5/MQL | No `.mq5`, `.mql5`, compiled EA, adapter, or configuration artifact. | Missing |
| Docker/dev tooling | No Dockerfile, Compose file, task runner, lockfile, or dependency manifest. | Missing |
| Tests | No unit, integration, component, or end-to-end test files/configuration. | Missing |
| CI | No GitHub/GitLab/other CI configuration. | Missing |
| Generated/obsolete artifacts | `.DS_Store` at package root and workspace parent are OS metadata; `MANIFEST.txt` is a valid package inventory. No large/generated market-data artifact exists. | Cleanup candidate, non-blocking |

## Capability matrix against the locked PRD

Classifications describe executable capabilities, not claims depicted in the design prototype.

| PRD capability | Status | Evidence / gap |
|---|---|---|
| FR-01 Live Decision Cockpit | EXISTING/PARTIAL | UI reference sketches cockpit fields in `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`; values are dummy and no EA/telemetry/UI application exists. |
| FR-02 Interactive Chart Analyst | EXISTING/PARTIAL | Reference has prompt/quick-action interaction only; it returns fixed display content and generated synthetic candles. No deterministic analytics, LLM gateway, overlays, or `Research This` persistence. |
| FR-03 Research Idea | EXISTING/PARTIAL | Reference depicts a draft hypothesis form only. No parsing, schema, deterministic definition storage, or edit/run workflow. |
| FR-04 Event-to-Pattern Research | MISSING | No event definition, point normalization, scanner, statistics, or sample review data. |
| FR-05 Pattern Discovery | MISSING | No feature store, candidate mining, validation, or computed metrics. |
| FR-06 Historical Similarity | MISSING | No state vector, index, dataset, or outcome retrieval. |
| FR-07 Visual Validation | EXISTING/PARTIAL | Prototype depicts sample navigation/overlays, but no historical samples or detector results exist. |
| FR-08 Backtest Lab | EXISTING/PARTIAL | Prototype depicts metrics/gates with dummy values only; no deterministic engine, ledger, cost model, or validation. |
| FR-09 Strategy Library | EXISTING/PARTIAL | Prototype depicts lifecycle records only; no versioned strategy data/configuration/audit store. |
| FR-10 MT5 EA Execution Engine | MISSING | No EA or execution-plane source exists. |
| FR-11 Demo Deployment | EXISTING/PARTIAL | Prototype presents demo-only intent, but no account verification, artifact, sync, acknowledgement, or enforced lock exists. |
| FR-12 Trade Journal | EXISTING/PARTIAL | Prototype table contains dummy entries only; no telemetry ingestion or journal storage. |
| FR-13 MT5 & Data | EXISTING/PARTIAL | Prototype presents intended status fields only; no dataset, metadata, quality check, or MT5 connection. |
| FR-14 AI Gateway | MISSING | No parser/router/provider integration/cache exists. |
| NFR-01 to NFR-08 | MISSING | No implementation or tests exist to demonstrate determinism, auditability, execution independence, data integrity, safety, or testability. |

**EXISTING/PASS:** none. No PRD capability is executable in this workspace.  
**CONFLICTS WITH LOCKED ARCHITECTURE:** none found in executable code, because no executable ARKANA code exists.

## Architecture-boundary audit

| Locked boundary | Finding | Classification / minimal remediation |
|---|---|---|
| MT5 EA owns realtime decision, risk, and execution | No application or EA exists. The reference correctly states the intended separation, but cannot enforce it. | Missing — implement only in CP6, using an independent `ARKANA_ENGINE.mq5` execution plane. |
| Web/API outside the per-tick path | No web/API exists. | No executable conflict; must be enforced when API is introduced. |
| No LLM on realtime trading path | No LLM integration exists. | No executable conflict; preserve ADR-003 when CP2/CP10 are implemented. |
| Raw historical data never sent to LLM | No data or LLM integration exists. | No executable conflict; preserve compact-summary contract. |
| DEMO first; no automatic LIVE promotion | No deployment code exists. Reference visually labels DEMO/LIVE lock but does not enforce it. | Missing — enforce server- and EA-side in CP6/CP7; do not treat the mock UI as a safeguard. |
| Generic EA plus versioned config | No EA or config schema exists. | Missing — CP5/CP6 work. |

### Architecture conflict requiring care

There is no actual architecture violation to remediate in this package. However, the reference HTML uses convincing dummy statuses (for example `MT5 EA Connected`, price, position, and deployment values). Its footer explicitly identifies all values as dummy. If this file were exposed as the application unchanged, those values would conflict with the development rule prohibiting misleading fake realtime state. Sprint 01 must either wire truthful data or label every unavailable value `Not connected / future sprint`; it must not promote this prototype as a functioning cockpit.

## Dataset and historical-data inventory

| Field | Actual availability |
|---|---|
| Dataset files | None: no CSV, Parquet, database, tick, OHLC, archive, or data directory found. |
| Symbols | None. `XAUUSD` appears only in requirements/reference text, not as data. |
| Resolutions/ranges/row counts | Unknown; no dataset exists to measure. |
| Timezone | Unknown; no import metadata or source files. |
| Bid/Ask/tick history | Unknown/unavailable. |
| Broker symbol metadata / point size | Unknown/unavailable. |
| Storage format | None selected. |

No import was run and no dataset was downloaded, in accordance with Sprint 00 scope.

## UI gap map

The only UI artifact is the static prototype itself; there is no existing application page/component to reuse.

| Target screen / concern | Existing page/component | Reuse possible? | Actual gap | Proposed sprint |
|---|---|---|---|---|
| App shell and navigation | Reference `<aside>`, top bar, and views `live`, `positions`, `research`, `backtest`, `strategies`, `deployment`, `journal`, `data`, `settings` | Intent/style only | Build a real shell in the selected existing application repo; retain IA but avoid copying dummy state. | S1 (minimal shell) |
| Historical chart | Reference `liveChart`/`researchChart` canvas | Visual behavior only | It uses seeded synthetic candles; needs bounded real-data API, state, timeframe switch, loading/error, range navigation, and provenance. | S1 |
| MT5 & Data health | Reference `data` view | Intent only | Needs actual dataset registry/quality metadata; no MT5 health is in S1 scope. | S1 |
| Live decision / positions | Reference `live` and `positions` views | No functional reuse | Must remain explicitly disconnected until CP6/CP8. | CP6/CP8 |
| Research / backtest / strategy / deployment / journal | Reference views | Information-architecture reference only | All need actual domain data and workflows after CP1. | CP2–CP8 |

## Local development / startup procedure

There is no ARKANA application to start in this handoff package. Thus a clean shell **cannot start frontend, backend, database, MT5 adapter, or test suite** from this workspace.

### Inspect the package

```bash
cd /Users/investree/Documents/project/trade/ARKANA_Codex_Handoff_v1
find . -type f | sort
```

### View the non-functional UI reference only

Prerequisite: Python 3 (available during audit: Python 3.14.5).

```bash
cd /Users/investree/Documents/project/trade/ARKANA_Codex_Handoff_v1
python3 -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`. This serves a design prototype only; it does not start ARKANA or connect to MT5/data. Stop it with `Ctrl-C`.

No `.env`/`.env.example`, database startup, backend command, frontend command, or MT5 step is present. Do not invent secrets or configuration.

## Automated-check baseline

| Category | Command / discovery | Result | Notes |
|---|---|---|---|
| Unit tests | No test configuration or test files found. | NOT AVAILABLE | Not a failure hidden by this audit. |
| Integration tests | No test configuration or test files found. | NOT AVAILABLE | Same. |
| Lint | No dependency manifest or lint configuration found. | NOT AVAILABLE | Same. |
| Typecheck | No typed source or typecheck configuration found. | NOT AVAILABLE | Same. |
| Application build | No build manifest/configuration found. | NOT AVAILABLE | Same. |
| Reference inline JS syntax | `node -e` compiled the sole inline script with `new Function(...)`. | PASS | Node v26.3.1; this is a narrow reference sanity check, not an app test. |
| Reference HTML parse | Python `html.parser` parsed the file. | PASS | Narrow structural sanity check. |
| Reference tidy check | `tidy -qe ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` | FAIL (warnings only) | Exit 1 due to four “trimming empty `<span>`” warnings at lines 22, 25, 30, and 35. This is not a configured repository quality gate and was not modified. |

## Sprint 00 conclusion

Sprint 00 added only baseline documentation and updated the next-sprint plan. It did not implement data, UI, research, backtest, MT5, AI, deployment, or live-trading functionality.

The missing implementation repository/source and the missing XAUUSD dataset are material prerequisites for executing Sprint 01. If this handoff package was expected to sit inside an existing codebase, provide that codebase (and the approved data source/location) before starting Sprint 01.
