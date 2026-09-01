"""ARK-S24-04 a fixture may never shadow real evidence.

The production database holds nine registered XAUUSD datasets of which exactly
one is real.  Seven fixtures are newer than it, and the newest points at a file
that does not exist, so every "latest XAUUSD dataset" caller resolved to a
fixture and the accepted Quick Backtest path died on a raw DuckDB IOException.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.market_data import latest_dataset
from app.migrations import run_migrations
from app.models import Dataset, DatasetBarAsset
from app.strategy_lineage import synthetic_dataset_reason


REAL_FINGERPRINT = "a1b2c3d4e5f6" + "0" * 52


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/datasets.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as value:
        yield value


def _add(session, *, ident, source, fingerprint=None, imported, symbol="XAUUSD"):
    # Fingerprints are unique, so each fixture needs its own real-looking digest.
    fingerprint = fingerprint or (f"{abs(hash(ident)):016x}" * 4)[:64]
    dataset = Dataset(id=ident, fingerprint=fingerprint, symbol=symbol, source=source,
                      timezone_status="UNVERIFIED_BROKER_TIME", imported_at=imported)
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path=f"/data/{ident}/M1.parquet", row_count=1000,
                                        range_start=datetime(2020, 1, 1), range_end=datetime(2026, 1, 1)))
    session.add(dataset); session.commit()
    return dataset


# ---- one rule for what a fixture is ----------------------------------------

def test_the_selector_reuses_the_lineage_classifier_rule():
    """A second definition of "fixture" is exactly what this must not create."""
    import inspect
    from app import market_data
    assert "synthetic_dataset_reason" in inspect.getsource(market_data.latest_dataset)


@pytest.mark.parametrize("source,fingerprint,synthetic", [
    ("MT5", REAL_FINGERPRINT, False),
    ("S13-03 pass fixture", REAL_FINGERPRINT, True),
    ("MT5 fixture", REAL_FINGERPRINT, True),
    ("TEST", REAL_FINGERPRINT, True),
    ("MT5", "dataset-fp", True),
    ("MT5", "3" * 64, True),
])
def test_the_shared_rule_agrees_with_the_classifier(session, source, fingerprint, synthetic):
    dataset = _add(session, ident=f"ds-{abs(hash((source, fingerprint)))}", source=source,
                   fingerprint=fingerprint, imported=datetime(2026, 1, 1))
    assert (synthetic_dataset_reason(dataset) is not None) is synthetic


# ---- the defect, isolated --------------------------------------------------

def test_a_newer_fixture_can_never_shadow_real_evidence(session):
    real = _add(session, ident="ds-real", source="MT5", fingerprint=REAL_FINGERPRINT,
                imported=datetime(2026, 8, 11))
    _add(session, ident="ds-fixture", source="S13-03 pass fixture", imported=datetime(2026, 9, 5))
    assert latest_dataset(session).id == real.id


def test_a_future_dated_fixture_can_never_shadow_real_evidence(session):
    """The production fixture is dated five days ahead of today, which is how
    it won 'latest' in the first place."""
    real = _add(session, ident="ds-real", source="MT5", fingerprint=REAL_FINGERPRINT,
                imported=datetime(2026, 8, 11))
    _add(session, ident="ds-future", source="TEST", imported=datetime(2099, 1, 1))
    assert latest_dataset(session).id == real.id


def test_the_newest_real_dataset_still_wins_among_real_ones(session):
    _add(session, ident="ds-old", source="MT5", fingerprint=REAL_FINGERPRINT, imported=datetime(2025, 1, 1))
    newer = _add(session, ident="ds-new", source="MT5", fingerprint="b" + REAL_FINGERPRINT[1:],
                 imported=datetime(2026, 8, 11))
    assert latest_dataset(session).id == newer.id


def test_selection_is_scoped_to_the_requested_symbol(session):
    _add(session, ident="ds-xau", source="MT5", fingerprint=REAL_FINGERPRINT, imported=datetime(2026, 1, 1))
    _add(session, ident="ds-eur", source="MT5", fingerprint="c" + REAL_FINGERPRINT[1:],
         imported=datetime(2026, 8, 1), symbol="EURUSD")
    assert latest_dataset(session, "XAUUSD").id == "ds-xau"
    assert latest_dataset(session, "EURUSD").id == "ds-eur"


# ---- a fixture-only environment is unchanged -------------------------------

def test_a_fixture_only_database_still_resolves_to_its_newest(session):
    """Judging whether a *result* is real belongs to the lineage classifier.
    The selector's job is only that a fixture never shadows real evidence."""
    _add(session, ident="ds-old", source="TEST", imported=datetime(2026, 1, 1))
    _add(session, ident="ds-new", source="TEST", imported=datetime(2026, 6, 1))
    assert latest_dataset(session).id == "ds-new"


def test_an_empty_database_returns_none(session):
    assert latest_dataset(session) is None


# ---- every caller goes through it ------------------------------------------

# Selecting one dataset by hand is what caused this defect.  Two call sites
# legitimately order datasets and are named here with their reason, so adding a
# third is a deliberate act rather than an oversight.
EXEMPT = {
    "market_data.py": "defines the shared selector",
    "main.py": "lists every registered dataset, fixtures included, for display",
    "mt5_acquisition.py": "already scoped to source == 'MT5', which is stricter",
}


def test_no_module_picks_a_single_dataset_by_hand():
    """A caller that re-implements the ordering reintroduces the defect."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in sorted(root.glob("*.py")):
        if path.name in EXEMPT:
            continue
        for line in path.read_text().splitlines():
            if "Dataset.imported_at.desc()" in line:
                offenders.append(f"{path.name}: {line.strip()[:90]}")
    assert not offenders, "these still order datasets by hand:\n" + "\n".join(offenders)


def test_the_display_listing_still_shows_every_dataset():
    """Hiding fixtures from the Owner's dataset list would be the wrong fix."""
    import inspect
    from app import main
    assert "order_by(Dataset.imported_at.desc())" in inspect.getsource(main.list_datasets)


def test_the_bars_endpoint_uses_the_shared_selector():
    import inspect
    from app import main
    assert "latest_dataset(session, symbol.upper())" in inspect.getsource(main.bars)


# ---- ARK-S24-06 a future-dated record cannot be the latest -----------------

def test_a_future_dated_real_looking_dataset_is_not_selected(session):
    """The production fixture was stamped five days ahead, which is how it won
    'latest'.  A row that merely looks real must not win the same way."""
    real = _add(session, ident="ds-real", source="MT5", fingerprint=REAL_FINGERPRINT,
                imported=datetime(2026, 8, 11))
    _add(session, ident="ds-ahead", source="MT5", imported=datetime(2099, 1, 1))
    assert latest_dataset(session).id == real.id


def test_future_dating_is_judged_with_a_skew_tolerance(session):
    from datetime import timedelta
    from app.market_data import FUTURE_DATED_TOLERANCE, future_dated
    now = datetime.utcnow()
    assert FUTURE_DATED_TOLERANCE == timedelta(hours=1)
    just_now = _add(session, ident="ds-now", source="MT5", imported=now)
    slightly_ahead = _add(session, ident="ds-skew", source="MT5", imported=now + timedelta(minutes=5))
    far_ahead = _add(session, ident="ds-far", source="MT5", imported=now + timedelta(days=5))
    assert not future_dated(just_now)
    assert not future_dated(slightly_ahead), "clock skew must not disqualify a real import"
    assert future_dated(far_ahead)


def test_a_future_dated_dataset_is_still_returned_when_it_is_all_there_is(session):
    """The selector refuses to let it shadow real evidence; it does not pretend
    the row is absent."""
    _add(session, ident="ds-only", source="MT5", imported=datetime(2099, 1, 1))
    assert latest_dataset(session).id == "ds-only"
