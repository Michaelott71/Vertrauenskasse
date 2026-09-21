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

1. ~~**Logo**~~ Erledigt. Echtes Logo eingebaut: `assets/img/logo/logo-icon.png`
   (quadratische Wort-Bild-Marke, fuer Header/Favicon) und
   `assets/img/logo/logo-full.png` (volles Lockup mit Schriftzug, als Asset
   verfuegbar, aktuell nirgends fest eingebunden).
2. **Schrift Qaranta Bold**: Kostet beim Schriftgestalter 5 $ Lizenzgebuehr
   fuer die kommerzielle Nutzung (dafont.com bietet nur die private Nutzung
   kostenlos an). Bis die Lizenz gekauft ist, verwendet die Seite
   **Poppins Bold** als Uebergangslösung – eine aehnlich kraeftige,
   geometrische Schrift, kostenlos auch fuer kommerzielle Nutzung (SIL Open
   Font License, selbst gehostet in `assets/fonts/BrandDisplay-Bold.woff2`,
   Lizenztext in `assets/fonts/OFL-Poppins.txt`). Sobald die Qaranta-Lizenz
   gekauft ist: `Qaranta-Bold.woff2` in `assets/fonts/` ablegen – sie wird
   dann automatisch statt Poppins verwendet, ohne dass sonst etwas
   geaendert werden muss.
3. ~~**Bay-Fotos**~~ Erledigt – 4 echte Fotos in `assets/img/bay/`
   eingebunden (`content/gallery.json`), darunter zwei mit dem
   Hofgut-Georgenthal-Partnerbanner im Bild. **Trackman-„Know Your
   Numbers"-Grafikset (12 Bilder) fehlt noch** – bitte ebenfalls hier
   anhaengen, dann werden sie in `assets/img/trackman/` abgelegt und in
   `content/trackman.json` eingetragen.
4. **`content/config.json`**: `booking_url` durch die echte Adresse des
   Buchungsportals ersetzen, `google_ads_conversion_id` /
   `google_ads_label_booking` / `google_ads_label_call` /
   `google_analytics_id` durch echte IDs ersetzen, sobald Google
   Ads/Analytics-Zugang geprueft ist. `whatsapp_number` gegenchecken (siehe
   `whatsapp_note`-Feld in der Datei) – die zweite Telefonnummer fuer
   telefonische Buchung ist bereits bestaetigt und in der Preise-Sektion
   sichtbar.
5. **Datenschutzerklaerung** (`datenschutz.html`): als Entwurf markiert –
   bitte anwaltlich pruefen/freigeben lassen, siehe Hinweisbox oben auf der
   Seite.
6. **Impressum** (`impressum.html`): Umsatzsteuer-ID/Handelsregister
   ergaenzen, falls vorhanden.

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
    fonts/              Qaranta Bold hier ablegen (Poppins Bold als Uebergangslösung bereits vorhanden)
    img/
      logo/             Echtes Logo (logo-icon.png fuer Header/Favicon, logo-full.png als Lockup-Asset)
      bay/               Fotos der Anlage (inkl. 2 Fotos mit Hofgut-Georgenthal-Partnerbanner)
      trackman/          Trackman-Grafikset (noch zu ergaenzen)
      partner/           Reserviert fuer eigenstaendige Hofgut-Georgenthal-Fotos (aktuell leer)
```
