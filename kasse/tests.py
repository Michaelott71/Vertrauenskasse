from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    Beleg,
    BelegPosition,
    DifferenzZuordnung,
    Freigetraenk,
    Getraenk,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
)
from .services import AuswertungError, berechne_auswertung


class AuswertungTests(TestCase):
    def setUp(self):
        self.bier = Getraenk.objects.create(
            name="Bier", warenpreis=Decimal("0.50"), pfand=Decimal("0.15"),
            verkaufspreis=Decimal("1.50"),
        )
        self.cola = Getraenk.objects.create(
            name="Cola", warenpreis=Decimal("0.40"), pfand=Decimal("0.15"),
            verkaufspreis=Decimal("1.00"),
        )
        self.start = Zaehlung.objects.create(datum="2026-06-01", bargeld_gezaehlt=Decimal("0"))
        self.ende = Zaehlung.objects.create(datum="2026-06-15", bargeld_gezaehlt=Decimal("142.50"))

        ZaehlungBestand.objects.create(
            zaehlung=self.start, getraenk=self.bier,
            vollbestand_gezaehlt=100, leergut_gezaehlt=20,
        )
        ZaehlungBestand.objects.create(
            zaehlung=self.start, getraenk=self.cola,
            vollbestand_gezaehlt=50, leergut_gezaehlt=10,
        )

    def _ende_bestand(self, voll_bier, leergut_bier, rueckgabe_bier, voll_cola, leergut_cola, rueckgabe_cola):
        ZaehlungBestand.objects.create(
            zaehlung=self.ende, getraenk=self.bier,
            vollbestand_gezaehlt=voll_bier, leergut_gezaehlt=leergut_bier,
            rueckgabe_an_getraenkemarkt=rueckgabe_bier,
        )
        ZaehlungBestand.objects.create(
            zaehlung=self.ende, getraenk=self.cola,
            vollbestand_gezaehlt=voll_cola, leergut_gezaehlt=leergut_cola,
            rueckgabe_an_getraenkemarkt=rueckgabe_cola,
        )

    def test_verkauft_und_soll_kasse_ohne_nachschub_und_freigetraenke(self):
        # Bier: 100 Start -> 40 Ende => 60 verkauft
        # Cola: 50 Start -> 20 Ende => 30 verkauft
        self._ende_bestand(40, 40, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)

        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)
        cola_pos = next(p for p in ergebnis.positionen if p.getraenk == self.cola)

        self.assertEqual(bier_pos.verkauft, 60)
        self.assertEqual(cola_pos.verkauft, 30)
        self.assertEqual(
            ergebnis.soll_kasse,
            60 * Decimal("1.50") + 30 * Decimal("1.00"),
        )

    def test_nachschub_erhoeht_verkauft(self):
        beleg = Beleg.objects.create(
            datum="2026-06-10", gesamtbetrag=Decimal("30.00"), haendler="Getraenkemarkt"
        )
        BelegPosition.objects.create(
            beleg=beleg, getraenk=self.bier, anzahl=24, einzelpreis=Decimal("0.50")
        )
        self._ende_bestand(100, 40, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        # 100 Start + 24 Nachschub - 100 Ende - 0 Frei = 24 verkauft
        self.assertEqual(bier_pos.verkauft, 24)

    def test_freigetraenke_reduziert_verkauft(self):
        Freigetraenk.objects.create(
            getraenk=self.bier, datum="2026-06-05", anzahl=5, kommentar="Teamevent"
        )
        self._ende_bestand(40, 40, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        # 100 Start - 40 Ende - 5 Frei = 55 verkauft
        self.assertEqual(bier_pos.verkauft, 55)

    def test_nachschub_ausserhalb_zeitraum_wird_nicht_gezaehlt(self):
        beleg = Beleg.objects.create(
            datum="2026-05-20", gesamtbetrag=Decimal("30.00"), haendler="Getraenkemarkt"
        )
        BelegPosition.objects.create(
            beleg=beleg, getraenk=self.bier, anzahl=24, einzelpreis=Decimal("0.50")
        )
        self._ende_bestand(40, 40, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        self.assertEqual(bier_pos.verkauft, 60)

    def test_ist_kasse_beruecksichtigt_nur_markierte_paypal_zahlungen(self):
        PaypalZahlung.objects.create(
            datum="2026-06-12", betrag=Decimal("20.00"), zaehlung=self.ende,
            ist_getraenke_zahlung=True,
        )
        PaypalZahlung.objects.create(
            datum="2026-06-13", betrag=Decimal("99.00"), zaehlung=self.ende,
            ist_getraenke_zahlung=False,
        )
        self._ende_bestand(40, 40, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)

        self.assertEqual(ergebnis.paypal_getraenke, Decimal("20.00"))
        self.assertEqual(ergebnis.ist_kasse, Decimal("142.50") + Decimal("20.00"))

    def test_kassendifferenz_ohne_rundungstoleranz(self):
        self._ende_bestand(40, 40, 0, 20, 20, 0)
        # Soll: 60*1.50 + 30*1.00 = 120.00; Ist: 142.50 (Bargeld) -> Differenz 22.50
        ergebnis = berechne_auswertung(self.start, self.ende)
        self.assertEqual(ergebnis.soll_kasse, Decimal("120.00"))
        self.assertEqual(ergebnis.kassendifferenz, Decimal("22.50"))

    def test_leergut_differenz_negativ_bei_schwund(self):
        # Verkauft Bier = 60, erwartetes Leergut = 20 (start) + 60 - 0 (rueckgabe) = 80
        # tatsaechlich gezaehlt nur 70 -> Differenz -10 (Schwund)
        self._ende_bestand(40, 70, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        self.assertEqual(bier_pos.erwartetes_leergut, 80)
        self.assertEqual(bier_pos.leergut_differenz, -10)
        self.assertTrue(ergebnis.leergut_differenz_gesamt < 0)

    def test_leergut_differenz_positiv_bei_fund(self):
        # erwartetes Leergut = 80, tatsaechlich 85 -> +5 (Fremdleergut)
        self._ende_bestand(40, 85, 0, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        self.assertEqual(bier_pos.leergut_differenz, 5)

    def test_rueckgabe_an_markt_reduziert_erwartetes_leergut(self):
        # 20 Start + 60 verkauft - 30 Rueckgabe = 50 erwartet
        self._ende_bestand(40, 50, 30, 20, 20, 0)

        ergebnis = berechne_auswertung(self.start, self.ende)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        self.assertEqual(bier_pos.erwartetes_leergut, 50)
        self.assertEqual(bier_pos.leergut_differenz, 0)

    def test_gleiche_zaehlung_wirft_fehler(self):
        with self.assertRaises(AuswertungError):
            berechne_auswertung(self.start, self.start)

    def test_falsche_reihenfolge_wirft_fehler(self):
        with self.assertRaises(AuswertungError):
            berechne_auswertung(self.ende, self.start)


class MehrperiodenAuswertungTests(TestCase):
    """Deckt Zaehlungen ab, die zeitlich ZWISCHEN Start und Ende liegen
    (z.B. Monatsauswertung ueber mehrere Zaehlungen), inkl. der
    Bargeld-Entnahme-Logik (Kasse wird mal geleert, mal nicht)."""

    def setUp(self):
        self.bier = Getraenk.objects.create(
            name="Bier", warenpreis=Decimal("0.50"), pfand=Decimal("0.15"),
            verkaufspreis=Decimal("1.50"),
        )
        self.z1 = Zaehlung.objects.create(datum="2026-07-01", bargeld_gezaehlt=Decimal("0"))
        self.z2 = Zaehlung.objects.create(datum="2026-07-10", bargeld_gezaehlt=Decimal("100.00"))
        self.z3 = Zaehlung.objects.create(datum="2026-07-20", bargeld_gezaehlt=Decimal("115.00"))
        ZaehlungBestand.objects.create(
            zaehlung=self.z1, getraenk=self.bier, vollbestand_gezaehlt=100, leergut_gezaehlt=20
        )
        ZaehlungBestand.objects.create(
            zaehlung=self.z2, getraenk=self.bier, vollbestand_gezaehlt=60, leergut_gezaehlt=60
        )
        ZaehlungBestand.objects.create(
            zaehlung=self.z3, getraenk=self.bier, vollbestand_gezaehlt=20, leergut_gezaehlt=100
        )
        # Verkauft ueber den ganzen Zeitraum: 100 - 20 = 80 * 1.50 = 120.00

    def test_bargeld_akkumuliert_wenn_nie_entnommen(self):
        # Kasse wird nie geleert: Einnahmen = Endstand - Startstand
        ergebnis = berechne_auswertung(self.z1, self.z3)
        self.assertEqual(ergebnis.bargeld_einnahmen, Decimal("115.00"))
        self.assertEqual(ergebnis.bargeld_entnommen_zwischenzeitlich, Decimal("0"))

    def test_bargeld_wird_bei_zwischenzeitlicher_entnahme_addiert(self):
        # Bei z2 wird die Kasse komplett geleert (100 entnommen)
        self.z2.bargeld_entnommen = Decimal("100.00")
        self.z2.save()

        ergebnis = berechne_auswertung(self.z1, self.z3)

        # Einnahmen gesamt = 100 (bis z2 entnommen) + 15 (z3 - Rest von z2, der 0 ist)
        self.assertEqual(ergebnis.bargeld_entnommen_zwischenzeitlich, Decimal("100.00"))
        self.assertEqual(ergebnis.bargeld_einnahmen, Decimal("215.00"))

    def test_bargeld_entnahme_an_start_reduziert_basis(self):
        self.z1.bargeld_entnommen = Decimal("0")
        self.z1.save()
        self.z2.bargeld_entnommen = Decimal("50.00")
        self.z2.save()

        ergebnis = berechne_auswertung(self.z1, self.z3)

        # z1->z2: 100 - 0 = 100 eingenommen. Basis nach z2: 100 - 50 = 50
        # verbleiben in der Kasse. z2->z3: 115 - 50 = 65 eingenommen.
        # Gesamt: 100 + 65 = 165.
        self.assertEqual(ergebnis.bargeld_einnahmen, Decimal("165.00"))

    def test_rueckgabe_bei_zwischenzeitlicher_zaehlung_wird_beruecksichtigt(self):
        bestand_z2 = ZaehlungBestand.objects.get(zaehlung=self.z2, getraenk=self.bier)
        bestand_z2.rueckgabe_an_getraenkemarkt = 15
        bestand_z2.save()

        ergebnis = berechne_auswertung(self.z1, self.z3)
        bier_pos = next(p for p in ergebnis.positionen if p.getraenk == self.bier)

        self.assertEqual(bier_pos.rueckgabe_an_getraenkemarkt, 15)
        # Erwartetes Leergut = 20 (Start) + 80 (verkauft) - 15 (Rueckgabe) = 85
        self.assertEqual(bier_pos.erwartetes_leergut, 85)

    def test_paypal_bei_zwischenzeitlicher_zaehlung_wird_beruecksichtigt(self):
        PaypalZahlung.objects.create(
            datum="2026-07-11", betrag=Decimal("12.00"), zaehlung=self.z2,
            ist_getraenke_zahlung=True,
        )

        ergebnis = berechne_auswertung(self.z1, self.z3)

        self.assertEqual(ergebnis.paypal_getraenke, Decimal("12.00"))


class DifferenzZuordnungTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.bier = Getraenk.objects.create(
            name="Bier", warenpreis=Decimal("0.50"), pfand=Decimal("0.15"),
            verkaufspreis=Decimal("1.50"),
        )
        self.start = Zaehlung.objects.create(datum="2026-07-01", bargeld_gezaehlt=Decimal("0"))
        self.ende = Zaehlung.objects.create(datum="2026-07-10", bargeld_gezaehlt=Decimal("100.00"))
        ZaehlungBestand.objects.create(
            zaehlung=self.start, getraenk=self.bier, vollbestand_gezaehlt=100, leergut_gezaehlt=20
        )
        ZaehlungBestand.objects.create(
            zaehlung=self.ende, getraenk=self.bier, vollbestand_gezaehlt=40, leergut_gezaehlt=80
        )
        # Verkauft = 60 * 1.50 = 90 Soll; Ist = 100 -> Kassendifferenz = +10

    def test_zuordnung_ueber_view_erstellt_und_an_ende_zaehlung_gehaengt(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.post(
            reverse("kasse:auswertung"),
            {
                "start": self.start.pk,
                "ende": self.ende.pk,
                "kategorie": DifferenzZuordnung.Kategorie.NICHT_BEZAHLT,
                "betrag": "10.00",
                "kommentar": "Testfall",
            },
        )
        self.assertEqual(response.status_code, 302)
        zuordnungen = list(self.ende.differenz_zuordnungen.all())
        self.assertEqual(len(zuordnungen), 1)
        self.assertEqual(zuordnungen[0].kategorie, DifferenzZuordnung.Kategorie.NICHT_BEZAHLT)
        self.assertEqual(zuordnungen[0].betrag, Decimal("10.00"))

    def test_auswertung_zeigt_rest_offen(self):
        DifferenzZuordnung.objects.create(
            zaehlung=self.ende,
            kategorie=DifferenzZuordnung.Kategorie.NICHT_BEZAHLT,
            betrag=Decimal("4.00"),
        )
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:auswertung"), {"start": self.start.pk, "ende": self.ende.pk}
        )
        self.assertEqual(response.context["zuordnung_summe"], Decimal("4.00"))
        self.assertEqual(response.context["zuordnung_rest"], Decimal("6.00"))


class MonatsauswertungViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw12345678")
        self.bier = Getraenk.objects.create(
            name="Bier", warenpreis=Decimal("0.50"), pfand=Decimal("0.15"),
            verkaufspreis=Decimal("1.50"),
        )
        for datum, voll in [("2026-07-01", 100), ("2026-07-10", 60), ("2026-07-20", 20)]:
            z = Zaehlung.objects.create(datum=datum, bargeld_gezaehlt=Decimal("0"))
            ZaehlungBestand.objects.create(
                zaehlung=z, getraenk=self.bier, vollbestand_gezaehlt=voll, leergut_gezaehlt=0
            )
        Zaehlung.objects.create(datum="2026-06-15", bargeld_gezaehlt=Decimal("0"))

    def test_zeigt_nur_zaehlungen_des_gewaehlten_monats(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:monatsauswertung"), {"monat": "2026-07"}
        )
        self.assertEqual(len(response.context["zaehlungen"]), 3)
        self.assertTrue(
            all(z.datum.month == 7 for z in response.context["zaehlungen"])
        )

    def test_gesamtauswertung_nutzt_erste_und_letzte_zaehlung_im_monat(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:monatsauswertung"), {"monat": "2026-07"}
        )
        result = response.context["result"]
        self.assertIsNotNone(result)
        # 100 (erste Zaehlung) -> 20 (letzte Zaehlung) = 80 verkauft
        bier_pos = next(p for p in result.positionen if p.getraenk == self.bier)
        self.assertEqual(bier_pos.verkauft, 80)

    def test_ohne_zaehlungen_kein_ergebnis(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:monatsauswertung"), {"monat": "2026-01"}
        )
        self.assertIsNone(response.context["result"])
        self.assertEqual(len(response.context["zaehlungen"]), 0)


@override_settings(MEDIA_ROOT="/tmp/vertrauenskasse-test-media")
class MediaServeTests(TestCase):
    def setUp(self):
        import os

        os.makedirs("/tmp/vertrauenskasse-test-media/belege", exist_ok=True)
        with open("/tmp/vertrauenskasse-test-media/belege/beleg.pdf", "wb") as f:
            f.write(b"%PDF-1.4 test")
        self.user = User.objects.create_user(username="tester", password="pw12345678")

    def test_ohne_login_gibt_es_keinen_zugriff(self):
        response = self.client.get(
            reverse("kasse:media", kwargs={"path": "belege/beleg.pdf"})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_eingeloggter_nutzer_bekommt_die_datei(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:media", kwargs={"path": "belege/beleg.pdf"})
        )
        self.assertEqual(response.status_code, 200)

    def test_path_traversal_wird_verhindert(self):
        self.client.login(username="tester", password="pw12345678")
        response = self.client.get(
            reverse("kasse:media", kwargs={"path": "../settings.py"})
        )
        self.assertEqual(response.status_code, 404)
