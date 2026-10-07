import calendar
from decimal import Decimal
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
    BelegForm,
    ExportForm,
    FreigetraenkMetaForm,
    KassenbewegungForm,
    MonatsauswahlForm,
    PaypalKlaerungForm,
    PaypalZahlungForm,
    ZaehlungMetaForm,
)
from .models import (
    Beleg,
    Freigetraenk,
    GesperrterMonatError,
    Getraenk,
    Kassenbewegung,
    MonatsExport,
    PaypalZahlung,
    Zaehlung,
    ZaehlungVerbrauch,
    pruefe_monat_nicht_exportiert,
)
from .services import berechne_auswertung, berechne_zeitraum


def _int_aus_post(data, key):
    try:
        wert = int(data.get(key, "0") or "0")
    except (TypeError, ValueError):
        wert = 0
    return max(wert, 0)


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
    artikel = list(Getraenk.objects.filter(aktiv=True).order_by("name"))

    if not artikel:
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
                for getraenk in artikel:
                    ZaehlungVerbrauch.objects.create(
                        zaehlung=zaehlung,
                        getraenk=getraenk,
                        verbraucht=_int_aus_post(
                            request.POST, f"verbraucht_{getraenk.id}"
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
            "artikel": artikel,
        },
    )


@login_required
def freigetraenk_neu(request):
    artikel = list(Getraenk.objects.filter(aktiv=True).order_by("name"))

    if not artikel:
        messages.info(
            request,
            "Es sind noch keine aktiven Getränke angelegt. Bitte zuerst in der "
            "Verwaltung ein Getränk anlegen.",
        )
        return render(request, "kasse/freigetraenk_form.html", {"keine_artikel": True})

    if request.method == "POST":
        meta_form = FreigetraenkMetaForm(request.POST)
        if meta_form.is_valid():
            datum = meta_form.cleaned_data["datum"]
            kommentar = meta_form.cleaned_data["kommentar"]
            try:
                pruefe_monat_nicht_exportiert(datum, "Ein nachgetragenes Freigetränk")
            except GesperrterMonatError as exc:
                messages.error(request, str(exc))
            else:
                erstellt = 0
                with transaction.atomic():
                    for getraenk in artikel:
                        anzahl = _int_aus_post(request.POST, f"anzahl_{getraenk.id}")
                        if anzahl > 0:
                            Freigetraenk.objects.create(
                                getraenk=getraenk,
                                datum=datum,
                                anzahl=anzahl,
                                kommentar=kommentar,
                            )
                            erstellt += 1
                if erstellt:
                    messages.success(
                        request, f"{erstellt} Freigetränke-Eintrag/-einträge gespeichert."
                    )
                else:
                    messages.info(request, "Keine Mengen eingegeben, nichts gespeichert.")
                return redirect(reverse("kasse:home"))
    else:
        meta_form = FreigetraenkMetaForm(initial={"datum": timezone.localdate()})

    return render(
        request,
        "kasse/freigetraenk_form.html",
        {"meta_form": meta_form, "artikel": artikel},
    )


@login_required
def kassenbewegung_neu(request):
    if request.method == "POST":
        form = KassenbewegungForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Kassenbewegung gespeichert.")
            return redirect(reverse("kasse:kassenbewegung_neu"))
    else:
        form = KassenbewegungForm(initial={"datum": timezone.localdate()})

    bewegungen = Kassenbewegung.objects.all()[:50]
    return render(
        request,
        "kasse/kassenbewegung_form.html",
        {"form": form, "bewegungen": bewegungen},
    )


@login_required
def beleg_neu(request):
    if request.method == "POST":
        form = BelegForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Beleg gespeichert.")
            return redirect(reverse("kasse:beleg_neu"))
    else:
        form = BelegForm(initial={"datum": timezone.localdate()})

    heute = timezone.localdate()
    monatsbelege = Beleg.objects.filter(
        datum__year=heute.year, datum__month=heute.month
    )
    # Python-Summe statt SQL-Sum(): SQLite berechnet SUM() ueber Decimal-
    # Spalten per Gleitkomma, was Rundungsmuell wie "40,3000000000000"
    # erzeugt.
    einkaufswert_monat = sum(
        (b.gesamtbetrag for b in monatsbelege), Decimal("0")
    )

    belege = Beleg.objects.all()[:50]
    return render(
        request,
        "kasse/beleg_form.html",
        {
            "form": form,
            "belege": belege,
            "einkaufswert_monat": einkaufswert_monat,
        },
    )


@login_required
def auswertung(request):
    zaehlungen = Zaehlung.objects.all()

    zaehlung_id = request.GET.get("zaehlung")
    if zaehlung_id:
        aktuelle_zaehlung = get_object_or_404(Zaehlung, pk=zaehlung_id)
    else:
        aktuelle_zaehlung = zaehlungen.first()

    result = berechne_auswertung(aktuelle_zaehlung) if aktuelle_zaehlung else None

    return render(
        request,
        "kasse/auswertung.html",
        {
            "zaehlungen": zaehlungen,
            "aktuelle_zaehlung": aktuelle_zaehlung,
            "result": result,
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

    result = berechne_zeitraum(zaehlungen_im_monat)

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
