import calendar
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .datev import baue_datev_buchungsstapel
from .export import rechnungen_als_csv, rechnungen_als_xlsx
from .models import Quittung, Rechnung, ZahlungsdienstleisterGebuehr
from .pdf import quittung_pdf, rechnung_pdf


def _monat_aus_request(request):
    heute = date.today()
    jahr = int(request.GET.get("jahr", heute.year))
    monat = int(request.GET.get("monat", heute.month))
    return jahr, monat


def _monatsgrenzen(jahr, monat):
    letzter_tag = calendar.monthrange(jahr, monat)[1]
    return date(jahr, monat, 1), date(jahr, monat, letzter_tag)


@login_required
def monatsliste(request):
    jahr, monat = _monat_aus_request(request)
    start, ende = _monatsgrenzen(jahr, monat)
    rechnungen = Rechnung.objects.filter(datum__gte=start, datum__lte=ende)

    return render(
        request,
        "buchhaltung/monatsliste.html",
        {
            "rechnungen": rechnungen,
            "jahr": jahr,
            "monat": monat,
            "netto_summe": sum((r.netto_summe for r in rechnungen), 0),
            "brutto_summe": sum((r.brutto_summe for r in rechnungen), 0),
        },
    )


@login_required
@require_POST
def rechnung_bezahlt_umschalten(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    rechnung.bezahlt = not rechnung.bezahlt
    rechnung.bezahlt_am = date.today() if rechnung.bezahlt else None
    rechnung.save()
    messages.success(
        request,
        f"{rechnung.nummer} als {'bezahlt' if rechnung.bezahlt else 'offen'} markiert.",
    )
    jahr, monat = _monat_aus_request(request)
    return redirect(f"{reverse('buchhaltung:monatsliste')}?jahr={jahr}&monat={monat}")


@login_required
def rechnung_pdf_view(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    pdf_bytes = rechnung_pdf(rechnung)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{rechnung.nummer}.pdf"'
    return response


@login_required
def quittung_pdf_view(request, pk):
    quittung = get_object_or_404(Quittung, pk=pk)
    pdf_bytes = quittung_pdf(quittung)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{quittung.nummer}.pdf"'
    return response


@login_required
def export_csv(request):
    jahr, monat = _monat_aus_request(request)
    start, ende = _monatsgrenzen(jahr, monat)
    rechnungen = Rechnung.objects.filter(datum__gte=start, datum__lte=ende)
    response = HttpResponse(rechnungen_als_csv(rechnungen), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="rechnungen_{jahr}-{monat:02d}.csv"'
    return response


@login_required
def export_xlsx(request):
    jahr, monat = _monat_aus_request(request)
    start, ende = _monatsgrenzen(jahr, monat)
    rechnungen = Rechnung.objects.filter(datum__gte=start, datum__lte=ende)
    response = HttpResponse(
        rechnungen_als_xlsx(rechnungen),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="rechnungen_{jahr}-{monat:02d}.xlsx"'
    return response


@login_required
def export_datev(request):
    jahr, monat = _monat_aus_request(request)
    start, ende = _monatsgrenzen(jahr, monat)
    rechnungen = Rechnung.objects.filter(datum__gte=start, datum__lte=ende)
    gebuehren = ZahlungsdienstleisterGebuehr.objects.filter(datum__gte=start, datum__lte=ende)
    inhalt = baue_datev_buchungsstapel(
        rechnungen,
        gebuehren,
        kontenrahmen=settings.DATEV_KONTENRAHMEN,
        datum_von=start,
        datum_bis=ende,
    )
    response = HttpResponse(inhalt, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="EXTF_Buchungsstapel_{jahr}-{monat:02d}.csv"'
    return response
