# Deployment mit Docker

Diese Anleitung bringt die Vertrauenskasse per Docker Compose auf einen Server
(z.B. Vereins-Server, NAS, VPS, Raspberry Pi mit Docker). Zwei Container:

- **web**: Django-App via Gunicorn (nicht direkt von aussen erreichbar)
- **caddy**: Reverse Proxy, terminiert TLS und leitet an `web` weiter

## Voraussetzungen

- Docker + Docker Compose Plugin auf dem Zielserver (`docker compose version`)
- Entweder:
  - eine Domain, die per DNS (A-Record) auf den Server zeigt, plus Port 80 **und**
    443 offen -> Caddy holt automatisch ein Let's-Encrypt-Zertifikat, oder
  - nur Zugriff im Vereins-LAN per IP -> reines HTTP auf Port 80 (kein eigenes
    Zertifikat noetig)

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
