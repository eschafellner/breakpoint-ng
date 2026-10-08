#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

skip_public=0
update_infrastructure=0
requested_image=""
usage() {
    echo "Verwendung: bash scripts/deploy.sh [VERSION|IMAGE] [--skip-public-check] [--update-infrastructure]" >&2
}
for argument in "$@"; do
    case "$argument" in
        --skip-public-check) skip_public=1 ;;
        --update-infrastructure) update_infrastructure=1 ;;
        --*) usage; exit 2 ;;
        *)
            if [ -n "$requested_image" ]; then usage; exit 2; fi
            requested_image="$argument"
            ;;
    esac
done

version_pattern='^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$'
valid_release_image() {
    local image="$1" tag repository
    if [[ "$image" =~ ^[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}$ ]]; then
        return 0
    fi
    tag="${image##*:}"
    repository="${image%:*}"
    [[ "$image" == *:* ]] && [[ "$repository" =~ ^[a-z0-9][a-z0-9./:_-]*$ ]] && [[ "$tag" =~ $version_pattern ]]
}
if [ -n "$requested_image" ]; then
    if [[ "$requested_image" =~ $version_pattern ]]; then
        requested_image="ghcr.io/eschafellner/breakpoint-ng:$requested_image"
    fi
    if ! valid_release_image "$requested_image"; then
        echo "Fehler: Eine Version wie v0.1.0 oder ein Image mit :v0.1.0 bzw. @sha256:… angeben." >&2
        exit 2
    fi
    if [ ! -f .env ]; then
        echo "Fehler: Zuerst .env anhand von .env.example einrichten (siehe DEPLOYMENT.md)." >&2
        exit 1
    fi
    export APP_IMAGE="$requested_image"
fi

compose=(docker compose -f docker-compose.prod.yml)
if ! mkdir .deployment-lock 2>/dev/null; then
    echo "Fehler: Ein Deployment läuft bereits (.deployment-lock)." >&2
    exit 1
fi
maintenance_started=0
env_pending=""
cleanup() {
    result=$?
    if [ "$result" -ne 0 ] && [ "$maintenance_started" -eq 1 ]; then
        "${compose[@]}" stop cloudflared || true
        echo "Deployment fehlgeschlagen. Tunnel wurde zum Stoppen aufgefordert; Status und Logs prüfen." >&2
        echo "Diagnose: docker compose -f docker-compose.prod.yml logs --tail=100 prepare web nginx cloudflared" >&2
    fi
    if [ -n "$env_pending" ]; then rm -f -- "$env_pending"; fi
    rmdir .deployment-lock
    exit "$result"
}
trap cleanup EXIT
"${compose[@]}" config --quiet
# `config --images prepare` also lists dependency images (PostgreSQL/Redis).
# Read only prepare's image from Compose's canonical YAML without printing its
# environment, which contains credentials. This needs no Python/jq on the host.
APP_IMAGE=$("${compose[@]}" config prepare | awk '
    /^  prepare:$/ { in_prepare = 1; next }
    /^  [a-zA-Z0-9_-]+:$/ { in_prepare = 0 }
    in_prepare && /^    image: / { sub(/^    image: /, ""); print }
')
if ! valid_release_image "$APP_IMAGE"; then
    echo "Fehler: APP_IMAGE muss eine Version wie :v0.1.0 oder einen SHA256-Digest enthalten; kein latest." >&2
    exit 1
fi
export APP_IMAGE

echo "-> Lade Release-Image: $APP_IMAGE"
"${compose[@]}" pull prepare

echo "-> Prüfe öffentliche Domain vor dem Wartungsfenster..."
"${compose[@]}" run --rm --no-deps --pull never -T --entrypoint python prepare scripts/check_deployment.py --validate-config

if [ "$update_infrastructure" -eq 1 ]; then
    echo "-> Lade die ausdrücklich ausgewählten Nginx- und Tunnel-Versionen..."
    "${compose[@]}" pull nginx cloudflared
else
    echo "-> Lade Infrastruktur-Images nur, falls sie lokal fehlen..."
    "${compose[@]}" pull --policy missing nginx cloudflared
fi
"${compose[@]}" pull --policy missing db redis

# Remember the selected release before migrations. A failed deployment must retry
# the same target; silently switching back could conflict with a changed schema.
if [ -n "$requested_image" ]; then
    umask 077
    env_pending=$(mktemp .env.release.XXXXXX)
    awk -v image="$APP_IMAGE" '
        /^[[:space:]]*(export[[:space:]]+)?APP_IMAGE[[:space:]]*=/ {
            if (!written++) print "APP_IMAGE=" image
            next
        }
        { print }
        END { if (!written) print "APP_IMAGE=" image }
    ' .env > "$env_pending"
    mv -- "$env_pending" .env
    env_pending=""
    echo "-> Ausgewähltes Release in .env gespeichert."
fi

echo "-> Starte Datenbank und Redis..."
"${compose[@]}" up -d --no-build --pull never --wait --wait-timeout 120 db redis

# A shared static volume and schema changes require a maintenance window.
# Stop all application services before modifying either; preserve data volumes.
echo "-> Beginne Wartungsfenster..."
maintenance_started=1
"${compose[@]}" stop cloudflared nginx celery_beat celery_worker web

echo "-> Sichere Datenbank und Medien-Volume vor Migrationen..."
bash scripts/backup.sh

echo "-> Bereite Datenbank und statische Dateien vor..."
"${compose[@]}" up -d --no-deps --no-build --pull never --force-recreate prepare
prepare_id=$("${compose[@]}" ps -a -q prepare)
prepare_exit=$(docker wait "$prepare_id")
"${compose[@]}" logs --no-color prepare
if [ "$prepare_exit" != "0" ]; then
    echo "Fehler: Vorbereitung fehlgeschlagen. Anwendungsdienste bleiben gestoppt." >&2
    exit 1
fi

echo "-> Starte und prüfe Anwendung und Nginx..."
"${compose[@]}" up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 web
"${compose[@]}" up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 nginx
"${compose[@]}" exec -T nginx nginx -t
"${compose[@]}" exec -T web python scripts/check_deployment.py

echo "-> Starte Hintergrunddienste und Cloudflare Tunnel..."
"${compose[@]}" up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 celery_worker celery_beat
"${compose[@]}" up -d --no-deps --no-build --pull never cloudflared
"${compose[@]}" exec -T web python scripts/check_tunnel.py
echo "-> Prüfe das Tunnelziel aus dem Netzwerk von cloudflared..."
"${compose[@]}" run --rm --no-deps --pull never -T tunnel_probe
if [ "$skip_public" -eq 1 ]; then
    echo "=== Lokale Prüfungen bestanden; öffentliche Website NICHT geprüft ==="
    echo "Vereinsadresse im Browser prüfen. Ein Healthy-Tunnel bestätigt keine erreichbare Website."
else
    echo "-> Prüfe öffentliche HTTPS-Adresse über Cloudflare..."
    "${compose[@]}" exec -T web python scripts/check_deployment.py --public
    echo "=== Deployment erfolgreich geprüft ==="
fi
