// Preisstruktur – Platzhalterwerte. TODO: mit echten Preisen von Majors Golfbox ersetzen.

export interface PricingPlan {
  id: string;
  nameKey: string;
  priceDe: string;
  priceEn: string;
  descriptionKeyDe: string;
  descriptionKeyEn: string;
  highlight?: boolean;
}

export const hourlyRates: PricingPlan[] = [
  {
    id: 'hourly-off-peak',
    nameKey: 'Nebenzeit',
    priceDe: 'ab 25 € / Stunde',
    priceEn: 'from €25 / hour',
    descriptionKeyDe: 'Montag–Freitag, 09:00–17:00 Uhr',
    descriptionKeyEn: 'Monday–Friday, 9am–5pm',
  },
  {
    id: 'hourly-peak',
    nameKey: 'Hauptzeit',
    priceDe: 'ab 35 € / Stunde',
    priceEn: 'from €35 / hour',
    descriptionKeyDe: 'Abende & Wochenende',
    descriptionKeyEn: 'Evenings & weekends',
  },
];

export const membershipPlans: PricingPlan[] = [
  {
    id: 'single-session',
    nameKey: 'Einzelstunde',
    priceDe: 'ab 25 €',
    priceEn: 'from €25',
    descriptionKeyDe: 'Flexibel, ohne Bindung',
    descriptionKeyEn: 'Flexible, no commitment',
  },
  {
    id: 'ten-pack',
    nameKey: '10er-Karte',
    priceDe: 'ab 220 €',
    priceEn: 'from €220',
    descriptionKeyDe: '10 Stunden, 12 Monate gültig',
    descriptionKeyEn: '10 hours, valid 12 months',
    highlight: true,
  },
  {
    id: 'monthly',
    nameKey: 'Monats-Flatrate',
    priceDe: 'ab 149 € / Monat',
    priceEn: 'from €149 / month',
    descriptionKeyDe: 'Unbegrenzt spielen, monatlich kündbar',
    descriptionKeyEn: 'Unlimited play, cancel monthly',
  },
];
