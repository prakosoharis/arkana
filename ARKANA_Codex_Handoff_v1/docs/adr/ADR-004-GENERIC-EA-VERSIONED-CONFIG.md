# ADR-004: Generic EA + Versioned Strategy Configuration

**Status:** Accepted

## Decision
Prefer one generic `ARKANA_ENGINE.mq5` with versioned, schema-validated strategy configuration instead of generating a new EA source file for every strategy variation.

## Why
- reduces duplicate code;
- easier testing and rollback;
- central risk controls;
- strategy version can be audited independently of EA version;
- avoids a growing collection of nearly identical `.mq5` files.

## Exception
A strategy may require dedicated EA code only if the generic execution contract cannot support it cleanly. Such exception requires a new ADR.
