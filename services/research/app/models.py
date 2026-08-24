from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone_status: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    bars: Mapped[list["DatasetBarAsset"]] = relationship(cascade="all, delete-orphan")


class BrokerMetadataSnapshot(Base):
    __tablename__ = "broker_metadata_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    canonical_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    collected_at: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DatasetBarAsset(Base):
    __tablename__ = "dataset_bar_assets"
    __table_args__ = (UniqueConstraint("dataset_id", "timeframe", name="uq_dataset_timeframe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    range_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class HistoricalSyncState(Base):
    """One durable state row per canonical research instrument.

    These timestamps deliberately have different meanings: market timestamps are
    broker-time-naive values, while successful_sync_at is service clock time.
    """
    __tablename__ = "historical_sync_states"
    canonical_instrument: Mapped[str] = mapped_column(String(32), primary_key=True)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_SYNCED")
    latest_market_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_scheduled_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class HistoricalSyncJob(Base):
    __tablename__ = "historical_sync_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    canonical_instrument: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # MANUAL or SCHEDULED
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ResearchHypothesis(Base):
    __tablename__ = "research_hypotheses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_prompt: Mapped[str] = mapped_column(String(4000), nullable=False)
    parser_source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ResearchRuleDefinition(Base):
    """Owner-controlled, versioned deterministic research rules; never strategies."""
    __tablename__ = "research_rule_definitions"
    __table_args__ = (UniqueConstraint("canonical_name", "version", name="uq_research_rule_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    canonical_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    created_source: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("research_hypotheses.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    samples: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    trades: Mapped[list] = mapped_column(JSON, nullable=False)
    # Sprint 12 target lineage: a StrategyVersion may exist before its first
    # BacktestRun.  The legacy reverse link on StrategyVersion remains intact.
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class OosValidation(Base):
    """Frozen OOS review evidence; it carries no automatic promotion power."""
    __tablename__ = "oos_validations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_oos_validation_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupplementalHistoricalValidation(Base):
    """Immutable full-history evidence linked to, but never replacing, approval evidence."""
    __tablename__ = "supplemental_historical_validations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_supplemental_validation_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    original_backtest_run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    trades: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class DerivedFinancialEvidence(Base):
    __tablename__="derived_financial_evidence"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    fingerprint: Mapped[str]=mapped_column(String(64),unique=True,nullable=False,index=True)
    source_full_validation_id: Mapped[str]=mapped_column(ForeignKey("supplemental_historical_validations.id"),nullable=False,index=True)
    strategy_version_id: Mapped[str]=mapped_column(ForeignKey("strategy_versions.id"),nullable=False,index=True)
    broker_metadata_snapshot_id: Mapped[str]=mapped_column(ForeignKey("broker_metadata_snapshots.id"),nullable=False)
    volume: Mapped[float]=mapped_column(Float,nullable=False)
    currency: Mapped[str]=mapped_column(String(16),nullable=False)
    parity_status: Mapped[str]=mapped_column(String(32),nullable=False)
    metrics: Mapped[dict]=mapped_column(JSON,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,nullable=False)


class StrategyCandidate(Base):
    """Pre-backtest strategy intent with explicit source and provenance."""
    __tablename__ = "strategy_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_key", "version", name="uq_strategy_key_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_key: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    profile: Mapped[str] = mapped_column(String(32), nullable=False, default="SCALPING")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CANDIDATE")
    # This legacy post-backtest relationship remains readable for all existing
    # records.  New pre-backtest versions will leave it NULL until a BacktestRun
    # is created and linked through BacktestRun.strategy_version_id.
    backtest_run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True, index=True)
    strategy_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_candidates.id"), nullable=True, index=True)
    strategy_contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    supersedes_strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True)
    validation_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("oos_validations.id"), nullable=True, index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    target_environment: Mapped[str] = mapped_column(String(16), nullable=False)
    target_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    broker_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    config_text: Mapped[str] = mapped_column(String(8000), nullable=False)
    config_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    acknowledgement: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    previous_deployment_id: Mapped[str | None] = mapped_column(ForeignKey("deployments.id"), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class JournalEvent(Base):
    __tablename__ = "journal_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    deployment_id: Mapped[str | None] = mapped_column(ForeignKey("deployments.id"), nullable=True, index=True)
    event_timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(96), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(48), nullable=False)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    detail: Mapped[str] = mapped_column(String(1024), nullable=False)
    positions: Mapped[str] = mapped_column(String(32), nullable=False)
    emergency_stop: Mapped[str] = mapped_column(String(16), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (UniqueConstraint("request_fingerprint", name="uq_ai_interaction_request_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    route_status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DemoTrade(Base):
    __tablename__ = "demo_trades"
    __table_args__ = (UniqueConstraint("deal_ticket", name="uq_demo_trade_deal_ticket"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deployment_id: Mapped[str | None] = mapped_column(ForeignKey("deployments.id"), nullable=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    deal_ticket: Mapped[str] = mapped_column(String(32), nullable=False)
    position_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    swap: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_state: Mapped[str] = mapped_column(String(48), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
