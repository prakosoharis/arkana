# Sprint 07 — Demo Deployment End-to-End

**Status: Complete — MT5 owner acceptance required.**

## Local adapter

The local/shared-file adapter mounts `MT5_COMMON_FILES_ROOT` into the research service. It atomically writes `ARKANA/strategy.ini`; `ARKANA_ENGINE` reloads only through its timer, validates schema/demo environment/checksum, preserves its last valid config on rejection, and writes `CONFIG_LOADED` acknowledgement to `ARKANA/telemetry.csv`. The API polls that acknowledgement outside `OnTick`.

### Pre-OAT mount contract

| Layer | Required value |
|---|---|
| macOS host path | `<TERMINAL_COMMONDATA_PATH>/Files` |
| Docker Compose bind source | `${MT5_COMMON_FILES_ROOT}` from the host `.env` |
| Research container path | `/workspace/mt5-common` |
| Application `MT5_COMMON_FILES_ROOT` | `/workspace/mt5-common` (fixed container path) |

`POST /api/v1/deployments/preflight` performs a safe non-trading adapter probe: create `ARKANA/`, write a temporary probe, atomic replace, readback verification, and cleanup. It never writes `strategy.ini` during this probe.

### OAT blocker correction: contract drift

The owner-captured file with `volume=0.01` and `checksum=8626` exposed an exact drift: the API serialized `volume` minimally, while the EA checksum canonicalized it as `0.01000000`. Consequently the EA checksum payload differed. The API now emits every decimal (`volume`, `stop_distance`, `target_distance`, `max_spread_price`) through the same eight-place contract function; `max_open_positions` and `checksum` are canonical decimal integers without leading zeroes. The matching fixture has checksum `8914`. The captured stale config is retained as a regression fixture at `mt5/contracts/owner_oat_stale_strategy.ini` and is rejected specifically as `non-canonical numeric serialization: volume`. The EA also rejects unknown, duplicated, and missing fields rather than silently ignoring them. An existing generated file is deliberately not edited in place: create a fresh audited DEMO deployment to replace it atomically.

## Delivered

- Approved-only DEMO preflight and deployment; no LIVE endpoint or UI target.
- Versioned config artifact with deterministic `CHECKSUM_V1` value.
- Deployment audit history/statuses: `PREFLIGHT_FAILED`, `READY_TO_DEPLOY`, `DEPLOYING`, `AWAITING_ACK`, `DEMO_ACTIVE`, `FAILED`, `ROLLED_BACK`.
- Exact strategy/version/checksum acknowledgement matching.
- Canonical instrument and broker execution symbol are separate: strategy identity remains `XAUUSD`; owner supplies exact deployment `broker_symbol` such as `XAUUSD.m`, which is checksum-covered and must exactly match EA chart `_Symbol`.
- Canonical config v1 is defined by `services/research/app/deployment_contract.py`, with the cross-plane fixture at `mt5/contracts/deployment_config_v1.ini`. The strict ordered fields are `schema_version`, `strategy_id`, `strategy_version`, `canonical_instrument`, `broker_symbol`, `enabled`, `allowed_environment`, `rule_set`, `volume`, `stop_distance`, `target_distance`, `max_spread_price`, and `max_open_positions`, followed by `checksum`.
- Decimal risk values use exactly eight fractional digits. `CHECKSUM_V1` is the UTF-8 byte sum (mod `2147483647`) of those first thirteen values joined in that exact order with `|`; `checksum` itself is excluded. Unknown, duplicate, missing, non-canonical, or invalid-enum fields are rejected. This is intentionally strict.
- Rollback writes the previous acknowledged DEMO config and records audit state.
- Deployment UI: strategy selector, DEMO target, preflight, checksum, status, acknowledgement, history, and rollback.

## Required macOS setup / Owner Acceptance

1. Recompile the updated `ARKANA_ENGINE.mq5` in MetaEditor (zero errors), remove/reattach it, and use a **demo** `XAUUSD.m` M1 chart. Obtain `TERMINAL_COMMONDATA_PATH` from its Experts log.
2. Set `MT5_COMMON_FILES_ROOT` in the project `.env` to exactly `<TERMINAL_COMMONDATA_PATH>/Files`, then run `docker compose up --build -d`.
3. Create/approve a strategy in ARKANA. Open Demo Deployment, select it, enter a demo-account reference and exact broker symbol `XAUUSD.m`, run preflight, then deploy.
4. Confirm the API writes `<MT5_COMMON_FILES_ROOT>/ARKANA/strategy.ini`. Its `volume` must be `0.01000000` (not `0.01`) and the supplied fixture values produce checksum `8914`; do not copy or edit checksum manually.
5. Wait for EA timer, then click **Check EA acknowledgement**. Confirm `DEMO_ACTIVE`, exact version/checksum/**broker symbol**, and telemetry `CONFIG_LOADED` row. A numeric rejection now identifies its exact field, for example `non-canonical numeric serialization: volume`; other categories remain unknown, duplicate, missing, enum, symbol, or checksum.
6. Corrupt the checksum in `strategy.ini`; confirm EA logs rejection and keeps the previous valid config. Restore through a new ARKANA deployment, not manual live configuration.
7. Deploy a second approved version, acknowledge it, then use **Rollback** and confirm the previous exact valid config is restored.
8. Confirm a LIVE target is impossible in the UI/API and attaching EA to a live account is rejected.

MetaEditor/real MT5 validation is not runnable in this workspace; these steps are OWNER ACCEPTANCE REQUIRED.
