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

from .models import Kassenbewegung, MonatsExport, PaypalZahlung, Zaehlung
from .services import berechne_auswertung, berechne_zeitraum, vorherige_zaehlung

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
    "Notiz",
]


def _euro(betrag: Decimal) -> str:
    betrag = Decimal(betrag).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{betrag:.2f}".replace(".", ",")


def _datum(d) -> str:
    return d.strftime("%d.%m.%Y")


def _brutto_zeile(
    datum, belegnummer, artikel, menge, brutto, zahlungsart, referenz="", notiz=""
):
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
        "Notiz": notiz,
    }


def _kassenbestand_zeile(datum, artikel, betrag, referenz=""):
    """Zeile fuer die Kassenbestand-Uebersicht (Anfangsbestand, einzelne
    Kassenbewegungen, Endbestand) - keine Umsatzzeile, deshalb Netto/USt
    leer und Zahlungsart klar als 'Kassenbestand' markiert, damit sie nicht
    versehentlich als Erloes mitgezaehlt wird."""
    return {
        "Datum": _datum(datum),
        "Belegnummer": "",
        "Artikel": artikel,
        "Menge": "",
        "Netto": "",
        "USt-Satz": "",
        "USt-Betrag": "",
        "Brutto": _euro(betrag),
        "Zahlungsart": "Kassenbestand",
        "Referenz": referenz,
        "Notiz": "",
    }


def _zaehlungen_im_monat(jahr, monat):
    return list(
        Zaehlung.objects.filter(datum__year=jahr, datum__month=monat).order_by(
            "datum", "id"
        )
    )


def erzeuge_zeilen(jahr, monat, aggregiert=False):
    """Baut die CSV-Zeilen fuer einen Monat. Gibt (zeilen, warnungen) zurueck."""
    zeilen = []  # Liste von (datum, zeile) zum Sortieren, roh vor der Formatierung
    warnungen = []
    zaehlungen = _zaehlungen_im_monat(jahr, monat)

    if aggregiert:
        ergebnis = berechne_zeitraum(zaehlungen)
        if ergebnis is not None and (
            ergebnis.soll_kasse or ergebnis.bar_anteil or ergebnis.kassendifferenz
        ):
            menge = sum(p.verkauft for p in ergebnis.positionen)
            letzte = zaehlungen[-1]
            notizen = "; ".join(z.notiz for z in zaehlungen if z.notiz)
            zeilen.append((
                letzte.datum,
                _brutto_zeile(
                    letzte.datum,
                    letzte.belegnummer,
                    "Getränke & Snacks (Sammelposten, Monat)",
                    menge,
                    ergebnis.bar_anteil,
                    "Bar",
                    notiz=notizen,
                ),
            ))
    else:
        for zaehlung in zaehlungen:
            ergebnis = berechne_auswertung(zaehlung)
            menge = sum(p.verkauft for p in ergebnis.positionen)
            if (
                ergebnis.soll_kasse
                or ergebnis.bar_anteil
                or ergebnis.kassendifferenz
                or zaehlung.notiz
            ):
                zeilen.append((
                    zaehlung.datum,
                    _brutto_zeile(
                        zaehlung.datum,
                        zaehlung.belegnummer,
                        "Getränke & Snacks (Sammelposten)",
                        menge,
                        ergebnis.bar_anteil,
                        "Bar",
                        notiz=zaehlung.notiz,
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
    umsatz_zeilen = [zeile for _, zeile in zeilen]

    kassenbestand_zeilen, kassenbestand_warnungen = _kassenbestand_zeilen(
        jahr, monat, zaehlungen
    )
    warnungen.extend(kassenbestand_warnungen)

    return umsatz_zeilen + kassenbestand_zeilen, warnungen


def _kassenbestand_zeilen(jahr, monat, zaehlungen):
    """Anfangsbestand, einzelne Kassenbewegungen und Endbestand des Monats -
    keine Erloese, sondern eine Nachvollziehbarkeits-Uebersicht, damit z.B.
    eine Einlage nicht spurlos verschwindet und der Kassenbestand sich von
    Monat zu Monat lueckenlos nachrechnen laesst."""
    zeilen = []
    warnungen = []
    if not zaehlungen:
        return zeilen, warnungen

    erste = zaehlungen[0]
    letzte = zaehlungen[-1]
    vorherige = vorherige_zaehlung(erste)
    anfangsbestand = (
        vorherige.bargeld_gezaehlt if vorherige and vorherige.bargeld_gezaehlt is not None else Decimal("0")
    )
    zeilen.append(_kassenbestand_zeile(erste.datum, "Anfangsbestand", anfangsbestand))

    for bewegung in Kassenbewegung.objects.filter(
        datum__year=jahr, datum__month=monat
    ).order_by("datum", "id"):
        zeilen.append(
            _kassenbestand_zeile(
                bewegung.datum,
                bewegung.get_art_display(),
                bewegung.betrag,
                referenz=bewegung.rg_nummer or bewegung.notiz,
            )
        )

    if letzte.bargeld_gezaehlt is None:
        warnungen.append(
            "Die letzte Zählung des Monats hat noch kein bestätigtes Bargeld - "
            "der Endbestand in der CSV ist deshalb unvollständig."
        )
    else:
        zeilen.append(
            _kassenbestand_zeile(letzte.datum, "Endbestand", letzte.bargeld_gezaehlt)
        )

    return zeilen, warnungen


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
