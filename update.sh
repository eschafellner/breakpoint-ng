#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

echo "=== Starte Aktualisierung des Tennisverein-CMS ==="
bash scripts/deploy.sh "$@"
if [[ " $* " == *" --skip-public-check "* ]]; then
    echo "=== Update lokal abgeschlossen; öffentliche Website noch im Browser prüfen ==="
else
    echo "=== Update erfolgreich geprüft ==="
fi
