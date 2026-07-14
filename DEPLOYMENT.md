# Deployment mit Docker

Diese Anleitung bringt die Vertrauenskasse per Docker Compose auf einen Server
(z.B. NAS, VPS, Raspberry Pi mit Docker). Zwei Container:

- **web**: Django-App via Gunicorn (nicht direkt von aussen erreichbar)
- **caddy**: Reverse Proxy, terminiert TLS und leitet an `web` weiter

## Geplanter Rollout (Notiz, Stand 2026-07-14)

Vereinbarter Plan fuer den Einsatz in der Firma:

1. **Phase 1 (jetzt):** Lokal auf dem PC laufen lassen, ohne Docker/NAS/Tailscale
   — siehe "Setup" in der README (`python manage.py runserver`). Reicht zum
   Testen und ersten produktiven Erfassen von Zaehlungen.
2. **Phase 2 (spaeter):** Daten (SQLite-Datei + `media/`-Ordner mit Belegen) auf
   das heimische NAS umziehen, dort per Docker Compose (diese Anleitung)
   betreiben, und den Fernzugriff ueber **Tailscale** (VPN) statt einer
   oeffentlichen Domain herstellen — kein Port-Forwarding, NAS bleibt nach
   aussen unsichtbar. Siehe Abschnitt "Zugriff per Tailscale" unten.

Der Umzug von Phase 1 zu Phase 2 ist unkompliziert, weil die komplette
Datenbank eine einzelne Datei ist (`db.sqlite3`) — einfach kopieren, siehe
Abschnitt "Von lokalem PC auf NAS umziehen".

## Voraussetzungen

- Docker + Docker Compose Plugin auf dem Zielserver (`docker compose version`)
- Fuer den Fernzugriff (siehe Phase 2 oben): entweder
  - **Tailscale** (empfohlen fuer diesen Anwendungsfall): kein Port-Forwarding,
    keine Domain noetig — siehe eigener Abschnitt unten, oder
  - eine Domain, die per DNS (A-Record) auf den Server zeigt, plus Port 80 **und**
    443 offen -> Caddy holt automatisch ein Let's-Encrypt-Zertifikat, oder
  - nur Zugriff im lokalen Heim-/Firmennetz per IP -> reines HTTP auf Port 80
    (kein eigenes Zertifikat noetig)

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

## Zugriff per Tailscale einrichten (fuer Phase 2)

Statt einer oeffentlichen Domain mit Port-Forwarding: Tailscale baut ein
privates VPN zwischen deinen Geraeten auf, das NAS bleibt fuer das Internet
unsichtbar.

1. Kostenlosen Account auf [tailscale.com](https://tailscale.com) anlegen
   (Free-Tier reicht fuer 1-2 Personen locker aus).
2. Tailscale auf dem NAS installieren:
   - **Synology**: Paket-Zentrum -> nach "Tailscale" suchen (ab DSM 7.2 offiziell
     verfuegbar) und installieren. Falls nicht gelistet: als Docker-Container
     `tailscale/tailscale` in Container Manager laufen lassen.
   - **QNAP**: App Center -> "Tailscale" installieren (falls verfuegbar), sonst
     ebenfalls als Docker-Container ueber Container Station.
   Danach im Tailscale-Client auf dem NAS mit dem Account anmelden.
3. Tailscale-App auf dem Handy/Laptop installieren (App Store/Play Store) und
   mit demselben Account anmelden.
4. Im [Tailscale Admin-Console](https://login.tailscale.com/admin/machines)
   nachsehen, welchen Namen/welche IP das NAS bekommen hat (z.B.
   `nas.tailXXXX.ts.net` oder `100.x.x.x`).
5. In `.env`:
   - `DJANGO_ALLOWED_HOSTS=<tailscale-name-oder-ip-des-nas>`
   - `SITE_ADDRESS=:80` (kein oeffentliches Zertifikat noetig — Tailscale
     verschluesselt die Verbindung bereits selbst)
   - `DJANGO_CSRF_TRUSTED_ORIGINS` leer lassen
6. `docker compose up -d --build`.
7. Von unterwegs: Tailscale-App auf dem Handy aktivieren, dann im Browser
   `http://<tailscale-name-des-nas>/` aufrufen — funktioniert wie im Heimnetz.

## Von lokalem PC auf NAS umziehen (Phase 1 -> Phase 2)

Wenn die App vorher lokal ohne Docker lief (`python manage.py runserver`):

1. Auf dem PC: App stoppen. `db.sqlite3` und den `media/`-Ordner (falls
   vorhanden, enthaelt hochgeladene Beleg-Scans) aus dem Projektordner
   sichern.
2. Auf dem NAS: Repository klonen, `.env` gemaess Anleitung oben einrichten
   (inkl. Tailscale-Abschnitt), dann normal starten: `docker compose up -d --build`.
3. `web`-Container kurz anhalten, damit die SQLite-Datei nicht gerade offen
   ist, dann die gesicherten Dateien einspielen und neu starten:
   ```bash
   docker compose stop web
   docker cp db.sqlite3 $(docker compose ps -aq web):/app/data/db.sqlite3
   docker cp media/. $(docker compose ps -aq web):/app/media/
   docker compose start web
   ```

## Updates einspielen

```bash
git pull
docker compose up -d --build
```

Migrationen laufen automatisch beim Neustart des `web`-Containers.

## Backup

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
