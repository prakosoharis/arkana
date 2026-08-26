"""ARK-S21-01 immutable unified journal index.

The index stores exact references and hashes only. It never copies raw evidence,
publishes configuration, contacts MT5, changes lifecycle, or places a trade.
"""
from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    BacktestRun,
    DemoTrade,
    Deployment,
    GenericDemoChainVerification,
    GenericDemoContract,
    GenericEvidenceDecision,
    GenericEvidenceOwnerConfirmation,
    GenericEvidenceVerification,
    GenericForwardEvidence,
    GenericMt5Compilation,
    GenericMt5Publication,
    GenericMt5TelemetryEvent,
    GenericRobustnessEvidence,
    GenericValidationEligibility,
    GenericValidationLifecycleVerification,
    GenericValidationPromotion,
    GenericValidationRetirement,
    GovernanceJournalItem,
    JournalEvent,
    OosValidation,
    StrategyRouterDecision,
    StrategyRouterDecisionParameters,
    StrategyRouterEligibility,
    StrategyRouterVerification,
    StrategyVersion,
)
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GOVERNANCE_JOURNAL_INDEX_V1"
INTEGRITY_VERIFIED = "VERIFIED_AT_INDEXING"
ORIGINS = {"REAL_OWNER", "FIXTURE_OAT", "LEGACY", "UNKNOWN"}
SCOPES = {"HISTORICAL", "ROUTER", "LEGACY_DEMO", "GENERIC_DEMO_FORWARD"}

SOURCE_REGISTRY: dict[str, tuple[type, str]] = {
    "HISTORICAL_BACKTEST": (BacktestRun, "HISTORICAL"),
    "HISTORICAL_OOS": (OosValidation, "HISTORICAL"),
    "HISTORICAL_ROBUSTNESS": (GenericRobustnessEvidence, "HISTORICAL"),
    "HISTORICAL_EVIDENCE_DECISION": (GenericEvidenceDecision, "HISTORICAL"),
    "HISTORICAL_EVIDENCE_VERIFICATION": (GenericEvidenceVerification, "HISTORICAL"),
    "LIFECYCLE_ELIGIBILITY": (GenericValidationEligibility, "HISTORICAL"),
    "LIFECYCLE_OWNER_CONFIRMATION": (GenericEvidenceOwnerConfirmation, "HISTORICAL"),
    "LIFECYCLE_PROMOTION": (GenericValidationPromotion, "HISTORICAL"),
    "LIFECYCLE_RETIREMENT": (GenericValidationRetirement, "HISTORICAL"),
    "LIFECYCLE_VERIFICATION": (GenericValidationLifecycleVerification, "HISTORICAL"),
    "ROUTER_ELIGIBILITY": (StrategyRouterEligibility, "ROUTER"),
    "ROUTER_DECISION": (StrategyRouterDecision, "ROUTER"),
    "ROUTER_PARAMETERS": (StrategyRouterDecisionParameters, "ROUTER"),
    "ROUTER_VERIFICATION": (StrategyRouterVerification, "ROUTER"),
    "LEGACY_DEPLOYMENT": (Deployment, "LEGACY_DEMO"),
    "LEGACY_JOURNAL": (JournalEvent, "LEGACY_DEMO"),
    "LEGACY_TRADE": (DemoTrade, "LEGACY_DEMO"),
    "GENERIC_DEMO_CONTRACT": (GenericDemoContract, "GENERIC_DEMO_FORWARD"),
    "GENERIC_COMPILATION": (GenericMt5Compilation, "GENERIC_DEMO_FORWARD"),
    "GENERIC_PUBLICATION": (GenericMt5Publication, "GENERIC_DEMO_FORWARD"),
    "GENERIC_TELEMETRY": (GenericMt5TelemetryEvent, "GENERIC_DEMO_FORWARD"),
    "GENERIC_FORWARD_EVIDENCE": (GenericForwardEvidence, "GENERIC_DEMO_FORWARD"),
    "GENERIC_CHAIN_VERIFICATION": (GenericDemoChainVerification, "GENERIC_DEMO_FORWARD"),
}

SAFE_SCALAR_COLUMNS = {
    "id", "fingerprint", "status", "protocol_version", "verifier_version",
    "compiler_protocol_version", "adapter_capability_id", "adapter_registry_fingerprint",
    "config_checksum", "publication_checksum", "payload_checksum", "event_sequence",
    "event_timestamp", "event_type", "event_code", "strategy_version_id", "dataset_id",
    "oos_validation_id", "robustness_evidence_id", "decision_id", "eligibility_id",
    "promotion_id", "retirement_id", "owner_confirmation_id", "evidence_verification_id",
    "router_policy_id", "selected_strategy_version_id", "selected_eligibility_id",
    "evaluated_at", "router_decision_id", "decision_parameters_id",
    "generic_demo_contract_id", "compilation_id", "publication_id", "forward_evidence_id",
    "lifecycle_verification_id", "capability_assessment_id", "broker_metadata_snapshot_id",
    "capital_contract_id", "target_environment", "broker_symbol", "window_started_at",
    "window_ended_at", "deployment_id", "environment", "decision", "strategy_id",
    "strategy_version", "deal_ticket", "position_id", "side", "observed_at", "created_at",
    "published_at", "acknowledged_at", "validated_at", "retired_at", "checksum",
    "backtest_run_id", "strategy_candidate_id",
}
ACCOUNT_IDENTITY_COLUMNS = {"target_account_login", "target_account_server", "target_reference"}


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _hash(value: Any) -> str:
    return sha256(canonical_json(_normalize(value)).encode()).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds") + "Z"


def _event_clock(item: Any) -> tuple[str, str, str]:
    observed = getattr(item, "observed_at", None) or getattr(item, "created_at", None)
    if not isinstance(observed, datetime):
        raise ValueError("journal source has no valid observed or created time")
    event = getattr(item, "event_timestamp", None)
    if isinstance(event, str):
        value = event.strip()
        if not value or len(value) > 64:
            raise ValueError("journal source event time is invalid")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                event_time = _iso(parsed)
                semantics = "EXPLICIT_UTC"
            else:
                event_time = parsed.isoformat(timespec="seconds")
                semantics = "SOURCE_NAIVE_PRESERVED"
        except ValueError:
            try:
                datetime.strptime(value, "%Y.%m.%d %H:%M:%S")
            except ValueError as error:
                raise ValueError("journal source event time is invalid") from error
            event_time = value
            semantics = "BROKER_TIME_NAIVE_PRESERVED"
        return event_time, _iso(observed), semantics
    for name in ("evaluated_at", "published_at", "acknowledged_at", "created_at"):
        value = getattr(item, name, None)
        if isinstance(value, datetime):
            return _iso(value), _iso(observed), "UTC_DATABASE_TIMESTAMP"
    raise ValueError("journal source has no valid event time")


def _publication_for(session: Session, source_type: str, item: Any) -> GenericMt5Publication | None:
    if isinstance(item, GenericMt5Publication):
        return item
    if isinstance(item, GenericMt5TelemetryEvent):
        return session.get(GenericMt5Publication, item.publication_id)
    if isinstance(item, GenericForwardEvidence):
        return session.get(GenericMt5Publication, item.publication_id)
    if isinstance(item, GenericDemoChainVerification):
        publication = session.get(GenericMt5Publication, item.publication_id)
        evidence = session.get(GenericForwardEvidence, item.forward_evidence_id)
        if not publication or not evidence or evidence.publication_id != item.publication_id:
            raise ValueError("generic chain verification has conflicting publication lineage")
        return publication
    return None


def _contract_for(session: Session, item: Any, publication: GenericMt5Publication | None) -> GenericDemoContract | None:
    if isinstance(item, GenericDemoContract):
        return item
    compilation = item if isinstance(item, GenericMt5Compilation) else None
    if publication:
        compilation = session.get(GenericMt5Compilation, publication.compilation_id)
        if not compilation:
            raise ValueError("generic publication compilation lineage is missing")
        if publication.target_environment != "DEMO" or publication.config_checksum != compilation.config_checksum:
            raise ValueError("generic publication environment or config lineage conflicts")
        manifest = publication.manifest or {}
        expected_manifest = {
            "publication_id": publication.id,
            "target_environment": "DEMO",
            "broker_symbol": publication.broker_symbol,
            "config_checksum": publication.config_checksum,
        }
        if any(manifest.get(key) != value for key, value in expected_manifest.items()):
            raise ValueError("generic publication manifest lineage conflicts")
        if publication.acknowledgement:
            acknowledgement = publication.acknowledgement
            expected_ack = {
                "publication_id": publication.id,
                "environment": "DEMO",
                "account_login": publication.target_account_login,
                "account_server": publication.target_account_server,
                "broker_symbol": publication.broker_symbol,
                "config_checksum": publication.config_checksum,
                "publication_checksum": publication.publication_checksum,
                "decision": "GENERIC_CONFIG_LOADED",
            }
            if any(acknowledgement.get(key) != value for key, value in expected_ack.items()):
                raise ValueError("generic publication acknowledgement lineage conflicts")
    if compilation:
        if sha256(compilation.config_text.encode()).hexdigest() != compilation.config_checksum:
            raise ValueError("generic compilation config checksum conflicts")
        contract = session.get(GenericDemoContract, compilation.generic_demo_contract_id)
        if not contract:
            raise ValueError("generic compilation contract lineage is missing")
        return contract
    return None


def _strategy_for(session: Session, item: Any, contract: GenericDemoContract | None) -> StrategyVersion | None:
    strategy_id = getattr(item, "strategy_version_id", None)
    if isinstance(item, StrategyRouterDecision):
        strategy_id = item.selected_strategy_version_id
    elif isinstance(item, StrategyRouterDecisionParameters):
        decision = session.get(StrategyRouterDecision, item.router_decision_id)
        if not decision or item.strategy_version_id != decision.selected_strategy_version_id:
            raise ValueError("Router parameters have conflicting decision strategy lineage")
        strategy_id = item.strategy_version_id
    elif isinstance(item, StrategyRouterEligibility):
        lifecycle = session.get(GenericValidationLifecycleVerification, item.lifecycle_verification_id) if item.lifecycle_verification_id else None
        if lifecycle and lifecycle.strategy_version_id != item.strategy_version_id:
            raise ValueError("Router eligibility has conflicting lifecycle strategy lineage")
    elif isinstance(item, StrategyRouterVerification):
        decision = session.get(StrategyRouterDecision, item.router_decision_id)
        parameters = session.get(StrategyRouterDecisionParameters, item.decision_parameters_id)
        if not decision or not parameters or parameters.router_decision_id != decision.id:
            raise ValueError("Router verification has conflicting decision lineage")
        strategy_id = decision.selected_strategy_version_id
    elif isinstance(item, (JournalEvent, DemoTrade)):
        deployment = session.get(Deployment, item.deployment_id) if item.deployment_id else None
        if deployment:
            strategy_id = deployment.strategy_version_id
    elif isinstance(item, BacktestRun) and not strategy_id:
        linked = list(session.scalars(select(StrategyVersion).where(StrategyVersion.backtest_run_id == item.id)))
        if len(linked) > 1:
            raise ValueError("historical backtest has ambiguous StrategyVersion lineage")
        strategy_id = linked[0].id if linked else None
    if contract:
        if strategy_id and strategy_id != contract.strategy_version_id:
            raise ValueError("source strategy differs from generic contract lineage")
        strategy_id = contract.strategy_version_id
    if not strategy_id:
        return None
    strategy = session.get(StrategyVersion, strategy_id)
    if not strategy:
        raise ValueError("journal source StrategyVersion lineage is missing")
    if isinstance(item, GenericMt5TelemetryEvent) and item.strategy_version_id != strategy.id:
        raise ValueError("generic telemetry strategy lineage conflicts")
    return strategy


def _account_reference(publication: GenericMt5Publication | None) -> str | None:
    if not publication:
        return None
    return _hash({
        "domain": "ARKANA_ACCOUNT_REFERENCE_V1",
        "authorization_fingerprint": publication.authorization_fingerprint,
        "login": publication.target_account_login,
        "server": publication.target_account_server,
        "reference": publication.target_reference,
    })


def _origin(source_type: str, item: Any, strategy: StrategyVersion | None, publication: GenericMt5Publication | None) -> str:
    if source_type.startswith("LEGACY_"):
        return "LEGACY"
    markers: list[str] = [source_type]
    if strategy:
        markers.extend([strategy.strategy_key, strategy.name])
        markers.extend([canonical_json(_normalize(strategy.configuration)), canonical_json(_normalize(strategy.strategy_contract or {}))])
    for name in ("result", "policy", "validation", "contract", "field_lineage"):
        value = getattr(item, name, None)
        if isinstance(value, (dict, list)):
            markers.append(json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")))
    lowered = " ".join(markers).lower()
    if any(marker in lowered for marker in ("fixture", "test", "oat", "router-ready", "acceptance", "passing-lineage")):
        return "FIXTURE_OAT"
    if publication and publication.target_environment == "DEMO" and publication.acknowledgement:
        return "REAL_OWNER"
    return "UNKNOWN"


def _source_snapshot(item: Any, account_reference_hash: str | None) -> dict[str, Any]:
    scalars: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for column in item.__table__.columns:
        name = column.name
        value = getattr(item, name)
        if name in ACCOUNT_IDENTITY_COLUMNS:
            continue
        if name in SAFE_SCALAR_COLUMNS and not isinstance(value, (dict, list)):
            scalars[name] = _normalize(value)
        elif value is not None:
            hashes[name + "_sha256"] = _hash(value)
    return {
        "source_table": item.__tablename__,
        "safe_scalars": scalars,
        "payload_hashes": hashes,
        "account_reference_hash": account_reference_hash,
    }


def _prepare(session: Session, source_type: str, source_id: str) -> dict[str, Any]:
    if source_type not in SOURCE_REGISTRY:
        raise ValueError("unknown governance journal source_type")
    if not isinstance(source_id, str) or not source_id.strip() or len(source_id.strip()) > 36:
        raise ValueError("source_id is required and must fit the source identity contract")
    model, scope = SOURCE_REGISTRY[source_type]
    item = session.get(model, source_id.strip())
    if not item:
        raise ValueError("governance journal source record not found")
    publication = _publication_for(session, source_type, item)
    if source_type.startswith("GENERIC_") and source_type not in {"GENERIC_DEMO_CONTRACT", "GENERIC_COMPILATION"} and not publication:
        raise ValueError("generic source publication lineage is missing")
    contract = _contract_for(session, item, publication)
    strategy = _strategy_for(session, item, contract)
    if source_type not in {"ROUTER_DECISION", "ROUTER_PARAMETERS", "ROUTER_VERIFICATION", "LEGACY_JOURNAL", "LEGACY_TRADE"} and not strategy:
        raise ValueError("journal source is missing mandatory StrategyVersion lineage")
    if isinstance(item, (Deployment, JournalEvent, DemoTrade)) and getattr(item, "target_environment", getattr(item, "environment", "DEMO")) != "DEMO":
        raise ValueError("legacy journal source is not DEMO scoped")
    account_reference_hash = _account_reference(publication)
    event_time, observed_time, time_semantics = _event_clock(item)
    snapshot = _source_snapshot(item, account_reference_hash)
    source_fingerprint = _hash(snapshot)
    config_checksum = getattr(item, "config_checksum", None)
    if not config_checksum and isinstance(item, GenericMt5Compilation):
        config_checksum = item.config_checksum
    broker_symbol = getattr(item, "broker_symbol", None)
    if not broker_symbol and publication:
        broker_symbol = publication.broker_symbol
    if not broker_symbol and contract:
        broker_symbol = contract.contract.get("broker_symbol")
    lineage = {
        "protocol_version": PROTOCOL_VERSION,
        "source": {
            "type": source_type,
            "table": item.__tablename__,
            "id": item.id,
            "declared_fingerprint": getattr(item, "fingerprint", None),
            "snapshot_fingerprint": source_fingerprint,
        },
        "strategy": {"id": strategy.id, "checksum": strategy.checksum} if strategy else None,
        "generic": {
            "contract_id": contract.id if contract else None,
            "publication_id": publication.id if publication else None,
            "config_checksum": config_checksum,
        },
        "privacy": {
            "raw_payload_copied": False,
            "raw_account_identity_stored": False,
            "account_reference_hash": account_reference_hash,
        },
        "time": {"event_time": event_time, "observed_time": observed_time, "semantics": time_semantics},
    }
    origin = _origin(source_type, item, strategy, publication)
    if origin not in ORIGINS or scope not in SCOPES:
        raise ValueError("journal origin or scope classification is invalid")
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "source_fingerprint": source_fingerprint,
        "evidence_origin": origin,
        "evidence_scope": scope,
        "lineage": lineage,
    }
    return {
        "fingerprint": _hash(payload),
        "source_type": source_type,
        "source_table": item.__tablename__,
        "source_id": item.id,
        "source_fingerprint": source_fingerprint,
        "evidence_origin": origin,
        "evidence_scope": scope,
        "strategy_version_id": strategy.id if strategy else None,
        "strategy_checksum": strategy.checksum if strategy else None,
        "config_checksum": config_checksum,
        "publication_id": publication.id if publication else None,
        "account_reference_hash": account_reference_hash,
        "broker_symbol": broker_symbol,
        "event_time": event_time,
        "observed_time": observed_time,
        "time_semantics": time_semantics,
        "integrity_status": INTEGRITY_VERIFIED,
        "lineage": lineage,
        "snapshot": snapshot,
    }


def materialize(session: Session, payload: object) -> tuple[GovernanceJournalItem, bool]:
    if not isinstance(payload, dict) or set(payload) != {"source_type", "source_id"}:
        raise ValueError("journal materialization requires exact source_type and source_id fields")
    prepared = _prepare(session, str(payload["source_type"]), str(payload["source_id"]))
    existing = session.scalar(select(GovernanceJournalItem).where(
        GovernanceJournalItem.source_type == prepared["source_type"],
        GovernanceJournalItem.source_id == prepared["source_id"],
    ))
    if existing:
        if existing.fingerprint != prepared["fingerprint"] or existing.source_fingerprint != prepared["source_fingerprint"] or existing.lineage != prepared["lineage"]:
            raise ValueError("journal source identity conflicts with its immutable indexed record")
        return existing, True
    item = GovernanceJournalItem(**{key: value for key, value in prepared.items() if key != "snapshot"})
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(GovernanceJournalItem).where(
            GovernanceJournalItem.source_type == prepared["source_type"],
            GovernanceJournalItem.source_id == prepared["source_id"],
        ))
        if existing and existing.fingerprint == prepared["fingerprint"] and existing.source_fingerprint == prepared["source_fingerprint"] and existing.lineage == prepared["lineage"]:
            return existing, True
        raise ValueError("concurrent governance journal identity conflict")
    session.refresh(item)
    return item, False


def verify(session: Session, item: GovernanceJournalItem) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    try:
        prepared = _prepare(session, item.source_type, item.source_id)
        expected = {
            "fingerprint": prepared["fingerprint"],
            "source_fingerprint": prepared["source_fingerprint"],
            "source_table": prepared["source_table"],
            "evidence_origin": prepared["evidence_origin"],
            "evidence_scope": prepared["evidence_scope"],
            "strategy_version_id": prepared["strategy_version_id"],
            "strategy_checksum": prepared["strategy_checksum"],
            "config_checksum": prepared["config_checksum"],
            "publication_id": prepared["publication_id"],
            "account_reference_hash": prepared["account_reference_hash"],
            "broker_symbol": prepared["broker_symbol"],
            "event_time": prepared["event_time"],
            "observed_time": prepared["observed_time"],
            "time_semantics": prepared["time_semantics"],
            "lineage": prepared["lineage"],
        }
        observed = {key: getattr(item, key) for key in expected}
        for key in expected:
            checks[key] = {"status": "PASS" if observed[key] == expected[key] else "FAIL"}
    except Exception as error:
        checks["source_available_and_valid"] = {"status": "FAIL", "reason_code": type(error).__name__}
    passed = bool(checks) and all(check["status"] == "PASS" for check in checks.values())
    return {
        "status": "PASSED" if passed else "FAILED",
        "journal_item_id": item.id,
        "journal_fingerprint": item.fingerprint,
        "checks": checks,
        "safety_boundary": {
            "read_only": True,
            "source_mutated": False,
            "deployment_created": False,
            "mt5_action_created": False,
            "order_or_trade_created": False,
            "live_authorized": False,
        },
    }


def serialize(item: GovernanceJournalItem, reused: bool | None = None) -> dict[str, Any]:
    result = {
        "id": item.id,
        "fingerprint": item.fingerprint,
        "source_type": item.source_type,
        "source_table": item.source_table,
        "source_id": item.source_id,
        "source_fingerprint": item.source_fingerprint,
        "evidence_origin": item.evidence_origin,
        "evidence_scope": item.evidence_scope,
        "strategy_version_id": item.strategy_version_id,
        "strategy_checksum": item.strategy_checksum,
        "config_checksum": item.config_checksum,
        "publication_id": item.publication_id,
        "account_reference_hash": item.account_reference_hash,
        "broker_symbol": item.broker_symbol,
        "event_time": item.event_time,
        "observed_time": item.observed_time,
        "time_semantics": item.time_semantics,
        "integrity_status": item.integrity_status,
        "lineage": item.lineage,
        "created_at": _iso(item.created_at),
        "safety_boundary": {
            "append_only_reference": True,
            "raw_payload_copied": False,
            "source_mutated": False,
            "live_authorized": False,
        },
    }
    if reused is not None:
        result["reused"] = reused
    return result


def _cursor_encode(item: GovernanceJournalItem) -> str:
    value = canonical_json({"created_at": _iso(item.created_at), "id": item.id}).encode()
    return urlsafe_b64encode(value).decode().rstrip("=")


def _cursor_decode(value: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode())
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
        item_id = str(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("journal cursor is invalid") from error
    if not item_id or len(item_id) > 36:
        raise ValueError("journal cursor is invalid")
    return created_at, item_id


def list_items(
    session: Session,
    *,
    limit: int,
    cursor: str | None = None,
    source_type: str | None = None,
    evidence_scope: str | None = None,
    evidence_origin: str | None = None,
    strategy_version_id: str | None = None,
) -> dict[str, Any]:
    if source_type and source_type not in SOURCE_REGISTRY:
        raise ValueError("unknown governance journal source_type filter")
    if evidence_scope and evidence_scope not in SCOPES:
        raise ValueError("unknown governance journal evidence_scope filter")
    if evidence_origin and evidence_origin not in ORIGINS:
        raise ValueError("unknown governance journal evidence_origin filter")
    query = select(GovernanceJournalItem)
    if source_type:
        query = query.where(GovernanceJournalItem.source_type == source_type)
    if evidence_scope:
        query = query.where(GovernanceJournalItem.evidence_scope == evidence_scope)
    if evidence_origin:
        query = query.where(GovernanceJournalItem.evidence_origin == evidence_origin)
    if strategy_version_id:
        query = query.where(GovernanceJournalItem.strategy_version_id == strategy_version_id)
    if cursor:
        created_at, item_id = _cursor_decode(cursor)
        query = query.where(or_(
            GovernanceJournalItem.created_at < created_at,
            and_(GovernanceJournalItem.created_at == created_at, GovernanceJournalItem.id < item_id),
        ))
    rows = list(session.scalars(query.order_by(GovernanceJournalItem.created_at.desc(), GovernanceJournalItem.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    items = rows[:limit]
    return {
        "items": [serialize(item) for item in items],
        "page": {
            "limit": limit,
            "has_more": has_more,
            "next_cursor": _cursor_encode(items[-1]) if has_more and items else None,
            "order": "created_at DESC, id DESC",
        },
        "safety_boundary": {"read_only": True, "source_mutated": False, "live_authorized": False},
    }


def source_contract() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_types": [
            {"source_type": name, "source_table": model.__tablename__, "evidence_scope": scope}
            for name, (model, scope) in sorted(SOURCE_REGISTRY.items())
        ],
        "origins": sorted(ORIGINS),
        "scopes": sorted(SCOPES),
        "identity": "source_type + source_id + exact source snapshot fingerprint + lineage",
        "pagination": "opaque cursor over created_at DESC, id DESC",
        "privacy": {
            "raw_payloads_copied": False,
            "raw_account_identity_stored": False,
            "account_reference": "application-scoped SHA-256 reference only",
        },
        "safety_boundary": {
            "append_only": True,
            "delete_endpoint": False,
            "source_mutation": False,
            "deployment_created": False,
            "mt5_action_created": False,
            "order_or_trade_created": False,
            "live_authorized": False,
        },
    }
