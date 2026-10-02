#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

echo "=== Starte Aktualisierung des Tennisverein-CMS ==="
if [ -d .git ]; then
    git pull --ff-only
fi

bash scripts/deploy.sh
echo "=== Update erfolgreich abgeschlossen! ==="
