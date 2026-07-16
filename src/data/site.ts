// Zentrale Kontakt-/Konfigurationsdaten. Platzhalter mit "TODO" bitte durch echte Daten ersetzen.

export const site = {
  name: 'Majors Golfbox',
  domain: 'https://majorsgolfbox.de',

  // TODO: echte Buchungsportal-URL eintragen, sobald verfügbar
  bookingUrl: 'https://booking.majorsgolfbox.de',

  contact: {
    // TODO: echte Telefonnummer eintragen
    phoneDisplay: '+49 (0) 00 000 00000',
    phoneHref: 'tel:+490000000000',
    // TODO: echte WhatsApp-Business-Nummer eintragen (internationales Format ohne + oder Leerzeichen)
    whatsappNumber: '490000000000',
    // TODO: echte E-Mail-Adresse eintragen
    email: 'info@majorsgolfbox.de',
  },

  // Google-Bewertungen
  reviews: {
    count: 41,
    rating: 5,
    url: 'https://g.page/r/CX6XPYEZx-q-EAE/review',
  },

  // Tracking – IDs erst eintragen, wenn GTM/GA4-Container final eingerichtet sind
  tracking: {
    // TODO: GTM-Container-ID eintragen, z. B. "GTM-XXXXXXX"
    gtmId: '',
  },

  // Optionaler Produkte-Bereich – auf true setzen, sobald Inhalte vorliegen
  showProducts: false,
} as const;
