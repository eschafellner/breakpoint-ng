#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

echo "=== Starte Aktualisierung des Tennisverein-CMS ==="
if [ -d .git ]; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "Fehler: Lokale Änderungen vorhanden. Vor dem Update committen oder sichern." >&2
        exit 1
    fi
    git pull --ff-only
fi

bash scripts/deploy.sh
echo "=== Update erfolgreich abgeschlossen! ==="
