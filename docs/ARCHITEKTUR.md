# Majors Golfbox – Buchungsportal: Konzept & Architektur

Stand: 2026-07-15. Dieses Dokument fasst die Anforderungen aus dem Projektbriefing
in eine technische Struktur, definiert das Datenmodell, grenzt MVP (Ziel 1. Oktober)
von späteren Phasen ab und listet offene Punkte.

## 1. Ziel & Phasen

**Phase 1 – MVP (bis 1. Oktober):**
Buchungskalender für 2 Bays, Registrierung/Login, Buchungsregeln (55 Min/volle
Stunde, 14-Tage-Fenster, Neukunden-Sperrfrist), einfaches Admin-Blocking.

**Phase 2 (parallel/kurz danach, vor Saisonstart 1.10.–15.4.):**
Zahlungsanbindung, Quittungen/Datev-Export, Guthaben & Rabatte, Storno/No-Show,
Mitgliedschaften, Preisregeln, Zugangscode-Mailings.

**Phase 3 (Nov/Dez, laut Briefing verschiebbar):**
Gutschein-Einlösung, WhatsApp-Anbindung, Trainer-Portal (Nick) als eigene Instanz,
Mehrsprachigkeit (DE/EN).

Firmenbuchungen (Abschnitt 11) laufen dauerhaft außerhalb des Portals und werden
nur als manuelle Admin-Blocks abgebildet – kein separates Modul nötig.

## 2. Tech-Stack (Vorschlag)

| Bereich | Wahl | Begründung |
|---|---|---|
| Web-Framework | Next.js (App Router, TypeScript) | Ein Repo für Front- und Backend (API-Routen/Server Actions), gutes Mobile-First-Tooling, einfach zu hosten |
| Styling | Tailwind CSS | schnelles Mobile-First-Layout, konsistentes Design-System |
| Datenbank | PostgreSQL | relationale Integrität für Buchungen/Zahlungen, gute Reporting-/Export-Fähigkeiten (Datev) |
| ORM | Prisma | typsichere Queries, Migrations, gute DX |
| Auth | eigene Implementierung (bcrypt + JWT-Session-Cookie) | schlank, keine Abhängigkeit von Social-Login, volle Kontrolle über Registrierungsfelder |
| Zahlungsdienstleister | offen (siehe offene Punkte) – Anbindung über eigenes `PaymentProvider`-Interface | Wechsel des Anbieters soll keine Datenmodelländerung erfordern |
| E-Mail-Versand | Transactional-E-Mail-Provider (z. B. Resend/Postmark), austauschbar über Interface | Bestätigungen, Zugangscodes, Bewertungs-Mail |
| Deployment | Docker-fähig, env-basierte Konfiguration | Hosting-Wahl bleibt offen |

Die Codebasis wird von Anfang an so strukturiert, dass das **Trainer-Portal**
(Abschnitt 6) als zweite Instanz derselben Codebasis mit eigener Konfiguration
(eigene Bays/Ressourcen, eigene Preislogik, eigener Betreiber) deploybar ist,
ohne Code zu forken (Mandantenfähigkeit über eine `Tenant`/`Location`-Entität).

## 3. Datenmodell (Kernentitäten)

```
User
 - id, email (unique), passwordHash
 - name, address, phone
 - role: CUSTOMER | ADMIN | STAFF (Abschnitt 10: Mitarbeiterzugänge, später)
 - customerType: NEW | REGULAR | MEMBER  (für Farbcodierung im Kalender, Abschnitt 8)
 - isInstructed: boolean   // bereits eingewiesen -> Ausnahme von 1-Tag-Sperrfrist
 - marketingOptIn: boolean
 - privacyAcceptedAt: datetime
 - createdAt

Bay
 - id, name ("Bay 1", "Bay 2"), photoUrl
 - tenantId  (Mandant: Golfbox vs. künftiges Trainer-Portal)

Booking
 - id, bayId, userId (nullable bei Admin-Block ohne Kunde)
 - startsAt, endsAt        // startsAt immer volle Stunde, Dauer 55 Min
 - status: CONFIRMED | CANCELLED | NO_SHOW | COMPLETED
 - type: CUSTOMER | ADMIN_BLOCK_FREE | ADMIN_BLOCK_PAID | TRAINER_SLOT
 - paymentStatus: NONE | PENDING | PAID | REFUNDED_AS_CREDIT | FAILED
 - trainerId (nullable, nur wenn type = TRAINER_SLOT)
 - createdAt, cancelledAt, cancelledBy

Payment
 - id, bookingId (nullable, auch für Guthabenkauf), userId
 - amount, currency, provider, providerRef
 - status: PENDING | SUCCEEDED | FAILED | REFUNDED
 - receiptNumber (fortlaufend, unique, pro Kalenderjahr oder global – s. offene Punkte)
 - createdAt

Receipt
 - id, paymentId, number (fortlaufend), pdfUrl, cancelledAt (bei Storno)

CreditAccount (Guthaben)
 - id, userId, balance
CreditTransaction
 - id, creditAccountId, amount (+/-), reason (PURCHASE_BONUS | BOOKING_PAYMENT |
   CANCELLATION_REFUND | ADMIN_ADJUSTMENT), relatedBookingId, relatedPaymentId, createdAt

MembershipPlan
 - id, name, type: ANYTIME | RESTRICTED_HOURS | CUSTOM
 - allowedFrom, allowedTo (bei RESTRICTED_HOURS, z. B. 06:00–16:00)
 - monthlyQuotaHours (Standard 10), maxAdvanceBookingHours (Standard 3)
 - price, priceInstallment2 (für 2-Raten-Option)
 - extraHourDiscountPrice
 - season (z. B. "2026/2027": 1.10.–15.4.)

Membership
 - id, userId, membershipPlanId
 - status: ACTIVE | INACTIVE | PENDING_PAYMENT
 - paymentMode: FULL | TWO_INSTALLMENTS
 - installment1PaidAt, installment2PaidAt
Membership monatliches Kontingent wird nicht als Feld auf Membership gespeichert,
sondern über eine MonthlyQuota-Tabelle (userId, yearMonth, baseHours, bonusHours,
usedHours) berechnet – so bleiben Admin-Zusatzstunden (Urlaubsfälle) und Verfall
sauber nachvollziehbar.

PriceRule
 - id, tenantId, name, priority
 - dayType: WEEKDAY | WEEKEND | HOLIDAY
 - timeFrom, timeTo (z. B. Happy Hour)
 - pricePerSlot
(Auswertung: höchste passende Priority gewinnt; Preisvorschau nutzt dieselbe
Funktion wie die eigentliche Buchung, damit Anzeige und Abrechnung nie auseinanderlaufen.)

AccessCode
 - id, bookingDate (Code gilt tagesbezogen für die Anlage, nicht pro Buchung),
   code, validFrom, validTo
CodeLog: historische Zuordnung Datum -> Code für Nachvollziehbarkeit.

NotificationLog
 - id, userId, type: BOOKING_CONFIRMATION | REVIEW_REQUEST | PAYMENT_FAILED |
   MEMBERSHIP_REMINDER | WHATSAPP_REMINDER (Phase 3)
 - sentAt, channel: EMAIL | WHATSAPP
```

**Warum getrennte `CreditAccount`/`CreditTransaction` statt nur ein Saldo-Feld:**
Abschnitt 2 und 3 verlangen Nachvollziehbarkeit ("Hinweis: bereits bezahlt über
Rechnung XYZ", Storno-Gutschriften) – ein Ledger aus Einzeltransaktionen ist hier
robuster als ein simples `balance`-Feld und verhindert Debugging-Aufwand bei
Differenzen.

## 4. Buchungsregeln (Kernlogik, gilt für Golfbox-Bays und Trainer-Slots gleichermaßen)

- Slotraster: Start nur zur vollen Stunde, Dauer immer 55 Minuten.
- Buchungsfenster Standard: heute + 14 Tage (heute+14 buchbar, heute+15 nicht).
- Neukunden ohne `isInstructed`: erst ab 1 Tag Vorlauf buchbar.
- Standardkunden: max. 10 Std. Vorausbuchung gleichzeitig offen.
- Mitglieder: max. 3 Std. Vorausbuchung innerhalb ihres Monatskontingents;
  Zusatzstunden über Kontingent hinaus zum Rabattpreis, keine 3h-Vorausbuchungs-
  Begrenzung dafür vorgesehen (offener Punkt, s. u.).
- Beide Bays sind unabhängig voneinander buchbar; ein Kunde kann beide parallel
  belegen (kein Constraint "ein Kunde = eine aktive Buchung").
- Trainer-Slots sind normale `Booking`-Zeilen mit `type = TRAINER_SLOT` auf einer
  der beiden echten Bays – für Kunden im Golfbox-Kalender nicht als eigene
  Ressource sichtbar, nur farblich/labeled als "Trainerstunde".
- Stornierung: >24h vorher durch Kunde möglich (Gutschrift als Guthaben oder
  reine Terminfreigabe ohne Gutschrift), <24h nur Admin. No-Show: Zahlung
  verfällt; bei Mitgliedern wird die Stunde trotzdem vom Kontingent abgezogen.

Diese Regeln werden als reine Funktionen (z. B. `getBookableWindow(user)`,
`isSlotBookable(user, slot)`) implementiert, damit Kalenderanzeige, Server-
seitige Validierung und spätere Preisvorschau dieselbe Quelle nutzen.

## 5. Modulübersicht (Mapping auf Briefing-Abschnitte)

| # | Modul | Phase |
|---|---|---|
| 1 | Zahlung & Rechnungen (Quittungsnummerierung, Datev-Export) | 2 |
| 2 | Guthaben & Rabatte | 2 |
| 3 | Stornierung/No-Show | 2 |
| 4 | Registrierung | **1 (MVP)** |
| 5 | Mitgliedschaften | 2 |
| 6 | Trainer (Golfbox-interne Slots) / Trainer-Portal (separate Instanz) | 1 (Slots als Blocks) / 3 (eigenes Portal) |
| 7 | Preise (Preisregeln + Vorschau) | 2 |
| 8 | Kalender/UI (2 Bays, Tages-/Wochenansicht, Fotos, Farbcodierung) | **1 (MVP, Basis)** / Feinschliff Phase 2 |
| 9 | Kommunikation/Workflows (Mail, Zugangscode, Bewertungsmail, WhatsApp) | 2 (Mail) / 3 (WhatsApp) |
| 10 | Admin-Funktionen (Blocken, wiederkehrend, Mitarbeiterzugänge) | **1 (Basis-Blocking)** / 2 (wiederkehrend, Mitarbeiterrollen) |
| 11 | Firmenbuchungen | manuell über Admin-Block, kein eigenes Modul |
| 12 | Sprache DE/EN | 3 (nice-to-have) |
| 13 | Parallel-Buchung beider Bays | **1**, siehe Buchungsregeln |

## 6. Rollen & Rechte

- **Kunde (nicht eingeloggt/neu):** sehen nur öffentliche Verfügbarkeit, keine Namen.
- **Kunde (eingeloggt):** eigene Buchungen anlegen/stornieren im erlaubten Fenster.
- **Mitglied:** wie Kunde + Kontingent-Logik.
- **Admin:** alles blocken/buchen (kostenfrei/bezahlt), Stornos <24h entscheiden,
  Gutschriften, Mitgliedschaften aktivieren/deaktivieren, Kundennamen in
  Tagesansicht sehen.
- **Mitarbeiter (später):** Teilmenge der Admin-Rechte (Abschnitt 10).
- **Trainer (Nick, eigene Instanz):** voller Admin auf seiner eigenen
  Trainer-Portal-Instanz, kein Zugriff auf Golfbox-Hauptinstanz.

## 7. Offene Punkte (aus Briefing Abschnitt 14 + technische Ergänzungen)

1. Genaue Freigabefrist für nicht gebuchte Trainer-Slots (3–6 Tage → finaler Wert).
2. AGB-Text (wird noch hochgeladen zur Prüfung/Einbindung).
3. Trackman-API-Anbindung – Rechercheergebnis offen; solange keine API-Details
   vorliegen, bleibt die Buchung unabhängig vom Trackman-System (kein Auto-Setup
   der Simulator-Session beim Buchen).
4. Zahlungsdienstleister mit echter Sammelrechnung – Rechercheergebnis offen;
   `PaymentProvider`-Interface hält beide Varianten (Sammelrechnung vs. manuelle
   Gebührenverbuchung) offen.
5. WhatsApp Business API – Anbieter/Setup später klären (Phase 3).
6. Quittungsnummerierung: fortlaufend – kalenderjahrbezogen oder komplett
   durchlaufend? (Relevant für Datev-Exportformat, mit Steuerberater klären.)
7. Genaue Vorausbuchungsregel für Mitglieder-Zusatzstunden (nur 3h-Grenze fürs
   Grundkontingent, oder auch für Zusatzstunden?).

## 8. Nicht-Ziele der MVP-Phase (bewusst ausgeklammert)

Zahlungsabwicklung, Guthaben/Rabatte, Storno-Gutschriften, Mitgliedschaften,
Preisregeln-UI, E-Mail-Versand, Zugangscode-System, Trainer-Portal als eigene
Instanz, Mehrsprachigkeit. Diese werden im Datenmodell bereits berücksichtigt
(s. Abschnitt 3), aber in der MVP-UI/-Logik nicht bedient, um Umfang und
Timeline (1. Oktober) realistisch zu halten.
