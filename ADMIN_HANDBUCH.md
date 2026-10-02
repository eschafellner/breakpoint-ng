# Admin- und Vereinshandbuch: Tennisverein-CMS

Dieses Handbuch richtet sich an den Vorstand, Kassier, Platzwart, Turnierleiter und Administratoren des Tennisvereins. Es erklärt alle zentralen Abläufe in verständlicher Sprache – ganz ohne Programmierkenntnisse.

---

## Inhaltsverzeichnis

1. [Zugang zum Administrationsbereich](#1-zugang-zum-administrationsbereich)
2. [Rollen und Berechtigungen im Verein](#2-rollen-und-berechtigungen-im-verein)
3. [Mitgliederverwaltung](#3-mitgliederverwaltung)
   - 3.1 Offene Mitgliedsanträge prüfen und freischalten
   - 3.2 Mitgliedsantrag ablehnen
   - 3.3 Mitglieder manuell anlegen oder per CSV importieren
   - 3.4 Interne Mitgliederliste (DSGVO)
4. [Beitragswesen und Finanzen (Kassier)](#4-beitragswesen-und-finanzen-kassier)
   - 4.1 Beitragslauf für die Saison durchführen
   - 4.2 Zahlungen erfassen (Überweisung / Bar)
   - 4.3 Offene Posten und Mahnungen im Kassier-Dashboard
   - 4.4 CSV-Export für die Buchhaltung
5. [Platzverwaltung und Buchungen (Platzwart)](#5-platzverwaltung-und-buchungen-platzwart)
   - 5.1 Plätze und Öffnungszeiten verwalten
   - 5.2 Platzsperren (Training, Wetter, Meisterschaft) eintragen
   - 5.3 Automatische Benachrichtigung bei Stornierungen
6. [Preise, Gastgebühren und Extras pflegen](#6-preise-gastgebühren-und-extras-pflegen)
   - 6.1 Gastgebühren anpassen
   - 6.2 Extras anlegen (z.B. Flutlicht, Hallenaufschlag, Ballmaschine)
7. [Turniere und Meisterschaften (Turnierleiter)](#7-turniere-und-meisterschaften-turnierleiter)
   - 7.1 Neues Turnier anlegen und ausschreiben
   - 7.2 Anmeldungen verwalten und Partnerbestätigungen
   - 7.3 Auslosung durchführen (K.-o.-Tableau oder Jeder-gegen-jeden)
   - 7.4 Spielergebnisse eintragen und Sieger ermitteln
   - 7.5 Spiele Plätzen zuweisen (automatische Platzsperre)
8. [News und Berichte veröffentlichen (Redakteur)](#8-news-und-berichte-veröffentlichen-redakteur)
   - 8.1 Artikel anlegen und formatieren
   - 8.2 Bildergalerie hinzufügen und Alt-Texte pflegen
   - 8.3 Zeitgesteuerte und mitglieder-exklusive Veröffentlichung
9. [Betrieb, Updates und Datensicherung (DevOps / Verein)](#9-betrieb-updates-und-datensicherung-devops--verein)
   - 9.1 Updates einspielen mit `./update.sh`
   - 9.2 Backups erstellen und wiederherstellen
   - 9.3 Cloudflare Tunnel & Sicherheit

---

## 1. Zugang zum Administrationsbereich

- **Startseite:** Aufruf der Vereins-Webseite im Browser (z.B. `https://tc-musterdorf.at`).
- **Anmeldung:** Klick oben rechts auf **„Anmelden“** mit Vereins-E-Mail und Passwort.
- **Admin-Menü:** Nach der Anmeldung erscheint in der Navigation der Menüpunkt **„Admin“** (bzw. **„Anträge“** und **„Kassier“** je nach Rolle).
- **Vollständiger Django-Admin:** Erreichbar unter `/admin/`.

---

## 2. Rollen und Berechtigungen im Verein

Die Plattform unterscheidet zwischen folgenden Rollen:

| Rolle | Aufgaben & Zugriffsrechte |
|---|---|
| **Besucher** | Öffentliche News lesen, Spielberichte ansehen, anonymisierten Buchungskalender sehen. |
| **Gast** | Registrierter Nutzer. Kann kostenpflichtig Plätze buchen und sich für offene Turniere anmelden. |
| **Mitglied** | Aktives Vereinsmitglied. Kostenlose Platzbuchung, Zugriff auf interne Mitgliederliste, Teilnahme an vereinsinternen Meisterschaften. |
| **Redakteur** | Verfassen und Veröffentlichen von Artikeln und Fotogalerien. |
| **Platzwart** | Sperren von Plätzen wegen Wetter/Pflege/Training, Pflege der Öffnungszeiten. |
| **Kassier** | Durchführung des jährlichen/monatlichen Beitragslaufs, Erfassung von Zahlungseingängen, Finanzexporte. |
| **Turnierleiter** | Anlegen von Turnieren, Auslosung von Tableaus, Ergebniserfassung. |
| **Administrator (Vorstand)** | Freischaltung neuer Mitglieder, Vereinsstammdaten, Zuweisung von Vereinsrollen. |

---

## 3. Mitgliederverwaltung

### 3.1 Offene Mitgliedsanträge prüfen und freischalten
1. Navigiere in der Menüleiste auf **„Anträge“** (oder im Admin unter *Mitgliedsanträge*).
2. Du siehst eine Liste aller Personen, die sich auf der Webseite registriert und die Mitgliedschaft beantragt haben.
3. Klicke auf die grüne Schaltfläche **„✓ Freischalten“**.
4. **Was das System automatisch erledigt:**
   - Der Benutzer wird sofort vom Typ *Gast* auf *Mitglied* hochgestuft.
   - Dem Mitglied wird automatisch die nächste freie Mitgliedsnummer zugewiesen (z.B. `TCM-0042`).
   - Eine Willkommens-E-Mail mit Mitgliedsnummer und Zugangsdaten wird an das Mitglied versendet.
   - Die Freischaltung wird revisionssicher im Änderungsprotokoll protokolliert.

### 3.2 Mitgliedsantrag ablehnen
1. In der Antragsliste neben dem Namen auf **„✕ Ablehnen“** klicken.
2. Im erscheinenden Feld die **Begründung** eingeben (z.B. *„Aufnahmestopp in der gewünschten Altersklasse“*).
3. Auf **„Ablehnen bestätigen“** klicken.
4. Der Antragsteller erhält automatisch eine E-Mail mit der Begründung. Sein Account bleibt als reines Gast-Konto für Buchungen erhalten.

### 3.3 Mitglieder manuell anlegen oder per CSV importieren
- **Einzeln anlegen:** Im Django-Admin unter *Benutzer* oder *Mitgliedschaften* auf *Hinzufügen* klicken.
- **CSV-Sammelimport:**
  1. Gehe auf **„Anträge“** → **„+ CSV-Import“**.
  2. Wähle eine CSV-Datei aus (oder füge den Text direkt ein).
  3. Format der Spalten:
     `email,first_name,last_name,phone,membership_type`
  4. Auf **„CSV-Import ausführen“** klicken.
  5. Das System legt die Konten an. Fehlerhafte Zeilen (z.B. unbekannte Mitgliedschaftsart) werden mit genauer Zeilennummer angezeigt, ohne den restlichen Import zu stoppen.

### 3.4 Interne Mitgliederliste (DSGVO)
- Unter dem Menüpunkt **„Mitglieder“** sehen aktive Vereinsmitglieder die Kontaktdaten (Name, Telefon, E-Mail) aller anderen aktiven Mitglieder zur Organisation von Spielpartnern.
- Gäste, Besucher und Antragsteller haben **keinen** Zugriff (sie erhalten die Meldung *Zugriff verweigert*).
- Jedes Mitglied kann die eigenen Daten jederzeit im **Profil** bearbeiten oder gemäß Art. 15 DSGVO als JSON-Datei herunterladen.

---

## 4. Beitragswesen und Finanzen (Kassier)

### 4.1 Beitragslauf für die Saison durchführen
1. Öffne das **„Kassier-Dashboard“** in der Navigation.
2. Oben rechts befindet sich die Schaltfläche **„⚡ Beitragslauf [Jahr] ausführen“**.
3. Klicke auf den Button und bestätige die Abfrage.
4. **Intelligente Automatik:**
   - Für jedes aktive Mitglied wird exakt eine Beitragsforderung gemäß seiner Mitgliedschaftsart erzeugt.
   - **Idempotenz (Sicherheit vor Doppelbuchungen):** Ein erneuter Klick erzeugt niemals doppelte Forderungen!
   - **Anteilige Berechnung:** Tritt ein Mitglied unterjährig bei (z.B. am 1. Juli), berechnet das System automatisch den reduzierten Beitrag (z.B. 50 % bei 6 verbleibenden Monaten).

### 4.2 Zahlungen erfassen (Überweisung / Bar)
1. Im Kassier-Dashboard in der Tabelle der offenen Forderungen nach dem Mitglied oder der Rechnungsnummer suchen.
2. In der Spalte **„Zahlung erfassen“** den gezahlten Betrag eintragen (Standard: Restbetrag).
3. Zahlungsart wählen (*Überweisung*, *Bar* oder *SEPA*).
4. Auf das grüne Häkchen **„✓“** klicken.
5. Bei vollständiger Zahlung wechselt der Status sofort auf **„Bezahlt“**, bei Teilzahlung auf **„Teilweise bezahlt“**.

### 4.3 Offene Posten und Mahnungen
- Das Dashboard zeigt oben in Echtzeit die Summe aller offenen Forderungen und die Anzahl überfälliger Posten.
- Über das Status-Filterfeld kann direkt nach *„Offen“* oder *„Teilweise bezahlt“* gefiltert werden.

### 4.4 CSV-Export für die Buchhaltung
- Durch Klick auf **„📥 CSV-Export“** wird die aktuelle Liste der Forderungen und Zahlungen als Excel-/Buchhaltungs-kompatible CSV-Datei heruntergeladen.

---

## 5. Platzverwaltung und Buchungen (Platzwart)

### 5.1 Plätze und Öffnungszeiten verwalten
- Im Django-Admin unter *Plätze* können Namen (z.B. *Centrecourt*, *Halle 1*), Beläge (Sand, Halle, etc.) und Ausstattungsmerkmale (Flutlicht) gepflegt werden.
- Jeder Platz hat konfigurierbare Öffnungszeiten je Wochentag und eine Slot-Länge (Standard: 60 Minuten).

### 5.2 Platzsperren eintragen
1. Im Buchungskalender oder unter `/courts/blockings/` auf **„Platzsperren verwalten“** gehen.
2. Platz auswählen, Grund wählen (*Training*, *Mannschaftsspiel*, *Turnier*, *Platzpflege*, *Wetter*).
3. Start- und Endzeit angeben sowie eine optionale Notiz (z.B. *„Plätze nach Unwetter gesperrt“*).
4. Auf **„Sperre eintragen“** klicken.

### 5.3 Automatische Stornierung & Benachrichtigung
- Wenn eine Sperre über bereits bestehende Buchungen gelegt wird, **storniert das System diese Buchungen automatisch**.
- Angefallene Gastgebühren werden sofort storniert.
- Die betroffenen Spieler erhalten sofort eine verständliche E-Mail mit der Begründung des Platzwarts.

---

## 6. Preise, Gastgebühren und Extras pflegen

**Keine Beträge sind im Code festgeschrieben! Alles kann im Admin angepasst werden:**

### 6.1 Gastgebühren anpassen
- Im Django-Admin unter **Preisregeln**:
  - `GUEST`: Stundenpreis für externe Gäste (z.B. 16,00 € / Stunde).
  - `GUEST_OF_MEMBER`: Gebühr pro Gastspieler, wenn ein Mitglied mit einem Gast spielt (z.B. 5,00 € pro Gast).
  - Preise gelten immer erst ab neuen Buchungen; bestehende Buchungen behalten den vereinbarten Preis.

### 6.2 Extras anlegen (Halle, Flutlicht, Ballmaschine)
- Im Django-Admin unter **Buchungs-Extras**:
  - **Bezeichnung:** z.B. *Flutlicht*, *Hallenaufschlag*, *Leihschläger*.
  - **Mitgliederpreis / Gästepreis:** Unterschiedliche Tarife möglich.
  - **Abrechnung:** *Pro Stunde* oder *Pro Buchung*.
  - **Modus:**
    - *Automatisch:* Wird für den zugewiesenen Platz immer berechnet (z.B. Hallenaufschlag).
    - *Optional:* Erscheint in der Buchungsmaske als Checkbox zum Auswählen (z.B. Flutlicht).
  - Neue Extras erscheinen **sofort ohne Programmieraufwand** in der Online-Buchungsmaske!

---

## 7. Turniere und Meisterschaften (Turnierleiter)

### 7.1 Neues Turnier anlegen
1. Im Admin oder Menü unter *Turniere* auf *Hinzufügen*.
2. Name, Zeitraum, Anmeldeschluss, Startgebühren für Mitglieder und Gäste festlegen.
3. Berechtigung wählen: *Nur Mitglieder* oder *Mitglieder und Gäste*.
4. Konkurrenzen anlegen (z.B. *Herren Einzel*, *Damen Doppel*, *Mixed*) und Format wählen (*K.-o.-System* oder *Jeder gegen jeden*).

### 7.2 Anmeldungen und Warteliste
- Spieler melden sich online mit einem Klick an.
- Bei Doppelbewerben wählt der Spieler seinen Partner aus; die Anmeldung wird aktiv, sobald der Partner bestätigt.
- Ist die maximale Teilnehmerzahl erreicht, setzt das System weitere Spieler automatisch auf die **Warteliste**. Zieht ein Spieler zurück, rückt der nächste Wartelisten-Spieler automatisch nach.

### 7.3 Auslosung durchführen
1. Nach Anmeldeschluss im Admin bei der Konkurrenz auf die Auslosung klicken.
2. **K.-o.-System:** Das System generiert automatisch ein volles Tableau (z.B. 16er-Raster für 11 Spieler mit 5 Freilosen). Die Gesetzten 1 und 2 werden an entgegengesetzten Enden platziert und können erst im Finale aufeinandertreffen.
3. **Jeder gegen jeden (Round Robin):** Das System erzeugt den kompletten Spielplan aller Paarungen.

### 7.4 Ergebniseingabe
1. Beim jeweiligen Spiel im Turnier-Tableau auf **„Ergebnis eintragen“** klicken.
2. Sätze eingeben (z.B. `6:4`, `7:5` oder Match-Tiebreak `10:8`). Ungültige Tennisstände (wie `6:5`) werden vom System abgelehnt.
3. Bei K.-o.-Spielen rückt der Sieger **automatisch in das nächste Runden-Match** vor!
4. Bei Round-Robin wird die Tabelle in Echtzeit nach Siegen, Satzdifferenz und Game-Differenz aktualisiert.

### 7.5 Plätze für Turnierspiele reservieren
- Bei Zuweisung eines Platzes und Termins zu einem Spiel erzeugt das System automatisch eine Platzsperre (*Turnier*).
- Gibt es eine Terminkollision mit einer Buchung, warnt das System sofort.

---

## 8. News und Berichte veröffentlichen (Redakteur)

### 8.1 Artikel anlegen
1. Im Admin unter *Artikel* auf *Hinzufügen*.
2. Titel, Teaser (Kurzfassung für Startseite) und ausführlichen Inhalt eingeben.
3. Formatierungen (Fett, Überschriften, Aufzählungen, Tabellen) sind direkt im Editor möglich. Schädlicher Code wird automatisch bereinigt.

### 8.2 Bilder und Barrierefreiheit
- **Titelbild:** Beim Upload eines Titelbilds muss ein aussagekräftiger **Alt-Text** angegeben werden (z.B. *„Siegerfoto der Ortsmeisterschaft 2027 mit Vorstand“*).
- **Galeriebilder:** Weitere Bilder können angehängt werden. Das System skaliert jedes Bild automatisch in 3 Größen (Vorschaubild, Web-Größe und Großansicht).

### 8.3 Zeitsteuerung & Sichtbarkeit
- **Status:** *Entwurf*, *Veröffentlicht* oder *Archiviert*.
- **Zeitgesteuert:** Liegt das Veröffentlichungsdatum in der Zukunft, bleibt der Artikel bis zu diesem Zeitpunkt für Besucher unsichtbar.
- **Nur Mitglieder:** Vertrauliche Vereinsberichte können auf *„Nur Mitglieder“* gestellt werden. Gäste und Besucher erhalten beim Aufruf eine 404-Meldung.

---

## 9. Betrieb, Updates und Datensicherung

Die Plattform läuft vollautomatisch in Docker-Containern.

### 9.1 Updates einspielen mit `bash update.sh`
Wenn eine neue Version verfügbar ist, genügt ein einziger Befehl im Terminal des Servers:

```bash
bash update.sh
```

**Was dieses Skript automatisch erledigt:**
1. Es lädt den neuesten Quellcode herunter.
2. Es baut das neue Anwendungsimage und prüft die Konfiguration.
3. Es stoppt die Anwendungsdienste für ein Wartungsfenster.
4. Es führt Datenbank-Migrationen aus und sammelt versionierte CSS-/JavaScript-Dateien.
5. Es startet Django und Nginx und prüft die tatsächliche HTTP-Auslieferung.
6. Erst nach erfolgreicher Prüfung startet es die Hintergrunddienste und den Tunnel.

Während des Wartungsfensters ist die Webseite kurzzeitig nicht erreichbar.
Vor einem Update müssen Datenbank und das Docker-Volume `media_prod_volume`
gesichert werden. Bei einem Fehler bricht das Skript ab; ein fehlgeschlagenes
Update wird nicht als erfolgreich gemeldet. Details: [DEPLOYMENT.md](DEPLOYMENT.md).

### 9.2 Backups erstellen und wiederherstellen

#### Backup erstellen:
```bash
./scripts/backup.sh
```
Erstellt im Ordner `./backups/` eine komprimierte Sicherung der gesamten Datenbank und aller Medien-Uploads mit Zeitstempel.

#### Wiederherstellung (Restore auf neuem System):
```bash
./scripts/restore.sh backups/db_backup_JJJJMMTT_HHMMSS.sql.gz backups/media_backup_JJJJMMTT_HHMMSS.tar.gz
```
Stellt die Datenbank und alle hochgeladenen Bilder 1:1 wieder her.

### 9.3 Cloudflare Tunnel & Sicherheit
- Die Vereins-Webseite ist über einen verschlüsselten Cloudflare Tunnel angebunden.
- Das Tunnelziel muss im Cloudflare-Dashboard auf `http://nginx:80` eingestellt sein.
- Nginx liefert die Web-Dateien aus; Django prüft vor der Bildauslieferung die Zugriffsrechte.
- Es müssen **keine offenen Ports** am Router oder Vereinsheim-Internet freigeschaltet werden.
- HTTPS-Zertifikate, Schutz vor DDoS-Angriffen und SSL-Verschlüsselung übernimmt Cloudflare automatisch.
- Bei 5 falschen Passwort-Eingaben innerhalb von 15 Minuten wird ein Benutzerkonto automatisch temporär gesperrt.

---

*TC Musterdorf – Tennisverein-CMS Handbuch Version 1.0*
