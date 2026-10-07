import csv
import io
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from . import matching
from .export import erzeuge_csv, markiere_als_exportiert
from .models import (
    Auffuellung,
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
    ZaehlungBestand,
)
from .services import AuswertungError, berechne_auswertung, lagerbestaende_aktiv


def _zaehlung(datum, bargeld):
    return Zaehlung.objects.create(datum=datum, bargeld_gezaehlt=Decimal(bargeld))


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

        ZaehlungBestand.objects.create(zaehlung=self.start, getraenk=self.wasser, vollbestand_gezaehlt=100)
        ZaehlungBestand.objects.create(zaehlung=self.start, getraenk=self.cola, vollbestand_gezaehlt=50)
        ZaehlungBestand.objects.create(zaehlung=self.start, getraenk=self.twix, vollbestand_gezaehlt=20)

    def _ende_bestand(self, wasser=40, cola=20, twix=10):
        ZaehlungBestand.objects.create(zaehlung=self.ende, getraenk=self.wasser, vollbestand_gezaehlt=wasser)
        ZaehlungBestand.objects.create(zaehlung=self.ende, getraenk=self.cola, vollbestand_gezaehlt=cola)
        ZaehlungBestand.objects.create(zaehlung=self.ende, getraenk=self.twix, vollbestand_gezaehlt=twix)

    def test_verkauft_und_soll_kasse_je_artikel_mit_unterschiedlichem_preis(self):
        # Wasser 100 -> 40 = 60 verkauft * 1.50; Cola 50 -> 20 = 30 verkauft * 2.50
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)

        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        cola_pos = next(p for p in ergebnis.positionen if p.getraenk == self.cola)
        self.assertEqual(wasser_pos.verkauft, 60)
        self.assertEqual(cola_pos.verkauft, 30)
        self.assertEqual(
            ergebnis.soll_kasse,
            60 * Decimal("1.50") + 30 * Decimal("2.50") + 10 * Decimal("1.00"),
        )

    def test_auffuellung_erhoeht_verkauft(self):
        Auffuellung.objects.create(getraenk=self.wasser, datum="2026-06-10", anzahl=24)
        self._ende_bestand(wasser=100)

        ergebnis = berechne_auswertung(self.start, self.ende)
        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        self.assertEqual(wasser_pos.aufgefuellt, 24)
        self.assertEqual(wasser_pos.verkauft, 24)

    def test_einkaufsbeleg_allein_veraendert_verkauft_nicht(self):
        # Ein Einkauf erhoeht nur den Lagerbestand, nicht den Kuehlschrankbestand,
        # solange keine Auffuellung stattgefunden hat.
        beleg = Beleg.objects.create(datum="2026-06-10", gesamtbetrag=Decimal("12.00"), haendler="Getraenkemarkt")
        BelegPosition.objects.create(beleg=beleg, getraenk=self.wasser, anzahl=24, einzelpreis=Decimal("0.50"))
        self._ende_bestand(wasser=100)

        ergebnis = berechne_auswertung(self.start, self.ende)
        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        self.assertEqual(wasser_pos.aufgefuellt, 0)
        # 100 Start - 100 Ende = 0 verkauft (keine Auffuellung erfasst)
        self.assertEqual(wasser_pos.verkauft, 0)

    def test_freigetraenke_reduziert_verkauft(self):
        Freigetraenk.objects.create(getraenk=self.wasser, datum="2026-06-05", anzahl=5, kommentar="Team")
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        wasser_pos = next(p for p in ergebnis.positionen if p.getraenk == self.wasser)
        self.assertEqual(wasser_pos.verkauft, 55)

    def test_bar_anteil_ist_differenz_des_gezaehlten_bargelds(self):
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.bar_anteil, Decimal("142.50"))

    def test_kassendifferenz_ohne_rundungstoleranz(self):
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        # Soll = 90+75+10 = 175.00; Ist (nur bar) = 142.50 -> Differenz -32.50
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
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.paypal_anteil, Decimal("20.00"))
        self.assertEqual(ergebnis.ist_kasse, Decimal("142.50") + Decimal("20.00"))
        self.assertFalse(ergebnis.vorlaeufig)

    def test_ungeklaerte_paypal_zahlung_macht_ergebnis_vorlaeufig(self):
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("20.00"), paypal_transaktions_id="TX3",
        )
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertTrue(ergebnis.vorlaeufig)
        self.assertEqual(ergebnis.paypal_anteil, Decimal("0"))

    def test_gleiche_zaehlung_wirft_fehler(self):
        with self.assertRaises(AuswertungError):
            berechne_auswertung(self.start, self.start)

    def test_falsche_reihenfolge_wirft_fehler(self):
        with self.assertRaises(AuswertungError):
            berechne_auswertung(self.ende, self.start)

    def test_entnahme_wird_zur_bargelddifferenz_addiert(self):
        # Bargeld-Differenz waere sonst 142.50, aber dazwischen wurden 50 EUR
        # entnommen (z.B. Einnahmen abgeholt) - die muessen trotzdem als
        # Getraenke-Umsatz zaehlen.
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-06-10", betrag=Decimal("50.00")
        )
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.bargeld_differenz, Decimal("142.50"))
        self.assertEqual(ergebnis.entnahmen, Decimal("50.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("192.50"))

    def test_einlage_wird_von_bargelddifferenz_abgezogen(self):
        # Eine private Einlage (z.B. Wechselgeld nachgelegt) ist kein Erloes.
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.EINLAGE, datum="2026-06-10", betrag=Decimal("30.00")
        )
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.einlagen, Decimal("30.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("112.50"))

    def test_fremder_bargeldeingang_wird_von_bargelddifferenz_abgezogen(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.FREMDER_BARGELDEINGANG,
            datum="2026-06-10",
            betrag=Decimal("20.00"),
            rg_nummer="RG-2026-010",
        )
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.fremde_bargeldeingaenge, Decimal("20.00"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("122.50"))
        self.assertEqual(len(ergebnis.kassenbewegungen), 1)

    def test_kassenbewegung_ausserhalb_zeitraum_zaehlt_nicht(self):
        Kassenbewegung.objects.create(
            art=Kassenbewegung.Art.ENTNAHME, datum="2026-05-01", betrag=Decimal("50.00")
        )
        self._ende_bestand()
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.entnahmen, Decimal("0"))
        self.assertEqual(ergebnis.bar_anteil, Decimal("142.50"))


class LagerbestandTests(TestCase):
    def test_lagerbestand_nur_anfangsbestand(self):
        Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
            anfangsbestand_lager=50,
        )
        ergebnis = dict((g.name, b) for g, b in lagerbestaende_aktiv())
        self.assertEqual(ergebnis["Wasser"], 50)

    def test_einkauf_erhoeht_lagerbestand_auffuellung_reduziert_ihn(self):
        wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
            anfangsbestand_lager=50,
        )
        beleg = Beleg.objects.create(datum="2026-06-10", gesamtbetrag=Decimal("12.00"))
        BelegPosition.objects.create(beleg=beleg, getraenk=wasser, anzahl=24, einzelpreis=Decimal("0.50"))
        Auffuellung.objects.create(getraenk=wasser, datum="2026-06-11", anzahl=10)

        ergebnis = dict((g.name, b) for g, b in lagerbestaende_aktiv())
        # 50 Anfang + 24 Einkauf - 10 Auffuellung = 64
        self.assertEqual(ergebnis["Wasser"], 64)

    def test_inaktive_getraenke_werden_nicht_angezeigt(self):
        Getraenk.objects.create(
            name="Altes Getraenk", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
            aktiv=False,
        )
        namen = [g.name for g, _ in lagerbestaende_aktiv()]
        self.assertNotIn("Altes Getraenk", namen)


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
        # 2 x Cola (2.50) = 5.00, kein Stichwort, keine RG-Nummer
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

        # Wiederkehrender Betreff -> automatisch als Stichwort gelernt
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

    def test_auffuellung_in_exportiertem_monat_wird_blockiert(self):
        import datetime

        auffuellung = Auffuellung(getraenk=self.getraenk, datum=datetime.date(2026, 6, 15), anzahl=1)
        with self.assertRaises(GesperrterMonatError):
            auffuellung.clean()

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
        ZaehlungBestand.objects.create(zaehlung=self.start, getraenk=self.wasser, vollbestand_gezaehlt=100)
        ZaehlungBestand.objects.create(zaehlung=self.ende, getraenk=self.wasser, vollbestand_gezaehlt=60)
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

    def test_post_speichert_bestand(self):
        response = self.client.post(
            reverse("kasse:zaehlung_neu"),
            {
                "datum": "2026-06-01",
                "notiz": "",
                "bargeld_gezaehlt": "50.00",
                f"bestand_{self.wasser.id}": "80",
                f"bestand_{self.twix.id}": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        zaehlung = Zaehlung.objects.get(datum="2026-06-01")
        self.assertEqual(
            ZaehlungBestand.objects.get(zaehlung=zaehlung, getraenk=self.wasser).vollbestand_gezaehlt,
            80,
        )
        self.assertEqual(
            ZaehlungBestand.objects.get(zaehlung=zaehlung, getraenk=self.twix).vollbestand_gezaehlt,
            15,
        )


class AuffuellungNeuViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.wasser = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
        )
        self.client.login(username="tester", password="pw12345678")

    def test_post_erstellt_auffuellung(self):
        response = self.client.post(
            reverse("kasse:auffuellung_neu"),
            {"datum": "2026-06-10", f"anzahl_{self.wasser.id}": "15"},
        )
        self.assertEqual(response.status_code, 302)
        auffuellung = Auffuellung.objects.get(getraenk=self.wasser)
        self.assertEqual(auffuellung.anzahl, 15)

    def test_post_in_exportiertem_monat_wird_blockiert(self):
        MonatsExport.objects.create(jahr=2026, monat=6)
        response = self.client.post(
            reverse("kasse:auffuellung_neu"),
            {"datum": "2026-06-10", f"anzahl_{self.wasser.id}": "15"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Auffuellung.objects.filter(getraenk=self.wasser).exists())


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


class LagerUebersichtViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50"),
            anfangsbestand_lager=42,
        )
        self.client.login(username="tester", password="pw12345678")

    def test_zeigt_lagerbestand(self):
        response = self.client.get(reverse("kasse:lager_uebersicht"))
        self.assertContains(response, "Wasser")
        self.assertContains(response, "42")


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

    def test_zeigt_freundlichen_hinweis_ohne_zaehlungen(self):
        response = self.client.get(reverse("kasse:auswertung"))
        self.assertContains(response, "mindestens")
        self.assertContains(response, "zwei")
        self.assertNotContains(response, "dürfen nicht identisch sein")

    def test_zeigt_freundlichen_hinweis_bei_nur_einer_zaehlung(self):
        _zaehlung("2026-06-01", "0")
        response = self.client.get(reverse("kasse:auswertung"))
        self.assertContains(response, "mindestens")
        self.assertNotContains(response, "dürfen nicht identisch sein")

    def test_zeigt_formular_ab_zwei_zaehlungen(self):
        _zaehlung("2026-06-01", "0")
        _zaehlung("2026-06-15", "0")
        response = self.client.get(reverse("kasse:auswertung"))
        self.assertContains(response, "Start-Zählung")


class MonatsauswertungViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.getraenk = Getraenk.objects.create(
            name="Wasser", warenpreis=Decimal("0.50"), verkaufspreis=Decimal("1.50")
        )
        for datum, voll in [("2026-07-01", 100), ("2026-07-10", 60), ("2026-07-20", 20)]:
            z = _zaehlung(datum, "0")
            ZaehlungBestand.objects.create(zaehlung=z, getraenk=self.getraenk, vollbestand_gezaehlt=voll)
        _zaehlung("2026-06-15", "0")

    def test_zeigt_nur_zaehlungen_des_gewaehlten_monats(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(reverse("kasse:monatsauswertung"), {"monat": "2026-07"})
        self.assertEqual(len(response.context["zaehlungen"]), 3)

    def test_gesamtauswertung_nutzt_erste_und_letzte_zaehlung_im_monat(self):
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
