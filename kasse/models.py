from django.core.exceptions import ValidationError
from django.db import models


class Getraenk(models.Model):
    name = models.CharField(max_length=100, unique=True)
    warenpreis = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Einkaufspreis pro Einheit"
    )
    pfand = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    verkaufspreis = models.DecimalField(max_digits=8, decimal_places=2)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Getränk"
        verbose_name_plural = "Getränke"

    def __str__(self):
        return self.name


class Zaehlung(models.Model):
    datum = models.DateField()
    notiz = models.TextField(blank=True)
    # Zusaetzlich zum vorgegebenen Datenmodell: das gezaehlte Bargeld muss
    # irgendwo erfasst werden, da es fuer die Ist-Kasse-Berechnung benoetigt
    # wird, im Modell aber sonst kein Feld dafuer vorgesehen ist.
    bargeld_gezaehlt = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Gezaehltes Bargeld in der Kasse bei dieser Zaehlung",
    )

    class Meta:
        ordering = ["-datum", "-id"]
        verbose_name = "Zählung"
        verbose_name_plural = "Zählungen"

    def __str__(self):
        return f"Zaehlung vom {self.datum}"


class ZaehlungBestand(models.Model):
    zaehlung = models.ForeignKey(
        Zaehlung, on_delete=models.CASCADE, related_name="bestaende"
    )
    getraenk = models.ForeignKey(
        Getraenk, on_delete=models.PROTECT, related_name="bestaende"
    )
    vollbestand_gezaehlt = models.PositiveIntegerField()
    leergut_gezaehlt = models.PositiveIntegerField()
    rueckgabe_an_getraenkemarkt = models.PositiveIntegerField(
        default=0,
        help_text="Anzahl Leergut seit der letzten Zaehlung an den Getraenkemarkt zurueckgegeben",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["zaehlung", "getraenk"], name="unique_zaehlung_getraenk"
            )
        ]
        ordering = ["zaehlung", "getraenk"]
        verbose_name = "Zählungsbestand"
        verbose_name_plural = "Zählungsbestände"

    def __str__(self):
        return f"{self.getraenk} @ {self.zaehlung}"


class Beleg(models.Model):
    datum = models.DateField()
    dateipfad = models.FileField(upload_to="belege/%Y/%m/", blank=True)
    gesamtbetrag = models.DecimalField(max_digits=9, decimal_places=2)
    haendler = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-datum", "-id"]
        verbose_name = "Beleg"
        verbose_name_plural = "Belege"

    def __str__(self):
        return f"Beleg {self.haendler} vom {self.datum}"


class BelegPosition(models.Model):
    beleg = models.ForeignKey(
        Beleg, on_delete=models.CASCADE, related_name="positionen"
    )
    getraenk = models.ForeignKey(
        Getraenk, on_delete=models.PROTECT, related_name="belegpositionen"
    )
    anzahl = models.PositiveIntegerField()
    einzelpreis = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Belegposition"
        verbose_name_plural = "Belegpositionen"

    def __str__(self):
        return f"{self.anzahl}x {self.getraenk} ({self.beleg})"


class Freigetraenk(models.Model):
    getraenk = models.ForeignKey(
        Getraenk, on_delete=models.PROTECT, related_name="freigetraenke"
    )
    datum = models.DateField()
    anzahl = models.PositiveIntegerField()
    kommentar = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-datum", "-id"]
        verbose_name = "Freigetränk"
        verbose_name_plural = "Freigetränke"

    def __str__(self):
        return f"{self.anzahl}x {self.getraenk} frei am {self.datum}"


class PaypalZahlung(models.Model):
    datum = models.DateField()
    betrag = models.DecimalField(max_digits=9, decimal_places=2)
    zaehlung = models.ForeignKey(
        Zaehlung,
        on_delete=models.SET_NULL,
        related_name="paypal_zahlungen",
        null=True,
        blank=True,
    )
    ist_getraenke_zahlung = models.BooleanField(
        default=False,
        help_text="Nur als 'Getraenke-Zahlung' markierte Betraege fliessen in die Ist-Kasse ein",
    )

    class Meta:
        ordering = ["-datum", "-id"]
        verbose_name = "PayPal-Zahlung"
        verbose_name_plural = "PayPal-Zahlungen"

    def __str__(self):
        return f"PayPal {self.betrag} EUR am {self.datum}"

    def clean(self):
        if self.ist_getraenke_zahlung and self.zaehlung_id is None:
            raise ValidationError(
                "Eine als Getraenke-Zahlung markierte PayPal-Zahlung muss "
                "einer Zaehlung zugeordnet sein."
            )
