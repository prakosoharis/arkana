# ARK-S22-05 — Campaign Verifier, Owner UI, and Sprint 22 Closure

**Date:** 2026-08-27

**Status:** implementation, automated regression, Docker restart recovery, and
browser OAT complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the materialized chain verifier, the Owner view, and the
documentation closure recorded below. It is not a claim that an edge exists.
Sprint 22's verdict remains `NO_EDGE_FOUND`.

## Outcome

Sprint 22's result existed only in the database and in `curl` output. For a
product whose entire premise is that the Owner can inspect the evidence, that
was a real gap. This checkpoint closes it.

Migration 054 adds `edge_search_campaign_verifications`, an append-only
recomputation of a whole campaign chain — frozen grid, recorded trials, spent
budget, gate outcomes, and terminal verdict — bound by exact ID and fingerprint
and failing closed on any mismatch.

`/edge-search` renders that chain for the Owner. It shows the pre-registered
grid, the executed trial count, holdout survivors, the spent budget, **why**
the gate refused rather than only that it refused, the immutable verdict, and
the verifier result.

## Chain verifier

`EDGE_SEARCH_CAMPAIGN_VERIFIER_V1` composes the eight ARK-S22-01 grid checks
with six new chain checks:

| Check | What it refuses |
|---|---|
| `outcome_has_spent_opening` | a gate outcome that never consumed a budget unit |
| `outcome_trial_is_a_survivor` | final OOS reached from a non-survivor |
| `outcome_gate_evidence_exact` | a stored decision that disagrees with its `oos_validations` row |
| `no_strategy_was_promoted` | a campaign strategy that reached `VALIDATED` |
| `verdict_recomputes` | a recorded verdict that disagrees with recomputation |
| `budget_never_exceeded` | consumption beyond the frozen budget |

Each failure mode is covered by a test that tampers with the runtime and
asserts the verifier refuses: a promoted strategy, an altered verdict, and a
rewritten gate decision all produce `FAILED`.

## Owner view

The page is built so a negative result cannot be misread in either direction:

- `NO_EDGE_FOUND` renders as **"HASIL LENGKAP, BUKAN KEGAGALAN"** — a complete
  result, never a platform failure;
- a survivor is never shown without its selection disclosure, which states that
  it is one of 384 pre-registered hypotheses;
- the header carries a permanent `NO VALIDATED STRATEGY CREATED` boundary;
- the final-OOS panel states that the StrategyVersion is `CONTRACT_VALID` and
  that the generic path never promotes automatically.

### A defect found and fixed during browser OAT

The first render showed `year_pnl_concentration` and `regime_pnl_concentration`
as `FAIL` with **no number**. The gate reports those two under
`maximum_observed`, not `observed`, and the component read only `observed`.

The two figures that actually refused the strategy were therefore invisible,
which would have made the page misleading in exactly the place it matters most.
`gateObservation` now reads either field and appends the limit, and the browser
confirms `0.659408 (max 0.5)` and `0.810214 (max 0.5)`. Three unit tests cover
both field shapes and the absent case.

## Automated verification

| Scope | Result |
|---|---|
| focused chain-verifier suite | **9 passed** |
| full backend regression | **405 passed** (396 before this checkpoint) |
| web Vitest | **41 passed across 13 files** (38 before the OAT fix) |
| TypeScript | passed |
| ESLint | passed |
| Next production build | passed; `/edge-search` and all 8 edge-search routes generated |

## Runtime OAT

Docker research and web rebuilt. PostgreSQL records migration 054 exactly once.

| Fact | Value |
|---|---|
| chain verification | `PASSED`, **14 of 14 checks** |
| verification fingerprint | `2673e6521c01c1729db81410810d946e0ce3b6b15d295d46b67b7f87d6a0602d` |
| verdict | `NO_EDGE_FOUND`, fingerprint `8cf4b787…` |
| after `docker compose restart research` | identical fingerprint, identical `PASSED` |
| BFF owner-overview / chain-verification | `200` / `200` |
| browser OAT | page renders, concentration figures visible, **no console error** |
| anonymous research call | `401` |

### A boundary statement that changed

Earlier sprints asserted that `/api/v1/live` returns HTTP `404`. Since
ARK-S23-01 the authentication middleware runs ahead of routing, so an
**anonymous** call now returns `401` and an **authenticated** call returns
`404`. The route still does not exist. The assertion is recorded in its new
form rather than left to look like a regression.

## Sprint 22 closure

| Checkpoint | Commit | Result |
|---|---|---|
| ARK-S22-00 | `b64f951` | search space enumerated, anti-overfitting policy frozen |
| ARK-S22-01 | `7c501b2` | 384-trial grid pre-registered, budget ledger immutable |
| ARK-S22-02 | `9663190` | full sweep; geometry decides, rules do not |
| ARK-S22-03 | `4e91d46` | one budget unit spent, gate `FAIL`, verdict `NO_EDGE_FOUND` |
| ARK-S22-05 | this | chain verifier, Owner UI, closure |

ARK-S22-04's conditional registry extension is unlocked by the `NO_EDGE_FOUND`
verdict but **remains unauthorized**. Its honest scope is a milestone rather
than a checkpoint: `SHORT` direction, a session filter, and volatility-scaled
stops each require evaluator, compiler, EA, and golden parity work.

Canonical documentation is corrected: `CURRENT_STATE.md` and
`ARKANA_CODEX_MASTER_CONTEXT.md` now record Sprint 22's verdict and Sprint 23's
partial acceptance instead of asserting that Sprint 21 was the last milestone.

## What Sprint 22 established

It set out to find an edge and did not find one. It established two things
instead, and the second is the more durable:

1. The currently executable strategy space — six generic blocks over XAUUSD M1
   LONG at the frozen geometry range — contains nothing that survives the
   accepted gate. Apparent survivors are drift exposure in a rising market.
2. **The gate works.** Twenty-two sprints assumed it would refuse a
   plausible-looking result. The strongest survivor was profitable in all three
   splits and was refused anyway, for stated reasons, on the first genuine
   test.

## Known limitations

1. **The spread assumption remains Owner-reported at 0.25.** A terminal reading
   at 03:50 local time showed 97 points during rollover, which is expected at
   that hour but confirms the spread varies by roughly 4× across a day. A
   single constant is the wrong model; a session-aware profile is needed before
   any future campaign, and the updated exporter can now capture it.
2. **Two final-OOS budget units remain unspent.** Nothing compels spending
   them, and given rule independence a second opening would likely reproduce
   the same refusal.
3. **`NO_EDGE_FOUND` is bounded to this space.** It is not evidence that no
   edge exists.

## Owner OAT steps

```bash
docker compose up -d --build research web
open http://localhost:3000/edge-search
```

Confirm the verdict reads `TIDAK ADA EDGE DITEMUKAN — HASIL LENGKAP, BUKAN
KEGAGALAN`, that the selection disclosure names 384 pre-registered hypotheses,
that the two concentration checks show their numbers and limits, and that no
control on the page can publish, deploy, promote, or trade.

**ARK-S22-05 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S22-05
DITERIMA — SPRINT 22
```
