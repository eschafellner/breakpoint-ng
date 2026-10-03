# Deployment-Prüfung vom 02.10.2026

Geprüft wurde der Repository-Stand nach Einführung von Nginx: Docker-Build,
Compose-Startabhängigkeiten, Assets, Medienrechte, Migrationen, Updates,
Hintergrunddienste, Tunnel, Backup/Restore und Bedienungsanleitungen.
Eine Verbindung zum produktiven Vereinsserver wurde nicht hergestellt.

## Ergebnis und korrigierte Lücken

| Bereich | Feststellung und Ergebnis |
| --- | --- |
| Nginx / CSS | MIME-Typen, versionierte URLs, Gzip und Cache-Header mit echtem Nginx geprüft; Vereins- und Admin-CSS funktionieren unter `DEBUG=False` |
| Medien | Django prüft den Zugriff vor `X-Accel-Redirect`; direkte interne Pfade, unbekannte Dateien und interne Newsbilder sind für Besucher gesperrt |
| Vorbereitung | `prepare` migriert und sammelt Assets vor Webstart; Update erstellt den Dienst ausdrücklich neu |
| Backup | Bisher wurde der lokale Ordner `./media` statt des Docker-Volumes gesichert. Jetzt wird das tatsächliche Medien-Volume archiviert; DB-Zugangsdaten stammen aus dem DB-Container |
| Backup-Fehler | `pipefail`, temporäre Dateien und Archivprüfung verhindern Erfolgsmeldungen bei fehlgeschlagenem Dump oder unvollständigen Sicherungen |
| Restore | Bisher wurde auf dem Host entpackt, SQL-Fehler wurden nicht zuverlässig erkannt. Jetzt Volume-Restore, Archivprüfung, Prüfung gestoppter Anwendungsdienste und transaktionales SQL mit `ON_ERROR_STOP=1` |
| Wartungsfenster | Vor Migrationen werden schreibende Dienste gestoppt und Daten gesichert. Bei einem späteren Fehler wird auch der Tunnel gestoppt |
| Image-Downloads | Nginx-/Tunnel-Images werden vor dem Wartungsfenster geladen; ein Downloadfehler an dieser Stelle lässt die alte Anwendung laufen |
| Parallele Deployments | Lock verhindert zwei gleichzeitige Skriptläufe; normale Fehler entfernen den Lock wieder |
| Celery | Worker-Antwort und Beat-Prozess werden geprüft. Der zuvor fehlende Beat-Zeitplan für vorhandene Aufgaben ist ergänzt; der Scheduler-Stand ist persistent |
| Cloudflare | Start allein gilt nicht als Verbindungsnachweis. `check_tunnel.py` wartet auf `/ready`; `PUBLIC_SITE_URL` ermöglicht eine zusätzliche öffentliche HTTPS-Prüfung |
| Updates | Lokale Änderungen werden vor `git pull --ff-only` erkannt; Restart allein ersetzt weiterhin keinen Image-Build |
| Dokumentation | `DEPLOYMENT.md` enthält Schritte für Erstinstallation, Admin, Updates, Backup, Restore und Diagnose. README, Admin-Handbuch und Bauplan sind angepasst |
| WhiteNoise | War nicht implementiert; der zuvor diskutierte Ansatz wird im Bauplan ausdrücklich durch die verbindliche Nginx-Architektur ersetzt |

## Durchgeführte Validierung

- Gesamte Pytest-Suite mit echtem Nginx: **81 Tests bestanden**.
- Nginx 1.28.0 wurde für die HTTP-Tests portabel verwendet. Die Tests lesen
  dieselbe `deploy/nginx/default.conf`, ersetzen nur Listen-Port, Backend und
  temporäre Dateipfade und führen `nginx -t` aus.
- Die HTTP-Tests prüfen korrekte und fehlende Assets, Hash-Caching, Gzip,
  die Stylesheet-Referenz, öffentliche Bildauslieferung und interne Sperren.
- Backup/Restore-Tests prüfen einen tatsächlichen Medien-Archiv-Roundtrip,
  unzulässige Pfade, Links, beschädigte Gzip-Dateien und Archivvalidierung
  vor Dateischreibvorgängen.
- Die realen Bash-Skripte laufen in Fehlerfalltests mit simulierten
  Docker-Aufrufen: fehlgeschlagene Dumps, Archivprüfung, SQL-Fehler,
  laufende Dienste sowie Celery-/Tunnel-/öffentliche Prüfungsfehler.
- Die aktuelle Compose-Konfiguration wurde mit dem offiziellen
  Docker-Compose-Prüfprogramm (`config --quiet`) validiert.
- Django-Systemcheck mit `config.settings.prod`: keine Fehler.
- Bash-Syntax und `git diff --check`: keine Fehler.

## Verbleibende Prüfung auf dem Server

Nachfolgende Anwendungscode-Prüfung am 03.10.2026: **212 Tests unter PostgreSQL
bestanden**, einschließlich der Deployment-Tests und sieben echten Paralleltests.
Unter SQLite bestanden 205 Tests, sieben wurden gezielt übersprungen. Eine
isolierte PostgreSQL-Testinstanz ersetzt weiterhin keinen Container-Backup-/Restore-Test.
Details: [CODE_PRUEFUNG.md](CODE_PRUEFUNG.md).

Die lokalen Tests beweisen die getesteten HTTP- und Skriptpfade. Hier ist kein
Docker-Daemon installiert; deshalb wurden **kein vollständiger Linux-Compose-Start,
kein PostgreSQL-Backup/Restore in echten Containern und keine produktive
Cloudflare-/SMTP-Verbindung** ausgeführt.

Vor Freigabe gemäß `DEPLOYMENT.md` auf einem Docker-System prüfen:

1. Start der gesamten Umgebung mit echten Produktionswerten und identischen
   Compose-Projekt-/Volume-Namen.
2. Cloudflare-Service-URL `http://nginx:80`, Hostheader, externe HTTPS-Erreichbarkeit
   und Verhalten der öffentlichen Cache-/Access-Regeln.
3. Einen realen DB-/Medien-Restore auf einem leeren, getrennten System mit
   kompatibler Anwendungsversion; anschließend Daten und Bilder vergleichen.
4. Admin-Anmeldung, CSRF, öffentliche/interne Bilder und SMTP-Zustellung.
5. Ausführung der geplanten Celery-Aufgaben und Logüberwachung im Betrieb.
6. Täglichen Backup-Termin, externe geschützte Ablage, Speicherplatz und
   Aufbewahrungsfristen einrichten. Das Deployment-Backup ersetzt keinen
   täglichen Sicherungsplan.

### HTTPS / HSTS

`manage.py check --deploy` meldet mit den aktuellen Einstellungen weiterhin:

- `security.W004`: `SECURE_HSTS_SECONDS` ist nicht gesetzt.
- `security.W008`: `SECURE_SSL_REDIRECT` ist nicht aktiviert.

Das sind offene Betriebsprüfungen. Cloudflare soll Besucher von HTTP auf HTTPS
umleiten; HSTS muss für die tatsächlich vollständig über HTTPS erreichbare
Domain geprüft bzw. eingerichtet werden. Diese Edge-Konfiguration kann ein
lokaler Django-Check nicht verifizieren. Warnungen wurden nicht ausgeblendet.
Das ursprüngliche Bauplan-Kriterium „check --deploy ohne Warnungen“ ist damit
noch nicht vollständig nachgewiesen.

### Bedeutung der Bereitschaftsprüfungen

Der Worker-Healthcheck prüft eine Antwort des konkreten Celery-Workers.
Der Beat-Healthcheck prüft den laufenden Scheduler-Prozess, nicht die Zustellung
einer E-Mail. Die Tunnelprüfung belegt eine aktive Verbindung zu Cloudflare,
nicht die Richtigkeit jedes öffentlich konfigurierten Hostnamens.
Darum bleibt der externe HTTPS-/Browser-Test erforderlich, falls
`PUBLIC_SITE_URL` nicht gesetzt ist oder Cloudflare Access den Test verhindert.

SQL und Medien besitzen beim Restore keine gemeinsame Transaktion. Bei einem
Fehler nach erfolgreichem SQL-Restore muss das Medien-Problem vor dem Neustart
behoben werden. Neue Anwendungsversionen können ein anderes DB-Schema haben;
ein Image-Rollback allein setzt Migrationen nicht zurück.

Technische Grundlagen:
[Compose-Bereitschaft und Startreihenfolge](https://docs.docker.com/compose/how-tos/startup-order/),
[Docker-Volumes](https://docs.docker.com/engine/storage/volumes/),
[PostgreSQL-Dumps](https://www.postgresql.org/docs/16/app-pgdump.html),
[Celery-Monitoring](https://docs.celeryq.dev/en/stable/userguide/monitoring.html),
[Cloudflare-Tunnelbereitschaft](https://developers.cloudflare.com/tunnel/guides/kubernetes/),
[Python-Archivfilter](https://docs.python.org/3.12/library/tarfile.html#extraction-filters).
