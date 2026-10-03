# Breakpoint-NG: Prüfung von Bugs und Geschäftslogik

Stand: 03.10.2026. Geprüft wurden die sieben Anwendungsbereiche, ihre Views,
Admin-Abläufe, Hintergrundaufgaben, die Buchungsoberfläche sowie Migrationen
und Deployment. Korrekturen und Tests liegen im lokalen Arbeitsstand.

## Behobene Fehler

| Bereich | Fehler und korrigiertes Verhalten |
| --- | --- |
| Anmeldung | E-Mail-Großschreibung wird berücksichtigt; Sperrzähler arbeiten atomar in einem echten 15-Minuten-Fenster. Ein richtiges Passwort bei unbestätigter E-Mail zählt nicht als falscher Versuch. Weiterleitungen bleiben auf zulässige Hosts beschränkt; Logout erfordert POST. |
| Registrierung | Passwortregeln, Geburtsdatum, Mitgliedschaftsart und E-Mail-Dubletten werden geprüft. Ungültige Anträge hinterlassen kein halbfertiges Benutzerkonto. Bestätigungslinks verwenden die konfigurierte Vereinsadresse bzw. die Anfrageadresse. |
| Berechtigungen | Mitgliederrechte benötigen eine aktuell gültige aktive Mitgliedschaft und ein aktives, bestätigtes Konto. `is_staff` allein ersetzt keine fachliche Rolle. Vereinsrollen erhalten ihre zuvor fehlenden Django-Modellberechtigungen. |
| Mitgliedschaften | Freischaltungen arbeiten mit aktuellen, gesperrten Datensätzen; mehrfaches Freischalten und kollidierende Mitgliedsnummern werden verhindert. Manuelle Mitgliedschaften synchronisieren den Kontotyp. CSV-Fehler werden je Zeile gemeldet; neue Importkonten haben kein bekanntes Standardpasswort. |
| SEPA | IBANs werden statt im Klartext verschlüsselt gespeichert. Bestehende Daten werden migriert; Schlüsselrotation und Rückmigration sind getestet. Ein falscher Schlüssel führt zu einem Fehler, nicht zu vermeintlich gültigen Daten. |
| Finanzen | Beträge müssen endlich, positiv und speicherbar sein. Überzahlung, Zahlung auf erledigte Forderungen und unzulässige Stornierungen werden abgewiesen. Teilzahlungen reduzieren die offene Summe. Parallele Beitragsläufe erzeugen keine doppelten Forderungen. CSV-Formelzeichen werden entschärft. |
| Finanz-Admin | Manuelle Forderungen laufen durch validierte Services. Bestehende Forderungen, Zahlungen und Preispositionen sind gegen direkte Bearbeitung geschützt; Erlass ist nur für vollständig unbezahlte offene Forderungen erlaubt. |
| Platzbuchungen | Buchungen prüfen Öffnungszeiten, Saison, volle Slots, Dauer, Teilnehmer, Fristen und Kontingente. Benutzer- und Platzsperren verhindern parallele Doppelbuchungen sowie das Umgehen des Benutzerlimits über verschiedene Plätze. |
| Preise und Oberfläche | Vorschau und Speicherung verwenden dieselbe serverseitige Preisberechnung. Regeln zu Saison, Wochentag und Uhrzeit sowie Gastspieler und platzbezogene Extras werden berücksichtigt. Veraltete Vorschauantworten werden verworfen; bei Fehlern bleibt die verbindliche Buchung deaktiviert. |
| Sperren und Erinnerungen | Platzsperren und Stornierungen prüfen Rollen und aktuelle Datensätze. Bereits gezahlte Forderungen bleiben erhalten. Erinnerungen sind wiederholbar ohne Mehrfachversand; ein Versandfehler markiert die Erinnerung nicht als erledigt. |
| News und Bilder | Artikel-HTML wird auch beim Admin-Speichern und beim Anzeigen alter Inhalte bereinigt. Interne Kategorien und Bilder folgen den tatsächlichen Zugriffsrechten. Galeriegrößen enthalten echte JPEG-Daten; ungültige Uploads erzeugen keine Restdateien. |
| Turnieranmeldung | Kapazität, Frist, Mitgliedschaft, Partner und Mehrfachanmeldungen werden geprüft. Partnerbestätigung und Rückzug besitzen geschützte POST-Abläufe. Unbestätigte Partnerschaften verfallen nach Anmeldeschluss per stündlichem Celery-Job. |
| Turnierspiele | Ergebnisse müssen zur Satzfolge und zum Sieger passen; fehlerhafte Tiebreaks und widersprüchliche Resultate werden abgewiesen. Ein bereits abgeschlossenes Folgespiel wird nicht durch eine nachträgliche Siegeränderung beschädigt. Gesetzte erhalten passende Freilose. Terminänderungen erhalten bei Konflikten die bisherige Sperre. |
| Gemeinsame Abläufe | Benachrichtigungen erfolgen nach erfolgreichem Transaktionsabschluss; Rollback erzeugt keine Erfolgs-E-Mail. Fehler werden protokolliert. Ungültige IDs erzeugen kontrollierte Fehler statt Serverabstürzen. Der eigene Datenexport umfasst eigene Mitgliedschaften, Zahlungen, Buchungen und Turnierteilnahmen. |

## Tests und Nachweise

Die anfängliche Regressionstestgruppe zeigte am alten Stand **51 Fehlschläge
bei 54 Fällen**. Die abschließende vollständige Suite enthält **212 Testfälle**:

| Lauf | Ergebnis |
| --- | --- |
| SQLite, Python 3.12 / Django 6.0 | 205 bestanden; sieben PostgreSQL-Paralleltests ausdrücklich übersprungen |
| PostgreSQL 16.15, gleiche vollständige Suite | 212 bestanden; keine übersprungenen Tests |
| Geschäftsservices (`apps/*/services.py`) | 89 % Zeilenabdeckung, 1.048 ausführbare Zeilen |
| Anwendungscode ohne Migrationen | 81 % Zeilenabdeckung, 3.259 ausführbare Zeilen |
| Django-Systemcheck und Migrationskonsistenz | Keine Fehler; `makemigrations --check --dry-run` ohne neue Änderungen |
| Ruff-Prüfung auf undefinierte Namen und Syntaxfehler | `F821,F822,F823,E9` bestanden |

Nach der abschließenden Ergänzung der Schlüsselweitergabe in Compose wurden
alle **39 Deployment-Tests nochmals erfolgreich ausgeführt**. Die tatsächlich
aufgelöste Konfiguration wird auf Fallback-Schlüssel in allen Anwendungsdiensten
geprüft; ein fehlender Hauptschlüssel führt wie erwartet zum Konfigurationsfehler.

Die neuen Tests prüfen neben erfolgreichen Vorgängen ausdrücklich unerlaubte
Rollen, abgelaufene Mitgliedschaften, doppelte Anmeldungen, falsche Weiterleitungen,
negative/ungültige Geldbeträge, Überzahlungen, veraltete Objektstände, ungültige
Tennisresultate, beschädigte Uploads, falsche Verschlüsselungsschlüssel,
fehlgeschlagene Transaktionen und gescheiterte Deployments. Erwartete Ablehnungen
werden mit ihren Auswirkungen auf Datenbank, Dateien oder E-Mail-Ausgang geprüft.

Die sieben PostgreSQL-Tests führen jeweils zwei echte Transaktionen parallel aus:

1. Zahlungen überschreiten zusammen den offenen Betrag nicht.
2. Für denselben Platz und Zeitraum gelingt nur eine Buchung.
3. Buchungen auf verschiedenen Plätzen überschreiten das Benutzerkontingent nicht.
4. Gleichzeitige Beitragsläufe erzeugen nur eine Forderung.
5. Gleichzeitige Freischaltungen erhalten unterschiedliche Mitgliedsnummern.
6. Derselbe Antrag erzeugt bei gleichzeitiger Freischaltung nur eine Mitgliedschaft.
7. Ein Turnierplatz wird nur einmal vergeben; die weitere Anmeldung kommt auf die Warteliste.

Die Testinstanz von PostgreSQL lief isoliert auf localhost mit eigener Datenbank;
Produktionsdaten wurden nicht verwendet. Das portable Paket stammt aus den
[offiziellen EDB-Binärarchiven](https://www.enterprisedb.com/download-postgresql-binaries).

Weitere Nachweise: echte HTTP-Anfragen gegen Nginx, Ausführung des tatsächlich
gerenderten Preisvorschau-JavaScripts mit Node.js, Vorwärts-/Rückwärtsmigration
bestehender SEPA-Daten und Abbruch der E-Mail-Migration bei Dubletten. Die
Deployment-Skripte werden für Fehlerfälle mit simulierten Docker-Aufrufen geprüft.

Testdateien: `tests/test_application_regressions.py`,
`tests/test_postgres_concurrency.py`, `tests/test_data_migrations.py`,
`tests/test_booking_preview_ui.py`, `tests/booking_price_preview.js` sowie die
vorhandenen Akzeptanz- und Deployment-Tests. `.github/workflows/tests.yml`
enthält vollständige SQLite- und PostgreSQL-Läufe mit Nginx. Der neue Workflow
ist angelegt; ein GitHub-Ausführungsergebnis liegt noch nicht vor.

## Auswirkungen auf ein bestehendes Deployment

Es gibt drei neue Migrationen:

- `accounts.0003`: Login-Zeitstempel und eindeutige E-Mail-Adressen ohne Unterscheidung der Groß-/Kleinschreibung.
- `courts.0002`: gespeicherter Versandzeitpunkt der Buchungserinnerung.
- `members.0002`: verschlüsseltes SEPA-Feld einschließlich Übernahme bestehender IBANs.

Vor dem Update E-Mail-Dubletten prüfen und den vorhandenen `DJANGO_SECRET_KEY`
beibehalten. Migrationen laufen über den vorbereitenden Deployment-Dienst.
Schlüssel und benötigte alte Schlüssel getrennt vom Datenbank-Backup sichern.
Die schrittweise Anleitung einschließlich Schlüsselrotation steht in
[DEPLOYMENT.md](DEPLOYMENT.md). Die Migrationen wurden nur in Testdatenbanken
ausgeführt; dieser Arbeitsstand wurde nicht auf das Produktionssystem deployed.

## Verbleibende Grenzen

- Wiederkehrende Platzsperren sind eine noch fehlende Bauplan-Funktion. Eine
  Wiederholungsregel wird jetzt ausdrücklich abgewiesen und nicht still ignoriert.
- Gruppen-/Hauptrunden-K.-o. bleibt Phase 2; die unterstützten Auslosungen sind
  K.-o. und Round Robin.
- Zeilenabdeckung misst ausgeführten Code und beweist nicht die Fehlerfreiheit
  aller Kombinationen. Einige Views, Formulare und Hilfsfunktionen besitzen
  noch ungetestete Zweige. Es wurde kein vollständiger Browser-, Last- oder
  Barrierefreiheitstest aller Seiten durchgeführt.
- Docker-Daemon, produktiver Cloudflare-Tunnel und SMTP-Verbindung standen lokal
  nicht zur Verfügung. Ein kompletter Compose-Start und ein echter DB-/Medien-Restore
  in Containern bleiben Betriebsprüfungen. HTTPS-/HSTS-Punkte stehen in
  [DEPLOYMENT_PRUEFUNG.md](DEPLOYMENT_PRUEFUNG.md).
