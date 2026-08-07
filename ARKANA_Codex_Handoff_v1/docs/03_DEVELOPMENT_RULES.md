# ARKANA Development Rules

These rules apply to every Codex implementation session.

## Scope Discipline

1. Implement only the active sprint.
2. Do not implement future sprint features "while already here".
3. Inspect existing code before creating new modules.
4. If functionality already exists, reuse or minimally adapt it.
5. Do not create duplicate APIs, services, pages, tables, or feature calculators.
6. Do not perform a big-bang rewrite unless an explicit ADR authorizes it.

## Architecture

7. MT5 EA owns realtime execution.
8. Web/API is not in the per-tick critical execution path.
9. LLM is never called on every tick.
10. LLM must not directly choose a realtime trade.
11. Raw historical market datasets are never sent to the LLM.
12. Approved strategy logic must be deterministic and schema/version controlled.
13. New strategy versions deploy to DEMO first.
14. Automatic live promotion is prohibited.
15. Web outage must not prevent the EA from managing positions using its last valid approved config.

## Data

16. Historical imports must be idempotent.
17. Dataset source/range/timezone/quality must be recorded.
18. Normalize broker point/pip/price semantics explicitly.
19. Prefer Parquet/columnar files for large market history.
20. Do not store every raw tick in a transactional DB without evidence it is needed.
21. Precompute/cache expensive reusable features.
22. Backtest/research runs should have fingerprints to avoid unnecessary recomputation.

## Trading Research

23. A trading concept must have a deterministic definition before backtest.
24. Always report sample size.
25. Do not confuse `P(feature | outcome)` with `P(outcome | feature)`.
26. Separate in-sample and out-of-sample where applicable.
27. Costs/spread must be accounted for before promotion.
28. If intrabar ordering is unknown, default to a conservative policy or mark ambiguity explicitly.
29. No strategy is promoted because of win rate alone; expectancy and drawdown matter.

## Code Quality

30. Use the repository's existing language/framework conventions.
31. Do not add a new dependency without documenting why existing dependencies are insufficient.
32. Keep domain logic outside UI components.
33. Deterministic trading logic requires unit tests.
34. API/adapter boundaries require integration tests where practical.
35. Run lint/typecheck/tests/build used by the repository before declaring completion.
36. Do not hide test failures.
37. Do not silently fallback to dummy data in production paths.
38. Feature flags/mock data must be explicitly labeled.

## Database / Schema

39. Schema changes require migrations.
40. Migrations must be reversible or have a documented recovery path.
41. Do not rename/drop existing fields or tables casually.
42. Strategy/version/deployment history must remain auditable.

## UI / UX

43. Use `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` as intent reference.
44. Preserve a simple command-center UX.
45. Advanced controls should use progressive disclosure.
46. Demo/live environment must always be visually obvious.
47. Destructive/emergency actions require explicit affordance.
48. Do not expose a one-click live deployment path in initial milestones.

## Documentation

49. If an API/schema/config contract changes, update relevant docs in the same task.
50. Add an ADR before materially reversing a locked architectural decision.
51. Sprint completion must include manual owner test steps.
52. Codex completion report must list: changed files, tests run, known limitations, manual verification steps.

## Definition of Done for Any Task

A task is not done until:
- code is implemented;
- automated checks pass or failures are explicitly explained;
- no unrelated scope was added;
- documentation is updated when needed;
- manual verification is provided;
- no demo/live safety rule was bypassed.
