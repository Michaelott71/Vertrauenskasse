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
    Pfandkategorie,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
    ZaehlungLeergut,
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


@dataclass
class LeergutAuswertung:
    pfandkategorie: Pfandkategorie
    leergut_start: int
    leergut_ende: int
    verkauft_gesamt: int
    rueckgabe_an_getraenkemarkt: int
    erwartetes_leergut: int
    leergut_differenz: int


@dataclass
class Auswertung:
    start: Zaehlung
    ende: Zaehlung
    positionen: list = field(default_factory=list)
    leergut_positionen: list = field(default_factory=list)
    soll_kasse: Decimal = Decimal("0")
    bar_anteil: Decimal = Decimal("0")
    paypal_anteil: Decimal = Decimal("0")
    ist_kasse: Decimal = Decimal("0")
    kassendifferenz: Decimal = Decimal("0")
    vorlaeufig: bool = False
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
    zwei Zaehlungen (start -> ende), je Getraenk/Pfandkategorie und als Gesamtsumme.

    Beruecksichtigt dabei auch Zaehlungen, die zeitlich zwischen start und ende
    liegen (z.B. bei einer Monatsauswertung ueber mehrere Zaehlungen hinweg):
    zwischenzeitliche Leergut-Rueckgaben fliessen mit ein, statt nur die Werte
    der End-Zaehlung zu betrachten.
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
    perioden_zaehlung_ids = [z.id for z in perioden_zaehlungen]

    start_bestaende = {
        b.getraenk_id: b for b in ZaehlungBestand.objects.filter(zaehlung=start)
    }
    ende_bestaende = {
        b.getraenk_id: b for b in ZaehlungBestand.objects.filter(zaehlung=ende)
    }
    getraenk_ids = set(start_bestaende) | set(ende_bestaende)
    getraenke = {
        g.id: g
        for g in Getraenk.objects.filter(id__in=getraenk_ids).select_related(
            "pfandkategorie"
        )
    }

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

    auswertung = Auswertung(start=start, ende=ende)
    verkauft_je_kategorie: dict = {}

    for getraenk_id in sorted(getraenke, key=lambda gid: getraenke[gid].name.lower()):
        getraenk = getraenke[getraenk_id]
        start_b = start_bestaende.get(getraenk_id)
        ende_b = ende_bestaende.get(getraenk_id)

        vollbestand_start = start_b.vollbestand_gezaehlt if start_b else 0
        vollbestand_ende = ende_b.vollbestand_gezaehlt if ende_b else 0
        nachschub = nachschub_je_getraenk.get(getraenk_id, 0)
        freigetraenke = freigetraenke_je_getraenk.get(getraenk_id, 0)

        verkauft = vollbestand_start + nachschub - vollbestand_ende - freigetraenke
        soll_kasse_i = verkauft * getraenk.verkaufspreis

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
            )
        )
        auswertung.soll_kasse += soll_kasse_i

        if getraenk.pfandkategorie_id:
            verkauft_je_kategorie[getraenk.pfandkategorie_id] = (
                verkauft_je_kategorie.get(getraenk.pfandkategorie_id, 0) + verkauft
            )

    # Leergut je Pfandkategorie (eine Zahl fuer alle Artikel dieser Kategorie).
    start_leergut = {
        l.pfandkategorie_id: l
        for l in ZaehlungLeergut.objects.filter(zaehlung=start)
    }
    ende_leergut = {
        l.pfandkategorie_id: l
        for l in ZaehlungLeergut.objects.filter(zaehlung=ende)
    }
    kategorie_ids = (
        set(start_leergut) | set(ende_leergut) | set(verkauft_je_kategorie)
    )
    kategorien = {
        k.id: k for k in Pfandkategorie.objects.filter(id__in=kategorie_ids)
    }
    rueckgabe_je_kategorie = dict(
        ZaehlungLeergut.objects.filter(
            zaehlung_id__in=perioden_zaehlung_ids, pfandkategorie_id__in=kategorie_ids
        )
        .values("pfandkategorie_id")
        .annotate(summe=Sum("rueckgabe_an_getraenkemarkt"))
        .values_list("pfandkategorie_id", "summe")
    )

    for kategorie_id in sorted(
        kategorien, key=lambda kid: kategorien[kid].name.lower()
    ):
        kategorie = kategorien[kategorie_id]
        start_l = start_leergut.get(kategorie_id)
        ende_l = ende_leergut.get(kategorie_id)
        leergut_start = start_l.leergut_gezaehlt if start_l else 0
        leergut_ende = ende_l.leergut_gezaehlt if ende_l else 0
        verkauft_gesamt = verkauft_je_kategorie.get(kategorie_id, 0)
        rueckgabe = rueckgabe_je_kategorie.get(kategorie_id, 0)

        erwartetes_leergut = leergut_start + verkauft_gesamt - rueckgabe
        leergut_differenz = leergut_ende - erwartetes_leergut

        auswertung.leergut_positionen.append(
            LeergutAuswertung(
                pfandkategorie=kategorie,
                leergut_start=leergut_start,
                leergut_ende=leergut_ende,
                verkauft_gesamt=verkauft_gesamt,
                rueckgabe_an_getraenkemarkt=rueckgabe,
                erwartetes_leergut=erwartetes_leergut,
                leergut_differenz=leergut_differenz,
            )
        )
        auswertung.leergut_differenz_gesamt += leergut_differenz

    # Bar-Anteil: einfache Differenz des gezaehlten Bargelds zwischen den beiden
    # Zaehlungen (kein Geldabfluss ausser privaten Einlagen, siehe Beleg-Modell).
    auswertung.bar_anteil = (ende.bargeld_gezaehlt or Decimal("0")) - (
        start.bargeld_gezaehlt or Decimal("0")
    )

    paypal_im_zeitraum = PaypalZahlung.objects.filter(
        datum__gt=start.datum, datum__lte=ende.datum
    )
    paypal_summe = paypal_im_zeitraum.filter(
        zaehlung_id__in=perioden_zaehlung_ids, ist_getraenke_zahlung=True
    ).aggregate(summe=Sum("betrag"))["summe"]
    auswertung.paypal_anteil = paypal_summe or Decimal("0")
    auswertung.vorlaeufig = paypal_im_zeitraum.filter(
        ist_getraenke_zahlung__isnull=True
    ).exists()

    auswertung.ist_kasse = auswertung.bar_anteil + auswertung.paypal_anteil
    auswertung.kassendifferenz = auswertung.ist_kasse - auswertung.soll_kasse

    return auswertung
