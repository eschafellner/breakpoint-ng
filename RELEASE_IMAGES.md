# Release-Images erstellen: Anleitung für Einsteiger

Ein **Release-Image** ist ein fertig gepacktes Programm mit Python und den
benötigten Bibliotheken. Der Vereinsserver lädt dieses Paket herunter. Er muss
das Programm dadurch bei einem Update nicht selbst bauen.

Für dieses Projekt übernimmt **GitHub Actions** das Erstellen, Testen und
Hochladen. Das Image liegt anschließend in **GitHub Container Registry**,
kurz **GHCR**. Dafür ist kein Docker-Hub-Konto erforderlich.

| Begriff | Bedeutung | Beispiel |
| --- | --- | --- |
| Repository | Projekt mit dem Quellcode auf GitHub | `eschafellner/breakpoint-ng` |
| Release | Benannte, veröffentlichte Programmversion | `v0.1.0` |
| Tag | Markierung des zugehörigen Code-Stands | `v0.1.0` |
| Image-Adresse | Adresse des fertigen Pakets | `ghcr.io/eschafellner/breakpoint-ng:v0.1.0` |
| Digest | Eindeutiger Fingerabdruck eines Image-Inhalts | `sha256:…` |

Die Versionsnummern in dieser Anleitung sind Beispiele. Ein Image existiert
erst, nachdem der Workflow erfolgreich abgeschlossen wurde.

## 1. Einmalig vorbereiten

Du brauchst ein GitHub-Konto mit Schreibzugriff auf das Repository.
Die neuen Dateien müssen bereits auf GitHub liegen, insbesondere
`.github/workflows/release-image.yml`, `.github/workflows/tests.yml` und
`Dockerfile`. Nur lokal gespeicherte Änderungen kann GitHub nicht verwenden.

Falls die Änderungen bisher nur auf deinem Rechner liegen, diese mit deinem
Git-Programm committen und anschließend **Push** ausführen. Bei GitHub Desktop
sind das **Commit** und danach **Push origin**. Den Branch merken, auf den du
die Änderungen hochgeladen hast.

Alternativ kannst du die **einmalige Vorbereitung dieser Umstellung** im Terminal
des lokalen Projektordners durchführen (Linux, macOS oder Git Bash):

```bash
git status
git add Dockerfile docker-compose.prod.yml .env.example .gitignore update.sh \
  scripts .github/workflows README.md DEPLOYMENT.md DEPLOYMENT_PRUEFUNG.md \
  ADMIN_HANDBUCH.md RELEASE_IMAGES.md UPDATES.md \
  tests/test_deployment.py tests/test_deployment_operations.py
git commit -m "Release-Images und vereinfachte Updates vorbereiten"
git push
```

`git status` zeigt die lokalen Änderungen. `git add` wählt die Dateien für den
Commit aus, `git commit` speichert diesen Stand lokal und erst `git push` lädt
ihn zu GitHub hoch. Dafür muss dein Git-Zugang zum Repository bereits eingerichtet
sein. Bei einem geschützten Branch die Änderungen wie im Repository üblich über
einen Pull Request übernehmen. Die echte `.env` mit Zugangsdaten gehört nicht
in den Commit; oben ist ausschließlich die Vorlage `.env.example` ausgewählt.

Auf der Repository-Seite muss der Reiter **Actions** verfügbar und aktiviert
sein. Falls GitHub beim ersten Öffnen eine Aktivierung anbietet, diese durchführen.
Bei organisatorischen Einschränkungen müssen die verwendeten GitHub- und
Docker-Actions erlaubt sein. Der Workflow besitzt selbst die zum Hochladen
benötigte Berechtigung `packages: write` und verwendet den automatisch von GitHub
bereitgestellten `GITHUB_TOKEN`. Ein eigener Token als Repository-Secret ist
für diesen Workflow normalerweise nicht nötig.

Für die automatische Erstellung brauchst du auf deinem Rechner weder Python
noch Docker. Docker wird erst auf dem Vereinsserver zum Installieren benötigt.

## 2. Einen Release im Browser anlegen

1. Das [GitHub-Repository](https://github.com/eschafellner/breakpoint-ng) öffnen.
   Bei einer eigenen Kopie die Seite dieser Kopie verwenden.
2. **Releases** öffnen und **Draft a new release** bzw. **Create a new release**
   auswählen.
3. Unter **Choose a tag** eine neue Version eingeben, zum Beispiel `v0.1.0`.
   Die Option zum Erstellen dieses neuen Tags wählen.
4. Bei **Target** den Branch auswählen, auf dem der gewünschte und geprüfte
   Code liegt. Er muss die neuen Workflow-Dateien enthalten.
5. Einen Titel und eine kurze Beschreibung der Änderungen eintragen.
   Änderungen an Deployment-Dateien, `.env` oder Datenbankmigrationen erwähnen,
   damit der Betreiber weiß, was bei der Installation erforderlich ist.
6. **Publish release** auswählen. Ein gespeicherter Entwurf startet den
   Image-Workflow noch nicht.

Versionsnummern beginnen mit `v` und enthalten drei Zahlen:
`v0.1.0`, `v0.1.1`, `v0.2.0`. Für einen ausdrücklich bezeichneten Testrelease
ist zum Beispiel `v0.2.0-rc.1` möglich. Jede veröffentlichte Version erhält
eine neue Nummer. Einen bestehenden Tag oder ein bestehendes Image nicht
nachträglich mit anderem Code überschreiben.

## 3. Die automatische Erstellung abwarten

Im Reiter **Actions** den neuen Lauf **Release image** öffnen. GitHub erledigt:

1. Versionsnummer prüfen.
2. Die bestehenden Anwendungstests mit SQLite und PostgreSQL ausführen,
   einschließlich der Deployment- und Nginx-Prüfungen.
3. Das Image bauen und darin die Django-Konfiguration sowie die gesammelten
   CSS-Dateien prüfen.
4. Images für `linux/amd64` und `linux/arm64` erstellen und bei GHCR hochladen.

Damit werden übliche Intel-/AMD-Server und viele ARM-Server abgedeckt. Docker
wählt beim Herunterladen automatisch die passende Variante aus.

Erst wenn der **gesamte Lauf grün** ist, das Release installieren. Ein roter
Lauf ist kein fertiges Release-Image. Den fehlgeschlagenen Schritt öffnen,
die Ursache korrigieren und für geänderten Code eine neue Version veröffentlichen.
Wenn nur ein vorübergehender Fehler auftrat und noch kein Image hochgeladen
wurde, lässt sich derselbe Lauf über **Re-run failed jobs** erneut versuchen.
Der Workflow verweigert das Überschreiben eines bereits vorhandenen Images.

Die Tests brauchen keinen Zugriff auf Vereinsdaten, Server-Zugangsdaten oder
den produktiven Cloudflare Tunnel. Eine Prüfung des laufenden Vereinsservers
erfolgt später während der Installation.

## 4. Die Image-Adresse finden

Den erfolgreichen Workflow-Lauf öffnen. Auf der Übersichtsseite steht unter
**Release-Image ist bereit** beispielsweise:

```text
ghcr.io/eschafellner/breakpoint-ng:v0.1.0
```

Das Schema lautet `ghcr.io/EIGENTÜMER/REPOSITORY:VERSION`. Der Workflow verwendet
den tatsächlichen Repository-Namen in Kleinschreibung, also auch bei einer Kopie
des Projekts. Die Zusammenfassung enthält außerdem den vollständigen Digest
und kopierbare Update-Befehle.

Der Tag ist leicht lesbar. Die Variante `ghcr.io/…@sha256:…` legt zusätzlich
exakt den Inhalt fest. Den vollständigen Digest aus der Zusammenfassung kopieren;
die Punkte in diesem Beispiel sind kein gültiger Digest.

## 5. Einmalig den Downloadzugriff festlegen

Ein neues GHCR-Paket ist zunächst privat. Auch ein öffentliches Quellcode-Repository
macht das Image nicht automatisch öffentlich.

Wenn das Anwendungsimage öffentlich heruntergeladen werden darf:

1. Nach dem ersten erfolgreichen Build auf der Repository-Seite **Packages**
   öffnen oder auf deiner GitHub-Profilseite zum Reiter **Packages** wechseln.
2. Das Container-Paket `breakpoint-ng` auswählen.
3. **Package settings** öffnen und unter **Change visibility** die Sichtbarkeit
   auf **Public** ändern. Dafür ist die entsprechende Verwaltungsberechtigung nötig.

Ein öffentliches Image kann der Server ohne Docker-Anmeldung herunterladen.
Das Image enthält Anwendungscode und Bibliotheken. Vereinsdaten, `.env`,
Uploads und Backups werden durch `.dockerignore` vom Build ausgeschlossen.
Geheimnisse dürfen auch nicht in eingecheckten Quelldateien stehen.

Wenn das Image privat bleiben soll, den nächsten Abschnitt zur Anmeldung verwenden.
GitHub erklärt die Zugriffsregeln in der
[Dokumentation zur Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## 6. Das Image auf dem Server verwenden

Bei einer bereits eingerichteten Installation im bisherigen Projektordner:

```bash
bash update.sh v0.1.0
```

Die Kurzform gilt für `ghcr.io/eschafellner/breakpoint-ng`. Bei einer eigenen
Kopie den vollständigen Befehl aus der Workflow-Zusammenfassung verwenden.
Das Skript speichert die Auswahl in der bestehenden `.env`.
Die [kurze Update-Anleitung](UPDATES.md) erklärt Erfolgsmeldung und Fehlerfälle.

Bei einer **neuen Installation** zuerst `.env` anhand von `.env.example`
einrichten und dort die fertige Image-Adresse unter `APP_IMAGE` eintragen:

```dotenv
APP_IMAGE=ghcr.io/eschafellner/breakpoint-ng:v0.1.0
```

Danach der [Einrichtungsanleitung](DEPLOYMENT.md) folgen.
Die Beispielversion muss zu deinem tatsächlich veröffentlichten Release passen.

Für ein **privates Image** zusätzlich einmalig auf dem Server:

```bash
docker login ghcr.io -u DEIN-GITHUB-NAME
```

Als Passwort einen GitHub **Personal access token (classic)** mit `read:packages`
und Zugriff auf das Paket eingeben. Er wird in den GitHub-Kontoeinstellungen unter
**Developer settings → Personal access tokens → Tokens (classic)** erstellt.
Bei Organisationen kann zusätzlich eine SSO-Freigabe erforderlich sein.
Der Token gehört in die Passwortabfrage, nicht in `.env` oder eine Git-Datei.
Die Anmeldung mit demselben Betriebssystembenutzer ausführen, der anschließend
`bash update.sh` startet.

## 7. Die nächste Version veröffentlichen

Änderungen committen und auf GitHub hochladen. Danach die Schritte 2 bis 4 mit
einer **neuen** Nummer wiederholen, beispielsweise `v0.1.1`.
Der Betreiber führt dann `bash update.sh v0.1.1` aus. Das Veröffentlichen eines
Images installiert es nicht automatisch auf dem Vereinsserver.

Ändern sich Compose-Dateien, Host-Skripte oder die Nginx-Konfiguration, dies in
den Release-Hinweisen nennen. Diese Dateien müssen gesondert auf den Server
übernommen werden; gewöhnliche Änderungen an der Anwendung kommen über das Image.

## Häufige Probleme

| Meldung / Situation | Nächster Schritt |
| --- | --- |
| Nach „Publish release“ erscheint kein Workflow | Prüfen, ob Actions aktiviert ist und der gewählte Tag die neuen Workflow-Dateien enthält. |
| Versionsprüfung ist rot | Einen neuen Release mit einem Tag wie `v0.1.0` anlegen. |
| Tests sind rot | Fehlgeschlagenen Schritt öffnen und den Code korrigieren. Für den korrigierten Code eine neue Versionsnummer verwenden. |
| `permission_denied` beim Hochladen | Paketberechtigungen und Organisationsregeln prüfen. Ein schon vorhandenes Paket muss dem Repository Schreibzugriff erlauben. |
| `denied` / `unauthorized` auf dem Server | Paket öffentlich machen oder mit einem zum Paket berechtigten `read:packages`-Token anmelden. |
| `manifest unknown` / Image nicht gefunden | Image-Adresse und Versionsnummer vergleichen; den erfolgreichen Abschluss des Workflows prüfen. |
| Version existiert bereits | Die vorhandene Version verwenden oder geänderten Code unter einer neuen Versionsnummer veröffentlichen. |

## Optional: Ein Image auf dem eigenen Rechner bauen

Der automatische GitHub-Weg oben ist der normale Ablauf. Zum lokalen Prüfen
kannst du mit installiertem Docker im Projektordner bauen:

```bash
docker build -t breakpoint-ng:v0.1.0-test .
```

Dieses Image liegt nur auf deinem Rechner. Es ist dadurch weder veröffentlicht
noch für den Vereinsserver erreichbar. Das lokale Bauen ersetzt die Tests und
die Veröffentlichung des Release-Workflows nicht.

Technische Grundlagen:
[Images mit GitHub Actions veröffentlichen](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images),
[Images für mehrere Plattformen bauen](https://docs.docker.com/build/ci/github-actions/multi-platform/),
[Docker-Build-Cache nutzen](https://docs.docker.com/build/cache/optimize/).
