# Breakpoint-NG: Deployment Schritt für Schritt

Stand: 03.10.2026. Diese Anleitung gilt für die Produktion mit Docker,
Nginx und Cloudflare Tunnel. Die Entwicklung verwendet weiterhin
`docker-compose.yml` und den Django-Entwicklungsserver.

## 1. Voraussetzungen prüfen

Auf dem Server werden Git, Bash, gzip und Docker mit Linux-Containern sowie
eine aktuelle Docker-Compose-Version (v2 oder neuer) benötigt. Für den
Produktivbetrieb ist ein Linux-Server vorgesehen. Unter Windows dieselben
Skripte in Git Bash mit Docker Desktop im Linux-Modus ausführen.

```bash
git --version
bash --version
gzip --version
docker version
docker info --format '{{.OSType}}'
docker compose version
docker compose up --help
```

Erwartet: Docker-Client und -Server sind erreichbar, der Betriebssystemtyp
ist `linux`, und Compose unterstützt `--wait` und `--wait-timeout`.
Nur ein installiertes Compose-Programm ohne Docker-Daemon genügt nicht.
Der Server benötigt ausgehenden Zugriff auf Paket-/Image-Registries,
Cloudflare und den verwendeten SMTP-Server. Am Router sind keine eingehenden
Portfreigaben nötig; die Produktions-Compose-Datei veröffentlicht keine Hostports.

## 2. Repository bereitstellen

Nur auf einem neuen Server:

```bash
git clone https://github.com/eschafellner/breakpoint-ng.git Breakpoint-ng
cd Breakpoint-ng
```

Bei einer bestehenden Installation im bisherigen Projektverzeichnis arbeiten.
Den vorhandenen Compose-Projektnamen beibehalten, damit dieselben Daten-Volumes
verwendet werden. Falls bisher `COMPOSE_PROJECT_NAME` in `.env` gesetzt war,
diesen Wert übernehmen. Der Projektname ist mit
`docker compose -f docker-compose.prod.yml config --format json` einsehbar;
diese Ausgabe enthält auch konfigurierte Zugangsdaten und gehört nicht in Logs.

Kein `docker compose down -v` und kein Volume-Pruning auf der Produktionsinstallation
ausführen: Diese Befehle können die gespeicherten Vereinsdaten entfernen.

## 3. Produktionskonfiguration anlegen

Nur wenn noch keine `.env` existiert:

```bash
cp .env.example .env
chmod 600 .env
```

Eine bestehende `.env` nicht überschreiben. Die folgenden Werte mit einem
Texteditor eintragen; Beispielwerte aus der Vorlage müssen ersetzt werden.

| Variable | Einzutragender Wert |
| --- | --- |
| `DJANGO_SECRET_KEY` | Eigener zufälliger Schlüssel; auf einem bestehenden System behalten |
| `DJANGO_SECRET_KEY_FALLBACKS` | Normalerweise leer; alte Schlüssel nur bei geplanter Rotation |
| `DJANGO_ALLOWED_HOSTS` | Vereinsdomain(s), durch Kommas getrennt, ohne `https://` |
| `CSRF_TRUSTED_ORIGINS` | Dieselben öffentlichen Domains mit `https://` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL-Datenbank und Zugangsdaten |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` | SMTP-Server, typischerweise Port 587 mit TLS |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP-Anmeldung |
| `DEFAULT_FROM_EMAIL` | Zulässige Absenderadresse, bei Anzeigenamen in Anführungszeichen |
| `CLOUDFLARE_TUNNEL_TOKEN` | Token des vorgesehenen Cloudflare Tunnels |
| `PUBLIC_SITE_URL` | Empfohlen: `https://tennis.example`, für E-Mail-Links und den externen Test |

Einen neuen Schlüssel kann man ohne lokale Python-Installation erzeugen:

```bash
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(50))"
```

In Produktion setzt Compose `DB_HOST=db`, den PostgreSQL-Treiber und die
Redis-/Celery-Adressen selbst. Die `localhost`-Werte der Vorlage betreffen
lokale Entwicklung. Bei einem vorhandenen PostgreSQL-Volume verändert ein
neuer `DB_PASSWORD`-Wert nicht automatisch das Passwort im Datenbankserver;
eine Passwortänderung muss dort separat erfolgen.

`PUBLIC_SITE_URL` kann leer bleiben, wenn Cloudflare Access den öffentlichen
Zugang schützt. Dann wird der externe Test im angemeldeten Browser durchgeführt.
Domain, Hostliste und CSRF-Origin müssen zusammenpassen.
Ohne diesen Wert verwendet die Webregistrierung die Adresse der aktuellen Anfrage
für ihre Bestätigungslinks. Ein fest gesetzter Wert gibt eine eindeutige Vereinsadresse vor.

### Vor dem ersten Update auf den geprüften Code-Stand

Die neuen Migrationen ergänzen das Login-Zeitfenster und den Erinnerungszeitpunkt,
machen E-Mail-Adressen unabhängig von Groß-/Kleinschreibung eindeutig und
verschlüsseln bestehende SEPA-IBANs. `prepare` führt sie automatisch aus.
Der bestehende `DJANGO_SECRET_KEY` muss dabei erhalten bleiben. Die Sicherung
vor den Migrationen erfolgt durch `scripts/deploy.sh`.

Bei bestehenden Daten zuerst auf doppelte E-Mail-Adressen prüfen:

```bash
docker compose -f docker-compose.prod.yml exec -T web python manage.py shell -c 'from django.contrib.auth import get_user_model; from django.db.models import Count; from django.db.models.functions import Lower; print(list(get_user_model().objects.values(normalized_email=Lower("email")).annotate(total=Count("pk")).filter(total__gt=1)))'
```

Erwartet wird `[]`. Andernfalls die betroffenen Konten und ihre Mitgliedschaften,
Buchungen und Forderungen fachlich prüfen und bereinigen. Die Migration bricht
bei solchen Dubletten bewusst ab und löscht oder vereinigt keine Konten automatisch.
Die Ausgabe enthält personenbezogene Daten und gehört nicht in öffentliche Logs.

## 4. Cloudflare Tunnel auf Nginx einstellen

Im Cloudflare-Dashboard den Tunnel und den öffentlichen Hostnamen für die
Vereinsdomain konfigurieren:

- Service-Typ: **HTTP**.
- Service-URL: **`nginx:80`**, vollständig **`http://nginx:80`**.
- Das frühere Ziel `http://web:8000` ersetzen.
- Eine HTTP-Host-Header-Überschreibung entfernen oder auf eine erlaubte
  öffentliche Vereinsdomain setzen.
- HTTPS für Besucher aktivieren und HTTP am Cloudflare-Rand auf HTTPS umleiten.
- Keine „Cache Everything“-Regel für dynamische Seiten oder `/media/` anwenden.
  Medien müssen `private, no-store` respektieren.
- HSTS erst für eine vollständig über HTTPS erreichbare Domain aktivieren.

Der tokenbasierte Tunnel erhält seinen öffentlichen Hostnamen aus dem Dashboard.
Die Compose-Datei kann diese Dashboard-Einstellung nicht automatisch ändern.
Eine bestehende Installation ist während der Umstellung kurzzeitig unterbrochen.

## 5. Deployment ausführen

```bash
docker compose -f docker-compose.prod.yml config --quiet
bash scripts/deploy.sh
```

Der Ablauf ist bei Erstinstallation und Updates derselbe:

1. Ein Deployment-Lock verhindert gleichzeitige Skriptläufe.
2. Konfiguration prüfen, Anwendung bauen, Nginx-/Tunnel-Images herunterladen.
   Fehler in dieser Phase stoppen die bisher laufende Anwendung nicht.
3. PostgreSQL und Redis starten und auf Bereitschaft warten.
4. Tunnel, Nginx, Web und Celery für das Wartungsfenster stoppen.
5. Datenbank und das Docker-Medien-Volume sichern; fehlerhafte Backups brechen ab.
   Beim ersten Start ist dies eine Sicherung des noch leeren Systems.
6. Den einmaligen Dienst `prepare` neu erstellen: Migrationen, `collectstatic`,
   Prüfung des versionierten Stylesheets.
7. Web und Nginx neu erstellen und ihre Healthchecks abwarten.
8. Nginx-Konfiguration sowie echte HTTP-Auslieferung von Vereins-/Admin-CSS,
   Startseite und vorhandenen öffentlichen Bildern prüfen.
9. Celery Worker und Beat starten und ihre Healthchecks abwarten.
10. Tunnel starten und seine Verbindung über den internen `/ready`-Endpunkt prüfen.
11. Wenn `PUBLIC_SITE_URL` gesetzt ist, die HTTPS-Auslieferung durch Cloudflare prüfen.

Bei einem Fehler nach Beginn des Wartungsfensters wird der Tunnel gestoppt.
Das Skript meldet Erfolg erst nach den vorgesehenen Prüfungen.
Backups werden nicht automatisch gelöscht; Speicherplatz und Aufbewahrung
müssen im Betrieb verwaltet werden.

Ein direktes `docker compose up -d --build` besitzt zwar Startabhängigkeiten,
ersetzt aber weder die Backup-Schritte noch den vollständigen Prüfablauf des Skripts.

## 6. Administrator anlegen

Nur beim ersten Deployment, wenn noch kein Administrator existiert:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Eigene E-Mail-Adresse und ein eigenes Passwort wählen. Danach unter
`https://DEINE-DOMAIN/admin/` anmelden und Vereinsname, Kontaktdaten,
Mitgliedschaftsarten, Platzregeln und Bankverbindung pflegen.

`seed_data` ist für Entwicklungs-/Demosysteme vorgesehen. Auf dem öffentlichen
Produktionssystem keine Demokonten mit bekannten Passwörtern anlegen.

## 7. Technischen und fachlichen Funktionstest durchführen

```bash
docker compose -f docker-compose.prod.yml ps -a
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
docker compose -f docker-compose.prod.yml exec -T web python scripts/check_deployment.py
docker compose -f docker-compose.prod.yml exec -T web python scripts/check_tunnel.py
docker compose -f docker-compose.prod.yml exec -T web python scripts/check_deployment.py --base-url https://DEINE-DOMAIN
docker compose -f docker-compose.prod.yml exec -T web python manage.py check --deploy
```

`prepare` soll mit **Exit-Code 0** beendet sein. DB, Redis, Web, Nginx und
Celery sollen laufen; die vorhandenen Healthchecks sollen `healthy` zeigen.
Der Tunnel besitzt eine separate Verbindungsprüfung, keinen eingebauten
Compose-Healthcheck im minimalen Cloudflare-Image.

Der HTTP-Test erwartet CSS mit **HTTP 200, `text/css` und dem Inhalt des
aktuellen Images**. Die Startseite muss das versionierte Stylesheet referenzieren.
Ohne hochgeladene öffentliche Bilder meldet der Bildtest einen Hinweis.

Im Browser zusätzlich prüfen:

1. Startseite und Admin besitzen Styles, auch nach einem Neuladen.
2. Administrator kann sich anmelden und speichern; keine CSRF-Fehler.
3. Ein veröffentlichtes öffentliches Newsbild wird ausgeliefert.
4. Ein internes Newsbild ist für ein Mitglied erreichbar, aber über dieselbe
   direkte Bild-URL in einem privaten Browserfenster nicht erreichbar.
5. SMTP funktioniert, etwa über einen selbst ausgelösten Passwort-Reset.
6. Testweise eine Buchung durchführen und die erwarteten Berechtigungen prüfen.

Aktuell meldet `check --deploy` bei den vorhandenen Produktionseinstellungen
`security.W004` (HSTS) und `security.W008` (HTTPS-Umleitung). Diese sind noch
nicht durch lokale Tests erledigt. Die Cloudflare-Umleitung und die HSTS-Header
der öffentlichen Domain separat prüfen. Django-HSTS bleibt zunächst deaktiviert,
und interne HTTP-Healthchecks dürfen nicht unbeabsichtigt auf HTTPS umgeleitet werden.
Prüfstand: [DEPLOYMENT_PRUEFUNG.md](DEPLOYMENT_PRUEFUNG.md).

## 8. Laufende Updates einspielen

```bash
bash update.sh
```

Das Skript verweigert lokale Änderungen, holt Code mit `git pull --ff-only`
und verwendet anschließend denselben Deployment-Ablauf mit Backup und Tests.
Ein Wartungsfenster ist einzuplanen. Vor einem eigenen manuellen Checkout die
Änderungen prüfen; für bereits ausgecheckten Code `bash scripts/deploy.sh` verwenden.

Ein `docker compose restart` kopiert keinen neuen Quellcode ins Image.
Migrationen werden bei Fehlern nicht automatisch zurückgesetzt.

## 9. Backups erstellen und außerhalb des Servers sichern

```bash
bash scripts/backup.sh
```

Dies erzeugt zwei zusammengehörige Dateien mit gleichem Zeitstempel:

- `backups/db_backup_<zeitstempel>.sql.gz`: PostgreSQL-Dump mit Container-Zugangsdaten.
- `backups/media_backup_<zeitstempel>.tar.gz`: Inhalt von `media_prod_volume`.

Das Skript benötigt eine laufende DB und das gebaute Anwendungsimage mit
`scripts/media_archive.py`. Ein vorhandener Webcontainer muss dabei nicht laufen.
Bei der erstmaligen Übernahme dieser Skripte zuvor
`docker compose -f docker-compose.prod.yml build prepare` ausführen.

Während eines normalen Online-Backups können Uploads geändert werden. Für ein
zusammenpassendes DB-/Medien-Backup die schreibenden Anwendungsdienste zuerst
stoppen; das Deployment-Skript macht dies automatisch.
Ein täglicher Backup-Termin muss auf dem Server separat eingerichtet werden.
Diese Anleitung installiert keinen Cronjob.

Beide Dateien auf NAS oder externen Speicher kopieren. Die `.env` separat
geschützt sichern; insbesondere den ursprünglichen `DJANGO_SECRET_KEY`
für die Wiederherstellung behalten. Backups und `.env` nicht zu GitHub hochladen.
Verschlüsselte SEPA-Daten sind ohne den passenden Schlüssel nicht lesbar.
Der DB-/Medien-Dump enthält die `.env` und ihre Schlüssel nicht.
Aufbewahrung, verfügbaren Speicherplatz und regelmäßige Restore-Tests festlegen.

### Geplante Rotation des SEPA-Schlüssels

1. Anwendungsdienste stoppen und DB-/Medien-Backup sowie bisherige `.env` sichern.
2. In `.env` einen neuen `DJANGO_SECRET_KEY` setzen und den bisherigen Schlüssel
   in `DJANGO_SECRET_KEY_FALLBACKS` eintragen. Bereits vorhandene, benötigte
   Fallback-Schlüssel beibehalten.
3. `bash scripts/deploy.sh` ausführen. Die Anwendung kann bestehende Daten mit
   dem Fallback lesen und schreibt neue Daten mit dem neuen Schlüssel.
4. Bestehende Datensätze neu verschlüsseln:

   ```bash
   docker compose -f docker-compose.prod.yml exec -T web python manage.py rotate_sepa_keys
   ```

5. Zugriff auf die SEPA-Daten prüfen und ein neues Backup erstellen. Erst dann
   den alten Fallback aus der aktuellen `.env` entfernen und die Anwendungsdienste
   mit `bash scripts/deploy.sh` neu erstellen.

Alte Backups brauchen weiterhin den damaligen Schlüssel. Diesen bis zum Ende
ihrer Aufbewahrung geschützt behalten. Ein bloßer Container-Restart lädt
geänderte Compose-Umgebungsvariablen nicht neu.

## 10. Backup wiederherstellen

Die Wiederherstellung verändert Daten. Sie sollte zunächst auf einem getrennten,
leeren System mit den zum Backup passenden Anwendungsversionen geprüft werden.

### Wiederherstellung auf einem neuen System

1. Repository bereitstellen, die gesicherte `.env` übernehmen und das zum Backup
   passende Git-Release auschecken. Die aktuellen Restore-Hilfsskripte benötigen
   ein Image, das `scripts/media_archive.py` enthält.
2. Image bauen und nur DB/Redis starten:

   ```bash
   docker compose -f docker-compose.prod.yml build prepare
   docker compose -f docker-compose.prod.yml up -d --wait --wait-timeout 120 db redis
   ```

3. Die beiden zusammengehörigen Backup-Dateien auf den Server kopieren.
4. Restore ausführen:

   ```bash
   bash scripts/restore.sh backups/db_backup_ZEITSTEMPEL.sql.gz backups/media_backup_ZEITSTEMPEL.tar.gz
   ```

5. Erst nach erfolgreichem Restore `bash scripts/deploy.sh` ausführen.
6. Anmeldung, Mitglieder, Buchungen und Bilder prüfen; danach den Tunnel
   auf diesen Server umstellen. Eine Testumgebung darf nicht versehentlich
   parallel über den Produktionstunnel veröffentlichen.

### Wiederherstellung auf einem bestehenden System

Zuerst den aktuellen Zustand sichern und anschließend alle Anwendungsdienste stoppen:

```bash
docker compose -f docker-compose.prod.yml stop cloudflared nginx celery_beat celery_worker web
bash scripts/backup.sh
bash scripts/restore.sh backups/db_backup_ZEITSTEMPEL.sql.gz backups/media_backup_ZEITSTEMPEL.tar.gz
bash scripts/deploy.sh
```

Das Restore-Skript verweigert die Arbeit, solange Anwendungsdienste oder
`prepare` laufen, und verwendet denselben Lock wie das Deployment.
Es prüft beide Archive vor dem SQL-Restore, verwendet
`ON_ERROR_STOP=1` und eine SQL-Transaktion und schreibt Medien ins Docker-Volume.
Medienpfade, Links und Spezialdateien werden vor dem Entpacken geprüft.

Die SQL-Sicherung enthält `DROP ... IF EXISTS` für gesicherte Objekte.
Zusätzliche Tabellen/Constraints aus einer neueren Version können einen Restore
in ein bestehendes Schema verhindern; dann ein leeres, getrenntes Ziel verwenden.
Vorhandene Medien werden überschrieben, zusätzliche Dateien jedoch nicht gelöscht.
SQL und Medien bilden keine gemeinsame Transaktion: Bei einem Medienfehler nach
erfolgreichem SQL-Restore bleiben die Anwendungsdienste gestoppt und der Fehler
muss vor dem Neustart behoben werden.

## 11. Fehler diagnostizieren

```bash
docker compose -f docker-compose.prod.yml ps -a
docker compose -f docker-compose.prod.yml logs --tail=100 prepare web nginx celery_worker celery_beat cloudflared
docker compose -f docker-compose.prod.yml exec -T web python manage.py findstatic css/styles.css --verbosity 2
```

| Beobachtung | Nächster Prüfschritt |
| --- | --- |
| CSS antwortet mit `text/html` | Tunnelziel, `prepare`-Exit-Code und Static-Volume prüfen |
| Nur öffentliche URL fehlerhaft | Cloudflare-Hostheader, Cache/Access und `PUBLIC_SITE_URL` prüfen |
| Migration oder Backup fehlgeschlagen | Dienste gestoppt lassen, Logs und freien Speicher prüfen |
| Nginx liefert 502 | Web-Healthcheck, Gunicorn-Logs und Nginx-Konfiguration prüfen |
| CSRF-Fehler | Öffentliche Domain, HTTPS-Origin und weitergeleitetes Protokoll prüfen |
| Celery startet nicht | Redis, Worker-Healthcheck und Celery-Logs prüfen |
| Tunnel verbindet nicht | Token, ausgehende Verbindung und Tunnel-Logs prüfen |
| Deployment-Lock vorhanden | Zuerst sicherstellen, dass kein Deployment läuft; nur einen verwaisten Lock entfernen |

Nach der Fehlerkorrektur `bash scripts/deploy.sh` erneut ausführen.
Bei einem Prozessabbruch mit SIGKILL kann ein leerer Lock-Ordner verbleiben.
Nach Prüfung, dass kein Deployment mehr läuft, im Projektverzeichnis
`rmdir .deployment-lock` verwenden. Keine Produktions-Volumes löschen.

## 12. Zuständigkeiten der Komponenten

**Browser → Cloudflare Tunnel → Nginx → Gunicorn/Django**

- `prepare` schreibt gesammelte Assets in `static_prod_volume`.
- Web/Nginx lesen statische Dateien nur; Hash-URLs erhalten ein Jahr Cache-Zeit,
  ursprüngliche Dateinamen 60 Sekunden. CSS/JavaScript werden mit Gzip komprimiert.
- Web/Celery schreiben Uploads; Nginx liest `media_prod_volume` nur.
- Jede `/media/`-Anfrage wird durch Django autorisiert, anschließend liefert
  Nginx per `X-Accel-Redirect` über einen internen Pfad aus.
- Vereinslogos sind öffentlich, Newsbilder folgen dem Artikelzugriff,
  Profilbilder sind für Besitzer/Staff erreichbar; unbekannte Dateien bleiben gesperrt.
- Der aktuelle CSS-Stand benötigt keinen Tailwind-/Node-Build.
- **WhiteNoise wird nicht eingesetzt.**
- Celery Beat läuft einmal mit persistentem Scheduler-Stand:
  Mitgliedschaftsprüfung täglich 00:05 Uhr, Buchungserinnerungen stündlich,
  Ablauf unbestätigter Turnierpartner ebenfalls stündlich,
  in der eingestellten Zeitzone `Europe/Vienna`.

## 13. Lokal verifizierbare Regressionstests

```bash
python -m pip install -e '.[dev]'
python -m pytest
NGINX_BINARY=/usr/sbin/nginx pytest tests/test_deployment.py tests/test_deployment_operations.py
```

Unter PowerShell zuerst `$env:NGINX_BINARY = 'C:/Pfad/nginx.exe'` setzen.
Die beiden echten HTTP-Tests benötigen Nginx; alle Dateien und Ports sind temporär.
Ohne Nginx werden diese beiden Tests übersprungen. Die Skripttests verwenden
simulierte Docker-Aufrufe und berühren keine Produktionsdaten.
Ein echter PostgreSQL-Restore und ein vollständiger Compose-Start müssen
zusätzlich auf einem Docker-System geprüft werden.

Die sieben Tests mit parallelen Datenbanktransaktionen benötigen PostgreSQL;
unter SQLite werden sie ausdrücklich übersprungen. Mit einer getrennten lokalen
Testinstanz (kein Produktionsserver) lässt sich die vollständige Suite so starten:

```bash
DB_ENGINE=django.db.backends.postgresql DB_NAME=breakpoint_tests DB_USER=postgres DB_PASSWORD=TESTPASSWORT DB_HOST=127.0.0.1 DB_PORT=5432 python -m pytest
```

Der Testbenutzer muss Testdatenbanken anlegen und löschen dürfen. Der Testlauf
verwendet `test_breakpoint_tests`. In PowerShell die Variablen vorher mit
`$env:DB_ENGINE = 'django.db.backends.postgresql'` usw. setzen.
Die JavaScript-Prüfung der tatsächlichen Preisvorschau benötigt Node.js.
Der GitHub-Workflow prüft SQLite und PostgreSQL mit installiertem Nginx.
Ergebnisse und fachliche Grenzen: [CODE_PRUEFUNG.md](CODE_PRUEFUNG.md).

Technische Referenzen:
[Compose-Startabhängigkeiten](https://docs.docker.com/compose/how-tos/startup-order/),
[Docker-Volumes](https://docs.docker.com/engine/storage/volumes/),
[PostgreSQL-Dumps](https://www.postgresql.org/docs/16/app-pgdump.html),
[Cloudflare-Verbindungsprüfung](https://developers.cloudflare.com/tunnel/guides/kubernetes/).
