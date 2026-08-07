# Codex Bootstrap Prompt — Start ARKANA Development

Use the following as the **first instruction** to Codex after placing this package in the repository.

---

You are implementing ARKANA incrementally in this existing repository.

First, read these files completely before changing code:

- `README.md` from the ARKANA handoff package
- `docs/01_PRD.md`
- `docs/02_TECHNICAL_ARCHITECTURE.md`
- `docs/03_DEVELOPMENT_RULES.md`
- every file under `docs/adr/`
- `docs/04_MASTER_DELIVERY_PLAN.md`
- `docs/sprints/SPRINT_00_REPOSITORY_BASELINE.md`
- `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`

Then execute **Sprint 00 only**.

Critical instructions:

1. This is an existing repository, not assumed greenfield.
2. Inspect before implementing.
3. Do not rebuild features that already exist. Mark them `EXISTING/PASS`.
4. Do not implement Sprint 1 or future sprint scope during Sprint 0.
5. Do not perform a broad refactor merely to match the documents.
6. Preserve the locked architecture: MT5 EA owns realtime execution; no LLM in the live trading path; demo-first deployment.
7. Create/update `docs/CURRENT_STATE.md` with the repository inventory, PRD capability matrix, architecture conflicts, test/build baseline, dataset inventory, and UI gap map.
8. Verify and document the actual local startup procedure.
9. Run the repository's existing tests/lint/typecheck/build. Do not hide failures.
10. At the end, update `docs/sprints/SPRINT_01_DATA_AND_CHART_FOUNDATION.md` using actual repo findings. Remove/skip tasks already satisfied and add concrete module/file references where useful.

Do not start Sprint 1.

When Sprint 0 is complete, return a concise completion report with:

- repository architecture discovered;
- what is already implemented;
- what is partial/missing;
- architecture conflicts;
- tests/build commands and results;
- data inventory summary;
- files changed;
- finalized Sprint 1 scope;
- exact owner verification steps.
