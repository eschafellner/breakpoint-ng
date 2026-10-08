#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [ "$#" -ne 2 ]; then
    echo "Verwendung: bash scripts/restore.sh <db.sql.gz> <media.tar.gz>" >&2
    exit 1
fi
DB_BACKUP="$1"
MEDIA_BACKUP="$2"
for archive in "$DB_BACKUP" "$MEDIA_BACKUP"; do
    if [ ! -f "$archive" ]; then
        echo "Fehler: Backup-Datei fehlt: $archive" >&2
        exit 1
    fi
done

if ! mkdir .deployment-lock 2>/dev/null; then
    echo "Fehler: Ein Deployment oder Restore läuft bereits (.deployment-lock)." >&2
    exit 1
fi
trap 'rmdir .deployment-lock' EXIT

compose=(docker compose -f docker-compose.prod.yml)
running=$("${compose[@]}" ps --status running --services)
while IFS= read -r service; do
    case "$service" in
        prepare|web|nginx|cloudflared|celery_worker|celery_beat)
            echo "Fehler: Anwendungsdienste zuerst stoppen. Datenbank und Redis dürfen weiterlaufen." >&2
            exit 1
            ;;
    esac
done <<< "$running"

echo "-> Prüfe beide Archive vor der Wiederherstellung..."
gzip -t -- "$DB_BACKUP"
"${compose[@]}" run --rm --no-deps --pull never -T --entrypoint python web scripts/media_archive.py validate < "$MEDIA_BACKUP"

echo "-> Stelle PostgreSQL transaktional wieder her..."
gunzip -c -- "$DB_BACKUP" | "${compose[@]}" exec -T db sh -c 'exec psql --set=ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" "$POSTGRES_DB"'

echo "-> Stelle das Docker-Medien-Volume wieder her..."
"${compose[@]}" run --rm --no-deps --pull never -T --entrypoint python web scripts/media_archive.py restore < "$MEDIA_BACKUP"

echo "Wiederherstellung abgeschlossen. Anwendung erst mit bash scripts/deploy.sh starten."
