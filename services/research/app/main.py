from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread

from hmac import compare_digest

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .database import Base, SessionLocal, engine, get_session
from .migrations import run_migrations
from .market_data import TIMEFRAMES, import_csv, read_bars, serialize_dataset
from .models import AIInteraction, BacktestRun, CapitalBrokerContract, ConstrainedCapitalPoint, ConstrainedCapitalSimulation, ControlledLearningProposal, Dataset, DatasetBarAsset, Deployment, EdgeSearchCampaign, FixedLotCapitalSimulation, FixedLotEquityPoint, FractionalRiskCapitalSimulation, FractionalRiskEquityPoint, GenericDemoChainVerification, GenericDemoContract, GenericForwardEvidence, GenericMt5Compilation, GenericMt5Publication, GenericMt5TelemetryEvent, GenericEvidenceDecision, GenericEvidenceOwnerConfirmation, GenericEvidenceVerification, GenericRobustnessEvidence, GenericValidationEligibility, GenericValidationLifecycleVerification, GenericValidationPromotion, GenericValidationRetirement, GovernanceIncident, GovernanceJournalItem, JournalEvent, LiveReadinessAssessment, ResearchHypothesis, ResearchRun, ResearchRuleDefinition, Sprint21AcceptanceVerification, StrategyCandidate, StrategyContractAssessment, StrategyEvaluatorVerification, StrategyRouterDecision, StrategyRouterDecisionParameters, StrategyRouterEligibility, StrategyRouterPolicy, StrategyRouterVerification, StrategyVersion, SupplementalHistoricalValidation, BrokerMetadataSnapshot, OosValidation, VariantExperimentContract, VariantHoldoutRun, VariantRevisionConfirmation, VariantTrainRun
from .hypotheses import parse_prompt, validate_definition
from .registries import assess
from .research_execution import run_hypothesis
from .backtesting import run_backtest, run_supplemental_full_validation
from .oos_validation import run as run_oos_validation
from .generic_robustness import run as run_generic_robustness, serialize as serialize_generic_robustness
from .generic_evidence_decisions import confirm as confirm_generic_evidence, materialize as materialize_generic_evidence_decision, serialize_confirmation as serialize_generic_evidence_confirmation, serialize_decision as serialize_generic_evidence_decision
from .generic_evidence_verification import get as get_generic_evidence_verification, materialize as materialize_generic_evidence_verification, serialize as serialize_generic_evidence_verification
from .generic_validation_eligibility import list_for_decision as list_generic_validation_eligibilities, materialize as materialize_generic_validation_eligibility, serialize as serialize_generic_validation_eligibility
from .generic_validation_promotions import get_for_eligibility as get_generic_validation_promotion, promote as promote_generic_validation, serialize as serialize_generic_validation_promotion
from .generic_validation_retirements import get_for_strategy as get_generic_validation_retirement, retire as retire_generic_validation, serialize as serialize_generic_validation_retirement
from .generic_validation_lifecycle_verification import get_latest as get_generic_lifecycle_verification, materialize as materialize_generic_lifecycle_verification, serialize as serialize_generic_lifecycle_verification
from .strategy_router_eligibility import current_policy as current_router_policy, list_for_strategy as list_router_eligibilities, materialize as materialize_router_eligibility, materialize_policy as materialize_router_policy, parse_evaluated_at, serialize as serialize_router_eligibility, serialize_policy as serialize_router_policy
from .strategy_router_decisions import decision_contract as router_decision_contract, list_all as list_router_decisions, materialize as materialize_router_decision, serialize as serialize_router_decision
from .strategy_router_parameters import materialize as materialize_router_parameters, parameter_contract as router_parameter_contract, serialize as serialize_router_parameters
from .strategy_router_verification import get_latest as get_latest_router_verification, materialize as materialize_router_verification, serialize as serialize_router_verification
from .strategy_router_safety import audit as audit_router_safety
from .generic_demo_contracts import create as create_generic_demo_contract, eligibility_overview as generic_demo_eligibility_overview, list_all as list_generic_demo_contracts, serialize as serialize_generic_demo_contract, validation_report as generic_demo_validation_report
from .generic_mt5_compiler import adapter_registry as generic_mt5_adapter_registry, create as create_generic_mt5_compilation, list_all as list_generic_mt5_compilations, serialize as serialize_generic_mt5_compilation, validation_report as generic_mt5_compilation_report
from .generic_mt5_publications import block_entries as block_generic_mt5_entries, list_all as list_generic_mt5_publications, poll_ack as poll_generic_mt5_ack, preflight as generic_mt5_publication_preflight, publish as publish_generic_mt5_compilation, reconcile_lifecycle as reconcile_generic_mt5_lifecycle, serialize as serialize_generic_mt5_publication
from .generic_forward_telemetry import list_evidence as list_generic_forward_evidence, list_events as list_generic_mt5_telemetry, materialize as materialize_generic_forward_evidence, serialize_evidence as serialize_generic_forward_evidence, serialize_event as serialize_generic_mt5_telemetry, sync as sync_generic_mt5_telemetry
from .generic_demo_chain_verification import get_latest as get_latest_generic_demo_verification, materialize as materialize_generic_demo_verification, serialize as serialize_generic_demo_verification
from .generic_demo_owner_overview import build as build_generic_demo_owner_overview
from .governance_journal import list_items as list_governance_journal_items, materialize as materialize_governance_journal_item, serialize as serialize_governance_journal_item, source_contract as governance_journal_source_contract, verify as verify_governance_journal_item
from .governance_incidents import acknowledge as acknowledge_governance_incident, list_all as list_governance_incidents, materialize as materialize_governance_incident, policy_contract as governance_incident_policy_contract, resolve as resolve_governance_incident, serialize as serialize_governance_incident, serialize_ack as serialize_governance_incident_ack, serialize_resolution as serialize_governance_incident_resolution, verify as verify_governance_incident
from .controlled_learning import confirm as confirm_learning_proposal, list_all as list_learning_proposals, materialize as materialize_learning_proposal, policy_contract as learning_proposal_policy_contract, serialize as serialize_learning_proposal, serialize_confirmation as serialize_learning_confirmation, verify as verify_learning_proposal
from .live_readiness import list_all as list_live_readiness_assessments, materialize as materialize_live_readiness_assessment, policy_contract as live_readiness_policy_contract, serialize as serialize_live_readiness_assessment, verify as verify_live_readiness_assessment
from .sprint21_acceptance import latest as latest_sprint21_acceptance, materialize as materialize_sprint21_acceptance, owner_overview as sprint21_owner_overview, serialize as serialize_sprint21_acceptance, verify as verify_sprint21_acceptance
from .edge_search import create as create_edge_search_campaign, list_all as list_edge_search_campaigns, list_trials as list_edge_search_trials, policy_contract as edge_search_policy_contract, serialize as serialize_edge_search_campaign, validation_report as edge_search_validation_report, verify as verify_edge_search_campaign
from .edge_search_execution import execute as execute_edge_search_campaign, progress as edge_search_progress, survivors as edge_search_survivors
from .strategies import approve_candidate, create_candidate, create_strategy_candidate, update_strategy_candidate, confirm_strategy_version, revision, serialize_strategy
from .strategy_contracts import validate as validate_strategy_contract
from .strategy_capabilities import confirm as confirm_capability_assessment, materialize as materialize_capability_assessment, registry as strategy_capability_registry, serialize as serialize_capability_assessment
from .strategy_compiler import compile_contract as compile_strategy_contract
from .strategy_evaluator_verification import get as get_strategy_evaluator_verification, materialize as materialize_strategy_evaluator_verification, serialize as serialize_strategy_evaluator_verification
from .deployments import adapter_preflight, create_deployment, poll_ack, preflight, rollback, serialize as serialize_deployment
from . import settings
from .settings import DATA_ROOT, MAX_BARS_PER_REQUEST
from .telemetry import serialize as serialize_journal_event, snapshot as telemetry_snapshot, sync as sync_telemetry
from .discovery import discover, similar
from .mt5_acquisition import bootstrap as bootstrap_mt5_historical, bootstrap_status as mt5_bootstrap_status, process as process_mt5_historical, scheduler_tick as mt5_scheduler_tick, status as mt5_historical_status
from .settings import HISTORICAL_SYNC_POLL_SECONDS
from .ai_gateway import AIError, draft as ai_draft, draft_rule_definitions as ai_rule_drafts, explain as ai_explain, usage as ai_usage
from .research_rules import SUPPORTED_PRIMITIVES, create_draft as create_rule_draft, confirm as confirm_rule, create_revision as create_rule_revision, reassess_hypotheses, serialize as serialize_rule, update_draft as update_rule_draft, validate_ai_drafts, validation_report as research_rule_validation_report
from .research_contracts import compile_contract, confirm_and_run
from .demo_validation import readiness as demo_readiness
from .broker_metadata import import_snapshot, import_order_calc_validation
from .financial_evidence import materialize as materialize_financial
from .capital_contracts import PROTOCOL_VERSION as CAPITAL_CONTRACT_PROTOCOL_VERSION, create as create_capital_contract, serialize as serialize_capital_contract, validation_report as capital_contract_validation_report
from .capital_simulations import run as run_fixed_lot_capital_simulation, serialize as serialize_fixed_lot_capital_simulation
from .fractional_risk_simulations import run as run_fractional_risk_simulation, serialize as serialize_fractional_risk_simulation
from .constrained_capital_simulations import get_materialized_verification, materialize_verification, run as run_constrained_capital_simulation, serialize as serialize_constrained_capital_simulation, serialize_verification
from .variant_experiment_contracts import PROTOCOL_VERSION as VARIANT_CONTRACT_PROTOCOL_VERSION, create as create_variant_experiment_contract, serialize as serialize_variant_experiment_contract, validation_report as variant_experiment_validation_report
from .variant_train_runs import TrainRunConflict, run as run_variant_train_evaluation, serialize as serialize_variant_train_run
from .variant_holdout_runs import HoldoutRunConflict, get_selection as get_variant_selection, run as run_variant_holdout_evaluation, serialize as serialize_variant_holdout_run, serialize_selection as serialize_variant_selection
from .variant_revision_lifecycle import RevisionRunConflict, confirm_and_run as confirm_variant_revision, serialize as serialize_variant_revision_confirmation
from .variant_experiment_verification import get_materialized as get_variant_experiment_verification, materialize as materialize_variant_experiment_verification, serialize as serialize_variant_experiment_verification


app = FastAPI(title="ARKANA Research Service", version="0.1.0")
_historical_scheduler_stop = Event()
_historical_scheduler_lock = Lock()
_historical_scheduler_thread: Thread | None = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_owner_token(request, call_next):
    """Fail-closed bearer-token gate in front of every research route.

    CORS restricts browsers only; it never restricted a direct client. Because
    a publication write reaches FILE_COMMON and the EA acts on it, an
    unauthenticated caller could previously reach real DEMO execution.
    """
    if request.url.path in settings.UNAUTHENTICATED_PATHS:
        return await call_next(request)
    if not settings.RESEARCH_API_TOKEN:
        return JSONResponse({"detail": "RESEARCH_API_TOKEN is not configured; the research API is refusing every request"},
                            status_code=503, headers={"x-arkana-auth": "API_TOKEN_NOT_CONFIGURED"})
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        return JSONResponse({"detail": "A bearer Owner token is required"}, status_code=401,
                            headers={"www-authenticate": "Bearer", "x-arkana-auth": "TOKEN_MISSING"})
    if not compare_digest(presented.strip(), settings.RESEARCH_API_TOKEN):
        return JSONResponse({"detail": "The presented Owner token is not valid"}, status_code=401,
                            headers={"www-authenticate": "Bearer", "x-arkana-auth": "TOKEN_INVALID"})
    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    # Reproducible forward-only Sprint 02 migration for databases created before versioning.
    with engine.connect() as connection:
        try:
            connection.execute(text("ALTER TABLE research_hypotheses ADD COLUMN version INTEGER NOT NULL DEFAULT 1")); connection.commit()
        except Exception:
            connection.rollback()
        try:
            connection.execute(text("ALTER TABLE deployments ADD COLUMN broker_symbol VARCHAR(64)")); connection.commit()
        except Exception:
            connection.rollback()
    global _historical_scheduler_thread
    if not _historical_scheduler_thread or not _historical_scheduler_thread.is_alive():
        _historical_scheduler_stop.clear()
        _historical_scheduler_thread = Thread(target=_historical_scheduler, name="arkana-historical-sync", daemon=True)
        _historical_scheduler_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    _historical_scheduler_stop.set()


def _historical_scheduler() -> None:
    # A local, single-instance poller: it only reads/writes FILE_COMMON and never
    # participates in MT5 OnTick or ARKANA_ENGINE execution.
    while not _historical_scheduler_stop.is_set():
        if _historical_scheduler_lock.acquire(blocking=False):
            try:
                with SessionLocal() as session:
                    mt5_scheduler_tick(session)
            finally:
                _historical_scheduler_lock.release()
        _historical_scheduler_stop.wait(HISTORICAL_SYNC_POLL_SECONDS)


def dataset_query():
    return select(Dataset).options(selectinload(Dataset.bars))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    datasets = session.scalars(dataset_query().order_by(Dataset.imported_at.desc())).all()
    return {"datasets": [serialize_dataset(dataset) for dataset in datasets]}


@app.post("/api/v1/imports/csv")
async def upload_csv(
    file: UploadFile = File(...),
    symbol: str = Query("XAUUSD", min_length=1, max_length=32),
    source: str = Query("MT5_CSV", min_length=1, max_length=255),
    timezone_status: str = Query("UNVERIFIED_BROKER_TIME", min_length=1, max_length=64),
    session: Session = Depends(get_session),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(422, "Only CSV uploads are supported")
    content = await file.read()
    if not content:
        raise HTTPException(422, "CSV upload is empty")
    dataset, already_imported = import_csv(
        session,
        content,
        filename=file.filename,
        symbol=symbol,
        source=source,
        timezone_status=timezone_status,
        data_root=DATA_ROOT,
    )
    dataset = session.scalar(dataset_query().where(Dataset.id == dataset.id))
    return {"already_imported": already_imported, "dataset": serialize_dataset(dataset)}


@app.get("/api/v1/bars")
def bars(
    symbol: str = Query(..., min_length=1, max_length=32),
    timeframe: str = Query("M1"),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(500, ge=1, le=MAX_BARS_PER_REQUEST),
    session: Session = Depends(get_session),
) -> dict:
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"Unsupported timeframe. Supported: {', '.join(TIMEFRAMES)}")
    if start and end and start > end:
        raise HTTPException(422, "start must be before end")
    dataset = session.scalar(
        dataset_query().where(Dataset.symbol == symbol.upper()).order_by(Dataset.imported_at.desc())
    )
    if not dataset:
        return {"bars": [], "meta": {"symbol": symbol.upper(), "timeframe": timeframe, "status": "NO_DATA"}}
    asset = next((item for item in dataset.bars if item.timeframe == timeframe), None)
    if not asset:
        return {"bars": [], "meta": {"symbol": symbol.upper(), "timeframe": timeframe, "status": "NO_DATA"}}
    # Interactive chart queries remain bounded.  A large registered dataset is not an error;
    # return only the requested bounded page instead of leaking the bulk acquisition size.
    result = read_bars(asset, start=start, end=end, limit=limit, latest=start is None and end is None)[:limit]
    return {
        "bars": result,
        "meta": {
            "dataset_id": dataset.id,
            "symbol": dataset.symbol,
            "timeframe": timeframe,
            "source": dataset.source,
            "timezone_status": dataset.timezone_status,
            "range_start": asset.range_start.isoformat() + "Z",
            "range_end": asset.range_end.isoformat() + "Z",
            "status": "READY" if result else "NO_DATA",
        },
    }


def serialize_hypothesis(item: ResearchHypothesis) -> dict:
    return {"id": item.id, "source_prompt": item.source_prompt, "parser_source": item.parser_source, "status": item.status, "version": item.version, "definition": item.definition, "created_at": item.created_at.isoformat()+"Z", "updated_at": item.updated_at.isoformat()+"Z"}


@app.post("/api/v1/hypotheses/draft")
def create_hypothesis(payload: dict, session: Session = Depends(get_session)) -> dict:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(422, "prompt is required")
    definition, parser_source, status = parse_prompt(prompt)
    definition = assess(definition, session); status = definition["status"]
    item = ResearchHypothesis(source_prompt=prompt, parser_source=parser_source, status=status, definition=definition)
    session.add(item); session.commit(); session.refresh(item)
    return serialize_hypothesis(item)


@app.put("/api/v1/hypotheses/{hypothesis_id}")
def update_hypothesis(hypothesis_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item = session.get(ResearchHypothesis, hypothesis_id)
    if not item: raise HTTPException(404, "hypothesis not found")
    item.definition = assess(validate_definition(payload.get("definition")), session); item.status = item.definition["status"]; item.version += 1; session.commit(); session.refresh(item)
    return serialize_hypothesis(item)


@app.get("/api/v1/ai/usage")
def get_ai_usage(session: Session = Depends(get_session)) -> dict:
    return ai_usage(session)


@app.post("/api/v1/ai/draft")
def create_ai_draft(payload: dict, session: Session = Depends(get_session)) -> dict:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(422, "prompt is required")
    try:
        assisted = ai_draft(session, prompt, str(payload.get("tier", "FAST")).upper())
        definition = assisted.get("result", {}).get("definition")
        if not isinstance(definition, dict):
            raise HTTPException(422, "AI response did not contain a typed hypothesis draft")
        definition = assess(validate_definition(definition), session)
    except AIError as error:
        raise HTTPException(error.status_code, str(error)) from error
    item = ResearchHypothesis(source_prompt=prompt, parser_source="AI_ASSISTED", status=definition["status"], definition=definition)
    session.add(item); session.commit(); session.refresh(item)
    return {**serialize_hypothesis(item), "ai": {key: assisted.get(key) for key in ("route_status", "cached", "provider", "model")}}


@app.get("/api/v1/research-rules")
def list_research_rules(canonical_name: str | None = None, session: Session = Depends(get_session)) -> dict:
    query=select(ResearchRuleDefinition).order_by(ResearchRuleDefinition.canonical_name, ResearchRuleDefinition.version.desc())
    if canonical_name: query=query.where(ResearchRuleDefinition.canonical_name==canonical_name.upper())
    return {"rules":[serialize_rule(item) for item in session.scalars(query).all()]}


@app.post("/api/v1/research-rules")
def create_research_rule(payload: dict, session: Session = Depends(get_session)) -> dict:
    return serialize_rule(create_rule_draft(session, payload, source="OWNER_MANUAL"))


@app.put("/api/v1/research-rules/{rule_id}")
def update_research_rule(rule_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item=session.get(ResearchRuleDefinition, rule_id)
    if not item: raise HTTPException(404,"research rule not found")
    return serialize_rule(update_rule_draft(session,item,payload))


@app.post("/api/v1/research-rules/{rule_id}/revisions")
def revise_research_rule(rule_id: str, session: Session = Depends(get_session)) -> dict:
    item=session.get(ResearchRuleDefinition, rule_id)
    if not item: raise HTTPException(404,"research rule not found")
    return serialize_rule(create_rule_revision(session,item))


@app.get("/api/v1/research-rules/{rule_id}/validation")
def validate_research_rule(rule_id: str, session: Session = Depends(get_session)) -> dict:
    item=session.get(ResearchRuleDefinition, rule_id)
    if not item: raise HTTPException(404,"research rule not found")
    return research_rule_validation_report(item)


@app.post("/api/v1/research-rules/{rule_id}/confirm")
def owner_confirm_research_rule(rule_id: str, session: Session = Depends(get_session)) -> dict:
    item=session.get(ResearchRuleDefinition, rule_id)
    if not item: raise HTTPException(404,"research rule not found")
    return serialize_rule(confirm_rule(session,item))


@app.post("/api/v1/ai/rule-drafts")
def create_ai_rule_drafts(payload: dict, session: Session = Depends(get_session)) -> dict:
    hypothesis=session.get(ResearchHypothesis, str(payload.get("hypothesis_id","")))
    if not hypothesis: raise HTTPException(404,"hypothesis not found")
    definition=hypothesis.definition
    if definition.get("research_mode")!="PATTERN_COMPARISON": raise HTTPException(422,"AI rule drafting is available only for unresolved pattern comparison concepts")
    concepts=definition["definition"].get("unresolved_concepts",[])
    if not concepts: raise HTTPException(409,"All required concepts already have owner-confirmed definitions")
    try:
        context={"instrument":definition.get("instrument"),"timeframe":definition["definition"].get("timeframe"),"research_mode":definition.get("research_mode"),"unresolved_concepts":concepts,"available_primitives":sorted(SUPPORTED_PRIMITIVES),"event_primitives":["CANDLE_DIRECTION","LOCAL_SWING_HIGH","LOCAL_SWING_LOW"],"sequence_constraint_kinds":["BAR_GAP","VALUE_GREATER_THAN","VALUE_WITHIN_RATIO"],"outcome_kinds":["BREAKOUT_RECLAIM","NO_BREAKOUT","MEASURED_MOVE_TARGET","MEASURED_MOVE_FAILURE_RECLAIM"]}
        assisted=ai_rule_drafts(session,hypothesis.source_prompt,context,str(payload.get("tier","FAST")).upper())
        drafts=validate_ai_drafts(assisted.get("result"))
    except AIError as error:
        raise HTTPException(error.status_code,str(error)) from error
    items=[create_rule_draft(session,draft,source="AI_ASSISTED") for draft in drafts]
    return {"rules":[serialize_rule(item) for item in items],"ai":{key:assisted.get(key) for key in ("route_status","cached","provider","model")}}


@app.post("/api/v1/research-contracts/compile")
def compile_research_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    hypothesis=session.get(ResearchHypothesis,str(payload.get("hypothesis_id","")))
    if not hypothesis: raise HTTPException(404,"hypothesis not found")
    return compile_contract(session,hypothesis)


@app.post("/api/v1/research-contracts/confirm-run")
def confirm_research_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    hypothesis=session.get(ResearchHypothesis,str(payload.get("hypothesis_id","")))
    if not hypothesis: raise HTTPException(404,"hypothesis not found")
    try:
        run,reused=confirm_and_run(session,hypothesis,[str(item) for item in payload.get("rule_ids",[])])
    except ValueError as error: raise HTTPException(422,str(error)) from error
    return {**serialize_run(run,include_samples=True),"reused":reused}


@app.post("/api/v1/ai/explanations/research-runs/{run_id}")
def explain_research_run(run_id: str, payload: dict | None = None, session: Session = Depends(get_session)) -> dict:
    run = session.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "research run not found")
    summary = {"kind":"RESEARCH_RUN","run_id":run.id,"status":run.status,"result":run.result,"warning":run.result.get("warning"),"raw_market_data_excluded":True}
    try:
        return {**ai_explain(session, summary, str((payload or {}).get("tier", "FAST")).upper()), "context": {"run_id":run.id, "raw_market_data_excluded":True}}
    except AIError as error:
        raise HTTPException(error.status_code, str(error)) from error


def serialize_run(item: ResearchRun, include_samples: bool = False) -> dict:
    payload = {"id": item.id, "hypothesis_id": item.hypothesis_id, "status": item.status, "result": item.result, "created_at": item.created_at.isoformat() + "Z"}
    if include_samples:
        payload["samples"] = item.samples
    return payload


@app.post("/api/v1/research-runs")
def create_research_run(payload: dict, session: Session = Depends(get_session)) -> dict:
    hypothesis_id = str(payload.get("hypothesis_id", ""))
    hypothesis = session.get(ResearchHypothesis, hypothesis_id)
    if not hypothesis:
        raise HTTPException(404, "hypothesis not found")
    try:
        run, reused = run_hypothesis(session, hypothesis)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {**serialize_run(run, include_samples=True), "reused": reused}


@app.get("/api/v1/research-runs/{run_id}")
def get_research_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "research run not found")
    return serialize_run(run)


@app.get("/api/v1/research-runs/{run_id}/samples")
def get_research_samples(run_id: str, limit: int = Query(50, ge=1, le=50), session: Session = Depends(get_session)) -> dict:
    run = session.get(ResearchRun, run_id)
    if not run:
        raise HTTPException(404, "research run not found")
    return {"run_id": run.id, "samples": run.samples[:limit], "total": len(run.samples)}


def serialize_backtest(item: BacktestRun, include_trades: bool = False) -> dict:
    payload = {"id": item.id, "dataset_id": item.dataset_id, "strategy_version_id":item.strategy_version_id, "fingerprint": item.fingerprint, "status": item.status, "configuration": item.configuration, "result": item.result, "created_at": item.created_at.isoformat() + "Z"}
    if include_trades:
        payload["trades"] = item.trades
    return payload


@app.post("/api/v1/backtests")
def create_backtest(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        run, reused = run_backtest(session, payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {**serialize_backtest(run, include_trades=True), "reused": reused}

@app.post("/api/v1/strategy-versions/{strategy_version_id}/oos-validations")
def create_oos_validation(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_oos_validation(session, strategy_version_id)
        return serialize_oos_validation(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

@app.get("/api/v1/strategy-versions/{strategy_version_id}/oos-validations")
def list_oos_validations(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(OosValidation).where(OosValidation.strategy_version_id == strategy_version_id).order_by(OosValidation.created_at.desc())).all()
    return {"validations": [serialize_oos_validation(item) for item in items]}


@app.post("/api/v1/strategy-versions/{strategy_version_id}/generic-robustness")
def create_generic_robustness(strategy_version_id: str, payload: dict | None = None, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_generic_robustness(session, strategy_version_id, baseline_oos_validation_id=(payload or {}).get("baseline_oos_validation_id"))
        return serialize_generic_robustness(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/generic-robustness")
def list_generic_robustness(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(GenericRobustnessEvidence).where(GenericRobustnessEvidence.strategy_version_id == strategy_version_id).order_by(GenericRobustnessEvidence.created_at.desc())).all()
    return {"evidence": [serialize_generic_robustness(item) for item in items]}


@app.get("/api/v1/generic-robustness/{evidence_id}")
def get_generic_robustness(evidence_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericRobustnessEvidence, evidence_id)
    if not item:
        raise HTTPException(404, "generic robustness evidence not found")
    return serialize_generic_robustness(item)


@app.post("/api/v1/strategy-versions/{strategy_version_id}/generic-evidence-decisions")
def create_generic_evidence_decision(strategy_version_id: str, payload: dict | None = None, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_evidence_decision(session, strategy_version_id, robustness_evidence_id=(payload or {}).get("robustness_evidence_id"))
        return serialize_generic_evidence_decision(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/generic-evidence-decisions")
def list_generic_evidence_decisions(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(GenericEvidenceDecision).where(GenericEvidenceDecision.strategy_version_id == strategy_version_id).order_by(GenericEvidenceDecision.created_at.desc())).all()
    return {"decisions": [serialize_generic_evidence_decision(item) for item in items]}


@app.get("/api/v1/generic-evidence-decisions/{decision_id}")
def get_generic_evidence_decision(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericEvidenceDecision, decision_id)
    if not item:
        raise HTTPException(404, "generic evidence decision not found")
    return serialize_generic_evidence_decision(item)


@app.post("/api/v1/generic-evidence-decisions/{decision_id}/owner-confirmations")
def create_generic_evidence_confirmation(decision_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = confirm_generic_evidence(session, decision_id, str(payload.get("acknowledgement", "")))
        return serialize_generic_evidence_confirmation(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-evidence-decisions/{decision_id}/owner-confirmation")
def get_generic_evidence_confirmation(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.scalar(select(GenericEvidenceOwnerConfirmation).where(GenericEvidenceOwnerConfirmation.decision_id == decision_id))
    if not item:
        raise HTTPException(404, "generic evidence Owner confirmation not found")
    return serialize_generic_evidence_confirmation(item)


@app.get("/api/v1/generic-evidence-decisions/{decision_id}/verification")
def get_generic_evidence_acceptance_verification(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_generic_evidence_verification(session, decision_id)
    if not item:
        raise HTTPException(404, "generic evidence verification has not been materialized")
    return serialize_generic_evidence_verification(item)


@app.post("/api/v1/generic-evidence-decisions/{decision_id}/verification")
def materialize_generic_evidence_acceptance_verification(decision_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_evidence_verification(session, decision_id)
        return serialize_generic_evidence_verification(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/generic-evidence-decisions/{decision_id}/validation-eligibilities")
def create_generic_validation_eligibility(decision_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_validation_eligibility(session, decision_id)
        return serialize_generic_validation_eligibility(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-evidence-decisions/{decision_id}/validation-eligibilities")
def get_generic_validation_eligibilities(decision_id: str, session: Session = Depends(get_session)) -> dict:
    return {"eligibilities": [serialize_generic_validation_eligibility(item) for item in list_generic_validation_eligibilities(session, decision_id)]}


@app.get("/api/v1/generic-validation-eligibilities/{eligibility_id}")
def get_generic_validation_eligibility(eligibility_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericValidationEligibility, eligibility_id)
    if not item:
        raise HTTPException(404, "generic validation eligibility not found")
    return serialize_generic_validation_eligibility(item)


@app.post("/api/v1/generic-validation-eligibilities/{eligibility_id}/promotions")
def create_generic_validation_promotion(eligibility_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = promote_generic_validation(session, eligibility_id, str(payload.get("authorization", "")))
        return serialize_generic_validation_promotion(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-validation-eligibilities/{eligibility_id}/promotion")
def get_generic_validation_promotion_for_eligibility(eligibility_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_generic_validation_promotion(session, eligibility_id)
    if not item:
        raise HTTPException(404, "generic validation promotion not found")
    return serialize_generic_validation_promotion(item)


@app.get("/api/v1/generic-validation-promotions/{promotion_id}")
def get_generic_validation_promotion_by_id(promotion_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericValidationPromotion, promotion_id)
    if not item:
        raise HTTPException(404, "generic validation promotion not found")
    return serialize_generic_validation_promotion(item)


@app.post("/api/v1/strategy-versions/{strategy_version_id}/retirement")
def create_generic_validation_retirement(strategy_version_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = retire_generic_validation(
            session,
            strategy_version_id,
            str(payload.get("authorization", "")),
            str(payload.get("reason", "")),
        )
        contract_ids = list(session.scalars(select(GenericDemoContract.id).where(GenericDemoContract.strategy_version_id == strategy_version_id)))
        compilation_ids = list(session.scalars(select(GenericMt5Compilation.id).where(GenericMt5Compilation.generic_demo_contract_id.in_(contract_ids)))) if contract_ids else []
        publications = list(session.scalars(select(GenericMt5Publication).where(GenericMt5Publication.compilation_id.in_(compilation_ids)))) if compilation_ids else []
        for publication in publications:
            reconcile_generic_mt5_lifecycle(session, publication)
        return serialize_generic_validation_retirement(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/retirement")
def get_generic_validation_retirement_for_strategy(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_generic_validation_retirement(session, strategy_version_id)
    if not item:
        raise HTTPException(404, "generic validation retirement not found")
    return serialize_generic_validation_retirement(item)


@app.get("/api/v1/generic-validation-retirements/{retirement_id}")
def get_generic_validation_retirement_by_id(retirement_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericValidationRetirement, retirement_id)
    if not item:
        raise HTTPException(404, "generic validation retirement not found")
    return serialize_generic_validation_retirement(item)


@app.post("/api/v1/strategy-versions/{strategy_version_id}/lifecycle-verification")
def materialize_generic_validation_lifecycle_verification(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_lifecycle_verification(session, strategy_version_id)
        return serialize_generic_lifecycle_verification(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/lifecycle-verification")
def get_generic_validation_lifecycle_verification(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_generic_lifecycle_verification(session, strategy_version_id)
    if not item:
        raise HTTPException(404, "generic validation lifecycle verification has not been materialized")
    return serialize_generic_lifecycle_verification(item)


@app.get("/api/v1/generic-validation-lifecycle-verifications/{verification_id}")
def get_generic_validation_lifecycle_verification_by_id(verification_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericValidationLifecycleVerification, verification_id)
    if not item:
        raise HTTPException(404, "generic validation lifecycle verification not found")
    return serialize_generic_lifecycle_verification(item)


@app.get("/api/v1/strategy-router/policy")
def get_current_strategy_router_policy() -> dict:
    return current_router_policy()


@app.post("/api/v1/strategy-router/policies")
def create_strategy_router_policy(session: Session = Depends(get_session)) -> dict:
    item, reused = materialize_router_policy(session)
    return serialize_router_policy(item, reused)


@app.get("/api/v1/strategy-router/policies/{policy_id}")
def get_strategy_router_policy(policy_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyRouterPolicy, policy_id)
    if not item:
        raise HTTPException(404, "strategy Router policy not found")
    return serialize_router_policy(item)


@app.post("/api/v1/strategy-versions/{strategy_version_id}/router-eligibilities")
def create_strategy_router_eligibility(strategy_version_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_router_eligibility(session, strategy_version_id, parse_evaluated_at(payload.get("evaluated_at")))
        return serialize_router_eligibility(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/router-eligibilities")
def get_strategy_router_eligibilities(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(StrategyVersion, strategy_version_id):
        raise HTTPException(404, "StrategyVersion not found")
    return {"eligibilities": [serialize_router_eligibility(item) for item in list_router_eligibilities(session, strategy_version_id)]}


@app.get("/api/v1/strategy-router-eligibilities/{eligibility_id}")
def get_strategy_router_eligibility(eligibility_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyRouterEligibility, eligibility_id)
    if not item:
        raise HTTPException(404, "strategy Router eligibility not found")
    return serialize_router_eligibility(item)


@app.post("/api/v1/strategy-router/decisions")
def create_strategy_router_decision(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_router_decision(session, payload.get("eligibility_ids"), parse_evaluated_at(payload.get("evaluated_at")))
        return serialize_router_decision(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-router/decision-contract")
def get_strategy_router_decision_contract() -> dict:
    return router_decision_contract()


@app.get("/api/v1/strategy-router/decisions")
def get_strategy_router_decisions(session: Session = Depends(get_session)) -> dict:
    return {"decisions": [serialize_router_decision(item) for item in list_router_decisions(session)]}


@app.get("/api/v1/strategy-router/decisions/{decision_id}")
def get_strategy_router_decision(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyRouterDecision, decision_id)
    if not item:
        raise HTTPException(404, "strategy Router decision not found")
    return serialize_router_decision(item)


@app.get("/api/v1/strategy-router/parameter-contract")
def get_strategy_router_parameter_contract() -> dict:
    return router_parameter_contract()


@app.post("/api/v1/strategy-router/decisions/{decision_id}/parameters")
def create_strategy_router_decision_parameters(decision_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_router_parameters(
            session,
            decision_id,
            payload.get("broker_metadata_snapshot_id"),
            payload.get("capital_contract_id"),
            payload.get("execution_snapshot"),
        )
        return serialize_router_parameters(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-router/decisions/{decision_id}/parameters")
def get_strategy_router_decision_parameters(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.scalar(select(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == decision_id))
    if not item:
        raise HTTPException(404, "strategy Router decision parameters not found")
    return serialize_router_parameters(item)


@app.get("/api/v1/strategy-router/decision-parameters/{parameters_id}")
def get_strategy_router_decision_parameters_by_id(parameters_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyRouterDecisionParameters, parameters_id)
    if not item:
        raise HTTPException(404, "strategy Router decision parameters not found")
    return serialize_router_parameters(item)


@app.post("/api/v1/strategy-router/decisions/{decision_id}/verification")
def create_strategy_router_verification(decision_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_router_verification(session, decision_id)
        return serialize_router_verification(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-router/decisions/{decision_id}/verification")
def get_strategy_router_verification(decision_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_latest_router_verification(session, decision_id)
    if not item:
        raise HTTPException(404, "strategy Router verification has not been materialized")
    return serialize_router_verification(item)


@app.get("/api/v1/strategy-router-verifications/{verification_id}")
def get_strategy_router_verification_by_id(verification_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyRouterVerification, verification_id)
    if not item:
        raise HTTPException(404, "strategy Router verification not found")
    return serialize_router_verification(item)


@app.get("/api/v1/strategy-router/safety-report")
def get_strategy_router_safety_report(session: Session = Depends(get_session)) -> dict:
    return audit_router_safety(session)


@app.get("/api/v1/generic-demo/eligibility")
def get_generic_demo_eligibility(session: Session = Depends(get_session)) -> dict:
    return generic_demo_eligibility_overview(session)


@app.get("/api/v1/generic-demo/owner-overview")
def get_generic_demo_owner_overview(session: Session = Depends(get_session)) -> dict:
    return build_generic_demo_owner_overview(session)


@app.get("/api/v1/governance-journal/source-contract")
def get_governance_journal_source_contract() -> dict:
    return governance_journal_source_contract()


@app.post("/api/v1/governance-journal/items")
def create_governance_journal_item(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_governance_journal_item(session, payload)
        return serialize_governance_journal_item(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance-journal/items")
def get_governance_journal_items(
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = Query(None),
    source_type: str | None = Query(None),
    evidence_scope: str | None = Query(None),
    evidence_origin: str | None = Query(None),
    strategy_version_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return list_governance_journal_items(
            session,
            limit=limit,
            cursor=cursor,
            source_type=source_type,
            evidence_scope=evidence_scope,
            evidence_origin=evidence_origin,
            strategy_version_id=strategy_version_id,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance-journal/items/{item_id}")
def get_governance_journal_item(item_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceJournalItem, item_id)
    if not item:
        raise HTTPException(404, "governance journal item not found")
    return serialize_governance_journal_item(item)


@app.get("/api/v1/governance-journal/items/{item_id}/verification")
def get_governance_journal_item_verification(item_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceJournalItem, item_id)
    if not item:
        raise HTTPException(404, "governance journal item not found")
    return verify_governance_journal_item(session, item)


@app.get("/api/v1/governance-incidents/policy-contract")
def get_governance_incident_policy_contract() -> dict:
    return governance_incident_policy_contract()


@app.post("/api/v1/governance-incidents")
def create_governance_incident(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_governance_incident(session, payload)
        return serialize_governance_incident(session, item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance-incidents")
def get_governance_incidents(
    limit: int = Query(100, ge=1, le=500),
    severity: str | None = Query(None),
    state: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return list_governance_incidents(session, limit=limit, severity=severity, state=state)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance-incidents/{incident_id}")
def get_governance_incident(incident_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceIncident, incident_id)
    if not item:
        raise HTTPException(404, "governance incident not found")
    return serialize_governance_incident(session, item)


@app.post("/api/v1/governance-incidents/{incident_id}/acknowledgements")
def post_governance_incident_acknowledgement(incident_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceIncident, incident_id)
    if not item:
        raise HTTPException(404, "governance incident not found")
    if set(payload) != {"acknowledgement"}:
        raise HTTPException(422, "acknowledgement request requires exactly acknowledgement")
    try:
        acknowledgement, reused = acknowledge_governance_incident(session, item, payload["acknowledgement"])
        return serialize_governance_incident_ack(acknowledgement, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/governance-incidents/{incident_id}/resolutions")
def post_governance_incident_resolution(incident_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceIncident, incident_id)
    if not item:
        raise HTTPException(404, "governance incident not found")
    try:
        resolution, reused = resolve_governance_incident(session, item, payload)
        return serialize_governance_incident_resolution(resolution, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance-incidents/{incident_id}/verification")
def get_governance_incident_verification(incident_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GovernanceIncident, incident_id)
    if not item:
        raise HTTPException(404, "governance incident not found")
    return verify_governance_incident(session, item)


@app.get("/api/v1/controlled-learning/policy-contract")
def get_controlled_learning_policy_contract() -> dict:
    return learning_proposal_policy_contract()


@app.post("/api/v1/controlled-learning/proposals")
def create_controlled_learning_proposal(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_learning_proposal(session, payload)
        return serialize_learning_proposal(session, item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/controlled-learning/proposals")
def get_controlled_learning_proposals(
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return list_learning_proposals(session, limit=limit, status=status)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/controlled-learning/proposals/{proposal_id}")
def get_controlled_learning_proposal(proposal_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(ControlledLearningProposal, proposal_id)
    if not item:
        raise HTTPException(404, "controlled-learning proposal not found")
    return serialize_learning_proposal(session, item)


@app.post("/api/v1/controlled-learning/proposals/{proposal_id}/confirmations")
def post_controlled_learning_confirmation(proposal_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item = session.get(ControlledLearningProposal, proposal_id)
    if not item:
        raise HTTPException(404, "controlled-learning proposal not found")
    if set(payload) != {"confirmation"}:
        raise HTTPException(422, "confirmation request requires exactly confirmation")
    try:
        confirmation, reused = confirm_learning_proposal(session, item, payload["confirmation"])
        return serialize_learning_confirmation(session, confirmation, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/controlled-learning/proposals/{proposal_id}/verification")
def get_controlled_learning_verification(proposal_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(ControlledLearningProposal, proposal_id)
    if not item:
        raise HTTPException(404, "controlled-learning proposal not found")
    return verify_learning_proposal(session, item)


@app.get("/api/v1/live-readiness/policy-contract")
def get_live_readiness_policy_contract() -> dict:
    return live_readiness_policy_contract()


@app.post("/api/v1/live-readiness/assessments")
def post_live_readiness_assessment(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_live_readiness_assessment(session, payload)
        return serialize_live_readiness_assessment(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/live-readiness/assessments")
def get_live_readiness_assessments(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)) -> dict:
    return {"assessments": [serialize_live_readiness_assessment(item) for item in list_live_readiness_assessments(session, limit=limit)]}


@app.get("/api/v1/live-readiness/assessments/{assessment_id}")
def get_live_readiness_assessment(assessment_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(LiveReadinessAssessment, assessment_id)
    if not item:
        raise HTTPException(404, "LIVE-readiness assessment not found")
    return serialize_live_readiness_assessment(item)


@app.get("/api/v1/live-readiness/assessments/{assessment_id}/verification")
def get_live_readiness_assessment_verification(assessment_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(LiveReadinessAssessment, assessment_id)
    if not item:
        raise HTTPException(404, "LIVE-readiness assessment not found")
    return verify_live_readiness_assessment(session, item)


@app.get("/api/v1/governance/owner-overview")
def get_sprint21_owner_governance_overview(session: Session = Depends(get_session)) -> dict:
    return sprint21_owner_overview(session)


@app.post("/api/v1/governance/sprint21-acceptance-verifications")
def post_sprint21_acceptance_verification(session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_sprint21_acceptance(session)
        return serialize_sprint21_acceptance(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/governance/sprint21-acceptance-verifications/latest")
def get_latest_sprint21_acceptance_verification(session: Session = Depends(get_session)) -> dict:
    item = latest_sprint21_acceptance(session)
    if not item:
        raise HTTPException(404, "Sprint 21 acceptance verification has not been materialized")
    return serialize_sprint21_acceptance(item)


@app.get("/api/v1/governance/sprint21-acceptance-verifications/{verification_id}/verification")
def get_sprint21_acceptance_verification(verification_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(Sprint21AcceptanceVerification, verification_id)
    if not item:
        raise HTTPException(404, "Sprint 21 acceptance verification not found")
    return verify_sprint21_acceptance(session, item)


@app.get("/api/v1/edge-search/policy-contract")
def get_edge_search_policy_contract() -> dict:
    return edge_search_policy_contract()


@app.post("/api/v1/edge-search/campaigns/validate")
def validate_edge_search_campaign(payload: dict, session: Session = Depends(get_session)) -> dict:
    return edge_search_validation_report(session, payload)


@app.post("/api/v1/edge-search/campaigns")
def post_edge_search_campaign(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = create_edge_search_campaign(session, payload)
        return serialize_edge_search_campaign(item, reused=reused, session=session)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/edge-search/campaigns")
def get_edge_search_campaigns(session: Session = Depends(get_session)) -> dict:
    return list_edge_search_campaigns(session)


@app.get("/api/v1/edge-search/campaigns/{campaign_id}")
def get_edge_search_campaign(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    return serialize_edge_search_campaign(item, session=session)


@app.get("/api/v1/edge-search/campaigns/{campaign_id}/trials")
def get_edge_search_campaign_trials(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    return list_edge_search_trials(session, item)


@app.post("/api/v1/edge-search/campaigns/{campaign_id}/execution")
def post_edge_search_execution(campaign_id: str, payload: dict | None = None, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    try:
        return execute_edge_search_campaign(session, item, max_trials=(payload or {}).get("max_trials"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/edge-search/campaigns/{campaign_id}/execution")
def get_edge_search_execution(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    return edge_search_progress(session, item)


@app.get("/api/v1/edge-search/campaigns/{campaign_id}/survivors")
def get_edge_search_survivors(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    return edge_search_survivors(session, item)


@app.get("/api/v1/edge-search/campaigns/{campaign_id}/verification")
def get_edge_search_campaign_verification(campaign_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(EdgeSearchCampaign, campaign_id)
    if not item:
        raise HTTPException(404, "Edge-search campaign not found")
    return verify_edge_search_campaign(session, item)


@app.post("/api/v1/generic-demo-contracts/validate")
def validate_generic_demo_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        return generic_demo_validation_report(session, payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/generic-demo-contracts")
def post_generic_demo_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = create_generic_demo_contract(session, payload)
        return serialize_generic_demo_contract(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-demo-contracts")
def get_generic_demo_contracts(session: Session = Depends(get_session)) -> dict:
    return {"generic_demo_contracts": [serialize_generic_demo_contract(item) for item in list_generic_demo_contracts(session)]}


@app.get("/api/v1/generic-demo-contracts/{contract_id}")
def get_generic_demo_contract(contract_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericDemoContract, contract_id)
    if not item:
        raise HTTPException(404, "generic DEMO contract not found")
    return serialize_generic_demo_contract(item)


@app.get("/api/v1/generic-mt5-adapter-registry")
def get_generic_mt5_adapter_registry() -> dict:
    return generic_mt5_adapter_registry()


@app.post("/api/v1/generic-demo-contracts/{contract_id}/compile/validate")
def validate_generic_mt5_compilation(contract_id: str, session: Session = Depends(get_session)) -> dict:
    return generic_mt5_compilation_report(session, contract_id)


@app.post("/api/v1/generic-demo-contracts/{contract_id}/compile")
def post_generic_mt5_compilation(contract_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = create_generic_mt5_compilation(session, contract_id)
        return serialize_generic_mt5_compilation(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-mt5-compilations")
def get_generic_mt5_compilations(session: Session = Depends(get_session)) -> dict:
    return {"generic_mt5_compilations": [serialize_generic_mt5_compilation(item) for item in list_generic_mt5_compilations(session)]}


@app.get("/api/v1/generic-mt5-compilations/{compilation_id}")
def get_generic_mt5_compilation(compilation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericMt5Compilation, compilation_id)
    if not item:
        raise HTTPException(404, "generic MT5 compilation not found")
    return serialize_generic_mt5_compilation(item)


@app.post("/api/v1/generic-mt5-compilations/{compilation_id}/publication/preflight")
def preflight_generic_mt5_publication(compilation_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    return generic_mt5_publication_preflight(session, compilation_id, payload)


@app.post("/api/v1/generic-mt5-compilations/{compilation_id}/publication")
def post_generic_mt5_publication(compilation_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = publish_generic_mt5_compilation(session, compilation_id, payload)
        return {**serialize_generic_mt5_publication(item), "reused": reused}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-mt5-publications")
def get_generic_mt5_publications(session: Session = Depends(get_session)) -> dict:
    return {"generic_mt5_publications": [serialize_generic_mt5_publication(item) for item in list_generic_mt5_publications(session)]}


@app.get("/api/v1/generic-mt5-publications/{publication_id}")
def get_generic_mt5_publication(publication_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericMt5Publication, publication_id)
    if not item:
        raise HTTPException(404, "generic MT5 publication not found")
    return serialize_generic_mt5_publication(item)


@app.post("/api/v1/generic-mt5-publications/{publication_id}/poll-ack")
def post_generic_mt5_publication_poll_ack(publication_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericMt5Publication, publication_id)
    if not item:
        raise HTTPException(404, "generic MT5 publication not found")
    try:
        return serialize_generic_mt5_publication(poll_generic_mt5_ack(session, item))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/generic-mt5-publications/{publication_id}/block-entries")
def post_generic_mt5_publication_block(publication_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericMt5Publication, publication_id)
    if not item:
        raise HTTPException(404, "generic MT5 publication not found")
    try:
        blocked, reused = block_generic_mt5_entries(session, item, str(payload.get("authorization", "")), str(payload.get("reason_code", "")))
        return {**serialize_generic_mt5_publication(blocked), "reused": reused}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/generic-mt5-publications/{publication_id}/reconcile-lifecycle")
def post_generic_mt5_publication_reconcile(publication_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericMt5Publication, publication_id)
    if not item:
        raise HTTPException(404, "generic MT5 publication not found")
    try:
        reconciled, reused = reconcile_generic_mt5_lifecycle(session, item)
        return {**serialize_generic_mt5_publication(reconciled), "reused": reused}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/generic-mt5-telemetry/sync")
def post_generic_mt5_telemetry_sync(session: Session = Depends(get_session)) -> dict:
    try:
        return sync_generic_mt5_telemetry(session)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-mt5-publications/{publication_id}/telemetry")
def get_generic_mt5_telemetry(publication_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(GenericMt5Publication, publication_id):
        raise HTTPException(404, "generic MT5 publication not found")
    return {"events": [serialize_generic_mt5_telemetry(item) for item in list_generic_mt5_telemetry(session, publication_id)]}


@app.post("/api/v1/generic-mt5-publications/{publication_id}/forward-evidence")
def post_generic_forward_evidence(publication_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_forward_evidence(session, publication_id)
        return serialize_generic_forward_evidence(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-mt5-publications/{publication_id}/forward-evidence")
def get_publication_generic_forward_evidence(publication_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(GenericMt5Publication, publication_id):
        raise HTTPException(404, "generic MT5 publication not found")
    return {"evidence": [serialize_generic_forward_evidence(item) for item in list_generic_forward_evidence(session, publication_id)]}


@app.get("/api/v1/generic-forward-evidence/{evidence_id}")
def get_generic_forward_evidence(evidence_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericForwardEvidence, evidence_id)
    if not item:
        raise HTTPException(404, "generic forward evidence not found")
    return serialize_generic_forward_evidence(item)


@app.post("/api/v1/generic-mt5-publications/{publication_id}/verification")
def post_generic_demo_chain_verification(publication_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_generic_demo_verification(session, publication_id)
        return serialize_generic_demo_verification(item, reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/generic-mt5-publications/{publication_id}/verification")
def get_generic_demo_chain_verification(publication_id: str, session: Session = Depends(get_session)) -> dict:
    if not session.get(GenericMt5Publication, publication_id):
        raise HTTPException(404, "generic MT5 publication not found")
    item = get_latest_generic_demo_verification(session, publication_id)
    if not item:
        raise HTTPException(404, "generic DEMO complete-chain verification has not been materialized")
    return serialize_generic_demo_verification(item)


@app.get("/api/v1/generic-demo-chain-verifications/{verification_id}")
def get_generic_demo_chain_verification_by_id(verification_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(GenericDemoChainVerification, verification_id)
    if not item:
        raise HTTPException(404, "generic DEMO complete-chain verification not found")
    return serialize_generic_demo_verification(item)


@app.post("/api/v1/capital-contracts/validate")
def validate_capital_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        contract, assessment = capital_contract_validation_report(
            session,
            str(payload.get("strategy_version_id", "")),
            str(payload.get("broker_metadata_snapshot_id", "")),
            payload.get("contract"),
        )
        return {"protocol_version": CAPITAL_CONTRACT_PROTOCOL_VERSION, "contract": contract, "broker_assessment": assessment}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/strategy-versions/{strategy_version_id}/capital-contracts")
def confirm_capital_contract(strategy_version_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = create_capital_contract(
            session,
            strategy_version_id,
            str(payload.get("broker_metadata_snapshot_id", "")),
            payload.get("contract"),
        )
        return serialize_capital_contract(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/capital-contracts")
def list_capital_contracts(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(CapitalBrokerContract).where(CapitalBrokerContract.strategy_version_id == strategy_version_id).order_by(CapitalBrokerContract.created_at.desc())).all()
    return {"capital_contracts": [serialize_capital_contract(item) for item in items]}


@app.post("/api/v1/variant-experiment-contracts/validate")
def validate_variant_experiment_contract(payload: dict, session: Session = Depends(get_session)) -> dict:
    contract, assessment = variant_experiment_validation_report(
        session,
        str(payload.get("strategy_version_id", "")),
        str(payload.get("dataset_id", "")),
        payload.get("contract"),
    )
    return {
        "protocol_version": VARIANT_CONTRACT_PROTOCOL_VERSION,
        "contract": contract,
        "assessment": assessment,
    }


@app.post("/api/v1/strategy-versions/{strategy_version_id}/variant-experiment-contracts")
def confirm_variant_experiment_contract(strategy_version_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = create_variant_experiment_contract(
            session,
            strategy_version_id,
            str(payload.get("dataset_id", "")),
            payload.get("contract"),
        )
        return serialize_variant_experiment_contract(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/variant-experiment-contracts")
def list_variant_experiment_contracts(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(
        select(VariantExperimentContract)
        .where(VariantExperimentContract.strategy_version_id == strategy_version_id)
        .order_by(VariantExperimentContract.created_at.desc())
    ).all()
    return {"variant_experiment_contracts": [serialize_variant_experiment_contract(item) for item in items]}


@app.get("/api/v1/variant-experiment-contracts")
def list_all_variant_experiment_contracts(session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(VariantExperimentContract).order_by(VariantExperimentContract.created_at.desc())).all()
    return {"variant_experiment_contracts": [serialize_variant_experiment_contract(item) for item in items]}


@app.get("/api/v1/variant-experiment-contracts/{contract_id}")
def get_variant_experiment_contract(contract_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(VariantExperimentContract, contract_id)
    if not item:
        raise HTTPException(404, "variant experiment contract not found")
    return serialize_variant_experiment_contract(item)


@app.post("/api/v1/variant-experiment-contracts/{contract_id}/train-runs")
def create_variant_train_run(contract_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_variant_train_evaluation(session, contract_id)
        return serialize_variant_train_run(item, reused=reused)
    except TrainRunConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/variant-experiment-contracts/{contract_id}/train-runs")
def list_variant_train_runs(contract_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(
        select(VariantTrainRun)
        .where(VariantTrainRun.experiment_contract_id == contract_id)
        .order_by(VariantTrainRun.created_at.desc())
    ).all()
    return {"train_runs": [serialize_variant_train_run(item) for item in items]}


@app.get("/api/v1/variant-train-runs/{run_id}")
def get_variant_train_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(VariantTrainRun, run_id)
    if not item:
        raise HTTPException(404, "variant train run not found")
    return serialize_variant_train_run(item)


@app.post("/api/v1/variant-train-runs/{train_run_id}/holdout-runs")
def create_variant_holdout_run(train_run_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, lock, reused = run_variant_holdout_evaluation(session, train_run_id)
        return serialize_variant_holdout_run(item, lock, reused=reused)
    except HoldoutRunConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/variant-train-runs/{train_run_id}/holdout-runs")
def list_variant_holdout_runs(train_run_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(VariantHoldoutRun).where(VariantHoldoutRun.train_run_id == train_run_id).order_by(VariantHoldoutRun.created_at.desc())).all()
    return {"holdout_runs": [serialize_variant_holdout_run(item, get_variant_selection(session, item)) for item in items]}


@app.get("/api/v1/variant-holdout-runs/{run_id}")
def get_variant_holdout_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(VariantHoldoutRun, run_id)
    if not item:
        raise HTTPException(404, "variant holdout run not found")
    return serialize_variant_holdout_run(item, get_variant_selection(session, item))


@app.get("/api/v1/variant-holdout-runs/{run_id}/selection")
def get_variant_holdout_selection(run_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(VariantHoldoutRun, run_id)
    if not item:
        raise HTTPException(404, "variant holdout run not found")
    lock = get_variant_selection(session, item)
    if not lock:
        raise HTTPException(404, "variant selection lock not found")
    return serialize_variant_selection(lock)


@app.post("/api/v1/variant-selection-locks/{selection_lock_id}/confirm-final-oos")
def confirm_variant_selection_final_oos(selection_lock_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = confirm_variant_revision(session, selection_lock_id, str(payload.get("acknowledgement", "")))
        return serialize_variant_revision_confirmation(item, reused=reused)
    except RevisionRunConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/variant-selection-locks/{selection_lock_id}/revision-confirmation")
def get_variant_revision_confirmation_for_lock(selection_lock_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.scalar(select(VariantRevisionConfirmation).where(VariantRevisionConfirmation.selection_lock_id == selection_lock_id))
    if not item:
        raise HTTPException(404, "variant revision confirmation not found")
    return serialize_variant_revision_confirmation(item)


@app.get("/api/v1/variant-revision-confirmations/{confirmation_id}")
def get_variant_revision_confirmation(confirmation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(VariantRevisionConfirmation, confirmation_id)
    if not item:
        raise HTTPException(404, "variant revision confirmation not found")
    return serialize_variant_revision_confirmation(item)


@app.get("/api/v1/variant-experiment-contracts/{contract_id}/verification")
def get_variant_experiment_acceptance_verification(contract_id: str, session: Session = Depends(get_session)) -> dict:
    experiment = session.get(VariantExperimentContract, contract_id)
    if not experiment:
        raise HTTPException(404, "variant experiment contract not found")
    item = get_variant_experiment_verification(session, experiment)
    if not item:
        raise HTTPException(404, "variant experiment verification has not been materialized")
    return serialize_variant_experiment_verification(item)


@app.post("/api/v1/variant-experiment-contracts/{contract_id}/verification")
def materialize_variant_experiment_acceptance_verification(contract_id: str, session: Session = Depends(get_session)) -> dict:
    experiment = session.get(VariantExperimentContract, contract_id)
    if not experiment:
        raise HTTPException(404, "variant experiment contract not found")
    try:
        item, reused = materialize_variant_experiment_verification(session, experiment)
        return serialize_variant_experiment_verification(item, reused=reused)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/v1/capital-contracts/{capital_contract_id}/fixed-lot-simulations")
def create_fixed_lot_capital_simulation(capital_contract_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_fixed_lot_capital_simulation(
            session,
            capital_contract_id,
            str(payload.get("source_full_validation_id", "")),
        )
        return serialize_fixed_lot_capital_simulation(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/capital-contracts/{capital_contract_id}/fixed-lot-simulations")
def list_fixed_lot_capital_simulations(capital_contract_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(FixedLotCapitalSimulation).where(FixedLotCapitalSimulation.capital_contract_id == capital_contract_id).order_by(FixedLotCapitalSimulation.created_at.desc())).all()
    return {"simulations": [serialize_fixed_lot_capital_simulation(item) for item in items]}


@app.get("/api/v1/fixed-lot-capital-simulations/{simulation_id}")
def get_fixed_lot_capital_simulation(simulation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(FixedLotCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "fixed-lot capital simulation not found")
    return serialize_fixed_lot_capital_simulation(item)


@app.get("/api/v1/fixed-lot-capital-simulations/{simulation_id}/equity-path")
def get_fixed_lot_equity_path(simulation_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)) -> dict:
    item = session.get(FixedLotCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "fixed-lot capital simulation not found")
    points = session.scalars(select(FixedLotEquityPoint).where(FixedLotEquityPoint.simulation_id == item.id, FixedLotEquityPoint.sequence >= offset).order_by(FixedLotEquityPoint.sequence).limit(limit)).all()
    total = int((item.result or {}).get("metrics", {}).get("completed_trades", 0)) + 1
    return {"simulation_id": item.id, "offset": offset, "limit": limit, "total": total, "equity_path": [point.payload for point in points]}


@app.post("/api/v1/capital-contracts/{capital_contract_id}/fractional-risk-simulations")
def create_fractional_risk_simulation(capital_contract_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_fractional_risk_simulation(session, capital_contract_id, str(payload.get("source_full_validation_id", "")))
        return serialize_fractional_risk_simulation(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/capital-contracts/{capital_contract_id}/fractional-risk-simulations")
def list_fractional_risk_simulations(capital_contract_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(FractionalRiskCapitalSimulation).where(FractionalRiskCapitalSimulation.capital_contract_id == capital_contract_id).order_by(FractionalRiskCapitalSimulation.created_at.desc())).all()
    return {"simulations": [serialize_fractional_risk_simulation(item) for item in items]}


@app.get("/api/v1/fractional-risk-capital-simulations/{simulation_id}")
def get_fractional_risk_simulation(simulation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(FractionalRiskCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "fractional-risk capital simulation not found")
    return serialize_fractional_risk_simulation(item)


@app.get("/api/v1/fractional-risk-capital-simulations/{simulation_id}/equity-path")
def get_fractional_risk_equity_path(simulation_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)) -> dict:
    item = session.get(FractionalRiskCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "fractional-risk capital simulation not found")
    points = session.scalars(select(FractionalRiskEquityPoint).where(FractionalRiskEquityPoint.simulation_id == item.id, FractionalRiskEquityPoint.sequence >= offset).order_by(FractionalRiskEquityPoint.sequence).limit(limit)).all()
    total = int((item.result or {}).get("metrics", {}).get("equity_path_points", 0))
    return {"simulation_id": item.id, "offset": offset, "limit": limit, "total": total, "equity_path": [point.payload for point in points]}


@app.post("/api/v1/capital-contracts/{capital_contract_id}/constrained-simulations")
def create_constrained_capital_simulation(capital_contract_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = run_constrained_capital_simulation(session, capital_contract_id, str(payload.get("source_full_validation_id", "")))
        return serialize_constrained_capital_simulation(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/capital-contracts/{capital_contract_id}/constrained-simulations")
def list_constrained_capital_simulations(capital_contract_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(ConstrainedCapitalSimulation).where(ConstrainedCapitalSimulation.capital_contract_id == capital_contract_id).order_by(ConstrainedCapitalSimulation.created_at.desc())).all()
    return {"simulations": [serialize_constrained_capital_simulation(item) for item in items]}


@app.get("/api/v1/constrained-capital-simulations/{simulation_id}")
def get_constrained_capital_simulation(simulation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(ConstrainedCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "constrained capital simulation not found")
    return serialize_constrained_capital_simulation(item)


@app.get("/api/v1/constrained-capital-simulations/{simulation_id}/capital-path")
def get_constrained_capital_path(simulation_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), session: Session = Depends(get_session)) -> dict:
    item = session.get(ConstrainedCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "constrained capital simulation not found")
    points = session.scalars(select(ConstrainedCapitalPoint).where(ConstrainedCapitalPoint.simulation_id == item.id, ConstrainedCapitalPoint.sequence >= offset).order_by(ConstrainedCapitalPoint.sequence).limit(limit)).all()
    total = int((item.result or {}).get("metrics", {}).get("capital_path_points", 0))
    return {"simulation_id": item.id, "offset": offset, "limit": limit, "total": total, "capital_path": [point.payload for point in points]}


@app.get("/api/v1/constrained-capital-simulations/{simulation_id}/verification")
def verify_constrained_capital_simulation(simulation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(ConstrainedCapitalSimulation, simulation_id)
    if not item:
        raise HTTPException(404, "constrained capital simulation not found")
    artifact = get_materialized_verification(session, item)
    if not artifact: raise HTTPException(404, "full-history verification has not been materialized")
    return serialize_verification(artifact)


@app.post("/api/v1/constrained-capital-simulations/{simulation_id}/verification")
def materialize_constrained_capital_verification(simulation_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(ConstrainedCapitalSimulation, simulation_id)
    if not item: raise HTTPException(404, "constrained capital simulation not found")
    try:
        artifact, reused = materialize_verification(session, item)
        return serialize_verification(artifact, reused=reused)
    except ValueError as error: raise HTTPException(409, str(error)) from error


def serialize_oos_validation(item: OosValidation, *, reused: bool | None = None) -> dict:
    payload = {"id": item.id, "fingerprint": item.fingerprint, "strategy_version_id": item.strategy_version_id, "dataset_id": item.dataset_id, "protocol": item.protocol, "result": item.result, "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        payload["reused"] = reused
    return payload


@app.get("/api/v1/backtests/{backtest_id}")
def get_backtest(backtest_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(BacktestRun, backtest_id)
    if not run:
        raise HTTPException(404, "backtest run not found")
    return serialize_backtest(run)


@app.get("/api/v1/backtests/{backtest_id}/trades")
def get_backtest_trades(backtest_id: str, limit: int = Query(100, ge=1, le=100), session: Session = Depends(get_session)) -> dict:
    run = session.get(BacktestRun, backtest_id)
    if not run:
        raise HTTPException(404, "backtest run not found")
    return {"backtest_id": run.id, "trades": run.trades[:limit], "total": len(run.trades)}


@app.post("/api/v1/broker-metadata/import")
def import_broker_metadata(session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = import_snapshot(session)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"id": item.id, "fingerprint": item.fingerprint, "source": item.source, "broker_symbol": item.broker_symbol, "canonical_symbol": item.canonical_symbol, "collected_at": item.collected_at, "metadata": item.snapshot, "reused": reused}


@app.get("/api/v1/broker-metadata/latest")
def latest_broker_metadata(session: Session = Depends(get_session)) -> dict:
    item = session.scalar(select(BrokerMetadataSnapshot).order_by(BrokerMetadataSnapshot.created_at.desc()))
    if not item: raise HTTPException(404, "No imported MT5 broker metadata snapshot")
    return {"id": item.id, "fingerprint": item.fingerprint, "source": item.source, "broker_symbol": item.broker_symbol, "canonical_symbol": item.canonical_symbol, "collected_at": item.collected_at, "metadata": item.snapshot}

@app.post("/api/v1/broker-metadata/order-calc-profit-validation/import")
def import_order_calc_profit_validation(session: Session = Depends(get_session)) -> dict:
    try: return import_order_calc_validation(session)
    except ValueError as error: raise HTTPException(422, str(error)) from error

@app.post("/api/v1/full-validations/{full_id}/financial-evidence")
def create_financial_evidence(full_id:str, session:Session=Depends(get_session))->dict:
    try:
        item,reused=materialize_financial(session,full_id)
        return {"id":item.id,"reused":reused,"volume":item.volume,"currency":item.currency,"parity_status":item.parity_status,"metrics":item.metrics}
    except ValueError as error: raise HTTPException(422,str(error)) from error

@app.get("/api/v1/full-validations/{full_id}/financial-evidence")
def get_financial_evidence(full_id:str, session:Session=Depends(get_session))->dict:
    item=session.scalar(select(DerivedFinancialEvidence).where(DerivedFinancialEvidence.source_full_validation_id==full_id).order_by(DerivedFinancialEvidence.created_at.desc()))
    if not item:return {"status":"NOT_GENERATED"}
    return {"status":"AVAILABLE","id":item.id,"volume":item.volume,"currency":item.currency,"parity_status":item.parity_status,"metrics":item.metrics,"created_at":item.created_at.isoformat()+"Z"}


def serialize_supplemental_validation(item: SupplementalHistoricalValidation, include_trades: bool = False) -> dict:
    payload = {"id": item.id, "strategy_version_id": item.strategy_version_id, "original_backtest_run_id": item.original_backtest_run_id, "dataset_id": item.dataset_id, "fingerprint": item.fingerprint, "status": item.status, "configuration": item.configuration, "result": item.result, "created_at": item.created_at.isoformat() + "Z"}
    if include_trades:
        payload["trades"] = item.trades
    return payload


@app.post("/api/v1/strategy-versions/{strategy_version_id}/supplemental-historical-validation")
def create_supplemental_historical_validation(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy:
        raise HTTPException(404, "strategy version not found")
    try:
        item, reused = run_supplemental_full_validation(session, strategy)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {**serialize_supplemental_validation(item, include_trades=True), "reused": reused}


@app.get("/api/v1/strategy-versions/{strategy_version_id}/supplemental-historical-validations")
def list_supplemental_historical_validations(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(SupplementalHistoricalValidation).where(SupplementalHistoricalValidation.strategy_version_id == strategy_version_id).order_by(SupplementalHistoricalValidation.created_at.desc())).all()
    return {"validations": [serialize_supplemental_validation(item) for item in items]}


@app.get("/api/v1/strategy-versions")
def list_strategy_versions(session: Session = Depends(get_session)) -> dict:
    items = session.scalars(select(StrategyVersion).order_by(StrategyVersion.created_at.desc())).all()
    return {"strategy_versions": [serialize_strategy(item) for item in items]}

@app.post("/api/v1/strategy-candidates")
def create_strategy_candidate_route(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item=create_strategy_candidate(session,payload); return {"id":item.id,"name":item.name,"source":item.source,"provenance":item.provenance,"status":item.status}
    except ValueError as error: raise HTTPException(422,str(error)) from error

@app.get("/api/v1/strategy-candidates")
def list_strategy_candidates(session: Session = Depends(get_session)) -> dict:
    items=session.scalars(select(StrategyCandidate).order_by(StrategyCandidate.created_at.desc())).all(); return {"strategy_candidates":[{"id":item.id,"name":item.name,"source":item.source,"provenance":item.provenance,"status":item.status} for item in items]}

@app.get("/api/v1/strategy-candidates/{candidate_id}")
def get_strategy_candidate(candidate_id:str,session:Session=Depends(get_session))->dict:
    item=session.get(StrategyCandidate,candidate_id)
    if not item: raise HTTPException(404,"strategy candidate not found")
    return {"id":item.id,"name":item.name,"source":item.source,"provenance":item.provenance,"status":item.status}

@app.put("/api/v1/strategy-candidates/{candidate_id}")
def update_strategy_candidate_route(candidate_id:str,payload:dict,session:Session=Depends(get_session))->dict:
    item=session.get(StrategyCandidate,candidate_id)
    if not item: raise HTTPException(404,"strategy candidate not found")
    try:
        item=update_strategy_candidate(session,item,payload); return {"id":item.id,"name":item.name,"source":item.source,"provenance":item.provenance,"status":item.status}
    except ValueError as error: raise HTTPException(422,str(error)) from error

@app.post("/api/v1/strategy-candidates/validate")
def validate_strategy_candidate(payload:dict)->dict:
    return validate_strategy_contract(payload.get("strategy_contract"))


@app.get("/api/v1/strategy-capabilities")
def get_strategy_capabilities() -> dict:
    return strategy_capability_registry()


@app.post("/api/v1/strategy-contract-assessments")
def create_strategy_contract_assessment(payload: dict, session: Session = Depends(get_session)) -> dict:
    item, reused = materialize_capability_assessment(session, payload.get("strategy_contract"))
    return serialize_capability_assessment(item, reused=reused)


@app.get("/api/v1/strategy-contract-assessments/{assessment_id}")
def get_strategy_contract_assessment(assessment_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyContractAssessment, assessment_id)
    if not item:
        raise HTTPException(404, "strategy contract assessment not found")
    return serialize_capability_assessment(item)


@app.post("/api/v1/strategy-contract-assessments/{assessment_id}/compile")
def compile_strategy_contract_assessment(assessment_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyContractAssessment, assessment_id)
    if not item:
        raise HTTPException(404, "strategy contract assessment not found")
    try:
        compiled = compile_strategy_contract(item.normalized_contract)
        if compiled["assessment_fingerprint"] != item.fingerprint:
            raise ValueError("assessment no longer matches the active registry")
        return compiled
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/strategy-contract-assessments/{assessment_id}/confirm")
def confirm_strategy_contract_assessment(assessment_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = confirm_capability_assessment(session, assessment_id, str(payload.get("strategy_candidate_id", "")), payload.get("strategy_key"))
        return {**serialize_strategy(item), "reused": reused}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/strategy-versions/{strategy_version_id}/backtests/{backtest_id}/verification")
def get_strategy_evaluator_acceptance_verification(strategy_version_id: str, backtest_id: str, session: Session = Depends(get_session)) -> dict:
    item = get_strategy_evaluator_verification(session, strategy_version_id, backtest_id)
    if not item: raise HTTPException(404, "strategy evaluator verification has not been materialized")
    return serialize_strategy_evaluator_verification(item)


@app.post("/api/v1/strategy-versions/{strategy_version_id}/backtests/{backtest_id}/verification")
def materialize_strategy_evaluator_acceptance_verification(strategy_version_id: str, backtest_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        item, reused = materialize_strategy_evaluator_verification(session, strategy_version_id, backtest_id)
        return serialize_strategy_evaluator_verification(item, reused=reused)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

@app.post("/api/v1/strategy-versions/confirm")
def confirm_strategy_version_route(payload: dict, session: Session = Depends(get_session)) -> dict:
    try: return serialize_strategy(confirm_strategy_version(session,payload))
    except ValueError as error: raise HTTPException(422,str(error)) from error

@app.post("/api/v1/strategy-versions/{strategy_version_id}/revision")
def create_strategy_revision(strategy_version_id:str,session:Session=Depends(get_session))->dict:
    item=session.get(StrategyVersion,strategy_version_id)
    if not item: raise HTTPException(404,"strategy version not found")
    try:
        candidate=revision(session,item); return {"id":candidate.id,"name":candidate.name,"source":candidate.source,"provenance":candidate.provenance,"status":candidate.status}
    except ValueError as error: raise HTTPException(422,str(error)) from error


@app.post("/api/v1/strategy-versions")
def create_strategy_version(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        return serialize_strategy(create_candidate(session, payload))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/strategy-versions/{strategy_version_id}/approve")
def approve_strategy_version(strategy_version_id: str, session: Session = Depends(get_session)) -> dict:
    item = session.get(StrategyVersion, strategy_version_id)
    if not item:
        raise HTTPException(404, "strategy version not found")
    try:
        return serialize_strategy(approve_candidate(session, item))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/deployments")
def list_deployments(session: Session = Depends(get_session)) -> dict:
    return {"deployments": [serialize_deployment(item) for item in session.scalars(select(Deployment).order_by(Deployment.created_at.desc())).all()]}


@app.post("/api/v1/deployments/preflight")
def deployment_preflight(payload: dict, session: Session = Depends(get_session)) -> dict:
    strategy, path, errors = preflight(session, str(payload.get("strategy_version_id", "")), str(payload.get("target_environment", "")), str(payload.get("target_reference", "")), str(payload.get("broker_symbol", "")).strip())
    root, adapter_errors = adapter_preflight()
    return {"status": "READY_TO_DEPLOY" if not errors else "PREFLIGHT_FAILED", "errors": errors, "adapter": {"host_mount_visible_at_container_path": str(root), "safe_write_atomic_replace_readback": "PASS" if not adapter_errors else "FAILED", "errors": adapter_errors}, "strategy_version_id": strategy.id if strategy else None, "config_path": str(path), "target_environment": payload.get("target_environment")}


@app.post("/api/v1/deployments")
def deploy(payload: dict, session: Session = Depends(get_session)) -> dict:
    try: return serialize_deployment(create_deployment(session, payload))
    except ValueError as error: raise HTTPException(422, str(error)) from error


@app.post("/api/v1/deployments/{deployment_id}/poll-ack")
def deployment_poll_ack(deployment_id: str, session: Session = Depends(get_session)) -> dict:
    item=session.get(Deployment,deployment_id)
    if not item: raise HTTPException(404,"deployment not found")
    try: return serialize_deployment(poll_ack(session,item))
    except ValueError as error: raise HTTPException(422,str(error)) from error


@app.post("/api/v1/deployments/{deployment_id}/rollback")
def deployment_rollback(deployment_id: str, session: Session = Depends(get_session)) -> dict:
    item=session.get(Deployment,deployment_id)
    if not item: raise HTTPException(404,"deployment not found")
    try: return serialize_deployment(rollback(session,item))
    except ValueError as error: raise HTTPException(422,str(error)) from error


@app.get("/api/v1/cockpit")
def cockpit(session: Session = Depends(get_session)) -> dict:
    return telemetry_snapshot(session)


@app.get("/api/v1/journal")
def journal(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)) -> dict:
    adapter = sync_telemetry(session)
    events = session.scalars(select(JournalEvent).order_by(JournalEvent.observed_at.desc()).limit(limit)).all()
    return {"adapter": adapter, "events": [serialize_journal_event(event) for event in events]}

@app.get("/api/v1/demo-validation")
def demo_validation(session: Session = Depends(get_session)) -> dict:
    sync_telemetry(session)
    active=session.scalar(select(Deployment).where(Deployment.status=="DEMO_ACTIVE").order_by(Deployment.acknowledged_at.desc()))
    return demo_readiness(session,active)

@app.get("/api/v1/demo-validation/trades")
def demo_validation_trades(session: Session = Depends(get_session)) -> dict:
    active=session.scalar(select(Deployment).where(Deployment.status=="DEMO_ACTIVE").order_by(Deployment.acknowledged_at.desc()))
    report=demo_readiness(session,active)
    return {"status":report["status"],"trades":report["trades"],"performance":report["performance"]}

@app.get("/api/v1/discovery")
def pattern_discovery(symbol:str=Query("XAUUSD"),timeframe:str=Query("M15"),session:Session=Depends(get_session)) -> dict:
    try:return discover(session,symbol.upper(),timeframe.upper())
    except ValueError as error:raise HTTPException(422,str(error)) from error

@app.get("/api/v1/similarity")
def historical_similarity(timestamp:str=Query(...),symbol:str=Query("XAUUSD"),timeframe:str=Query("M15"),top_n:int=Query(8,ge=1,le=20),session:Session=Depends(get_session))->dict:
    try:return similar(session,symbol.upper(),timeframe.upper(),timestamp,top_n)
    except ValueError as error:raise HTTPException(422,str(error)) from error

@app.get("/api/v1/mt5-historical/status")
def mt5_historical_export_status(session:Session=Depends(get_session))->dict: return mt5_historical_status(session)

@app.post("/api/v1/mt5-historical/sync")
def mt5_historical_sync(session:Session=Depends(get_session))->dict:
    if not _historical_scheduler_lock.acquire(blocking=False):
        raise HTTPException(409,"Historical sync is already running")
    try:return process_mt5_historical(session,trigger="MANUAL",force=True)
    except ValueError as error:raise HTTPException(422,str(error)) from error
    finally:_historical_scheduler_lock.release()

@app.get("/api/v1/mt5-historical/bootstrap-status")
def mt5_historical_bootstrap_status()->dict: return mt5_bootstrap_status()

@app.post("/api/v1/mt5-historical/bootstrap")
def mt5_historical_bootstrap(session:Session=Depends(get_session))->dict:
    try:return bootstrap_mt5_historical(session)
    except ValueError as error:raise HTTPException(422,str(error)) from error
