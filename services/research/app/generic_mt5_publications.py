"""ARK-S20-03 owner-authorized generic DEMO publication and MT5 acknowledgement.

The compiler output is written to an immutable checksum-addressed file first.
An atomically replaced manifest is the only activation pointer. The API never
owns OnTick and an acknowledgement can only be observed from FILE_COMMON.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_mt5_compiler import (
    ADAPTER_CAPABILITY_ID,
    COMPILER_VERSION,
    STATUS_READY as COMPILATION_READY,
    parse_config,
    validation_report as compilation_validation,
)
from .models import GenericMt5Compilation, GenericMt5Publication
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_MT5_DEMO_PUBLICATION_V1"
AUTHORIZATION_PHRASE = "AUTHORIZE_GENERIC_DEMO_PUBLICATION_V1"
STATUS_WAITING = "DEMO_WAITING_FOR_MT5"
STATUS_ACTIVE = "DEMO_ACKNOWLEDGED"
AUTHORIZATION_MAX_AGE_SECONDS = 300
MANIFEST_RELATIVE = Path("ARKANA") / "generic" / "publication.ini"
ACK_RELATIVE = Path("ARKANA") / "generic" / "acknowledgement.csv"
MANIFEST_FIELDS = (
    "publication_protocol_version", "publication_id", "target_environment",
    "target_account_login", "target_account_server", "target_reference",
    "broker_symbol", "strategy_version_id", "compiler_protocol_version",
    "adapter_capability_id", "config_checksum", "config_file", "published_at",
)
ACK_FIELDS = (
    "timestamp", "publication_id", "environment", "account_login",
    "account_server", "broker_symbol", "strategy_version_id",
    "compiler_protocol_version", "adapter_capability_id", "config_checksum",
    "publication_checksum", "decision",
)
_publication_lock = Lock()


def adapter_root() -> Path:
    from .settings import MT5_COMMON_FILES_ROOT
    return MT5_COMMON_FILES_ROOT


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)


def _parse_authorized_at(value: object, now: datetime) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("authorized_at must be an explicit UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("authorized_at must be an explicit UTC ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("authorized_at must include a UTC offset")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(seconds=30):
        raise ValueError("authorization timestamp is in the future")
    if now - parsed > timedelta(seconds=AUTHORIZATION_MAX_AGE_SECONDS):
        raise ValueError("publication authorization request is stale")
    return parsed


def _identity(payload: dict[str, Any]) -> dict[str, str]:
    login = str(payload.get("target_account_login", "")).strip()
    server = str(payload.get("target_account_server", "")).strip()
    reference = str(payload.get("target_reference", "")).strip()
    environment = str(payload.get("target_environment", "")).strip()
    if not login.isdigit() or login != str(int(login)) or int(login) <= 0:
        raise ValueError("target_account_login must be a canonical positive integer string")
    if not server or len(server) > 128 or any(character in server for character in "\r\n,="):
        raise ValueError("target_account_server is required and cannot contain serialization delimiters")
    if not reference or len(reference) > 160 or any(character in reference for character in "\r\n="):
        raise ValueError("target_reference is required and cannot contain serialization delimiters")
    if environment != "DEMO":
        raise ValueError("only exact DEMO publication is supported; LIVE remains locked")
    return {
        "target_account_login": login,
        "target_account_server": server,
        "target_reference": reference,
        "target_environment": environment,
    }


def _exact_compilation(session: Session, compilation_id: str) -> tuple[GenericMt5Compilation, dict[str, str]]:
    item = session.get(GenericMt5Compilation, compilation_id)
    if not item:
        raise ValueError("generic MT5 compilation is unavailable")
    values = parse_config(item.config_text)
    configuration = {key: value for key, value in values.items() if key != "checksum"}
    if values["checksum"] != item.config_checksum or configuration != item.configuration:
        raise ValueError("stored generic MT5 compilation differs from exact canonical bytes")
    report = compilation_validation(session, item.generic_demo_contract_id)
    if report.get("status") != COMPILATION_READY or report.get("config_checksum") != item.config_checksum or report.get("config_text") != item.config_text:
        raise ValueError("generic MT5 compilation is no longer exactly eligible")
    if item.compiler_protocol_version != COMPILER_VERSION or item.adapter_capability_id != ADAPTER_CAPABILITY_ID:
        raise ValueError("generic MT5 compiler protocol or adapter capability is unsupported")
    return item, configuration


def _adapter_preflight(root: Path) -> list[str]:
    directory = root / MANIFEST_RELATIVE.parent
    token = sha256(str(directory).encode()).hexdigest()
    probe_id = uuid4().hex
    probe = directory / f".publication-preflight-{probe_id}"
    temporary = directory / f".publication-preflight-{probe_id}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(token, encoding="utf-8")
        temporary.replace(probe)
        if probe.read_text(encoding="utf-8") != token:
            raise OSError("atomic readback differs")
        probe.unlink()
        return []
    except OSError as error:
        temporary.unlink(missing_ok=True)
        probe.unlink(missing_ok=True)
        return [f"FILE_COMMON atomic write/readback failed: {error}"]


def preflight(session: Session, compilation_id: str, payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = _utc(now)
    errors: list[str] = []
    item: GenericMt5Compilation | None = None
    configuration: dict[str, str] = {}
    identity: dict[str, str] = {}
    try:
        if payload.get("authorization") != AUTHORIZATION_PHRASE:
            raise ValueError(f"authorization must equal {AUTHORIZATION_PHRASE}")
        _parse_authorized_at(payload.get("authorized_at"), current)
        identity = _identity(payload)
        item, configuration = _exact_compilation(session, compilation_id)
        if configuration["allowed_environment"] != identity["target_environment"]:
            raise ValueError("compiled environment differs from publication target")
    except ValueError as error:
        errors.append(str(error))
    root = adapter_root()
    errors.extend(_adapter_preflight(root))
    return {
        "status": "READY_TO_PUBLISH" if not errors else "PREFLIGHT_FAILED",
        "ready": not errors,
        "issues": errors,
        "binding": {
            "compilation_id": item.id if item else compilation_id,
            "target_environment": identity.get("target_environment"),
            "target_account_login": identity.get("target_account_login"),
            "target_account_server": identity.get("target_account_server"),
            "broker_symbol": configuration.get("broker_symbol"),
            "strategy_version_id": configuration.get("strategy_version_id"),
            "compiler_protocol_version": configuration.get("compiler_protocol_version"),
            "adapter_capability_id": configuration.get("adapter_capability_id"),
            "config_checksum": item.config_checksum if item else None,
        },
        "transport": {
            "root": str(root), "manifest_path": str(root / MANIFEST_RELATIVE),
            "checksum_addressed_config": True, "atomic_manifest_activation": True,
            "mt5_available": (root / ACK_RELATIVE).exists(),
        },
        "safety_boundary": {"read_only_domain_validation": True, "preflight_probe_only": True, "configuration_published": False, "mt5_acknowledged": False, "api_owns_on_tick": False, "order_or_trade_created": False, "live_authorized": False},
    }


def _manifest(values: dict[str, str]) -> tuple[str, str]:
    if set(values) != set(MANIFEST_FIELDS) or any(not value or "\n" in value or "\r" in value for value in values.values()):
        raise ValueError("publication manifest has missing, unsupported, or unsafe fields")
    payload = "\n".join(f"{name}={values[name]}" for name in MANIFEST_FIELDS) + "\n"
    checksum = sha256(payload.encode()).hexdigest()
    return payload + f"publication_checksum={checksum}\n", checksum


def parse_manifest(text: object) -> dict[str, str]:
    if not isinstance(text, str):
        raise ValueError("publication manifest text is required")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.count("=") != 1:
            raise ValueError("publication manifest serialization is invalid")
        key, value = line.split("=", 1)
        if key in values or key not in {*MANIFEST_FIELDS, "publication_checksum"} or not value:
            raise ValueError("publication manifest contains unknown, duplicated, or empty fields")
        values[key] = value
    if set(values) != {*MANIFEST_FIELDS, "publication_checksum"}:
        raise ValueError("publication manifest is missing mandatory fields")
    expected, checksum = _manifest({key: values[key] for key in MANIFEST_FIELDS})
    if text != expected or values["publication_checksum"] != checksum:
        raise ValueError("publication manifest checksum or canonical serialization differs")
    if values["publication_protocol_version"] != PROTOCOL_VERSION or values["target_environment"] != "DEMO":
        raise ValueError("publication manifest protocol or environment is unsupported")
    if values["compiler_protocol_version"] != COMPILER_VERSION or values["adapter_capability_id"] != ADAPTER_CAPABILITY_ID:
        raise ValueError("publication compiler protocol or adapter is unsupported")
    if not values["target_account_login"].isdigit() or values["target_account_login"] != str(int(values["target_account_login"])):
        raise ValueError("publication account identity is non-canonical")
    if len(values["config_checksum"]) != 64 or values["config_file"] != f"ARKANA/generic/config-{values['config_checksum']}.ini":
        raise ValueError("publication config path is not checksum-addressed")
    return values


def _atomic_write(path: Path, content: str, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{token}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publish(session: Session, compilation_id: str, payload: dict[str, Any], *, now: datetime | None = None) -> tuple[GenericMt5Publication, bool]:
    current = _utc(now)
    report = preflight(session, compilation_id, payload, now=current)
    if not report["ready"]:
        raise ValueError("PREFLIGHT_FAILED: " + "; ".join(report["issues"]))
    compilation, configuration = _exact_compilation(session, compilation_id)
    identity = _identity(payload)
    stable_request = {"protocol_version": PROTOCOL_VERSION, "compilation_id": compilation.id, **identity}
    fingerprint = sha256(canonical_json(stable_request).encode()).hexdigest()
    existing = session.scalar(select(GenericMt5Publication).where(GenericMt5Publication.fingerprint == fingerprint))
    if existing:
        return existing, True
    publication = GenericMt5Publication(
        compilation_id=compilation.id, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION,
        authorization_fingerprint=sha256(AUTHORIZATION_PHRASE.encode()).hexdigest(),
        target_account_login=identity["target_account_login"], target_account_server=identity["target_account_server"],
        target_reference=identity["target_reference"], target_environment="DEMO",
        broker_symbol=configuration["broker_symbol"], config_checksum=compilation.config_checksum,
        publication_checksum="0" * 64, config_path="", manifest_path="", manifest={}, status="PUBLISHING",
    )
    session.add(publication)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(GenericMt5Publication).where(GenericMt5Publication.fingerprint == fingerprint))
        if not winner:
            raise
        return winner, True
    published_at = current.isoformat().replace("+00:00", "Z")
    relative_config = Path("ARKANA") / "generic" / f"config-{compilation.config_checksum}.ini"
    manifest_values = {
        "publication_protocol_version": PROTOCOL_VERSION, "publication_id": publication.id,
        "target_environment": "DEMO", "target_account_login": identity["target_account_login"],
        "target_account_server": identity["target_account_server"], "target_reference": identity["target_reference"],
        "broker_symbol": configuration["broker_symbol"], "strategy_version_id": configuration["strategy_version_id"],
        "compiler_protocol_version": compilation.compiler_protocol_version,
        "adapter_capability_id": compilation.adapter_capability_id, "config_checksum": compilation.config_checksum,
        "config_file": relative_config.as_posix(), "published_at": published_at,
    }
    manifest_text, publication_checksum = _manifest(manifest_values)
    root = adapter_root(); config_path = root / relative_config; manifest_path = root / MANIFEST_RELATIVE
    try:
        with _publication_lock:
            if config_path.exists() and config_path.read_text(encoding="utf-8") != compilation.config_text:
                raise OSError("checksum-addressed config already exists with divergent bytes")
            if not config_path.exists():
                _atomic_write(config_path, compilation.config_text, publication.id)
            if config_path.read_text(encoding="utf-8") != compilation.config_text:
                raise OSError("published config readback differs")
            _atomic_write(manifest_path, manifest_text, publication.id)
            if parse_manifest(manifest_path.read_text(encoding="utf-8"))["publication_checksum"] != publication_checksum:
                raise OSError("published manifest readback differs")
    except (OSError, ValueError) as error:
        publication.status = "PUBLICATION_FAILED"
        session.commit()
        raise ValueError(f"atomic FILE_COMMON publication failed: {error}") from error
    publication.publication_checksum = publication_checksum
    publication.config_path = str(config_path)
    publication.manifest_path = str(manifest_path)
    publication.manifest = {**manifest_values, "publication_checksum": publication_checksum}
    publication.status = STATUS_WAITING
    publication.published_at = current.replace(tzinfo=None)
    session.commit(); session.refresh(publication)
    return publication, False


def _ack_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
        reader = csv.DictReader(StringIO(content))
        if tuple(reader.fieldnames or ()) != ACK_FIELDS:
            return []
        return [dict(row) for row in reader if set(row) == set(ACK_FIELDS) and all(isinstance(value, str) for value in row.values())]
    except (OSError, UnicodeError, csv.Error):
        return []


def poll_ack(session: Session, item: GenericMt5Publication) -> GenericMt5Publication:
    if item.status == STATUS_ACTIVE:
        return item
    if item.status != STATUS_WAITING:
        raise ValueError("publication is not waiting for MT5 acknowledgement")
    expected = {
        "publication_id": item.id, "environment": "DEMO", "account_login": item.target_account_login,
        "account_server": item.target_account_server, "broker_symbol": item.broker_symbol,
        "strategy_version_id": item.manifest["strategy_version_id"],
        "compiler_protocol_version": COMPILER_VERSION, "adapter_capability_id": ADAPTER_CAPABILITY_ID,
        "config_checksum": item.config_checksum, "publication_checksum": item.publication_checksum,
        "decision": "GENERIC_CONFIG_LOADED",
    }
    for row in reversed(_ack_rows(adapter_root() / ACK_RELATIVE)):
        if all(row.get(key) == value for key, value in expected.items()):
            item.status = STATUS_ACTIVE
            item.acknowledgement = {key: row[key] for key in ACK_FIELDS}
            item.acknowledged_at = datetime.utcnow()
            session.commit(); session.refresh(item)
            return item
    return item


def serialize(item: GenericMt5Publication) -> dict[str, Any]:
    return {
        "id": item.id, "compilation_id": item.compilation_id, "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version, "target_account_login": item.target_account_login,
        "target_account_server": item.target_account_server, "target_reference": item.target_reference,
        "target_environment": item.target_environment, "broker_symbol": item.broker_symbol,
        "config_checksum": item.config_checksum, "publication_checksum": item.publication_checksum,
        "config_path": item.config_path, "manifest_path": item.manifest_path, "manifest": item.manifest,
        "status": item.status, "acknowledgement": item.acknowledgement,
        "published_at": item.published_at.isoformat() + "Z" if item.published_at else None,
        "acknowledged_at": item.acknowledged_at.isoformat() + "Z" if item.acknowledged_at else None,
        "created_at": item.created_at.isoformat() + "Z",
        "safety_boundary": {"demo_only": True, "mt5_owns_on_tick": True, "api_places_orders": False, "live_authorized": False},
        "warning": "Publication and exact acknowledgement authorize only this bounded DEMO configuration. They do not prove profitability or authorize LIVE.",
    }


def list_all(session: Session) -> list[GenericMt5Publication]:
    return list(session.scalars(select(GenericMt5Publication).order_by(GenericMt5Publication.created_at.desc())).all())
