import calendar

from django import forms

from .models import Beleg, Kassenbewegung, PaypalZahlung, Zaehlung


class ZaehlungMetaForm(forms.ModelForm):
    """Die "Kopf"-Felder einer Zaehlung. Die eigentlichen Verbrauchswerte
    kommen aus den Kacheln und werden im View direkt aus dem POST gelesen, da
    ihre Anzahl von den aktiven Getraenken abhaengt. Das gezaehlte Bargeld wird
    bewusst erst im zweiten Schritt (nach Berechnung des Soll-Betrags)
    abgefragt, siehe BargeldBestaetigenForm."""

    class Meta:
        model = Zaehlung
        fields = ["datum", "notiz"]
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notiz": forms.Textarea(attrs={"rows": 2}),
        }


class BargeldBestaetigenForm(forms.ModelForm):
    """Zweiter Schritt einer Zaehlung: das Feld wird mit dem berechneten
    Soll-Betrag vorausgefuellt, der Nutzer bestaetigt ihn oder korrigiert ihn
    auf das tatsaechlich gezaehlte Bargeld."""

    bargeld_gezaehlt = forms.DecimalField(
        label="Gezähltes Bargeld",
        max_digits=9,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "inputmode": "decimal",
                "class": "betrag-input-gross",
            }
        ),
    )

    class Meta:
        model = Zaehlung
        fields = ["bargeld_gezaehlt"]


class DifferenzErklaerenForm(forms.ModelForm):
    """Erklaerung einer Kassendifferenz (z.B. Trinkgeld, per PayPal bezahlt):
    Notiz als Begruendung plus optional ein Korrekturbetrag, der die
    Kassendifferenz entsprechend sinken laesst (siehe README, Abschnitt
    "Kassendifferenz erklaeren")."""

    differenz_korrektur = forms.DecimalField(
        label="Erklärter Betrag",
        max_digits=9,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={"step": "0.01", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = Zaehlung
        fields = ["notiz", "differenz_korrektur"]
        widgets = {"notiz": forms.Textarea(attrs={"rows": 2})}

    def clean_differenz_korrektur(self):
        return self.cleaned_data.get("differenz_korrektur") or 0


class KassenbewegungForm(forms.ModelForm):
    art = forms.ChoiceField(
        label="Art", choices=Kassenbewegung.Art.choices, widget=forms.RadioSelect
    )

    class Meta:
        model = Kassenbewegung
        fields = ["art", "datum", "betrag", "rg_nummer", "notiz"]
        labels = {"rg_nummer": "RG-Nummer (nur bei fremdem Bargeldeingang)"}
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "betrag": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "inputmode": "decimal",
                    "class": "betrag-input-gross",
                }
            ),
        }


class BelegForm(forms.ModelForm):
    """Erfassung eines Einkaufsbelegs im Haupt-UI (ohne Admin). Nur der
    Gesamtbetrag fliesst in die Gewinn-Berechnung ein; einzelne Positionen
    koennen bei Bedarf weiterhin in der Verwaltung ergaenzt werden."""

    class Meta:
        model = Beleg
        fields = ["datum", "haendler", "gesamtbetrag", "dateipfad"]
        labels = {
            "gesamtbetrag": "Gesamtbetrag (Einkaufswert)",
            "haendler": "Händler",
            "dateipfad": "Beleg-Scan (optional)",
        }
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "gesamtbetrag": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "inputmode": "decimal",
                    "class": "betrag-input-gross",
                }
            ),
        }


class MonatsauswahlForm(forms.Form):
    monat = forms.DateField(
        label="Monat",
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        input_formats=["%Y-%m"],
    )


class PaypalZahlungForm(forms.ModelForm):
    """Manuelle Erfassung einer PayPal-Zahlung (z.B. aus dem PayPal-Export
    abgetippt). Die automatische Zuordnung laeuft beim Speichern im View."""

    class Meta:
        model = PaypalZahlung
        fields = ["datum", "betrag", "verwendungszweck", "paypal_transaktions_id"]
        labels = {"paypal_transaktions_id": "PayPal-Transaktions-ID"}
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "betrag": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        }


class PaypalKlaerungForm(forms.Form):
    ENTSCHEIDUNG_CHOICES = [
        ("ja", "Ja, Vertrauenskasse"),
        ("nein", "Nein, keine Vertrauenskasse"),
    ]

    zahlung_id = forms.IntegerField(widget=forms.HiddenInput)
    entscheidung = forms.ChoiceField(choices=ENTSCHEIDUNG_CHOICES, widget=forms.RadioSelect)
    kommentar = forms.CharField(required=False, max_length=255)


class ExportForm(forms.Form):
    monat = forms.DateField(
        label="Monat",
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        input_formats=["%Y-%m"],
    )
    aggregiert = forms.BooleanField(
        required=False,
        label="Als eine aggregierte Zeile pro Monat exportieren (statt je Zählung)",
    )
    mit_belegen = forms.BooleanField(
        required=False,
        initial=True,
        label="Hochgeladene Beleg-Scans als ZIP mit exportieren (zum Ausdrucken für den Steuerberater)",
    )
    bestaetigen = forms.BooleanField(
        label="Mir ist bewusst, dass nach dem Export Korrekturen für diesen Monat "
        "nicht mehr rückwirkend möglich sind."
    )

    def clean_monat(self):
        monat = self.cleaned_data["monat"]
        letzter_tag = calendar.monthrange(monat.year, monat.month)[1]
        return monat.replace(day=letzter_tag)
