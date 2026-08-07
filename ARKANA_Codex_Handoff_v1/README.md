# ARKANA Codex Handoff v1

This package is the implementation source of truth for the next ARKANA development cycle.

## Goal

Build ARKANA as a **trading research and command center** that discovers and validates trading edges, while **MetaTrader 5 Expert Advisor (EA) owns realtime decision, risk, and execution**.

The product must be developed incrementally, with a **demo-first** deployment policy. No newly approved strategy may trade a live account automatically.

## Read Order for Codex

Codex must read these files before changing code:

1. `docs/01_PRD.md`
2. `docs/02_TECHNICAL_ARCHITECTURE.md`
3. `docs/03_DEVELOPMENT_RULES.md`
4. `docs/adr/*`
5. `docs/04_MASTER_DELIVERY_PLAN.md`
6. The active sprint file under `docs/sprints/`
7. `ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`

## Working Model

Do **not** implement the whole PRD in one pass.

Development loop:

```text
Product / Architecture
        ↓
Active Sprint Spec
        ↓
Codex inspects existing repo
        ↓
Implement only missing active-sprint scope
        ↓
Automated tests
        ↓
Owner acceptance test
        ↓
PASS / FIX
        ↓
Sprint accepted
        ↓
Plan next sprint
```

## First Instruction

Start with `docs/sprints/SPRINT_00_REPOSITORY_BASELINE.md` only.

Sprint 0 is deliberately an **inspection and baseline sprint**. Existing functionality must be reused. If the repository already satisfies an item, mark it `EXISTING/PASS`; do not rewrite it merely to match this document.

## UI Reference

`ui-reference/ARKANA_Trading_Intelligence_UI_v2.html` is a product/UX reference. Preserve the information architecture and interaction intent, but implementation may use the repository's existing component system.

## Definition of Efficient Development

Efficient means:

- no duplicate implementation;
- no speculative future-sprint work;
- no LLM calls on the realtime trading path;
- no raw historical dataset sent to an LLM;
- no browser dependency for active EA execution;
- no live-account deployment before demo validation;
- every sprint ends in something the owner can manually verify.
