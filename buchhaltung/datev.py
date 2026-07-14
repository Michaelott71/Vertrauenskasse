"""DATEV-Export (Buchungsstapel, Format 700/Kategorie 21) fuer die Uebergabe
an den Steuerberater.

WICHTIG: Kontenrahmen (SKR03 vs. SKR04) und die genaue Konto-Zuordnung sind
laut Spezifikation noch offene Punkte. ``KONTENRAHMEN_MAPPING`` unten enthaelt
daher nur ueblicherweise verwendete Platzhalter-Kontonummern (z.B. Erloeskonten
je MwSt-Satz, Bankkonto, Aufwandskonto fuer Zahlungsdienstleister-Gebuehren).
Diese Zuordnung sowie die Stammdaten in der Kopfzeile (Berater-/Mandanten-
nummer, Wirtschaftsjahr-Beginn) muessen vor dem produktiven Einsatz mit dem
Steuerberater abgestimmt und ueber Umgebungsvariablen/Firmenprofil final
gesetzt werden.
"""

import csv
import os
from datetime import date
from io import StringIO

KONTENRAHMEN_MAPPING = {
    "SKR03": {
        "erloes_19": "8400",
        "erloes_7": "8300",
        "erloes_0": "8200",
        "bank": "1200",
        "gebuehren_aufwand": "4970",
    },
    "SKR04": {
        "erloes_19": "4400",
        "erloes_7": "4300",
        "erloes_0": "4200",
        "bank": "1800",
        "gebuehren_aufwand": "6855",
    },
}


def _erloeskonto(mapping, mwst_satz):
    schluessel = f"erloes_{int(mwst_satz)}"
    return mapping.get(schluessel, mapping["erloes_19"])


def baue_datev_buchungsstapel(
    rechnungen,
    gebuehren,
    kontenrahmen: str,
    datum_von: date,
    datum_bis: date,
    erzeugt_am=None,
) -> str:
    """Erzeugt den Inhalt einer DATEV-EXTF-CSV-Datei fuer die uebergebenen
    Rechnungen (je MwSt-Satz eine Buchungszeile) und Zahlungsdienstleister-
    Gebuehren (separater Aufwandsposten, siehe Spezifikation).
    """
    mapping = KONTENRAHMEN_MAPPING.get(kontenrahmen, KONTENRAHMEN_MAPPING["SKR03"])
    erzeugt_am = erzeugt_am or date.today()

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_NONNUMERIC)

    beraternummer = os.environ.get("DATEV_BERATERNUMMER", "")
    mandantennummer = os.environ.get("DATEV_MANDANTENNUMMER", "")
    wj_beginn = os.environ.get("DATEV_WJ_BEGINN", f"{datum_von.year}0101")

    writer.writerow(
        [
            "EXTF",
            700,
            21,
            "Buchungsstapel",
            13,
            erzeugt_am.strftime("%Y%m%d%H%M%S000"),
            "",
            "RE",
            "",
            "",
            beraternummer,
            mandantennummer,
            wj_beginn,
            4,
            datum_von.strftime("%Y%m%d"),
            datum_bis.strftime("%Y%m%d"),
            "",
            "",
            1,
            0,
            0,
            "EUR",
        ]
    )
    writer.writerow(
        [
            "Umsatz (ohne Soll/Haben-Kz)",
            "Soll/Haben-Kennzeichen",
            "Konto",
            "Gegenkonto (ohne BU-Schluessel)",
            "BU-Schluessel",
            "Belegdatum",
            "Belegfeld 1",
            "Buchungstext",
        ]
    )

    for rechnung in rechnungen:
        for satz, werte in rechnung.mwst_aufschluesselung.items():
            brutto = werte["netto"] + werte["mwst"]
            if brutto == 0:
                continue
            writer.writerow(
                [
                    f"{brutto:.2f}".replace(".", ","),
                    "S",
                    mapping["bank"],
                    _erloeskonto(mapping, satz),
                    "",
                    rechnung.datum.strftime("%d%m"),
                    rechnung.nummer,
                    f"Rechnung {rechnung.nummer} ({satz}% MwSt)",
                ]
            )

    for gebuehr in gebuehren:
        beleg = gebuehr.rechnung.nummer if gebuehr.rechnung_id else gebuehr.quittung.nummer
        writer.writerow(
            [
                f"{gebuehr.gebuehr:.2f}".replace(".", ","),
                "S",
                mapping["gebuehren_aufwand"],
                mapping["bank"],
                "",
                gebuehr.datum.strftime("%d%m"),
                beleg,
                f"Zahlungsdienstleister-Gebuehr {gebuehr.anbieter}".strip(),
            ]
        )

    return buffer.getvalue()
