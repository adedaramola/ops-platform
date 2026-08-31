#!/usr/bin/env bash
set -euo pipefail

# Local-only logical backup/restore exercise. AWS snapshot restore remains an operator-run procedure.
backup_user="${OPS_BACKUP_TEST_USER:-opsdesk}"
source_database="${OPS_BACKUP_TEST_DATABASE:-opsdesk_db}"
restore_database="opsdesk_restore_verification"

backup_directory="$(mktemp -d)"
backup_file="${backup_directory}/opsdesk.dump"

cleanup() {
  docker compose exec -T postgres dropdb --if-exists --username "${backup_user}" "${restore_database}" >/dev/null 2>&1 || true
  rm -f "${backup_file}"
  rmdir "${backup_directory}" 2>/dev/null || true
}
trap cleanup EXIT

docker compose exec -T postgres dropdb --if-exists --username "${backup_user}" "${restore_database}"
docker compose exec -T postgres pg_dump --format=custom --no-owner --no-privileges --username "${backup_user}" "${source_database}" >"${backup_file}"
docker compose exec -T postgres createdb --username "${backup_user}" "${restore_database}"
docker compose exec -T postgres pg_restore --exit-on-error --no-owner --no-privileges --username "${backup_user}" --dbname "${restore_database}" <"${backup_file}"

source_revision="$(docker compose exec -T postgres psql --quiet --tuples-only --no-align --username "${backup_user}" --dbname "${source_database}" --command 'SELECT version_num FROM alembic_version')"
restored_revision="$(docker compose exec -T postgres psql --quiet --tuples-only --no-align --username "${backup_user}" --dbname "${restore_database}" --command 'SELECT version_num FROM alembic_version')"
source_tables="$(docker compose exec -T postgres psql --quiet --tuples-only --no-align --username "${backup_user}" --dbname "${source_database}" --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")"
restored_tables="$(docker compose exec -T postgres psql --quiet --tuples-only --no-align --username "${backup_user}" --dbname "${restore_database}" --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")"

if [[ "${source_revision}" != "${restored_revision}" || "${source_tables}" != "${restored_tables}" ]]; then
  echo "Backup restore verification failed: schema metadata differs." >&2
  exit 1
fi

echo "Backup restore verified at migration ${restored_revision} with ${restored_tables} public tables."
