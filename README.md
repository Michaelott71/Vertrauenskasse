# Vertrauenskasse

Modul zur Verwaltung der Getraenke-Vertrauenskasse im Vereinsheim: Bestandszaehlungen,
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

**Abweichung vom vorgegebenen Schema:** `Zaehlung` hat zusaetzlich das Feld
`bargeld_gezaehlt`. Ohne dieses Feld liesse sich die geforderte Formel
`Ist-Kasse = gezaehltes Bargeld + manuell markierte PayPal-Zahlungen` nicht
berechnen, da im urspruenglichen Modell kein Feld fuer das gezaehlte Bargeld
vorgesehen war.

## Rechenlogik

Die komplette Berechnung steckt in `kasse/services.py`
(`berechne_auswertung(start, ende)`), fuer jedes Getraenk zwischen zwei
Zaehlungen `start` und `ende`:

- `Verkauft = Vollbestand_Start + Nachschub − Vollbestand_Ende − Freigetraenke`
  (Nachschub = Summe `BelegPosition.anzahl` aus Belegen mit Datum im Zeitraum
  `(start.datum, ende.datum]`; Freigetraenke analog)
- `Soll-Kasse = Σ Verkauft(i) × Verkaufspreis(i)`
- `Ist-Kasse = bargeld_gezaehlt(ende) + Σ PayPal-Zahlungen mit ist_Getraenke_Zahlung=True, zaehlung=ende`
- `Kassendifferenz = Ist-Kasse − Soll-Kasse` (keine Rundungstoleranz)
- `Erwartetes Leergut(i) = Leergut_Start(i) + Verkauft(i) − Rueckgabe_an_Getraenkemarkt(i)`
- `Leergut-Differenz(i) = Leergut_Ende(i) − Erwartetes Leergut(i)`
  (negativ = Schwund/Pfandverlust, positiv = Fund/Fremdleergut)

Getestet in `kasse/tests.py` (`python manage.py test`).

## Workflows

- **Neue Zaehlung** (`/zaehlung/neu/`): Datum, Notiz, gezaehltes Bargeld sowie
  Voll-/Leergut-Bestand je aktivem Getraenk in einem mobilfreundlichen Formular
  erfassen.
- **Auswertung** (`/auswertung/`): Start- und End-Zaehlung auswaehlen, Soll/Ist-Kasse,
  Kassendifferenz und Leergut-Differenz je Getraenk sowie in Summe ansehen.
- **Verwaltung** (`/admin/`): Getraenke, Belege (inkl. Positionen), Freigetraenke
  und PayPal-Zahlungen pflegen.

## Getraenke im Admin anlegen

1. Unter `/admin/` anmelden (Superuser-Zugangsdaten).
2. Im Bereich **Kasse** auf **Getraenks** klicken, dann **Getraenk hinzufuegen**.
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
