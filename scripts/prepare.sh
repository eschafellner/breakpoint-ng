#!/bin/sh
set -eu

echo "-> Führe Datenbank-Migrationen aus..."
python manage.py migrate --noinput
echo "-> Sammle versionierte statische Dateien..."
python manage.py collectstatic --noinput
python manage.py shell -c 'from django.contrib.staticfiles.storage import staticfiles_storage; name = staticfiles_storage.stored_name("css/styles.css"); assert staticfiles_storage.exists(name), "Gesammeltes Stylesheet fehlt"; print("Stylesheet bereit:", name)'
