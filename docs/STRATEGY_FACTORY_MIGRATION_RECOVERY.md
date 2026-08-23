# Strategy Factory migration and recovery — ARK-S12-02

## Scope

Migration `013_strategy_factory_foundation` evolves metadata forward only. It
adds `strategy_candidates`, `strategy_versions.strategy_candidate_id`, and
`backtest_runs.strategy_version_id`. It relaxes the legacy
`strategy_versions.backtest_run_id` requirement on PostgreSQL so a target
StrategyVersion can exist before its first BacktestRun.

It does not delete, backfill, relabel, or reinterpret legacy records. PostgreSQL
alters the nullable constraint in place. For a legacy SQLite database only, the
runner transactionally copies every `strategy_versions` row to an equivalent
replacement table before swapping names, because SQLite cannot relax `NOT NULL`
in place; this is a schema-rebuild implementation detail, not data cleanup.
The legacy `StrategyVersion.backtest_run_id` remains the original
version-to-backtest approval relationship. The new nullable
`BacktestRun.strategy_version_id` is the target lineage for a backtest created
from a pre-existing StrategyVersion.

## Execution and verification

At service startup, `Base.metadata.create_all` creates only missing tables for
an empty database, then `app.migrations.run_migrations` records successfully
applied migrations in `schema_migrations`. Existing metadata is evolved by the
version-tracked migration; it is safe to rerun after a successful application.

Before deployment, back up PostgreSQL metadata. Start the Research service,
then verify:

```sql
SELECT version, applied_at FROM schema_migrations
WHERE version = '013_strategy_factory_foundation';
```

Confirm the new table/columns exist and that legacy `strategy_versions` rows
remain readable with their original `backtest_run_id` and status.

## Recovery

If migration startup fails, stop the service and retain the database backup.
Do not drop, reset, or restore over the production database blindly. Correct
the specific schema/permission issue, then restart: the migration transaction
records its version only after completion. If recovery requires reverting an
application deployment, deploy the prior application against the retained
database; the added nullable table/columns do not remove compatibility with
legacy records. Escalate any request to remove data or reverse schema changes
for an explicit Owner decision.
