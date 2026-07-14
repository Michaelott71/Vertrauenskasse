from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


def _naechste_nummer(queryset, prefix, jahr):
    """Ermittelt die naechste fortlaufende Nummer eines Jahres im Format
    ``PREFIX-JAHR-NNN`` (z.B. ``RE-2026-001``), indem die hoechste bereits
    vergebene laufende Nummer des Jahres gesucht und um 1 erhoeht wird.
    """
    praefix = f"{prefix}-{jahr}-"
    hoechste = 0
    for nummer in queryset.filter(nummer__startswith=praefix).values_list(
        "nummer", flat=True
    ):
        try:
            laufend = int(nummer.rsplit("-", 1)[-1])
        except ValueError:
            continue
        hoechste = max(hoechste, laufend)
    return f"{praefix}{hoechste + 1:03d}"


class Firmenprofil(models.Model):
    """Stammdaten fuer Briefkopf/Logo auf Rechnungen und Quittungen.

    Es wird genau ein Datensatz gepflegt (siehe ``get_solo``); als Model statt
    fixer Settings, damit Adresse/Logo bequem im Admin bearbeitbar sind.
    """

    name = models.CharField(max_length=200, default="")
    adresse = models.TextField(blank=True)
    steuernummer = models.CharField(max_length=50, blank=True)
    ust_idnr = models.CharField(max_length=50, blank=True)
    bank = models.CharField(max_length=100, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    bic = models.CharField(max_length=11, blank=True)
    logo = models.FileField(upload_to="firma/", blank=True)
    rechnung_fusszeile = models.TextField(
        blank=True, help_text="Freitext am Ende jeder Rechnung/Quittung (z.B. Zahlungsziel)"
    )

    class Meta:
        verbose_name = "Firmenprofil"
        verbose_name_plural = "Firmenprofil"

    def __str__(self):
        return self.name or "Firmenprofil"

    @classmethod
    def get_solo(cls):
        instanz, _ = cls.objects.get_or_create(pk=1)
        return instanz


class Konto(models.Model):
    """Bankkonto, dem Rechnungen/Quittungen zugeordnet werden koennen.

    Anzahl und genaue Kontenstruktur sind mit dem Steuerberater noch nicht
    final geklaert, daher bewusst als freie Liste statt fester Anzahl Felder.
    """

    bezeichnung = models.CharField(max_length=100, unique=True)
    iban = models.CharField(max_length=34, blank=True)
    kontonummer_datev = models.CharField(
        max_length=20,
        blank=True,
        help_text="Kontonummer im DATEV-Kontenrahmen fuer den Export (z.B. Bankkonto)",
    )
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["bezeichnung"]

    def __str__(self):
        return self.bezeichnung


class Artikel(models.Model):
    name = models.CharField(max_length=150, unique=True)
    beschreibung = models.TextField(blank=True)
    einzelpreis = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Netto-Einzelpreis"
    )
    mwst_satz = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("19.00"),
        help_text="MwSt-Satz in Prozent, individuell je Artikel",
    )
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Rechnung(models.Model):
    nummer = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    datum = models.DateField(default=date.today)
    kunde_name = models.CharField(max_length=200, blank=True)
    kunde_adresse = models.TextField(blank=True)
    konto = models.ForeignKey(
        Konto,
        on_delete=models.PROTECT,
        related_name="rechnungen",
        null=True,
        blank=True,
    )
    bezahlt = models.BooleanField(default=False)
    bezahlt_am = models.DateField(null=True, blank=True)
    notiz = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.nummer or f"Rechnung (Entwurf, {self.datum})"

    def save(self, *args, **kwargs):
        if not self.nummer:
            self.nummer = _naechste_nummer(
                Rechnung.objects.all(), "RE", self.datum.year
            )
        super().save(*args, **kwargs)

    @property
    def netto_summe(self):
        return sum((p.netto_summe for p in self.positionen.all()), Decimal("0"))

    @property
    def mwst_gesamt(self):
        return sum((p.mwst_betrag for p in self.positionen.all()), Decimal("0"))

    @property
    def brutto_summe(self):
        return self.netto_summe + self.mwst_gesamt

    @property
    def mwst_aufschluesselung(self):
        """Netto/MwSt/Brutto je vorkommendem MwSt-Satz, fuer den Rechnungsdruck."""
        aufschluesselung = {}
        for position in self.positionen.all():
            eintrag = aufschluesselung.setdefault(
                position.mwst_satz, {"netto": Decimal("0"), "mwst": Decimal("0")}
            )
            eintrag["netto"] += position.netto_summe
            eintrag["mwst"] += position.mwst_betrag
        return dict(sorted(aufschluesselung.items()))


class RechnungsPosition(models.Model):
    rechnung = models.ForeignKey(
        Rechnung, on_delete=models.CASCADE, related_name="positionen"
    )
    artikel = models.ForeignKey(
        Artikel,
        on_delete=models.PROTECT,
        related_name="rechnungspositionen",
        null=True,
        blank=True,
    )
    bezeichnung = models.CharField(max_length=200)
    menge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1"))
    einzelpreis = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Netto-Einzelpreis"
    )
    # Beim Anlegen aus dem Artikel-Satz uebernommen und danach eingefroren,
    # damit spaetere MwSt-Satz-Aenderungen am Artikel bereits geschriebene
    # Rechnungen nicht rueckwirkend veraendern.
    mwst_satz = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.menge}x {self.bezeichnung}"

    def save(self, *args, **kwargs):
        if not self.bezeichnung and self.artikel_id:
            self.bezeichnung = self.artikel.name
        if self.mwst_satz is None and self.artikel_id:
            self.mwst_satz = self.artikel.mwst_satz
        super().save(*args, **kwargs)

    @property
    def netto_summe(self):
        return self.menge * self.einzelpreis

    @property
    def mwst_betrag(self):
        return (self.netto_summe * self.mwst_satz / Decimal("100")).quantize(
            Decimal("0.01")
        )

    @property
    def brutto_summe(self):
        return self.netto_summe + self.mwst_betrag


class Quittung(models.Model):
    nummer = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    datum = models.DateField(default=date.today)
    name = models.CharField(
        max_length=200, blank=True, help_text="Optional, Quittung kann auch ohne Namen ausgestellt werden"
    )
    verwendungszweck = models.TextField(blank=True, help_text="Freier Verwendungszweck")
    betrag = models.DecimalField(max_digits=9, decimal_places=2)
    konto = models.ForeignKey(
        Konto,
        on_delete=models.PROTECT,
        related_name="quittungen",
        null=True,
        blank=True,
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.nummer or f"Quittung (Entwurf, {self.datum})"

    def save(self, *args, **kwargs):
        if not self.nummer:
            self.nummer = _naechste_nummer(
                Quittung.objects.all(), "Q", self.datum.year
            )
        super().save(*args, **kwargs)


class Gutschein(models.Model):
    TYP_FEST = "fest"
    TYP_PROZENT = "prozent"
    TYP_CHOICES = [
        (TYP_FEST, "Fester Betrag"),
        (TYP_PROZENT, "Prozentual"),
    ]

    GRUND_VERKAUF = "verkauf"
    GRUND_PREIS = "preis"
    GRUND_VERLOSUNG = "verlosung"
    GRUND_CHOICES = [
        (GRUND_VERKAUF, "Verkauf"),
        (GRUND_PREIS, "Preis"),
        (GRUND_VERLOSUNG, "Verlosungsgewinn"),
    ]

    code = models.CharField(max_length=30, unique=True)
    typ = models.CharField(max_length=10, choices=TYP_CHOICES, default=TYP_FEST)
    wert = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Euro-Betrag bei 'Fester Betrag', Prozentsatz bei 'Prozentual'",
    )
    ausgestellt_am = models.DateField(default=date.today)
    ablaufdatum = models.DateField(null=True, blank=True)
    grund = models.CharField(max_length=10, choices=GRUND_CHOICES, default=GRUND_VERKAUF)
    notiz = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-ausgestellt_am", "-id"]

    def __str__(self):
        return self.code

    @property
    def eingeloest_betrag(self):
        return sum(
            (e.betrag for e in self.einloesungen.all()), Decimal("0")
        )

    @property
    def restguthaben(self):
        """Nur fuer feste Betraege sinnvoll: verbleibendes Guthaben ueber
        mehrere Teil-Einloesungen hinweg. Prozentuale Gutscheine gelten je
        Einloesung als vollstaendig verwendet.
        """
        if self.typ != self.TYP_FEST:
            return None
        return self.wert - self.eingeloest_betrag

    @property
    def ist_abgelaufen(self):
        return bool(self.ablaufdatum and self.ablaufdatum < date.today())

    @property
    def status(self):
        if self.ist_abgelaufen:
            return "abgelaufen"
        if self.typ == self.TYP_FEST:
            if self.restguthaben is not None and self.restguthaben <= 0:
                return "eingeloest"
        elif self.einloesungen.exists():
            return "eingeloest"
        return "aktiv"


class GutscheinEinloesung(models.Model):
    gutschein = models.ForeignKey(
        Gutschein, on_delete=models.CASCADE, related_name="einloesungen"
    )
    rechnung = models.ForeignKey(
        Rechnung,
        on_delete=models.PROTECT,
        related_name="gutschein_einloesungen",
        null=True,
        blank=True,
    )
    quittung = models.ForeignKey(
        Quittung,
        on_delete=models.PROTECT,
        related_name="gutschein_einloesungen",
        null=True,
        blank=True,
    )
    datum = models.DateField(default=date.today)
    betrag = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Eingeloester Euro-Wert bei dieser Buchung"
    )

    class Meta:
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.betrag} EUR von {self.gutschein} am {self.datum}"


class ZahlungsdienstleisterGebuehr(models.Model):
    """Gebuehr eines Zahlungsdienstleisters (Anbieter noch offen) zu einer
    Rechnung oder Quittung. Der volle Betrag wird regulaer verbucht, die
    Gebuehr separat als eigener Aufwandsposten (siehe Buchungslogik/DATEV-Export).
    """

    rechnung = models.ForeignKey(
        Rechnung,
        on_delete=models.CASCADE,
        related_name="gebuehren",
        null=True,
        blank=True,
    )
    quittung = models.ForeignKey(
        Quittung,
        on_delete=models.CASCADE,
        related_name="gebuehren",
        null=True,
        blank=True,
    )
    anbieter = models.CharField(
        max_length=100, blank=True, help_text="z.B. PayPal, SumUp, Stripe (Anbieter noch offen)"
    )
    bruttobetrag = models.DecimalField(
        max_digits=9, decimal_places=2, help_text="Voller eingegangener Betrag"
    )
    gebuehr = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Vom Anbieter einbehaltene Gebuehr"
    )
    datum = models.DateField(default=date.today)

    class Meta:
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"Gebuehr {self.gebuehr} EUR ({self.anbieter}) am {self.datum}"

    def clean(self):
        if bool(self.rechnung_id) == bool(self.quittung_id):
            raise ValidationError(
                "Eine Zahlungsdienstleister-Gebuehr muss genau einer Rechnung "
                "oder einer Quittung zugeordnet sein (nicht beiden, nicht keinem)."
            )
