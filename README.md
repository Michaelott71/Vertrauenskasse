# Majors Golfbox – Website

One-Pager mit Ankernavigation (DE/EN), gebaut mit [Astro](https://astro.build) als statische Seite.
Kein Server, kein CMS – reine HTML/CSS/JS-Dateien, per FTP auf den bestehenden Strato-Webspace hochladbar.

## Struktur

```
src/
  components/     Wiederverwendbare Sektionen (Hero, Preise, Trainer, Turniere, Kontakt, Cookie-Banner, ...)
  data/
    site.ts        Kontaktdaten, Buchungsportal-Link, Google-Bewertungen-Link, GTM-ID
    pricing.ts      Preise/Mitgliedschaften
    tournaments.json  Turniere – "visible": false blendet den ganzen Bereich aus
  i18n/            Übersetzungen DE/EN (src/i18n/ui.ts)
  layouts/         BaseLayout.astro (Head, Header, Footer, Cookie-Banner, Tracking)
  pages/
    de/, en/        Startseite + Impressum/Datenschutz je Sprache
```

## Lokal entwickeln

```bash
npm install
npm run dev       # http://localhost:4321
npm run build     # baut nach dist/
npm run preview   # testet den Production-Build lokal
```

## Vor dem Launch zu erledigen

Alle offenen Punkte sind im Code mit `TODO:` markiert. Wichtigste Stellen:

- **`src/data/site.ts`** – echte Telefonnummer, WhatsApp-Business-Nummer, E-Mail, Google-Bewertungslink,
  finale Buchungsportal-URL und GTM-Container-ID eintragen.
- **`src/data/pricing.ts`** – Platzhalterpreise durch echte Stundenpreise/Mitgliedschaften ersetzen.
- **`src/pages/de/impressum.astro`, `datenschutz.astro`, `src/pages/en/imprint.astro`, `privacy.astro`** –
  durch die vorbereiteten, anwaltlich geprüften Texte ersetzen.
- **`src/data/tournaments.json`** – `"visible": true` setzen und Turnier eintragen, sobald eins ansteht.
- **`src/components/Trainer.astro`** – Platzhalter-Foto von Nick Ott ersetzen.
- **Logo & Farbschema** – Custom Properties in `src/styles/global.css` (`:root`) durch die echten
  Markenfarben ersetzen; Logo-Datei einbinden (aktuell nur Textmarke "Majors Golfbox" im Header/Footer).
- **Fotos/Videos** der Bays in `src/assets/` bzw. `public/` ablegen und in Hero/Über-uns einbinden.

## Tracking & Cookie-Consent

- Tracking läuft über **Google Tag Manager** mit **Consent Mode v2**. Ohne Zustimmung im Cookie-Banner
  wird kein Analytics-/Ads-Cookie gesetzt (`ad_storage`/`analytics_storage` standardmäßig `denied`).
- GTM wird nur geladen, wenn `site.tracking.gtmId` in `src/data/site.ts` gesetzt ist.
- Klicks auf CTAs (`data-cta="book-now"`, `"book-trainer"`, `"call"`, `"whatsapp"`, `"email"`) werden als
  `cta_click`-Event in den `dataLayer` gepusht – im GTM-Container als Trigger für die Conversion-Ziele
  „Angerufen" (`cta_type: call`) und „Buchung gestartet" (`cta_type: book-now`/`book-trainer`) nutzbar.
- **Wichtig:** Das eigentliche Ziel „Buchung abgeschlossen" kann nur im Buchungsportal selbst final erfasst
  werden (dort müsste ein eigenes GTM/GA4-Event bei Abschluss ausgelöst werden) – die Homepage kann nur den
  Klick auf „Jetzt buchen" als Vorstufe tracken.
- Vor Launch prüfen: Ist bereits ein GTM-Container/GA4-Property vorhanden (frühere Kampagne), oder muss
  neu eingerichtet werden? GTM-ID dann in `src/data/site.ts` eintragen.

## Deployment (Strato per FTP)

1. `npm run build` ausführen → Ergebnis liegt in `dist/`.
2. Inhalt von `dist/` (nicht den Ordner selbst) per FTP/SFTP in das Wurzelverzeichnis des Strato-Webspace
   hochladen (z. B. mit FileZilla oder `lftp`).
3. Domain `majorsgolfbox.de` zeigt weiterhin auf den bestehenden Strato-Webspace – keine DNS-Änderung nötig.

## Sprachumschaltung

`/de` ist die Standardsprache, `/en` die englische Version. Die Wurzel `/` leitet automatisch auf `/de`
weiter. Der Sprachumschalter im Header verlinkt jeweils auf die andere Sprache derselben Seite.
