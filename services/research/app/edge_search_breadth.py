"""ARK-S25-01 regime breadth for a pre-registered campaign's survivors.

The accepted gate refuses a strategy whose positive PnL is concentrated in one
year or one regime. Both campaigns so far spent an irreversible budget unit on
their highest-profit-factor survivor and were refused on exactly that check,
at regime concentration 0.8039 and 0.8537.

Breadth is measurable **before** a unit is spent, but only on the partitions
the search is allowed to read. This module computes it over train and holdout
and is structurally incapable of reading final OOS: `READABLE_SPLITS` is the
only source of bounds it consults, and a test asserts the forbidden name
appears nowhere in the module.

It changes no threshold. 0.50 is the accepted gate's own ceiling, applied
earlier and to different data, and a low concentration here is a prediction
about the gate rather than a substitute for it.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .edge_search import build_contract
from .models import Dataset, EdgeSearchCampaign, EdgeSearchTrialBreadth, EdgeSearchTrial
from .oos_validation import PROTOCOL as OOS_PROTOCOL, _calibrate_regime, _evaluate, generic_replay_plan
from .strategy_contracts import canonical_json

BREADTH_VERSION = "EDGE_SEARCH_REGIME_BREADTH_V1"

# The only partitions this module may read. Final OOS costs an irreversible
# budget unit and is reachable solely through an authorized ARK-S22-03 opening.
READABLE_SPLITS = ("train", "holdout")

# Not a new threshold. This is the accepted gate's
# `maximum_single_year_or_regime_pnl_concentration`, read from the same policy
# the gate reads, so the two can never drift apart.
CEILING = float(OOS_PROTOCOL["gate_policy"]["maximum_single_year_or_regime_pnl_concentration"])


def _concentration(buckets: dict[str, float]) -> dict[str, Any]:
    """The gate's own definition: the largest positive bucket's share of all
    positive buckets. Losing buckets do not dilute a concentration."""
    positive = {name: value for name, value in buckets.items() if value > 0}
    total = sum(positive.values())
    if total <= 0:
        return {"concentration": None, "reason": "NO_POSITIVE_PNL",
                "profitable_buckets": 0, "buckets": buckets}
    return {"concentration": round(max(positive.values()) / total, 6),
            "reason": None, "profitable_buckets": len(positive),
            "bucket_count": len(buckets), "buckets": {k: round(v, 6) for k, v in sorted(buckets.items())}}


def measure(session: Session, campaign: EdgeSearchCampaign, trial: EdgeSearchTrial,
            *, chunk_size: int = 10_000) -> dict[str, Any]:
    """Replay one survivor over the readable partitions and describe its spread."""
    if trial.campaign_id != campaign.id:
        raise ValueError("the trial does not belong to this campaign")
    dataset = session.get(Dataset, campaign.dataset_id)
    if not dataset:
        raise ValueError("the campaign dataset is no longer registered")
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None)
    if not asset:
        raise ValueError("the campaign dataset has no registered M1 asset")

    # The partitions are the ones the trial itself recorded, never recomputed.
    #
    # A registered dataset grows: an MT5 sync appended 11,281 bars after this
    # campaign was frozen, which moved `split_bounds` by 6,814 rows.  Recomputing
    # would have measured a holdout window the campaign never ran on, and would
    # have done so silently.  The recorded index ranges are exact lineage.
    permitted = {}
    for name in READABLE_SPLITS:
        split = (trial.result or {}).get("splits", {}).get(name) or {}
        span = split.get("index_range") or {}
        if "start_inclusive" not in span or "end_exclusive" not in span:
            raise ValueError(f"the trial did not record an index range for {name}; breadth needs exact lineage")
        permitted[name] = (int(span["start_inclusive"]), int(span["end_exclusive"]))
    drifted = dataset.fingerprint != campaign.dataset_fingerprint
    calibration = _calibrate_regime(asset, permitted["train"][1], chunk_size=chunk_size)
    config, artifact, factory = generic_replay_plan(dataset, build_contract(trial.parameters), chunk_size=chunk_size)

    regime: dict[str, float] = {}
    year: dict[str, float] = {}
    for name in READABLE_SPLITS:
        start, end = permitted[name]
        split = _evaluate(asset, start, end, config, chunk_size=chunk_size,
                          regime_thresholds=calibration["thresholds"], evaluator_factory=factory)
        # Growth appends, so old indices should still address the same bars.
        # "Should" is not evidence: the trial recorded the timestamps those
        # indices produced, so continuity is checked rather than assumed.
        recorded = (trial.result["splits"][name].get("timestamp_range") or {})
        if recorded and split.get("timestamp_range") != recorded:
            raise ValueError(
                f"the {name} partition no longer yields the timestamps the trial recorded; "
                "the registered asset changed beneath the frozen grid")
        for bucket, value in split["breakdown"]["regime_net_pnl"].items():
            regime[bucket] = regime.get(bucket, 0.0) + float(value)
        for bucket, value in split["breakdown"]["year_net_pnl"].items():
            year[bucket] = year.get(bucket, 0.0) + float(value)

    regime_result, year_result = _concentration(regime), _concentration(year)
    observed = regime_result["concentration"]
    return {
        "breadth_version": BREADTH_VERSION,
        "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
        "trial_id": trial.id, "trial_index": trial.trial_index,
        "contract_fingerprint": trial.contract_fingerprint,
        "parameters": trial.parameters,
        "splits_read": list(READABLE_SPLITS),
        "index_ranges": {name: {"start_inclusive": a, "end_exclusive": b} for name, (a, b) in permitted.items()},
        "dataset_fingerprint_at_pre_registration": campaign.dataset_fingerprint,
        "dataset_fingerprint_now": dataset.fingerprint,
        "dataset_grew_since_pre_registration": drifted,
        "final_oos_read": False,
        "regime_calibration_status": calibration["status"],
        "regime": regime_result, "year": year_result,
        "ceiling": CEILING,
        "within_ceiling": observed is not None and observed <= CEILING,
        "evaluator": {"capability": artifact.get("evaluator_capability_id"),
                      "version": artifact.get("evaluator_version")},
        "warning": (
            "Breadth is measured on train and holdout only. The accepted gate measures concentration over "
            "holdout and final OOS, so this is a prediction about that check and never a substitute for it. "
            "It relaxes no threshold and grants no VALIDATED, DEMO, LIVE, order, or trade authority."
        ),
    }


def materialize(session: Session, campaign: EdgeSearchCampaign, trial: EdgeSearchTrial,
                *, chunk_size: int = 10_000) -> tuple[EdgeSearchTrialBreadth, bool]:
    result = measure(session, campaign, trial, chunk_size=chunk_size)
    fingerprint = sha256(canonical_json(result).encode()).hexdigest()
    existing = session.scalar(select(EdgeSearchTrialBreadth).where(EdgeSearchTrialBreadth.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = EdgeSearchTrialBreadth(
        campaign_id=campaign.id, trial_id=trial.id, fingerprint=fingerprint,
        breadth_version=BREADTH_VERSION,
        regime_concentration=result["regime"]["concentration"],
        year_concentration=result["year"]["concentration"],
        within_ceiling=result["within_ceiling"], result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchTrialBreadth).where(EdgeSearchTrialBreadth.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("breadth evidence conflicts with a concurrent immutable write")


def recorded(session: Session, campaign: EdgeSearchCampaign) -> dict[str, EdgeSearchTrialBreadth]:
    return {item.trial_id: item for item in session.scalars(
        select(EdgeSearchTrialBreadth).where(EdgeSearchTrialBreadth.campaign_id == campaign.id))}


def selection(session: Session, campaign: EdgeSearchCampaign, limit: int = 10) -> dict[str, Any]:
    """The ARK-S25-00 rule, applied to whatever breadth evidence exists.

    Among survivors within the gate's own ceiling, the highest holdout profit
    factor.  Deliberately not "the broadest": the broadest survivor of
    ARK-S24-04 sat at rank 99 of 101 with a profit factor barely above the
    floor, which trades a concentration refusal for a profit-factor one.
    """
    from .edge_search_execution import _profit_factor

    evidence = recorded(session, campaign)
    trials = {item.id: item for item in session.scalars(
        select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id))}
    rows = []
    for trial_id, record in evidence.items():
        trial = trials.get(trial_id)
        if not trial or not (trial.result or {}).get("holdout_survivor"):
            continue
        factor = _profit_factor(trial.result["splits"]["holdout"]["metrics"])
        rows.append({"trial_id": trial.id, "trial_index": trial.trial_index,
                     "parameters": trial.parameters, "holdout_profit_factor": factor,
                     "regime_concentration": record.regime_concentration,
                     "year_concentration": record.year_concentration,
                     "within_ceiling": record.within_ceiling,
                     "breadth_fingerprint": record.fingerprint})
    eligible = [row for row in rows if row["within_ceiling"]]
    eligible.sort(key=lambda row: (row["holdout_profit_factor"] or 0.0), reverse=True)
    return {
        "breadth_version": BREADTH_VERSION,
        "campaign_id": campaign.id, "ceiling": CEILING,
        "rule": ("among survivors whose train+holdout regime concentration is at or below the accepted gate's "
                 "own ceiling, the highest holdout profit factor"),
        "survivors_with_breadth_evidence": len(rows),
        "within_ceiling": len(eligible),
        "ranked": eligible[:limit],
        "safety_boundary": {"final_oos_read": False, "threshold_relaxed": False,
                            "selection_made": False, "budget_consumed": False, "live_authorized": False},
        "warning": (
            "Ranking is train and holdout evidence only. A high rank is not an edge and not a selection; "
            "opening final OOS still requires an exact Owner authorization and costs an irreversible unit."
        ),
    }


def serialize(item: EdgeSearchTrialBreadth, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "campaign_id": item.campaign_id, "trial_id": item.trial_id,
             "fingerprint": item.fingerprint, "breadth_version": item.breadth_version,
             "regime_concentration": item.regime_concentration,
             "year_concentration": item.year_concentration,
             "within_ceiling": item.within_ceiling, "result": item.result,
             "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        value["reused"] = reused
    return value
