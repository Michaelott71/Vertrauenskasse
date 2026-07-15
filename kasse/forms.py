from django import forms
from django.forms import modelformset_factory

from .models import DifferenzZuordnung, Zaehlung, ZaehlungBestand


class ZaehlungForm(forms.ModelForm):
    class Meta:
        model = Zaehlung
        fields = ["datum", "notiz", "bargeld_gezaehlt", "bargeld_entnommen"]
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notiz": forms.Textarea(attrs={"rows": 2}),
        }


def build_bestand_formset(anzahl_getraenke, data=None, queryset=None):
    """Erzeugt dynamisch ein Formset mit genau einer Zeile je (aktivem) Getraenk."""
    factory = modelformset_factory(
        ZaehlungBestand,
        fields=[
            "getraenk",
            "vollbestand_gezaehlt",
            "leergut_gezaehlt",
            "rueckgabe_an_getraenkemarkt",
        ],
        extra=anzahl_getraenke,
        widgets={"getraenk": forms.HiddenInput()},
    )
    if queryset is None:
        queryset = ZaehlungBestand.objects.none()
    return factory(data=data, queryset=queryset)


class AuswertungAuswahlForm(forms.Form):
    start = forms.ModelChoiceField(
        queryset=Zaehlung.objects.all(), label="Start-Zaehlung"
    )
    ende = forms.ModelChoiceField(
        queryset=Zaehlung.objects.all(), label="End-Zaehlung"
    )


class DifferenzZuordnungForm(forms.ModelForm):
    class Meta:
        model = DifferenzZuordnung
        fields = ["kategorie", "betrag", "kommentar"]


class MonatsauswahlForm(forms.Form):
    monat = forms.DateField(
        label="Monat",
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        input_formats=["%Y-%m"],
    )
