#!/bin/bash
# ========================================================
# TC Musterdorf – Backup-Skript
# Sichert PostgreSQL-Datenbank und hochgeladene Medien
# ========================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/db_backup_${TIMESTAMP}.sql.gz"
MEDIA_FILE="$BACKUP_DIR/media_backup_${TIMESTAMP}.tar.gz"

echo "=== Starte Backup: ${TIMESTAMP} ==="

# 1. PostgreSQL Datenbank-Dump
echo "-> Erstelle Datenbank-Dump..."
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U "${DB_USER:-tennisclub}" "${DB_NAME:-tennisclub}" | gzip > "$DB_FILE"

# 2. Medien-Verzeichnis sichern
echo "-> Sichere Medien-Dateien (Fotos, Dokumente)..."
if [ -d "./media" ]; then
    tar -czf "$MEDIA_FILE" -C . media
fi

echo "✓ Backup erfolgreich gespeichert:"
echo "  - Datenbank: $DB_FILE"
if [ -f "$MEDIA_FILE" ]; then
    echo "  - Medien:    $MEDIA_FILE"
fi

# Ältere Backups bereinigen (optional: behalte Backups der letzten 30 Tage)
find "$BACKUP_DIR" -type f -name "*.gz" -mtime +30 -delete
echo "=== Backup beendet ==="
