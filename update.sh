#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--skip-public-check" ]; }; then
    echo "Verwendung: bash update.sh [--skip-public-check]" >&2
    exit 2
fi

echo "=== Starte Aktualisierung des Tennisverein-CMS ==="
if [ -d .git ]; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "Fehler: Lokale Änderungen vorhanden. Vor dem Update committen oder sichern." >&2
        exit 1
    fi
    git pull --ff-only
fi

bash scripts/deploy.sh "$@"
if [ "${1:-}" = "--skip-public-check" ]; then
    echo "=== Update lokal abgeschlossen; öffentliche Website noch im Browser prüfen ==="
else
    echo "=== Update erfolgreich geprüft ==="
fi
