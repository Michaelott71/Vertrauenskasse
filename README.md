# Vertrauenskasse

Modul zur Verwaltung der Getraenke-Vertrauenskasse im Betrieb: Bestandszaehlungen,
Belege, Freigetraenke und PayPal-Zahlungen erfassen und automatisch Soll/Ist-Kasse
sowie den Leergut-Abgleich berechnen.

## Tech-Stack

- **Django 5** (Python) mit **SQLite** als Datenbank
- Django Admin fuer die Verwaltung von Getraenken, Belegen, Freigetraenken und
  PayPal-Zahlungen
- Eigene, mobile-optimierte Views/Templates fuer die zwei Kernworkflows:
  Zaehlung erfassen und Auswertung ansehen
- Kein Build-Tooling, keine externen JS/CSS-CDN-Abhaengigkeiten (funktioniert offline)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Anschliessend im Browser unter `http://127.0.0.1:8000/` anmelden.

## Datenmodell

7 Tabellen (App `kasse`, siehe `kasse/models.py`):

| Tabelle | Zweck |
|---|---|
| `Getraenk` | Stammdaten: Name, Warenpreis, Pfand, Verkaufspreis, aktiv |
| `Zaehlung` | Ein Zaehlungszeitpunkt (Datum, Notiz) |
| `ZaehlungBestand` | Gezaehlter Voll-/Leergut-Bestand je Getraenk zu einer Zaehlung |
| `Beleg` | Einkaufsbeleg (Datum, Dateipfad, Gesamtbetrag, Haendler) |
| `BelegPosition` | Positionen eines Belegs je Getraenk (Nachschub) |
| `Freigetraenk` | Freigetraenke je Getraenk (reduzieren den Verkauf) |
| `PaypalZahlung` | PayPal-Zahlungen, optional einer Zaehlung zugeordnet und als Getraenke-Zahlung markiert |
| `DifferenzZuordnung` | Ordnet die Kassendifferenz einer Zaehlung Kategorien zu (Diebstahl, Nicht bezahlt, Freigetraenke, Veranstaltung) |

**Abweichungen vom urspruenglich vorgegebenen Schema:**

- `Zaehlung` hat zusaetzlich die Felder `bargeld_gezaehlt` und
  `bargeld_entnommen`. Ohne `bargeld_gezaehlt` liesse sich die geforderte
  Formel `Ist-Kasse = gezaehltes Bargeld + manuell markierte
  PayPal-Zahlungen` nicht berechnen. `bargeld_entnommen` wurde noetig, weil
  die Kasse in der Praxis manchmal bei einer Zaehlung geleert wird (Geld
  entnommen) und manchmal nicht — siehe Rechenlogik unten.
- `DifferenzZuordnung` ist eine komplett neue Tabelle (siehe "Differenz
  zuordnen" unten).

## Rechenlogik

Die komplette Berechnung steckt in `kasse/services.py`
(`berechne_auswertung(start, ende)`), fuer jedes Getraenk zwischen zwei
Zaehlungen `start` und `ende` — auch wenn dazwischen weitere Zaehlungen
liegen (z.B. bei der Monatsauswertung):

- `Verkauft = Vollbestand_Start + Nachschub − Vollbestand_Ende − Freigetraenke`
  (Nachschub = Summe `BelegPosition.anzahl` aus Belegen mit Datum im Zeitraum
  `(start.datum, ende.datum]`; Freigetraenke analog)
- `Soll-Kasse = Σ Verkauft(i) × Verkaufspreis(i)`
- `Bargeld-Einnahmen = bargeld_gezaehlt(ende) − (bargeld_gezaehlt(start) − bargeld_entnommen(start)) + Σ bargeld_entnommen(z)`
  fuer alle Zaehlungen `z` zeitlich zwischen `start` und `ende`. Damit
  funktioniert die Rechnung unabhaengig davon, ob die Kasse zwischendurch
  geleert wurde oder nicht:
  - Wird die Kasse bei jeder Zaehlung komplett geleert (`bargeld_entnommen`
    = `bargeld_gezaehlt`), ergibt das denselben Wert wie einfach
    `bargeld_gezaehlt(ende)`.
  - Bleibt das Geld einfach liegen (`bargeld_entnommen` = 0), ergibt das
    `bargeld_gezaehlt(ende) − bargeld_gezaehlt(start)`.
  - Mischformen (mal geleert, mal nicht) werden korrekt anteilig verrechnet.
- `Ist-Kasse = Bargeld-Einnahmen + Σ PayPal-Zahlungen mit ist_Getraenke_Zahlung=True`,
  fuer alle Zaehlungen zeitlich nach `start` bis inkl. `ende`
- `Kassendifferenz = Ist-Kasse − Soll-Kasse` (keine Rundungstoleranz)
- `Rueckgabe_an_Getraenkemarkt(i)` wird ebenfalls ueber alle Zaehlungen
  zwischen `start` (exklusiv) und `ende` (inklusiv) aufsummiert, nicht nur
  bei `ende` gezaehlt
- `Erwartetes Leergut(i) = Leergut_Start(i) + Verkauft(i) − Rueckgabe_an_Getraenkemarkt(i)`
- `Leergut-Differenz(i) = Leergut_Ende(i) − Erwartetes Leergut(i)`
  (negativ = Schwund/Pfandverlust, positiv = Fund/Fremdleergut)

Getestet in `kasse/tests.py` (`python manage.py test`), inkl. Szenarien mit
mehreren Zaehlungen im selben Auswertungszeitraum.

## Workflows

- **Neue Zaehlung** (`/zaehlung/neu/`): Datum, Notiz, gezaehltes Bargeld,
  entnommenes Bargeld sowie Voll-/Leergut-Bestand je aktivem Getraenk in
  einem mobilfreundlichen Formular erfassen.
- **Auswertung** (`/auswertung/`): Start- und End-Zaehlung auswaehlen, Soll/Ist-Kasse,
  Kassendifferenz und Leergut-Differenz je Getraenk sowie in Summe ansehen.
- **Monatsauswertung** (`/auswertung/monat/`): Monat auswaehlen, alle
  Zaehlungen des Monats als Liste (mit Link zur Auswertung zur jeweils
  vorherigen Zaehlung), plus ein Gesamtergebnis fuer den ganzen Monat
  (erste vs. letzte Zaehlung im Monat).
- **Differenz zuordnen** (Teil der Auswertungsseite): Die Kassendifferenz
  einer Zaehlung auf feste Kategorien aufteilen — Diebstahl, Nicht bezahlt,
  Freigetraenke (nicht erfasst), Veranstaltung inkl. Getraenke. Betrag mit
  gleichem Vorzeichen wie die Kassendifferenz eingeben. Die Seite zeigt an,
  wie viel bereits zugeordnet ist und wie viel "Rest offen" bleibt.
- **Verwaltung** (`/admin/`): Getraenke, Belege (inkl. Positionen), Freigetraenke,
  PayPal-Zahlungen und Differenz-Zuordnungen pflegen.

## Getraenke im Admin anlegen

1. Unter `/admin/` anmelden (Superuser-Zugangsdaten).
2. Im Bereich **Kasse** auf **Getränke** klicken, dann **Getränk hinzufügen**.
3. Felder ausfuellen:
   - **Name**: z.B. "Bier 0,33l" — muss eindeutig sein.
   - **Warenpreis**: Einkaufspreis pro Flasche/Dose (nur informativ, fliesst
     nicht in die Soll/Ist-Berechnung ein).
   - **Pfand**: Pfandbetrag pro Einheit (aktuell informativ, nicht Teil der
     Rechenlogik).
   - **Verkaufspreis**: Preis, zu dem in der Vertrauenskasse verkauft wird —
     zentral fuer die Soll-Kasse-Berechnung.
   - **Aktiv**: Haken setzen. Nur aktive Getraenke tauchen im Formular "Neue
     Zaehlung erfassen" auf. Ein Getraenk aus dem Sortiment nehmen, ohne die
     Historie zu verlieren: Haken einfach wieder entfernen statt zu loeschen.
4. **Speichern**. Das Getraenk erscheint danach in der Zaehlungs-Erfassung.

Zum Loeschen eines Getraenks: nicht empfohlen, wenn bereits Zaehlungen, Belege
oder Freigetraenke dafuer existieren (diese Datensaetze bleiben durch die
Datenbank-Constraints erhalten und blockieren das Loeschen). Stattdessen auf
"Aktiv" = Nein setzen.

## Deployment

Fuer den Produktivbetrieb per Docker Compose (Django + Gunicorn + Caddy als
Reverse Proxy mit optionalem automatischem HTTPS) siehe [DEPLOYMENT.md](DEPLOYMENT.md).

## Konfiguration (Produktivbetrieb)

Ueber Umgebungsvariablen (siehe `config/settings.py` und `.env.example`):

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG` (`True`/`False`)
- `DJANGO_ALLOWED_HOSTS` (kommagetrennt)
- `DJANGO_CSRF_TRUSTED_ORIGINS` (kommagetrennt, nur bei HTTPS-Domain noetig)
- `DJANGO_DB_PATH` (Pfad zur SQLite-Datei, Default: `db.sqlite3` im Projektverzeichnis)
- `SITE_ADDRESS` (nur Docker/Caddy: Domain fuer automatisches HTTPS oder `:80` fuer reines HTTP)
