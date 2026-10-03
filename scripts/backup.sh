#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
umask 077

compose=(docker compose -f docker-compose.prod.yml)
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")_$$
mkdir -p -- "$BACKUP_DIR"
DB_FILE="$BACKUP_DIR/db_backup_${TIMESTAMP}.sql.gz"
MEDIA_FILE="$BACKUP_DIR/media_backup_${TIMESTAMP}.tar.gz"
db_partial="$DB_FILE.part"
media_partial="$MEDIA_FILE.part"
trap 'rm -f -- "$db_partial" "$media_partial"' EXIT

echo "-> Sichere PostgreSQL..."
"${compose[@]}" exec -T db sh -c 'exec pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$db_partial"
gzip -t -- "$db_partial"

echo "-> Sichere das Docker-Medien-Volume..."
"${compose[@]}" run --rm --no-deps -T --entrypoint python web scripts/media_archive.py backup > "$media_partial"
"${compose[@]}" run --rm --no-deps -T --entrypoint python web scripts/media_archive.py validate < "$media_partial"

mv -- "$db_partial" "$DB_FILE"
mv -- "$media_partial" "$MEDIA_FILE"
echo "Backup erfolgreich: $DB_FILE und $MEDIA_FILE"
echo "Beide Dateien sowie .env separat außerhalb des Servers sichern."
