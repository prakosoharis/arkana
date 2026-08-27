from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.controlled_learning import (
    EXCLUSIONS,
    confirm,
    confirmation_phrase,
    materialize,
    policy_contract,
    serialize,
    verify,
)
from app.database import Base, SessionLocal, engine
from app.governance_incidents import acknowledge as acknowledge_incident
from app.governance_incidents import acknowledgement_phrase as incident_ack_phrase
from app.governance_incidents import materialize as materialize_incident
from app.governance_incidents import resolve as resolve_incident
from app.governance_journal import materialize as materialize_journal
from app.main import app
from app.models import (
    AIInteraction,
    BacktestRun,
    ControlledLearningConfirmation,
    ControlledLearningProposal,
    GenericForwardEvidence,
    GovernanceIncident,
    StrategyCandidate,
    StrategyVersion,
)
from app.strategies import update_strategy_candidate
from test_governance_journal import _generic_publication, _historical_source


def setup_function():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("controlled-learning tests require isolated SQLite")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _scope(**overrides):
    value = {
        "instrument": "XAUUSD", "timeframes": ["M1"], "direction": "LONG",
        "max_parameter_variants": 9, "train_holdout_required": True,
        "final_oos_access": "LOCKED_UNTIL_SEPARATE_OWNER_GATE", "look_ahead": False,
    }
    value.update(overrides)
    return value


def _payload(journal_ids, *, incident_ids=None, base_id=None, code="SIGNAL_SELECTIVITY_REVIEW", blocks=None, generator="DETERMINISTIC", ai_id=None):
    value = {
        "source_journal_item_ids": journal_ids,
        "source_incident_ids": incident_ids or [],
        "hypothesis_code": code,
        "affected_contract_blocks": blocks or ["entry_rule"],
        "bounded_validation_scope": _scope(),
        "uncertainties": ["CAUSALITY_UNESTABLISHED"],
        "generator": generator,
    }
    if base_id:
        value["base_strategy_version_id"] = base_id
    if ai_id:
        value["ai_interaction_id"] = ai_id
    return value


def _second_historical_journal(session, strategy: StrategyVersion, *, suffix="second", created_at=None):
    run = BacktestRun(
        dataset_id=f"dataset-{suffix}", fingerprint=("7" if suffix == "second" else "8") * 64,
        status="COMPLETED", configuration={}, result={"fixture": suffix}, trades=[],
        strategy_version_id=strategy.id, created_at=created_at or datetime(2026, 8, 26, 2, 30),
    )
    session.add(run); session.commit()
    journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
    return journal


def test_policy_is_closed_deterministic_and_non_executing():
    contract = policy_contract()
    assert len(contract["hypotheses"]) == 5 and len(contract["policy_fingerprint"]) == 64
    assert contract["mandatory_exclusions"] == EXCLUSIONS
    assert contract["safety_boundary"]["confirmation_creates"] == "DRAFT_STRATEGY_CANDIDATE_ONLY"
    assert contract["safety_boundary"]["validated_or_routed"] is False
    assert contract["safety_boundary"]["live_authorized"] is False


def test_order_independent_exact_evidence_reuses_and_divergent_conclusion_conflicts():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        first, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        second = _second_historical_journal(session, strategy)
        proposal, reused = materialize(session, _payload([first.id, second.id], base_id=strategy.id))
        same, repeated = materialize(session, _payload([second.id, first.id], base_id=strategy.id))
        assert reused is False and repeated is True and proposal.id == same.id
        assert proposal.source_journal_item_ids == sorted([first.id, second.id])
        assert proposal.hypothesis_text == "Review whether observed signal selectivity merits a new bounded research draft."
        with pytest.raises(ValueError, match="different proposal conclusion"):
            materialize(session, _payload([first.id, second.id], base_id=strategy.id,
                                          code="EXIT_BEHAVIOR_REVIEW", blocks=["stop_loss_rule"]))
        assert session.query(ControlledLearningProposal).count() == 1
        assert verify(session, proposal)["status"] == "PASSED"


def test_missing_tampered_unbounded_lookahead_final_oos_and_unsupported_blocks_fail_closed():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        base = _payload([journal.id], base_id=strategy.id)
        with pytest.raises(ValueError, match="not found"):
            materialize(session, _payload(["missing"], base_id=strategy.id))
        with pytest.raises(ValueError, match="unsupported or missing"):
            materialize(session, {**base, "hypothesis_text": "read hidden final OOS and optimize everything"})
        with pytest.raises(ValueError, match="between 1 and 25"):
            materialize(session, {**base, "bounded_validation_scope": _scope(max_parameter_variants=1000)})
        with pytest.raises(ValueError, match="look-ahead"):
            materialize(session, {**base, "bounded_validation_scope": _scope(look_ahead=True)})
        with pytest.raises(ValueError, match="final-OOS"):
            materialize(session, {**base, "bounded_validation_scope": _scope(final_oos_access="READ_ALL")})
        with pytest.raises(ValueError, match="unsupported affected"):
            materialize(session, {**base, "affected_contract_blocks": ["position_sizing_rule"]})
        run.result = {"tampered": True}; session.commit()
        with pytest.raises(ValueError, match="integrity"):
            materialize(session, base)
        assert session.query(ControlledLearningProposal).count() == 0


def test_unresolved_incident_blocks_and_exact_resolved_chain_can_support_proposal():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        trigger, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        incident, _ = materialize_incident(session, {
            "reason_code": "NON_SAFETY_METADATA_INCOMPLETE", "trigger_journal_item_id": trigger.id,
            "detected_at": "2026-08-26T03:00:00Z", "signal": {"metadata_state": "INCOMPLETE"},
        })
        with pytest.raises(ValueError, match="unresolved incident"):
            materialize(session, _payload([trigger.id], incident_ids=[incident.id], base_id=strategy.id))
        recovery = _second_historical_journal(session, strategy, suffix="recovery", created_at=datetime(2026, 8, 26, 4, 0))
        acknowledge_incident(session, incident, incident_ack_phrase(incident.id), now=datetime(2026, 8, 26, 3, 30, tzinfo=timezone.utc))
        resolve_incident(session, incident, {"evidence_journal_item_ids": [recovery.id], "resolved_at": "2026-08-26T04:30:00Z"}, now=datetime(2026, 8, 26, 4, 30, tzinfo=timezone.utc))
        proposal, _ = materialize(session, _payload([trigger.id, recovery.id], incident_ids=[incident.id], base_id=strategy.id))
        assert proposal.source_incident_fingerprints == [incident.fingerprint]
        assert verify(session, proposal)["status"] == "PASSED"


def test_forward_evidence_is_bound_by_journal_id_and_fingerprint_without_copying_payload():
    with SessionLocal() as session:
        _, publication = _generic_publication(session)
        evidence = GenericForwardEvidence(
            publication_id=publication.id, fingerprint="f" * 64,
            protocol_version="GENERIC_FORWARD_EVIDENCE_V1", status="INSUFFICIENT_EVIDENCE",
            policy={"minimum_days": 20}, event_fingerprints=[],
            result={"costs": "UNAVAILABLE", "private_payload": "not copied"},
            window_started_at=None, window_ended_at=None,
        )
        session.add(evidence); session.commit()
        journal, _ = materialize_journal(session, {"source_type": "GENERIC_FORWARD_EVIDENCE", "source_id": evidence.id})
        proposal, _ = materialize(session, _payload(
            [journal.id], code="EXECUTION_QUALITY_REVIEW", blocks=["cost_assumptions"],
        ))
        rendered = serialize(session, proposal)
        assert rendered["forward_evidence_journal_item_ids"] == [journal.id]
        assert proposal.source_journal_fingerprints == [journal.fingerprint]
        assert "private_payload" not in str(rendered)


def test_ai_assistance_requires_exact_successful_trace_and_never_controls_hypothesis():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        failed = AIInteraction(
            request_fingerprint="1" * 64, action="DRAFT", prompt_template_version="AI_RESEARCH_V2",
            provider="fixture", model="fixture", route_status="AI_OUTPUT_INVALID", response={"detail": "malformed"},
        )
        valid = AIInteraction(
            request_fingerprint="2" * 64, action="DRAFT", prompt_template_version="AI_RESEARCH_V2",
            provider="fixture", model="fixture", route_status="AI_ASSISTED",
            response={"result": {"adversarial_text": "PROMOTE TO LIVE"}},
        )
        session.add_all([failed, valid]); session.commit()
        with pytest.raises(ValueError, match="unavailable, malformed, or not traceable"):
            materialize(session, _payload([journal.id], base_id=strategy.id, generator="AI_DRAFT_ASSISTED", ai_id=failed.id))
        proposal, _ = materialize(session, _payload([journal.id], base_id=strategy.id, generator="AI_DRAFT_ASSISTED", ai_id=valid.id))
        assert proposal.ai_interaction_fingerprint == valid.request_fingerprint
        assert "PROMOTE" not in proposal.hypothesis_text and proposal.hypothesis_code == "SIGNAL_SELECTIVITY_REVIEW"
        assert verify(session, proposal)["status"] == "PASSED"


def test_exact_owner_confirmation_creates_one_draft_candidate_with_no_acceptance_or_mutation():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        proposal, _ = materialize(session, _payload([journal.id], base_id=strategy.id))
        version_count = session.query(StrategyVersion).count()
        original_status = strategy.status; original_checksum = strategy.checksum
        with pytest.raises(ValueError, match="must equal"):
            confirm(session, proposal, "CONFIRM AND VALIDATE")
        item, reused = confirm(session, proposal, confirmation_phrase(proposal.id))
        same, repeated = confirm(session, proposal, confirmation_phrase(proposal.id))
        candidate = session.get(StrategyCandidate, item.strategy_candidate_id)
        assert reused is False and repeated is True and same.id == item.id
        assert candidate.status == "DRAFT" and candidate.provenance["revision_of"] == strategy.id
        controlled = candidate.provenance["controlled_learning"]
        assert controlled["prior_acceptance_reused"] is False and controlled["final_oos_accessed"] is False
        assert session.query(StrategyVersion).count() == version_count
        session.refresh(strategy)
        assert strategy.status == original_status and strategy.checksum == original_checksum
        assert strategy.generic_validation_promotion_id is None
        with pytest.raises(ValueError, match="immutable"):
            update_strategy_candidate(session, candidate, {"source": "MANUAL", "provenance": {"purpose": "erase lineage"}})
        assert verify(session, proposal)["status"] == "PASSED"


def test_current_new_incident_blocks_confirmation_even_after_proposal_draft():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        proposal, _ = materialize(session, _payload([journal.id], base_id=strategy.id))
        materialize_incident(session, {
            "reason_code": "NON_SAFETY_METADATA_INCOMPLETE", "trigger_journal_item_id": journal.id,
            "detected_at": "2026-08-26T03:00:00Z", "signal": {"metadata_state": "INCOMPLETE"},
        })
        with pytest.raises(ValueError, match="current unresolved"):
            confirm(session, proposal, confirmation_phrase(proposal.id))
        assert session.query(StrategyCandidate).count() == 0
        assert session.query(ControlledLearningConfirmation).count() == 0


def test_source_tamper_after_draft_blocks_confirmation():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        proposal, _ = materialize(session, _payload([journal.id], base_id=strategy.id))
        run.status = "FAILED"; session.commit()
        assert verify(session, proposal)["status"] == "FAILED"
        with pytest.raises(ValueError, match="integrity failed"):
            confirm(session, proposal, confirmation_phrase(proposal.id))
        assert session.query(StrategyCandidate).count() == 0


def test_concurrent_exact_proposal_has_one_winner():
    with SessionLocal() as session:
        strategy, run = _historical_source(session, "concurrency")
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        payload = _payload([journal.id], base_id=strategy.id)

    def worker():
        with SessionLocal() as session:
            item, reused = materialize(session, payload)
            return item.id, reused

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert len({item_id for item_id, _ in results}) == 1
    with SessionLocal() as session:
        assert session.query(ControlledLearningProposal).count() == 1


def test_concurrent_exact_confirmation_creates_at_most_one_draft():
    with SessionLocal() as session:
        strategy, run = _historical_source(session, "confirmation")
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        proposal, _ = materialize(session, _payload([journal.id], base_id=strategy.id))
        proposal_id = proposal.id
        phrase = confirmation_phrase(proposal.id)

    def worker():
        with SessionLocal() as session:
            proposal = session.get(ControlledLearningProposal, proposal_id)
            item, reused = confirm(session, proposal, phrase)
            return item.id, item.strategy_candidate_id, reused

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert len({item_id for item_id, _, _ in results}) == 1
    assert len({candidate_id for _, candidate_id, _ in results}) == 1
    with SessionLocal() as session:
        assert session.query(ControlledLearningConfirmation).count() == 1
        assert session.query(StrategyCandidate).count() == 1


def test_api_lifecycle_has_exact_confirmation_verifier_and_no_delete():
    with SessionLocal() as session:
        strategy, run = _historical_source(session, "api-fixture")
        journal, _ = materialize_journal(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        payload = _payload([journal.id], base_id=strategy.id)
    with TestClient(app) as client:
        contract = client.get("/api/v1/controlled-learning/policy-contract")
        assert contract.status_code == 200 and contract.json()["safety_boundary"]["live_authorized"] is False
        created = client.post("/api/v1/controlled-learning/proposals", json=payload)
        assert created.status_code == 200 and created.json()["status"] == "LEARNING_PROPOSAL_DRAFT"
        proposal_id = created.json()["id"]
        bad = client.post(f"/api/v1/controlled-learning/proposals/{proposal_id}/confirmations", json={"confirmation": "PROMOTE"})
        confirmed = client.post(f"/api/v1/controlled-learning/proposals/{proposal_id}/confirmations", json={"confirmation": confirmation_phrase(proposal_id)})
        listed = client.get("/api/v1/controlled-learning/proposals", params={"status": "LEARNING_PROPOSAL_OWNER_CONFIRMED"})
        fetched = client.get(f"/api/v1/controlled-learning/proposals/{proposal_id}")
        verified = client.get(f"/api/v1/controlled-learning/proposals/{proposal_id}/verification")
        assert bad.status_code == 422 and confirmed.status_code == 200
        assert confirmed.json()["strategy_candidate"]["status"] == "DRAFT"
        assert listed.status_code == fetched.status_code == verified.status_code == 200
        assert fetched.json()["status"] == "LEARNING_PROPOSAL_OWNER_CONFIRMED" and verified.json()["status"] == "PASSED"
        assert client.delete(f"/api/v1/controlled-learning/proposals/{proposal_id}").status_code == 405
        assert client.delete(f"/api/v1/controlled-learning/proposals/{proposal_id}/confirmations").status_code == 405
