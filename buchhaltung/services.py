"""Geschaeftslogik der Buchhaltung, die ueber einfaches Feld-Mapping
hinausgeht: Gutschein-Einloesung mit Restguthaben-Pruefung.

Die fortlaufende Nummerierung von Rechnungen/Quittungen steckt bewusst in
``models.py`` (``Rechnung.save`` / ``Quittung.save``), da sie beim Speichern
jedes einzelnen Datensatzes greifen muss, auch wenn er direkt im Admin
angelegt wird.
"""

from datetime import date
from decimal import Decimal

from .models import Gutschein, GutscheinEinloesung, Quittung, Rechnung


class GutscheinError(Exception):
    """Wird ausgeloest, wenn ein Gutschein nicht (mehr) eingeloest werden kann."""


def gutschein_einloesen(
    gutschein: Gutschein,
    betrag: Decimal,
    rechnung: Rechnung = None,
    quittung: Quittung = None,
    datum: date = None,
) -> GutscheinEinloesung:
    """Loest einen Gutschein (teilweise) gegen eine Rechnung oder Quittung ein.

    Prueft Ablaufdatum und - bei Gutscheinen mit festem Betrag - dass die
    Einloesung das Restguthaben nicht uebersteigt. Prozentuale Gutscheine
    gelten je Einloesung als vollstaendig verwendet (siehe
    ``Gutschein.restguthaben``) und koennen daher kein zweites Mal eingeloest
    werden.
    """
    if bool(rechnung) == bool(quittung):
        raise GutscheinError(
            "Eine Gutschein-Einloesung muss genau einer Rechnung oder einer "
            "Quittung zugeordnet werden."
        )
    if gutschein.ist_abgelaufen:
        raise GutscheinError(f"Gutschein {gutschein.code} ist abgelaufen.")
    if betrag <= 0:
        raise GutscheinError("Der Einloesungsbetrag muss positiv sein.")

    if gutschein.typ == Gutschein.TYP_FEST:
        if betrag > gutschein.restguthaben:
            raise GutscheinError(
                f"Gutschein {gutschein.code} hat nur noch "
                f"{gutschein.restguthaben} EUR Restguthaben."
            )
    elif gutschein.einloesungen.exists():
        raise GutscheinError(
            f"Prozentualer Gutschein {gutschein.code} wurde bereits eingeloest."
        )

    return GutscheinEinloesung.objects.create(
        gutschein=gutschein,
        rechnung=rechnung,
        quittung=quittung,
        betrag=betrag,
        datum=datum or date.today(),
    )
