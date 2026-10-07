from django.urls import path

from . import views

app_name = "kasse"

urlpatterns = [
    path("", views.home, name="home"),
    path("zaehlung/neu/", views.zaehlung_neu, name="zaehlung_neu"),
    path("auffuellung/neu/", views.auffuellung_neu, name="auffuellung_neu"),
    path("freigetraenk/neu/", views.freigetraenk_neu, name="freigetraenk_neu"),
    path("lager/", views.lager_uebersicht, name="lager_uebersicht"),
    path("kassenbewegung/neu/", views.kassenbewegung_neu, name="kassenbewegung_neu"),
    path("auswertung/", views.auswertung, name="auswertung"),
    path("auswertung/monat/", views.monatsauswertung, name="monatsauswertung"),
    path("paypal/", views.paypal_abgleich, name="paypal_abgleich"),
    path("export/", views.export_csv, name="export_csv"),
    path("media/<path:path>", views.media_serve, name="media"),
]
