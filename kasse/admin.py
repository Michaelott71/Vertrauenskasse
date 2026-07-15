from django.contrib import admin

from .models import (
    Beleg,
    BelegPosition,
    DifferenzZuordnung,
    Freigetraenk,
    Getraenk,
    PaypalZahlung,
    Zaehlung,
    ZaehlungBestand,
)


@admin.register(Getraenk)
class GetraenkAdmin(admin.ModelAdmin):
    list_display = ("name", "warenpreis", "pfand", "verkaufspreis", "aktiv")
    list_filter = ("aktiv",)
    search_fields = ("name",)


class ZaehlungBestandInline(admin.TabularInline):
    model = ZaehlungBestand
    extra = 1


class DifferenzZuordnungInline(admin.TabularInline):
    model = DifferenzZuordnung
    extra = 0


@admin.register(Zaehlung)
class ZaehlungAdmin(admin.ModelAdmin):
    list_display = ("datum", "notiz", "bargeld_gezaehlt", "bargeld_entnommen")
    inlines = [ZaehlungBestandInline, DifferenzZuordnungInline]


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
    list_display = ("datum", "betrag", "zaehlung", "ist_getraenke_zahlung")
    list_filter = ("ist_getraenke_zahlung",)
