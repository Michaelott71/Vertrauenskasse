"""Automatische Zuordnung von PayPal-Zahlungen zur Vertrauenskasse.

Prueft in dieser Reihenfolge (erste passende Regel gewinnt):

1. Fester Verwendungszweck "Getraenke Golfbox" (eigener QR-Code) -> Vertrauenskasse
2. RG-Nummer im Betreff (Ausgangsrechnung) -> KEINE Vertrauenskasse
3. Stichwortliste (erweiterbar, siehe PaypalStichwort) -> Vertrauenskasse
4. Betragsregel: kleiner Betrag ohne Rechnungsnummer, passend zu einem
   Getraenke-/Snackpreis oder einem Vielfachen davon -> "vermutlich Vertrauenskasse"
5. Alles andere -> unklar, auf die Klaerungsliste (einmal monatlich manuell entscheiden)

Ergebnis wird nie automatisch auf True/False fuer den unklaren/vermutlich-Fall
gesetzt (bleibt `None`), damit die vorgeschriebene monatliche manuelle
Entscheidung erhalten bleibt. Nur Regel 1 und 2 sind eindeutig genug fuer eine
automatische Entscheidung.
"""

import re
from decimal import Decimal

from .models import Getraenk, PaypalStichwort, PaypalZahlung

FESTER_VERWENDUNGSZWECK = "getränke golfbox"
RG_MUSTER = re.compile(r"\brg[-\s]?\d+\b|rechnungs-?nr\.?|rechnungsnummer", re.IGNORECASE)

# Toleranz beim Preisabgleich fuer Rundungsdifferenzen in PayPal-Betraegen.
BETRAG_TOLERANZ = Decimal("0.01")
MAX_VIELFACHES = 20


def _normalisiert(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _passt_zu_getraenkepreisen(betrag: Decimal) -> bool:
    if betrag <= 0:
        return False
    preise = list(
        Getraenk.objects.filter(aktiv=True).values_list("verkaufspreis", flat=True)
    )
    for preis in preise:
        if preis <= 0:
            continue
        for vielfaches in range(1, MAX_VIELFACHES + 1):
            ziel = preis * vielfaches
            if abs(ziel - betrag) <= BETRAG_TOLERANZ:
                return True
            if ziel > betrag + BETRAG_TOLERANZ:
                break
    return False


def ordne_zahlung_zu(zahlung: PaypalZahlung) -> None:
    """Setzt ist_getraenke_zahlung und zuordnungsgrund anhand der Regeln oben.
    Speichert die Zahlung nicht selbst (der Aufrufer entscheidet, wann)."""
    zweck = _normalisiert(zahlung.verwendungszweck)

    if zweck == FESTER_VERWENDUNGSZWECK:
        zahlung.ist_getraenke_zahlung = True
        zahlung.zuordnungsgrund = "Fester Verwendungszweck 'Getränke Golfbox'"
        return

    if RG_MUSTER.search(zahlung.verwendungszweck or ""):
        zahlung.ist_getraenke_zahlung = False
        zahlung.zuordnungsgrund = "RG-Nummer im Betreff (Ausgangsrechnung)"
        return

    stichworte = list(PaypalStichwort.objects.values_list("wort", flat=True))
    for stichwort in stichworte:
        if _normalisiert(stichwort) and _normalisiert(stichwort) in zweck:
            zahlung.ist_getraenke_zahlung = True
            zahlung.zuordnungsgrund = f"Stichwort '{stichwort}' im Betreff"
            return

    if _passt_zu_getraenkepreisen(zahlung.betrag):
        zahlung.ist_getraenke_zahlung = None
        zahlung.zuordnungsgrund = (
            "Vermutlich Vertrauenskasse (Betrag passt zu Getränke-/Snackpreisen) "
            "- bitte beim Monatsabgleich bestaetigen"
        )
        return

    zahlung.ist_getraenke_zahlung = None
    zahlung.zuordnungsgrund = "Unklar - auf Klärungsliste, bitte manuell entscheiden"


def klaerungsliste():
    """Alle noch nicht entschiedenen PayPal-Zahlungen (fuer den monatlichen Abgleich)."""
    return PaypalZahlung.objects.filter(ist_getraenke_zahlung__isnull=True).order_by(
        "datum"
    )


def ordne_zaehlung_zu(zahlung: PaypalZahlung):
    """Ordnet eine als Vertrauenskasse-Zahlung entschiedene PayPal-Zahlung anhand
    ihres Datums rueckwirkend der ersten Zaehlung zu, deren Datum auf oder nach
    dem Zahlungsdatum liegt (die Zaehlung, bei der die Kasse fuer diesen Zeitraum
    'abgerechnet' wird)."""
    from .models import Zaehlung

    return (
        Zaehlung.objects.filter(datum__gte=zahlung.datum).order_by("datum", "id").first()
    )


def entscheide_manuell(zahlung: PaypalZahlung, ist_getraenke_zahlung: bool, kommentar: str = "") -> None:
    """Wird beim monatlichen Abgleich fuer eine Zahlung von der Klaerungsliste
    aufgerufen. Setzt die Entscheidung, ordnet bei True die passende Zaehlung zu
    und merkt sich den Betreff als Stichwort, damit ein wiederkehrender Betreff
    beim naechsten Mal automatisch erkannt wird."""
    zahlung.ist_getraenke_zahlung = ist_getraenke_zahlung
    zahlung.zuordnungsgrund = kommentar or "Manuell entschieden beim Monatsabgleich"
    if ist_getraenke_zahlung:
        zahlung.zaehlung = ordne_zaehlung_zu(zahlung)
    zahlung.save()

    if ist_getraenke_zahlung and zahlung.verwendungszweck.strip():
        PaypalStichwort.objects.get_or_create(wort=zahlung.verwendungszweck.strip())
