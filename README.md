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

## Konfiguration (Produktivbetrieb)

Ueber Umgebungsvariablen (siehe `config/settings.py`):

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG` (`True`/`False`)
- `DJANGO_ALLOWED_HOSTS` (kommagetrennt)
