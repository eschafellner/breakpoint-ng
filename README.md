# Breakpoint-ng: Modernes Tennisverein-CMS

Ein vollständiges, hochmodernes Web-Portal für Tennisvereine auf Basis von Python 3.12 und **Django 6.0**, PostgreSQL, Celery, Redis und Docker.

---

## 🎾 Kernmodule

1. **News-Portal (N-1 bis N-7):**
   - Artikel mit Titelbild, Galerie in 3 Größen (Thumbnail, Mittel, Groß), Alt-Text-Validierung.
   - Status: Entwurf, Veröffentlicht, Archiviert; zeitgesteuerte Veröffentlichung.
   - Sichtbarkeitsstufen: Öffentlich vs. Nur für Mitglieder.
   - RSS-Feed für öffentliche Artikel (`/news/feed/`).
   - XSS-geschützte HTML-Formatierung mit `nh3`.

2. **Mitgliederverwaltung (M-1 bis M-15):**
   - Selbstregistrierung mit Wahl: Gast oder Mitgliedsantrag (Double-Opt-In per E-Mail).
   - Administrationsbereich für offene Anträge (Freischalten mit sequentieller Mitgliedsnummer oder Ablehnung mit Begründung).
   - Revisionssicheres Änderungsprotokoll (Audit-Log).
   - CSV-Sammelimport mit zeilenweiser Fehlerberichterstattung.
   - Interne Mitgliederliste (M-12a) für aktive Mitglieder, vor Gästen und Besuchern geschützt (403).
   - DSGVO Art. 15 JSON-Datenexport.
   - Celery-Beat-Job zur automatischen Beendigung abgelaufener Mitgliedschaften.

3. **Platzverwaltung & Buchungssystem (P-1 bis P-11):**
   - Plätze (Sand, Halle), Öffnungszeiten, dynamische Saisons.
   - Platzsperren (Training, Wetter, Turniere) mit automatischer Stornierung kollidierender Buchungen und E-Mail-Benachrichtigung.
   - Interaktiver Buchungskalender mit Tag-Auswahl, Slot-Matrix und Live-Kostenberechnung.
   - Concurrency-Schutz: atomare Transaktionen und Kollisionsprüfungen verhindern Doppelbuchungen zuverlässig.
   - Vollständig pflegbare Gastgebühren und Extras (z.B. Flutlicht, Hallenaufschlag).
   - Buchungsregeln (Vorlauf, max. offene Buchungen, max. Dauer, kostenlose Stornierungsfrist).
   - 24h-Vorab-Erinnerungs-E-Mail per Celery.
   - Anonymisierte öffentliche Ansicht („Belegt“).

4. **Turniere & Ortsmeisterschaften (T-1 bis T-9):**
   - Turnierausschreibung für Einzel, Doppel und Mixed in K.-o.- oder Round-Robin-Modus.
   - Partnerbestätigung bei Doppelanmeldungen und automatische Warteliste.
   - Startgebühren erzeugen automatisch Forderungen im Billing-System.
   - K.-o.-Auslosung mit Freilosen (Byes) und entgegengesetzten Positionen für Gesetzte 1 und 2.
   - Round-Robin-Spielplan mit Echtzeit-Tabelle (Siege, Satz- und Game-Differenz).
   - Satz-für-Satz Ergebniseingabe mit Tennis-Validierung (z.B. 6:4, 7:6, MTB 10:8) und automatischem Vorrücken der Sieger.
   - Zuweisung von Matches auf Platz-Slots mit Terminkollisionsprüfung.
   - Historische Ehrentafel der Ortsmeister.

5. **Zentrales Billing & Kassier-Dashboard (M-7 bis M-10):**
   - Zentraler Dienst `create_charge` für Mitgliedsbeiträge, Platzgebühren, Gastgebühren und Turnierstartgelder.
   - Idempotenter automatischer Beitragslauf für das ganze Jahr oder Monate.
   - Anteilige Berechnung bei unterjährigem Vereinseintritt.
   - Erfassung von Zahlungen (Überweisung, Bar, SEPA) mit Statusübergängen (Offen → Teilweise bezahlt → Bezahlt).
   - Kassier-Dashboard mit Kennzahlen und CSV-Export.

---

## 🚀 Schnelleinstieg & Lokale Entwicklung

### Voraussetzungen
- Python 3.12+
- Docker & Docker Compose (optional, aber empfohlen für Postgres/Redis)

### 1. Repository klonen und virtuelle Umgebung anlegen
```bash
python -m venv .venv
# Unter Windows:
.venv\Scripts\activate
# Unter Linux/macOS:
source .venv/bin/activate
```

### 2. Abhängigkeiten installieren
```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### 3. Datenbank migrieren und Demodaten einspielen
```bash
python manage.py migrate
python manage.py seed_data
```
Das Skript `seed_data` richtet automatisch alle Rollen, Einstellungen, 50 Mitglieder, 10 Gäste, 4 Plätze und 2 spielbereite Turniere ein!

### 4. Entwicklungsserver starten
```bash
python manage.py runserver
```
Webseite aufrufen unter: [http://127.0.0.1:8000](http://127.0.0.1:8000)

**Standard-Zugangsdaten (Demo):**
- Administrator: `admin@tc-musterdorf.at` (Passwort: `admin1234`)
- Kassier: `kassier@tc-musterdorf.at` (Passwort: `kassier1234`)
- Platzwart: `platzwart@tc-musterdorf.at` (Passwort: `platzwart1234`)
- Redakteur: `redakteur@tc-musterdorf.at` (Passwort: `redakteur1234`)
- Turnierleiter: `turnierleiter@tc-musterdorf.at` (Passwort: `turnier1234`)
- Mitglied: `mitglied01@example.com` (Passwort: `pass1234`)
- Gast: `gast01@example.com` (Passwort: `gast1234`)

---

## 🧪 Tests ausführen

Die Pytest-Suite prüft Geschäftslogik, Berechtigungen und Buchungsabläufe mit positiven Fällen und gezielten Negativtests:

```bash
pytest
```
Die Tests umfassen die 42 ursprünglichen Akzeptanztests sowie Regressionen zu Anmeldung, Mitgliedschaften, Zahlungen, Buchungen, Turnieren, Migrationen und Deployment. Echte Nginx-HTTP-Tests benötigen Nginx (`NGINX_BINARY`), die Preisvorschau-Prüfung Node.js. Sieben Paralleltests benötigen PostgreSQL und werden unter SQLite übersprungen. GitHub Actions enthält beide Datenbankläufe. Prüfstand und Grenzen: [CODE_PRUEFUNG.md](CODE_PRUEFUNG.md).

---

## 🐳 Docker & Produktion

Die Produktionsarchitektur ist **Cloudflare Tunnel → Nginx → Gunicorn/Django**.
Nginx liefert CSS und JavaScript aus. Bei hochgeladenen Bildern prüft Django
zuerst die Berechtigung; Nginx überträgt anschließend die Datei.

```bash
# .env aus der Vorlage erstellen und Produktionswerte eintragen:
cp .env.example .env
# PUBLIC_SITE_URL=https://DEINE-DOMAIN sowie Hosts, CSRF-Origin und Token setzen.

# Erstdeployment: Image bauen, Migrationen, collectstatic und HTTP-Prüfung:
bash scripts/deploy.sh
```

**Cloudflare-Konfiguration:** Die Service-URL des bestehenden Tunnels muss auf
`http://nginx:80` zeigen (bisher `http://web:8000`). Diese Änderung erfolgt im
Cloudflare-Dashboard; die Compose-Datei kann sie bei einem tokenbasierten Tunnel
nicht automatisch setzen.

**„Healthy“ bestätigt die Verbindung zu Cloudflare, nicht die Erreichbarkeit
der Website.** Der Tunnel muss im Compose-Projekt laufen; ein zusätzlich
installierter Connector kann `nginx` nicht ohne Weiteres erreichen. Das Deployment
prüft jetzt Domain-Konfiguration, den Netzwerkweg aus dem Tunnel-Container und
die öffentliche HTTPS-Adresse. `PUBLIC_SITE_URL` ist dafür erforderlich.
Bei Cloudflare Access ausdrücklich `bash scripts/deploy.sh --skip-public-check`
verwenden und die Website anschließend im angemeldeten Browser prüfen.
Die [Schritt-für-Schritt-Anleitung mit 502-Diagnose](DEPLOYMENT.md) erklärt die
Dashboard-Einstellungen und erwarteten Ergebnisse.

### Wartung & Updates
- Updates mit einem Befehl: `bash update.sh`
- Es gibt ein Wartungsfenster während Migrationen und Containerwechsel.
- Ein `docker compose restart` übernimmt keinen neuen Anwendungscode.
- Ausführliche Deployment- und Diagnoseanleitung: [DEPLOYMENT.md](DEPLOYMENT.md).
- Backup von DB und Docker-Medien: `bash scripts/backup.sh`; beim Deployment erfolgt es vor Migrationen automatisch.
- Backup wiederherstellen: `bash scripts/restore.sh backups/<db-datei>.sql.gz backups/<media-datei>.tar.gz` (Anwendungsdienste vorher stoppen).
- Aktueller Prüfstand und Betriebsprüfungen: [DEPLOYMENT_PRUEFUNG.md](DEPLOYMENT_PRUEFUNG.md).
- SEPA-IBANs werden verschlüsselt gespeichert. Den vorhandenen `DJANGO_SECRET_KEY` samt benötigten alten Schlüsseln getrennt vom DB-Backup sichern; Rotation siehe [DEPLOYMENT.md](DEPLOYMENT.md).
- Ausführliche Anleitung für den Vorstand: siehe [ADMIN_HANDBUCH.md](ADMIN_HANDBUCH.md).
