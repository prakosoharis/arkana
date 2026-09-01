# ARK-S24-07 — Running the Application

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the defect found by running the application, its fix across
both services, and the page-by-page survey recorded below. No registered record
was deleted, relabelled, or edited.

## Why this checkpoint exists

The Owner asked whether the application could now be exercised end to end. The
honest way to answer was to start it and look, rather than to reason from a
green test suite.

Two things were wrong, and neither was visible from the tests.

## Defect 1 — the Market & Data page reported a fixture as the data source

```text
Dataset status   READY   XAUUSD
Source           S13-03 pass fixture
Dataset registry M1   1,000 rows   2024-01-01 → 2025-12-31
```

Meanwhile the chart directly below it drew the real asset:
`2017-04-12 → 2026-08-20`.

ARK-S24-04b routed every **backend** "latest dataset" caller through one shared
selector. `/api/v1/datasets` is deliberately exempt, because the registry
listing must show the Owner every dataset including fixtures. The frontend then
did this:

```ts
const dataset = datasets.find((item) => item.symbol === "XAUUSD");
```

The listing is ordered newest-first, so `.find` took the fixture. The same
defect as ARK-S24-04b, one layer up.

### The fix keeps one rule

Re-deriving "what is a fixture" in TypeScript would create a second definition
that eventually disagrees with the Python one. Instead the **backend states its
judgement on the wire**:

```json
{ "synthetic_reason": "dataset source 'S13-03 pass fixture' declares itself a fixture",
  "future_dated": true,
  "evidence_grade": false }
```

and the client just reads it:

```ts
export function evidenceDataset(datasets: Dataset[], symbol: string) {
  const forSymbol = datasets.filter(item => item.symbol === symbol);
  return forSymbol.find(item => item.evidence_grade !== false) ?? forSymbol[0];
}
```

`evidence_grade !== false` rather than `=== true`, so a response from an older
API without the field is still usable and the page can never blank. The
registry table still lists every dataset; only the *selection* changed.

After the fix, on the running application:

```text
Source            MT5
Dataset registry  M1   2,985,994 rows
```

## Defect 2 — the web build was broken by the first fix

`variant-explorer.tsx` declares its own local `Dataset` type, so
`npm run build` failed:

```text
error TS2339: Property 'evidence_grade' does not exist on type 'Dataset'
```

`npm test` passed while `npm run build` did not, because vitest does not
type-check. Found by rebuilding the container, not by the suite.

## Page-by-page survey of the running application

| page | HTTP | note |
|---|---|---|
| Market & Data | 200 | fixed; now reports the MT5 asset |
| Command Center | 200 | renders |
| Edge Search | 200 | both campaigns, verdicts, gate checks |
| Strategies, Backtest, Discovery | 200 | render |
| Variants, Deployments, Governance | 200 | render |
| Capital, Current Decision, Demo Forward, Research | 200 | render |
| `/backtest-diagnostics` | **404** | a directory exists with no page; recorded, not fixed |

The research API exposes **177 routes**; `/health`, `/api/v1/datasets`,
`/api/v1/bars`, `/api/v1/cockpit`, `/api/v1/strategy-versions`,
`/api/v1/deployments` and `/api/v1/operational-health` were each exercised
against the live stack.

The Edge Search page renders the Sprint 24 campaign correctly without any UI
change: all nine axes on trial 480, both verdicts, the chain verifier, and —
importantly — the two concentration numbers as `0.703363 (max 0.5)` rather than
blank, which is `gateObservation` reading `maximum_observed` as ARK-S24-05
described.

## Automated verification

| Scope | Result |
|---|---|
| dataset selection suite | **21 passed** (19 before) |
| web `market.ts` suite | **49 passed** (44 before) |
| full backend regression | **698 passed** (696 before this checkpoint) |
| `npx tsc --noEmit` | clean |
| `docker compose build web` | succeeds |

## Known limitations

1. **`/backtest-diagnostics` returns 404.** `apps/web/app/backtest-diagnostics/`
   exists without a `page.tsx`. Recorded rather than fixed; adding a page is a
   feature decision, not a repair.
2. **`operational-health` reports `CRITICAL`.** Driven by the three
   `DEMO_ACTIVE` deployments with no telemetry, which is the Owner's pending
   decision, and it is reporting truthfully.
3. **The MT5 connection is `MT5_UNAVAILABLE`** with a sync request pending
   since 2026-08-20. The terminal is not running the collector; the last good
   historical dataset stays active, which is the designed behaviour.
4. **Rendering is not exercising.** Every page returns 200 and draws its data;
   this checkpoint did not drive each workflow to completion.
5. **The polluted rows are still registered** and still listed, by design.

## Owner OAT steps

```bash
docker compose up -d
```

Then open `http://127.0.0.1:3000` and confirm Market & Data reports
`Source: MT5` with 2,985,994 M1 rows, and that Edge Search shows two campaigns
both reading `TIDAK ADA EDGE DITEMUKAN`.

**ARK-S24-07 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-07
```
