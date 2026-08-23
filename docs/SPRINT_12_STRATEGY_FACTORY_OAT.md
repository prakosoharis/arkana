# Sprint 12 Strategy Factory — Verification and Owner Acceptance

**Checkpoint:** ARK-S12-09
**Scope:** the narrow XAUUSD / M1 / LONG `BULLISH_REVERSAL_M1` compatibility
slice only.
**Not a validation or deployment gate:** passing this runbook does **not** make
a strategy `VALIDATED`, profitable, DEMO-ready, LIVE-ready, or a trade
recommendation.

## Automated acceptance evidence

Run these commands from the repository root. They use an isolated SQLite
database and processed-data location; they must never run against the runtime
metadata database.

```bash
# Set this to a Python 3.13 environment with services/research requirements.
PYTHON_BIN=/path/to/python3.13-venv/bin/python

DATABASE_URL=sqlite:////tmp/arkana-s12-09.db \
DATA_ROOT=/tmp/arkana-s12-09-data \
PYTHONPATH=services/research \
"$PYTHON_BIN" -m pytest \
  services/research/tests/test_strategy_factory_acceptance.py -q

DATABASE_URL=sqlite:////tmp/arkana-s12-09-all.db \
DATA_ROOT=/tmp/arkana-s12-09-all-data \
PYTHONPATH=services/research \
"$PYTHON_BIN" -m pytest services/research/tests -q

cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
```

The acceptance regression proves:

| Check | Expected proof |
|---|---|
| Invalid contract | Validation report returns `ready: false`. |
| Draft provenance | Candidate starts at `DRAFT`. |
| Contract confirmation | Immutable StrategyVersion is `CONTRACT_VALID`, with no original backtest required. |
| Canonical execution | Backtest evidence contains the StrategyVersion id, adapter version, `NEXT_BAR_OPEN`, `M1_BROAD`, and `STOP_FIRST`. |
| Reproducibility | An identical request returns the recorded run with `reused: true`. |
| Immutability | Revision creates a new `DRAFT`; the original remains `CONTRACT_VALID`. |
| Promotion guard | The legacy manual-approval endpoint rejects a contract version. |

## Owner Acceptance Test

1. Start the FastAPI service on port 8000 and the web application with
   `RESEARCH_API_URL` pointing to that service. Open `/strategies`.
2. Create a draft candidate. Confirm that name, source, and provenance are
   visible in the selected draft.
3. Use the default compatibility terms and choose **Validate contract**. The UI
   must show `CONTRACT VALID`; changing any numeric term must clear that state
   until it is validated again.
4. Choose **Confirm immutable version**. A `CONTRACT_VALID · NOT VALIDATED`
   entry must appear in Version registry.
5. Choose **Run canonical backtest**. Verify that the evidence panel shows the
   run/fingerprint, trade metrics, `NEXT_BAR_OPEN`, `STOP_FIRST`, and lineage
   details. Re-run the same version and verify the reuse message.
6. Choose **Create revision draft**. The registry's original contract version
   must remain unchanged; the new candidate must be `DRAFT`.
7. Confirm these actions are absent: mark `VALIDATED`, automatic approval,
   deployment, MT5 configuration, BUY/SELL, or LIVE action.
8. Optionally inspect the legacy `CANDIDATE → APPROVED` record. It remains
   visibly separate from the contract workflow and still does not deploy.

## Acceptance decision

Accept ARK-S12-09 only if every automated check passes and the Owner OAT shows
the stated boundaries. Record acceptance as:

```text
DITERIMA — ARK-S12-09
```

The Sprint 12 compatibility thin slice then ends. The next product work is
not an automatic promotion: it requires a separately authorized milestone for
frozen train/holdout/final-OOS and robustness acceptance before any `VALIDATED`
claim can exist.
