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
- `erstellt_am` auf `Zaehlung`, `Kassenbewegung`, `Freigetraenk` und `Beleg`:
  wird automatisch beim Speichern gesetzt, nicht vom Nutzer. Nötig, damit sich
  Ereignisse am **selben Kalendertag** wie eine Zählung noch eindeutig
  zeitlich einordnen lassen (siehe "Rechenlogik" → Zeitraum-Zuordnung).

## Rechenlogik

Komplett in `kasse/services.py`. Zentral ist `berechne_auswertung(zaehlung)`:
sie nimmt **eine einzige** Zählung und berechnet automatisch das Ergebnis für
den Zeitraum seit der zeitlich vorangehenden Zählung (`vorherige_zaehlung()`)
— es muss also nichts "zwischen zwei Zählungen" ausgewählt werden, jede
Zählung hat sofort ihr eigenes Ergebnis, auch die allererste:

- `Verkauft(i) = Verbraucht_eingetragen(i) − Freigetränke(i)` (direkt
  eingetragener Wert, kein Bestandsvergleich)
- `Soll-Kasse = Σ Verkauft(i) × Verkaufspreis(i)` (Verkaufspreis ohne Pfand-Anteil,
  reiner Umsatz dieses Zeitraums, keine absolute Bestandsgröße)
- `Bargeld-Differenz = bargeld_gezählt(jetzt) − bargeld_gezählt(letzte Zählung)`
  (0 statt letzterem, wenn dies die allererste Zählung ist)
- `Netto aus Kassenbewegungen = Einlagen + fremde Bargeldeingänge − Entnahmen`
  (die drei `Kassenbewegung`-Arten seit der letzten Zählung, siehe unten, mit
  ihrem natürlichen Vorzeichen: Geld, das reinkam, plus; Geld, das
  rausgenommen wurde, minus)
- `Kassendifferenz = Bar-Anteil (aus Getränkeverkauf) − Soll-Kasse`, wobei
  `Bar-Anteil = Bargeld-Differenz − Netto aus Kassenbewegungen` (ohne diese
  Bereinigung würde z.B. eine Entnahme wie ein Fehlbetrag aussehen, eine
  private Einlage oder ein fremder Bargeldeingang hingegen wie zusätzlicher
  Getränkeumsatz) — keine Rundungstoleranz, exakt ausgewiesen.

**PayPal hat bewusst nichts mit dem Kassenbestand zu tun**: eine
PayPal-Zahlung landet nie physisch in der Kasse, deshalb fließt der
`PayPal-Anteil` (Σ PayPal-Zahlungen mit `ist_Getränke_Zahlung=True`, die
dieser Zählung zugeordnet sind) in **keine** der obigen Berechnungen ein.
Wurde ein Getränk per PayPal bezahlt, zeigt sich das also ganz bewusst als
Kassendifferenz — die Auswertung weist den PayPal-Anteil daneben nur als
Information aus ("davon vermutlich X € per PayPal bezahlt … ggf. noch
Quittung ausstellen"), ohne ihn zu verrechnen.

**Anzeige in der Auswertung — zwei absolute Beträge statt Umsatz-Deltas**:
Die Begriffe "Soll-Kasse" und "Bar-Anteil" sind reine **Zeitraum-Umsätze**
(Deltas), keine Kontostände — eine Starteinlage von 35 € würde dort z.B. nie
auftauchen, obwohl sie tatsächlich physisch in der Kasse liegt. Deshalb
zeigt die Auswertung oben stattdessen zwei **absolute Kassenbestände**:

- `Soll-Kassenbestand = Bargeld(letzte Zählung) + Soll-Kasse + Netto aus Kassenbewegungen`
  — der gleiche Wert, der schon beim "Bargeld bestätigen" als Vorschlag
  diente (siehe unten), also was jetzt im Kasten liegen müsste (ohne PayPal).
- `Ist-Kassenbestand = bargeld_gezählt` — genau der tatsächlich gezählte,
  absolute Betrag (zeigt z.B. die 35 € Starteinlage korrekt an).
- `Kassendifferenz = Ist-Kassenbestand − Soll-Kassenbestand` − `Zaehlung.differenz_korrektur`
  — rechnerisch identisch zur obigen Definition über Bar-Anteil/Soll-Kasse
  (nur aus den beiden absoluten Beständen hergeleitet statt aus den
  Zeitraum-Deltas), zusätzlich bereinigt um eine erklärte Differenz, siehe
  "Kassendifferenz erklären (Auflösung)" unten.

Darunter eine Karte **"Kassenbestand-Verlauf"**: alter Bargeldbestand (der
vorherigen Zählung) → Kassenbewegungen in diesem Zeitraum (Tabelle) → neuer
Bargeldbestand (gezählt) — ein einfacher, nachvollziehbarer Kontoauszug ohne
Soll/Ist-Mathematik.

#### Kassendifferenz erklären (Auflösung)

Ist die Kassendifferenz ungleich 0, zeigt die Auswertung direkt ein Feld
**"Kassendifferenz erklären"** an: Notiz (z.B. "Trinkgeld", "Per PayPal
bezahlt") plus einen **erklärten Betrag** (`Zaehlung.differenz_korrektur`),
vorausgefüllt mit der kompletten aktuellen Differenz, sodass ein Klick auf
"Trinkgeld" oder "Per PayPal bezahlt" sie automatisch auf den vollen Betrag
setzt. Nach dem Speichern:

- `Kassendifferenz_unerklärt` (die ursprüngliche, "rohe" Differenz vor jeder
  Erklärung) bleibt als Audit-Spur erhalten und wird zusammen mit der Notiz
  angezeigt ("✓ Erledigt: von ursprünglich X € Differenz sind Y € erklärt
  (Notiz)").
- Die angezeigte **Kassendifferenz sinkt um genau den erklärten Betrag** — bei
  vollständiger Erklärung auf 0,00 €, sie gilt dann als abgehakt und das
  Erklär-Formular verschwindet. Eine Teilerklärung lässt den Rest weiterhin
  als offene Differenz stehen.
- Der erklärte Betrag fließt dafür direkt (nur für diese eine Zählung) in den
  Soll-Kassenbestand/Bargeld-Vorschlag ein, nicht in Bar-Anteil oder
  Soll-Kasse selbst — die zugrunde liegenden Zahlen (Verbrauch, gezähltes
  Bargeld, Kassenbewegungen) bleiben unverändert, nur die Differenz-Anzeige
  wird um den erklärten, dokumentierten Anteil bereinigt.
- Die Erklärung erscheint danach in der Monatsauswertung (ebenfalls
  aufgelöst/als "Erledigt" markiert, summiert über alle Zählungen) und im
  CSV-Export (`Zaehlung.notiz` in der `Notiz`-Spalte), damit für den
  Steuerberater nachvollziehbar ist, warum eine Differenz entstanden und wie
  sie erklärt worden ist.
- Diese Korrektur ist bewusst direkt an die jeweilige Zählung gebunden (nicht
  über Datum/`erstellt_am` gesucht wie Kassenbewegungen/Freigetränke/Belege,
  siehe "Zeitraum-Zuordnung bei gleichem Kalendertag") — so lässt sich auch
  eine bereits bestätigte Zählung gezielt und ohne Seiteneffekte auf andere
  Zeiträume auflösen.
- Einkaufsbelege (`Beleg`/`BelegPosition`) gehen **nicht** in Soll-Kasse,
  Kassendifferenz oder den Bargeld-Vorschlag ein — rein dokumentarisch
  (Wareneinsatz, immer private Einlage von Nick, siehe oben).
- Für Zeiträume über mehrere Zählungen (Monatsauswertung, CSV-Export) summiert
  `berechne_zeitraum(zaehlungen)` einfach die Einzelergebnisse jeder Zählung.

### Zeitraum-Zuordnung bei gleichem Kalendertag

`Kassenbewegung`, `Freigetraenk` und `Beleg` werden anhand ihres Datums einer
Zählungsperiode zugeordnet (alles zwischen der vorherigen und der aktuellen
Zählung). Fallen mehrere Ereignisse auf **denselben Kalendertag** wie eine
Zählung, reicht das Datum allein nicht aus, um zu entscheiden, ob ein
Ereignis noch "davor" oder schon "danach" passiert ist. Deshalb trägt jede
dieser Tabellen zusätzlich `erstellt_am` (automatisch beim Speichern
gesetzt) — bei gleichem Datum entscheidet die tatsächliche Erfassungs-
reihenfolge. Ohne das würde z.B. eine Kassenbewegung, die erst **nach**
einer bereits bestätigten Zählung gebucht wird, deren längst abgeschlossenes
Ergebnis rückwirkend verändern, obwohl sie zum Zeitpunkt der Zählung noch
gar nicht existierte.

### Bargeld-Vorschlag (Schritt 2 der Zählung)

Beim Erfassen einer Zählung wird zunächst nur der Verbrauch eingetragen
(Schritt 1). Erst danach (Schritt 2, "Bargeld bestätigen") zeigt die Kasse
einen vorausgefüllten Vorschlag, wie viel jetzt im Kasten liegen müsste — der
Nutzer bestätigt ihn oder korrigiert ihn auf das tatsächlich gezählte
Bargeld:

- `Bargeld-Vorschlag = Bargeld(letzte Zählung) + Soll-Kasse + Einlagen − Entnahmen + fremde Bargeldeingänge`

Einlagen/fremde Bargeldeingänge erhöhen den Vorschlag (physisch mehr Geld in
der Kasse), Entnahmen senken ihn (Geld raus). PayPal fließt **nicht** ein
(siehe oben) — wurde etwas per PayPal bezahlt, zeigt sich das stattdessen als
Differenz zum Vorschlag. Einkaufsbelege fließen ebenfalls **nicht** in diesen
Vorschlag ein (siehe oben) — ein Einkauf verändert nie, wie viel Bargeld in
der Kasse erwartet wird.

Weicht der bestätigte Betrag vom Vorschlag ab, führt die Kasse direkt zu
einer dritten Seite **"Differenz klären"** (`/zaehlung/<id>/differenz/`):
zeigt die Kassendifferenz (plus einen Hinweis, falls für den Zeitraum schon
PayPal-Zahlungen zugeordnet sind) und bietet drei Wege an, sie zu klären —
direkt zu "Freigetränke erfassen" springen (Datum der Zählung ist
vorausgefüllt), falls etwas verschenkt wurde; "Trinkgeld" oder "Per PayPal
bezahlt" anklicken (füllt Notiz **und** erklärten Betrag automatisch mit der
vollen Differenz vor, siehe "Kassendifferenz erklären (Auflösung)" oben); oder
einfach einen eigenen Kommentar plus erklärten Betrag für den Steuerberater
hinterlassen (schreibt in `Zaehlung.notiz`/`Zaehlung.differenz_korrektur`,
dieselbe Auflösung wie auf der Auswertungsseite — die Kassendifferenz sinkt
danach entsprechend, bei vollem Betrag auf 0,00 €). Stimmt der bestätigte
Betrag mit dem Vorschlag überein, entfällt dieser Schritt.

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
(Semikolon-getrennt, UTF-8, deutsches Zahlenformat mit Komma). Spalten:
`Datum;Belegnummer;Artikel;Menge;Netto;USt-Satz;USt-Betrag;Brutto;Zahlungsart;Referenz;Notiz`.

- Eine Zeile pro Zählungszeitraum fasst alle Artikel zu einem Sammelposten
  zusammen (erlaubte Vereinfachung laut Vorgabe, da ohnehin einheitlich 19%
  USt anfallen und sich Bar-Zahlungen nicht auf einzelne Artikel aufteilen
  lassen) — die `Notiz`-Spalte übernimmt dabei `Zaehlung.notiz`, also auch
  eine über die Auswertung erfasste Kassendifferenz-Erklärung. Diese Zeile
  erscheint **immer** für jede Zählung mit Umsatz, offener Kassendifferenz
  oder Notiz — auch wenn der Bar-Anteil zufällig 0 € beträgt, damit eine
  Differenz nie spurlos aus dem Export verschwindet.
- Jede PayPal-Zahlung bekommt eine eigene Zeile mit ihrer Transaktions-ID als
  Referenz.
- Optional als eine einzige aggregierte Bar-Zeile für den ganzen Monat
  exportierbar.
- Zusätzlich eine **Kassenbestand-Übersicht** (Zahlungsart `Kassenbestand`,
  keine Erlös-Zeilen, deshalb Netto/USt leer): Anfangsbestand (gezähltes
  Bargeld der letzten Zählung vor dem Monat, 0 € falls keine vorhanden), jede
  einzelne `Kassenbewegung` des Monats (Einlage/Entnahme/fremder
  Bargeldeingang mit Betrag und Notiz/RG-Nummer als Referenz) und Endbestand
  (gezähltes Bargeld der letzten Zählung im Monat). So verschwindet z.B. eine
  Einlage nicht spurlos, und der Kassenbestand lässt sich von Monat zu Monat
  lückenlos nachrechnen. Hat die letzte Zählung des Monats noch kein
  bestätigtes Bargeld, fehlt der Endbestand und es gibt eine Warnung.

Der Export markiert den Monat als exportiert (`MonatsExport`) — danach sind
Korrekturen für diesen Monat nicht mehr rückwirkend möglich (Freigetränke,
Bestandskorrekturen), sondern werden als Vermerk im Folgemonat erfasst. Da
das nicht mehr rückgängig zu machen ist, prüft die Seite "CSV-Export" vor
jedem Export zwei Dinge:

### 1. Zählung genau auf den Monatsletzten Pflicht (`pruefe_monat_vollstaendig_gezaehlt`)

Eine Zählung deckt immer den Zeitraum seit der letzten Zählung bis
einschließlich ihres eigenen Datums ab und wird komplett dem Monat ihres
eigenen Datums zugerechnet. Wird z.B. nicht am 30.06., sondern erst am
04.07. gezählt, würde der gesamte Verbrauch seit dem 30.06. (also auch die
letzten Tage des Juni) fälschlich komplett dem Juli zugerechnet — der Juni
wäre dann zu niedrig, der Juli zu hoch ausgewiesen.

Deshalb lässt sich ein Monat nur exportieren, wenn die letzte Zählung dieses
Monats **genau auf den letzten Kalendertag** fällt und ihr Bargeld bereits
bestätigt ist (ein Monat ganz ohne jede Zählung ist unproblematisch, da es
nichts abzugleichen gibt). Fehlt diese Zählung, zeigt die Export-Seite einen
Block "Dieser Monat kann noch nicht abgeschlossen werden" mit einer direkten
Schaltfläche, die genau diese Zählung mit vorausgefülltem Datum anlegt (auch
mit 0 Verbrauch möglich, wenn an dem Tag nichts passiert ist — sie dient
dann nur als sauberer Monatsabschluss-Schnitt). Fehlt nur die
Bargeld-Bestätigung, führt die Schaltfläche stattdessen direkt zu "Bargeld
bestätigen" für diese Zählung.

### 2. Sicherheitsabfrage beim zu frühen Abschließen

Ist der gewählte Monat noch nicht vorbei (heutiges Datum liegt noch im
gewählten Monat oder davor), zeigt die Export-Seite statt des direkten
Downloads eine Sicherheitsabfrage ("Heute ist erst der TT.MM.JJJJ … Wirklich
jetzt schon abschließen?"). Erst ein zweiter, expliziter Klick auf "Ja,
trotzdem jetzt abschließen" führt den Export tatsächlich aus — so passiert
ein versehentlicher Abschluss eines noch laufenden Monats nicht durch einen
einzelnen Klick.

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
  3. **Differenz klären** (`/zaehlung/<id>/differenz/`), nur wenn der
     bestätigte Betrag vom Vorschlag abweicht: Kassendifferenz anzeigen und
     direkt anbieten, entweder Freigetränke nachzutragen (Datum
     vorausgefüllt) oder einen Kommentar für den Steuerberater zu
     hinterlassen.

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
  letzte), zeigt sofort ihr Ergebnis — Soll-Kassenbestand, Ist-Kassenbestand,
  Kassendifferenz, Zusammensetzung des Bar-Anteils sowie (rein informativ)
  den Einkaufswert der erfassten Belege und den Wert ausgegebener
  Freigetränke. Bei einer Kassendifferenz ungleich 0 direkt ein Feld zum
  Erklären der Differenz, das sie nach dem Speichern auflöst (siehe
  "Kassendifferenz erklären (Auflösung)" unter "Rechenlogik") — eine bereits
  erklärte Differenz erscheint stattdessen als "✓ Erledigt" mit Audit-Spur.
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
