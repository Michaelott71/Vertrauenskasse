import calendar
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from . import matching
from .export import erzeuge_csv, markiere_als_exportiert
from .forms import (
    AuswertungAuswahlForm,
    ExportForm,
    MonatsauswahlForm,
    PaypalKlaerungForm,
    PaypalZahlungForm,
    ZaehlungMetaForm,
)
from .models import (
    Getraenk,
    MonatsExport,
    Pfandkategorie,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
    ZaehlungLeergut,
)
from .services import AuswertungError, berechne_auswertung


def _int_aus_post(data, key):
    try:
        wert = int(data.get(key, "0") or "0")
    except (TypeError, ValueError):
        wert = 0
    return max(wert, 0)


def _kategorien_mit_aktiven_getraenken():
    ergebnis = []
    for kategorie in Pfandkategorie.objects.order_by("name"):
        artikel = list(kategorie.getraenke.filter(aktiv=True).order_by("name"))
        if artikel:
            ergebnis.append((kategorie, artikel))
    return ergebnis


@login_required
def home(request):
    zaehlungen = Zaehlung.objects.all()[:10]
    offene_paypal = matching.klaerungsliste().count()
    return render(
        request,
        "kasse/home.html",
        {"zaehlungen": zaehlungen, "offene_paypal": offene_paypal},
    )


@login_required
def zaehlung_neu(request):
    kategorien = _kategorien_mit_aktiven_getraenken()
    snacks = list(
        Getraenk.objects.filter(aktiv=True, pfandkategorie__isnull=True).order_by("name")
    )

    if not kategorien and not snacks:
        messages.info(
            request,
            "Es sind noch keine aktiven Getränke angelegt. Bitte zuerst in der "
            "Verwaltung ein Getränk anlegen.",
        )
        return render(request, "kasse/zaehlung_form.html", {"keine_artikel": True})

    if request.method == "POST":
        meta_form = ZaehlungMetaForm(request.POST)
        if meta_form.is_valid():
            with transaction.atomic():
                zaehlung = meta_form.save()
                for kategorie, artikel_liste in kategorien:
                    for getraenk in artikel_liste:
                        ZaehlungBestand.objects.create(
                            zaehlung=zaehlung,
                            getraenk=getraenk,
                            vollbestand_gezaehlt=_int_aus_post(
                                request.POST, f"bestand_{getraenk.id}"
                            ),
                        )
                    ZaehlungLeergut.objects.create(
                        zaehlung=zaehlung,
                        pfandkategorie=kategorie,
                        leergut_gezaehlt=_int_aus_post(
                            request.POST, f"leergut_{kategorie.id}"
                        ),
                        rueckgabe_an_getraenkemarkt=_int_aus_post(
                            request.POST, f"rueckgabe_{kategorie.id}"
                        ),
                    )
                for getraenk in snacks:
                    ZaehlungBestand.objects.create(
                        zaehlung=zaehlung,
                        getraenk=getraenk,
                        vollbestand_gezaehlt=_int_aus_post(
                            request.POST, f"bestand_{getraenk.id}"
                        ),
                    )
            messages.success(
                request, f"Zählung {zaehlung.belegnummer} wurde gespeichert."
            )
            return redirect(reverse("kasse:home"))
    else:
        meta_form = ZaehlungMetaForm(initial={"datum": timezone.localdate()})

    return render(
        request,
        "kasse/zaehlung_form.html",
        {
            "meta_form": meta_form,
            "kategorien": kategorien,
            "snacks": snacks,
        },
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

    return render(
        request,
        "kasse/auswertung.html",
        {
            "form": form,
            "result": result,
            "error": error,
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

    bereits_exportiert = MonatsExport.objects.filter(
        jahr=monat_start.year, monat=monat_start.month
    ).exists()

    return render(
        request,
        "kasse/monatsauswertung.html",
        {
            "monat_form": monat_form,
            "monat_start": monat_start,
            "zaehlungen": zaehlungen_im_monat,
            "result": result,
            "error": error,
            "bereits_exportiert": bereits_exportiert,
        },
    )


@login_required
def paypal_abgleich(request):
    if request.method == "POST" and request.POST.get("formular") == "neu":
        neu_form = PaypalZahlungForm(request.POST)
        if neu_form.is_valid():
            zahlung = neu_form.save(commit=False)
            matching.ordne_zahlung_zu(zahlung)
            zahlung.save()
            if zahlung.ist_getraenke_zahlung:
                zahlung.zaehlung = matching.ordne_zaehlung_zu(zahlung)
                zahlung.save()
            messages.success(
                request,
                f"PayPal-Zahlung erfasst: {zahlung.zuordnungsgrund}",
            )
            return redirect(reverse("kasse:paypal_abgleich"))
    else:
        neu_form = PaypalZahlungForm(initial={"datum": timezone.localdate()})

    if request.method == "POST" and request.POST.get("formular") == "entscheidung":
        klaerung_form = PaypalKlaerungForm(request.POST)
        if klaerung_form.is_valid():
            zahlung = get_object_or_404(
                PaypalZahlung,
                pk=klaerung_form.cleaned_data["zahlung_id"],
            )
            matching.entscheide_manuell(
                zahlung,
                klaerung_form.cleaned_data["entscheidung"] == "ja",
                klaerung_form.cleaned_data["kommentar"],
            )
            messages.success(request, "Entscheidung gespeichert.")
            return redirect(reverse("kasse:paypal_abgleich"))

    offene = matching.klaerungsliste()
    return render(
        request,
        "kasse/paypal_abgleich.html",
        {"neu_form": neu_form, "offene": offene},
    )


@login_required
def export_csv(request):
    bereits_exportiert = MonatsExport.objects.order_by("-jahr", "-monat")[:12]

    if request.method == "POST":
        form = ExportForm(request.POST)
        if form.is_valid():
            monat_letzter_tag = form.cleaned_data["monat"]
            jahr, monat = monat_letzter_tag.year, monat_letzter_tag.month
            dateiname, csv_text, warnungen = erzeuge_csv(
                jahr, monat, aggregiert=form.cleaned_data["aggregiert"]
            )
            markiere_als_exportiert(jahr, monat)
            for warnung in warnungen:
                messages.warning(request, warnung)
            response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{dateiname}"'
            return response
    else:
        form = ExportForm(initial={"monat": timezone.localdate().replace(day=1)})

    return render(
        request,
        "kasse/export.html",
        {"form": form, "bereits_exportiert": bereits_exportiert},
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
