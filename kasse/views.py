import calendar
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AuswertungAuswahlForm,
    DifferenzZuordnungForm,
    MonatsauswahlForm,
    ZaehlungForm,
    build_bestand_formset,
)
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
    zuordnungen = []
    zuordnung_summe = Decimal("0")

    if request.method == "POST":
        start_id = request.POST.get("start")
        ende_id = request.POST.get("ende")
        zuordnung_form = DifferenzZuordnungForm(request.POST)
        if start_id and ende_id and zuordnung_form.is_valid():
            ende = get_object_or_404(Zaehlung, pk=ende_id)
            zuordnung = zuordnung_form.save(commit=False)
            zuordnung.zaehlung = ende
            zuordnung.save()
            messages.success(request, "Differenz-Zuordnung wurde gespeichert.")
            return redirect(
                f"{reverse('kasse:auswertung')}?start={start_id}&ende={ende_id}"
            )
    else:
        start_id = request.GET.get("start")
        ende_id = request.GET.get("ende")
        zuordnung_form = DifferenzZuordnungForm()

    initial = {}
    if start_id and ende_id:
        initial = {"start": start_id, "ende": ende_id}
    else:
        letzte = list(zaehlungen[:2])
        if len(letzte) == 2:
            initial = {"start": letzte[1].pk, "ende": letzte[0].pk}

    selection_data = {"start": start_id, "ende": ende_id} if start_id and ende_id else None
    form = AuswertungAuswahlForm(selection_data, initial=initial)
    form.fields["start"].queryset = zaehlungen
    form.fields["ende"].queryset = zaehlungen

    if start_id and ende_id:
        start = get_object_or_404(Zaehlung, pk=start_id)
        ende = get_object_or_404(Zaehlung, pk=ende_id)
        try:
            result = berechne_auswertung(start, ende)
        except AuswertungError as exc:
            error = str(exc)
        else:
            zuordnungen = list(ende.differenz_zuordnungen.all())
            zuordnung_summe = sum((z.betrag for z in zuordnungen), Decimal("0"))

    return render(
        request,
        "kasse/auswertung.html",
        {
            "form": form,
            "result": result,
            "error": error,
            "zuordnungen": zuordnungen,
            "zuordnung_summe": zuordnung_summe,
            "zuordnung_rest": (result.kassendifferenz - zuordnung_summe) if result else None,
            "zuordnung_form": zuordnung_form,
            "start_id": start_id,
            "ende_id": ende_id,
        },
    )


@login_required
def monatsauswertung(request):
    heute = timezone.localdate()
    monat_form = MonatsauswahlForm(
        request.GET or None, initial={"monat": heute.replace(day=1)}
    )

    monat_start = heute.replace(day=1)
    if monat_form.is_valid():
        monat_start = monat_form.cleaned_data["monat"].replace(day=1)
    letzter_tag = calendar.monthrange(monat_start.year, monat_start.month)[1]
    monat_ende = monat_start.replace(day=letzter_tag)

    zaehlungen_im_monat = list(
        Zaehlung.objects.filter(datum__gte=monat_start, datum__lte=monat_ende).order_by(
            "datum", "id"
        )
    )
    for vorherige, aktuelle in zip(zaehlungen_im_monat, zaehlungen_im_monat[1:]):
        aktuelle.vorherige_id = vorherige.pk

    result = None
    error = None
    if len(zaehlungen_im_monat) >= 2:
        try:
            result = berechne_auswertung(zaehlungen_im_monat[0], zaehlungen_im_monat[-1])
        except AuswertungError as exc:
            error = str(exc)

    return render(
        request,
        "kasse/monatsauswertung.html",
        {
            "monat_form": monat_form,
            "monat_start": monat_start,
            "zaehlungen": zaehlungen_im_monat,
            "result": result,
            "error": error,
        },
    )


@login_required
def media_serve(request, path):
    """Liefert hochgeladene Belege nur fuer angemeldete Nutzer aus.

    Ersetzt Djangos DEBUG-only static()-Helper, damit Beleg-Scans nicht
    unauthentifiziert ueber den Reverse Proxy abrufbar sind.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    target = (media_root / path).resolve()
    if media_root not in target.parents or not target.is_file():
        raise Http404
    return FileResponse(target.open("rb"))
