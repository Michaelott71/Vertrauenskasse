"""PDF-Erzeugung fuer Rechnungen und Quittungen mit Firmenlogo/Briefkopf.

Nutzt reportlab (reine Python-Bibliothek, keine System-Abhaengigkeiten wie
Pango/Cairo), damit das Deployment per Docker/Whitenoise unveraendert bleibt.
Die PDFs werden bei Abruf on-the-fly erzeugt statt als Datei abgelegt.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import Firmenprofil

_STYLES = getSampleStyleSheet()


def _briefkopf(elemente, firma: Firmenprofil):
    if firma.logo:
        try:
            elemente.append(Image(firma.logo.path, width=40 * mm, height=20 * mm))
        except (FileNotFoundError, OSError):
            pass
    kopf = f"<b>{firma.name}</b><br/>{firma.adresse.replace(chr(10), '<br/>')}"
    if firma.steuernummer:
        kopf += f"<br/>Steuernummer: {firma.steuernummer}"
    if firma.ust_idnr:
        kopf += f"<br/>USt-IdNr.: {firma.ust_idnr}"
    elemente.append(Paragraph(kopf, _STYLES["Normal"]))
    elemente.append(Spacer(1, 10 * mm))


def _fusszeile(elemente, firma: Firmenprofil):
    elemente.append(Spacer(1, 10 * mm))
    zeilen = []
    if firma.bank:
        zeilen.append(firma.bank)
    if firma.iban:
        zeilen.append(f"IBAN: {firma.iban}")
    if firma.bic:
        zeilen.append(f"BIC: {firma.bic}")
    if firma.rechnung_fusszeile:
        zeilen.append(firma.rechnung_fusszeile)
    if zeilen:
        elemente.append(Paragraph("<br/>".join(zeilen), _STYLES["Normal"]))


def rechnung_pdf(rechnung) -> bytes:
    firma = Firmenprofil.get_solo()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elemente = []

    _briefkopf(elemente, firma)

    elemente.append(Paragraph(f"Rechnung {rechnung.nummer}", _STYLES["Title"]))
    elemente.append(Paragraph(f"Datum: {rechnung.datum:%d.%m.%Y}", _STYLES["Normal"]))
    if rechnung.kunde_name:
        empfaenger = rechnung.kunde_name
        if rechnung.kunde_adresse:
            empfaenger += "<br/>" + rechnung.kunde_adresse.replace("\n", "<br/>")
        elemente.append(Spacer(1, 5 * mm))
        elemente.append(Paragraph(empfaenger, _STYLES["Normal"]))
    elemente.append(Spacer(1, 8 * mm))

    daten = [["Pos.", "Bezeichnung", "Menge", "Einzelpreis", "MwSt", "Netto"]]
    for i, position in enumerate(rechnung.positionen.all(), start=1):
        daten.append(
            [
                str(i),
                position.bezeichnung,
                f"{position.menge}",
                f"{position.einzelpreis:.2f} EUR",
                f"{position.mwst_satz}%",
                f"{position.netto_summe:.2f} EUR",
            ]
        )
    tabelle = Table(daten, colWidths=[12 * mm, 65 * mm, 20 * mm, 30 * mm, 18 * mm, 30 * mm])
    tabelle.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elemente.append(tabelle)
    elemente.append(Spacer(1, 6 * mm))

    summen = [["Netto-Summe", f"{rechnung.netto_summe:.2f} EUR"]]
    for satz, werte in rechnung.mwst_aufschluesselung.items():
        summen.append([f"zzgl. {satz}% MwSt", f"{werte['mwst']:.2f} EUR"])
    summen.append(["Gesamtbetrag", f"{rechnung.brutto_summe:.2f} EUR"])
    summentabelle = Table(summen, colWidths=[105 * mm, 30 * mm])
    summentabelle.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
            ]
        )
    )
    elemente.append(summentabelle)

    if rechnung.bezahlt:
        elemente.append(Spacer(1, 6 * mm))
        elemente.append(Paragraph("<b>Bezahlt</b>", _STYLES["Normal"]))

    _fusszeile(elemente, firma)

    doc.build(elemente)
    return buffer.getvalue()


def quittung_pdf(quittung) -> bytes:
    firma = Firmenprofil.get_solo()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elemente = []

    _briefkopf(elemente, firma)

    elemente.append(Paragraph(f"Quittung {quittung.nummer}", _STYLES["Title"]))
    elemente.append(Paragraph(f"Datum: {quittung.datum:%d.%m.%Y}", _STYLES["Normal"]))
    if quittung.name:
        elemente.append(Paragraph(f"Für: {quittung.name}", _STYLES["Normal"]))
    if quittung.verwendungszweck:
        elemente.append(
            Paragraph(f"Verwendungszweck: {quittung.verwendungszweck}", _STYLES["Normal"])
        )
    elemente.append(Spacer(1, 8 * mm))
    elemente.append(
        Paragraph(f"<b>Betrag: {quittung.betrag:.2f} EUR</b>", _STYLES["Normal"])
    )

    _fusszeile(elemente, firma)

    doc.build(elemente)
    return buffer.getvalue()
