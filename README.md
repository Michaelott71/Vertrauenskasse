# Vertrauenskasse

Modul zur Verwaltung der Getränke-/Snack-Vertrauenskasse: Bestandszählungen im
Kassensystem-Stil, Belege, Freigetränke und PayPal-Zahlungen erfassen und
automatisch Soll/Ist-Kasse berechnen.

Pfand ist bewusst **kein** Teil der Geschäftslogik: Der Einkauf wird immer
privat bezahlt (nie aus der Firmenkasse), und die Pfand-Erstattung beim
Getränkemarkt nimmt Nick ebenfalls privat entgegen — beides läuft komplett
außerhalb der Vertrauenskasse, die selbst nie Pfand auszahlt.

## Tech-Stack

- **Django 5** (Python) mit **SQLite** als Datenbank — ein einzelner, kleiner
  Prozess ohne separaten Frontend-Build, läuft problemlos auf einem NAS/Raspberry Pi.
- Django Admin für die Verwaltung von Getränken, Belegen, Freigetränken,
  PayPal-Zahlungen und Stichwörtern.
- Eigene, mobile-optimierte Views/Templates für die Kernworkflows: Zählung
  erfassen, Auswertung ansehen, PayPal-Abgleich, CSV-Export.
- Die Zählung selbst ist **kein Formular**, sondern eine Kachel-Oberfläche
  (reines Vanilla-JS, kein Framework, kein Build-Tooling): antippen = +1,
  Minus-Symbol oder langes Drücken = -1, Zählstand live sichtbar.
- Kein Build-Tooling, keine externen JS/CSS-CDN-Abhängigkeiten (funktioniert offline).
- Zwei gleichberechtigte Nutzer teilen sich einen Login (kein Rechtesystem nötig).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Anschliessend im Browser unter `http://127.0.0.1:8000/` anmelden. Getränke
zuerst im Admin-Bereich (`/admin/`) anlegen.

## Datenmodell

App `kasse`, siehe `kasse/models.py`, plus einige kleine Zusatztabellen/-felder,
die für die geforderte Rechen-/Zuordnungslogik technisch nötig sind (siehe
"Abweichungen" unten):

| Tabelle | Zweck |
|---|---|
| `Getraenk` | Artikel: Name, Warenpreis (ohne Pfand), Verkaufspreis, aktiv |
| `Zaehlung` | Ein Zählungszeitpunkt (Datum, Notiz, Belegnummer `VK-JJJJ-MM-NN`) |
| `ZaehlungBestand` | Gezählter Vollbestand je Artikel zu einer Zählung |
| `Beleg` | Einkaufsbeleg (Datum, Dateipfad, Gesamtbetrag, Händler) — private Einlage, kein Geldabfluss aus der Kasse |
| `BelegPosition` | Positionen eines Belegs je Getränk (Nachschub), Einzelpreis nur der Warenpreis ohne Pfand-Anteil |
| `Freigetraenk` | Freigetränke je Getränk, auch rückwirkend nachtragbar (bis zum CSV-Export des Monats) |
| `PaypalZahlung` | PayPal-Zahlungen mit automatischer Zuordnung zur Vertrauenskasse |

Pfand ist absichtlich **nicht** Teil des Datenmodells: Einkauf und
Pfand-Rückerstattung laufen immer privat und komplett außerhalb der Kasse,
es gibt keinen Rückgabemechanismus an Kunden.

**Abweichungen vom ursprünglich vorgegebenen Schema** (technisch notwendig,
keine neuen fachlichen Konzepte):

- `Zaehlung.bargeld_gezaehlt`: Ohne dieses Feld liesse sich die geforderte
  Formel `Ist-Kasse = gezähltes Bargeld + PayPal-Zahlungen` nicht berechnen.
- `PaypalZahlung.verwendungszweck`: Rohtext-Eingabe für die automatische
  Zuordnung (fester Verwendungszweck, RG-Nummer, Stichwortliste). Ohne dieses
  Feld gäbe es nichts, worauf die Zuordnungsregeln prüfen könnten.
- `PaypalStichwort` (neue Tabelle): speichert die geforderte "erweiterbare
  Stichwortliste" inkl. automatisch gelernter, wiederkehrender Betreffs.
- `MonatsExport` (neue Tabelle): merkt sich, welche Monate bereits als CSV
  exportiert wurden, um die Regel "Korrekturen nur bis zum Export rückwirkend
  möglich" technisch durchzusetzen.

## Rechenlogik

Komplett in `kasse/services.py` (`berechne_auswertung(start, ende)`), für
jeden Artikel zwischen zwei Zählungen — auch wenn dazwischen weitere
Zählungen liegen (z.B. bei der Monatsauswertung):

- `Verkauft(i) = Vollbestand_Start(i) + Nachschub(i) − Vollbestand_Ende(i) − Freigetränke(i)`
- `Soll-Kasse = Σ Verkauft(i) × Verkaufspreis(i)` (Verkaufspreis ohne Pfand-Anteil)
- `Bar-Anteil = bargeld_gezählt(Ende) − bargeld_gezählt(Start)`
- `PayPal-Anteil = Σ PayPal-Zahlungen mit ist_Getränke_Zahlung=True im Zeitraum`
- `Ist-Kasse = Bar-Anteil + PayPal-Anteil`
- `Kassendifferenz = Ist-Kasse − Soll-Kasse` (keine Rundungstoleranz, exakt ausgewiesen)
- Anzeige in der Auswertung: zuerst Soll-Kasse, dann Bar-Anteil und
  PayPal-Anteil der Ist-Kasse, erst danach die Kassendifferenz — damit online
  bezahlte Getränke nie wie ein Fehlbetrag aussehen.
- Solange im Zeitraum noch ungeklärte PayPal-Zahlungen liegen (Klärungsliste),
  markiert die Auswertung das Ergebnis als **vorläufig**: die Bar-Differenz
  kann dann normal negativ sein, das ist kein Alarmsignal.

Es gibt bewusst **keine** Leergut-/Pfand-Differenzrechnung: Einkauf und
Pfand-Rückgabe sind private Angelegenheiten von Nick und fließen nie durch
die Vertrauenskasse.

Getestet in `kasse/tests.py` (`python manage.py test`).

## PayPal-Zuordnung

Automatisiert in `kasse/matching.py`, in dieser Reihenfolge:

1. Fester Verwendungszweck "Getränke Golfbox" → Vertrauenskasse
2. RG-Nummer im Betreff → keine Vertrauenskasse (Ausgangsrechnung)
3. Stichwortliste (`PaypalStichwort`, erweiterbar über den Admin-Bereich oder
   automatisch beim manuellen Entscheiden) → Vertrauenskasse
4. Betragsregel: Betrag passt zu einem Getränke-/Snackpreis oder einem
   Vielfachen davon → "vermutlich", bleibt aber auf der Klärungsliste
5. Alles andere → Klärungsliste, einmal monatlich manuell entscheiden (Seite
   "PayPal-Abgleich")

Wird eine Zahlung dort manuell als Vertrauenskasse bestätigt, wird sie
anhand ihres Datums der passenden Zählung zugeordnet und ihr Betreff als
neues Stichwort gemerkt — taucht der gleiche Betreff später erneut auf, wird
er automatisch erkannt.

## Monatsexport (CSV)

`kasse/export.py`, Seite "CSV-Export": erzeugt `JJJJ-MM_Vertrauenskasse.csv`
(Semikolon-getrennt, UTF-8, deutsches Zahlenformat mit Komma). Eine Zeile pro
Zählungszeitraum fasst alle Artikel zu einem Sammelposten zusammen (erlaubte
Vereinfachung laut Vorgabe, da ohnehin einheitlich 19% USt anfallen und sich
Bar-Zahlungen nicht auf einzelne Artikel aufteilen lassen); jede PayPal-Zahlung
bekommt eine eigene Zeile mit ihrer Transaktions-ID als Referenz. Optional als
eine einzige aggregierte Bar-Zeile für den ganzen Monat exportierbar.

Der Export markiert den Monat als exportiert (`MonatsExport`) — danach sind
Korrekturen für diesen Monat nicht mehr rückwirkend möglich (Freigetränke,
Bestandskorrekturen), sondern werden als Vermerk im Folgemonat erfasst.

## Workflows

- **Neue Zählung** (`/zaehlung/neu/`): Kachel-Oberfläche wie an einem
  Kassensystem — eine Kachel pro aktivem Artikel (Vollbestand), keine
  Textfelder. Antippen zählt hoch, Minus-Symbol oder langes Drücken wieder
  runter, Zählstand live sichtbar.
- **Auswertung** (`/auswertung/`): Start- und End-Zählung wählen, Soll-Kasse,
  Bar-/PayPal-Anteil und Kassendifferenz.
- **Monatsauswertung** (`/auswertung/monat/`): alle Zählungen eines Monats
  plus Gesamtergebnis (erste vs. letzte Zählung im Monat).
- **PayPal-Abgleich** (`/paypal/`): neue Zahlungen erfassen (automatische
  Zuordnung läuft sofort) und die Klärungsliste einmal monatlich abarbeiten.
- **CSV-Export** (`/export/`): Monat auswählen, CSV herunterladen.
- **Verwaltung** (`/admin/`): Getränke, Belege (inkl. Positionen),
  Freigetränke, PayPal-Zahlungen und Stichwörter pflegen.

Belege-Upload/OCR ist **nicht** Teil dieser ersten Version (das `Beleg`-Modell
inkl. Dateiupload existiert bereits für eine spätere Erweiterung).

## Deployment

Für den Produktivbetrieb per Docker Compose (Django + Gunicorn + Caddy als
Reverse Proxy mit optionalem automatischem HTTPS) siehe [DEPLOYMENT.md](DEPLOYMENT.md).

## Konfiguration (Produktivbetrieb)

Über Umgebungsvariablen (siehe `config/settings.py` und `.env.example`):

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG` (`True`/`False`)
- `DJANGO_ALLOWED_HOSTS` (kommagetrennt)
- `DJANGO_CSRF_TRUSTED_ORIGINS` (kommagetrennt, nur bei HTTPS-Domain nötig)
- `DJANGO_DB_PATH` (Pfad zur SQLite-Datei, Default: `db.sqlite3` im Projektverzeichnis)
- `SITE_ADDRESS` (nur Docker/Caddy: Domain für automatisches HTTPS oder `:80` für reines HTTP)
