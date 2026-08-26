# ARK-S20-05 — Owner DEMO UI, Complete-Chain Verifier, and Recovery

**Implementation date:** 2026-08-26

**Checkpoint status:** accepted by Owner on 2026-08-26

**Technical claim:** `VALIDATED` for S20-05 source, automated tests, Docker,
restart, MetaEditor, and browser OAT only

**Sprint closure status:** `BLOCKED_EXTERNAL_EVIDENCE`

## Objective and delivered boundary

This checkpoint closes the technical loop around the generic MT5 DEMO chain
without inventing a strategy, terminal, acknowledgement, telemetry, order, or
trade. It delivers:

- an Owner dashboard at `/demo-forward` that separates
  `HISTORICAL_VALIDATION_ONLY` from real forward DEMO evidence;
- exact contract/compiler/config/publication/acknowledgement/connection/
  decision/position/evidence/verifier visibility;
- Owner-authorized publication and `BLOCK_GENERIC_DEMO_ENTRIES_V1` controls;
- migration `046_generic_demo_chain_verifier` and immutable
  `GENERIC_DEMO_COMPLETE_CHAIN_VERIFIER_V1` artifacts;
- fail-closed lifecycle reconciliation and an atomic persistent
  `BLOCK_NEW_ENTRIES` FILE_COMMON control;
- EA restart behavior that retains only the last exact valid cached config and
  rejects malformed controls safely;
- API and same-origin BFF routes for overview, block, reconcile, and verifier
  lifecycle.

The verifier checks exact current lifecycle/contract, deterministic compiler
identity, checksum-addressed publication bytes, full MT5 acknowledgement,
ordered checksum-bound telemetry, heartbeat freshness, frozen forward
evidence, entry control, DEMO-only lineage, and legacy/LIVE isolation. A PASS
means chain integrity only; it is not profitability evidence or LIVE authority.

## Safety and recovery behavior

- `DEMO ACTIVE` is rendered only for `DEMO_ACKNOWLEDGED` plus a non-empty exact
  acknowledgement. Waiting, blocked, missing, or malformed evidence cannot use
  that active state.
- Explicit Owner blocking requires the exact phrase
  `BLOCK_GENERIC_DEMO_ENTRIES_V1` and a canonical reason code.
- A retired/invalid lifecycle installs or preserves a persistent entry block;
  an existing immutable Owner block reason is never rewritten.
- Config and control writes are atomic with canonical checksum readback.
- The API never owns `OnTick`, creates an order, or exposes a LIVE action.
- Historical, Router, legacy deployment/journal, and generic forward evidence
  remain distinct.

## Automated evidence

Focused S20 regression:

```text
50 passed
```

It covers positive exact chain verification, insufficient-evidence scoped
PASS, contract/compiler/publication/ack/telemetry/evidence tampering, stale
heartbeat, manual block authorization, lifecycle retirement, cached-config and
manifest corruption, exact retry, concurrent verifier single-winner behavior,
migration recovery, API method boundaries, no-LIVE behavior, and legacy
isolation.

Full backend regression ran in an isolated SQLite database with AI explicitly
disabled:

```text
297 passed
```

Web verification:

```text
30 passed across 11 files
TypeScript: passed
ESLint: passed
Next.js optimized production build: passed
```

MetaEditor64 compiled the exact updated
`mt5/Experts/ARKANA_ENGINE.mq5` source:

```text
Result: 0 errors, 0 warnings
```

## Docker, restart, and browser OAT

Research and web production images rebuilt and restarted successfully.
Migration `046_generic_demo_chain_verifier` is present. Before and after the
restart:

```text
generic publications       0
generic telemetry events   0
generic forward evidence   0
generic chain verifiers    0
legacy journal rows        6,389
legacy deployments         5
generic evidence aggregate EMPTY
FILE_COMMON aggregate      14c1c3c3627d8833c206305625ff389457386937fc8d14eebcec0af0c892e383
```

The production overview returned HTTP 200 with
`BLOCKED_EXTERNAL_EVIDENCE`, zero publications, and explicit
`HISTORICAL_VALIDATION_ONLY`. Browser OAT loaded and refreshed
`http://localhost:3000/demo-forward`; the DOM and visual inspection confirmed:

- `LIVE LOCKED` and single-MT5-kernel ownership are prominent;
- historical eligibility and real Owner-terminal evidence are separate;
- the real state says no publication exists and the system is not active;
- the exact publication phrase is shown and the action is disabled without an
  eligible compilation/account/server/reference;
- no `DEMO ACTIVE` status is presented;
- browser console warning/error log is empty before and after refresh;
- the same-origin overview request completed and rendered without a network
  error.

## Honest real-runtime result

The real metadata contains no currently eligible generic StrategyVersion,
contract, compilation, publication, acknowledgement, generic telemetry, or
forward evidence. Therefore the technical S20-05 implementation is
`VALIDATED`, but Sprint 20 cannot honestly close as a real generic DEMO
activation. Its external status remains:

```text
BLOCKED_EXTERNAL_EVIDENCE
```

No acknowledgement, heartbeat, trade, profit, or broker evidence was
fabricated. `FORWARD_EVIDENCE_INSUFFICIENT` can only be claimed after a genuine
Owner terminal acknowledges an eligible exact publication and produces real
generic telemetry.

## Owner acceptance test

For this checkpoint's current technical boundary:

1. Open `http://localhost:3000/demo-forward`.
2. Confirm the top state is `BLOCKED EXTERNAL EVIDENCE`, not `DEMO ACTIVE`.
3. Confirm `Historical eligibility` is labeled
   `HISTORICAL_VALIDATION_ONLY` and real Owner-terminal evidence is separate.
4. Confirm `LIVE LOCKED`, exact authorization phrase, connection/decision/
   position sections, and the truthful no-publication message are visible.
5. Confirm the publication button is disabled because no exact eligible
   compilation exists.

To remove the Sprint-level external blocker later, the Owner must first produce
an actually eligible historically `VALIDATED` generic chain, then use an
Owner-controlled MT5 DEMO terminal to acknowledge the exact account/server/
symbol/config publication, emit a fresh heartbeat, test restart and entry
block, and materialize genuine forward evidence. That is external operational
evidence, not something an automated fixture may impersonate.

## Acceptance phrase

```text
DITERIMA — ARK-S20-05
```

The Owner accepted ARK-S20-05 on 2026-08-26. Source, tests, and documentation
may now be committed and pushed. Sprint-level real activation remains a
separate external-evidence boundary.
