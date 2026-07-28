from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_intake", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="aiintakemessage",
            name="client_request_id",
            field=models.UUIDField(
                blank=True, null=True, verbose_name="client request ID"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="aiintakemessage",
            unique_together={
                ("session", "sequence_number"),
                ("session", "client_request_id"),
            },
        ),
    ]
