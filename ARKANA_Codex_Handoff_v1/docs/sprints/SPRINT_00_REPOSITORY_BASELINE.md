# Sprint 00 — Repository & Architecture Baseline

**Checkpoint:** CP0  
**Sprint type:** Inspection / stabilization / planning  
**Feature work:** Minimal. Do not build future functionality.

---

## Sprint Goal

Make the current ARKANA repository reproducible and map what already exists against the locked PRD/architecture so that subsequent development does not duplicate or rewrite working functionality.

---

## User-Visible Outcome

At the end of Sprint 0, the owner receives a clear report showing:
- what currently works;
- what is partially implemented;
- what is missing;
- how to run/test the repo;
- exact proposed Sprint 1 gaps.

This sprint may have little visible feature change. That is intentional.

---

# Tasks

## S0-T01 Read Source of Truth

Codex must read:
- `README.md` in this package;
- `docs/01_PRD.md`;
- `docs/02_TECHNICAL_ARCHITECTURE.md`;
- `docs/03_DEVELOPMENT_RULES.md`;
- all ADRs;
- UI reference.

### Acceptance
Codex completion report explicitly confirms these documents were read and lists any contradictions with the current repo.

---

## S0-T02 Repository Inventory

Inspect, do not guess:
- frontend framework/version;
- backend/API framework/version;
- languages;
- DB/storage;
- data pipelines;
- backtest modules;
- research modules;
- MT5/MQL files;
- Docker/dev tooling;
- tests;
- CI;
- generated/obsolete files;
- large data directories that must not be committed.

Produce/update:

`docs/CURRENT_STATE.md`

with a component map.

### Required classification
For each PRD capability mark:
- `EXISTING/PASS`
- `EXISTING/PARTIAL`
- `MISSING`
- `CONFLICTS WITH LOCKED ARCHITECTURE`

---

## S0-T03 Reproducible Local Run

Establish the shortest reliable developer startup procedure.

Document:
- prerequisites;
- env file names without secrets;
- DB/data startup;
- backend startup;
- frontend startup;
- MT5-related steps if already present;
- test commands.

Update root `README` or add `docs/LOCAL_DEVELOPMENT.md` depending repo convention.

### Acceptance
A clean shell following the documented procedure can start the required development services without undocumented manual magic.

---

## S0-T04 Baseline Automated Checks

Run all existing relevant checks:
- unit tests;
- integration tests;
- lint;
- typecheck;
- build.

Do not weaken checks merely to make them green.

Record:
- command;
- PASS/FAIL;
- failing tests/errors;
- whether failure predates Sprint 0.

### Acceptance
`docs/CURRENT_STATE.md` contains baseline check status.

---

## S0-T05 Architecture Boundary Audit

Confirm whether existing code violates locked boundaries:

- Is web currently responsible for realtime trade execution?
- Is any LLM in the realtime decision path?
- Are raw candles sent to LLM?
- Is there an MT5 EA already?
- Is strategy logic duplicated between services?
- Is demo/live environment represented?
- Is there any unsafe direct live deployment path?

### Acceptance
Each issue is documented with file references and a proposed minimal remediation. Do not implement CP6+ architecture yet.

---

## S0-T06 Data Baseline Audit

Identify actual datasets available to the repository:
- symbols;
- resolutions;
- historical ranges;
- row counts where cheap to obtain;
- storage formats;
- timezone handling;
- Bid/Ask/tick availability;
- broker metadata availability.

Do not re-import huge datasets unnecessarily.

### Acceptance
Data inventory is documented, including unknowns.

---

## S0-T07 UI Gap Map

Compare current UI with `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`.

Do not rewrite all pages.

Produce a table:
- target screen;
- existing page/component;
- reuse possible?;
- missing UX;
- proposed sprint.

### Acceptance
UI work for Sprint 1 is narrowed to what is actually missing.

---

## S0-T08 Finalize Sprint 1 Scope

Based on audit, update `docs/sprints/SPRINT_01_DATA_AND_CHART_FOUNDATION.md`:
- mark already-complete tasks `SKIP — EXISTING/PASS`;
- keep only real gaps;
- add repo-specific file/module pointers;
- do not expand into Sprint 2.

### Acceptance
Sprint 1 is implementation-ready and contains no duplicated work.

---

# Out of Scope

- building Pattern Discovery;
- building new backtest engine if one already exists;
- implementing MT5 live/demo EA execution;
- deploying to broker;
- integrating AI providers;
- redesigning the entire frontend;
- broad refactor for style preference.

---

# Definition of Done

- [ ] `docs/CURRENT_STATE.md` created/updated.
- [ ] Local run instructions verified.
- [ ] Existing automated checks executed.
- [ ] PRD capability matrix created.
- [ ] Architecture conflicts identified.
- [ ] Dataset inventory captured.
- [ ] UI gap map captured.
- [ ] Sprint 1 updated from actual repo findings.
- [ ] No future-sprint feature was implemented.

---

# Owner Acceptance Test

Owner should receive a concise summary answering:

1. Can the repo run locally now? How?
2. What major ARKANA capabilities already exist?
3. Which capabilities are partial?
4. What is the single biggest architecture conflict, if any?
5. What exact functionality will Sprint 1 add?
6. What should the owner manually test after Sprint 1?

**PASS condition:** owner understands the actual state without reading source code.
