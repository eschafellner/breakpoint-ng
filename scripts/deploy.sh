#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

compose=(docker compose -f docker-compose.prod.yml)
"${compose[@]}" config --quiet

echo "-> Baue das Anwendungsimage neu..."
"${compose[@]}" build prepare

echo "-> Starte Datenbank und Redis..."
"${compose[@]}" up -d --wait --wait-timeout 120 db redis

# A shared static volume and schema changes require a maintenance window.
# Stop all application services before modifying either; preserve data volumes.
echo "-> Beginne Wartungsfenster..."
"${compose[@]}" stop cloudflared nginx celery_beat celery_worker web

echo "-> Bereite Datenbank und statische Dateien vor..."
"${compose[@]}" up -d --no-deps --force-recreate prepare
prepare_id=$("${compose[@]}" ps -a -q prepare)
prepare_exit=$(docker wait "$prepare_id")
"${compose[@]}" logs --no-color prepare
if [ "$prepare_exit" != "0" ]; then
    echo "Fehler: Vorbereitung fehlgeschlagen. Anwendungsdienste bleiben gestoppt." >&2
    exit 1
fi

echo "-> Starte und prüfe Anwendung und Nginx..."
"${compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 120 web
"${compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 120 nginx
"${compose[@]}" exec -T nginx nginx -t
"${compose[@]}" exec -T web python scripts/check_deployment.py

echo "-> Starte Hintergrunddienste und Cloudflare Tunnel..."
"${compose[@]}" up -d --no-deps --force-recreate celery_worker celery_beat cloudflared
echo "=== Deployment erfolgreich geprüft ==="
