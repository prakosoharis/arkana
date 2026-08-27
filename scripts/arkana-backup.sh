#!/usr/bin/env bash
# ARK-S23-04 — ARKANA evidence backup.
#
# The research service deliberately does not run this. pg_dump lives in the
# postgres container, and a service that could overwrite its own backups is not
# a backup. This script runs on the host; the service only observes the
# manifest it writes and reports staleness.
#
# Usage:  scripts/arkana-backup.sh [BACKUP_ROOT]
set -euo pipefail

BACKUP_ROOT="${1:-${ARKANA_BACKUP_ROOT:-./backups}}"
POSTGRES_CONTAINER="${ARKANA_POSTGRES_CONTAINER:-arkana-postgres-1}"
POSTGRES_USER="${POSTGRES_USER:-arkana}"
POSTGRES_DB="${POSTGRES_DB:-arkana}"
DATA_ROOT="${ARKANA_DATA_ROOT:-./data}"
RETAIN="${ARKANA_BACKUP_RETAIN:-7}"

# Backups are named by content time, not by run time, so a re-run cannot
# silently overwrite an earlier distinct snapshot.
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DEST="${BACKUP_ROOT}/${STAMP}"
mkdir -p "${DEST}"

echo "ARKANA backup → ${DEST}"

if ! docker exec "${POSTGRES_CONTAINER}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
  echo "FATAL: ${POSTGRES_CONTAINER} is not accepting connections; refusing to write an empty backup" >&2
  rmdir "${DEST}" 2>/dev/null || true
  exit 1
fi

# -Fc is the compressed custom format; pg_restore can read it selectively.
echo "  postgres dump…"
docker exec "${POSTGRES_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc > "${DEST}/postgres.dump"

DUMP_BYTES="$(wc -c < "${DEST}/postgres.dump" | tr -d ' ')"
if [ "${DUMP_BYTES}" -lt 1024 ]; then
  echo "FATAL: dump is ${DUMP_BYTES} bytes; refusing to record a truncated backup" >&2
  rm -rf "${DEST}"
  exit 1
fi
DUMP_SHA="$(shasum -a 256 "${DEST}/postgres.dump" | awk '{print $1}')"

# Evidence row counts travel with the dump so a restore can be proven complete
# rather than merely "it ran without error".
echo "  evidence row counts…"
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -F',' -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;" > "${DEST}/row-counts.csv"

# Parquet is large and regenerable from MT5 exports, so the manifest records
# fingerprints rather than copying 450 MB on every run. A restore that finds a
# missing or altered file will therefore still be detected.
echo "  parquet manifest…"
if [ -d "${DATA_ROOT}" ]; then
  find "${DATA_ROOT}" -name '*.parquet' -type f -exec shasum -a 256 {} \; \
    | sort -k2 > "${DEST}/parquet-manifest.txt" || true
else
  : > "${DEST}/parquet-manifest.txt"
fi
PARQUET_COUNT="$(wc -l < "${DEST}/parquet-manifest.txt" | tr -d ' ')"

cat > "${DEST}/manifest.json" <<JSON
{
  "protocol_version": "ARKANA_BACKUP_V1",
  "created_at": "${STAMP}",
  "postgres": {
    "container": "${POSTGRES_CONTAINER}",
    "database": "${POSTGRES_DB}",
    "dump_bytes": ${DUMP_BYTES},
    "dump_sha256": "${DUMP_SHA}",
    "format": "pg_dump -Fc"
  },
  "parquet": { "file_count": ${PARQUET_COUNT}, "manifest": "parquet-manifest.txt" },
  "row_counts": "row-counts.csv",
  "restore_drill": "scripts/arkana-restore-drill.sh ${DEST}"
}
JSON

# The pointer is written last, so a crash mid-backup never advertises a
# partial snapshot as the latest good one.
cp "${DEST}/manifest.json" "${BACKUP_ROOT}/latest.json"

echo "  retention: keeping ${RETAIN} most recent"
ls -1d "${BACKUP_ROOT}"/*/ 2>/dev/null | sort -r | tail -n +"$((RETAIN + 1))" | while read -r old; do
  echo "    removing $(basename "${old}")"
  rm -rf "${old}"
done

echo "OK  ${DUMP_BYTES} bytes  sha256 ${DUMP_SHA}"
echo "Verify it with: scripts/arkana-restore-drill.sh ${DEST}"
