"""Monatsexport als CSV im vorgeschriebenen Format.

Eine Zeile pro Zaehlungszeitraum (Bar, aggregiert ueber alle Artikel - siehe
README fuer die Begruendung dieser Vereinfachung) plus eine Zeile je
zugeordneter PayPal-Zahlung (damit jede ihre eigene Referenz/Transaktions-ID
behaelt). Optional komplett auf eine einzige Bar-Zeile fuer den ganzen Monat
aggregierbar (`aggregiert=True`).
"""

import csv
import io
from decimal import ROUND_HALF_UP, Decimal

from .models import MonatsExport, PaypalZahlung, Zaehlung
from .services import AuswertungError, berechne_auswertung

USt_SATZ = Decimal("19")
CSV_SPALTEN = [
    "Datum",
    "Belegnummer",
    "Artikel",
    "Menge",
    "Netto",
    "USt-Satz",
    "USt-Betrag",
    "Brutto",
    "Zahlungsart",
    "Referenz",
]


def _euro(betrag: Decimal) -> str:
    betrag = Decimal(betrag).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{betrag:.2f}".replace(".", ",")


def _datum(d) -> str:
    return d.strftime("%d.%m.%Y")


def _brutto_zeile(datum, belegnummer, artikel, menge, brutto, zahlungsart, referenz=""):
    brutto = Decimal(brutto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    netto = (brutto / (1 + USt_SATZ / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ust_betrag = brutto - netto
    return {
        "Datum": _datum(datum),
        "Belegnummer": belegnummer,
        "Artikel": artikel,
        "Menge": menge,
        "Netto": _euro(netto),
        "USt-Satz": f"{USt_SATZ:.0f}%",
        "USt-Betrag": _euro(ust_betrag),
        "Brutto": _euro(brutto),
        "Zahlungsart": zahlungsart,
        "Referenz": referenz,
    }


def _zaehlungen_im_monat(jahr, monat):
    return list(
        Zaehlung.objects.filter(datum__year=jahr, datum__month=monat).order_by(
            "datum", "id"
        )
    )


def _vorherige_zaehlung(zaehlung):
    return (
        Zaehlung.objects.filter(datum__lt=zaehlung.datum)
        .order_by("-datum", "-id")
        .first()
    )


def erzeuge_zeilen(jahr, monat, aggregiert=False):
    """Baut die CSV-Zeilen fuer einen Monat. Gibt (zeilen, warnungen) zurueck."""
    zeilen = []  # Liste von (datum, zeile) zum Sortieren, roh vor der Formatierung
    warnungen = []
    zaehlungen = _zaehlungen_im_monat(jahr, monat)

    if aggregiert:
        if len(zaehlungen) >= 1:
            start = _vorherige_zaehlung(zaehlungen[0])
            ende = zaehlungen[-1]
            if start is None:
                warnungen.append(
                    "Keine vorherige Zaehlung vor dem Monat gefunden - Monatsanfang "
                    "kann nicht berechnet werden."
                )
            else:
                try:
                    ergebnis = berechne_auswertung(start, ende)
                except AuswertungError as exc:
                    warnungen.append(str(exc))
                else:
                    menge = sum(p.verkauft for p in ergebnis.positionen)
                    if ergebnis.bar_anteil:
                        zeilen.append((
                            ende.datum,
                            _brutto_zeile(
                                ende.datum,
                                ende.belegnummer,
                                "Getränke & Snacks (Sammelposten, Monat)",
                                menge,
                                ergebnis.bar_anteil,
                                "Bar",
                            ),
                        ))
    else:
        for zaehlung in zaehlungen:
            start = _vorherige_zaehlung(zaehlung)
            if start is None:
                warnungen.append(
                    f"{zaehlung.belegnummer}: keine vorherige Zaehlung gefunden, "
                    "wird im Export uebersprungen."
                )
                continue
            try:
                ergebnis = berechne_auswertung(start, zaehlung)
            except AuswertungError as exc:
                warnungen.append(f"{zaehlung.belegnummer}: {exc}")
                continue
            menge = sum(p.verkauft for p in ergebnis.positionen)
            if ergebnis.bar_anteil:
                zeilen.append((
                    zaehlung.datum,
                    _brutto_zeile(
                        zaehlung.datum,
                        zaehlung.belegnummer,
                        "Getränke & Snacks (Sammelposten)",
                        menge,
                        ergebnis.bar_anteil,
                        "Bar",
                    ),
                ))

    zaehlung_ids_im_monat = Zaehlung.objects.filter(
        datum__year=jahr, datum__month=monat
    ).values_list("id", flat=True)

    for zahlung in PaypalZahlung.objects.filter(
        zaehlung_id__in=list(zaehlung_ids_im_monat),
        ist_getraenke_zahlung=True,
        datum__year=jahr,
        datum__month=monat,
    ).order_by("datum", "id"):
        zeilen.append((
            zahlung.datum,
            _brutto_zeile(
                zahlung.datum,
                zahlung.zaehlung.belegnummer,
                "Getränke & Snacks (PayPal)",
                1,
                zahlung.betrag,
                "PayPal",
                referenz=zahlung.paypal_transaktions_id,
            ),
        ))

    zeilen.sort(key=lambda paar: paar[0])
    return [zeile for _, zeile in zeilen], warnungen


def erzeuge_csv(jahr, monat, aggregiert=False):
    """Gibt (dateiname, csv_text, warnungen) fuer den Monatsexport zurueck."""
    zeilen, warnungen = erzeuge_zeilen(jahr, monat, aggregiert=aggregiert)

    puffer = io.StringIO()
    writer = csv.DictWriter(puffer, fieldnames=CSV_SPALTEN, delimiter=";")
    writer.writeheader()
    for zeile in zeilen:
        writer.writerow(zeile)

    dateiname = f"{jahr:04d}-{monat:02d}_Vertrauenskasse.csv"
    return dateiname, puffer.getvalue(), warnungen


def markiere_als_exportiert(jahr, monat):
    MonatsExport.objects.get_or_create(jahr=jahr, monat=monat)
