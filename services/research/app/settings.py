from pathlib import Path
import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./arkana_metadata.db")
DATA_ROOT = Path(os.getenv("DATA_ROOT", "../../data/processed")).resolve()
MAX_BARS_PER_REQUEST = int(os.getenv("MAX_BARS_PER_REQUEST", "5000"))
MT5_COMMON_FILES_ROOT = Path(os.getenv("MT5_COMMON_FILES_ROOT", "../../data/mt5-common")).resolve()
HISTORICAL_SYNC_INTERVAL_SECONDS = int(os.getenv("HISTORICAL_SYNC_INTERVAL_SECONDS", "3600"))
HISTORICAL_SYNC_POLL_SECONDS = int(os.getenv("HISTORICAL_SYNC_POLL_SECONDS", "30"))
HISTORICAL_SYNC_RESPONSE_TIMEOUT_SECONDS = int(os.getenv("HISTORICAL_SYNC_RESPONSE_TIMEOUT_SECONDS", "300"))
# ARKANA_ENGINE emits a heartbeat on its configured 10-second reload timer.  Six
# missed intervals is a conservative operational-health boundary, not a trading rule.
EA_HEARTBEAT_CADENCE_SECONDS = int(os.getenv("EA_HEARTBEAT_CADENCE_SECONDS", "10"))
EA_HEARTBEAT_FRESHNESS_SECONDS = int(os.getenv("EA_HEARTBEAT_FRESHNESS_SECONDS", str(EA_HEARTBEAT_CADENCE_SECONDS * 6)))
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
AI_PROVIDER = os.getenv("AI_PROVIDER", "unconfigured").strip().lower()

def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Generic settings are the primary contract.  The legacy names below are read
# only as a migration bridge, never sent to browsers or persisted in records.
_LEGACY_KEY = (os.getenv("ZAI_API_KEY", "") if AI_PROVIDER == "zai" else
               os.getenv("META_MODEL_API_KEY", "") if AI_PROVIDER == "meta" else "")
_LEGACY_BASE_URL = (os.getenv("ZAI_BASE_URL", "") if AI_PROVIDER == "zai" else
                    os.getenv("META_MODEL_API_BASE_URL", "") if AI_PROVIDER == "meta" else "")
_LEGACY_MODEL = os.getenv("META_MODEL_ID", "") if AI_PROVIDER == "meta" else ""
AI_API_KEY = os.getenv("AI_API_KEY", "") or _LEGACY_KEY
AI_BASE_URL = os.getenv("AI_BASE_URL", "") or _LEGACY_BASE_URL
AI_MODEL_FAST = os.getenv("AI_MODEL_FAST") or _LEGACY_MODEL
AI_MODEL_REASONING = os.getenv("AI_MODEL_REASONING") or _LEGACY_MODEL
_PROFILE_DEFAULTS = {
    "zai": {"protocol": "openai_compatible", "endpoint_path": "/chat/completions", "json_mode": True, "thinking": True},
    "tencent": {"protocol": "openai_compatible", "endpoint_path": "/chat/completions", "json_mode": False, "thinking": False},
    "openrouter": {"protocol": "openai_compatible", "endpoint_path": "/chat/completions", "json_mode": True, "thinking": False},
    "groq": {"protocol": "openai_compatible", "endpoint_path": "/chat/completions", "json_mode": True, "thinking": False},
    "openai": {"protocol": "openai_compatible", "endpoint_path": "/chat/completions", "json_mode": True, "thinking": False},
    "anthropic": {"protocol": "anthropic_messages", "endpoint_path": "/messages", "json_mode": False, "thinking": False},
}
_PROFILE = _PROFILE_DEFAULTS.get(AI_PROVIDER, _PROFILE_DEFAULTS["openai"])
AI_PROTOCOL = (os.getenv("AI_PROTOCOL") or _PROFILE["protocol"]).strip().lower()
AI_ENDPOINT_PATH = os.getenv("AI_ENDPOINT_PATH") or _PROFILE["endpoint_path"]
AI_JSON_MODE = _bool("AI_JSON_MODE", _PROFILE["json_mode"])
AI_THINKING_ENABLED = _bool("AI_THINKING_ENABLED", _PROFILE["thinking"])
AI_AUTH_HEADER = os.getenv("AI_AUTH_HEADER") or ("x-api-key" if AI_PROTOCOL == "anthropic_messages" else "Authorization")
AI_AUTH_PREFIX = os.getenv("AI_AUTH_PREFIX") or ("" if AI_PROTOCOL == "anthropic_messages" else "Bearer ")
AI_EXTRA_HEADERS_JSON = os.getenv("AI_EXTRA_HEADERS_JSON") or ("{\"anthropic-version\":\"2023-06-01\"}" if AI_PROTOCOL == "anthropic_messages" else "{}")
AI_MONTHLY_BUDGET_USD = float(os.getenv("AI_MONTHLY_BUDGET_USD", "0"))
AI_REQUEST_LIMIT = int(os.getenv("AI_REQUEST_LIMIT", "100"))
AI_REQUEST_MAX_INPUT_TOKENS = int(os.getenv("AI_REQUEST_MAX_INPUT_TOKENS", "4000"))
# Structured rule-definition drafts can legitimately contain more than one
# typed rule.  800 is routinely truncated by otherwise healthy providers.
AI_REQUEST_MAX_OUTPUT_TOKENS = int(os.getenv("AI_REQUEST_MAX_OUTPUT_TOKENS", "1600"))
AI_REQUEST_MAX_COST_USD = float(os.getenv("AI_REQUEST_MAX_COST_USD", "0.05"))
# ARK-S23-01.  Every research endpoint mutates or exposes Owner evidence, and
# publication writes FILE_COMMON that the EA acts on.  An unset token is never
# treated as "open"; it fails closed on every route except /health.
RESEARCH_API_TOKEN = os.getenv("RESEARCH_API_TOKEN", "").strip()
# ARK-S23-04.  The service observes backups; it never writes them.  The host
# script owns BACKUP_ROOT and the service mounts it read-only.
BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", "../../backups")).resolve()
BACKUP_MAX_AGE_SECONDS = int(os.getenv("BACKUP_MAX_AGE_SECONDS", str(36 * 3600)))
DATASET_MAX_AGE_SECONDS = int(os.getenv("DATASET_MAX_AGE_SECONDS", str(14 * 24 * 3600)))
UNAUTHENTICATED_PATHS = frozenset({"/health"})
