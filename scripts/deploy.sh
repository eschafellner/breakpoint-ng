#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

skip_public=0
case "${1:-}" in
    "") ;;
    --skip-public-check) skip_public=1 ;;
    *) echo "Verwendung: bash scripts/deploy.sh [--skip-public-check]" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    echo "Fehler: Zu viele Argumente." >&2
    exit 2
fi

compose=(docker compose -f docker-compose.prod.yml)
if ! mkdir .deployment-lock 2>/dev/null; then
    echo "Fehler: Ein Deployment läuft bereits (.deployment-lock)." >&2
    exit 1
fi
maintenance_started=0
cleanup() {
    result=$?
    if [ "$result" -ne 0 ] && [ "$maintenance_started" -eq 1 ]; then
        "${compose[@]}" stop cloudflared || true
        echo "Deployment fehlgeschlagen. Tunnel wurde zum Stoppen aufgefordert; Status und Logs prüfen." >&2
        echo "Diagnose: docker compose -f docker-compose.prod.yml logs --tail=100 prepare web nginx cloudflared" >&2
    fi
    rmdir .deployment-lock
    exit "$result"
}
trap cleanup EXIT
"${compose[@]}" config --quiet

echo "-> Baue das Anwendungsimage neu..."
"${compose[@]}" build prepare

echo "-> Prüfe öffentliche Domain vor dem Wartungsfenster..."
"${compose[@]}" run --rm --no-deps -T --entrypoint python prepare scripts/check_deployment.py --validate-config

echo "-> Lade Nginx- und Tunnel-Images vor dem Wartungsfenster..."
"${compose[@]}" pull nginx cloudflared

echo "-> Starte Datenbank und Redis..."
"${compose[@]}" up -d --wait --wait-timeout 120 db redis

# A shared static volume and schema changes require a maintenance window.
# Stop all application services before modifying either; preserve data volumes.
echo "-> Beginne Wartungsfenster..."
maintenance_started=1
"${compose[@]}" stop cloudflared nginx celery_beat celery_worker web

echo "-> Sichere Datenbank und Medien-Volume vor Migrationen..."
bash scripts/backup.sh

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
"${compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 120 celery_worker celery_beat
"${compose[@]}" up -d --no-deps --force-recreate cloudflared
"${compose[@]}" exec -T web python scripts/check_tunnel.py
echo "-> Prüfe das Tunnelziel aus dem Netzwerk von cloudflared..."
"${compose[@]}" run --rm --no-deps -T tunnel_probe
if [ "$skip_public" -eq 1 ]; then
    echo "=== Lokale Prüfungen bestanden; öffentliche Website NICHT geprüft ==="
    echo "Vereinsadresse im Browser prüfen. Ein Healthy-Tunnel bestätigt keine erreichbare Website."
else
    echo "-> Prüfe öffentliche HTTPS-Adresse über Cloudflare..."
    "${compose[@]}" exec -T web python scripts/check_deployment.py --public
    echo "=== Deployment erfolgreich geprüft ==="
fi
