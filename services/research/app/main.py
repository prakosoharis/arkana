from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_session
from .market_data import TIMEFRAMES, import_csv, read_bars, serialize_dataset
from .models import BacktestRun, Dataset, DatasetBarAsset, ResearchHypothesis, ResearchRun, StrategyVersion
from .hypotheses import parse_prompt, validate_definition
from .registries import assess
from .research_execution import run_hypothesis
from .backtesting import run_backtest
from .strategies import approve_candidate, create_candidate, serialize_strategy
from .settings import DATA_ROOT, MAX_BARS_PER_REQUEST


app = FastAPI(title="ARKANA Research Service", version="0.1.0")
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
    result = read_bars(asset, start=start, end=end, limit=limit)
    if len(result) > limit:
        raise HTTPException(422, f"Requested range exceeds limit of {limit} bars; narrow the range")
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
