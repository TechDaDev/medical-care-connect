from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("consultations", "0004_consultationprioritychange_consultationtransfer"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="client_request_id",
            field=models.UUIDField(
                blank=True,
                help_text="Patient-scoped idempotency key for consultation creation.",
                null=True,
                verbose_name="client request ID",
            ),
        ),
        migrations.AddConstraint(
            model_name="consultation",
            constraint=models.UniqueConstraint(
                fields=("patient", "client_request_id"),
                name="consultation_unique_patient_request_id",
            ),
        ),
    ]
