"""Rechenlogik der Vertrauenskasse: Soll/Ist-Kassenvergleich.

Jede Zaehlung traegt direkt den Verbrauch je Artikel seit der letzten Zaehlung
(kein Bestand wird gezaehlt/verglichen). Eine Auswertung ist deshalb pro
Zaehlung immer sofort berechenbar, auch fuer die allererste.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum

from .models import (
    Beleg,
    BelegPosition,
    Freigetraenk,
    Getraenk,
    Kassenbewegung,
    PaypalZahlung,
    Zaehlung,
    ZaehlungVerbrauch,
)


@dataclass
class GetraenkAuswertung:
    getraenk: Getraenk
    verbraucht: int
    freigetraenke: int
    verkauft: int
    verkaufspreis: Decimal
    soll_kasse: Decimal


@dataclass
class Auswertung:
    zaehlung: Zaehlung
    vorherige: Zaehlung | None = None
    positionen: list = field(default_factory=list)
    soll_kasse: Decimal = Decimal("0")
    bargeld_differenz: Decimal = Decimal("0")
    einlagen: Decimal = Decimal("0")
    entnahmen: Decimal = Decimal("0")
    fremde_bargeldeingaenge: Decimal = Decimal("0")
    kassenbewegungen: list = field(default_factory=list)
    netto_kassenbewegungen: Decimal = Decimal("0")
    bar_anteil: Decimal = Decimal("0")
    paypal_anteil: Decimal = Decimal("0")
    ist_kasse: Decimal = Decimal("0")
    kassendifferenz: Decimal = Decimal("0")
    vorlaeufig: bool = False
    freigetraenke_wert: Decimal = Decimal("0")
    belege: list = field(default_factory=list)
    einkaufswert: Decimal = Decimal("0")
    bargeld_vorschlag: Decimal = Decimal("0")


def vorherige_zaehlung(zaehlung: Zaehlung):
    """Die zeitlich unmittelbar vorangehende Zaehlung (chronologisch nach
    Datum, bei gleichem Datum nach id), oder None, wenn `zaehlung` die
    allererste ist."""
    return (
        Zaehlung.objects.filter(
            Q(datum__lt=zaehlung.datum)
            | Q(datum=zaehlung.datum, id__lt=zaehlung.id)
        )
        .order_by("-datum", "-id")
        .first()
    )


def _im_zeitraum(queryset, vorherige, zaehlung):
    """Schraenkt eine Queryset (Modell braucht `datum` und `erstellt_am`) auf
    den Zeitraum zwischen `vorherige` (exklusiv) und `zaehlung` (inklusiv)
    ein. Bei gleichem Kalendertag wie eine der beiden Zaehlungen entscheidet
    zusaetzlich die Erfassungsreihenfolge (`erstellt_am`) - sonst liesse sich
    z.B. eine Kassenbewegung, die erst NACH einer bereits bestaetigten
    Zaehlung am selben Tag gebucht wird, nicht von einer vor dieser Zaehlung
    unterscheiden und wuerde faelschlich deren (schon abgeschlossenes)
    Ergebnis rueckwirkend veraendern."""
    obergrenze = Q(datum__lt=zaehlung.datum) | Q(
        datum=zaehlung.datum, erstellt_am__lte=zaehlung.erstellt_am
    )
    queryset = queryset.filter(obergrenze)
    if vorherige:
        untergrenze = Q(datum__gt=vorherige.datum) | Q(
            datum=vorherige.datum, erstellt_am__gt=vorherige.erstellt_am
        )
        queryset = queryset.filter(untergrenze)
    return queryset


def berechne_auswertung(zaehlung: Zaehlung) -> Auswertung:
    """Berechnet Soll/Ist-Kasse fuer den Zeitraum seit der letzten Zaehlung bis
    einschliesslich `zaehlung`, je Artikel direkt aus dem eingetragenen
    Verbrauch (kein Bestandsvergleich)."""
    vorherige = vorherige_zaehlung(zaehlung)

    verbraeuche = {
        v.getraenk_id: v.verbraucht
        for v in ZaehlungVerbrauch.objects.filter(zaehlung=zaehlung)
    }
    getraenk_ids = set(verbraeuche)
    getraenke = {g.id: g for g in Getraenk.objects.filter(id__in=getraenk_ids)}

    freigetraenke_filter = _im_zeitraum(
        Freigetraenk.objects.filter(getraenk_id__in=getraenk_ids), vorherige, zaehlung
    )
    freigetraenke_je_getraenk = dict(
        freigetraenke_filter.values("getraenk_id")
        .annotate(summe=Sum("anzahl"))
        .values_list("getraenk_id", "summe")
    )

    auswertung = Auswertung(zaehlung=zaehlung, vorherige=vorherige)

    for getraenk_id in sorted(getraenke, key=lambda gid: getraenke[gid].name.lower()):
        getraenk = getraenke[getraenk_id]
        verbraucht = verbraeuche.get(getraenk_id, 0)
        freigetraenke = freigetraenke_je_getraenk.get(getraenk_id, 0)

        verkauft = verbraucht - freigetraenke
        soll_kasse_i = verkauft * getraenk.verkaufspreis

        auswertung.positionen.append(
            GetraenkAuswertung(
                getraenk=getraenk,
                verbraucht=verbraucht,
                freigetraenke=freigetraenke,
                verkauft=verkauft,
                verkaufspreis=getraenk.verkaufspreis,
                soll_kasse=soll_kasse_i,
            )
        )
        auswertung.soll_kasse += soll_kasse_i
        auswertung.freigetraenke_wert += freigetraenke * getraenk.verkaufspreis

    # Bargeld-Differenz: einfache Differenz des gezaehlten Bargelds seit der
    # letzten Zaehlung (0, wenn dies die allererste Zaehlung ist).
    auswertung.bargeld_differenz = (zaehlung.bargeld_gezaehlt or Decimal("0")) - (
        (vorherige.bargeld_gezaehlt or Decimal("0")) if vorherige else Decimal("0")
    )

    bewegungen_filter = _im_zeitraum(Kassenbewegung.objects.all(), vorherige, zaehlung)
    bewegungen = list(bewegungen_filter.order_by("datum", "id"))
    auswertung.kassenbewegungen = bewegungen
    for bewegung in bewegungen:
        if bewegung.art == Kassenbewegung.Art.EINLAGE:
            auswertung.einlagen += bewegung.betrag
        elif bewegung.art == Kassenbewegung.Art.ENTNAHME:
            auswertung.entnahmen += bewegung.betrag
        elif bewegung.art == Kassenbewegung.Art.FREMDER_BARGELDEINGANG:
            auswertung.fremde_bargeldeingaenge += bewegung.betrag

    # Netto aus Kassenbewegungen: wie viel vom gezaehlten Bargeld NICHT aus
    # Getraenkeverkauf stammt (Einlagen/fremde Eingaenge erhoehen das
    # physische Bargeld, Entnahmen senken es). Wird komplett herausgerechnet,
    # damit z.B. eine Entnahme nicht wie ein Fehlbetrag aussieht.
    auswertung.netto_kassenbewegungen = (
        auswertung.einlagen
        + auswertung.fremde_bargeldeingaenge
        - auswertung.entnahmen
    )
    auswertung.bar_anteil = (
        auswertung.bargeld_differenz - auswertung.netto_kassenbewegungen
    )

    # Python-Summe statt SQL-Sum(): SQLite berechnet SUM() ueber Decimal-
    # Spalten per Gleitkomma, was Rundungsmuell wie "40,3000000000000" erzeugt.
    paypal_zahlungen = PaypalZahlung.objects.filter(
        zaehlung=zaehlung, ist_getraenke_zahlung=True
    )
    auswertung.paypal_anteil = sum(
        (p.betrag for p in paypal_zahlungen), Decimal("0")
    )

    paypal_im_zeitraum = PaypalZahlung.objects.filter(datum__lte=zaehlung.datum)
    if vorherige:
        paypal_im_zeitraum = paypal_im_zeitraum.filter(datum__gt=vorherige.datum)
    auswertung.vorlaeufig = paypal_im_zeitraum.filter(
        ist_getraenke_zahlung__isnull=True
    ).exists()

    auswertung.ist_kasse = auswertung.bar_anteil + auswertung.paypal_anteil
    auswertung.kassendifferenz = auswertung.ist_kasse - auswertung.soll_kasse

    # Einkaufswert: rein informativ (Einkaeufe sind immer private Einlagen von
    # Nick, siehe Beleg-Docstring) - fliesst nicht in Soll-/Ist-Kasse oder die
    # Kassendifferenz ein (siehe README).
    belege_filter = _im_zeitraum(Beleg.objects.all(), vorherige, zaehlung)
    belege = list(belege_filter.order_by("datum", "id"))
    auswertung.belege = belege
    auswertung.einkaufswert = sum(
        (b.gesamtbetrag for b in belege), Decimal("0")
    )

    # Vorschlag fuer das zu zaehlende Bargeld (Schritt 2 der Zaehlung): der
    # Betrag, der bei einer Kassendifferenz von 0 jetzt in der Kasse liegen
    # muesste - vorheriges Bargeld plus den Soll-Umsatz dieses Zeitraums,
    # bereinigt um Kassenbewegungen (Einlagen/fremde Eingaenge erhoehen,
    # Entnahmen senken das physische Bargeld) und um den PayPal-Anteil (der
    # nie physisch in der Kasse landet).
    vorheriges_bargeld = (
        vorherige.bargeld_gezaehlt
        if vorherige and vorherige.bargeld_gezaehlt is not None
        else Decimal("0")
    )
    auswertung.bargeld_vorschlag = (
        vorheriges_bargeld
        + auswertung.soll_kasse
        + auswertung.einlagen
        - auswertung.entnahmen
        + auswertung.fremde_bargeldeingaenge
        - auswertung.paypal_anteil
    )

    return auswertung


@dataclass
class ZeitraumAuswertung:
    """Summe mehrerer Einzel-Auswertungen (z.B. alle Zaehlungen eines Monats)."""

    einzelergebnisse: list = field(default_factory=list)
    positionen: list = field(default_factory=list)
    soll_kasse: Decimal = Decimal("0")
    bargeld_differenz: Decimal = Decimal("0")
    einlagen: Decimal = Decimal("0")
    entnahmen: Decimal = Decimal("0")
    fremde_bargeldeingaenge: Decimal = Decimal("0")
    netto_kassenbewegungen: Decimal = Decimal("0")
    bar_anteil: Decimal = Decimal("0")
    paypal_anteil: Decimal = Decimal("0")
    ist_kasse: Decimal = Decimal("0")
    kassendifferenz: Decimal = Decimal("0")
    vorlaeufig: bool = False
    freigetraenke_wert: Decimal = Decimal("0")
    belege: list = field(default_factory=list)
    einkaufswert: Decimal = Decimal("0")


def berechne_zeitraum(zaehlungen) -> ZeitraumAuswertung | None:
    """Summiert die Einzelauswertungen mehrerer Zaehlungen (z.B. fuer die
    Monatsauswertung oder den CSV-Export)."""
    zaehlungen = list(zaehlungen)
    if not zaehlungen:
        return None

    zeitraum = ZeitraumAuswertung()
    positionen_je_getraenk: dict = {}

    for zaehlung in zaehlungen:
        ergebnis = berechne_auswertung(zaehlung)
        zeitraum.einzelergebnisse.append(ergebnis)
        zeitraum.soll_kasse += ergebnis.soll_kasse
        zeitraum.bargeld_differenz += ergebnis.bargeld_differenz
        zeitraum.einlagen += ergebnis.einlagen
        zeitraum.entnahmen += ergebnis.entnahmen
        zeitraum.fremde_bargeldeingaenge += ergebnis.fremde_bargeldeingaenge
        zeitraum.netto_kassenbewegungen += ergebnis.netto_kassenbewegungen
        zeitraum.bar_anteil += ergebnis.bar_anteil
        zeitraum.paypal_anteil += ergebnis.paypal_anteil
        zeitraum.vorlaeufig = zeitraum.vorlaeufig or ergebnis.vorlaeufig
        zeitraum.freigetraenke_wert += ergebnis.freigetraenke_wert
        zeitraum.belege += ergebnis.belege
        zeitraum.einkaufswert += ergebnis.einkaufswert

        for position in ergebnis.positionen:
            aggregiert = positionen_je_getraenk.setdefault(
                position.getraenk.id,
                GetraenkAuswertung(
                    getraenk=position.getraenk,
                    verbraucht=0,
                    freigetraenke=0,
                    verkauft=0,
                    verkaufspreis=position.verkaufspreis,
                    soll_kasse=Decimal("0"),
                ),
            )
            aggregiert.verbraucht += position.verbraucht
            aggregiert.freigetraenke += position.freigetraenke
            aggregiert.verkauft += position.verkauft
            aggregiert.soll_kasse += position.soll_kasse

    zeitraum.positionen = sorted(
        positionen_je_getraenk.values(), key=lambda p: p.getraenk.name.lower()
    )
    zeitraum.ist_kasse = zeitraum.bar_anteil + zeitraum.paypal_anteil
    zeitraum.kassendifferenz = zeitraum.ist_kasse - zeitraum.soll_kasse
    return zeitraum


@dataclass
class GetraenkBestand:
    getraenk: Getraenk
    eingekauft: int
    verbraucht: int
    bestand: int


def berechne_bestand():
    """Aktueller Bestand je Getraenk, ueber die komplette Historie: Summe
    aller eingekauften Mengen (BelegPosition) minus Summe aller verbrauchten
    Mengen (ZaehlungVerbrauch) - ein einziger Gesamtbestand, keine Trennung
    nach Lagerort. Rein informativ, fliesst in keine Kassenberechnung ein."""
    eingekauft = dict(
        BelegPosition.objects.values("getraenk_id")
        .annotate(summe=Sum("anzahl"))
        .values_list("getraenk_id", "summe")
    )
    verbraucht = dict(
        ZaehlungVerbrauch.objects.values("getraenk_id")
        .annotate(summe=Sum("verbraucht"))
        .values_list("getraenk_id", "summe")
    )

    ergebnisse = []
    for getraenk in Getraenk.objects.order_by("name"):
        anzahl_eingekauft = eingekauft.get(getraenk.id, 0)
        anzahl_verbraucht = verbraucht.get(getraenk.id, 0)
        ergebnisse.append(
            GetraenkBestand(
                getraenk=getraenk,
                eingekauft=anzahl_eingekauft,
                verbraucht=anzahl_verbraucht,
                bestand=anzahl_eingekauft - anzahl_verbraucht,
            )
        )
    return ergebnisse
