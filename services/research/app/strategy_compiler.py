"""ARK-S16-02 deterministic compiler seam into the sole Backtest V1 kernel.

The compiler is intentionally compatibility-only.  It produces kernel input and
evidence, never executes a ledger and never falls back to an unregistered rule.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .backtesting import validate_backtest_config
from .strategy_capabilities import EXECUTABLE, assess
from .strategy_contracts import canonical_json


COMPILER_VERSION = "STRATEGY_CONTRACT_COMPILER_V1"
KERNEL_ID = "BACKTEST_V1_SINGLE_STATEFUL_KERNEL"


def compile_contract(contract: object) -> dict[str, Any]:
    """Compile only a registry-valid legacy contract to canonical kernel input."""
    assessment = assess(contract)
    if assessment["status"] != "CONTRACT_VALID" or assessment["evaluator_capability_id"] != EXECUTABLE:
        raise ValueError("CAPABILITY_NOT_SUPPORTED: contract has no accepted compiler capability")
    normalized = assessment["normalized_contract"]
    guards = {item["block_id"]: item for item in normalized["no_trade_conditions"]}
    kernel_config = validate_backtest_config({
        "candidate_id": "BULLISH_REVERSAL_M1",
        "candidate_version": 1,
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "stop_distance": normalized["stop_loss_rule"]["distance"],
        "target_distance": normalized["take_profit_rule"]["distance"],
        "spread_price": guards["FIXED_SPREAD_GUARD"]["maximum"],
        "commission_price": normalized["cost_assumptions"]["commission_price"],
        "ambiguity_policy": "STOP_FIRST",
        "execution_resolution": "M1_BROAD",
    })
    timing = {
        "signal_inputs": "TWO_COMPLETED_M1_CANDLES",
        "minimum_completed_bars": 2,
        "entry_timing": "NEXT_M1_BAR_OPEN",
        "context_alignment": "M1_CLOSE_AVAILABLE_AT_DECISION_ONLY",
        "warmup": {"required_completed_bars": 2, "missing_history": "NO_SIGNAL"},
        "ambiguity_policy": "STOP_FIRST",
    }
    unsigned = {
        "compiler_version": COMPILER_VERSION,
        "kernel_id": KERNEL_ID,
        "assessment_fingerprint": assessment["fingerprint"],
        "strategy_contract_fingerprint": assessment["strategy_contract_fingerprint"],
        "registry": assessment["registry"],
        "evaluator_capability_id": EXECUTABLE,
        "kernel_config": kernel_config,
        "kernel_config_fingerprint": sha256(canonical_json(kernel_config).encode()).hexdigest(),
        "timing_semantics": timing,
    }
    return {**unsigned, "fingerprint": sha256(canonical_json(unsigned).encode()).hexdigest()}
