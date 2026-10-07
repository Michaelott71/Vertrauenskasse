import calendar

from django import forms

from .models import Kassenbewegung, PaypalZahlung, Zaehlung


class ZaehlungMetaForm(forms.ModelForm):
    """Die "Kopf"-Felder einer Zaehlung. Die eigentlichen Bestandswerte kommen
    aus den Kacheln und werden im View direkt aus dem POST gelesen, da ihre
    Anzahl von den aktiven Getraenken abhaengt."""

    class Meta:
        model = Zaehlung
        fields = ["datum", "notiz", "bargeld_gezaehlt"]
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notiz": forms.Textarea(attrs={"rows": 2}),
            "bargeld_gezaehlt": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "inputmode": "decimal",
                    "class": "betrag-input-gross",
                }
            ),
        }


class AuffuellungMetaForm(forms.Form):
    """Datum fuer eine Auffuellungs-Erfassung; die Mengen je Artikel kommen aus
    den Kacheln und werden im View direkt aus dem POST gelesen."""

    datum = forms.DateField(
        label="Datum",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )


class FreigetraenkMetaForm(forms.Form):
    """Datum/Kommentar fuer eine Freigetraenke-Erfassung; die Mengen je Artikel
    kommen aus den Kacheln und werden im View direkt aus dem POST gelesen."""

    datum = forms.DateField(
        label="Datum",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    kommentar = forms.CharField(label="Kommentar", required=False, max_length=255)


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


class AuswertungAuswahlForm(forms.Form):
    start = forms.ModelChoiceField(
        queryset=Zaehlung.objects.all(), label="Start-Zählung"
    )
    ende = forms.ModelChoiceField(
        queryset=Zaehlung.objects.all(), label="End-Zählung"
    )


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
    bestaetigen = forms.BooleanField(
        label="Mir ist bewusst, dass nach dem Export Korrekturen für diesen Monat "
        "nicht mehr rückwirkend möglich sind."
    )

    def clean_monat(self):
        monat = self.cleaned_data["monat"]
        letzter_tag = calendar.monthrange(monat.year, monat.month)[1]
        return monat.replace(day=letzter_tag)
