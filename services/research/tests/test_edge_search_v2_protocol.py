"""ARK-S24-04 the extended campaign protocol.

V2 adds direction, session_window, and stop_type.  It is a new protocol rather
than an edit of V1, so the first obligation is that every accepted V1 campaign
still expands, fingerprints, and verifies exactly as it did.
"""
from copy import deepcopy

import pytest

from app import edge_search as es
from app.strategy_capabilities import GENERIC, assess
from app.strategy_contracts import fingerprint as contract_fingerprint

from tests.test_edge_search import BASE_DIMENSIONS, CALIBRATION, session  # noqa: F401


V2_DIMENSIONS = {
    "stop_scale": [10, 80], "target_ratio": [1.0, 1.474, 2.0],
    "sma_fast": [2, 5], "sma_slow": [10, 50], "sma_relation": ["ABOVE", "BELOW"],
    "polarity": ["BULLISH", "BEARISH"], "direction": ["LONG", "SHORT"],
    "session_window": ["NONE", "02-21"], "stop_type": ["FIXED", "ATR"],
}
V2_POINT = {"stop_scale": 80, "target_ratio": 2.0, "sma_fast": 2, "sma_slow": 50,
            "sma_relation": "ABOVE", "polarity": "BULLISH", "direction": "LONG",
            "session_window": "NONE", "stop_type": "FIXED"}


def _small(**overrides):
    """A two-point V2 grid, so tests stay fast."""
    value = {key: [values[0]] for key, values in V2_DIMENSIONS.items()}
    value["stop_type"] = ["FIXED", "ATR"]
    value.update(overrides)
    return value


# ---- V1 did not move -------------------------------------------------------

def test_a_v1_grid_point_still_builds_a_byte_identical_contract():
    point = {"stop_scale": 80, "target_ratio": 2.0, "sma_fast": 2, "sma_slow": 50,
             "sma_relation": "ABOVE", "setup_direction": "BULLISH", "trigger_direction": "BULLISH"}
    contract = es.build_contract(point)
    assert contract["provenance"]["protocol_version"] == es.PROTOCOL_VERSION
    assert contract["direction_eligibility"] == "LONG"
    assert contract["stop_loss_rule"]["block_id"] == "FIXED_PRICE_DISTANCE_SL"
    assert len(contract["no_trade_conditions"]) == 3, "a V1 contract carries no session block"


def test_a_v1_grid_still_enumerates_and_fingerprints_as_v1(session):
    campaign, _ = es.create(session, {"dataset_id": "ds-1", "grid_dimensions": dict(BASE_DIMENSIONS),
                                      "calibration_disclosure": CALIBRATION})
    assert campaign.protocol_version == es.PROTOCOL_VERSION
    assert campaign.grid["enumeration_order"] == list(es.DIMENSION_KEYS)
    assert es.verify(session, campaign)["status"] == "PASSED"


def test_the_v1_dimension_keys_are_untouched():
    assert es.DIMENSION_KEYS == ("stop_scale", "target_ratio", "sma_fast", "sma_slow",
                                 "sma_relation", "setup_direction", "trigger_direction")


# ---- protocol detection ----------------------------------------------------

def test_the_protocol_is_read_from_the_point_not_a_module_constant():
    assert es.protocol_of({"stop_scale": 10}) == es.PROTOCOL_VERSION
    assert es.protocol_of(V2_POINT) == es.PROTOCOL_VERSION_V2


def test_a_half_declared_v2_point_is_refused():
    for missing in ("direction", "session_window", "stop_type"):
        point = {key: value for key, value in V2_POINT.items() if key != missing}
        with pytest.raises(ValueError, match="must declare all of"):
            es.protocol_of(point)


def test_a_mixed_dimension_set_is_refused():
    with pytest.raises(ValueError, match="must declare exactly"):
        es.enumerate_grid({**BASE_DIMENSIONS, "stop_type": ["FIXED"]})


# ---- the three new axes ----------------------------------------------------

def test_direction_reaches_the_contract():
    assert es.build_contract({**V2_POINT, "direction": "SHORT"})["direction_eligibility"] == "SHORT"


def test_a_session_window_becomes_a_no_trade_block():
    contract = es.build_contract({**V2_POINT, "session_window": "02-21"})
    block = next(item for item in contract["no_trade_conditions"] if item["block_id"] == "SESSION_WINDOW")
    assert block["clock"] == "BROKER_TIME"
    assert block["windows"] == [{"start_hour": 2, "end_hour": 21}]


def test_none_adds_no_block_at_all():
    contract = es.build_contract({**V2_POINT, "session_window": "NONE"})
    assert [item["block_id"] for item in contract["no_trade_conditions"]] == [
        "FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS", "STOP_FIRST"]


def test_the_two_stop_types_are_matched_on_mean_distance():
    """A wider scaled arm would compare geometry, not adaptivity."""
    fixed = es.build_contract({**V2_POINT, "stop_type": "FIXED"})
    scaled = es.build_contract({**V2_POINT, "stop_type": "ATR"})
    stop = fixed["stop_loss_rule"]["distance"]
    assert scaled["stop_loss_rule"]["multiplier"] == pytest.approx(stop / es.MEAN_M1_TRUE_RANGE, rel=1e-5)
    assert scaled["stop_loss_rule"]["period"] == es.ATR_PERIOD == scaled["take_profit_rule"]["period"]


def test_the_target_ratio_survives_the_scaled_arm():
    scaled = es.build_contract({**V2_POINT, "stop_type": "ATR", "target_ratio": 2.0})
    assert scaled["take_profit_rule"]["multiplier"] == pytest.approx(
        2.0 * scaled["stop_loss_rule"]["multiplier"], rel=1e-5)


def test_polarity_drives_both_setup_and_trigger():
    contract = es.build_contract({**V2_POINT, "polarity": "BEARISH"})
    assert contract["setup_rules"][0]["direction"] == "BEARISH"
    assert contract["trigger_rules"][0]["direction"] == "BEARISH"


# ---- validation ------------------------------------------------------------

@pytest.mark.parametrize("key,value", [
    ("direction", "BOTH"), ("polarity", "LONG"), ("stop_type", "TRAILING"),
    ("session_window", "22-02"), ("session_window", "2-21"), ("session_window", "02-24"), ("session_window", 2),
])
def test_a_malformed_new_axis_value_is_refused(key, value):
    with pytest.raises(ValueError):
        es.enumerate_grid({**V2_DIMENSIONS, key: [value]})


def test_every_point_of_the_full_v2_grid_is_generic_executable():
    points = es.enumerate_grid(V2_DIMENSIONS)
    assert len(points) == 768
    for point in points:
        report = assess(es.build_contract(point))
        assert report["status"] == "CONTRACT_VALID", (point, report["issues"])
        assert report["evaluator_capability_id"] == GENERIC


def test_declaration_order_does_not_change_the_frozen_enumeration():
    first = es.enumerate_grid({**V2_DIMENSIONS, "stop_scale": [80, 10]})
    second = es.enumerate_grid({**V2_DIMENSIONS, "stop_scale": [10, 80]})
    assert first == second


# ---- the measured budget ---------------------------------------------------

def test_the_operative_cap_is_derived_from_the_measured_baseline():
    assert es.MEASURED_SECONDS_PER_TRIAL_V2 == 72
    assert es.OPERATIVE_TRIAL_CAP_V2 == es.WALL_CLOCK_BUDGET_SECONDS_V2 // es.MEASURED_SECONDS_PER_TRIAL_V2
    assert es.operative_trial_cap(es.PROTOCOL_VERSION_V2) == 900
    assert es.operative_trial_cap(es.PROTOCOL_VERSION) == es.OPERATIVE_TRIAL_CAP


def test_the_full_v2_grid_fits_the_measured_budget():
    points = es.enumerate_grid(V2_DIMENSIONS)
    assert len(points) <= es.operative_trial_cap(es.PROTOCOL_VERSION_V2)
    assert len(points) * es.seconds_per_trial(es.PROTOCOL_VERSION_V2) <= es.WALL_CLOCK_BUDGET_SECONDS_V2


def test_a_grid_over_the_cap_is_refused(session):
    oversized = {**V2_DIMENSIONS, "stop_scale": [10, 20, 40, 80]}
    report = es.validation_report(session, {"dataset_id": "ds-1", "grid_dimensions": oversized,
                                            "calibration_disclosure": CALIBRATION})
    assert not report["ready"]
    assert any("operative cap" in issue for issue in report["issues"])


# ---- the cost assumption was not altered -----------------------------------

def test_the_frozen_cost_assumption_is_unchanged_in_v2():
    """ARK-S24-04 forbids altering a cost assumption; 0.18 is a later
    sensitivity question, never a grid dimension."""
    assert es.SPREAD_ASSUMPTION == 0.25
    for stop_type in ("FIXED", "ATR"):
        contract = es.build_contract({**V2_POINT, "stop_type": stop_type})
        guard = next(item for item in contract["no_trade_conditions"] if item["block_id"] == "FIXED_SPREAD_GUARD")
        assert guard["maximum"] == 0.25
        assert contract["cost_assumptions"] == {"commission_price": 0.0}


def test_the_final_oos_budget_is_unchanged_in_v2():
    assert es.policy_contract(es.PROTOCOL_VERSION_V2)["final_oos_budget"] == 3
    assert es.policy_contract(es.PROTOCOL_VERSION_V2)["gate_policy"] == es.policy_contract()["gate_policy"]
    assert es.policy_contract(es.PROTOCOL_VERSION_V2)["split_policy"] == es.policy_contract()["split_policy"]


# ---- a V2 campaign end to end ---------------------------------------------

def test_a_v2_campaign_pre_registers_verifies_and_records_its_dependencies(session):
    campaign, reused = es.create(session, {"dataset_id": "ds-1", "grid_dimensions": _small(),
                                           "calibration_disclosure": CALIBRATION})
    assert not reused
    assert campaign.protocol_version == es.PROTOCOL_VERSION_V2
    assert campaign.grid["enumeration_order"] == list(es.DIMENSION_KEYS_V2)
    assert campaign.trial_count == 2
    report = es.verify(session, campaign)
    assert report["status"] == "PASSED", report["checks"]
    assert report["protocol_version"] == es.PROTOCOL_VERSION_V2
    # The scaled arm pulls the two ATR blocks into the dependency set.
    assert {"ATR_SCALED_SL", "ATR_SCALED_TP"} <= set(es.campaign_block_ids(campaign))
    assert campaign.result["capability_dependency_fingerprint"] == es.capability_dependency_fingerprint(campaign)


def test_a_v2_campaign_with_a_session_window_depends_on_that_block_too(session):
    campaign, _ = es.create(session, {"dataset_id": "ds-1",
                                      "grid_dimensions": _small(session_window=["02-21"]),
                                      "calibration_disclosure": CALIBRATION})
    assert "SESSION_WINDOW" in es.campaign_block_ids(campaign)
    assert es.verify(session, campaign)["status"] == "PASSED"


def test_two_protocols_coexist_without_disturbing_each_other(session):
    v1, _ = es.create(session, {"dataset_id": "ds-1", "grid_dimensions": dict(BASE_DIMENSIONS),
                                "calibration_disclosure": CALIBRATION})
    v2, _ = es.create(session, {"dataset_id": "ds-1", "grid_dimensions": _small(),
                                "calibration_disclosure": CALIBRATION})
    assert v1.fingerprint != v2.fingerprint
    assert es.verify(session, v1)["status"] == "PASSED"
    assert es.verify(session, v2)["status"] == "PASSED"
    assert es.verify(session, v1)["protocol_version"] == es.PROTOCOL_VERSION
    assert es.verify(session, v2)["protocol_version"] == es.PROTOCOL_VERSION_V2


def test_the_executor_needs_no_change_to_run_a_v2_point(session):
    """The exit criterion: the accepted executor is reused unmodified."""
    from app import edge_search_execution
    import inspect
    source = inspect.getsource(edge_search_execution)
    assert "PROTOCOL_VERSION_V2" not in source
    assert "stop_type" not in source and "session_window" not in source
    # It reaches the contract only through build_contract, which dispatches.
    assert "build_contract(entry[\"parameters\"])" in source
