from django.contrib import admin

from .models import (
    Beleg,
    BelegPosition,
    Freigetraenk,
    Getraenk,
    MonatsExport,
    Pfandkategorie,
    PaypalStichwort,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
    ZaehlungLeergut,
)


@admin.register(Pfandkategorie)
class PfandkategorieAdmin(admin.ModelAdmin):
    list_display = ("name", "pfandbetrag")


@admin.register(Getraenk)
class GetraenkAdmin(admin.ModelAdmin):
    list_display = ("name", "pfandkategorie", "warenpreis", "verkaufspreis", "aktiv")
    list_filter = ("aktiv", "pfandkategorie")
    search_fields = ("name",)


class ZaehlungBestandInline(admin.TabularInline):
    model = ZaehlungBestand
    extra = 1


class ZaehlungLeergutInline(admin.TabularInline):
    model = ZaehlungLeergut
    extra = 1


@admin.register(Zaehlung)
class ZaehlungAdmin(admin.ModelAdmin):
    list_display = ("belegnummer", "datum", "notiz", "bargeld_gezaehlt")
    readonly_fields = ("belegnummer",)
    inlines = [ZaehlungBestandInline, ZaehlungLeergutInline]


class BelegPositionInline(admin.TabularInline):
    model = BelegPosition
    extra = 1


@admin.register(Beleg)
class BelegAdmin(admin.ModelAdmin):
    list_display = ("datum", "haendler", "gesamtbetrag", "dateipfad")
    inlines = [BelegPositionInline]


@admin.register(Freigetraenk)
class FreigetraenkAdmin(admin.ModelAdmin):
    list_display = ("datum", "getraenk", "anzahl", "kommentar")
    list_filter = ("getraenk",)


@admin.register(PaypalZahlung)
class PaypalZahlungAdmin(admin.ModelAdmin):
    list_display = (
        "datum",
        "betrag",
        "verwendungszweck",
        "ist_getraenke_zahlung",
        "zaehlung",
        "zuordnungsgrund",
    )
    list_filter = ("ist_getraenke_zahlung",)
    search_fields = ("verwendungszweck", "paypal_transaktions_id")


@admin.register(PaypalStichwort)
class PaypalStichwortAdmin(admin.ModelAdmin):
    list_display = ("wort",)
    search_fields = ("wort",)


@admin.register(MonatsExport)
class MonatsExportAdmin(admin.ModelAdmin):
    list_display = ("jahr", "monat", "exportiert_am")
