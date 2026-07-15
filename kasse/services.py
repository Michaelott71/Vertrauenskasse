"""Rechenlogik der Vertrauenskasse: Soll/Ist-Kassenvergleich und Leergut-Abgleich
zwischen zwei Zaehlungen.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

from .models import (
    BelegPosition,
    Freigetraenk,
    Getraenk,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
)


class AuswertungError(Exception):
    """Wird ausgeloest, wenn zwischen zwei Zaehlungen nicht sinnvoll gerechnet werden kann."""


@dataclass
class GetraenkAuswertung:
    getraenk: Getraenk
    vollbestand_start: int
    vollbestand_ende: int
    nachschub: int
    freigetraenke: int
    verkauft: int
    verkaufspreis: Decimal
    soll_kasse: Decimal
    leergut_start: int
    leergut_ende: int
    rueckgabe_an_getraenkemarkt: int
    erwartetes_leergut: int
    leergut_differenz: int


@dataclass
class Auswertung:
    start: Zaehlung
    ende: Zaehlung
    positionen: list = field(default_factory=list)
    soll_kasse: Decimal = Decimal("0")
    bargeld_einnahmen: Decimal = Decimal("0")
    bargeld_entnommen_zwischenzeitlich: Decimal = Decimal("0")
    paypal_getraenke: Decimal = Decimal("0")
    ist_kasse: Decimal = Decimal("0")
    kassendifferenz: Decimal = Decimal("0")
    leergut_differenz_gesamt: int = 0


def _zaehlungen_im_zeitraum(start: Zaehlung, ende: Zaehlung):
    """Alle Zaehlungen zwischen start und ende (chronologisch), inkl. beider Enden."""
    return list(
        Zaehlung.objects.filter(
            datum__gte=start.datum, datum__lte=ende.datum
        ).order_by("datum", "id")
    )


def berechne_auswertung(start: Zaehlung, ende: Zaehlung) -> Auswertung:
    """Berechnet Soll/Ist-Kasse und Leergut-Differenz fuer den Zeitraum zwischen
    zwei Zaehlungen (start -> ende), je Getraenk und als Gesamtsumme.

    Beruecksichtigt dabei auch Zaehlungen, die zeitlich zwischen start und ende
    liegen (z.B. bei einer Monatsauswertung ueber mehrere Zaehlungen hinweg):
    zwischenzeitliche Leergut-Rueckgaben, Bargeld-Entnahmen und PayPal-Zahlungen
    fliessen mit ein, statt nur die Werte der End-Zaehlung zu betrachten.
    """
    if start.id == ende.id:
        raise AuswertungError("Start- und End-Zaehlung duerfen nicht identisch sein.")
    if start.datum > ende.datum:
        raise AuswertungError(
            "Die Start-Zaehlung muss vor (oder am selben Tag wie) der End-Zaehlung liegen."
        )

    zeitraum = _zaehlungen_im_zeitraum(start, ende)
    start_index = next(i for i, z in enumerate(zeitraum) if z.id == start.id)
    ende_index = next(i for i, z in enumerate(zeitraum) if z.id == ende.id)
    if start_index >= ende_index:
        raise AuswertungError(
            "Die Start-Zaehlung muss vor (oder am selben Tag wie) der End-Zaehlung liegen."
        )
    zwischentermine = zeitraum[start_index + 1 : ende_index]
    # Zaehlungen, deren Rueckgaben/PayPal-Zahlungen in diesen Zeitraum faellen
    # (alles nach start, bis inkl. ende).
    perioden_zaehlungen = zwischentermine + [ende]

    start_bestaende = {
        b.getraenk_id: b for b in ZaehlungBestand.objects.filter(zaehlung=start)
    }
    ende_bestaende = {
        b.getraenk_id: b for b in ZaehlungBestand.objects.filter(zaehlung=ende)
    }
    getraenk_ids = set(start_bestaende) | set(ende_bestaende)
    getraenke = {g.id: g for g in Getraenk.objects.filter(id__in=getraenk_ids)}

    nachschub_je_getraenk = dict(
        BelegPosition.objects.filter(
            beleg__datum__gt=start.datum,
            beleg__datum__lte=ende.datum,
            getraenk_id__in=getraenk_ids,
        )
        .values("getraenk_id")
        .annotate(summe=Sum("anzahl"))
        .values_list("getraenk_id", "summe")
    )
    freigetraenke_je_getraenk = dict(
        Freigetraenk.objects.filter(
            datum__gt=start.datum,
            datum__lte=ende.datum,
            getraenk_id__in=getraenk_ids,
        )
        .values("getraenk_id")
        .annotate(summe=Sum("anzahl"))
        .values_list("getraenk_id", "summe")
    )
    rueckgabe_je_getraenk = dict(
        ZaehlungBestand.objects.filter(
            zaehlung__in=[z.id for z in perioden_zaehlungen],
            getraenk_id__in=getraenk_ids,
        )
        .values("getraenk_id")
        .annotate(summe=Sum("rueckgabe_an_getraenkemarkt"))
        .values_list("getraenk_id", "summe")
    )

    auswertung = Auswertung(start=start, ende=ende)

    for getraenk_id in sorted(getraenke, key=lambda gid: getraenke[gid].name.lower()):
        getraenk = getraenke[getraenk_id]
        start_b = start_bestaende.get(getraenk_id)
        ende_b = ende_bestaende.get(getraenk_id)

        vollbestand_start = start_b.vollbestand_gezaehlt if start_b else 0
        leergut_start = start_b.leergut_gezaehlt if start_b else 0
        vollbestand_ende = ende_b.vollbestand_gezaehlt if ende_b else 0
        leergut_ende = ende_b.leergut_gezaehlt if ende_b else 0
        rueckgabe = rueckgabe_je_getraenk.get(getraenk_id, 0)

        nachschub = nachschub_je_getraenk.get(getraenk_id, 0)
        freigetraenke = freigetraenke_je_getraenk.get(getraenk_id, 0)

        verkauft = vollbestand_start + nachschub - vollbestand_ende - freigetraenke
        soll_kasse_i = verkauft * getraenk.verkaufspreis

        erwartetes_leergut = leergut_start + verkauft - rueckgabe
        leergut_differenz = leergut_ende - erwartetes_leergut

        auswertung.positionen.append(
            GetraenkAuswertung(
                getraenk=getraenk,
                vollbestand_start=vollbestand_start,
                vollbestand_ende=vollbestand_ende,
                nachschub=nachschub,
                freigetraenke=freigetraenke,
                verkauft=verkauft,
                verkaufspreis=getraenk.verkaufspreis,
                soll_kasse=soll_kasse_i,
                leergut_start=leergut_start,
                leergut_ende=leergut_ende,
                rueckgabe_an_getraenkemarkt=rueckgabe,
                erwartetes_leergut=erwartetes_leergut,
                leergut_differenz=leergut_differenz,
            )
        )
        auswertung.soll_kasse += soll_kasse_i
        auswertung.leergut_differenz_gesamt += leergut_differenz

    # Bargeld-Einnahmen im Zeitraum: Endstand minus das, was nach der
    # Start-Zaehlung noch in der Kasse verblieben ist (gezaehlt minus dort
    # bereits entnommen), plus alles, was bei zwischenzeitlichen Zaehlungen
    # entnommen wurde (das war ebenfalls im Zeitraum eingenommenes Geld).
    start_rest = (start.bargeld_gezaehlt or Decimal("0")) - (
        start.bargeld_entnommen or Decimal("0")
    )
    zwischen_entnahmen = sum(
        (z.bargeld_entnommen or Decimal("0") for z in zwischentermine), Decimal("0")
    )
    auswertung.bargeld_entnommen_zwischenzeitlich = zwischen_entnahmen
    auswertung.bargeld_einnahmen = (
        (ende.bargeld_gezaehlt or Decimal("0")) - start_rest + zwischen_entnahmen
    )

    paypal_summe = PaypalZahlung.objects.filter(
        zaehlung_id__in=[z.id for z in perioden_zaehlungen], ist_getraenke_zahlung=True
    ).aggregate(summe=Sum("betrag"))["summe"]
    auswertung.paypal_getraenke = paypal_summe or Decimal("0")
    auswertung.ist_kasse = auswertung.bargeld_einnahmen + auswertung.paypal_getraenke
    auswertung.kassendifferenz = auswertung.ist_kasse - auswertung.soll_kasse

    return auswertung
