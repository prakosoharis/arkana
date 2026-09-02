from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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


class GenericRobustnessEvidence(Base):
    """Bounded local stability evidence; it has no lifecycle authority."""
    __tablename__ = "generic_robustness_evidence"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_robustness_evidence_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    baseline_oos_validation_id: Mapped[str] = mapped_column(ForeignKey("oos_validations.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericEvidenceDecision(Base):
    """Combined generic historical outcome; never a lifecycle transition."""
    __tablename__ = "generic_evidence_decisions"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_evidence_decision_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    oos_validation_id: Mapped[str] = mapped_column(ForeignKey("oos_validations.id"), nullable=False, index=True)
    robustness_evidence_id: Mapped[str] = mapped_column(ForeignKey("generic_robustness_evidence.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericEvidenceOwnerConfirmation(Base):
    """Owner acknowledgement only; future promotion remains a separate scope."""
    __tablename__ = "generic_evidence_owner_confirmations"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_generic_evidence_owner_confirmation_decision"),
        UniqueConstraint("fingerprint", name="uq_generic_evidence_owner_confirmation_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    decision_id: Mapped[str] = mapped_column(ForeignKey("generic_evidence_decisions.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgement: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericEvidenceVerification(Base):
    """Materialized read-only verification of the complete generic evidence chain."""
    __tablename__ = "generic_evidence_verifications"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_generic_evidence_verification_decision"),
        UniqueConstraint("fingerprint", name="uq_generic_evidence_verification_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    decision_id: Mapped[str] = mapped_column(ForeignKey("generic_evidence_decisions.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericValidationEligibility(Base):
    """Immutable read-only eligibility snapshot; it cannot promote a strategy."""
    __tablename__ = "generic_validation_eligibilities"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_validation_eligibility_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("generic_evidence_decisions.id"), nullable=False, index=True)
    owner_confirmation_id: Mapped[str | None] = mapped_column(ForeignKey("generic_evidence_owner_confirmations.id"), nullable=True, index=True)
    evidence_verification_id: Mapped[str | None] = mapped_column(ForeignKey("generic_evidence_verifications.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericValidationPromotion(Base):
    """Explicit Owner-authorized historical validation transition."""
    __tablename__ = "generic_validation_promotions"
    __table_args__ = (
        UniqueConstraint("eligibility_id", name="uq_generic_validation_promotion_eligibility"),
        UniqueConstraint("fingerprint", name="uq_generic_validation_promotion_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    eligibility_id: Mapped[str] = mapped_column(ForeignKey("generic_validation_eligibilities.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("generic_evidence_decisions.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization: Mapped[str] = mapped_column("authorization_phrase", String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericValidationRetirement(Base):
    """Explicit, reasoned, irreversible retirement of one validated version."""
    __tablename__ = "generic_validation_retirements"
    __table_args__ = (
        UniqueConstraint("strategy_version_id", name="uq_generic_validation_retirement_strategy"),
        UniqueConstraint("promotion_id", name="uq_generic_validation_retirement_promotion"),
        UniqueConstraint("fingerprint", name="uq_generic_validation_retirement_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    promotion_id: Mapped[str] = mapped_column(ForeignKey("generic_validation_promotions.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization: Mapped[str] = mapped_column("authorization_phrase", String(96), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericValidationLifecycleVerification(Base):
    """Materialized read-only verification of one generic lifecycle snapshot."""
    __tablename__ = "generic_validation_lifecycle_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_validation_lifecycle_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    eligibility_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_eligibilities.id"), nullable=True, index=True)
    promotion_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_promotions.id"), nullable=True, index=True)
    retirement_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_retirements.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRouterPolicy(Base):
    """Immutable, versioned Router eligibility policy; it carries no decision authority."""
    __tablename__ = "strategy_router_policies"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_router_policy_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRouterEligibility(Base):
    """Read-only eligibility snapshot; it never creates a Router decision or execution action."""
    __tablename__ = "strategy_router_eligibilities"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_router_eligibility_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    router_policy_id: Mapped[str] = mapped_column(ForeignKey("strategy_router_policies.id"), nullable=False, index=True)
    lifecycle_verification_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_lifecycle_verifications.id"), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRouterDecision(Base):
    """Deterministic current-direction evidence; never an order or execution instruction."""
    __tablename__ = "strategy_router_decisions"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_router_decision_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    router_policy_id: Mapped[str] = mapped_column(ForeignKey("strategy_router_policies.id"), nullable=False, index=True)
    selected_strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    selected_eligibility_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_router_eligibilities.id"), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRouterDecisionParameters(Base):
    """Entry/SL/TP/size calculation evidence; never an executable order."""
    __tablename__ = "strategy_router_decision_parameters"
    __table_args__ = (
        UniqueConstraint("router_decision_id", name="uq_strategy_router_parameters_decision"),
        UniqueConstraint("fingerprint", name="uq_strategy_router_parameters_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    router_decision_id: Mapped[str] = mapped_column(ForeignKey("strategy_router_decisions.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    broker_metadata_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("broker_metadata_snapshots.id"), nullable=True, index=True)
    capital_contract_id: Mapped[str | None] = mapped_column(ForeignKey("capital_broker_contracts.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRouterVerification(Base):
    """Materialized read-only verifier of a complete Router decision chain."""
    __tablename__ = "strategy_router_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_router_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    router_decision_id: Mapped[str] = mapped_column(ForeignKey("strategy_router_decisions.id"), nullable=False, index=True)
    decision_parameters_id: Mapped[str] = mapped_column(ForeignKey("strategy_router_decision_parameters.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericDemoContract(Base):
    """Immutable pre-compilation contract; it has no publication authority."""
    __tablename__ = "generic_demo_contracts"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_demo_contract_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    lifecycle_verification_id: Mapped[str] = mapped_column(ForeignKey("generic_validation_lifecycle_verifications.id"), nullable=False, index=True)
    capability_assessment_id: Mapped[str] = mapped_column(ForeignKey("strategy_contract_assessments.id"), nullable=False, index=True)
    broker_metadata_snapshot_id: Mapped[str] = mapped_column(ForeignKey("broker_metadata_snapshots.id"), nullable=False, index=True)
    capital_contract_id: Mapped[str] = mapped_column(ForeignKey("capital_broker_contracts.id"), nullable=False, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericMt5Compilation(Base):
    """Immutable compiler output; storage grants no publication authority."""
    __tablename__ = "generic_mt5_compilations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_mt5_compilation_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    generic_demo_contract_id: Mapped[str] = mapped_column(ForeignKey("generic_demo_contracts.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    compiler_protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_capability_id: Mapped[str] = mapped_column(String(96), nullable=False)
    adapter_registry_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    config_text: Mapped[str] = mapped_column(Text, nullable=False)
    field_lineage: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericMt5Publication(Base):
    """Owner-authorized DEMO publication; acknowledgement remains MT5-owned."""
    __tablename__ = "generic_mt5_publications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_mt5_publication_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    compilation_id: Mapped[str] = mapped_column(ForeignKey("generic_mt5_compilations.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    target_account_login: Mapped[str] = mapped_column(String(32), nullable=False)
    target_account_server: Mapped[str] = mapped_column(String(128), nullable=False)
    target_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(16), nullable=False)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    publication_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    acknowledgement: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericMt5TelemetryEvent(Base):
    """Immutable checksum-bound MT5 event; duplicate sequence payloads conflict."""
    __tablename__ = "generic_mt5_telemetry_events"
    __table_args__ = (
        UniqueConstraint("publication_id", "event_sequence", name="uq_generic_mt5_telemetry_publication_sequence"),
        UniqueConstraint("fingerprint", name="uq_generic_mt5_telemetry_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    publication_id: Mapped[str] = mapped_column(ForeignKey("generic_mt5_publications.id"), nullable=False, index=True)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    event_timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    event_code: Mapped[str] = mapped_column(String(96), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    broker_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericForwardEvidence(Base):
    """Frozen generic DEMO evidence snapshot, never historical or LIVE evidence."""
    __tablename__ = "generic_forward_evidence"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_forward_evidence_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    publication_id: Mapped[str] = mapped_column(ForeignKey("generic_mt5_publications.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    event_fingerprints: Mapped[list] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    window_started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    window_ended_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GenericDemoChainVerification(Base):
    """Immutable complete-chain generic DEMO verifier snapshot."""
    __tablename__ = "generic_demo_chain_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_generic_demo_chain_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    publication_id: Mapped[str] = mapped_column(ForeignKey("generic_mt5_publications.id"), nullable=False, index=True)
    forward_evidence_id: Mapped[str] = mapped_column(ForeignKey("generic_forward_evidence.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GovernanceJournalItem(Base):
    """Append-only reference to exact source evidence; never a blended ledger."""
    __tablename__ = "governance_journal_items"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_governance_journal_fingerprint"),
        UniqueConstraint("source_type", "source_id", name="uq_governance_journal_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_table: Mapped[str] = mapped_column(String(96), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_origin: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    evidence_scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    strategy_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    account_reference_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_time: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_time: Mapped[str] = mapped_column(String(64), nullable=False)
    time_semantics: Mapped[str] = mapped_column(String(48), nullable=False)
    integrity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    lineage: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GovernanceIncident(Base):
    """Immutable deterministic safety observation; status is derived from its chain."""
    __tablename__ = "governance_incidents"
    __table_args__ = (
        UniqueConstraint("incident_key", name="uq_governance_incident_key"),
        UniqueConstraint("fingerprint", name="uq_governance_incident_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trigger_journal_item_id: Mapped[str] = mapped_column(ForeignKey("governance_journal_items.id"), nullable=False, index=True)
    trigger_journal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(96), nullable=False)
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    entry_block_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entry_block_state: Mapped[str] = mapped_column(String(32), nullable=False)
    readiness_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    signal: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GovernanceIncidentAcknowledgement(Base):
    """Owner review receipt; deliberately incapable of resolving an incident."""
    __tablename__ = "governance_incident_acknowledgements"
    __table_args__ = (
        UniqueConstraint("incident_id", name="uq_governance_incident_ack_incident"),
        UniqueConstraint("fingerprint", name="uq_governance_incident_ack_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("governance_incidents.id"), nullable=False, index=True)
    incident_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgement_phrase: Mapped[str] = mapped_column(String(192), nullable=False)
    phrase_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GovernanceIncidentResolution(Base):
    """Immutable evidence-bound recovery; it never removes an entry block."""
    __tablename__ = "governance_incident_resolutions"
    __table_args__ = (
        UniqueConstraint("incident_id", name="uq_governance_incident_resolution_incident"),
        UniqueConstraint("fingerprint", name="uq_governance_incident_resolution_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("governance_incidents.id"), nullable=False, index=True)
    incident_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgement_id: Mapped[str | None] = mapped_column(ForeignKey("governance_incident_acknowledgements.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_journal_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_fingerprints: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlledLearningProposal(Base):
    """Immutable evidence-to-research proposal; never an executable strategy."""
    __tablename__ = "controlled_learning_proposals"
    __table_args__ = (
        UniqueConstraint("evidence_key", name="uq_controlled_learning_evidence_key"),
        UniqueConstraint("fingerprint", name="uq_controlled_learning_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    evidence_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    hypothesis_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    hypothesis_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_journal_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    source_journal_fingerprints: Mapped[list] = mapped_column(JSON, nullable=False)
    source_incident_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    source_incident_fingerprints: Mapped[list] = mapped_column(JSON, nullable=False)
    base_strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    base_strategy_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    affected_contract_blocks: Mapped[list] = mapped_column(JSON, nullable=False)
    bounded_validation_scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    uncertainties: Mapped[list] = mapped_column(JSON, nullable=False)
    exclusions: Mapped[list] = mapped_column(JSON, nullable=False)
    generator: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ai_interaction_id: Mapped[str | None] = mapped_column(ForeignKey("ai_interactions.id"), nullable=True)
    ai_interaction_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlledLearningConfirmation(Base):
    """Exact Owner gate that creates one DRAFT candidate and nothing more."""
    __tablename__ = "controlled_learning_confirmations"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_controlled_learning_confirmation_proposal"),
        UniqueConstraint("fingerprint", name="uq_controlled_learning_confirmation_fingerprint"),
        UniqueConstraint("strategy_candidate_id", name="uq_controlled_learning_confirmation_candidate"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("controlled_learning_proposals.id"), nullable=False, index=True)
    proposal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_phrase: Mapped[str] = mapped_column(String(192), nullable=False)
    phrase_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_candidate_id: Mapped[str] = mapped_column(ForeignKey("strategy_candidates.id"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class LiveReadinessAssessment(Base):
    """Immutable, read-only S21 readiness snapshot; it grants no LIVE authority."""
    __tablename__ = "live_readiness_assessments"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_live_readiness_assessment_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("generic_mt5_publications.id"), nullable=True, index=True)
    strategy_version_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_versions.id"), nullable=True, index=True)
    strategy_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exact_inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    gates: Mapped[list] = mapped_column(JSON, nullable=False)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_origin_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    live_authorization: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Sprint21AcceptanceVerification(Base):
    """Immutable full Sprint 21 integrity snapshot; never a readiness waiver."""
    __tablename__ = "sprint21_acceptance_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_sprint21_acceptance_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchCampaign(Base):
    """Immutable pre-registered search grid. Pre-registration is what stops a
    sweep from being reinterpreted after its results are visible."""
    __tablename__ = "edge_search_campaigns"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_edge_search_campaign_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    grid: Mapped[dict] = mapped_column(JSON, nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    spread_assumption: Mapped[str] = mapped_column(String(32), nullable=False)
    final_oos_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    split_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    calibration_disclosure: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchTrial(Base):
    """One pre-registered grid point. Recorded whether it survives or fails."""
    __tablename__ = "edge_search_trials"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contract_fingerprint", name="uq_edge_search_trial_contract"),
        UniqueConstraint("campaign_id", "trial_index", name="uq_edge_search_trial_index"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False, index=True)
    trial_index: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    split_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchFinalOosOpening(Base):
    """Append-only final-OOS budget. A mutable counter could be reset; an
    accumulating ledger cannot be."""
    __tablename__ = "edge_search_final_oos_openings"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_edge_search_opening_fingerprint"),
        UniqueConstraint("campaign_id", "sequence", name="uq_edge_search_opening_sequence"),
        UniqueConstraint("campaign_id", "trial_id", name="uq_edge_search_opening_trial"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False, index=True)
    trial_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_trials.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    authorization_phrase: Mapped[str] = mapped_column(String(128), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchFinalOosOutcome(Base):
    """The gate result of one spent final-OOS budget unit, bound to the exact
    opening, trial, StrategyVersion, and accepted OOS evidence row."""
    __tablename__ = "edge_search_final_oos_outcomes"
    __table_args__ = (
        UniqueConstraint("opening_id", name="uq_edge_search_final_oos_outcome_opening"),
        UniqueConstraint("fingerprint", name="uq_edge_search_final_oos_outcome_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    opening_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_final_oos_openings.id"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False, index=True)
    trial_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_trials.id"), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("strategy_versions.id"), nullable=False)
    oos_validation_id: Mapped[str] = mapped_column(String(36), ForeignKey("oos_validations.id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gate_decision: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchCampaignConclusion(Base):
    """Immutable terminal verdict. `NO_EDGE_FOUND` is as hard to revise as a pass."""
    __tablename__ = "edge_search_campaign_conclusions"
    __table_args__ = (
        UniqueConstraint("campaign_id", name="uq_edge_search_conclusion_campaign"),
        UniqueConstraint("fingerprint", name="uq_edge_search_conclusion_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conclusion: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchCampaignVerification(Base):
    """Immutable recomputation of a whole campaign chain: grid, trials, spent
    budget, gate outcomes, and verdict. Integrity only; never an edge claim."""
    __tablename__ = "edge_search_campaign_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_edge_search_campaign_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EdgeSearchTrialBreadth(Base):
    """ARK-S25-01 immutable regime/year spread for one pre-registered survivor,
    measured over train and holdout only. It predicts the accepted gate's
    concentration check; it never replaces it and grants no authority."""
    __tablename__ = "edge_search_trial_breadth"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_edge_search_trial_breadth_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_campaigns.id"), nullable=False, index=True)
    trial_id: Mapped[str] = mapped_column(String(36), ForeignKey("edge_search_trials.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    breadth_version: Mapped[str] = mapped_column(String(64), nullable=False)
    regime_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    within_ceiling: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyLineageClassification(Base):
    """Immutable, evidence-derived judgement of whether a StrategyVersion's
    lineage is real. A fixture must be refused by rule, not by coincidence."""
    __tablename__ = "strategy_lineage_classifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_lineage_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("strategy_versions.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    classifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    may_satisfy_generic_gate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Sprint23AcceptanceVerification(Base):
    """Immutable Sprint 23 boundary snapshot: authentication, lineage, backup
    observability, and operational health. Integrity only, never LIVE consent."""
    __tablename__ = "sprint23_acceptance_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_sprint23_acceptance_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CapitalBrokerContract(Base):
    """Immutable capital/broker assumptions; this is not a simulation result."""
    __tablename__ = "capital_broker_contracts"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_capital_broker_contract_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    broker_metadata_snapshot_id: Mapped[str] = mapped_column(ForeignKey("broker_metadata_snapshots.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    broker_assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VariantExperimentContract(Base):
    """Immutable bounded-search declaration; no variant result is stored here."""
    __tablename__ = "variant_experiment_contracts"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_variant_experiment_contract_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VariantTrainRun(Base):
    """Single-winner bounded matrix evidence over the train partition only."""
    __tablename__ = "variant_train_runs"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_variant_train_run_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_contract_id: Mapped[str] = mapped_column(ForeignKey("variant_experiment_contracts.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    baseline_oos_validation_id: Mapped[str] = mapped_column(ForeignKey("oos_validations.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VariantHoldoutRun(Base):
    """Single-winner marginal-value evidence over holdout only."""
    __tablename__ = "variant_holdout_runs"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_variant_holdout_run_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    train_run_id: Mapped[str] = mapped_column(ForeignKey("variant_train_runs.id"), nullable=False, index=True)
    experiment_contract_id: Mapped[str] = mapped_column(ForeignKey("variant_experiment_contracts.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    baseline_oos_validation_id: Mapped[str] = mapped_column(ForeignKey("oos_validations.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VariantSelectionLock(Base):
    """Immutable at-most-one selection after holdout; final-OOS is untouched."""
    __tablename__ = "variant_selection_locks"
    __table_args__ = (
        UniqueConstraint("holdout_run_id", name="uq_variant_selection_lock_holdout_run"),
        UniqueConstraint("fingerprint", name="uq_variant_selection_lock_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    holdout_run_id: Mapped[str] = mapped_column(ForeignKey("variant_holdout_runs.id"), nullable=False, index=True)
    experiment_contract_id: Mapped[str] = mapped_column(ForeignKey("variant_experiment_contracts.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selection_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    selected_variant_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VariantRevisionConfirmation(Base):
    """Owner-confirmed selected revision and its exact protocol-V3 outcome."""
    __tablename__ = "variant_revision_confirmations"
    __table_args__ = (
        UniqueConstraint("selection_lock_id", name="uq_variant_revision_confirmation_selection_lock"),
        UniqueConstraint("revision_strategy_version_id", name="uq_variant_revision_confirmation_revision"),
        UniqueConstraint("fingerprint", name="uq_variant_revision_confirmation_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    selection_lock_id: Mapped[str] = mapped_column(ForeignKey("variant_selection_locks.id"), nullable=False, index=True)
    experiment_contract_id: Mapped[str] = mapped_column(ForeignKey("variant_experiment_contracts.id"), nullable=False, index=True)
    baseline_strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    revision_strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    selected_variant_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    oos_validation_id: Mapped[str | None] = mapped_column(ForeignKey("oos_validations.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VariantExperimentVerification(Base):
    """Materialized read-only verification of one Sprint 15 experiment chain."""
    __tablename__ = "variant_experiment_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_variant_experiment_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_contract_id: Mapped[str] = mapped_column(ForeignKey("variant_experiment_contracts.id"), nullable=False, index=True)
    experiment_contract_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class FixedLotCapitalSimulation(Base):
    """Immutable realized-equity evidence produced by the sole backtest kernel."""
    __tablename__ = "fixed_lot_capital_simulations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_fixed_lot_capital_simulation_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    capital_contract_id: Mapped[str] = mapped_column(ForeignKey("capital_broker_contracts.id"), nullable=False, index=True)
    source_full_validation_id: Mapped[str] = mapped_column(ForeignKey("supplemental_historical_validations.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    equity_path: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class FixedLotEquityPoint(Base):
    """One paginable close-event point; sequence is stable within its simulation."""
    __tablename__ = "fixed_lot_equity_points"
    simulation_id: Mapped[str] = mapped_column(ForeignKey("fixed_lot_capital_simulations.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class FractionalRiskCapitalSimulation(Base):
    """Immutable fractional-risk/compounding evidence; no margin decisions."""
    __tablename__ = "fractional_risk_capital_simulations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_fractional_risk_capital_simulation_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    capital_contract_id: Mapped[str] = mapped_column(ForeignKey("capital_broker_contracts.id"), nullable=False, index=True)
    source_full_validation_id: Mapped[str] = mapped_column(ForeignKey("supplemental_historical_validations.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class FractionalRiskEquityPoint(Base):
    __tablename__ = "fractional_risk_equity_points"
    simulation_id: Mapped[str] = mapped_column(ForeignKey("fractional_risk_capital_simulations.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ConstrainedCapitalSimulation(Base):
    """Immutable broker-constrained realized-capital evidence."""
    __tablename__ = "constrained_capital_simulations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_constrained_capital_simulation_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    capital_contract_id: Mapped[str] = mapped_column(ForeignKey("capital_broker_contracts.id"), nullable=False, index=True)
    source_full_validation_id: Mapped[str] = mapped_column(ForeignKey("supplemental_historical_validations.id"), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ConstrainedCapitalPoint(Base):
    __tablename__ = "constrained_capital_points"
    simulation_id: Mapped[str] = mapped_column(ForeignKey("constrained_capital_simulations.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ConstrainedCapitalVerification(Base):
    """Persisted single-winner full replay; GET never performs heavy work."""
    __tablename__ = "constrained_capital_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_constrained_capital_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    simulation_id: Mapped[str] = mapped_column(ForeignKey("constrained_capital_simulations.id"), nullable=False, index=True)
    simulation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
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


class StrategyContractAssessment(Base):
    """Immutable S16 capability/normalization assessment before confirmation."""
    __tablename__ = "strategy_contract_assessments"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_contract_assessment_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_capability_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    normalized_contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyEvaluatorVerification(Base):
    """Materialized S16 owner acceptance verifier; never reruns Backtest V1."""
    __tablename__ = "strategy_evaluator_verifications"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_strategy_evaluator_verification_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"), nullable=False, index=True)
    backtest_run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


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
    generic_validation_promotion_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_promotions.id"), nullable=True, index=True)
    generic_validation_retirement_id: Mapped[str | None] = mapped_column(ForeignKey("generic_validation_retirements.id"), nullable=True, index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class MarketExploration(Base):
    """ARK-S26-01 a descriptive measurement of the market, cached by lineage.

    A full pass over the 3M-bar M1 asset takes tens of seconds, so the result is
    stored. It is keyed by the dataset fingerprint it read: an MT5 sync rewrites
    that fingerprint, and the stale row simply stops matching instead of being
    served as if it still described the data.
    """
    __tablename__ = "market_explorations"
    __table_args__ = (UniqueConstraint("dataset_fingerprint", "timeframe", "protocol_version",
                                       name="uq_market_exploration_lineage"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    bars_measured: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
