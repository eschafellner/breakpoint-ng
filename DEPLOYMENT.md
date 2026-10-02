# Produktion mit Nginx

Die Anfrage läuft über Cloudflare und den Tunnel zu Nginx. Nginx liefert
`/static/` aus dem gesammelten Static-Volume und leitet Anwendungsanfragen an
Gunicorn weiter. Es werden keine Ports am Host veröffentlicht.

## Erstdeployment und Umstellung eines bestehenden Servers

Voraussetzungen: Docker mit Linux-Containern, eine aktuelle Docker-Compose-Version
(v2 oder neuer), Bash und ein eingerichteter Cloudflare Tunnel.

1. Im bestehenden Projektverzeichnis arbeiten. Dessen Name bzw. der bisherige
   Compose-Projektname muss gleich bleiben, damit vorhandene Daten-Volumes
   weiterverwendet werden. Kein `docker compose down -v` ausführen.
2. Beim Erstdeployment `cp .env.example .env` ausführen. Bei einem bestehenden
   System die vorhandene `.env` behalten. Produktionswerte setzen, insbesondere
   einen eigenen `DJANGO_SECRET_KEY`, Hosts, HTTPS-CSRF-Origins, DB-Passwort,
   SMTP-Zugang und Tunnel-Token. Vor Änderungen Datenbank und Medien-Volume sichern.
3. Im Cloudflare-Dashboard beim öffentlichen Hostnamen des Tunnels die Service-URL
   auf **`http://nginx:80`** ändern. Das bisherige Ziel `http://web:8000` würde
   Nginx umgehen und weiterhin keine statischen Dateien ausliefern. Eine eventuell
   gesetzte HTTP-Host-Header-Überschreibung entfernen oder auf einen erlaubten
   öffentlichen Host setzen. Beim Wechsel entsteht eine kurze Unterbrechung.
4. Deployment ausführen:

   ```bash
   bash scripts/deploy.sh
   ```

5. Die öffentliche Webseite und das Stylesheet im Browser prüfen. Optional den
   HTTP-Test zusätzlich durch den öffentlichen Tunnel ausführen:

   ```bash
   docker compose -f docker-compose.prod.yml exec -T web python scripts/check_deployment.py --base-url https://DEINE-DOMAIN
   ```

Das Skript validiert die Compose-Konfiguration und baut das Anwendungsimage.
Dann wartet es auf Datenbank und Redis, stoppt Tunnel, Nginx, Web und Celery,
und erstellt den einmaligen Dienst `prepare` neu. Dieser führt `migrate` und
`collectstatic` aus und prüft das versionierte Stylesheet. Bei einem Fehler
bleiben die Anwendungsdienste gestoppt.

Anschließend werden Web und Nginx neu erstellt und auf Bereitschaft geprüft.
Der HTTP-Test prüft die ursprünglichen und versionierten Vereins-/Admin-CSS-Dateien
auf Status 200, `text/css` und Übereinstimmung mit den gesammelten Dateien.
Er prüft außerdem die Startseite, die CSS-Referenz, fehlende Dateien und
öffentliche Bilder, sofern bereits welche hochgeladen wurden.
Erst danach starten Celery und der Tunnel. Die interne Prüfung kann eine falsche
Service-URL oder Cache-Regel im Cloudflare-Dashboard nicht erkennen; dafür ist
die zusätzliche öffentliche Prüfung vorgesehen.

Auch `docker compose -f docker-compose.prod.yml up -d --build` führt beim
Erststart die Vorbereitung durch, bietet aber nicht den vollständigen HTTP-Test
des Skripts. Für Updates das Skript verwenden: Es verhindert Änderungen am
gemeinsamen Static-Volume, während die alte Anwendung noch darauf zugreift.

## Updates

```bash
bash update.sh
```

`update.sh` holt Änderungen mit `git pull --ff-only` und ruft denselben
Deployment-Ablauf auf. Lokale Konflikte und divergierende Branches führen zum
Abbruch. `docker compose restart` ersetzt keinen Image-Neubau.

Nach einer eigenen Codeänderung oder einem manuellen Checkout genügt
`bash scripts/deploy.sh`; es holt keinen weiteren Code aus Git.

Es gibt ein Wartungsfenster. Migrationen und Deployment sind nicht automatisch
reversibel: Bei fehlgeschlagenen Migrationen zuerst die Logs prüfen und den
Fehler beheben. Ein altes Image allein setzt das Datenbankschema nicht zurück.

## Dateien und Caching

- `static_prod_volume`: `prepare` schreibt; Web und Nginx lesen nur.
- `media_prod_volume`: Web/Celery schreiben; Nginx liest nur.
- Django erzeugt mit `ManifestStaticFilesStorage` Dateinamen wie
  `styles.<hash>.css`. Die bestehenden `{% static %}`-Tags verwenden diese URLs
  automatisch. Nginx setzt für sie ein Jahr Cache-Zeit mit `immutable`, für
  ursprüngliche Dateinamen 60 Sekunden und komprimiert CSS/JavaScript mit Gzip.
- `static/css/styles.css` ist fertiges CSS. Ein Node-/Tailwind-Build ist derzeit
  nicht erforderlich. Ein künftiger CSS-Build muss vor `collectstatic` laufen.
- `.dockerignore` schließt lokale Umgebungen, `.env`, Datenbank, Uploads und
  gesammelte Dateien aus dem Image aus.

Alle `/media/`-Anfragen gehen zuerst an Django. Vereinslogos sind öffentlich,
Newsbilder folgen exakt der Veröffentlichungs-/Mitgliedersichtbarkeit des
zugehörigen Artikels. Profilbilder sind für den Besitzer und Staff verfügbar.
Danach sendet Django `X-Accel-Redirect` auf einen internen Nginx-Pfad; Nginx
überträgt die Datei. Direkter Zugriff auf diesen internen Pfad ist gesperrt.
Medien erhalten `private, no-store`, damit ein öffentlicher Cache die
Zugriffsprüfung nicht umgehen kann. Cloudflare darf `/media/` nicht durch eine
"Cache Everything"-Regel zwischenspeichern.

Unbekannte Dateien und Dateitypen werden nicht öffentlich freigegeben.
Für spätere Dokument-Uploads muss eine eigene Berechtigungsregel ergänzt werden.
Auch lokal prüft Django die Bildberechtigungen und liefert freigegebene Bilder
bei Bedarf selbst aus.

## Diagnose

```bash
docker compose -f docker-compose.prod.yml ps -a
docker compose -f docker-compose.prod.yml logs --tail=100 prepare web nginx
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
docker compose -f docker-compose.prod.yml exec -T web python manage.py findstatic css/styles.css --verbosity 2
docker compose -f docker-compose.prod.yml exec -T web python scripts/check_deployment.py
```

Bei `text/html` statt `text/css` zuerst prüfen, ob der Tunnel tatsächlich Nginx
anspricht, `prepare` mit Exit-Code 0 beendet wurde und Nginx dasselbe Static-Volume
liest. Die Existenz einer Quelldatei unter `/app/static/` allein genügt nicht.
Das Deployment-Skript erzeugt die gesammelten Dateien und startet die Dienste
in der vorgesehenen Reihenfolge erneut. Falls ausschließlich die öffentliche
URL alte Fehler liefert, zusätzlich Cloudflare-Cache/Regeln prüfen.

## Lokale Regressionstests

```bash
pytest
# Mit installiertem Nginx auch echte HTTP-Tests ausführen:
NGINX_BINARY=/usr/sbin/nginx pytest tests/test_deployment.py
```

Unter PowerShell zuerst `$env:NGINX_BINARY = 'C:/Pfad/nginx.exe'` setzen.
Die HTTP-Tests verwenden dieselbe Nginx-Konfiguration mit temporären Dateipfaden
und lokalen Ports. Sie prüfen unter `DEBUG=False` CSS-MIME-Typen, Hash-Caching,
Gzip, 404-Antworten, Bildauslieferung und den Schutz interner Bilder.
Ohne Nginx werden nur diese zwei HTTP-Tests übersprungen. Die übrigen Tests
prüfen Bereitschaft, Berechtigungen, Dateipfade und die Erkennung falscher MIME-Typen.
