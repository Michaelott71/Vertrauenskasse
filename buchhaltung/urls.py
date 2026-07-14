from django.urls import path

from . import views

app_name = "buchhaltung"

urlpatterns = [
    path("", views.monatsliste, name="monatsliste"),
    path("rechnung/<int:pk>/bezahlt/", views.rechnung_bezahlt_umschalten, name="rechnung_bezahlt"),
    path("rechnung/<int:pk>/pdf/", views.rechnung_pdf_view, name="rechnung_pdf"),
    path("quittung/<int:pk>/pdf/", views.quittung_pdf_view, name="quittung_pdf"),
    path("export/csv/", views.export_csv, name="export_csv"),
    path("export/xlsx/", views.export_xlsx, name="export_xlsx"),
    path("export/datev/", views.export_datev, name="export_datev"),
]
