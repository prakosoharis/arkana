# ARK-S21-03 — Controlled-Learning Proposal Ledger

**Date:** 2026-08-26

**Status:** implementation, tests, migration/restart OAT, and concrete report complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` is strictly scoped to immutable evidence-to-research proposals,
exact Owner confirmation, DRAFT-only candidate creation, verifier behavior,
tests, and OAT. It is not automatic learning, parameter optimization, strategy
validation, Router selection, DEMO/LIVE activation, or a trade recommendation.

## Outcome

Migration 049 adds:

- `controlled_learning_proposals`, an immutable ledger binding exact journal,
  incident, forward-evidence, base-strategy, policy, hypothesis, scope,
  uncertainty, exclusion, and optional AI-audit fingerprints;
- `controlled_learning_confirmations`, an immutable one-to-one Owner gate that
  can create exactly one `StrategyCandidate` with status `DRAFT`.

The protocol is `CONTROLLED_LEARNING_PROPOSAL_V1`. The accepted OAT policy
fingerprint is
`17e5f9e3ac1b626f9bb76c88d7359fe66d0aa08ad6382761d735f4f10d581e7e`.

Proposal status is derived without mutating the proposal row:

```text
LEARNING_PROPOSAL_DRAFT
  → exact Owner confirmation ledger
  → LEARNING_PROPOSAL_OWNER_CONFIRMED
  → one StrategyCandidate(status=DRAFT)
```

No StrategyVersion is created by this flow.

## Deterministic proposal policy

Five closed hypothesis templates are registered:

- signal selectivity review;
- exit behavior review;
- execution quality review;
- data quality review;
- operational resilience review.

Each template has an allowlist of contract blocks. The caller cannot submit
free-form hypothesis text, arbitrary blocks, or hidden AI output. The service
generates the persisted hypothesis text from the versioned registry.

Every validation scope must remain:

- XAUUSD, LONG research only;
- explicit supported timeframes;
- maximum 1–25 parameter variants;
- train/holdout required;
- `look_ahead = false`;
- final-OOS locked behind its separate existing Owner gate.

Every proposal also persists at least one explicit uncertainty and these exact
exclusions:

- `NO_AUTOMATIC_PARAMETER_OR_RISK_CHANGE`;
- `NO_FINAL_OOS_ACCESS`;
- `NO_LIVE_OR_DEMO_INFERENCE`;
- `NO_PRIOR_ACCEPTANCE_REUSE`.

## Evidence and conflict semantics

- journal and incident IDs are sorted before fingerprinting, making evidence
  grouping order-independent;
- exact retries reuse one proposal;
- the same immutable evidence with a divergent hypothesis, block set, scope,
  uncertainty, generator, AI trace, or base lineage conflicts;
- source journal integrity is verified at proposal creation and again before
  Owner confirmation;
- incident evidence must have a complete valid recovery chain and include its
  exact trigger journal;
- any open related strategy/publication incident blocks both materialization
  and later confirmation;
- generic forward evidence is referenced through its exact unified-journal ID
  and fingerprint; its raw payload is not copied;
- base StrategyVersion checksum must remain exact. Prior validation,
  promotion, final-OOS acceptance, backtest, or lifecycle state is never
  inherited by the DRAFT candidate.

## AI boundary

`AI_DRAFT_ASSISTED` requires an exact persisted `AIInteraction` whose status is
`AI_ASSISTED` and whose structured response exists. Disabled, unavailable,
malformed, rejected, or untraceable AI records fail closed.

The AI response does not determine hypothesis text, affected blocks, scope,
uncertainty, confirmation, candidate lifecycle, or any governance outcome. An
adversarial fixture containing `PROMOTE TO LIVE` was ignored; only its audit
fingerprint was retained.

## Owner confirmation

The exact phrase is:

```text
CONFIRM LEARNING PROPOSAL — CREATE DRAFT ONLY — <proposal_id>
```

Confirmation is atomic, idempotent, and concurrent single-winner. It creates
one candidate whose immutable controlled-learning provenance includes the
proposal/evidence fingerprints and explicit flags:

- `prior_acceptance_reused = false`;
- `final_oos_accessed = false`;
- `automatic_contract_or_risk_change = false`.

For a revision proposal, the candidate references the base StrategyVersion and
copies its contract only as editable DRAFT context. The existing
StrategyVersion remains unchanged. The generic candidate update API cannot
erase or replace the controlled-learning provenance/source.

## API and BFF

FastAPI and same-origin Next.js BFF expose:

- `GET /api/v1/controlled-learning/policy-contract`;
- `POST/GET /api/v1/controlled-learning/proposals`;
- `GET /api/v1/controlled-learning/proposals/{id}`;
- `POST /api/v1/controlled-learning/proposals/{id}/confirmations`;
- `GET /api/v1/controlled-learning/proposals/{id}/verification`.

There is no DELETE, automatic confirmation, StrategyVersion creation,
promotion, Router selection, compilation, publication, deployment, order,
trade, or LIVE endpoint.

## Automated verification

Focused accepted regression:

- **38 passed** across controlled learning, incident governance, unified
  journal, and migration recovery;
- covers policy closure, order independence, exact retry, concurrent proposal
  and confirmation single-winner, divergent conclusion conflict, missing and
  tampered evidence, open/resolved incidents, forward evidence, AI failure and
  adversarial text, unsupported blocks, unbounded search, look-ahead,
  final-OOS lock, exact phrase, DRAFT-only creation, immutable provenance,
  no prior acceptance reuse, source tamper before confirmation, API lifecycle,
  verifier, and no DELETE.

Full accepted regression:

- backend: **331 passed** under Python 3.13 with isolated SQLite, data, and MT5
  paths plus a read-only repository mount;
- web: **30 passed across 11 files**;
- TypeScript: passed;
- ESLint: passed;
- optimized local build: passed, **60 generated routes/pages**;
- Docker research/web builds: passed.

The Docker web build retains the known non-failing ESLint-plugin detection and
autoprefixer compatibility warnings. Backend deprecation warnings are
pre-existing and did not produce failures.

## Runtime OAT

Research/web images were rebuilt and restarted twice. PostgreSQL remained
healthy. Read-only API/BFF and database checks reported:

| Check | Result |
|---|---|
| research health | `ok` |
| policy protocol | `CONTROLLED_LEARNING_PROPOSAL_V1` |
| deterministic hypothesis templates | 5 |
| migration 049 | recorded exactly once after restart |
| proposals / learning confirmations | `0 / 0` |
| StrategyCandidate / StrategyVersion | unchanged at `7 / 13` |
| backtests | unchanged at `8` |
| journal / incidents | `0 / 0` |
| deployments / legacy journal / demo trades | unchanged at `5 / 6389 / 0` |
| proposal DELETE | HTTP `405` |

No proposal or candidate was fabricated from the empty journal baseline.
Startup and GET remained side-effect free.

FILE_COMMON hashes remained unchanged:

- `Arkana/strategy.ini`:
  `00b5994401545542b7a9ae14151826d11dccae6b5244efd78194151999db0e08`;
- `Arkana/telemetry.csv`:
  `a76b793a2894cbb5a61cc435d94b9e2d276e878c0f8d7e591d381b27bd6bdddd`.

## Remaining boundary

- Immutable LIVE-readiness assessment remains ARK-S21-04.
- Owner UI and complete-chain verification remain ARK-S21-05.
- No LIVE configuration, credential, endpoint, deployment, order, or trade
  authority exists.

**ARK-S21-03 is ready for Owner acceptance with technical claim `VALIDATED`.**

Acceptance phrase:

```text
DITERIMA — ARK-S21-03
Lanjut ARK-S21-04.
```
