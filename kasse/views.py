from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import AuswertungAuswahlForm, ZaehlungForm, build_bestand_formset
from .models import Getraenk, Zaehlung
from .services import AuswertungError, berechne_auswertung


@login_required
def home(request):
    zaehlungen = Zaehlung.objects.all()[:10]
    return render(request, "kasse/home.html", {"zaehlungen": zaehlungen})


@login_required
def zaehlung_neu(request):
    aktive_getraenke = list(Getraenk.objects.filter(aktiv=True))

    if request.method == "POST":
        zaehlung_form = ZaehlungForm(request.POST)
        formset = build_bestand_formset(len(aktive_getraenke), data=request.POST)
        if zaehlung_form.is_valid() and formset.is_valid():
            zaehlung = zaehlung_form.save()
            bestaende = formset.save(commit=False)
            for bestand in bestaende:
                bestand.zaehlung = zaehlung
                bestand.save()
            messages.success(request, "Zaehlung wurde gespeichert.")
            return redirect(reverse("kasse:home"))
    else:
        zaehlung_form = ZaehlungForm()
        formset = build_bestand_formset(len(aktive_getraenke))
        for form, getraenk in zip(formset.forms, aktive_getraenke):
            form.initial["getraenk"] = getraenk.pk

    for form, getraenk in zip(formset.forms, aktive_getraenke):
        form.getraenk_name = getraenk.name

    return render(
        request,
        "kasse/zaehlung_form.html",
        {"zaehlung_form": zaehlung_form, "formset": formset},
    )


@login_required
def auswertung(request):
    zaehlungen = Zaehlung.objects.all()
    result = None
    error = None

    start_id = request.GET.get("start")
    ende_id = request.GET.get("ende")
    initial = {}
    if start_id and ende_id:
        initial = {"start": start_id, "ende": ende_id}
    else:
        letzte = list(zaehlungen[:2])
        if len(letzte) == 2:
            initial = {"start": letzte[1].pk, "ende": letzte[0].pk}

    form = AuswertungAuswahlForm(request.GET or None, initial=initial)
    form.fields["start"].queryset = zaehlungen
    form.fields["ende"].queryset = zaehlungen

    if start_id and ende_id:
        start = get_object_or_404(Zaehlung, pk=start_id)
        ende = get_object_or_404(Zaehlung, pk=ende_id)
        try:
            result = berechne_auswertung(start, ende)
        except AuswertungError as exc:
            error = str(exc)

    return render(
        request,
        "kasse/auswertung.html",
        {"form": form, "result": result, "error": error},
    )
