from django.db import migrations

STANDARD_STICHWORTE = [
    "Cola",
    "Bier",
    "Wasser",
    "Spezi",
    "Schorle",
    "Limo",
    "Duplo",
    "Twix",
    "Kasse",
]


def seed(apps, schema_editor):
    PaypalStichwort = apps.get_model("kasse", "PaypalStichwort")
    for wort in STANDARD_STICHWORTE:
        PaypalStichwort.objects.get_or_create(wort=wort)


def unseed(apps, schema_editor):
    PaypalStichwort = apps.get_model("kasse", "PaypalStichwort")
    PaypalStichwort.objects.filter(wort__in=STANDARD_STICHWORTE).delete()


class Migration(migrations.Migration):
    dependencies = [("kasse", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
