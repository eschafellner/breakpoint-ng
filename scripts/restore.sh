#!/bin/bash
# ========================================================
# TC Musterdorf – Restore-Skript
# Stellt Datenbank und Medien aus einem Backup wieder her
# ========================================================

set -e

if [ -z "$1" ]; then
    echo "Verwendung: $0 <pfad_zur_db_backup_datei.sql.gz> [pfad_zur_media_datei.tar.gz]"
    exit 1
fi

DB_BACKUP="$1"
MEDIA_BACKUP="$2"

if [ ! -f "$DB_BACKUP" ]; then
    echo "Fehler: Datei $DB_BACKUP existiert nicht!"
    exit 1
fi

echo "=== Starte Wiederherstellung aus $DB_BACKUP ==="

# 1. Datenbank leeren und aus Backup wiederherstellen
echo "-> Stelle Datenbank wieder her..."
gunzip -c "$DB_BACKUP" | docker compose -f docker-compose.prod.yml exec -T db psql -U "${DB_USER:-tennisclub}" "${DB_NAME:-tennisclub}"

# 2. Medien wiederherstellen (falls angegeben)
if [ -n "$MEDIA_BACKUP" ] && [ -f "$MEDIA_BACKUP" ]; then
    echo "-> Stelle Medien-Dateien wieder her..."
    tar -xzf "$MEDIA_BACKUP" -C .
fi

echo "=== Wiederherstellung erfolgreich abgeschlossen! ==="
