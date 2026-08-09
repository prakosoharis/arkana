# Sprint 05 — Strategy Library & Governance

**Status: Complete — owner acceptance pending.**

## Delivered

- Create immutable `CANDIDATE` strategy versions from a recorded backtest.
- Persist source backtest, deterministic configuration, version, checksum, and rollback/supersession metadata.
- Manual owner approval moves only `CANDIDATE → APPROVED`.
- Every generated configuration is disabled and restricted to `DEMO`.

## Excluded

No strategy is automatically approved, deployed, activated, synced to MT5, or allowed to trade. Configuration sync and EA execution remain future work.

## Owner acceptance

1. Run a recorded backtest in Backtest Lab.
2. Click **Create strategy candidate** and confirm the acknowledgement.
3. Open Strategy Library; confirm candidate version, backtest link, checksum, and `DEMO only` state.
4. Click **Approve manually** and confirm the state changes to `APPROVED · NOT DEPLOYED`.
5. Confirm no deployment or live-trading action appears.
