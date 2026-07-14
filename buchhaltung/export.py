"""CSV- und Excel-Export der Monatsliste fuer die Uebergabe an den
Steuerberater bzw. zur eigenen Ablage.
"""

import csv
from io import BytesIO, StringIO

from openpyxl import Workbook

SPALTEN = [
    "Nummer",
    "Datum",
    "Kunde",
    "Netto",
    "MwSt",
    "Brutto",
    "Bezahlt",
    "Bezahlt am",
    "Konto",
]


def _zeile(rechnung):
    return [
        rechnung.nummer,
        rechnung.datum.isoformat(),
        rechnung.kunde_name,
        f"{rechnung.netto_summe:.2f}",
        f"{rechnung.mwst_gesamt:.2f}",
        f"{rechnung.brutto_summe:.2f}",
        "ja" if rechnung.bezahlt else "nein",
        rechnung.bezahlt_am.isoformat() if rechnung.bezahlt_am else "",
        rechnung.konto.bezeichnung if rechnung.konto else "",
    ]


def rechnungen_als_csv(rechnungen) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(SPALTEN)
    for rechnung in rechnungen:
        writer.writerow(_zeile(rechnung))
    return buffer.getvalue()


def rechnungen_als_xlsx(rechnungen) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rechnungen"
    sheet.append(SPALTEN)
    for rechnung in rechnungen:
        sheet.append(_zeile(rechnung))

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
