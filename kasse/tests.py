import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from . import matching
from .export import erzeuge_csv, markiere_als_exportiert
from .models import (
    Beleg,
    BelegPosition,
    Freigetraenk,
    Getraenk,
    GesperrterMonatError,
    Kassenbewegung,
    MonatsExport,
    PaypalStichwort,
    PaypalZahlung,
    Zaehlung,
    ZaehlungVerbrauch,
)
from .services import berechne_auswertung, berechne_bestand, berechne_zeitraum


def _zaehlung(datum, bargeld):
    return Zaehlung.objects.create(datum=datum, bargeld_gezaehlt=Decimal(bargeld))


def _verbrauch(zaehlung, getraenk, menge):
    return ZaehlungVerbrauch.objects.create(
        zaehlung=zaehlung, getraenk=getraenk, verbraucht=menge
    )


class BelegnummerTests(TestCase):
    def test_format_und_laufende_nummer_im_monat(self):
        z1 = _zaehlung("2026-06-01", "0")
        z2 = _zaehlung("2026-06-15", "0")
        z3 = _zaehlung("2026-07-01", "0")

        self.assertEqual(z1.belegnummer, "VK-2026-06-01")
        self.assertEqual(z2.belegnummer, "VK-2026-06-02")
        self.assertEqual(z3.belegnummer, "VK-2026-07-01")

    def test_belegnummer_bleibt_bei_erneutem_speichern_gleich(self):
        z1 = _zaehlung("2026-06-01", "0")
        nummer = z1.belegnummer
        z1.notiz = "geaendert"
        z1.save()
        self.assertEqual(z1.belegnummer, nummer)


class AuswertungTests(TestCase):
    def setUp(self):
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.cola = Getraenk.objects.create(
            name="Cola", warenpreis=Decimal("0.40"), verkaufspreis=Decimal("2.50"),
        )
        self.twix = Getraenk.objects.create(
            name="Twix", warenpreis=Decimal("0.30"), verkaufspreis=Decimal("1.00"),
        )
        self.start = _zaehlung("2026-06-01", "0")
        self.ende = _zaehlung("2026-06-15", "142.50")

    def _ende_verbrauch(self, wasser=60, cola=30, twix=10):
        _verbrauch(self.ende, self.wasser, wasser)
        _verbrauch(self.ende, self.cola, cola)
        _verbrauch(self.ende, self.twix, twix)

    def test_verkauft_und_soll_kasse_je_artikel_mit_unterschiedlichem_preis(self):
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)

        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        cola_pos = next(p for p in ergebnis.positionen if p.getraenk == self.cola)
        self.assertEqual(wasser_pos.verkauft, 60)
        self.assertEqual(cola_pos.verkauft, 30)
        self.assertEqual(
            ergebnis.soll_kasse,
            60 * Decimal("1.50") + 30 * Decimal("2.50") + 10 * Decimal("1.00"),
        )

    def test_erste_zaehlung_hat_eigenes_ergebnis_ohne_vorherige(self):
        # Die allererste Zaehlung braucht keine vorherige, um ein Ergebnis zu
        # liefern - Bargeld_letzte_Zaehlung gilt dann als 0.
        erste = _zaehlung("2026-05-01", "20.00")
        _verbrauch(erste, self.wasser, 5)

        ergebnis = berechne_auswertung(erste)
        self.assertIsNone(ergebnis.vorherige)
        self.assertEqual(ergebnis.soll_kasse, Decimal("7.50"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("20.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("12.50"))

    def test_einkaufsbeleg_veraendert_verkauft_nicht(self):
        # Ein Einkauf ist reine Dokumentation (Wareneinsatz) und fliesst nicht
        # in die Kassenformel ein - nur der direkt eingetragene Verbrauch zaehlt.
        beleg = Beleg.objects.create(
            datum="2026-06-10", gesamtbetrag=Decimal("12.00"), haendler="Getraenkemarkt"
        )
        BelegPosition.objects.create(
            beleg=beleg, getraenk=self.wasser, anzahl=24, einzelpreis=Decimal("0.50")
        )
        self._ende_verbrauch()

        ergebnis = berechne_auswertung(self.ende)
        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        self.assertEqual(wasser_pos.verkauft, 60)

    def test_freigetraenke_reduziert_verkauft(self):
        Freigetraenk.objects.create(
            getraenk=self.wasser, datum="2026-06-05", anzahl=5, kommentar="Team"
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        self.assertEqual(wasser_pos.verkauft, 55)

    def test_bar_anteil_ist_differenz_des_gezaehlten_bargelds(self):
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.bar_anteil, Decimal("142.50"))

    def test_kassendifferenz_ohne_rundungstoleranz(self):
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.soll_kasse, Decimal("175.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("-32.50"))

    def test_paypal_zahlung_ist_informativ_und_veraendert_kassenbestand_nicht(self):
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("20.00"), zaehlung=self.ende,
            paypal_transaktions_id="TX1", ist_getraenke_zahlung=True,
        )
        PaypalZahlung.objects.create(
            datum="2026-06-13", betrag=Decimal("99.00"), zaehlung=self.ende,
            paypal_transaktions_id="TX2", ist_getraenke_zahlung=False,
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.paypal_anteil, Decimal("20.00"))
        # PayPal hat nichts mit dem Kassenbestand zu tun - Bar-Anteil,
        # Bargeld-Vorschlag und Kassendifferenz bleiben unveraendert.
        self.assertEqual(ergebnis.bar_anteil, Decimal("142.50"))
        self.assertEqual(ergebnis.bargeld_vorschlag, ergebnis.soll_kasse)
        self.assertEqual(ergebnis.kassendifferenz, Decimal("-32.50"))

    def test_vollstaendig_per_paypal_bezahlt_zeigt_volle_kassendifferenz(self):
        # Alles wurde per PayPal bezahlt, kein Bargeld kam dazu - das zeigt
        # sich jetzt bewusst als Kassendifferenz (frueher wurde der
        # PayPal-Anteil automatisch verrechnet und die Differenz verschwand).
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("175.00"), zaehlung=self.ende,
            paypal_transaktions_id="TXPP", ist_getraenke_zahlung=True,
        )
        self.ende.bargeld_gezaehlt = Decimal("0.00")
        self.ende.save()
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.paypal_anteil, Decimal("175.00"))
        self.assertEqual(ergebnis.bargeld_vorschlag, Decimal("175.00"))
        self.assertEqual(ergebnis.neuer_bargeldbestand, Decimal("0.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("-175.00"))

    def test_entnahme_wird_zur_bargelddifferenz_addiert(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-06-10", betrag=Decimal("50.00")
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.bargeld_differenz, Decimal("142.50"))
        self.assertEqual(ergebnis.entnahmen, Decimal("50.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("192.50"))

    def test_einlage_wird_von_bargelddifferenz_abgezogen(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-10", betrag=Decimal("30.00")
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.einlagen, Decimal("30.00"))
        self.assertEqual(ergebnis.netto_kassenbewegungen, Decimal("30.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("112.50"))

    def test_netto_kassenbewegungen_ist_einlagen_plus_fremde_minus_entnahmen(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-10", betrag=Decimal("20.00")
        )
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-06-11", betrag=Decimal("5.00")
        )
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.FREMDER_BARGELDEINGANG, datum="2026-06-12", betrag=Decimal("8.00")
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.netto_kassenbewegungen, Decimal("20.00") + Decimal("8.00") - Decimal("5.00"))
        self.assertEqual(ergebnis.bar_anteil, ergebnis.bargeld_differenz - ergebnis.netto_kassenbewegungen)

    def test_fremder_bargeldeingang_wird_von_bargelddifferenz_abgezogen(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.FREMDER_BARGELDEINGANG,
            datum="2026-06-10",
            betrag=Decimal("20.00"),
            rg_nummer="RG-2026-010",
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.fremde_bargeldeingaenge, Decimal("20.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("122.50"))
        self.assertEqual(len(ergebnis.kassenbewegungen), 1)

    def test_kassenbewegung_ausserhalb_zeitraum_zaehlt_nicht(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-05-01", betrag=Decimal("50.00")
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.entnahmen, Decimal("0"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("142.50"))

    def test_einkaufswert_ist_rein_informativ_und_veraendert_soll_kasse_nicht(self):
        Beleg.objects.create(
            datum="2026-06-10", gesamtbetrag=Decimal("40.00"), haendler="Getraenkemarkt"
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.einkaufswert, Decimal("40.00"))
        self.assertEqual(ergebnis.soll_kasse, Decimal("175.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("-32.50"))
        self.assertEqual(len(ergebnis.belege), 1)

    def test_beleg_ausserhalb_zeitraum_zaehlt_nicht_zum_einkaufswert(self):
        Beleg.objects.create(
            datum="2026-05-01", gesamtbetrag=Decimal("40.00"), haendler="Vorher"
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.einkaufswert, Decimal("0"))
        self.assertEqual(ergebnis.belege, [])

    def test_freigetraenke_wert_wird_zu_verkaufspreis_berechnet(self):
        Freigetraenk.objects.create(
            getraenk=self.wasser, datum="2026-06-05", anzahl=5, kommentar="Team"
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.freigetraenke_wert, 5 * Decimal("1.50"))

    def test_bargeld_vorschlag_ohne_kassenbewegungen(self):
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        # start.bargeld_gezaehlt ist 0, also Vorschlag = 0 + Soll-Kasse.
        self.assertEqual(ergebnis.bargeld_vorschlag, ergebnis.soll_kasse)

    def test_bargeld_vorschlag_beruecksichtigt_vorheriges_bargeld(self):
        # Reproduziert den vom Nutzer gemeldeten Fall: der Vorschlag fuer eine
        # zweite Zaehlung muss den bereits bestaetigten Betrag der vorherigen
        # Zaehlung aufaddieren, nicht nur den neuen Soll-Umsatz.
        self.start.bargeld_gezaehlt = Decimal("50.00")
        self.start.save()
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(
            ergebnis.bargeld_vorschlag, Decimal("50.00") + ergebnis.soll_kasse
        )

    def test_bargeld_vorschlag_beruecksichtigt_kassenbewegungen_nicht_paypal(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-10", betrag=Decimal("20.00")
        )
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-06-11", betrag=Decimal("5.00")
        )
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("10.00"), zaehlung=self.ende,
            paypal_transaktions_id="TXV1", ist_getraenke_zahlung=True,
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        # PayPal hat nichts mit dem Kassenbestand zu tun und fliesst deshalb
        # NICHT in den Vorschlag ein - nur Einlagen/Entnahmen tun das.
        self.assertEqual(
            ergebnis.bargeld_vorschlag,
            ergebnis.soll_kasse + Decimal("20.00") - Decimal("5.00"),
        )

    def test_einkaufswert_fliesst_nicht_in_bargeld_vorschlag_ein(self):
        Beleg.objects.create(datum="2026-06-10", gesamtbetrag=Decimal("40.00"))
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertEqual(ergebnis.bargeld_vorschlag, ergebnis.soll_kasse)


class KassenbestandVerlaufTests(TestCase):
    """Reproduziert den vom Nutzer gemeldeten Fall: eine Starteinlage muss im
    'Ist-Kassenbestand' als tatsaechlich vorhandenes Geld sichtbar sein, nicht
    als 0 erscheinen, nur weil sie nicht aus Getraenkeverkauf stammt."""

    def setUp(self):
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )

    def test_starteinlage_erscheint_als_ist_und_soll_kassenbestand(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-01", betrag=Decimal("35.00")
        )
        z1 = _zaehlung("2026-06-01", "35.00")
        ergebnis = berechne_auswertung(z1)

        self.assertEqual(ergebnis.alter_bargeldbestand, Decimal("0"))
        self.assertEqual(ergebnis.neuer_bargeldbestand, Decimal("35.00"))
        self.assertEqual(ergebnis.bargeld_vorschlag, Decimal("35.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("0"))

    def test_alter_und_neuer_bargeldbestand_bei_zweiter_zaehlung(self):
        z1 = _zaehlung("2026-06-01", "35.00")
        z2 = _zaehlung("2026-06-10", "50.00")
        _verbrauch(z2, self.wasser, 10)  # 10 * 1.50 = 15.00 Soll

        ergebnis = berechne_auswertung(z2)
        self.assertEqual(ergebnis.alter_bargeldbestand, Decimal("35.00"))
        self.assertEqual(ergebnis.neuer_bargeldbestand, Decimal("50.00"))
        self.assertEqual(ergebnis.bargeld_vorschlag, Decimal("50.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("0"))

    def test_neuer_bargeldbestand_ist_none_wenn_noch_nicht_bestaetigt(self):
        z1 = _zaehlung("2026-06-01", "35.00")
        z2 = Zaehlung.objects.create(datum="2026-06-10")
        _verbrauch(z2, self.wasser, 2)

        ergebnis = berechne_auswertung(z2)
        self.assertIsNone(ergebnis.neuer_bargeldbestand)

    def test_zeitraum_verwendet_ersten_alten_und_letzten_neuen_bargeldbestand(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-01", betrag=Decimal("35.00")
        )
        z1 = _zaehlung("2026-06-01", "35.00")
        z2 = _zaehlung("2026-06-10", "50.00")
        z3 = _zaehlung("2026-06-20", "65.00")
        _verbrauch(z2, self.wasser, 10)  # Soll 15.00
        _verbrauch(z3, self.wasser, 10)  # Soll 15.00

        zeitraum = berechne_zeitraum([z1, z2, z3])
        self.assertEqual(zeitraum.alter_bargeldbestand, Decimal("0"))
        self.assertEqual(zeitraum.neuer_bargeldbestand, Decimal("65.00"))
        self.assertEqual(zeitraum.bargeld_vorschlag, Decimal("65.00"))
        self.assertEqual(zeitraum.kassendifferenz, Decimal("0"))


class GleicherTagReihenfolgeTests(TestCase):
    """Wenn mehrere Zaehlungen/Kassenbewegungen auf denselben Kalendertag
    fallen, muss die tatsaechliche Erfassungsreihenfolge entscheiden, nicht
    nur das Datum - sonst wuerde eine Kassenbewegung, die erst NACH einer
    bereits bestaetigten Zaehlung gebucht wird, deren Ergebnis rueckwirkend
    veraendern (genau das vom Nutzer gemeldete Szenario)."""

    def setUp(self):
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )

    def test_kassenbewegung_nach_zaehlung_wirkt_sich_nicht_rueckwirkend_aus(self):
        z1 = _zaehlung("2026-10-08", "0")
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-10-08", betrag=Decimal("35.00")
        )
        ergebnis = berechne_auswertung(z1)
        self.assertEqual(ergebnis.einlagen, Decimal("0"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("0"))

    def test_kassenbewegung_vor_zaehlung_zaehlt_noch_zu_deren_zeitraum(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-10-08", betrag=Decimal("35.00")
        )
        z1 = _zaehlung("2026-10-08", "0")
        ergebnis = berechne_auswertung(z1)
        self.assertEqual(ergebnis.einlagen, Decimal("35.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("-35.00"))

    def test_kassenbewegung_zwischen_zwei_zaehlungen_am_selben_tag(self):
        z1 = _zaehlung("2026-10-08", "0")
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-10-08", betrag=Decimal("35.00")
        )
        z2 = _zaehlung("2026-10-08", "50.00")
        _verbrauch(z2, self.wasser, 10)  # 10 * 1.50 = 15.00 Soll

        e1 = berechne_auswertung(z1)
        e2 = berechne_auswertung(z2)
        self.assertEqual(e1.einlagen, Decimal("0"))
        self.assertEqual(e1.bar_anteil, Decimal("0"))
        self.assertEqual(e2.einlagen, Decimal("35.00"))
        # bargeld_differenz = 50 - 0 = 50; bar_anteil = 50 - 35 = 15 = Soll
        self.assertEqual(e2.bar_anteil, Decimal("15.00"))
        self.assertEqual(e2.kassendifferenz, Decimal("0"))


class ZeitraumAuswertungTests(TestCase):
    def test_summiert_mehrere_zaehlungen(self):
        getraenk = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )
        z1 = _zaehlung("2026-07-01", "0")
        z2 = _zaehlung("2026-07-10", "60.00")
        z3 = _zaehlung("2026-07-20", "120.00")
        _verbrauch(z1, getraenk, 0)
        _verbrauch(z2, getraenk, 40)
        _verbrauch(z3, getraenk, 40)

        ergebnis = berechne_zeitraum([z1, z2, z3])
        pos = next(p for p in ergebnis.positionen if p.getraenk == getraenk)
        self.assertEqual(pos.verkauft, 80)
        self.assertEqual(ergebnis.soll_kasse, Decimal("120.00"))

    def test_leere_liste_gibt_none(self):
        self.assertIsNone(berechne_zeitraum([]))

    def test_summiert_einkaufswert_ohne_auswirkung_auf_soll_kasse(self):
        getraenk = Getraenk.objects.create(
            name="Cola", warenpreis=Decimal("0.40"), verkaufspreis=Decimal("2.00")
        )
        z1 = _zaehlung("2026-08-01", "0")
        z2 = _zaehlung("2026-08-10", "0")
        _verbrauch(z1, getraenk, 0)
        _verbrauch(z2, getraenk, 20)
        Beleg.objects.create(datum="2026-08-05", gesamtbetrag=Decimal("15.00"))

        ergebnis = berechne_zeitraum([z1, z2])
        self.assertEqual(ergebnis.einkaufswert, Decimal("15.00"))
        self.assertEqual(ergebnis.soll_kasse, Decimal("40.00"))


class BestandTests(TestCase):
    def setUp(self):
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.15"), verkaufspreis=Decimal("1.50"),
        )
        self.cola = Getraenk.objects.create(
            name="Cola", warenpreis=Decimal("0.40"), verkaufspreis=Decimal("2.00"),
        )

    def _beleg_position(self, getraenk, anzahl, datum="2026-06-01"):
        beleg = Beleg.objects.create(datum=datum, gesamtbetrag=Decimal("1.00"))
        BelegPosition.objects.create(
            beleg=beleg, getraenk=getraenk, anzahl=anzahl, einzelpreis=getraenk.warenpreis
        )

    def test_bestand_ist_eingekauft_minus_verbraucht(self):
        self._beleg_position(self.wasser, 10)
        z = _zaehlung("2026-06-05", "0")
        _verbrauch(z, self.wasser, 4)

        bestaende = berechne_bestand()
        wasser_bestand = next(b for b in bestaende if b.getraenk == self.wasser)
        self.assertEqual(wasser_bestand.eingekauft, 10)
        self.assertEqual(wasser_bestand.verbraucht, 4)
        self.assertEqual(wasser_bestand.bestand, 6)

    def test_getraenk_ohne_belege_oder_verbrauch_hat_bestand_null(self):
        bestaende = berechne_bestand()
        cola_bestand = next(b for b in bestaende if b.getraenk == self.cola)
        self.assertEqual(cola_bestand.eingekauft, 0)
        self.assertEqual(cola_bestand.verbraucht, 0)
        self.assertEqual(cola_bestand.bestand, 0)

    def test_summiert_mehrere_belege_und_zaehlungen(self):
        self._beleg_position(self.wasser, 10, datum="2026-06-01")
        self._beleg_position(self.wasser, 5, datum="2026-06-10")
        z1 = _zaehlung("2026-06-05", "0")
        z2 = _zaehlung("2026-06-15", "0")
        _verbrauch(z1, self.wasser, 3)
        _verbrauch(z2, self.wasser, 2)

        bestaende = berechne_bestand()
        wasser_bestand = next(b for b in bestaende if b.getraenk == self.wasser)
        self.assertEqual(wasser_bestand.eingekauft, 15)
        self.assertEqual(wasser_bestand.verbraucht, 5)
        self.assertEqual(wasser_bestand.bestand, 10)

    def test_freigetraenke_werden_nicht_doppelt_vom_bestand_abgezogen(self):
        # Freigetraenke sind bereits Teil von "verbraucht" (das ist die
        # physisch entnommene Menge) - sie duerfen nicht zusaetzlich nochmal
        # vom Bestand abgezogen werden.
        self._beleg_position(self.wasser, 10)
        z = _zaehlung("2026-06-05", "0")
        _verbrauch(z, self.wasser, 4)
        Freigetraenk.objects.create(getraenk=self.wasser, datum="2026-06-05", anzahl=2)

        bestaende = berechne_bestand()
        wasser_bestand = next(b for b in bestaende if b.getraenk == self.wasser)
        self.assertEqual(wasser_bestand.bestand, 6)


class PaypalMatchingTests(TestCase):
    def setUp(self):
        Getraenk.objects.create(name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"))
        Getraenk.objects.create(name="Cola", warenpreis=Decimal("0.40"), verkaufspreis=Decimal("2.50"))
        for wort in ["Cola", "Bier", "Wasser", "Kasse"]:
            PaypalStichwort.objects.get_or_create(wort=wort)

    def test_fester_verwendungszweck(self):
        z = PaypalZahlung(datum="2026-06-01", betrag=Decimal("10.00"), paypal_transaktions_id="A",
                           verwendungszweck="Getränke Golfbox")
        matching.ordne_zahlung_zu(z)
        self.assertTrue(z.ist_getraenke_zahlung)
        self.assertIn("Golfbox", z.zuordnungsgrund)

    def test_rg_nummer_schliesst_vertrauenskasse_aus(self):
        z = PaypalZahlung(datum="2026-06-01", betrag=Decimal("1.50"), paypal_transaktions_id="B",
                           verwendungszweck="Zahlung zu RG-2026-042")
        matching.ordne_zahlung_zu(z)
        self.assertFalse(z.ist_getraenke_zahlung)

    def test_stichwort_treffer(self):
        z = PaypalZahlung(datum="2026-06-01", betrag=Decimal("5.00"), paypal_transaktions_id="C",
                           verwendungszweck="fuer die Kasse, danke!")
        matching.ordne_zahlung_zu(z)
        self.assertTrue(z.ist_getraenke_zahlung)
        self.assertIn("Kasse", z.zuordnungsgrund)

    def test_betragsregel_vermutlich_bleibt_unklar(self):
        z = PaypalZahlung(datum="2026-06-01", betrag=Decimal("5.00"), paypal_transaktions_id="D",
                           verwendungszweck="Danke!")
        matching.ordne_zahlung_zu(z)
        self.assertIsNone(z.ist_getraenke_zahlung)
        self.assertIn("Vermutlich", z.zuordnungsgrund)

    def test_unklarer_betrag_landet_auf_klaerungsliste(self):
        z = PaypalZahlung(datum="2026-06-01", betrag=Decimal("17.37"), paypal_transaktions_id="E",
                           verwendungszweck="Danke!")
        matching.ordne_zahlung_zu(z)
        self.assertIsNone(z.ist_getraenke_zahlung)
        self.assertIn("Unklar", z.zuordnungsgrund)

    def test_klaerungsliste_enthaelt_nur_unentschiedene(self):
        z1 = PaypalZahlung.objects.create(
            datum="2026-06-01", betrag=Decimal("17.37"), paypal_transaktions_id="F",
        )
        PaypalZahlung.objects.create(
            datum="2026-06-02", betrag=Decimal("10.00"), paypal_transaktions_id="G",
            ist_getraenke_zahlung=True,
        )
        self.assertEqual(list(matching.klaerungsliste()), [z1])

    def test_manuelle_entscheidung_ordnet_zaehlung_zu_und_lernt_stichwort(self):
        ende = _zaehlung("2026-06-20", "0")
        z = PaypalZahlung.objects.create(
            datum="2026-06-10", betrag=Decimal("17.37"), paypal_transaktions_id="H",
            verwendungszweck="Getränke Meier",
        )
        matching.entscheide_manuell(z, True)
        z.refresh_from_db()
        self.assertTrue(z.ist_getraenke_zahlung)
        self.assertEqual(z.zaehlung, ende)

        z2 = PaypalZahlung.objects.create(
            datum="2026-06-11", betrag=Decimal("22.00"), paypal_transaktions_id="I",
            verwendungszweck="Getränke Meier",
        )
        matching.ordne_zahlung_zu(z2)
        self.assertTrue(z2.ist_getraenke_zahlung)
        self.assertIn("Stichwort", z2.zuordnungsgrund)


class MonatsExportLockTests(TestCase):
    def setUp(self):
        self.getraenk = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )
        MonatsExport.objects.create(jahr=2026, monat=6)

    def test_freigetraenk_in_exportiertem_monat_wird_blockiert(self):
        import datetime

        fg = Freigetraenk(getraenk=self.getraenk, datum=datetime.date(2026, 6, 15), anzahl=1)
        with self.assertRaises(GesperrterMonatError):
            fg.clean()

    def test_freigetraenk_in_nicht_exportiertem_monat_ist_erlaubt(self):
        import datetime

        fg = Freigetraenk(getraenk=self.getraenk, datum=datetime.date(2026, 7, 15), anzahl=1)
        fg.clean()  # keine Exception

    def test_zaehlung_in_exportiertem_monat_wird_blockiert(self):
        zaehlung = _zaehlung("2026-06-15", "0")
        zaehlung.bargeld_gezaehlt = Decimal("99.00")
        with self.assertRaises(GesperrterMonatError):
            zaehlung.clean()

    def test_zaehlung_in_nicht_exportiertem_monat_ist_erlaubt(self):
        zaehlung = _zaehlung("2026-07-15", "0")
        zaehlung.clean()  # keine Exception

    def test_zaehlungsverbrauch_in_exportiertem_monat_wird_blockiert(self):
        zaehlung = _zaehlung("2026-06-15", "0")
        verbrauch = ZaehlungVerbrauch(zaehlung=zaehlung, getraenk=self.getraenk, verbraucht=5)
        with self.assertRaises(GesperrterMonatError):
            verbrauch.clean()

    def test_kassenbewegung_in_exportiertem_monat_wird_blockiert(self):
        import datetime

        bewegung = Kassenbewegung(
            art=Kassenbewegung.Art.ENTNAHME,
            datum=datetime.date(2026, 6, 15),
            betrag=Decimal("10.00"),
        )
        with self.assertRaises(GesperrterMonatError):
            bewegung.clean()

    def test_beleg_in_exportiertem_monat_wird_blockiert(self):
        import datetime

        beleg = Beleg(datum=datetime.date(2026, 6, 15), gesamtbetrag=Decimal("10.00"))
        with self.assertRaises(GesperrterMonatError):
            beleg.clean()

    def test_beleg_in_nicht_exportiertem_monat_ist_erlaubt(self):
        import datetime

        beleg = Beleg(datum=datetime.date(2026, 7, 15), gesamtbetrag=Decimal("10.00"))
        beleg.clean()  # keine Exception


class CsvExportTests(TestCase):
    def setUp(self):
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.start = _zaehlung("2026-06-01", "0")
        self.ende = _zaehlung("2026-06-15", "60.00")
        _verbrauch(self.ende, self.wasser, 40)
        PaypalZahlung.objects.create(
            datum="2026-06-10", betrag=Decimal("10.00"), zaehlung=self.ende,
            paypal_transaktions_id="TX-99", ist_getraenke_zahlung=True,
        )

    def test_dateiname_und_header(self):
        dateiname, csv_text, warnungen = erzeuge_csv(2026, 6)
        self.assertEqual(dateiname, "2026-06_Vertrauenskasse.csv")
        header = csv_text.splitlines()[0]
        self.assertEqual(
            header,
            "Datum;Belegnummer;Artikel;Menge;Netto;USt-Satz;USt-Betrag;Brutto;Zahlungsart;Referenz;Notiz",
        )

    def test_bar_und_paypal_zeilen_mit_deutscher_zahlenformatierung(self):
        _, csv_text, _ = erzeuge_csv(2026, 6)
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        bar_zeile = next(r for r in rows if r["Zahlungsart"] == "Bar")
        paypal_zeile = next(r for r in rows if r["Zahlungsart"] == "PayPal")

        self.assertEqual(bar_zeile["Belegnummer"], self.ende.belegnummer)
        self.assertEqual(bar_zeile["Brutto"], "60,00")
        self.assertEqual(bar_zeile["Datum"], "15.06.2026")
        self.assertEqual(bar_zeile["USt-Satz"], "19%")

        self.assertEqual(paypal_zeile["Referenz"], "TX-99")
        self.assertEqual(paypal_zeile["Brutto"], "10,00")
        self.assertEqual(paypal_zeile["Belegnummer"], self.ende.belegnummer)

    def test_export_markiert_monat_als_exportiert(self):
        self.assertFalse(MonatsExport.objects.filter(jahr=2026, monat=6).exists())
        markiere_als_exportiert(2026, 6)
        self.assertTrue(MonatsExport.objects.filter(jahr=2026, monat=6).exists())

    def test_notiz_der_zaehlung_erscheint_in_der_csv(self):
        self.ende.notiz = "Kunde hat vergessen zu bezahlen"
        self.ende.save()
        _, csv_text, _ = erzeuge_csv(2026, 6)
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        bar_zeile = next(r for r in rows if r["Zahlungsart"] == "Bar")
        self.assertEqual(bar_zeile["Notiz"], "Kunde hat vergessen zu bezahlen")

    def test_anfangsbestand_und_endbestand_in_kassenbestand_uebersicht(self):
        _, csv_text, warnungen = erzeuge_csv(2026, 6)
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        kassenbestand_rows = [r for r in rows if r["Zahlungsart"] == "Kassenbestand"]
        anfang = next(r for r in kassenbestand_rows if r["Artikel"] == "Anfangsbestand")
        ende = next(r for r in kassenbestand_rows if r["Artikel"] == "Endbestand")
        self.assertEqual(anfang["Brutto"], "0,00")
        self.assertEqual(ende["Brutto"], "60,00")
        self.assertEqual(warnungen, [])

    def test_kassenbewegung_erscheint_in_kassenbestand_uebersicht(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-05", betrag=Decimal("35.00"),
            notiz="Kassenanfangssaldo",
        )
        _, csv_text, _ = erzeuge_csv(2026, 6)
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        einlage_zeile = next(
            r for r in rows
            if r["Zahlungsart"] == "Kassenbestand" and r["Artikel"] == "Einlage (Privateinlage)"
        )
        self.assertEqual(einlage_zeile["Brutto"], "35,00")
        self.assertEqual(einlage_zeile["Referenz"], "Kassenanfangssaldo")

    def test_zaehlung_mit_kassendifferenz_aber_bar_anteil_null_erscheint_trotzdem(self):
        # Bargeld-Differenz zufaellig 0, obwohl Soll-Kasse 60 EUR war -> es
        # gibt eine Kassendifferenz von -60 EUR, die Zeile darf nicht
        # verschwinden (sonst fehlt genau die Information, die der
        # Steuerberater fuer die Differenz-Erklaerung braucht).
        self.ende.bargeld_gezaehlt = Decimal("0.00")
        self.ende.notiz = "Komplette Differenz, Grund unklar"
        self.ende.save()
        _, csv_text, _ = erzeuge_csv(2026, 6)
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        bar_zeile = next(r for r in rows if r["Zahlungsart"] == "Bar")
        self.assertEqual(bar_zeile["Brutto"], "0,00")
        self.assertEqual(bar_zeile["Notiz"], "Komplette Differenz, Grund unklar")

    def test_warnung_wenn_endbestand_nicht_bestaetigt(self):
        self.ende.bargeld_gezaehlt = None
        self.ende.save()
        _, csv_text, warnungen = erzeuge_csv(2026, 6)
        self.assertTrue(any("Endbestand" in w for w in warnungen))
        rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
        self.assertFalse(any(r["Artikel"] == "Endbestand" for r in rows))


class ZaehlungNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.twix = Getraenk.objects.create(
            name="Twix", warenpreis=Decimal("0.30"), verkaufspreis=Decimal("1.00")
        )
        self.client.login(username="tester", password="pw12345678")

    def test_kacheln_werden_fuer_aktive_getraenke_gerendert(self):
        response = self.client.get(reverse("kasse:zaehlung_neu"))
        self.assertContains(response, "Wasser")
        self.assertContains(response, "Twix")

    def test_post_speichert_verbrauch_und_leitet_zur_bargeldbestaetigung(self):
        response = self.client.post(
            reverse("kasse:zaehlung_neu"),
            {
                "datum": "2026-06-01",
                "notiz": "",
                f"verbraucht_{self.wasser.id}": "80",
                f"verbraucht_{self.twix.id}": "15",
            },
        )
        zaehlung = Zaehlung.objects.get(datum="2026-06-01")
        self.assertRedirects(
            response, reverse("kasse:zaehlung_bargeld", args=[zaehlung.pk])
        )
        self.assertEqual(
            ZaehlungVerbrauch.objects.get(zaehlung=zaehlung, getraenk=self.wasser).verbraucht,
            80,
        )
        self.assertEqual(
            ZaehlungVerbrauch.objects.get(zaehlung=zaehlung, getraenk=self.twix).verbraucht,
            15,
        )
        self.assertIsNone(zaehlung.bargeld_gezaehlt)


class ZaehlungBargeldViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")
        self.zaehlung = Zaehlung.objects.create(datum="2026-06-01")
        _verbrauch(self.zaehlung, self.wasser, 10)

    def test_get_zeigt_soll_betrag_als_vorbelegten_wert(self):
        response = self.client.get(
            reverse("kasse:zaehlung_bargeld", args=[self.zaehlung.pk])
        )
        self.assertContains(response, "15,00")
        self.assertEqual(
            response.context["form"].initial["bargeld_gezaehlt"], Decimal("15.00")
        )

    def test_post_bestaetigt_betrag(self):
        response = self.client.post(
            reverse("kasse:zaehlung_bargeld", args=[self.zaehlung.pk]),
            {"bargeld_gezaehlt": "15.00"},
        )
        self.assertRedirects(response, reverse("kasse:home"))
        self.zaehlung.refresh_from_db()
        self.assertEqual(self.zaehlung.bargeld_gezaehlt, Decimal("15.00"))

    def test_post_korrigiert_betrag(self):
        response = self.client.post(
            reverse("kasse:zaehlung_bargeld", args=[self.zaehlung.pk]),
            {"bargeld_gezaehlt": "12.50"},
        )
        self.assertRedirects(
            response, reverse("kasse:zaehlung_differenz", args=[self.zaehlung.pk])
        )
        self.zaehlung.refresh_from_db()
        self.assertEqual(self.zaehlung.bargeld_gezaehlt, Decimal("12.50"))

    def test_get_zeigt_bisheriges_bargeld_bei_zweiter_zaehlung(self):
        self.zaehlung.bargeld_gezaehlt = Decimal("15.00")
        self.zaehlung.save()
        zweite = Zaehlung.objects.create(datum="2026-06-10")
        _verbrauch(zweite, self.wasser, 2)  # 2 * 1.50 = 3.00

        response = self.client.get(reverse("kasse:zaehlung_bargeld", args=[zweite.pk]))
        self.assertEqual(
            response.context["form"].initial["bargeld_gezaehlt"], Decimal("18.00")
        )

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:zaehlung_bargeld", args=[self.zaehlung.pk]),
            {"bargeld_gezaehlt": "15.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.zaehlung.refresh_from_db()
        self.assertIsNone(self.zaehlung.bargeld_gezaehlt)


class ZaehlungDifferenzViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")
        self.zaehlung = Zaehlung.objects.create(
            datum="2026-06-01", bargeld_gezaehlt=Decimal("12.50")
        )
        _verbrauch(self.zaehlung, self.wasser, 10)  # Soll 15.00, Differenz -2.50

    def test_zeigt_kassendifferenz_und_freigetraenke_link_mit_datum(self):
        response = self.client.get(
            reverse("kasse:zaehlung_differenz", args=[self.zaehlung.pk])
        )
        self.assertContains(response, "-2,50")
        self.assertContains(
            response,
            f"{reverse('kasse:freigetraenk_neu')}?datum=2026-06-01",
        )

    def test_post_speichert_kommentar_und_leitet_zur_startseite(self):
        response = self.client.post(
            reverse("kasse:zaehlung_differenz", args=[self.zaehlung.pk]),
            {"notiz": "Gast hat nicht bezahlt"},
        )
        self.assertRedirects(response, reverse("kasse:home"))
        self.zaehlung.refresh_from_db()
        self.assertEqual(self.zaehlung.notiz, "Gast hat nicht bezahlt")

    def test_zeigt_per_paypal_bezahlt_option_und_paypal_hinweis(self):
        PaypalZahlung.objects.create(
            datum="2026-06-01", betrag=Decimal("5.00"), zaehlung=self.zaehlung,
            paypal_transaktions_id="TXD1", ist_getraenke_zahlung=True,
        )
        response = self.client.get(
            reverse("kasse:zaehlung_differenz", args=[self.zaehlung.pk])
        )
        self.assertContains(response, "Per PayPal bezahlt")
        self.assertContains(response, "5,00")

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:zaehlung_differenz", args=[self.zaehlung.pk]),
            {"notiz": "nachtraeglich"},
        )
        self.assertEqual(response.status_code, 200)
        self.zaehlung.refresh_from_db()
        self.assertEqual(self.zaehlung.notiz, "")


class FreigetraenkNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")

    def test_get_mit_datum_param_belegt_datumsfeld_vor(self):
        response = self.client.get(
            reverse("kasse:freigetraenk_neu"), {"datum": "2026-07-04"}
        )
        self.assertEqual(
            response.context["meta_form"].initial["datum"], date(2026, 7, 4)
        )

    def test_post_erstellt_freigetraenk(self):
        response = self.client.post(
            reverse("kasse:freigetraenk_neu"),
            {
                "datum": "2026-06-10",
                "kommentar": "Teamevent",
                f"anzahl_{self.wasser.id}": "3",
            },
        )
        self.assertEqual(response.status_code, 302)
        fg = Freigetraenk.objects.get(getraenk=self.wasser)
        self.assertEqual(fg.anzahl, 3)
        self.assertEqual(fg.kommentar, "Teamevent")

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:freigetraenk_neu"),
            {"datum": "2026-06-10", "kommentar": "", f"anzahl_{self.wasser.id}": "3"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Freigetraenk.objects.filter(getraenk=self.wasser).exists())


class KassenbewegungNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.client.login(username="tester", password="pw12345678")

    def test_post_erstellt_kassenbewegung(self):
        response = self.client.post(
            reverse("kasse:kassenbewegung_neu"),
            {
                "art": Kassenbewegung.Art.EINLAGE,
                "datum": "2026-06-01",
                "betrag": "100.00",
                "rg_nummer": "",
                "notiz": "Kassenanfangssaldo",
            },
        )
        self.assertEqual(response.status_code, 302)
        bewegung = Kassenbewegung.objects.get()
        self.assertEqual(bewegung.betrag, Decimal("100.00"))
        self.assertEqual(bewegung.art, Kassenbewegung.Art.EINLAGE)

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:kassenbewegung_neu"),
            {
                "art": Kassenbewegung.Art.ENTNAHME,
                "datum": "2026-06-15",
                "betrag": "10.00",
                "rg_nummer": "",
                "notiz": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Kassenbewegung.objects.exists())


class BelegNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.15"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")

    def test_post_erstellt_beleg(self):
        response = self.client.post(
            reverse("kasse:beleg_neu"),
            {
                "datum": "2026-06-01",
                "haendler": "Getraenkemarkt",
                "gesamtbetrag": "40.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        beleg = Beleg.objects.get()
        self.assertEqual(beleg.gesamtbetrag, Decimal("40.00"))
        self.assertEqual(beleg.haendler, "Getraenkemarkt")

    def test_post_erstellt_belegposition_mit_warenpreis_als_einzelpreis(self):
        response = self.client.post(
            reverse("kasse:beleg_neu"),
            {
                "datum": "2026-06-01",
                "haendler": "Getraenkemarkt",
                "gesamtbetrag": "1.50",
                f"anzahl_{self.wasser.id}": "10",
            },
        )
        self.assertEqual(response.status_code, 302)
        beleg = Beleg.objects.get()
        position = BelegPosition.objects.get(beleg=beleg)
        self.assertEqual(position.getraenk, self.wasser)
        self.assertEqual(position.anzahl, 10)
        self.assertEqual(position.einzelpreis, Decimal("0.15"))

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:beleg_neu"),
            {"datum": "2026-06-15", "haendler": "", "gesamtbetrag": "10.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Beleg.objects.exists())

    def test_liste_zeigt_erfasste_belege(self):
        Beleg.objects.create(
            datum="2026-06-01", gesamtbetrag=Decimal("40.00"), haendler="Getraenkemarkt"
        )
        response = self.client.get(reverse("kasse:beleg_neu"))
        self.assertContains(response, "Getraenkemarkt")
        self.assertContains(response, "40,00")


class BestandUebersichtViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.client.login(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.15"), verkaufspreis=Decimal("1.50"),
        )

    def test_zeigt_bestand_je_getraenk(self):
        beleg = Beleg.objects.create(datum="2026-06-01", gesamtbetrag=Decimal("1.50"))
        BelegPosition.objects.create(
            beleg=beleg, getraenk=self.wasser, anzahl=10, einzelpreis=Decimal("0.15")
        )
        z = _zaehlung("2026-06-05", "0")
        _verbrauch(z, self.wasser, 4)

        response = self.client.get(reverse("kasse:bestand"))
        self.assertContains(response, "Wasser")
        self.assertEqual(
            next(b for b in response.context["bestaende"] if b.getraenk == self.wasser).bestand,
            6,
        )


class AuswertungViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.client.login(username="tester", password="pw12345678")

    def test_zeigt_hinweis_ohne_zaehlungen(self):
        response = self.client.get(reverse("kasse:auswertung"))
        self.assertContains(response, "Noch keine Zählung erfasst")

    def test_zeigt_sofort_ein_ergebnis_bei_nur_einer_zaehlung(self):
        zaehlung = _zaehlung("2026-06-01", "20.00")
        response = self.client.get(reverse("kasse:auswertung"))
        self.assertContains(response, zaehlung.belegnummer)
        self.assertContains(response, "Soll-Kassenbestand")
        self.assertContains(response, "Ist-Kassenbestand")
        self.assertNotContains(response, "PayPal-Anteil (Ist)")

    def test_starteinlage_erscheint_als_ist_kassenbestand(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-01", betrag=Decimal("35.00")
        )
        zaehlung = _zaehlung("2026-06-01", "35.00")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": zaehlung.pk})
        self.assertContains(response, "Kassenbestand-Verlauf")
        self.assertNotContains(response, "Wie sich der Bar-Anteil zusammensetzt")
        # "35,00" muss als Ist-Kassenbestand auftauchen, nicht nur versteckt
        # im Kassenbewegungen-Journal.
        self.assertContains(response, "Soll-Kassenbestand")
        content = response.content.decode()
        self.assertGreaterEqual(content.count("35,00"), 2)

    def test_auswahl_zeigt_gewaehlte_zaehlung(self):
        z1 = _zaehlung("2026-06-01", "0")
        _zaehlung("2026-06-15", "0")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": z1.pk})
        self.assertContains(response, z1.belegnummer)

    def test_warnt_wenn_bargeld_noch_nicht_bestaetigt(self):
        zaehlung = Zaehlung.objects.create(datum="2026-06-01")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": zaehlung.pk})
        self.assertContains(response, "noch kein Bargeld bestätigt")

    def test_zeigt_differenz_erklaeren_formular_bei_differenz(self):
        _zaehlung("2026-06-01", "0")
        zaehlung = _zaehlung("2026-06-15", "999.00")  # bewusst falsch -> Differenz
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": zaehlung.pk})
        self.assertContains(response, "Kassendifferenz erklären")

    def test_kein_differenz_erklaeren_formular_ohne_differenz(self):
        zaehlung = _zaehlung("2026-06-01", "0")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": zaehlung.pk})
        self.assertNotContains(response, "Kassendifferenz erklären")

    def test_post_speichert_differenz_erklaerung(self):
        zaehlung = _zaehlung("2026-06-15", "999.00")
        response = self.client.post(
            reverse("kasse:auswertung") + f"?zaehlung={zaehlung.pk}",
            {"zaehlung_id": zaehlung.pk, "notiz": "Kunde hat vergessen zu zahlen", "notiz_speichern": "1"},
        )
        self.assertRedirects(
            response, f"{reverse('kasse:auswertung')}?zaehlung={zaehlung.pk}"
        )
        zaehlung.refresh_from_db()
        self.assertEqual(zaehlung.notiz, "Kunde hat vergessen zu zahlen")

    def test_differenz_erklaerung_in_exportiertem_monat_wird_blockiert(self):
        zaehlung = _zaehlung("2026-06-15", "999.00")
        MonatsExport.objects.create(jahr=2026, monat=6)
        self.client.post(
            reverse("kasse:auswertung") + f"?zaehlung={zaehlung.pk}",
            {"zaehlung_id": zaehlung.pk, "notiz": "nachtraeglich", "notiz_speichern": "1"},
        )
        zaehlung.refresh_from_db()
        self.assertEqual(zaehlung.notiz, "")

    def test_keine_warnung_wenn_bargeld_erfasst(self):
        z = _zaehlung("2026-06-01", "0")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": z.pk})
        self.assertNotContains(response, "noch kein Bargeld bestätigt")


class MonatsauswertungViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.getraenk = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )
        for datum, menge in [("2026-07-01", 0), ("2026-07-10", 40), ("2026-07-20", 40)]:
            z = _zaehlung(datum, "0")
            _verbrauch(z, self.getraenk, menge)
        _zaehlung("2026-06-15", "0")

    def test_zeigt_nur_zaehlungen_des_gewaehlten_monats(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(reverse("kasse:monatsauswertung"), {"monat": "2026-07"})
        self.assertEqual(len(response.context["zaehlungen"]), 3)

    def test_monatsergebnis_summiert_alle_zaehlungen_im_monat(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(reverse("kasse:monatsauswertung"), {"monat": "2026-07"})
        result = response.context["result"]
        self.assertIsNotNone(result)
        pos = next(p for p in result.positionen if p.getraenk == self.getraenk)
        self.assertEqual(pos.verkauft, 80)


class PaypalAbgleichViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.client.login(username="tester", password="pw12345678")

    def test_neue_zahlung_wird_automatisch_zugeordnet(self):
        response = self.client.post(
            reverse("kasse:paypal_abgleich"),
            {
                "formular": "neu",
                "datum": "2026-06-01",
                "betrag": "10.00",
                "verwendungszweck": "Getränke Golfbox",
                "paypal_transaktions_id": "TX-1",
            },
        )
        self.assertEqual(response.status_code, 302)
        zahlung = PaypalZahlung.objects.get(paypal_transaktions_id="TX-1")
        self.assertTrue(zahlung.ist_getraenke_zahlung)

    def test_entscheidung_loest_zahlung_von_klaerungsliste(self):
        zahlung = PaypalZahlung.objects.create(
            datum="2026-06-01", betrag=Decimal("17.37"), paypal_transaktions_id="TX-2",
        )
        response = self.client.post(
            reverse("kasse:paypal_abgleich"),
            {
                "formular": "entscheidung",
                "zahlung_id": zahlung.id,
                "entscheidung": "nein",
                "kommentar": "Privatzahlung",
            },
        )
        self.assertEqual(response.status_code, 302)
        zahlung.refresh_from_db()
        self.assertFalse(zahlung.ist_getraenke_zahlung)


@override_settings(MEDIA_ROOT="/tmp/vertrauenskasse-test-media")
class MediaServeTests(TestCase):
    def setUp(self):
        import os

        os.makedirs("/tmp/vertrauenskasse-test-media/belege", exist_ok=True)
        with open("/tmp/vertrauenskasse-test-media/belege/beleg.pdf", "wb") as f:
            f.write(b"%PDF-1.4 test")
        self.user = User.objects.create_user(username="tester", password="pw12345678")

    def test_ohne_login_gibt_es_keinen_zugriff(self):
        response = self.client.get(reverse("kasse:media", kwargs={"path": "belege/beleg.pdf"}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_eingeloggter_nutzer_bekommt_die_datei(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(reverse("kasse:media", kwargs={"path": "belege/beleg.pdf"}))
        self.assertEqual(response.status_code, 200)

    def test_path_traversal_wird_verhindert(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(reverse("kasse:media", kwargs={"path": "../settings.py"}))
        self.assertEqual(response.status_code, 404)
