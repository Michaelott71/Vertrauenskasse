from django.contrib import admin

from .models import (
    Auffuellung,
    Beleg,
    BelegPosition,
    Freigetraenk,
    Getraenk,
    Kassenbewegung,
    MonatsExport,
    PaypalStichwort,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
)


@admin.register(Getraenk)
class GetraenkAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "warenpreis",
        "verkaufspreis",
        "anfangsbestand_lager",
        "aktiv",
    )
    list_filter = ("aktiv",)
    search_fields = ("name",)


class ZaehlungBestandInline(admin.TabularInline):
    model = ZaehlungBestand
    extra = 1


@admin.register(Zaehlung)
class ZaehlungAdmin(admin.ModelAdmin):
    list_display = ("belegnummer", "datum", "notiz", "bargeld_gezaehlt")
    readonly_fields = ("belegnummer",)
    inlines = [ZaehlungBestandInline]


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


@admin.register(Auffuellung)
class AuffuellungAdmin(admin.ModelAdmin):
    list_display = ("datum", "getraenk", "anzahl")
    list_filter = ("getraenk",)


@admin.register(Kassenbewegung)
class KassenbewegungAdmin(admin.ModelAdmin):
    list_display = ("datum", "art", "betrag", "rg_nummer", "notiz")
    list_filter = ("art",)


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
