from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .database import Base, SessionLocal, engine, get_session
from .market_data import TIMEFRAMES, import_csv, read_bars, serialize_dataset
from .models import AIInteraction, BacktestRun, Dataset, DatasetBarAsset, Deployment, JournalEvent, ResearchHypothesis, ResearchRun, ResearchRuleDefinition, StrategyVersion, SupplementalHistoricalValidation, BrokerMetadataSnapshot
from .hypotheses import parse_prompt, validate_definition
from .registries import assess
from .research_execution import run_hypothesis
from .backtesting import run_backtest, run_supplemental_full_validation
from .strategies import approve_candidate, create_candidate, serialize_strategy
from .deployments import adapter_preflight, create_deployment, poll_ack, preflight, rollback, serialize as serialize_deployment
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


@app.on_event("startup")
def startup() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
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
    payload = {"id": item.id, "dataset_id": item.dataset_id, "fingerprint": item.fingerprint, "status": item.status, "configuration": item.configuration, "result": item.result, "created_at": item.created_at.isoformat() + "Z"}
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
