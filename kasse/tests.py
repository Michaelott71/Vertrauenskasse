import csv
import io
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
from .services import berechne_auswertung, berechne_zeitraum


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

    def test_paypal_getraenke_zahlung_erhoeht_ist_kasse(self):
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
        self.assertEqual(ergebnis.ist_kasse, Decimal("142.50") + Decimal("20.00"))
        self.assertFalse(ergebnis.vorlaeufig)

    def test_ungeklaerte_paypal_zahlung_macht_ergebnis_vorlaeufig(self):
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("20.00"), paypal_transaktions_id="TX3",
        )
        self._ende_verbrauch()
        ergebnis = berechne_auswertung(self.ende)
        self.assertTrue(ergebnis.vorlaeufig)
        self.assertEqual(ergebnis.paypal_anteil, Decimal("0"))

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
        self.assertEqual(ergebnis.bar_anteil, Decimal("112.50"))

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
            "Datum;Belegnummer;Artikel;Menge;Netto;USt-Satz;USt-Betrag;Brutto;Zahlungsart;Referenz",
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

    def test_post_speichert_verbrauch(self):
        response = self.client.post(
            reverse("kasse:zaehlung_neu"),
            {
                "datum": "2026-06-01",
                "notiz": "",
                "bargeld_gezaehlt": "50.00",
                f"verbraucht_{self.wasser.id}": "80",
                f"verbraucht_{self.twix.id}": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        zaehlung = Zaehlung.objects.get(datum="2026-06-01")
        self.assertEqual(
            ZaehlungVerbrauch.objects.get(zaehlung=zaehlung, getraenk=self.wasser).verbraucht,
            80,
        )
        self.assertEqual(
            ZaehlungVerbrauch.objects.get(zaehlung=zaehlung, getraenk=self.twix).verbraucht,
            15,
        )


class FreigetraenkNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")

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
        self.assertContains(response, "Soll-Kasse")

    def test_auswahl_zeigt_gewaehlte_zaehlung(self):
        z1 = _zaehlung("2026-06-01", "0")
        _zaehlung("2026-06-15", "0")
        response = self.client.get(reverse("kasse:auswertung"), {"zaehlung": z1.pk})
        self.assertContains(response, z1.belegnummer)


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
