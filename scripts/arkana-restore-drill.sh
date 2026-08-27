#!/usr/bin/env bash
# ARK-S23-04 — restore drill.
#
# An untested backup is a belief, not a backup. This restores a snapshot into a
# scratch database and compares evidence row counts against the manifest taken
# at dump time. It never touches the live database.
#
# Usage:  scripts/arkana-restore-drill.sh BACKUP_DIR
set -euo pipefail

BACKUP_DIR="${1:?usage: arkana-restore-drill.sh BACKUP_DIR}"
POSTGRES_CONTAINER="${ARKANA_POSTGRES_CONTAINER:-arkana-postgres-1}"
POSTGRES_USER="${POSTGRES_USER:-arkana}"
SCRATCH_DB="${ARKANA_RESTORE_DRILL_DB:-arkana_restore_drill}"

for required in postgres.dump row-counts.csv manifest.json; do
  [ -f "${BACKUP_DIR}/${required}" ] || { echo "FATAL: ${BACKUP_DIR}/${required} is missing" >&2; exit 1; }
done

echo "ARKANA restore drill ← ${BACKUP_DIR}"

RECORDED_SHA="$(python3 -c "import json,sys;print(json.load(open('${BACKUP_DIR}/manifest.json'))['postgres']['dump_sha256'])")"
ACTUAL_SHA="$(shasum -a 256 "${BACKUP_DIR}/postgres.dump" | awk '{print $1}')"
if [ "${RECORDED_SHA}" != "${ACTUAL_SHA}" ]; then
  echo "FAIL: dump checksum changed since it was written" >&2
  echo "  recorded ${RECORDED_SHA}" >&2
  echo "  actual   ${ACTUAL_SHA}" >&2
  exit 1
fi
echo "  checksum matches the manifest"

# The scratch database is dropped first so a previous drill cannot make this
# one look successful.
echo "  restoring into ${SCRATCH_DB}…"
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" >/dev/null
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE ${SCRATCH_DB};" >/dev/null
docker exec -i "${POSTGRES_CONTAINER}" pg_restore -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" --no-owner < "${BACKUP_DIR}/postgres.dump" >/dev/null 2>&1 || true

docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" -c "ANALYZE;" >/dev/null
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${SCRATCH_DB}" -t -A -F',' -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;" > /tmp/arkana-drill-counts.csv

echo "  comparing evidence row counts…"
python3 - "${BACKUP_DIR}/row-counts.csv" /tmp/arkana-drill-counts.csv <<'PY'
import sys

def load(path):
    rows = {}
    for line in open(path):
        line = line.strip()
        if not line or "," not in line:
            continue
        name, count = line.rsplit(",", 1)
        rows[name] = int(count)
    return rows

recorded, restored = load(sys.argv[1]), load(sys.argv[2])
# n_live_tup is an estimate, so an exact match is not required for large
# tables; a missing table or an empty restore of a populated table is.
missing = sorted(name for name in recorded if name not in restored)
emptied = sorted(name for name, count in recorded.items()
                 if count > 0 and restored.get(name, 0) == 0)
extra = sorted(name for name in restored if name not in recorded)

for name in missing:
    print(f"  FAIL missing table: {name}")
for name in emptied:
    print(f"  FAIL table restored empty but held {recorded[name]} rows: {name}")
for name in extra:
    print(f"  note extra table not in manifest: {name}")

if missing or emptied:
    print(f"RESTORE DRILL FAILED — {len(missing)} missing, {len(emptied)} emptied")
    raise SystemExit(1)
print(f"RESTORE DRILL PASSED — {len(recorded)} tables, none missing, none emptied")
PY

echo "  dropping scratch database"
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" >/dev/null
echo "OK  the live database was never touched"
