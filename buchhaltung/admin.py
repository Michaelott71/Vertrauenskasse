from django.contrib import admin

from .models import (
    Artikel,
    Firmenprofil,
    Gutschein,
    GutscheinEinloesung,
    Konto,
    Quittung,
    Rechnung,
    RechnungsPosition,
    ZahlungsdienstleisterGebuehr,
)


@admin.register(Firmenprofil)
class FirmenprofilAdmin(admin.ModelAdmin):
    list_display = ("name", "steuernummer", "ust_idnr")

    def has_add_permission(self, request):
        # Es soll nur der eine Datensatz (get_solo) existieren.
        return not Firmenprofil.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Konto)
class KontoAdmin(admin.ModelAdmin):
    list_display = ("bezeichnung", "iban", "kontonummer_datev", "aktiv")
    list_filter = ("aktiv",)
    search_fields = ("bezeichnung", "iban")


@admin.register(Artikel)
class ArtikelAdmin(admin.ModelAdmin):
    list_display = ("name", "einzelpreis", "mwst_satz", "aktiv")
    list_filter = ("aktiv", "mwst_satz")
    search_fields = ("name",)


class RechnungsPositionInline(admin.TabularInline):
    model = RechnungsPosition
    extra = 1


class ZahlungsdienstleisterGebuehrInline(admin.TabularInline):
    model = ZahlungsdienstleisterGebuehr
    fk_name = "rechnung"
    extra = 0


@admin.register(Rechnung)
class RechnungAdmin(admin.ModelAdmin):
    list_display = (
        "nummer",
        "datum",
        "kunde_name",
        "konto",
        "netto_summe",
        "mwst_gesamt",
        "brutto_summe",
        "bezahlt",
    )
    list_filter = ("bezahlt", "konto")
    search_fields = ("nummer", "kunde_name")
    readonly_fields = ("nummer",)
    inlines = [RechnungsPositionInline, ZahlungsdienstleisterGebuehrInline]
    actions = ["als_bezahlt_markieren"]

    @admin.action(description="Ausgewaehlte Rechnungen als bezahlt markieren")
    def als_bezahlt_markieren(self, request, queryset):
        from datetime import date

        queryset.filter(bezahlt=False).update(bezahlt=True, bezahlt_am=date.today())


class GutscheinEinloesungInline(admin.TabularInline):
    model = GutscheinEinloesung
    fk_name = "rechnung"
    extra = 0


@admin.register(Quittung)
class QuittungAdmin(admin.ModelAdmin):
    list_display = ("nummer", "datum", "name", "verwendungszweck", "betrag", "konto")
    list_filter = ("konto",)
    search_fields = ("nummer", "name", "verwendungszweck")
    readonly_fields = ("nummer",)


class GutscheinEinloesungInlineForGutschein(admin.TabularInline):
    model = GutscheinEinloesung
    extra = 0


@admin.register(Gutschein)
class GutscheinAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "typ",
        "wert",
        "grund",
        "ausgestellt_am",
        "ablaufdatum",
        "restguthaben",
        "status",
    )
    list_filter = ("typ", "grund")
    search_fields = ("code",)
    inlines = [GutscheinEinloesungInlineForGutschein]


@admin.register(ZahlungsdienstleisterGebuehr)
class ZahlungsdienstleisterGebuehrAdmin(admin.ModelAdmin):
    list_display = ("datum", "anbieter", "bruttobetrag", "gebuehr", "rechnung", "quittung")
    list_filter = ("anbieter",)
