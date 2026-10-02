#!/bin/bash
# ========================================================
# TC Musterdorf – Update-Skript
# Automatisches Einspielen von Aktualisierungen und Migrationen
# ========================================================

set -e

echo "=== Starte Aktualisierung des Tennisverein-CMS ==="

# 1. Neuesten Code abrufen
if [ -d ".git" ]; then
    echo "-> Ziehe neueste Version aus dem Git-Repository..."
    git pull origin main || git pull
fi

# 2. Docker Images aktualisieren und neu bauen
echo "-> Baue Docker-Container neu..."
docker compose -f docker-compose.prod.yml build web celery_worker celery_beat

# 3. Container im Hintergrund neustarten
echo "-> Starte Container neu..."
docker compose -f docker-compose.prod.yml up -d

# 4. Datenbank-Migrationen ausführen
echo "-> Führe Datenbank-Migrationen aus..."
docker compose -f docker-compose.prod.yml exec web python manage.py migrate --noinput

# 5. Statische Dateien sammeln
echo "-> Sammle statische Dateien..."
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

echo "=== Update erfolgreich abgeschlossen! ==="
