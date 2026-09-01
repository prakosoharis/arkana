"""ARK-S24-08 an unbounded read of a fragmented asset exhausts DuckDB.

The registered M1 asset is a glob of immutable fragments. `read_bars` resolves
duplicates with a window function, and with `latest=False` and no date range
that window runs over the whole glob *before* the limit applies. On the real
2,985,994-bar asset it raises `OutOfMemoryException` before returning a row.

Nothing caught it because the code had only ever been exercised against the
1,000-row fixture that ARK-S24-04b stopped selecting. Fixing dataset selection
is what made these paths finally touch real data.
"""
import ast
import inspect
from pathlib import Path

import pytest

from app import discovery, research_execution
from app.market_data import _fragmented, read_bars

APP = Path(__file__).resolve().parents[1] / "app"


def _read_bars_calls(module) -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(module))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "read_bars"]


def _keyword(call: ast.Call, name: str):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def test_a_fragmented_path_is_recognised():
    assert _fragmented("/data/ds/M1/*.parquet")
    assert not _fragmented("/data/ds/M1.parquet")


@pytest.mark.parametrize("module", [discovery, research_execution], ids=["discovery", "research_execution"])
def test_no_unbounded_read_of_a_possibly_fragmented_asset(module):
    """A read with no start, no end and no `latest` is the exact shape that
    runs the window over the whole glob."""
    offenders = []
    for call in _read_bars_calls(module):
        start, end, latest = (_keyword(call, key) for key in ("start", "end", "latest"))
        bounded = not _is_none(start) or not _is_none(end)
        if bounded:
            continue
        if latest is None or (isinstance(latest, ast.Constant) and latest.value is not True):
            offenders.append(f"{module.__name__}: line {call.lineno}")
    assert not offenders, (
        "these read an asset with no range and no latest=True, which is "
        "unbounded on a fragment glob:\n" + "\n".join(offenders))


def test_every_module_is_covered_by_this_rule():
    """A new caller with the same shape must not slip in unnoticed."""
    checked = {"discovery.py", "research_execution.py"}
    # These are bounded by an explicit range or already pass latest=True.
    accepted = {"backtesting.py", "main.py", "validation_evidence.py",
                "strategy_router_decisions.py", "market_data.py"}
    callers = {path.name for path in sorted(APP.glob("*.py"))
               if "read_bars(" in path.read_text() and path.name != "market_data.py"}
    unknown = callers - checked - accepted
    assert not unknown, f"new read_bars callers are unreviewed: {sorted(unknown)}"


def test_the_bounded_path_is_what_the_limit_relies_on(tmp_path):
    """`latest=True` restricts the timestamp range before the window runs.
    Asserted on the query text, because the failure is a memory limit that a
    small fixture can never reproduce."""
    source = inspect.getsource(read_bars)
    bounded, unbounded = source.split("elif _fragmented(asset.path):", 1)[1].split("else:", 1)
    assert "timestamp >= ?" in bounded, "the latest path no longer restricts the range"
    assert "QUALIFY row_number()" in bounded
    # The unbounded branch is the non-fragmented one, where a glob window
    # cannot arise in the first place.
    assert "read_parquet(?, filename=true)" not in unbounded
