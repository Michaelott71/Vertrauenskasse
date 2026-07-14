from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .datev import baue_datev_buchungsstapel
from .export import rechnungen_als_csv, rechnungen_als_xlsx
from .models import (
    Artikel,
    Gutschein,
    Quittung,
    Rechnung,
    RechnungsPosition,
    ZahlungsdienstleisterGebuehr,
)
from .pdf import quittung_pdf, rechnung_pdf
from .services import GutscheinError, gutschein_einloesen


class RechnungsnummerTests(TestCase):
    def test_nummern_sind_fortlaufend_je_jahr(self):
        r1 = Rechnung.objects.create(datum=date(2026, 1, 5))
        r2 = Rechnung.objects.create(datum=date(2026, 3, 1))
        r3 = Rechnung.objects.create(datum=date(2027, 1, 1))

        self.assertEqual(r1.nummer, "RE-2026-001")
        self.assertEqual(r2.nummer, "RE-2026-002")
        self.assertEqual(r3.nummer, "RE-2027-001")

    def test_manuell_gesetzte_nummer_wird_nicht_ueberschrieben(self):
        r = Rechnung.objects.create(datum=date(2026, 1, 1), nummer="RE-2026-099")
        self.assertEqual(r.nummer, "RE-2026-099")


class QuittungsnummerTests(TestCase):
    def test_nummern_sind_fortlaufend_je_jahr(self):
        q1 = Quittung.objects.create(datum=date(2026, 1, 5), betrag=Decimal("10.00"))
        q2 = Quittung.objects.create(datum=date(2026, 3, 1), betrag=Decimal("5.00"))

        self.assertEqual(q1.nummer, "Q-2026-001")
        self.assertEqual(q2.nummer, "Q-2026-002")

    def test_quittung_ohne_namen_ist_gueltig(self):
        q = Quittung.objects.create(
            datum=date(2026, 1, 1), betrag=Decimal("42.00"), verwendungszweck="Spende"
        )
        self.assertEqual(q.name, "")


class RechnungsPositionMwstTests(TestCase):
    def setUp(self):
        self.rechnung = Rechnung.objects.create(datum=date(2026, 6, 1))

    def test_mwst_wird_individuell_pro_artikel_berechnet(self):
        RechnungsPosition.objects.create(
            rechnung=self.rechnung, bezeichnung="Beratung", menge=2,
            einzelpreis=Decimal("100.00"), mwst_satz=Decimal("19.00"),
        )
        RechnungsPosition.objects.create(
            rechnung=self.rechnung, bezeichnung="Buch", menge=1,
            einzelpreis=Decimal("20.00"), mwst_satz=Decimal("7.00"),
        )

        self.assertEqual(self.rechnung.netto_summe, Decimal("220.00"))
        self.assertEqual(
            self.rechnung.mwst_gesamt,
            (Decimal("200.00") * Decimal("0.19")) + (Decimal("20.00") * Decimal("0.07")),
        )
        aufschluesselung = self.rechnung.mwst_aufschluesselung
        self.assertEqual(set(aufschluesselung), {Decimal("19.00"), Decimal("7.00")})

    def test_artikel_mwst_satz_wird_beim_anlegen_uebernommen(self):
        artikel = Artikel.objects.create(
            name="Golfstunde", einzelpreis=Decimal("50.00"), mwst_satz=Decimal("19.00")
        )
        position = RechnungsPosition(
            rechnung=self.rechnung, artikel=artikel, menge=1, einzelpreis=artikel.einzelpreis
        )
        position.save()
        self.assertEqual(position.bezeichnung, "Golfstunde")
        self.assertEqual(position.mwst_satz, Decimal("19.00"))


class GutscheinEinloesungTests(TestCase):
    def setUp(self):
        self.rechnung = Rechnung.objects.create(datum=date(2026, 6, 1))

    def test_teilweise_einloesung_reduziert_restguthaben(self):
        gutschein = Gutschein.objects.create(code="ABC123", wert=Decimal("50.00"))

        gutschein_einloesen(gutschein, Decimal("20.00"), rechnung=self.rechnung)
        self.assertEqual(gutschein.restguthaben, Decimal("30.00"))
        self.assertEqual(gutschein.status, "aktiv")

        gutschein_einloesen(gutschein, Decimal("30.00"), rechnung=self.rechnung)
        self.assertEqual(gutschein.restguthaben, Decimal("0.00"))
        self.assertEqual(gutschein.status, "eingeloest")

    def test_einloesung_ueber_restguthaben_hinaus_schlaegt_fehl(self):
        gutschein = Gutschein.objects.create(code="XYZ789", wert=Decimal("20.00"))
        gutschein_einloesen(gutschein, Decimal("15.00"), rechnung=self.rechnung)

        with self.assertRaises(GutscheinError):
            gutschein_einloesen(gutschein, Decimal("10.00"), rechnung=self.rechnung)

    def test_abgelaufener_gutschein_kann_nicht_eingeloest_werden(self):
        gutschein = Gutschein.objects.create(
            code="OLD001", wert=Decimal("10.00"),
            ablaufdatum=date.today() - timedelta(days=1),
        )
        with self.assertRaises(GutscheinError):
            gutschein_einloesen(gutschein, Decimal("5.00"), rechnung=self.rechnung)

    def test_prozentualer_gutschein_nur_einmal_einloesbar(self):
        gutschein = Gutschein.objects.create(
            code="PROZ10", typ=Gutschein.TYP_PROZENT, wert=Decimal("10.00")
        )
        gutschein_einloesen(gutschein, Decimal("5.00"), rechnung=self.rechnung)
        with self.assertRaises(GutscheinError):
            gutschein_einloesen(gutschein, Decimal("3.00"), rechnung=self.rechnung)

    def test_verlosungsgewinn_als_ausgabegrund(self):
        gutschein = Gutschein.objects.create(
            code="WIN001", wert=Decimal("25.00"), grund=Gutschein.GRUND_VERLOSUNG
        )
        self.assertEqual(gutschein.grund, "verlosung")


class ZahlungsdienstleisterGebuehrTests(TestCase):
    def test_muss_genau_einer_rechnung_oder_quittung_zugeordnet_sein(self):
        gebuehr = ZahlungsdienstleisterGebuehr(
            bruttobetrag=Decimal("100.00"), gebuehr=Decimal("2.90")
        )
        with self.assertRaises(Exception):
            gebuehr.full_clean()


class DatevExportTests(TestCase):
    def setUp(self):
        self.rechnung = Rechnung.objects.create(datum=date(2026, 6, 15))
        RechnungsPosition.objects.create(
            rechnung=self.rechnung, bezeichnung="Beratung", menge=1,
            einzelpreis=Decimal("100.00"), mwst_satz=Decimal("19.00"),
        )
        self.gebuehr = ZahlungsdienstleisterGebuehr.objects.create(
            rechnung=self.rechnung, anbieter="PayPal",
            bruttobetrag=Decimal("119.00"), gebuehr=Decimal("3.50"),
            datum=date(2026, 6, 16),
        )

    def test_skr03_verwendet_erwartete_kontonummern(self):
        inhalt = baue_datev_buchungsstapel(
            [self.rechnung], [self.gebuehr], "SKR03",
            date(2026, 6, 1), date(2026, 6, 30),
        )
        self.assertIn("8400", inhalt)  # Erloeskonto 19% SKR03
        self.assertIn("1200", inhalt)  # Bankkonto SKR03
        self.assertIn("4970", inhalt)  # Gebuehren-Aufwandskonto SKR03

    def test_skr04_verwendet_andere_kontonummern(self):
        inhalt = baue_datev_buchungsstapel(
            [self.rechnung], [self.gebuehr], "SKR04",
            date(2026, 6, 1), date(2026, 6, 30),
        )
        self.assertIn("4400", inhalt)  # Erloeskonto 19% SKR04
        self.assertIn("1800", inhalt)  # Bankkonto SKR04


class ExportTests(TestCase):
    def setUp(self):
        self.rechnung = Rechnung.objects.create(datum=date(2026, 6, 1), kunde_name="Max Mustermann")
        RechnungsPosition.objects.create(
            rechnung=self.rechnung, bezeichnung="Ware", menge=1,
            einzelpreis=Decimal("10.00"), mwst_satz=Decimal("19.00"),
        )

    def test_csv_export_enthaelt_rechnungsnummer(self):
        inhalt = rechnungen_als_csv(Rechnung.objects.all())
        self.assertIn(self.rechnung.nummer, inhalt)
        self.assertIn("Max Mustermann", inhalt)

    def test_xlsx_export_erzeugt_gueltige_datei(self):
        inhalt = rechnungen_als_xlsx(Rechnung.objects.all())
        self.assertTrue(inhalt.startswith(b"PK"))  # xlsx ist ein ZIP-Container


class PdfTests(TestCase):
    def test_rechnung_pdf_erzeugt_gueltiges_pdf(self):
        rechnung = Rechnung.objects.create(datum=date(2026, 6, 1))
        RechnungsPosition.objects.create(
            rechnung=rechnung, bezeichnung="Ware", menge=1,
            einzelpreis=Decimal("10.00"), mwst_satz=Decimal("19.00"),
        )
        pdf_bytes = rechnung_pdf(rechnung)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_quittung_pdf_erzeugt_gueltiges_pdf(self):
        quittung = Quittung.objects.create(datum=date(2026, 6, 1), betrag=Decimal("42.00"))
        pdf_bytes = quittung_pdf(quittung)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class MonatslisteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.rechnung = Rechnung.objects.create(datum=date(2026, 6, 15))

    def test_ohne_login_wird_umgeleitet(self):
        response = self.client.get(reverse("buchhaltung:monatsliste"))
        self.assertEqual(response.status_code, 302)

    def test_eingeloggter_nutzer_sieht_die_liste(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("buchhaltung:monatsliste"), {"jahr": 2026, "monat": 6}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.rechnung.nummer)

    def test_bezahlt_umschalten(self):
        self.client.login(username="tester", password="pw12345678")
        self.assertFalse(self.rechnung.bezahlt)

        self.client.post(reverse("buchhaltung:rechnung_bezahlt", args=[self.rechnung.pk]))
        self.rechnung.refresh_from_db()
        self.assertTrue(self.rechnung.bezahlt)
        self.assertEqual(self.rechnung.bezahlt_am, date.today())

        self.client.post(reverse("buchhaltung:rechnung_bezahlt", args=[self.rechnung.pk]))
        self.rechnung.refresh_from_db()
        self.assertFalse(self.rechnung.bezahlt)
        self.assertIsNone(self.rechnung.bezahlt_am)
