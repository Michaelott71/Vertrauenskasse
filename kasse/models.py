from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


def ist_monat_exportiert(datum):
    """True, wenn fuer den Monat von `datum` bereits ein CSV-Export erstellt wurde.

    Ab diesem Zeitpunkt gelten Korrekturen (Freigetraenke, Bestandskorrekturen, ...)
    fuer diesen Monat nicht mehr rueckwirkend, siehe README.
    """
    return MonatsExport.objects.filter(jahr=datum.year, monat=datum.month).exists()


class GesperrterMonatError(ValidationError):
    pass


def pruefe_monat_nicht_exportiert(datum, was="Diese Korrektur"):
    if ist_monat_exportiert(datum):
        raise GesperrterMonatError(
            f"{was} faellt in {datum.month:02d}/{datum.year}, ein bereits als CSV "
            "exportierter Monat. Nachtraege fuer exportierte Monate sind nicht mehr "
            "rueckwirkend moeglich, sondern muessen als Vermerk im aktuellen Monat "
            "erfasst werden."
        )


class Getraenk(models.Model):
    name = models.CharField(max_length=100, unique=True)
    warenpreis = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Einkaufspreis pro Einheit (reiner Warenpreis ohne Pfand)",
    )
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
    belegnummer = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Wird automatisch im Format VK-JJJJ-MM-NN vergeben.",
    )
    # Nicht im urspruenglichen Schema, aber ohne dieses Feld liesse sich die
    # geforderte Formel "Ist-Kasse = gezaehltes Bargeld + PayPal-Zahlungen"
    # nicht berechnen: das tatsaechlich gezaehlte Bargeld muss irgendwo erfasst
    # werden. Siehe README, Abschnitt "Abweichungen vom Datenmodell".
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
        return self.belegnummer or f"Zaehlung vom {self.datum}"

    def clean(self):
        if self.datum:
            datum = self.datum
            if isinstance(datum, str):
                from django.utils.dateparse import parse_date

                datum = parse_date(datum)
            pruefe_monat_nicht_exportiert(datum, "Eine Änderung an dieser Zählung")

    def _naechste_laufende_nummer(self):
        vorhandene = Zaehlung.objects.filter(
            datum__year=self.datum.year, datum__month=self.datum.month
        ).exclude(pk=self.pk)
        return vorhandene.count() + 1

    def save(self, *args, **kwargs):
        if isinstance(self.datum, str):
            from django.utils.dateparse import parse_date

            self.datum = parse_date(self.datum)
        if not self.belegnummer:
            nr = self._naechste_laufende_nummer()
            self.belegnummer = f"VK-{self.datum.year:04d}-{self.datum.month:02d}-{nr:02d}"
        super().save(*args, **kwargs)


class ZaehlungVerbrauch(models.Model):
    """Wie viel von einem Artikel seit der letzten Zählung verbraucht/verkauft
    wurde – direkt eingetragen, kein Bestand wird gezählt oder verglichen."""

    zaehlung = models.ForeignKey(
        Zaehlung, on_delete=models.CASCADE, related_name="verbraeuche"
    )
    getraenk = models.ForeignKey(
        Getraenk, on_delete=models.PROTECT, related_name="verbraeuche"
    )
    verbraucht = models.PositiveIntegerField(
        help_text="Wie viele wurden seit der letzten Zählung verkauft/verbraucht?"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["zaehlung", "getraenk"], name="unique_zaehlung_getraenk"
            )
        ]
        ordering = ["zaehlung", "getraenk"]
        verbose_name = "Zählungsverbrauch"
        verbose_name_plural = "Zählungsverbräuche"

    def __str__(self):
        return f"{self.getraenk} @ {self.zaehlung}"

    def clean(self):
        if self.zaehlung_id:
            pruefe_monat_nicht_exportiert(
                self.zaehlung.datum, "Eine Verbrauchskorrektur"
            )


class Beleg(models.Model):
    """Einkaufsbeleg. Gilt immer automatisch als private Einlage von Nick –
    es gibt bewusst kein "Bezahlt von"-Feld, da der Einkauf nie aus der
    Vertrauenskasse selbst bezahlt wird. Rein dokumentarisch (Wareneinsatz),
    fließt nicht in die Kassenformel ein."""

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
    einzelpreis = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Nur der Warenpreis laut Quittung, ohne Pfand-Anteil (Pfand "
        "steht auf der Quittung meist als eigene Zeile und wird nicht erfasst).",
    )

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

    def clean(self):
        if self.datum:
            pruefe_monat_nicht_exportiert(self.datum, "Ein nachgetragenes Freigetränk")


class Kassenbewegung(models.Model):
    """Bargeldbewegungen der Kasse ohne Bezug zum Getränkeverkauf: der
    Kassenanfangssaldo/Wechselgeld (Einlage), Geld das herausgenommen wird
    (Entnahme), oder fremdes Bargeld, das nichts mit Getränken zu tun hat
    (z.B. eine bar bezahlte Platzstunde). Fließen nur in die Bar-Einnahmen-
    Formel ein (siehe services.py), sind aber keine Erlöse und tauchen daher
    NICHT im CSV-Monatsexport auf."""

    class Art(models.TextChoices):
        EINLAGE = "einlage", "Einlage (Privateinlage)"
        ENTNAHME = "entnahme", "Entnahme"
        FREMDER_BARGELDEINGANG = "fremder_bargeldeingang", "Fremder Bargeldeingang"

    art = models.CharField(max_length=30, choices=Art.choices)
    datum = models.DateField()
    betrag = models.DecimalField(max_digits=9, decimal_places=2)
    rg_nummer = models.CharField(
        max_length=50,
        blank=True,
        help_text="Nur bei 'Fremder Bargeldeingang': Verweis auf die "
        "Rechnungsnummer aus dem Rechnungsprogramm (keine Texterkennung in "
        "dieser Version – die Vertrauenskasse erstellt selbst keine Rechnungen "
        "und vergibt nur ihre eigenen VK-Nummern).",
    )
    notiz = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-datum", "-id"]
        verbose_name = "Kassenbewegung"
        verbose_name_plural = "Kassenbewegungen"

    def __str__(self):
        return f"{self.get_art_display()}: {self.betrag} EUR am {self.datum}"

    def clean(self):
        if self.datum:
            pruefe_monat_nicht_exportiert(self.datum, "Eine Kassenbewegung")


class PaypalZahlung(models.Model):
    datum = models.DateField()
    betrag = models.DecimalField(max_digits=9, decimal_places=2)
    zaehlung = models.ForeignKey(
        Zaehlung,
        on_delete=models.SET_NULL,
        related_name="paypal_zahlungen",
        null=True,
        blank=True,
        help_text="Wird beim monatlichen Abgleich anhand des Datums automatisch gesetzt.",
    )
    # Nicht im urspruenglichen Schema, aber als Eingabe fuer die automatische
    # Zuordnung (Stichwortliste, RG-Nummer, fester Verwendungszweck) unverzichtbar.
    verwendungszweck = models.CharField(
        max_length=255,
        blank=True,
        help_text="Betreff/Verwendungszweck aus dem PayPal-Export, Basis der Auto-Zuordnung.",
    )
    ist_getraenke_zahlung = models.BooleanField(
        null=True,
        blank=True,
        help_text="Ja/Nein = entschieden. Leer = ungeklaert (Klaerungsliste).",
    )
    zuordnungsgrund = models.CharField(
        max_length=255,
        blank=True,
        help_text="Von der automatischen Zuordnung gesetzt oder manuell dokumentiert.",
    )
    paypal_transaktions_id = models.CharField(max_length=64, unique=True)

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

    @property
    def ist_geklaert(self):
        return self.ist_getraenke_zahlung is not None


class PaypalStichwort(models.Model):
    """Erweiterbare Stichwortliste fuer die automatische PayPal-Zuordnung.
    Nicht Teil des urspruenglich vorgegebenen Schemas, aber noetig, um die
    geforderte "Stichwortliste (... erweiterbar)" ueberhaupt zu speichern."""

    wort = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["wort"]
        verbose_name = "PayPal-Stichwort"
        verbose_name_plural = "PayPal-Stichwörter"

    def __str__(self):
        return self.wort


class MonatsExport(models.Model):
    """Merkt sich, welche Monate bereits als CSV exportiert wurden, um die
    Regel "Korrekturen nur bis zum Export rueckwirkend moeglich" durchzusetzen.
    Nicht Teil des urspruenglich vorgegebenen Schemas."""

    jahr = models.PositiveIntegerField()
    monat = models.PositiveSmallIntegerField()
    exportiert_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["jahr", "monat"], name="unique_monat_export")
        ]
        ordering = ["-jahr", "-monat"]
        verbose_name = "Monatsexport"
        verbose_name_plural = "Monatsexporte"

    def __str__(self):
        return f"Export {self.monat:02d}/{self.jahr} am {self.exportiert_am:%d.%m.%Y}"
