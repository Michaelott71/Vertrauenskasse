# Majors Golfbox – Buchungsportal

Buchungsportal für die 2 Trackman-Bays der Majors Golfbox. Konzept, Datenmodell
und Roadmap stehen in [`docs/ARCHITEKTUR.md`](docs/ARCHITEKTUR.md).

Stack: Next.js (App Router, TypeScript), Tailwind CSS, Prisma + PostgreSQL.

## Setup

1. Abhängigkeiten installieren: `npm install`
2. `.env.example` nach `.env` kopieren und Werte anpassen (`DATABASE_URL`,
   `JWT_SECRET`, optional `ADMIN_EMAIL`/`ADMIN_PASSWORD` für den Seed).
3. Datenbank migrieren: `npx prisma migrate dev`
4. Grunddaten (Tenant, 2 Bays, optional Admin-Benutzer) anlegen:
   `npx prisma db seed`
5. Dev-Server starten: `npm run dev` und
   [http://localhost:3000](http://localhost:3000) öffnen.

## Aktueller Stand (MVP, Phase 1)

- Registrierung/Login (E-Mail + Passwort)
- Buchungskalender für beide Bays (rollierende 3-Tage-Ansicht, 55-Min-Slots
  zur vollen Stunde, 14-Tage-Buchungsfenster, 1-Tag-Vorlauf für Neukunden)
- Stornierung durch Kunden bis 24h vor Termin
- Admin: Tagesübersicht mit Kundennamen, Slots kostenfrei/bezahlt blocken,
  Blocks löschen, Kundenbuchungen stornieren

Zahlung, Guthaben, Mitgliedschaften, Preisregeln, Trainer-Portal, E-Mail-
Kommunikation und Mehrsprachigkeit sind in `docs/ARCHITEKTUR.md` als spätere
Phasen beschrieben, aber noch nicht implementiert.

## Nützliche Kommandos

- `npm run lint` – ESLint
- `npx tsc --noEmit` – Type-Check
- `npm run build` – Produktionsbuild
- `npx prisma studio` – Datenbank-Inhalte ansehen
