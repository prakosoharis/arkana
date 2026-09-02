"""ARK-S25-04 a verifier must judge a record against what the record stored.

Four verifiers reported FAILED on records nobody had touched, because each
recomputed from a value the system is designed to change: the capability
registry (ARK-S24-04a), then the dataset fingerprint and the row count an MT5
sync moved (ARK-S25-01, and the three found by the ARK-S25-01a audit).

The defect was found four times in two sprints because nothing asserted the
property directly. These tests assert it directly.
"""
import inspect

import pytest

from app import constrained_capital_simulations as capital
from app import generic_evidence_verification as evidence
from app import generic_robustness
from app import oos_validation
from app import variant_experiment_contracts as variant_contracts
from app import variant_experiment_verification as variant


# ---- the fingerprint helpers can be given what a record stored -------------

@pytest.mark.parametrize("helper", [
    oos_validation.evidence_fingerprint,
    generic_robustness.evidence_fingerprint,
    variant_contracts.fingerprint,
])
def test_a_fingerprint_helper_accepts_the_recorded_dataset_identity(helper):
    """Without an override a verifier can only read the live row, which is
    exactly how an untouched record stops reproducing its own fingerprint."""
    parameters = inspect.signature(helper).parameters
    assert "dataset_fingerprint" in parameters
    assert parameters["dataset_fingerprint"].default is None, "writers must keep the live row"


def test_the_oos_helper_also_accepts_a_recorded_asset_snapshot():
    """row_count and range_end move on every sync, and both are fingerprinted."""
    parameters = inspect.signature(oos_validation.evidence_fingerprint).parameters
    assert "asset_snapshot" in parameters
    assert parameters["asset_snapshot"].default is None


# ---- each verifier judges against recorded state ---------------------------

def _code(function) -> str:
    source = inspect.getsource(function)
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def test_generic_evidence_derives_its_bounds_from_the_record():
    """`split_bounds(m1.row_count)` describes a partition the record never ran
    on the moment the dataset grows."""
    code = _code(evidence.verify)
    assert "split_bounds(recorded_rows)" in code
    assert "split_bounds(m1.row_count)" not in code


def test_generic_evidence_uses_the_recorded_asset_lineage():
    code = _code(evidence.verify)
    assert 'stored_evaluator.get("asset_lineage")' in code
    assert "range_start.isoformat()" not in code, "lineage is no longer rebuilt from live rows"


def test_generic_evidence_checks_the_evaluator_artifact_against_itself():
    """The artifact embeds the registry it was built against, so re-deriving it
    from the live registry fails the moment a block is added."""
    code = _code(evidence.verify)
    assert "evaluator_self_consistent" in code
    assert "evaluator_artifact(" not in code


def test_generic_evidence_no_longer_requires_the_current_registry_to_match():
    code = _code(evidence.verify)
    assert 'assessment.fingerprint == bound.get("fingerprint")' in code
    assert 'assessment.registry_fingerprint == capability.get("registry", {}).get("fingerprint")' not in code


def test_variant_derives_its_bounds_from_the_baseline_record():
    code = _code(variant.verify)
    assert "split_bounds(recorded_rows)" in code


def test_variant_recomputes_from_the_stored_assessment():
    code = _code(variant.verify)
    assert "recorded_assessment" in code and "dataset_fingerprint=recorded_dataset_fingerprint" in code


def test_capital_walks_only_as_far_as_the_record_covers():
    """Replaying the whole live asset produced more trades than the stored
    capital path has points, and reported the record as truncated."""
    code = _code(capital.verify_full_history)
    assert "recorded_bars" in code and "_bounded(" in code


# ---- the drift is disclosed, not hidden ------------------------------------

@pytest.mark.parametrize("function,key", [
    (evidence.verify, "record_lineage"),
    (capital.verify_full_history, "dataset_grew_since_record"),
])
def test_the_drift_is_reported(function, key):
    assert key in _code(function)


# ---- the property that would have caught all four --------------------------

def test_no_verifier_rebuilds_split_bounds_from_a_live_row():
    """The single assertion whose absence let this defect be found four times.

    A verifier may compute canonical bounds -- that is what makes 60/20/20
    checkable -- but it must derive the row count from the record, never from
    the asset as it stands today.
    """
    import pathlib
    # A writer reads the live asset by definition -- that is how a record comes
    # to state a row count at all. Only verifiers are constrained here.
    WRITERS = {"variant_experiment_contracts.py", "oos_validation.py", "generic_robustness.py"}
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in sorted(root.glob("*.py")):
        if path.name in WRITERS:
            continue
        text = path.read_text()
        if "def verify" not in text and "def assess" not in text:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or "split_bounds(" not in stripped:
                continue
            if "asset.row_count" in stripped or "m1.row_count" in stripped:
                offenders.append(f"{path.name}:{number}: {stripped[:90]}")
    assert not offenders, (
        "these rebuild split bounds from a live asset inside a verifier:\n" + "\n".join(offenders))
