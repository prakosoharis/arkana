import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.broker_metadata as broker_metadata
from app.broker_metadata import import_order_calc_margin_validation, import_order_calc_validation, import_snapshot, money_pnl, validate_volume
from app.database import Base

META={"volume_min":"0.01","volume_max":"50","volume_step":"0.01","tick_size":"0.01","tick_value_profit":"1","tick_value_loss":"1"}
def test_volume_and_direct_usd_tick_contract():
    validate_volume(META,0.01)
    assert money_pnl(META,side="BUY",entry=100.00,exit=100.10,volume=0.01)==pytest.approx(0.10)
    assert money_pnl(META,side="BUY",entry=100.10,exit=100.00,volume=0.01)==pytest.approx(-0.10)
    assert money_pnl(META,side="SELL",entry=100.10,exit=100.00,volume=0.01)==pytest.approx(0.10)
    assert money_pnl(META,side="SELL",entry=100.00,exit=100.10,volume=0.01)==pytest.approx(-0.10)
def test_invalid_volume_is_not_rounded():
    with pytest.raises(ValueError): validate_volume(META,0.015)


def test_order_calc_artifact_is_bound_to_exact_metadata_file_and_collection_time(tmp_path, monkeypatch):
    root = tmp_path / "common"; folder = root / "ARKANA" / "broker_metadata"; folder.mkdir(parents=True)
    metadata_text = "\n".join([
        "schema_version=1", "source=MT5", "canonical_symbol=XAUUSD", "broker_symbol=XAUUSD.m", "digits=2", "point=0.01",
        "tick_size=0.01", "tick_value=1", "tick_value_profit=1", "tick_value_loss=1", "contract_size=100", "volume_min=0.01",
        "volume_max=50", "volume_step=0.01", "currency_base=XAU", "currency_profit=USD", "currency_margin=USD", "trade_calc_mode=2",
        "account_currency=USD", "collected_at=2026.08.24 10:00:00",
    ])
    (folder / "latest.ini").write_text(metadata_text)
    parity_text = "\n".join([
        "schema_version=2", "source=MT5_ORDERCALCPROFIT", "broker_symbol=XAUUSD.m", "metadata_collected_at=2026.08.24 10:00:00",
        "volume=0.01", "currency=USD", "timestamp=2026.08.24 10:01:00",
        "case=BUY_WIN|BUY|100|100.1|0.1|OK", "case=BUY_LOSS|BUY|100.1|100|-0.1|OK",
        "case=SELL_WIN|SELL|100.1|100|0.1|OK", "case=SELL_LOSS|SELL|100|100.1|-0.1|OK",
    ])
    (folder / "order_calc_profit_validation.ini").write_text(parity_text)
    monkeypatch.setattr(broker_metadata, "MT5_COMMON_FILES_ROOT", root)
    engine = create_engine(f"sqlite:///{tmp_path / 'broker.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        snapshot, _ = import_snapshot(session)
        report = import_order_calc_validation(session, snapshot.id)
        assert report["status"] == "PASSED"
        assert report["metadata_fingerprint"] == snapshot.fingerprint
        assert report["metadata_collected_at"] == snapshot.collected_at

        (folder / "order_calc_profit_validation.ini").write_text(parity_text.replace("metadata_collected_at=2026.08.24 10:00:00", "metadata_collected_at=2026.08.24 09:59:59"))
        with pytest.raises(ValueError, match="not bound"):
            import_order_calc_validation(session, snapshot.id)

        (folder / "order_calc_profit_validation.ini").write_text(parity_text)
        (folder / "latest.ini").write_text(metadata_text.replace("volume_max=50", "volume_max=25"))
        with pytest.raises(ValueError, match="exact latest.ini"):
            import_order_calc_validation(session, snapshot.id)


def test_order_calc_margin_artifact_proves_exact_frozen_cfd_formula(tmp_path, monkeypatch):
    root=tmp_path/"common";folder=root/"ARKANA"/"broker_metadata";folder.mkdir(parents=True)
    metadata_text="\n".join([
        "schema_version=1","source=MT5","canonical_symbol=XAUUSD","broker_symbol=XAUUSD.m","digits=2","point=0.01","tick_size=0.01","tick_value=1","tick_value_profit=1","tick_value_loss=1","contract_size=100","volume_min=0.01","volume_max=50","volume_step=0.01","margin_initial=0","margin_maintenance=0","margin_rate_buy_initial=0.01","margin_rate_buy_maintenance=0","margin_rate_sell_initial=0.01","margin_rate_sell_maintenance=0","account_leverage=500","currency_base=XAU","currency_profit=USD","currency_margin=USD","trade_calc_mode=2","account_currency=USD","collected_at=2026.08.24 10:00:00",
    ])
    (folder/"latest.ini").write_text(metadata_text)
    parity="\n".join(["schema_version=1","source=MT5_ORDERCALCMARGIN","broker_symbol=XAUUSD.m","metadata_collected_at=2026.08.24 10:00:00","currency=USD","timestamp=2026.08.24 10:01:00","case=BUY_MIN|BUY|0.01|100|1|OK","case=SELL_MIN|SELL|0.01|100|1|OK","case=BUY_STEP|BUY|0.02|101|2.02|OK","case=SELL_STEP|SELL|0.02|99|1.98|OK"])
    (folder/"order_calc_margin_validation.ini").write_text(parity)
    monkeypatch.setattr(broker_metadata,"MT5_COMMON_FILES_ROOT",root)
    engine=create_engine(f"sqlite:///{tmp_path/'margin.db'}");Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    with Session() as session:
        snapshot,_=import_snapshot(session);report=import_order_calc_margin_validation(session,snapshot.id)
        assert report["status"]=="PASSED" and report["formula"]=="MT5_CFD_MODE_2_INITIAL_MARGIN_V1"
        (folder/"order_calc_margin_validation.ini").write_text(parity.replace("case=BUY_MIN|BUY|0.01|100|1|OK","case=BUY_MIN|BUY|0.01|100|2|OK"))
        assert import_order_calc_margin_validation(session,snapshot.id)["status"]=="FAILED"
        (folder/"order_calc_margin_validation.ini").write_text(parity.replace("case=BUY_MIN|BUY|0.01|100|1|OK","case=BUY_MIN|SELL|0.01|100|1|OK"))
        with pytest.raises(ValueError,match="case schema"):import_order_calc_margin_validation(session,snapshot.id)
        (folder/"order_calc_margin_validation.ini").write_text(parity.replace("case=BUY_STEP|BUY|0.02|101|2.02|OK","case=BUY_STEP|BUY|0.03|101|3.03|OK"))
        with pytest.raises(ValueError,match="case schema"):import_order_calc_margin_validation(session,snapshot.id)
        (folder/"order_calc_margin_validation.ini").write_text(parity.replace("case=SELL_STEP|SELL|0.02|99|1.98|OK","case=BUY_MIN|BUY|0.01|100|1|OK"))
        with pytest.raises(ValueError,match="exactly four unique"):import_order_calc_margin_validation(session,snapshot.id)
        (folder/"order_calc_margin_validation.ini").write_text(parity.replace("metadata_collected_at=2026.08.24 10:00:00","metadata_collected_at=2026.08.24 09:59:59"))
        with pytest.raises(ValueError,match="not bound"):import_order_calc_margin_validation(session,snapshot.id)
