from django.db import migrations, models


def copy_existing_name(apps, schema_editor):
    Specialty = apps.get_model("specialties", "Specialty")
    for specialty in Specialty.objects.all().iterator():
        Specialty.objects.filter(pk=specialty.pk).update(
            name_en=specialty.name,
            name_ar=specialty.name,
            name_ckb=specialty.name,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("specialties", "0002_seed_medical_specialties"),
    ]

    operations = [
        migrations.AddField(
            model_name="specialty",
            name="name_en",
            field=models.CharField(default="", max_length=255, verbose_name="English name"),
        ),
        migrations.AddField(
            model_name="specialty",
            name="name_ar",
            field=models.CharField(default="", max_length=255, verbose_name="Arabic name"),
        ),
        migrations.AddField(
            model_name="specialty",
            name="name_ckb",
            field=models.CharField(default="", max_length=255, verbose_name="Kurdish Sorani name"),
        ),
        migrations.RunPython(copy_existing_name, migrations.RunPython.noop),
    ]
