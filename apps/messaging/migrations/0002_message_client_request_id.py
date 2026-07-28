from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("messaging", "0001_phase5_models")]

    operations = [
        migrations.AddField(
            model_name="consultationmessage",
            name="client_request_id",
            field=models.UUIDField(
                blank=True, null=True, verbose_name="client request ID"
            ),
        ),
        migrations.AddConstraint(
            model_name="consultationmessage",
            constraint=models.UniqueConstraint(
                fields=("sender", "client_request_id"),
                name="message_unique_sender_request_id",
            ),
        ),
    ]
