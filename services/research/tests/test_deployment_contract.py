from pathlib import Path
from types import SimpleNamespace

import pytest

from app.deployment_contract import parse_and_validate
from app.deployments import config_text


ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "mt5" / "contracts" / "deployment_config_v1.ini"
OWNER_OAT_STALE_FIXTURE = ROOT / "mt5" / "contracts" / "owner_oat_stale_strategy.ini"


def fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_canonical_generated_fixture_is_accepted_for_exact_broker_chart():
    values = parse_and_validate(fixture_text(), "XAUUSD.m")
    assert values["canonical_instrument"] == "XAUUSD"
    assert values["broker_symbol"] == "XAUUSD.m"
    assert values["checksum"] == "8914"


def test_api_generator_emits_the_same_canonical_fixture_contract():
    strategy = SimpleNamespace(configuration={
        "strategy_id": "bullish-reversal-m1", "strategy_version": "1.0.0", "symbol": "XAUUSD",
        "entry": {"rule_set": "BULLISH_REVERSAL_M1"},
        "exit": {"stop_distance": 0.1, "target_distance": 0.1},
        "guards": {"max_spread_price": 0.02},
    })
    generated, checksum = config_text(strategy, "XAUUSD.m")
    assert generated == fixture_text()
    assert checksum == "8914"


@pytest.mark.parametrize(
    ("mutated", "message"),
    [
        ("unknown_field=foo\n", "unknown or duplicated field"),
        ("broker_symbol=XAUUSD.m\nbroker_symbol=XAUUSD.m\n", "unknown or duplicated field"),
        ("", "missing mandatory field"),
        ("allowed_environment=LIVE\n", "wrong enum"),
        ("volume=0.01\n", "wrong numeric serialization"),
        ("checksum=0\n", "checksum mismatch"),
    ],
)
def test_contract_rejects_unknown_missing_wrong_enum_noncanonical_or_bad_checksum(mutated, message):
    text = fixture_text()
    if mutated == "":
        text = text.replace("broker_symbol=XAUUSD.m\n", "")
    elif mutated.startswith(("unknown_field", "broker_symbol=XAUUSD.m\nbroker_symbol")):
        text += mutated
    else:
        key = mutated.split("=", 1)[0]
        text = "\n".join([line if not line.startswith(key + "=") else mutated.rstrip() for line in text.splitlines()]) + "\n"
    with pytest.raises(ValueError, match=message):
        parse_and_validate(text, "XAUUSD.m")


def test_contract_requires_exact_execution_symbol_and_retains_prior_valid_fixture_after_rejection():
    prior = parse_and_validate(fixture_text(), "XAUUSD.m")
    with pytest.raises(ValueError, match="broker symbol mismatch"):
        parse_and_validate(fixture_text(), "XAUUSD")
    # The rejected candidate never mutates the already accepted, cached configuration.
    assert prior["broker_symbol"] == "XAUUSD.m"


def test_owner_oat_stale_config_is_rejected_for_the_exact_volume_serialization_drift():
    with pytest.raises(ValueError, match="wrong numeric serialization: volume"):
        parse_and_validate(OWNER_OAT_STALE_FIXTURE.read_text(encoding="utf-8"), "XAUUSD.m")
