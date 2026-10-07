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

**Wichtig**: Das ist nur der lokale Testlauf auf einem einzelnen Rechner —
für den echten Betrieb mit zwei Nutzern braucht es eine zentrale, durchgehend
laufende Instanz, die Handy und PC gleichermassen erreichen (sonst entstehen
getrennte Datenstände und doppelte VK-Belegnummern). Siehe Abschnitt
"Zentrale Instanz statt lokalem Testlauf" in [DEPLOYMENT.md](DEPLOYMENT.md).

## Datenmodell

App `kasse`, siehe `kasse/models.py`, plus einige kleine Zusatztabellen/-felder,
die für die geforderte Rechen-/Zuordnungslogik technisch nötig sind (siehe
"Abweichungen" unten):

| Tabelle | Zweck |
|---|---|
| `Getraenk` | Artikel: Name, Warenpreis (ohne Pfand), Verkaufspreis, aktiv |
| `Zaehlung` | Ein Zählungszeitpunkt (Datum, Notiz, Bargeld gezählt, Belegnummer `VK-JJJJ-MM-NN`) |
| `ZaehlungVerbrauch` | Direkt eingetragen: wie viel von einem Artikel seit der letzten Zählung verbraucht/verkauft wurde (kein Bestand wird gezählt oder verglichen) |
| `Beleg` | Einkaufsbeleg (Datum, Dateipfad, Gesamtbetrag, Händler) — gilt immer automatisch als private Einlage von Nick; rein dokumentarisch, fließt in keine Kassenberechnung ein |
| `BelegPosition` | Positionen eines Belegs je Getränk (Einkaufsmenge), Einzelpreis = `Getraenk.warenpreis` zum Zeitpunkt des Einkaufs |
| `Freigetraenk` | Freigetränke je Getränk, auch rückwirkend nachtragbar (bis zum CSV-Export des Monats) |
| `Kassenbewegung` | Bargeldbewegung ohne Bezug zum Getränkeverkauf: Einlage, Entnahme oder fremder Bargeldeingang |
| `PaypalZahlung` | PayPal-Zahlungen mit automatischer Zuordnung zur Vertrauenskasse |

**Bewusst kein Lager-/Kühlschrank-Bestand getrennt**: es gibt keine
Unterscheidung nach Lagerort. Für die Kassenformel zählt bei jeder Zählung
nur, wie viel seit der letzten Zählung verbraucht/verkauft wurde
(`ZaehlungVerbrauch`) — das ist bei der überschaubaren Menge an Artikeln
einfacher als ein Bestandsabgleich je Lagerort.

Zusätzlich gibt es einen **einzigen, errechneten Gesamtbestand** je Getränk
(Seite "Bestand", `/bestand/`): eingekaufte Menge (`BelegPosition`, z.B. "10x
Wasser") minus verbrauchte Menge (`ZaehlungVerbrauch`), über die komplette
Historie summiert — keine zusätzliche Dateneingabe nötig, da beide Mengen
ohnehin schon beim Beleg-Erfassen bzw. bei der Zählung eingetragen werden.
Rein informativ (z.B. um zu sehen, ob bald nachgekauft werden muss), fließt
in keine Kassenberechnung ein.

Der Einkauf selbst (`Beleg`/`BelegPosition`) ist immer eine private Einlage
von Nick (es gibt bewusst kein "Bezahlt von"-Feld, da der Einkauf nie aus der
Vertrauenskasse selbst bezahlt wird) und fließt deshalb in **keine**
Kassenberechnung ein — weder in Soll-Kasse noch in die Kassendifferenz noch
in den Bargeld-Vorschlag (siehe "Rechenlogik" unten).

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
  möglich" technisch durchzusetzen (gilt für `Zaehlung` selbst inkl.
  `bargeld_gezaehlt`, `ZaehlungVerbrauch`, `Freigetraenk`, `Kassenbewegung`
  und `Beleg`).

## Rechenlogik

Komplett in `kasse/services.py`. Zentral ist `berechne_auswertung(zaehlung)`:
sie nimmt **eine einzige** Zählung und berechnet automatisch das Ergebnis für
den Zeitraum seit der zeitlich vorangehenden Zählung (`vorherige_zaehlung()`)
— es muss also nichts "zwischen zwei Zählungen" ausgewählt werden, jede
Zählung hat sofort ihr eigenes Ergebnis, auch die allererste:

- `Verkauft(i) = Verbraucht_eingetragen(i) − Freigetränke(i)` (direkt
  eingetragener Wert, kein Bestandsvergleich)
- `Soll-Kasse = Σ Verkauft(i) × Verkaufspreis(i)` (Verkaufspreis ohne Pfand-Anteil)
- `Bargeld-Differenz = bargeld_gezählt(jetzt) − bargeld_gezählt(letzte Zählung)`
  (0 statt letzterem, wenn dies die allererste Zählung ist)
- `Bar-Anteil (Getränke) = Bargeld-Differenz + Entnahmen − Einlagen − fremde Bargeldeingänge`
  (die drei `Kassenbewegung`-Arten seit der letzten Zählung, siehe unten —
  ohne diese Bereinigung würde z.B. eine Entnahme wie ein Fehlbetrag aussehen,
  eine private Einlage oder ein fremder Bargeldeingang hingegen wie
  zusätzlicher Getränkeumsatz)
- `PayPal-Anteil = Σ PayPal-Zahlungen mit ist_Getränke_Zahlung=True, die dieser Zählung zugeordnet sind`
- `Ist-Kasse = Bar-Anteil + PayPal-Anteil`
- `Kassendifferenz = Ist-Kasse − Soll-Kasse` (keine Rundungstoleranz, exakt ausgewiesen)
- Anzeige in der Auswertung: zuerst Soll-Kasse, dann die Zusammensetzung des
  Bar-Anteils (Bargeld-Differenz, Entnahmen, Einlagen, fremde Bargeldeingänge)
  und der PayPal-Anteil, erst danach die Kassendifferenz — damit online
  bezahlte Getränke oder eine Bargeld-Entnahme nie wie ein Fehlbetrag aussehen.
- Solange im Zeitraum noch ungeklärte PayPal-Zahlungen liegen (Klärungsliste),
  markiert die Auswertung das Ergebnis als **vorläufig**: die Bar-Differenz
  kann dann normal negativ sein, das ist kein Alarmsignal.
- Einkaufsbelege (`Beleg`/`BelegPosition`) gehen **nicht** in Soll-Kasse,
  Kassendifferenz oder den Bargeld-Vorschlag ein — rein dokumentarisch
  (Wareneinsatz, immer private Einlage von Nick, siehe oben).
- Für Zeiträume über mehrere Zählungen (Monatsauswertung, CSV-Export) summiert
  `berechne_zeitraum(zaehlungen)` einfach die Einzelergebnisse jeder Zählung.

### Bargeld-Vorschlag (Schritt 2 der Zählung)

Beim Erfassen einer Zählung wird zunächst nur der Verbrauch eingetragen
(Schritt 1). Erst danach (Schritt 2, "Bargeld bestätigen") zeigt die Kasse
einen vorausgefüllten Vorschlag, wie viel jetzt im Kasten liegen müsste — der
Nutzer bestätigt ihn oder korrigiert ihn auf das tatsächlich gezählte
Bargeld:

- `Bargeld-Vorschlag = Bargeld(letzte Zählung) + Soll-Kasse + Einlagen − Entnahmen + fremde Bargeldeingänge − PayPal-Anteil`

Einlagen/fremde Bargeldeingänge erhöhen den Vorschlag (physisch mehr Geld in
der Kasse), Entnahmen und der PayPal-Anteil senken ihn (Geld raus bzw. nie
physisch in die Kasse gelangt). Einkaufsbelege fließen **nicht** in diesen
Vorschlag ein (siehe oben) — ein Einkauf verändert nie, wie viel Bargeld in
der Kasse erwartet wird.

### Einkäufe und Freigetränke-Wert (informativ)

Zusätzlich zeigt die Auswertung zwei rein informative Werte, die in keine der
obigen Berechnungen einfließen:

- `Einkaufswert = Σ Beleg.gesamtbetrag` aller im Zeitraum erfassten Belege
  (Seite "Einkäufe", `/beleg/neu/`) — inklusive der Angabe, was gekauft wurde.
- `Freigetränke-Wert = Σ Freigetränke(i) × Verkaufspreis(i)` — zeigt, wie viel
  Umsatz durch ausgegebene Freigetränke verschenkt wurde.

Es gibt bewusst **keine** Leergut-/Pfand-Differenzrechnung: Einkauf und
Pfand-Rückgabe sind private Angelegenheiten von Nick und fließen nie durch
die Vertrauenskasse.

### Kassenbewegungen (Einlage / Entnahme / fremder Bargeldeingang)

Alle Bargeldbewegungen ohne Bezug zum Getränkeverkauf werden als
`Kassenbewegung` erfasst (Seite "Kassenbewegung", `/kassenbewegung/neu/` —
zugleich die "Vertrauenskassenliste", ein chronologisches Journal aller
Bewegungen):

- **Einlage**: z.B. der Kassenanfangssaldo/Wechselgeld. Kein Erlös.
- **Entnahme**: Geld, das aus der Kasse genommen wird (z.B. Einnahmen
  abgeholt). Ohne diese Buchung würde es wie ein Fehlbetrag aussehen.
- **Fremder Bargeldeingang**: z.B. jemand zahlt eine Platzstunde bar. Verweis
  auf die RG-Nummer aus dem (separaten) Rechnungsprogramm als Freitext — keine
  Texterkennung in dieser Version. Die Vertrauenskasse erstellt selbst keine
  Rechnungen und vergibt ausschließlich ihre eigenen VK-Nummern.

Kassenbewegungen sind keine Erlöse und erscheinen daher **nicht** im
CSV-Monatsexport, wohl aber im Zählprotokoll (Auswertung je Zählung) und in
der Vertrauenskassenliste. Rückwirkende Korrekturen sind wie bei Freigetränken
nur bis zum CSV-Export des betroffenen Monats möglich.

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

- **Neue Zählung** (`/zaehlung/neu/`), in zwei Schritten:
  1. Kachel-Oberfläche wie an einem Kassensystem — eine Kachel pro aktivem
     Artikel, direkt eingetragen wird, wie viel seit der letzten Zählung
     verbraucht/verkauft wurde. Keine Textfelder, kein Bestand zählen.
     Antippen zählt hoch, Minus-Symbol oder langes Drücken wieder runter,
     Zählstand live sichtbar. Beim Speichern wird daraus direkt der
     Soll-Betrag berechnet.
  2. **Bargeld bestätigen** (`/zaehlung/<id>/bargeld/`): zeigt den Bargeld-
     Vorschlag (vorheriges Bargeld + Soll-Umsatz, siehe "Rechenlogik")
     vorausgefüllt in einem großen Zahlenfeld, inklusive Aufschlüsselung der
     einzelnen Bestandteile — das tatsächlich gezählte Bargeld in der Kasse
     wird damit entweder einfach bestätigt (wenn es stimmt) oder auf den
     abweichenden Wert korrigiert. Kein zweites, unabhängiges Eintippen eines
     Betrags mehr nötig.

  Wird Schritt 2 übersprungen (z.B. Browser geschlossen), bleibt das Bargeld
  der Zählung leer. Auf der Startseite erscheint dafür ein Hinweis "Bargeld
  noch erfassen", und die Auswertung warnt deutlich, dass die Kassendifferenz
  für diese Zählung noch nicht aussagekräftig ist (geht bis dahin von 0 €
  gezähltem Bargeld aus).
- **Freigetränke** (`/freigetraenk/neu/`): gleiche Kachel-Bedienung, Datum
  frei wählbar (auch rückwirkend, solange der Monat nicht exportiert ist).
- **Kassenbewegung** (`/kassenbewegung/neu/`): Einlage/Entnahme/fremder
  Bargeldeingang über ein großes Zahlenfeld erfassen, darunter die
  Vertrauenskassenliste (chronologisches Journal).
- **Einkäufe** (`/beleg/neu/`): Einkaufsbelege direkt im Haupt-UI erfassen —
  Datum, Händler, Gesamtbetrag, optional Beleg-Scan, plus Kachel-Oberfläche
  darunter für "was wurde gekauft" (z.B. "10x Wasser"). Legt automatisch
  `BelegPosition`-Einträge an (Einzelpreis = `Getraenk.warenpreis`). Zeigt den
  Einkaufswert des laufenden Monats sowie eine Liste der zuletzt erfassten
  Belege inkl. Inhalt.
- **Bestand** (`/bestand/`): errechneter Gesamtbestand je Getränk (eingekauft
  minus verbraucht, komplette Historie) — keine eigene Dateneingabe, rein
  informativ.
- **Auswertung** (`/auswertung/`): eine Zählung auswählen (Standard: die
  letzte), zeigt sofort ihr Ergebnis — Soll-Kasse, Zusammensetzung des
  Bar-Anteils, PayPal-Anteil, Kassendifferenz sowie (rein informativ) den
  Einkaufswert der erfassten Belege und den Wert ausgegebener Freigetränke.
  Kein Start/Ende-Picker nötig, jede Zählung steht für sich.
- **Monatsauswertung** (`/auswertung/monat/`): alle Zählungen eines Monats
  plus Gesamtergebnis (Summe aller Einzelergebnisse des Monats).
- **PayPal-Abgleich** (`/paypal/`): neue Zahlungen erfassen (automatische
  Zuordnung läuft sofort) und die Klärungsliste einmal monatlich abarbeiten.
- **CSV-Export** (`/export/`): Monat auswählen, CSV herunterladen.
- **Verwaltung** (`/admin/`): Getränke, einzelne Belegpositionen je Artikel,
  Freigetränke, Kassenbewegungen, PayPal-Zahlungen und Stichwörter pflegen.

Beleg-OCR (automatisches Auslesen des Gesamtbetrags aus dem Scan) ist
**nicht** Teil dieser Version — der Betrag wird manuell eingetragen, der
Scan selbst kann optional hochgeladen werden.

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
