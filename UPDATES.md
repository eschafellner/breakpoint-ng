# Updates auf dem Vereinsserver

Diese Anleitung gilt für ein bereits eingerichtetes System. Die einmalige
Einrichtung steht in [DEPLOYMENT.md](DEPLOYMENT.md). Wie man ein Release-Image
erstellt, erklärt [RELEASE_IMAGES.md](RELEASE_IMAGES.md).

## 1. Die gewünschte Version auswählen

Im GitHub-Repository unter **Releases** die gewünschte Version öffnen.
Der zugehörige Workflow **Release image** unter **Actions** muss erfolgreich
beendet sein. Ein veröffentlichter Release allein bedeutet noch nicht, dass
sein Image fertig ist. Die Versionsnummer aus dem Release verwenden;
`v0.1.1` ist hier ein Beispiel.

## 2. Update starten

Ein Terminal auf dem Server öffnen und in den bisherigen Projektordner wechseln.
Dort ausführen:

```bash
bash update.sh v0.1.1
```

Die Kurzform verwendet `ghcr.io/eschafellner/breakpoint-ng`. Bei einem anderen
GitHub-Repository die vollständige Image-Adresse aus der Workflow-Zusammenfassung
kopieren:

```bash
bash update.sh ghcr.io/DEIN-GITHUB-NAME/breakpoint-ng:v0.1.1
```

`DEIN-GITHUB-NAME` durch den tatsächlichen, kleingeschriebenen Namen ersetzen.
Alternativ akzeptiert das Skript die Adresse mit `@sha256:…` aus der
Zusammenfassung. Der Digest bezeichnet exakt einen Image-Inhalt.

Das Skript lädt das fertige Anwendungsimage herunter und prüft zuerst die
Konfiguration. Erst danach beginnt das Wartungsfenster. Es sichert Datenbank und
Medien, führt Migrationen aus, startet die Dienste und prüft die öffentliche
Website. Auf dem Server wird kein Anwendungscode gebaut und kein `git pull`
ausgeführt. Die gewählte Image-Adresse wird vor dem Wartungsfenster in `.env`
gespeichert; alle anderen Einstellungen bleiben erhalten.

Die `.env` muss einmalig eingerichtet sein, insbesondere `PUBLIC_SITE_URL`.
Bei einem privaten Image ist außerdem einmalig eine Docker-Anmeldung erforderlich;
siehe [RELEASE_IMAGES.md](RELEASE_IMAGES.md#6-das-image-auf-dem-server-verwenden).

## 3. Ergebnis prüfen

Erwartet wird am Ende **„Update erfolgreich geprüft“**. Danach die Vereinsseite
im Browser öffnen und Anmeldung sowie eine wichtige Vereinsfunktion prüfen.
Die beiden neu erstellten Dateien im Ordner `backups/` außerhalb des Servers
aufbewahren.

Mit `bash update.sh` ohne Versionsnummer wird die bereits in `.env` ausgewählte
Version erneut installiert und geprüft. Der Befehl sucht nicht automatisch nach
der neuesten Version.

Bei einer absichtlich durch Cloudflare Access geschützten Website:

```bash
bash update.sh v0.1.1 --skip-public-check
```

Dann bleibt die öffentliche Prüfung ausdrücklich offen. Die Vereinsseite im
angemeldeten Browser prüfen.

## Wenn das Update fehlschlägt

Die Fehlermeldung und die [Diagnoseanleitung](DEPLOYMENT.md#11-fehler-diagnostizieren)
verwenden. Fehler beim Herunterladen oder bei der Domain-Vorprüfung lassen die
bisherige Website laufen. Nach Beginn des Wartungsfensters wird der Tunnel bei
einem Fehler gestoppt.

Nach Behebung der Ursache genügt `bash update.sh`, um die ausgewählte Version
erneut zu versuchen. Sie bleibt auch bei einem späteren Fehler in `.env`
eingetragen. Eine ältere Image-Version stellt eine bereits geänderte Datenbank
nicht zurück. Eine Rückkehr zur alten Version muss deshalb mit den Migrationen
und gegebenenfalls dem zusammengehörigen Backup abgestimmt werden.

## Einmalige Umstellung vom bisherigen Build-Ablauf

1. Ein Release mit den neuen Deployment-Dateien veröffentlichen und den grünen
   Workflow abwarten; siehe [RELEASE_IMAGES.md](RELEASE_IMAGES.md).
2. Im **bestehenden** Server-Projektordner die neuen Deployment-Dateien übernehmen,
   beispielsweise einmalig mit `git pull --ff-only`. Lokale Änderungen vorher
   prüfen und sichern. Projektordner und Compose-Projektname beibehalten.
3. Die vorhandene `.env` behalten. Die Werte `NGINX_IMAGE` und `CLOUDFLARED_IMAGE`
   aus `.env.example` ergänzen bzw. bewusst gewählte Versionen eintragen.
4. `bash update.sh v0.1.0` mit der tatsächlich veröffentlichten Version ausführen.
   Das Skript ergänzt `APP_IMAGE` automatisch. Keine Daten-Volumes löschen.

Die neuen festen Nginx-/Tunnel-Versionen können bei dieser Umstellung einmalig
einen Infrastrukturwechsel bedeuten. Spätere normale Updates laden diese Images
nur, wenn sie lokal fehlen. Änderungen an Compose, Host-Skripten oder der
Nginx-Konfiguration stehen künftig in den Release-Hinweisen und müssen gezielt
in das Serververzeichnis übernommen werden; ein Anwendungsimage ersetzt diese
Host-Dateien nicht.
