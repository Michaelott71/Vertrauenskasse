# Deployment mit Docker

Diese Anleitung bringt die Vertrauenskasse per Docker Compose auf einen Server.
Zwei Container:

- **web**: Django-App via Gunicorn (nicht direkt von aussen erreichbar)
- **caddy**: Reverse Proxy, terminiert TLS und leitet an `web` weiter

## Zentrale Instanz statt lokalem Testlauf (Stand 2026-10-07)

`python manage.py runserver` auf einem einzelnen PC (siehe README) ist nur
zum **Testen** gedacht: läuft nur, solange das Fenster offen ist, und ist von
keinem anderen Gerät aus erreichbar. Für den echten Betrieb mit zwei Nutzern,
die sich einen gemeinsamen, fortlaufenden Datenbestand teilen (Zählungen
bauen aufeinander auf, VK-Belegnummern dürfen keine Lücken haben), braucht es
**eine einzige, durchgehend laufende Instanz**, die Handy und PC gleichermassen
erreichen.

**Empfehlung: ein kleiner Hetzner-Cloud-Server (CX22, Region Nürnberg/
Falkenstein, Deutschland/EU) für ca. 4-6 €/Monat**, darauf dieser bereits
fertige Docker-Compose-Stack, Zugriff von Handy und PC über **Tailscale**
(siehe eigener Abschnitt unten). Begründung dieser Wahl:

- **EU-Region**: Hetzner ist ein deutsches Unternehmen, Rechenzentren in
  Deutschland/Finnland.
- **Günstig**: ca. 4,49 €/Monat für den Server, ca. +20% für automatische
  Backups (siehe unten) — zusammen unter 6 €/Monat. (Preise bei Hetzner direkt
  vor der Buchung prüfen, können sich ändern.)
- **Ein Konto**: Nick legt nur **ein** Konto beim Hosting-Anbieter (Hetzner)
  an; Tailscale meldet man sich mit einer bestehenden Identität (Google/
  Microsoft/E-Mail) an, kein echtes Extra-Konto.
- **Kein Code-Umbau nötig**: Die App bleibt bei SQLite (eine einzelne Datei)
  — bei 2 Nutzern und ein paar Zählungen pro Woche gibt es keinen fachlichen
  Grund, auf eine separate Datenbank wie Postgres umzusteigen. Zentral wird
  die Sache dadurch, dass nur noch **eine** Instanz läuft, auf die beide
  Geräte zugreifen — nicht dadurch, welche Datenbank-Engine dahinter steckt.
- Wiederverwendet die hier bereits vorhandene, fertige Docker/Caddy-Konfiguration
  unveraendert.

Alternativen (jeder andere Anbieter mit Docker-Unterstuetzung und
EU-Rechenzentrum funktioniert genauso, z.B. ein beliebiger anderer VPS- oder
NAS-Anbieter) sind moeglich, aendern an dieser Anleitung aber nichts Grundsaetzliches.

### Server bei Hetzner Cloud anlegen (einmalig, macht Nick)

1. Auf [hetzner.com/cloud](https://www.hetzner.com/cloud) ein Konto anlegen
   (E-Mail + Zahlungsmethode, als Privatperson, keine Firma nötig).
2. Neues Projekt anlegen, z.B. "Vertrauenskasse".
3. "Server hinzufügen" / "Add Server":
   - **Standort**: Nürnberg oder Falkenstein (Deutschland)
   - **Image**: Ubuntu (aktuelle LTS-Version)
   - **Typ**: CX22 (2 vCPU, 4 GB RAM reicht sehr grosszügig für diese App)
   - **Backups**: Häkchen bei "Backups aktivieren" setzen (automatische
     wöchentliche Sicherungen, das erledigt die geforderten "automatischen
     Sicherungen")
   - SSH-Key oder Passwort nach Hetzners Anleitung einrichten
   - Server erstellen
4. Die öffentliche IPv4-Adresse des neuen Servers notieren.
5. Ab hier übernimmt der Rest dieser Anleitung — entweder tippt man die
   folgenden Befehle selbst über die **"Console"** im Hetzner-Browser-Dashboard
   ein (kein zusätzliches Programm nötig, öffnet eine Root-Konsole direkt im
   Browser), oder man gibt die IP-Adresse an die Person weiter, die den Rest
   einrichtet.

## Voraussetzungen

- Docker + Docker Compose Plugin auf dem Zielserver (`docker compose version`;
  auf einem frischen Hetzner-Ubuntu-Server: `curl -fsSL https://get.docker.com | sh`)
- Fuer den Fernzugriff: **Tailscale** (empfohlen, siehe eigener Abschnitt
  unten) — kein Port-Forwarding, keine Domain nötig, der Server bleibt für
  das übrige Internet unsichtbar.

## 1. Repository auf den Server bringen

```bash
git clone <repo-url> vertrauenskasse
cd vertrauenskasse
```

## 2. `.env` anlegen

```bash
cp .env.example .env
```

Secret Key erzeugen und eintragen:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`.env` bearbeiten:

- `DJANGO_SECRET_KEY`: den generierten Wert eintragen
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`: Domain (z.B. `vertrauenskasse.mein-verein.de`) oder,
  bei reinem LAN-Betrieb, die feste IP des Servers
- `DJANGO_CSRF_TRUSTED_ORIGINS`: nur bei Domain+HTTPS noetig, z.B.
  `https://vertrauenskasse.mein-verein.de` (bei reinem LAN/HTTP leer lassen)
- `SITE_ADDRESS`:
  - mit Domain: `SITE_ADDRESS=vertrauenskasse.mein-verein.de` (Caddy holt
    automatisch HTTPS)
  - ohne Domain, nur LAN: `SITE_ADDRESS=:80`

## 3. Bauen und starten

```bash
docker compose up -d --build
```

Logs pruefen:

```bash
docker compose logs -f web
```

Beim ersten Start fuehrt der Container automatisch `migrate` und
`collectstatic` aus (siehe `docker-entrypoint.sh`).

## 4. Superuser anlegen

```bash
docker compose exec web python manage.py createsuperuser
```

Fragt interaktiv nach Benutzername, E-Mail, Passwort. Danach unter
`https://<domain>/admin/` bzw. `http://<server-ip>/admin/` anmelden.

## 5. Getraenke anlegen

Siehe Abschnitt "Getraenke im Admin anlegen" in der README. Ohne mindestens
ein aktives Getraenk zeigt "Neue Zaehlung erfassen" nur einen Hinweis an.

## Zugriff per Tailscale einrichten

Statt einer oeffentlichen Domain mit Port-Forwarding: Tailscale baut ein
privates VPN zwischen Handy und Server auf, der Server bleibt fuer das
uebrige Internet unsichtbar.

1. Kostenlosen Account auf [tailscale.com](https://tailscale.com) anlegen
   (Free-Tier reicht fuer 1-2 Personen locker aus) — Anmeldung geht auch mit
   einem bestehenden Google-/Microsoft-Konto, kein neues Passwort noetig.
2. Tailscale auf dem Server installieren und anmelden:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up
   ```
   Der Befehl zeigt einen Link an — im Browser oeffnen und mit dem
   Tailscale-Account bestaetigen.
3. Tailscale-App auf dem Handy/Laptop installieren (App Store/Play Store) und
   mit demselben Account anmelden.
4. Im [Tailscale Admin-Console](https://login.tailscale.com/admin/machines)
   nachsehen, welchen Namen/welche IP der Server bekommen hat (z.B.
   `vertrauenskasse.tailXXXX.ts.net` oder `100.x.x.x`).
5. In `.env`:
   - `DJANGO_ALLOWED_HOSTS=<tailscale-name-oder-ip-des-servers>`
   - `SITE_ADDRESS=:80` (kein oeffentliches Zertifikat noetig — Tailscale
     verschluesselt die Verbindung bereits selbst)
   - `DJANGO_CSRF_TRUSTED_ORIGINS` leer lassen
6. `docker compose up -d --build`.
7. Von unterwegs: Tailscale-App auf dem Handy aktivieren, dann im Browser
   `http://<tailscale-name-des-servers>/` aufrufen — funktioniert wie im
   Heimnetz, egal wo man gerade ist.

## Von lokalem Testlauf auf den zentralen Server umziehen

Falls vorher schon lokal getestet wurde (`python manage.py runserver`) und
diese Testdaten tatsaechlich uebernommen werden sollen (meistens nicht noetig
— einfach auf dem zentralen Server frisch mit `migrate` anfangen reicht):

1. Auf dem PC: App stoppen. `db.sqlite3` und den `media/`-Ordner (falls
   vorhanden, enthaelt hochgeladene Beleg-Scans) aus dem Projektordner
   sichern.
2. Auf dem Server: Repository klonen, `.env` gemaess Anleitung oben einrichten
   (inkl. Tailscale-Abschnitt), dann normal starten: `docker compose up -d --build`.
3. `web`-Container kurz anhalten, damit die SQLite-Datei nicht gerade offen
   ist, dann die gesicherten Dateien einspielen und neu starten:
   ```bash
   docker compose stop web
   docker cp db.sqlite3 $(docker compose ps -aq web):/app/data/db.sqlite3
   docker cp media/. $(docker compose ps -aq web):/app/media/
   docker compose start web
   ```

Ab dem Zeitpunkt, an dem der zentrale Server laeuft, bitte **ausschliesslich**
diesen fuer echte Zaehlungen benutzen — ein paralleler lokaler Testlauf wuerde
sonst eigene, mit dem Server kollidierende VK-Belegnummern vergeben.

## Updates einspielen

```bash
git pull
docker compose up -d --build
```

Migrationen laufen automatisch beim Neustart des `web`-Containers.

## Backup

Bei Hetzner Cloud mit aktiviertem "Backups"-Haekchen sichert der Anbieter
bereits automatisch und ohne weiteres Zutun woechentlich den ganzen Server
(inkl. Datenbank). Zusaetzlich lohnt sich eine eigene, inhaltliche Sicherung
der SQLite-Datei (unabhaengig vom Hosting-Anbieter, z.B. um sie woanders
aufzubewahren):

Die SQLite-Datenbank und hochgeladenen Belege liegen in den Docker-Volumes
`db-data` (`/app/data/db.sqlite3`) und `media-data` (`/app/media/`). Backup
z.B. so:

```bash
docker compose exec web sh -c "sqlite3 /app/data/db.sqlite3 '.backup /app/data/backup.sqlite3'"
docker cp $(docker compose ps -q web):/app/data/backup.sqlite3 ./backup-$(date +%F).sqlite3
docker run --rm -v vertrauenskasse_media-data:/media -v "$PWD":/backup alpine \
  tar czf /backup/media-$(date +%F).tar.gz -C /media .
```

Beide Dateien regelmaessig (z.B. woechentlich per Cronjob) an einen anderen
Ort kopieren.

## Troubleshooting

- **502/Bad Gateway von Caddy**: `docker compose logs web` pruefen — meist ein
  fehlerhafter `DJANGO_SECRET_KEY`/`.env`-Wert oder eine fehlgeschlagene
  Migration.
- **CSRF-Fehler im Browser**: `DJANGO_CSRF_TRUSTED_ORIGINS` fehlt oder passt
  nicht zur tatsaechlich aufgerufenen URL (Schema `https://` nicht vergessen).
- **Kein automatisches HTTPS-Zertifikat**: DNS zeigt noch nicht auf den
  Server, oder Port 443 ist von aussen nicht erreichbar (Router/Firewall
  pruefen).
