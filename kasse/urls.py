from django.urls import path

from . import views

app_name = "kasse"

urlpatterns = [
    path("", views.home, name="home"),
    path("zaehlung/neu/", views.zaehlung_neu, name="zaehlung_neu"),
    path("auswertung/", views.auswertung, name="auswertung"),
    path("auswertung/monat/", views.monatsauswertung, name="monatsauswertung"),
    path("media/<path:path>", views.media_serve, name="media"),
]
