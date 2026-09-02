"""ARK-S24-04 the accepted Sprint 22 campaign must survive a registry extension.

The verifier compared the whole capability registry for equality, so Sprint 24
adding SESSION_WINDOW and the two ATR blocks made an accepted, untampered
`NO_EDGE_FOUND` record verify as FAILED.

These tests pin the replacement: what protects a campaign is that the blocks its
frozen contracts depend on still mean what they meant, not that nothing else in
the registry ever changed.
"""
from copy import deepcopy

import pytest

from app import edge_search
from app.strategy_capabilities import BLOCKS

from tests.test_edge_search import BASE_DIMENSIONS, CALIBRATION, session  # noqa: F401


def _create(session, **overrides):
    payload = {"dataset_id": "ds-1", "grid_dimensions": {**BASE_DIMENSIONS}, "calibration_disclosure": CALIBRATION}
    payload.update(overrides)
    return edge_search.create(session, payload)[0]


# ---- the accepted Sprint 22 values -----------------------------------------

def test_the_accepted_sprint_22_lineage_values_are_exact():
    """Both were read from the live record and the pre-Sprint-24 source, not
    assumed.  Editing either would make the accepted ARK-S22-01 record untrue."""
    assert edge_search.ACCEPTED_V1_REGISTRY_FINGERPRINT == "808d3506e7020b41d977fc8aae94f6cc6eb7a1c9e25a8093ea0bdb402a3b2bfb"
    assert edge_search.ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT == "f73b4bd68c5dd0b9d370d40390a81b4c4a5c60b5d2ca24662a4f584ff7a59069"


def test_the_sprint_22_grid_depends_on_exactly_eleven_blocks(session):
    campaign = _create(session)
    assert edge_search.campaign_block_ids(campaign) == [
        "ALWAYS", "CANDLE_DIRECTION", "FIXED_LOT_DEMO", "FIXED_PRICE_DISTANCE_SL",
        "FIXED_PRICE_DISTANCE_TP", "FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS",
        "NEXT_BAR_OPEN", "SMA_RELATION", "STOP_FIRST", "TWO_BAR_REVERSAL"]


def test_the_sprint_24_blocks_are_not_among_them(session):
    used = set(edge_search.campaign_block_ids(_create(session)))
    assert used.isdisjoint({"SESSION_WINDOW", "ATR_SCALED_SL", "ATR_SCALED_TP"})


def test_the_dependency_fingerprint_survived_the_sprint_24_extension(session):
    """The load-bearing claim: not one block the campaign uses changed."""
    campaign = _create(session)
    assert edge_search.capability_dependency_fingerprint(campaign) == \
        edge_search.ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT


# ---- the check the extension broke, and its replacement ---------------------

def test_a_campaign_verifies_although_the_registry_has_been_extended(session):
    campaign = _create(session)
    report = edge_search.verify(session, campaign)
    assert report["checks"]["capability_dependencies_unchanged"]["status"] == "PASS"
    assert report["checks"]["capability_dependencies_present"]["status"] == "PASS"


def test_the_registry_extension_is_reported_rather_than_hidden(session):
    campaign = _create(session)
    campaign.registry_fingerprint = edge_search.ACCEPTED_V1_REGISTRY_FINGERPRINT
    lineage = edge_search.verify(session, campaign)["registry_lineage"]
    assert lineage["registry_extended_since_pre_registration"] is True
    assert lineage["registry_fingerprint_at_pre_registration"] == edge_search.ACCEPTED_V1_REGISTRY_FINGERPRINT
    assert lineage["registry_fingerprint_now"] != edge_search.ACCEPTED_V1_REGISTRY_FINGERPRINT


# ---- negative controls: the check must still catch real tampering ----------

def test_mutating_a_block_the_campaign_uses_fails_the_check(session, monkeypatch):
    campaign = _create(session)
    mutated = deepcopy(BLOCKS)
    mutated["FIXED_PRICE_DISTANCE_SL"]["parameters"]["distance"] = "ANY_FINITE"
    monkeypatch.setattr("app.strategy_capabilities.BLOCKS", mutated)
    report = edge_search.verify(session, campaign)
    assert report["checks"]["capability_dependencies_unchanged"]["status"] == "FAIL"
    assert report["status"] == "FAILED"


def test_deleting_a_block_the_campaign_uses_fails_the_check(session, monkeypatch):
    campaign = _create(session)
    reduced = {key: value for key, value in deepcopy(BLOCKS).items() if key != "TWO_BAR_REVERSAL"}
    monkeypatch.setattr("app.strategy_capabilities.BLOCKS", reduced)
    report = edge_search.verify(session, campaign)
    assert report["checks"]["capability_dependencies_present"]["status"] == "FAIL"
    assert report["checks"]["capability_dependencies_present"]["observed"] == ["TWO_BAR_REVERSAL"]
    assert report["status"] == "FAILED"


def test_adding_an_unused_block_does_not_fail_the_check(session, monkeypatch):
    """The exact case Sprint 24 created, isolated."""
    campaign = _create(session)
    extended = deepcopy(BLOCKS)
    extended["A_BLOCK_NO_CAMPAIGN_USES"] = {"id": "A_BLOCK_NO_CAMPAIGN_USES", "category": "NO_TRADE",
                                            "execution": "GENERIC_COMPLETED_CANDLE_V1", "completed_candles": True,
                                            "parameters": {}}
    monkeypatch.setattr("app.strategy_capabilities.BLOCKS", extended)
    assert edge_search.verify(session, campaign)["checks"]["capability_dependencies_unchanged"]["status"] == "PASS"


# ---- campaigns recorded from now on carry the value themselves -------------

def test_a_new_campaign_records_its_own_dependency_fingerprint(session):
    campaign = _create(session)
    recorded = campaign.result["capability_dependency_fingerprint"]
    assert recorded == edge_search.capability_dependency_fingerprint(campaign)
    assert edge_search.accepted_dependency_fingerprint(campaign) == recorded


def test_a_campaign_recorded_before_this_checkpoint_falls_back_to_the_constant(session):
    """The one campaign that predates the field must keep verifying."""
    campaign = _create(session)
    campaign.result = {key: value for key, value in campaign.result.items()
                       if key != "capability_dependency_fingerprint"}
    assert edge_search.accepted_dependency_fingerprint(campaign) == \
        edge_search.ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT
    assert edge_search.verify(session, campaign)["checks"]["capability_dependencies_unchanged"]["status"] == "PASS"


def test_a_recorded_fingerprint_is_preferred_over_the_constant(session):
    """A future campaign must be held to its own value, never to Sprint 22's."""
    campaign = _create(session)
    campaign.result = {**campaign.result, "capability_dependency_fingerprint": "c" * 64}
    assert edge_search.accepted_dependency_fingerprint(campaign) == "c" * 64
    assert edge_search.verify(session, campaign)["checks"]["capability_dependencies_unchanged"]["status"] == "FAIL"


# ---- ARK-S25-01 a growing dataset must not break an accepted record ---------

def test_a_grown_dataset_does_not_break_the_grid_recomputation(session):
    """The verifier read `dataset.fingerprint` live. An MT5 sync appended
    11,281 bars and both accepted campaigns began verifying as FAILED although
    neither record had been touched -- the same defect class as ARK-S24-04a,
    one field over."""
    from app.models import Dataset
    campaign = _create(session)
    assert edge_search.verify(session, campaign)["status"] == "PASSED"
    dataset = session.get(Dataset, campaign.dataset_id)
    dataset.fingerprint = "grown-" + "f" * 58        # the sync rewrote it
    session.commit()
    report = edge_search.verify(session, campaign)
    assert report["checks"]["immutable_grid_recomputation"]["status"] == "PASS"
    assert report["status"] == "PASSED"


def test_the_dataset_drift_is_reported_rather_than_hidden(session):
    from app.models import Dataset
    campaign = _create(session)
    session.get(Dataset, campaign.dataset_id).fingerprint = "grown-" + "f" * 58
    session.commit()
    lineage = edge_search.verify(session, campaign)["dataset_lineage"]
    assert lineage["dataset_grew_since_pre_registration"] is True
    assert lineage["dataset_fingerprint_at_pre_registration"] == campaign.dataset_fingerprint
    assert lineage["dataset_fingerprint_now"] != campaign.dataset_fingerprint


def test_the_recomputation_uses_what_the_campaign_recorded(session):
    """Passing the live row in was the defect; a test pins the signature."""
    import inspect
    source = inspect.getsource(edge_search.verify)
    assert "campaign.dataset_fingerprint" in source
    assert "session.get(Dataset, campaign.dataset_id), campaign.registry_fingerprint" not in source


def test_the_chain_verifier_carries_both_lineage_blocks(session):
    from app import edge_search_verification as verification
    campaign = _create(session)
    report = verification.assess(session, campaign)
    assert report["dataset_lineage"]["dataset_id"] == campaign.dataset_id
    assert report["registry_lineage"]["capability_blocks_used"]
