# Majors Golfbox – Homepage

Statische One-Pager-Website (HTML/CSS/vanilla JS, kein Build-Tooling, kein
CMS). Laeuft auf jedem Standard-Webspace wie bei Strato – einfach den
kompletten Ordner `homepage/` per FTP/Datei-Manager auf den Webspace
hochladen (`index.html` als Startseite).

Eigenstaendiges Projekt, unabhaengig von der `kasse/`-Django-App in diesem
Repository (kein gemeinsamer Code, kein gemeinsames Deployment).

## Lokal testen

```bash
cd homepage
python3 -m http.server 8000
```

Dann im Browser `http://localhost:8000/` oeffnen. Wichtig: Die Seite laedt
Inhalte per `fetch()` aus den JSON-Dateien in `content/` – das funktioniert
nur ueber `http://`, nicht wenn man `index.html` direkt per Doppelklick
(`file://`) oeffnet.

## Inhalte pflegen – ohne Code anzufassen

Alle Inhalte, die sich haeufiger aendern, liegen in `content/*.json`
(einfache Textdateien, mit jedem Editor bearbeitbar):

| Datei | Zweck |
|---|---|
| `content/reviews.json` | Google-Sternebewertung + Anzahl. Einfach `rating`/`count` anpassen. |
| `content/gallery.json` | Fotos der Anlage. Bild in `assets/img/bay/` ablegen, Dateinamen hier eintragen. |
| `content/trackman.json` | Die 12 Trackman-„Know Your Numbers"-Grafiken. Bild in `assets/img/trackman/` ablegen, Dateinamen + Kennzahl eintragen. |
| `content/tournaments.json` | Aktuelle Turniere. Leeres `active`-Array = Abschnitt „Turniere" wird auf der Seite automatisch ausgeblendet. |
| `content/config.json` | Telefonnummern, E-Mail, WhatsApp, Buchungsportal-URL, Google-Ads/Analytics-IDs, Adresse. |
| `content/i18n.json` | Alle Texte der Seite, deutsch (`de`) und englisch (`en`). |

Nach dem Speichern reicht ein Neuladen der Seite im Browser (kein Deploy,
kein Build noetig).

## Vor dem Live-Schalten noch zu erledigen

1. **Logo**: `assets/img/logo/logo.svg` ist aktuell nur ein Platzhalter.
   Durch die finale Logo-Datei ersetzen (gleicher Dateiname, oder Pfad in
   `index.html`/`impressum.html`/`datenschutz.html` anpassen).
2. **Schrift Qaranta Bold**: Lizenzpflichtige Datei von dafont.com, liegt
   hier nicht bei. `Qaranta-Bold.woff2` (und optional `.woff`) in
   `assets/fonts/` ablegen – die Seite nutzt sie dann automatisch fuer
   Ueberschriften/Logo-Schriftzug. Bis dahin greift eine fette
   Systemschrift als Ersatz.
3. **Fotos**: Echte Bay-Fotos in `assets/img/bay/` ablegen, Trackman-
   Grafiken in `assets/img/trackman/`, Partner-Fotos (Hofgut Georgenthal)
   optional in `assets/img/partner/`. Dateinamen jeweils in den passenden
   `content/*.json` eintragen (siehe oben).
4. **`content/config.json`**: `booking_url` durch die echte Adresse des
   Buchungsportals ersetzen, `google_ads_conversion_id` /
   `google_ads_label_booking` / `google_ads_label_call` /
   `google_analytics_id` durch echte IDs ersetzen, sobald Google
   Ads/Analytics-Zugang geprueft ist. Zweite Telefonnummer
   (`phone_guthaben_display`) mit Michael Ott gegenchecken (siehe
   `_note`-Feld in der Datei).
5. **Datenschutzerklaerung** (`datenschutz.html`): als Entwurf markiert –
   bitte anwaltlich pruefen/freigeben lassen, siehe Hinweisbox oben auf der
   Seite.
6. **Impressum** (`impressum.html`): Umsatzsteuer-ID/Handelsregister
   ergaenzen, falls vorhanden.
7. **Training-Abschnitt**: Aktuell nur Trackman-basiertes Training
   beschrieben (`content/i18n.json` → `training`). Bitte bestaetigen, ob
   zusaetzlich persoenliches Coaching durch Trainer angeboten wird.

## Tracking / Cookie-Consent

Google Ads/Analytics werden **erst nach Zustimmung** im Cookie-Banner
geladen (`assets/js/main.js`, Funktion `loadTrackingScripts`). Solange in
`content/config.json` nur Platzhalter-IDs (`XXXX…`) stehen, bleibt das
Tracking inaktiv – es passiert also nichts Ungewolltes, bevor echte IDs
eingetragen sind. Conversion-Events:

- `booking_click` – Klick auf einen „Jetzt buchen"-Button (Ziel: „Buchung
  abgeschlossen"-Signal an Google Ads; fuer eine echte Abschluss-Conversion
  muesste das Buchungsportal selbst das Conversion-Tag feuern – aktuell
  wird hier der Klick zum externen Portal getrackt, nicht der tatsaechliche
  Abschluss dort)
- `call_click` – Klick auf „Anrufen" (`tel:`-Link)

## Struktur

```
homepage/
  index.html
  impressum.html
  datenschutz.html
  content/            JSON-Inhalte (siehe oben)
  assets/
    css/style.css     Design-System (Farben, Typo, Layout)
    js/main.js         i18n, Cookie-Consent, Slider, dynamisches Rendering
    fonts/              Qaranta Bold hier ablegen
    img/
      logo/             Logo (Platzhalter bis echte Datei vorliegt)
      bay/               Fotos der Anlage
      trackman/          Trackman-Grafikset
      partner/           Hofgut-Georgenthal-Fotos
```
