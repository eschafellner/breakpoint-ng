# Deployment-Prüfungen und Betriebsgrenzen

## Umstellung auf Release-Images vom 07.10.2026

Die Produktion verwendet jetzt `APP_IMAGE` statt eines lokalen Builds. Normale
Updates laden ein gewähltes Release, sichern Daten und führen weiterhin alle
Migrationen und Website-Prüfungen aus. Nginx und cloudflared sind auf konkrete
Versionen festgelegt; ein erneuter Infrastruktur-Download ist ausdrücklich
mit `--update-infrastructure` wählbar. Der bestehende Tunnelcontainer wird bei
unveränderter Konfiguration weiterverwendet.

Ein neuer GitHub-Workflow prüft Anwendung und Deployment vor dem Image-Build,
prüft die gepackte Anwendung und veröffentlicht Images für AMD64 und ARM64.
Der Workflow wird durch einen veröffentlichten GitHub-Release ausgelöst.
[RELEASE_IMAGES.md](RELEASE_IMAGES.md) und [UPDATES.md](UPDATES.md) beschreiben
Erstellung, Zugriff und Installation. Die folgenden Abschnitte dokumentieren
die frühere Prüfung; deren Hinweise auf lokale Builds und bewegliche
Nginx-/Tunnel-Tags gelten für den damaligen Stand.

Der neue GitHub-Workflow muss nach Übernahme der Dateien mit einem echten Release
auf GitHub ausgeführt werden. Eine lokale Prüfung bestätigt keine Veröffentlichung
bei GHCR und keine Verbindung zum produktiven Cloudflare-Tunnel.

### Lokale Validierung der Umstellung

- Docker-Image mit Python 3.12 und Django 6.0.9 erfolgreich gebaut. Ein erneuter
  Build nach Quellcodeänderungen verwendet die Abhängigkeits-Schicht aus dem Cache.
- Die im Workflow vorgesehene Prüfung der gepackten Anwendung, Domain-Konfiguration
  und gesammelten Vereins-/Admin-Stylesheets läuft erfolgreich im Image.
- GitHub-Workflows mit `actionlint` geprüft; Bash-Syntax, Ruff und
  `git diff --check` bestanden.
- Ein eigenes Compose-Testprojekt bestätigt PostgreSQL-/Redis-Bereitschaft,
  Migrationen, Nginx 1.30.5, tatsächliche CSS-/Startseiten-Auslieferung und die
  Bereitschaft von Celery Worker/Beat. Nach einem Containerwechsel bestehen
  die HTTP-Prüfungen erneut.
- Datenbank-/Medien-Backup und Restore im selben isolierten Testprojekt erfolgreich;
  eine zuvor entfernte Testdatei wird aus dem Medien-Archiv wiederhergestellt.
- Der Nginx-Konfigurationsmount nutzt jetzt `ro,Z`, damit auch ein Linux-Host
  mit aktivem SELinux den Lesezugriff im Container erlaubt. Die Prüfung bestätigt
  diesen Start auf dem lokalen Host.
- cloudflared 2026.10.0 lässt sich herunterladen und seine Version ausführen.
  Es wurde kein produktiver Tunnel gestartet.

Die Gesamt-Testsuite wurde unter Python 3.14/Django 6.0 mit SQLite ausgeführt.
PostgreSQL-Paralleltests und die auf dem Host nicht verfügbaren Nginx-Tests
werden dort übersprungen; die tatsächlichen Containerprüfungen oben sind getrennt
davon. ARM64-Build, Veröffentlichung bei GHCR und öffentliche Cloudflare-/SMTP-
Verbindungen sind erst durch den echten Release-/Serverlauf bestätigt.

## Frühere Cloudflare-502-Prüfung vom 03.10.2026

Der aktuelle Ablauf wurde gezielt auf den Fall „Deployment erfolgreich,
Tunnel Healthy, Website 502“ geprüft und korrigiert. Die Untersuchung umfasst
Quellcode, Compose-Konfiguration, Bash-Abläufe und lokale HTTP-Tests. Es besteht
kein Zugang zur produktiven Cloudflare-Konfiguration oder zum Vereinsserver;
die tatsächlich dort eingestellte Route und konkrete Ursache sind daher offen.

### Ergebnis am 03.10.2026

Cloudflare bestätigt mit **Healthy** nur die Verbindung vom Connector zum
Cloudflare-Netz. Das beweist nicht, dass Nginx oder Django erreichbar sind.
Ein Tunnel-502 mit `Unable to reach the origin service` betrifft den Weg zum
internen Ziel. Quelle:
[Cloudflare-Tunnelstatus und 502-Diagnose](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/troubleshoot-tunnels/common-errors/).

| Prüfung | Befund und Änderung |
| --- | --- |
| Erfolgsmeldung | Bisher übersprang `check_deployment.py --public` bei leerer `PUBLIC_SITE_URL` den öffentlichen Test mit Exit-Code 0. `deploy.sh` meldete anschließend Erfolg. Jetzt ist die URL für das Deployment erforderlich. |
| Vorprüfung | Nach dem Image-Build werden HTTPS-Adresse, erlaubte Domain und CSRF-Origin vor dem Wartungsfenster geprüft. Ein Konfigurationsfehler stoppt die alte Anwendung nicht. |
| Interner Hostheader | Die Verbindung zu `http://nginx` verwendete auch `nginx` als Hostheader; dieser Name fehlt normalerweise in den erlaubten Django-Hosts. Ein echter Nginx-/Django-Test bestätigt HTTP 400. Die internen Tests verwenden jetzt die Vereinsdomain und das weitergeleitete HTTPS-Protokoll. Das ist ein zusätzlicher Fehler im Prüfablauf, kein Nachweis der produktiven 502-Ursache. |
| Tunnelverbindung | `/ready` bleibt als Verbindungsprüfung erhalten. Die Ausgabe weist ausdrücklich darauf hin, dass die Website separat zu prüfen ist. |
| Tunnel zu Nginx | Der kurzlebige Dienst `tunnel_probe` prüft Anwendung und CSS im Netzwerk des Compose-Tunnels (`network_mode: service:cloudflared`). Dafür braucht das minimale cloudflared-Image keine Shell und kein curl. |
| Öffentliche Prüfung | Bis zu 60 Sekunden Bereitschaft prüfen, drei aufeinanderfolgende Antworten verlangen, danach aktuelle Assets, Startseite und vorhandene öffentliche Bilder prüfen. Neue Prüfkennungen und Cache-Control-Header reduzieren Antworten aus alten Caches. |
| Access / Umleitungen | HTTP-Umleitungen gelten nicht als erfolgreicher Origin-Test. Für Cloudflare Access ist `--skip-public-check` ausdrücklich wählbar; Deploy und Update kennzeichnen dann die öffentliche Website als ungeprüft. Die internen Prüfungen bleiben aktiv. |
| Fehler und Updates | Fehler nach Beginn des Wartungsfensters führen weiterhin zum Stoppen des lokalen Tunnels und Exit-Code ungleich 0. `update.sh` übernimmt Fehler und die ausdrückliche Access-Ausnahme. |
| Dashboard und Connector-Instanzen | `http://nginx:80` und eine leere Pfadregel sind nötig. Compose setzt diese Dashboard-Route nicht automatisch. Andere Connector-Instanzen mit demselben Token können ebenfalls Anfragen erhalten und müssen einzeln geprüft werden. |
| Übrige Abhängigkeiten | Bestehende DB-/Redis-Healthchecks, Backup vor Migrationen, einmaliges `prepare`, Web-/Nginx-Prüfungen und Celery-Prüfungen bleiben Teil des Ablaufs. Nginx wird zusammen mit Web neu erstellt, damit eine frühere Web-Container-IP nicht übernommen wird. |
| Anleitung | `DEPLOYMENT.md` erklärt die Komponenten, Domain-Werte, Dashboard-Felder, den Unterschied zwischen internem HTTP und öffentlichem HTTPS sowie eine Diagnosefolge mit erwarteten Ergebnissen. README, Admin-Handbuch, Bauplan und `.env.example` sind abgestimmt. |

### Validierung am 03.10.2026

- **72 gezielte Tests bestanden**, aus `tests/test_deployment.py`,
  `tests/test_deployment_operations.py` und `tests/test_tunnel_deployment.py`.
- Echte HTTP-Tests mit Nginx 1.28.0 und Django bestätigen insbesondere:
  Ein nicht erlaubter Hostheader wird zurückgewiesen; die korrigierte interne
  Prüfung besteht mit ausschließlich erlaubter Vereinsdomain. Bestehende
  CSS-/Medienprüfungen bestehen ebenfalls.
- Lokale HTTP-Testserver und Fehlerfalltests prüfen 502, Access-Umleitungen,
  fehlende/falsche Domain-Konfiguration, wiederholte öffentliche Bereitschaft,
  Abbruch vor dem Wartungsfenster, Tunnel-/Origin-/öffentliche Fehler sowie
  die ausdrücklich ungeprüfte Access-Ausnahme in Deploy und Update.
- Die Bash-Tests simulieren Docker und Git; sie berühren keine Produktionsdaten
  und führen kein echtes Update aus.
- Das offizielle portable Docker-Compose-Programm validiert die Konfiguration
  einschließlich Diagnoseprofil, gemeinsamem Tunnel-Netzwerk und fehlenden Hostports.
- Ruff (`F821,F822,F823,E9`), Bash-Syntaxprüfung und `git diff --check` bestanden.

### Damals noch auf dem tatsächlichen Docker-/Cloudflare-System zu prüfen

1. Öffentliche Route **HTTP → `nginx:80`**, leeres Pfadfeld, Hostheader,
   Domain/DNS und zum Tunnel passender Token.
2. Alle beabsichtigten Connector-Instanzen müssen Nginx erreichen. Ein lokal
   gestoppter Tunnel stoppt keine auf anderen Rechnern laufende Instanz.
3. Vollständiger Linux-Compose-Start einschließlich des Hilfscontainers,
   der mit dem laufenden Tunnel sein Netzwerk teilt.
4. Öffentliche HTTPS-Prüfung und Browser-Test für zusätzliche Hostnamen,
   Access/WAF/Cache-Regeln, Anmeldung, CSRF, Uploads und E-Mail-Zustellung.

Hier ist kein Docker-Daemon verfügbar; weder der vollständige Containerstart
noch die produktive Cloudflare-Verbindung wurden ausgeführt. Mehrere erfolgreiche
öffentliche Anfragen prüfen den Zustand zu diesem Zeitpunkt und ersetzen keine
Prüfung aller fremden Connector-Instanzen oder laufende Betriebsüberwachung.
Nginx und cloudflared verwenden weiterhin bewegliche Image-Tags; für reproduzierbare
Releases sollten im Betrieb gemeinsam geprüfte Versionen bzw. Digests festgelegt werden.

Die folgenden Ergebnisse dokumentieren die frühere Gesamtprüfung und bleiben
als Hintergrund erhalten.

## Vorherige Deployment-Prüfung vom 02.10.2026

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
Im aktuellen Stand ist `PUBLIC_SITE_URL` erforderlich und der externe HTTPS-Test
Teil des normalen Deployments. Verhindert Cloudflare Access den Test, bleibt nach
der ausdrücklichen Ausnahme `--skip-public-check` der Browser-Test erforderlich.

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
