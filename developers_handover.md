# Breakpoint-NG – Entwickler-Handover Dokumentation

**Stand:** 07. Oktober 2026  
**Autor:** Fullstack Engineering  
**Version:** 0.3.0 (Security & MVP Workflow Review)  
**Repository:** `breakpoint-ng`

---

## 1. Projektübersicht & Tech-Stack

**Breakpoint-NG** ist ein vollwertiges Web-Portal und Vereins-CMS für Tennisclubs mit integriertem Platzbuchungssystem, Turnierverwaltung, Mitgliederadministration und Beitragsverwaltung.

### Kerntechnologien
* **Backend:** Python 3.12+, **Django 6.0**, Celery (Tasks & Beat), PostgreSQL 16, Redis 7
* **Frontend:** Django Templates, HTMX 1.9+, Vanilla JavaScript (ES6+), Vanilla CSS mit Design-Tokens
* **Infrastruktur & Ops:** Docker & Docker Compose, Gunicorn, Nginx, Let's Encrypt / Cloudflare Tunnel
* **Design & Branding:** Sandplatz-Rot (`--clay: #B94E33`), Dunkelgrün (`--court: #1E3B2F`), Tennisball-Gelb (`--ball: #D7E64A`), Kreideweiß (`--chalk: #FBF8F3`)

---

## 2. Aktueller Entwicklungsstand

Der vorherige Entwicklungszyklus hatte zwei Schwerpunkte; die anschließenden Korrekturen des Code-Reviews sind in Abschnitt 8 dokumentiert:
1. **Vollständige Progressive Web App (PWA) Integration** (Installierbarkeit, Service Worker, dynamisches Manifest, Offline-Notfallmodus).
2. **Umfassendes Mobile UI/UX Audit & Refactoring** (Behebung von Überlagerungen, responsive Tabellen, Swipe-Navigation und mobile Touch-Optimierung).

---

## 3. Implementierte Features im Detail

### 3.1 Progressive Web App (PWA)

Die Web-Applikation kann nun auf allen modernen mobilen Betriebssystemen (iOS, Android) sowie Desktop-Browsern (Chrome, Edge) nativ installiert und über den Homescreen gestartet werden.

#### A. Dynamisches Web App Manifest (`/manifest.webmanifest` & `/manifest.json`)
* **Route:** Ausgeliefert über `apps.core.views.manifest_view` mit Header `Content-Type: application/manifest+json`.
* **Dynamische Daten:** Name (`name`), Kurzname (`short_name`) und Slogan (`description`) werden live aus dem Datenbank-Singleton `ClubSettings.get_settings()` ausgelesen. Bei Namensänderungen des Vereins im Backend aktualisiert sich das Manifest ohne Codeänderung sofort.
* **Farbwerte:** `theme_color` und `background_color` sind auf das Breakpoint-Dunkelgrün (`#1E3B2F`) gesetzt.
* **App-Shortcuts (Quick Actions):** Beim längeren Gedrückt-Halten des App-Icons auf Android/iOS:
  1. *Platz buchen* (`/courts/calendar/`)
  2. *Aktuelle News* (`/news/`)
  3. *Mein Profil* (`/accounts/profile/`)

#### B. Generiertes Übergangs-Logo & PWA-Iconset
* **Skript:** [`scripts/generate_pwa_icons.py`](file:///home/edgar/Videos/breakpoint-ng/scripts/generate_pwa_icons.py) generiert mathematisch scharfe Vektor- und Raster-Grafiken via Cairo & Pillow.
* **Design:** Tennisball mit Nahtlinien, weißen Platzkreidelinien und Breakpoint-Akzent auf dunkelgrünem Radialverlauf.
* **Dateien in [`static/icons/`](file:///home/edgar/Videos/breakpoint-ng/static/icons/):**
  * `icon.svg` – Skalierbare Vektor-Grafik
  * `icon-192x192.png` & `icon-512x512.png` – Standard-Icons für App-Launcher
  * `icon-maskable-512x512.png` – Maskierbares Icon mit Safe-Area-Padding (80% Zone) für Android Adaptive Icons
  * `apple-touch-icon.png` (180 × 180 px) – Spezifisch für iOS Home-Screens
  * `favicon-32x32.png` & `favicon.ico` – Standard-Browser-Favicons

#### C. Service Worker & Caching-Strategie ([`static/js/sw.js`](file:///home/edgar/Videos/breakpoint-ng/static/js/sw.js))
* **Scope & Auslieferung:** Ausgeliefert über Django unter `/sw.js` via `apps.core.views.service_worker_view` mit HTTP-Headern `Service-Worker-Allowed: /` und `Cache-Control: no-cache, no-store, must-revalidate`.
* **Strategien:**
  * **Navigation (HTML-Dokumente):** Ausschließlich Netzwerk; HTML der aufgerufenen Seiten wird nicht gespeichert. Bei Netzausfall wird nur die separat gespeicherte, öffentliche Route `/offline/` ausgegeben.
  * **Transaktionen (POST / PUT / DELETE):** Werden **grundsätzlich nicht gecacht**, um Fehl- oder Doppelbuchungen zu vermeiden.
  * **Statische Ressourcen unter `/static/` (CSS, JS, Fonts, Icons):** *Stale-While-Revalidate*, sofern die Antwort weder privates HTML noch `private`/`no-store` enthält. Manifest, API und Medien werden nicht vom Service Worker gecacht. Alte Breakpoint-Caches werden bei Aktivierung der Version `breakpoint-v2` entfernt.

#### D. Backend-wartbare Offline-Notfallseite (`/offline/`)
* **Datenmodell:** Neues Feld in [`ClubSettings`](file:///home/edgar/Videos/breakpoint-ng/apps/core/models.py):
  * `offline_emergency_info`: Textfeld für Platz- und Notfallhinweise bei Ausfall der Internetverbindung.
  * Administrierbar im Django-Admin im Fieldset *„PWA & Offline-Modus“*.
* **Migration:** [`apps/core/migrations/0002_clubsettings_offline_emergency_info.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/migrations/0002_clubsettings_offline_emergency_info.py).
* **Template ([`templates/core/offline.html`](file:///home/edgar/Videos/breakpoint-ng/templates/core/offline.html)):**
  * Zeigt bei Verbindungsverlust Notfallhinweise, Telefonnummer (klickbar als Anruf), E-Mail und Anschrift an.
  * Auto-Reconnect: Lauscht auf das Browser-Event `window.addEventListener('online', ...)`, zeigt eine Erfolgsmeldung und lädt die Seite automatisch neu, sobald das Netz zurückkehrt.

#### E. Client-PWA-Integration & Installations-Hinweise ([`static/js/pwa.js`](file:///home/edgar/Videos/breakpoint-ng/static/js/pwa.js))
* Registriert den Service Worker transparent.
* **Android / Desktop Chrome:** Fängt `beforeinstallprompt` ab und zeigt ein dezentes, schwebendes Banner mit *„Installieren“*-Aktion.
* **iOS Safari:** Erkennt iOS-Geräte und blendet nach kurzer Verweildauer eine visuelle Hilfestellung ein (*„Teilen-Symbol ➔ Zum Home-Bildschirm“*).
* **Dismissal-Speicherung:** Das Schließen des Banners wird für 14 Tage in `localStorage` gemerkt, um Nutzer nicht zu belästigen. Bereits installierte Apps (`display-mode: standalone`) zeigen das Banner nicht.

---

### 3.2 Mobile UI/UX & Responsiveness Audit

Alle Templates und CSS-Regeln wurden gezielt für Bildschirme zwischen 320px und 860px optimiert.

#### A. Behebung der Rahmenlinien-Kollision im Hero
* **Problem:** `.court-lines::before` zeichnete eine absolute 3px-Linie mit `inset: 24px;`. Da der Inhalts-Container `.wrap` bei `20px` begann, schnitt die weiße Linie genau durch die Anfangsbuchstaben von *„SPIEL, SATZ UND VEREIN.“* und das Subtitle-Element. Zudem kollidierte die untere Kante mit der Score-Box.
* **Lösung:**
  * Auf Mobil- und Tablet-Geräten (`max-width: 860px`) werden `.court-lines::before`, `.court-lines::after` und `.court-lines .service` vollständig ausgeblendet (`display: none !important`).
  * Auf Desktop-Geräten wurde der Innenabstand von `.hero .wrap` auf `48px` erhöht, sodass Text immer mindestens 24px Abstand zur Rahmenlinie hält.
  * Hero-Padding mobil von 90px auf 44px reduziert; `.hero-score` fungiert nun als saubere, responsive Karte in voller Breite.

#### B. Header & Mobile Navigation ([`templates/base.html`](file:///home/edgar/Videos/breakpoint-ng/templates/base.html))
* **Unsichtbares Profil behoben:** `.user { display: none; }` im mobilen CSS blendete zuvor das eingeloggte Profil komplett aus. Jetzt wird das Benutzerprofil mit Avatar und Namen oben im Burger-Menü ansprechend dargestellt.
* **Touch-Targets:** Alle Menüeinträge, Login- und Logout-Buttons haben nun volle Breite und mindestens 44px Berührungsfläche.
* **Lange Vereinsnamen:** Das Vereinslogo/der Name wird mobil mit Text-Ellipsis vor dem Burger-Button abgesichert, um Umbrüche zu verhindern.

#### C. Platzbuchungskalender ([`templates/courts/calendar.html`](file:///home/edgar/Videos/breakpoint-ng/templates/courts/calendar.html))
* **Sticky Uhrzeit-Spalte:** Beim horizontalen Wischen durch die Tennisplätze (Platz 1–4, Halle) bleibt die **Uhrzeit-Spalte fixiert am linken Rand stehen** (`position: sticky; left: 0; z-index: 2`). Die Zuordnung der Zeilen bleibt jederzeit erhalten.
* **Wischbarer Tagesstreifen (`.daypicker`):** Horizontales Wischen mit dem Finger (`overflow-x: auto; flex-wrap: nowrap; scrollbar-width: none`), statt unruhiger mehrzeiliger Umbrüche.
* **Touch-Slots:** Mindesthöhe der Slots auf 44px angehoben.
* **Sidebar:** Buchungsübersicht verliert mobil die `sticky`-Eigenschaft, um die Platzansicht nicht zu verdecken.

#### D. Turnierbäume & Datentabellen
* **Turnierbäume ([`templates/tournaments/detail.html`](file:///home/edgar/Videos/breakpoint-ng/templates/tournaments/detail.html)):** `.bracket` wurde von einem brechenden Grid auf horizontales Flexbox-Scrolling umgestellt (`display: flex; overflow-x: auto; .round { min-width: 220px; }`). Viertelfinale, Halbfinale und Finale bleiben nebeneinander angeordnet und lassen sich seitlich scrollen.
* **Tabellen (Kassier, Mitglieder, Sperren):** Sämtliche `.card`-Container mit `table.data` unterstützen nun horizontales Touch-Scrolling (`overflow-x: auto; -webkit-overflow-scrolling: touch;`). Kein Quetschen von Tabelleninhalten.
* **Schutz vor Viewport-Wackeln:** `html, body { overflow-x: hidden; max-width: 100vw; }`.

#### E. Formulare (Registrierung, Profil)
* Alle 2-Spalten-Formularzeilen (`first_name` / `last_name`, `phone` / `birth_date`) brechen unter 580px Bildschirmbreite automatisch einspaltig um.

---

## 4. Dateistruktur & Änderungen

### Neue Dateien
* [`scripts/generate_pwa_icons.py`](file:///home/edgar/Videos/breakpoint-ng/scripts/generate_pwa_icons.py) – Asset-Generator für PWA-Icons (SVG, PNG, ICO via Cairo & Pillow)
* [`static/icons/`](file:///home/edgar/Videos/breakpoint-ng/static/icons/) – PWA-Icons (`icon.svg`, `icon-512x512.png`, `icon-192x192.png`, `icon-maskable-512x512.png`, `apple-touch-icon.png`, `favicon-32x32.png`, `favicon.ico`)
* [`static/js/sw.js`](file:///home/edgar/Videos/breakpoint-ng/static/js/sw.js) – Service Worker Logik
* [`static/js/pwa.js`](file:///home/edgar/Videos/breakpoint-ng/static/js/pwa.js) – Client-seitige PWA-Registrierung & Install-Prompts
* [`templates/core/offline.html`](file:///home/edgar/Videos/breakpoint-ng/templates/core/offline.html) – Offline-Notfall-Template mit Vereins- und Notfallkontakten
* [`apps/core/migrations/0002_clubsettings_offline_emergency_info.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/migrations/0002_clubsettings_offline_emergency_info.py) – Datenbankschema-Erweiterung

### Modifizierte Dateien
* [`apps/core/models.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/models.py) – Feld `offline_emergency_info` zu `ClubSettings` hinzugefügt
* [`apps/core/admin.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/admin.py) – Fieldset *„PWA & Offline-Modus“* in `ClubSettingsAdmin` registriert
* [`apps/core/views.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/views.py) – Views `manifest_view`, `service_worker_view`, `offline_view` ergänzt
* [`apps/core/urls.py`](file:///home/edgar/Videos/breakpoint-ng/apps/core/urls.py) – Routen `/manifest.webmanifest`, `/manifest.json`, `/sw.js`, `/offline/`
* [`templates/base.html`](file:///home/edgar/Videos/breakpoint-ng/templates/base.html) – PWA-Metatags, Icons, Safe-Area Viewport, Burger-Menü Struktur
* [`static/css/styles.css`](file:///home/edgar/Videos/breakpoint-ng/static/css/styles.css) – PWA-Banner, Safe-Area Insets, Hero-Korrektur, Sticky-Kalender, Tabellen-Scrolling
* [`docker-compose.yml`](file:///home/edgar/Videos/breakpoint-ng/docker-compose.yml) – Host-Port für PostgreSQL mit Fallback `${DB_HOST_PORT:-5433}:5432` entkoppelt
* [`tests/test_ap01_core.py`](file:///home/edgar/Videos/breakpoint-ng/tests/test_ap01_core.py) – Dedizierte Unit- und Integrationstests für PWA & Notfallmodus

---

## 5. Lokale Entwicklung & Ausführung

### Datenbank-Migrationen anwenden
```bash
python manage.py migrate
```

### PWA-Icons neu generieren (z. B. bei Farb- oder Designanpassungen)
```bash
python scripts/generate_pwa_icons.py
```

### Statische Dateien für Produktion sammeln
```bash
python manage.py collectstatic --noinput
```

### Tests ausführen
```bash
pytest tests/test_ap01_core.py
```

---

## 6. Offene Punkte & Roadmap für nachfolgende Entwickler

1. **Web Push Benachrichtigungen (Geplant für Phase 2):**
   * Backend-Vorbereitung: VAPID-Schlüssel generieren, Datenmodell `WebPushSubscription` für Benutzer anlegen.
   * Trigger in Celery-Tasks integrieren:
     * Wetterbedingte Platzsperren (Sofort-Push an betroffene Buchungen).
     * Buchungserinnerungen 60 Minuten vor Spielbeginn.
     * Turnier-Spielansetzungen und Partnerbestätigungen.
2. **Dynamischer Icon-Generator aus Vereinslogo:**
   * Aktuell werden die PWA-Icons über `generate_pwa_icons.py` bereitgestellt.
   * Künftiges Feature: Wenn ein Administrator im Django-Admin ein neues Logo hochlädt (`ClubSettings.logo`), soll per Signal oder Celery-Task automatisch das entsprechende PWA-Iconset im Medienverzeichnis erzeugt und im Manifest referenziert werden.
3. **Erweiterter Offline-Cache für News:**
   * Optional können kürzlich angesehene News-Artikel im IndexedDB- oder Dynamic-Cache persistent hinterlegt werden, um sie auch im Flugmodus vollständig lesbar zu machen.

---

*Dokumentation vollständig und geprüft.*


## 8. Umsetzung des Code-Reviews (07. Oktober 2026)

Alle 13 Befunde des Reviews wurden umgesetzt. Die zuvor vorhandenen PWA- und Mobile-Anpassungen bleiben Bestandteil des Projekts.

| Befund | Umsetzung |
| --- | --- |
| Private Seiten im Offline-Cache | Der Worker speichert ausschließlich öffentliche Assets und die anonym erzeugte Offline-Seite. Navigation und geschützte Medien werden nicht gespeichert; alte Breakpoint-Caches werden gelöscht. |
| Umgehung von E-Mail-Bestätigung und Kontosperre im Admin | `ClubAuthenticationBackend` prüft Aktivität, Bestätigung und Sperre für öffentliche und Admin-Anmeldung. Beide Wege teilen das Limit von fünf Fehlversuchen innerhalb von 15 Minuten. |
| Fehlende Turnieraktionen | Turnierleiter erreichen eine Teilnehmerübersicht mit ausdrücklicher Bestätigung vor K.-o.- oder Round-Robin-Auslosung. Termine und Ergebnisse sind für beide Formate über Formulare erreichbar. |
| Offenlegung der Partnerliste | Partnerwahl nur für angemeldete, teilnahmeberechtigte Konten. Sichtbarkeit erfordert freiwillige Freigabe im Profil; Bestandskonten bleiben zunächst unsichtbar. Manipulierte Partner-IDs werden abgewiesen. |
| Kein Zugang für importierte Konten | CSV-Import stellt Einladungen zum Festlegen eines eigenen Passworts bereit. Kein Standardpasswort; Admin-Aktion zum erneuten Anfordern eines Links. |
| Fehlende Wiederherstellung nach Mailausfall | Dauerhafte Versandaufträge, Wiederholungsstrategie und öffentliche Seite „Zugang anfordern“. Bestätigungs- und Passwortlinks verfallen nach 24 Stunden, sind einmalig und werden bei erneuter Anforderung ersetzt. |
| UTC in Buchungsmails | Bestätigungen, Stornierungen und Erinnerungen verwenden `Europe/Vienna`, einschließlich Sommer- und Winterzeit. |
| Verlorene Erinnerungen | Unversandte Erinnerungen im Zeitraum bis 25 Stunden vor Beginn werden auch nach einem Ausfall nachgeholt. Bereits begonnene oder stornierte Buchungen erhalten keine Erinnerung. |
| Löschbare Audit-Einträge | Einzel- und Sammellöschung im Admin sind gesperrt. Auslosung, Partnerbestätigung, Abmeldung, Ergebnisse und Termine protokollieren den handelnden Benutzer. |
| Ungefiltertes rechtliches HTML | `nh3` bereinigt Impressum und Datenschutz beim Speichern und beim Lesen vorhandener Inhalte. |
| Veraltete Offline-Kontakte | Gezielte Aktualisierung beim Online-Start, bei Navigation und nach Wiederherstellung der Verbindung. Ausschließlich der öffentliche Offline-Cache dient als Fallback; die Seite zeigt einen Aktualisierungszeitpunkt. |
| Monatsfälligkeit vor Eintritt | Fälligkeit entspricht dem späteren Datum aus regulärem Fälligkeitstag und Mitgliedschaftsbeginn. |
| Zusätzliche Finanzabfragen und 100er-Grenze | Zahlungssummen als Queryset-Annotation, zwei Abfragen für Gesamtkennzahlen und Pagination mit 50 Forderungen pro Seite. Filter bleiben beim Seitenwechsel erhalten. |

Zusätzlich: PostgreSQL- und Redis-Entwicklungsports sind an `127.0.0.1` gebunden. SMTP hat einen Timeout von zehn Sekunden. Unerwartete Fehler in Zahlungs-, Buchungs- und Turnierformularen werden intern protokolliert und mit kontrollierten Meldungen angezeigt.

### 8.1 Neue Migrationen und Verhalten beim Update

Zusätzlich zur bereits vorhandenen PWA-Migration `core.0002` sind erforderlich:

- `accounts.0004_user_account_access_sent_at_and_more`: Zeitstempel für Bestätigungs- und Zugangslinks sowie `allow_partner_search` mit Standard `False`. Bestehende, bislang undatierte Bestätigungslinks erhalten bei der Migration einmalig ein Übergangsfenster von 24 Stunden.
- `core.0003_outgoingemail`: Dauerhafte Versandaufträge mit Status, Versuchen, Fehler und nächstem Versandzeitpunkt.

Vor dem regulären Neustart `python manage.py migrate` ausführen und statische Dateien mit `python manage.py collectstatic --noinput` einsammeln. Das bestehende Deployment-Skript übernimmt Migrationen, statische Dateien und den Neustart von Web, Worker und Beat in seinem Wartungsablauf.

Der Wechsel des Authentifizierungs-Backends beendet alte Sitzungen beim nächsten Aufruf; Benutzer melden sich erneut an. Auch Mitarbeiterkonten benötigen eine bestätigte E-Mail-Adresse. Neu angelegte Superuser sind bereits bestätigt. Importierte Konten mit unbrauchbarem Passwort erhalten beim Import automatisch eine Einladung; für bereits vorhandene Importkonten die Admin-Aktion „Einladungs- oder Bestätigungslink senden“ oder `/accounts/recover/` verwenden. Zum Versand muss `PUBLIC_SITE_URL` die Vereinsadresse enthalten.

Die Partnerfreigabe wird bewusst nicht automatisch erteilt. Personen müssen im Profil „In der Doppelpartnersuche sichtbar sein“ aktivieren. Bei für Gäste offenen Turnieren können auch teilnahmeberechtigte Gäste diese freigegebenen Namen sehen.

### 8.2 Mailbetrieb und Fehlerbehandlung

Im Produktionsprofil ist `MAIL_DELIVERY_ASYNC=True`: Geschäftsaktionen speichern den Versandauftrag in derselben Datenbanktransaktion. Nach Commit wird er an Celery übergeben; bei Broker-Ausfall bleibt der Auftrag gespeichert. Beat verarbeitet fällige Aufträge zusätzlich jede Minute. **Worker und genau eine Beat-Instanz müssen laufen.**

Nach SMTP-Fehlern folgen bis zu acht Versuche mit wachsendem Abstand von 1, 2, 4, 8, 16, 32 und 60 Minuten. Nach Ausschöpfen der Versuche erscheint der Auftrag als „Versand fehlgeschlagen“. Administratoren können ihn unter „E-Mail-Versandaufträge“ prüfen und per Aktion „Fehlgeschlagene E-Mails erneut zum Versand vormerken“ zurücksetzen. Diese Aktion wird protokolliert. Im Entwicklungsprofil erfolgt der Versand nach Commit direkt über das konfigurierte Console-Backend; gespeicherte fehlgeschlagene Aufträge können durch `deliver_pending_emails` erneut verarbeitet werden.

Eine Datenbanksperre verhindert gleichzeitiges Versenden desselben Auftrags durch mehrere Worker. SMTP und Datenbank bilden keine gemeinsame Transaktion: Ein Prozessabbruch nach SMTP-Annahme und vor Speicherung des Erfolgs kann zu einer doppelten Zustellung führen. Die Geschäftsoperation selbst wird dadurch nicht wiederholt.

Audit-Schutz gilt für den Anwendungs-Admin. Er ersetzt kein externes, manipulationsgeschütztes Protokoll gegen Personen mit direktem Datenbankzugriff.

### 8.3 Verifikation

- 279 automatisierte Testfälle insgesamt, davon 30 zusätzliche Regressionen zum Review einschließlich Migration und Parallelzugriff.
- PostgreSQL: **276 bestanden, 3 übersprungen** (Nginx nicht lokal verfügbar). Alle zehn Paralleltests bestanden, einschließlich gleichzeitiger Anmeldefehler, Einladungen und Versandversuche.
- SQLite: **266 bestanden, 13 übersprungen** (zehn PostgreSQL-Paralleltests und drei Nginx-Tests).
- Der tatsächliche Service Worker wird in einer isolierten JavaScript-Laufzeit ausgeführt: Upgrade löscht private Alt-Caches, private Antworten werden nicht gespeichert, Offline-Kontakte werden gezielt aktualisiert und Assets funktionieren offline.
- `manage.py check`, `makemigrations --check --dry-run`, Ruff für undefinierte Namen und Syntax sowie JavaScript-Syntaxprüfungen bestanden.
- Browserprüfung mit ausschließlich temporären Testdaten: Anmeldung, K.-o.-Auslosung über Bestätigungsseite, Round-Robin-Ergebniserfassung mit aktualisierter Tabelle, Termin- und Ergebnisformulare sowie Zugangsanfrage.
- Testlauf mit Python 3.14.7, Django 6.0.9 und PostgreSQL 18.6. Produktionskombination Python 3.12/PostgreSQL 16 und Nginx werden weiterhin durch die vorhandene CI geprüft; dieser lokale Lauf bestätigt deren Ergebnis nicht.

Ein produktives Deployment wurde nicht durchgeführt. Die öffentliche Cloudflare-/HTTPS-Konfiguration, tatsächliche SMTP-Zustellung, native PWA-Installation auf Mobilgeräten und ein vollständiger aktueller Abhängigkeits-/Container-CVE-Scan bleiben Betriebsprüfungen für die reale Zielumgebung.
