"""Versioned Strategy Factory V1 compatibility block registry."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


def _block(block_id: str, category: str, label: str, description: str, *, units: list[str] | None = None, directions: list[str] | None = None) -> dict[str, Any]:
    return {"id": block_id, "version": 1, "category": category, "label": label, "description": description, "supported_timeframes": ["M1"], "supported_directions": directions or ["LONG"], "parameters": [], "units": units or [], "evaluator_capability_id": "LEGACY_BULLISH_REVERSAL_M1_V1", "deployment_support": "DEMO_COMPATIBILITY_ONLY"}


BLOCKS = {
    item["id"]: item for item in (
        _block("ALWAYS", "CONTEXT", "Tidak ada context tambahan", "Compatibility block untuk legacy rule."),
        _block("CANDLE_DIRECTION", "TRIGGER", "Arah candle", "Evaluasi candle yang sudah selesai."),
        _block("SEQUENCE_PREVIOUS_THEN_CURRENT", "TRIGGER", "Urutan candle", "Urutan previous/current completed candle."),
        _block("NEXT_BAR_OPEN", "ENTRY", "Open candle berikutnya", "Entry hanya pada open bar berikutnya."),
        _block("FIXED_PRICE_DISTANCE_SL", "STOP_LOSS", "Stop distance tetap", "Jarak SL dalam price unit.", units=["PRICE"]),
        _block("FIXED_PRICE_DISTANCE_TP", "TAKE_PROFIT", "Target distance tetap", "Jarak TP dalam price unit.", units=["PRICE"]),
        _block("FIXED_SPREAD_GUARD", "NO_TRADE", "Batas spread", "Menolak entry saat spread melampaui batas.", units=["PRICE"]),
        _block("MAX_OPEN_POSITIONS", "NO_TRADE", "Maksimum posisi", "Menolak entry jika posisi ARKANA sudah terbuka."),
        _block("FIXED_LOT_DEMO", "RISK", "Lot DEMO tetap", "Hanya 0.01 lot untuk compatibility DEMO."),
        _block("STOP_FIRST", "AMBIGUITY", "STOP_FIRST", "SL menang jika SL dan TP tersentuh dalam candle sama."),
    )
}


def registry() -> dict[str, Any]:
    blocks = [BLOCKS[key] for key in sorted(BLOCKS)]
    canonical = json.dumps(blocks, sort_keys=True, separators=(",", ":"))
    return {"version": "STRATEGY_BLOCK_REGISTRY_V1", "fingerprint": sha256(canonical.encode()).hexdigest(), "blocks": blocks}


def supported(block_id: str) -> bool:
    return block_id in BLOCKS
