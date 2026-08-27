# ARKANA — Handover to Claude Code

**Prepared:** 2026-08-27

**Repository:** `/Users/investree/Documents/project/arkana`

**Branch:** `main`; remote is `origin/main`

**Purpose:** enable a new coding agent to continue safely without relying on
chat history. This document is an operational handover, not a claim that the
product is ready to trade LIVE.

## 1. What ARKANA is

ARKANA is a local-first **Trading Intelligence and Strategy Decision Platform**
for XAUUSD. Its intended owner-facing outcome is a defensible:

```text
LONG / SHORT / NO TRADE
selected immutable strategy/version
Entry / Stop Loss / Take Profit / position size / account risk
plain-language reasons plus exact historical and current evidence
DEMO evidence before any separate LIVE decision
```

It is deliberately not an autonomous trading bot, profit promise, black-box
signal generator, or a web/API system that manages MT5 positions. Historical
research and backtests produce evidence; they do not themselves create an
order. `NO_TRADE` is an intended, correct outcome when the exact eligible
evidence chain is absent.

## 2. Product goal and non-negotiable boundaries

The long product loop is:

```text
market data → discovery/research → immutable strategy contract/version
→ canonical historical backtest → OOS/robustness → historical validation
→ deterministic router/current decision → exact DEMO contract/compiler
→ Owner-authorised DEMO MT5 acknowledgement → forward evidence
→ journal/incident/governance → evidence-only LIVE-readiness review
```

These boundaries are locked:

1. `services/research/app/backtesting.py` Backtest V1 is the sole canonical
   simulation kernel. Never add a second backtester.
2. Preserve legacy execution semantics: completed-candle inputs, next-bar
   entry, `STOP_FIRST`, costs, and chunk continuity.
3. MT5 EA owns realtime DEMO execution/position management. Web, FastAPI,
   database, and AI must never be on the `OnTick` path.
4. AI can help research drafting/explanation only. It cannot determine a
   deterministic result, change risk/configuration, close incidents, authorise
   DEMO/LIVE, or place a trade.
5. Confirmed versions and governance records are immutable. Learning creates a
   new bounded research candidate; it never silently mutates a strategy.
6. DEMO precedes any future LIVE consideration. There is **no LIVE path** in
   the current product: no credential, endpoint, config, deployment, order,
   trade, or auto-promotion authority.
7. Fixtures are isolated test evidence, never evidence from the Owner's MT5
   terminal. Missing external evidence must be reported honestly.
8. Preserve legacy records using forward migrations; do not relabel/drop old
   records to make a new lifecycle look cleaner.

Canonical background: [ARKANA_CODEX_MASTER_CONTEXT.md](ARKANA_CODEX_MASTER_CONTEXT.md).

## 3. Architecture map

| Layer | Location | Responsibility |
|---|---|---|
| Web UI + BFF | `apps/web` | Next.js owner UI; `/app/api/v1` same-origin proxies only |
| Research API | `services/research/app` | FastAPI domain logic, SQLAlchemy models, deterministic verifiers |
| Metadata | PostgreSQL via Docker Compose | migrations are applied at research startup |
| History | Parquet/DuckDB/Polars | registered/fingerprinted historical OHLC data |
| Canonical simulation | `services/research/app/backtesting.py` | only Backtest V1 kernel |
| MT5 | `mt5/Experts/ARKANA_ENGINE.mq5` | independent DEMO EA and FILE_COMMON integration |
| Runtime stack | `docker-compose.yml` | `postgres:5432`, `research:8001`, `web:3000` |

Important: `CURRENT_STATE.md` remains labelled canonical, but its header was
last updated at S21-03 and is now stale. Do not use its active-card assertion
as current truth until it is updated after the S21-05 acceptance/commit. The
Sprint 20/21 documents and Git history are more current for this handover.

## 4. Delivery status at handover

### Completed, accepted, and already pushed

Sprint 12 through Sprint 20 are accepted and pushed. Their detailed contracts
and OAT reports are in `docs/SPRINT_12_*` through `docs/SPRINT_20_*`.

The material product capabilities already implemented include:

- deterministic data/research contracts and fingerprinted historical source;
- one canonical Backtest V1 with legacy parity;
- Strategy Candidate / immutable Strategy Version / bounded multi-timeframe
  generic evaluator;
- OOS robustness, broker/capital simulation, bounded variants, lifecycle
  eligibility/promotion/retirement, and exact verifiers;
- deterministic Strategy Router/current decision (real current runtime is
  honestly `NO_TRADE`, not a tradable recommendation);
- generic DEMO contract, deterministic MT5 compiler, DEMO publication,
  acknowledgement and telemetry/forward-evidence models/UI/verifiers;
- unified journal, incident acknowledgement/recovery, controlled-learning
  proposal foundations, and immutable LIVE-readiness assessment.

The most recent accepted/pushed S21 checkpoint is:

```text
ARK-S21-04
commit 0ba378f feat(governance): add immutable live readiness assessments
```

### Implemented and fully tested, but NOT yet accepted/committed/pushed

`ARK-S21-05 — Owner Governance UI, Acceptance Verifier, and Closure` is the
current uncommitted implementation. It has source, automated test, runtime,
restart, and browser OAT artifacts. It awaits the Owner phrase:

```text
DITERIMA — ARK-S21-05
DITERIMA — SPRINT 21
```

Its technical claim is `VALIDATED`, which means checkpoint implementation and
tests are valid. It does **not** mean the system is ready for LIVE.

Detailed evidence: [SPRINT_21_05_OWNER_GOVERNANCE_AND_CLOSURE.md](SPRINT_21_05_OWNER_GOVERNANCE_AND_CLOSURE.md).

## 5. Exact S21-05 change set to preserve

Keep and review these source/test/documentation changes as one coherent
checkpoint; do not mix runtime files into its commit:

```text
apps/web/app/api/v1/governance/owner-overview/route.ts
apps/web/app/api/v1/governance/sprint21-acceptance-verifications/route.ts
apps/web/app/governance/page.tsx
apps/web/components/app-sidebar.tsx
apps/web/components/governance-console.tsx
apps/web/components/governance-console.test.tsx
services/research/app/main.py
services/research/app/migrations.py
services/research/app/models.py
services/research/app/sprint21_acceptance.py
services/research/tests/test_sprint21_acceptance.py
services/research/tests/test_strategy_factory_migrations.py
docs/SPRINT_21_05_OWNER_GOVERNANCE_AND_CLOSURE.md
```

Functional result:

- migration `051_sprint21_acceptance_verifier` adds append-only
  `sprint21_acceptance_verifications`;
- deterministic verifier version is `SPRINT_21_ACCEPTANCE_VERIFIER_V1`;
- it recomputes journal, incident, controlled-learning, readiness, generic
  chain, and publication inputs by exact ID/fingerprint and fails closed;
- Owner UI is at `/governance` and shows historical eligibility, Owner DEMO
  evidence status, readiness gates/blockers, incident acknowledgement versus
  recovery, DRAFT-only learning, journal timeline, and verifier result;
- fixture-only readiness is rendered as `FIXTURE ONLY — BUKAN READY OWNER`,
  never a real Owner-ready label;
- API routes are read-only except materialising the immutable verifier:
  `GET /api/v1/governance/owner-overview`,
  `POST /api/v1/governance/sprint21-acceptance-verifications`,
  `GET .../latest`, and `GET .../{id}/verification`.

No source evidence, entry control, configuration, deployment, MT5 action,
order, or trade is mutated by this checkpoint.

## 6. Truthful runtime state (not a fixture)

Docker runtime was rebuilt/restarted during S21-05 OAT. PostgreSQL contains
one migration-051 verifier:

| Fact | Value |
|---|---|
| verifier ID | `c1444cf3-6127-4317-b8cd-fd159ab04f64` |
| fingerprint | `482d55f602430e579a98633a60411f18b382208f9d13511e37de7d471fd8ff27` |
| verifier integrity | `PASSED` |
| Owner acceptance state | `NOT_READY_FOR_OWNER_ACCEPTANCE` |
| underlying readiness | `NOT_READY_FOR_LIVE` |
| readiness assessment fingerprint | `c71f4dc85b55321e40cd03eaf180ea9e7b86b2963f0ffd61e02f216cad6ba67e` |
| real/fixture/legacy/unknown evidence origin | `0 / 0 / 0 / 0` |
| `/api/v1/live` | HTTP `404` |

The real blocked state is expected and correct. Current concrete blockers
include no eligible current validated strategy, missing exact generic DEMO
contract/compiler/publication acknowledgement, heartbeat, forward evidence,
broker/capital freshness, recovery/control evidence, and complete
journal/verifier lineage. Do not fabricate any of these inputs to turn green.

## 7. Test evidence already run

S21-05 has been executed against the uncommitted code:

| Scope | Result |
|---|---|
| focused backend S21 verifier/readiness/migration suite | 12 passed |
| full backend regression | **339 passed** |
| web Vitest suite | **31 passed across 12 files** |
| TypeScript | passed |
| ESLint | passed |
| Next production build | passed; `/governance` generated |
| Docker research/web build | passed |
| API/BFF/restart OAT | passed; fingerprint identical after restart |
| browser OAT `/governance` | passed; blocked state visible, no console warning/error, zero controls named `live` |

Web Docker build has non-failing pre-existing Next ESLint-plugin/autoprefixer
compatibility warnings. They were not treated as S21 regressions.

## 8. Dirty-tree classification and commit rule

At handover, `git status --short` contains both the intended S21-05 work and
generated runtime state. Claude must inspect before staging and use explicit
paths—never `git add .`.

| Classification | Paths | Action |
|---|---|---|
| KEEP — S21-05 source/test/doc | listed in section 5 | review, then commit only after Owner accepts S21-05 |
| GENERATED | `apps/web/tsconfig.tsbuildinfo` | do not commit; restore/clean only with Owner approval |
| RUNTIME STATE | `services/research/arkana_metadata.db` | never commit; retain/backup decision belongs to Owner |
| RUNTIME STATE | `data/mt5-common/` | never commit; FILE_COMMON/OAT artifact, may contain external terminal payloads |

Do not delete, reset, or overwrite generated/runtime artifacts casually. The
original delivery contract requires: Owner accepts a checkpoint first, then its
commit is pushed **before starting the next checkpoint**. Therefore the
immediate correct sequence is:

1. wait for Owner acceptance of S21-05/Sprint 21;
2. stage only the explicit S21-05 files above;
3. `git diff --cached --check`, review the staged diff, commit and push;
4. only then propose/contract the next milestone.

## 9. How to reproduce verification

From repository root:

```bash
docker compose up -d --build research web
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:8001/api/v1/governance/owner-overview
curl -fsS -X POST http://localhost:8001/api/v1/governance/sprint21-acceptance-verifications
curl -fsS http://localhost:3000/api/v1/governance/owner-overview
```

Full backend regression (isolated database/data paths, source mounted
read-only):

```bash
docker compose run --rm -w /workspace/project/services/research \
  -e PYTHONPATH=/workspace/project/services/research \
  -e DATABASE_URL=sqlite:////tmp/arkana-full.db \
  -e DATA_ROOT=/tmp/arkana-data \
  -e MT5_COMMON_FILES_ROOT=/tmp/arkana-mt5 \
  -e AI_ENABLED=false -e AI_PROVIDER=unconfigured -e AI_API_KEY= \
  -v "$PWD:/workspace/project:ro" research \
  pytest -q --disable-warnings --maxfail=1
```

Web verification:

```bash
cd apps/web
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

For browser OAT, open `http://localhost:3000/governance`; confirm explicit
`LIVE AUTHORIZATION NOT IMPLEMENTED`, `NOT READY FOR LIVE`, exact blockers,
and no action capable of publishing/configuring/deploying/trading LIVE.

## 10. What remains incomplete

### Product work not yet implemented

1. **Real externally controlled DEMO evidence.** The core missing item is an
   actual eligible generic strategy, Owner-authorised DEMO publication, exact
   MT5 terminal acknowledgement, coherent heartbeat, and sufficient forward
   evidence. Current system correctly says this evidence is absent.
2. **A new milestone contract after Sprint 21.** Do not invent a LIVE sprint or
   open a LIVE pathway. The logical next planning step is an Owner-operated
   DEMO evidence campaign/operational readiness programme, but its scope,
   evidence thresholds, terminal/broker environment, and Owner decisions must
   be explicitly contracted first.
3. **Future LIVE authorisation architecture.** It is intentionally outside
   Sprint 21 and must be a separately authorised product/safety/legal design,
   not an extension of a readiness label.
4. **Dynamic Discovery enhancement** remains a later roadmap epic after the
   deterministic evidence chain is trustworthy.

### Documentation debt

- Update `docs/CURRENT_STATE.md` after S21-05 is accepted and committed. Its
  top status incorrectly stops at S21-03; preserve history but replace only
  its current-state assertions with evidence-backed Sprint 21 closure facts.
- Update `docs/ARKANA_CODEX_MASTER_CONTEXT.md` where its older text describes
  S20/21 as next/missing; it should point to the accepted Sprint 21 closure and
  current blocked real DEMO evidence state.
- Do not update either document before confirming final staged scope and
  Owner acceptance, unless the Owner explicitly asks for an interim handover
  correction.

## 11. What Claude Code should ask the Owner before new implementation

No technical guessing can supply these material decisions:

1. Has the Owner accepted S21-05 and Sprint 21? If yes, permission to commit
   the listed source changes and push `main` is needed under the established
   checkpoint contract.
2. Does the Owner want a **DEMO evidence campaign** as the next milestone, or
   a different product priority such as Dynamic Discovery? The answer changes
   scope substantially.
3. For a DEMO campaign: which broker, DEMO account, XAUUSD symbol, terminal,
   EA attachment method, and Owner availability are in scope? Never request or
   store credentials in repository/docs/chat.
4. What Owner-approved forward-evidence duration/threshold and risk review
   policy applies? Existing frozen contracts must be read before changing any
   policy.
5. May generated `tsbuildinfo`, SQLite metadata, and `data/mt5-common` be
   cleaned after a safe backup/retention decision? Default is preserve and do
   not commit.

## 12. Recommended first prompt for Claude Code

```text
You are taking over ARKANA at /Users/investree/Documents/project/arkana.
Read docs/CLAUDE_CODE_HANDOVER_2026-08-27.md completely, then read
docs/ARKANA_CODEX_MASTER_CONTEXT.md, docs/CURRENT_STATE.md, the Sprint 20/21
contracts, and git status/log before editing. Repository source is authoritative.

Do not create a second backtester, a LIVE endpoint/config/order/trade path, or
an automatic promotion/learning path. Preserve legacy records with forward
migrations. Treat fixtures as non-real evidence. Do not stage generated runtime
files. The uncommitted S21-05 checkpoint has passed its tests/OAT but awaits
Owner acceptance; do not start a new milestone until it is explicitly accepted,
committed, and pushed.

First report: exact dirty-tree classification, confirm whether S21-05 source
matches the handover, and state the minimal Owner decision required. Then wait.
```

## 13. Owner acceptance/status protocol to retain

For every checkpoint:

1. agent implements source/tests/docs and runs proportional OAT;
2. agent reports objective, artefacts, test results, truthful runtime status,
   known blockers, and a technical checkpoint claim `VALIDATED` where earned;
3. Owner sends `DITERIMA — ARK-Sxx-yy`;
4. agent commits/pushes the accepted checkpoint before next checkpoint starts;
5. only then does the Owner authorise `Lanjut ARK-Sxx-zz`.

`VALIDATED`, `DEMO_ACTIVE`, `READY_FOR_OWNER_REVIEW`, and
`READY_FOR_OWNER_LIVE_REVIEW` have different meanings. None authorises LIVE.
