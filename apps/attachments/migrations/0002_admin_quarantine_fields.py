from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attachments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultationattachment",
            name="quarantine_reason",
            field=models.CharField(blank=True, max_length=255, verbose_name="quarantine reason"),
        ),
        migrations.AddField(
            model_name="consultationattachment",
            name="rejection_reason",
            field=models.CharField(blank=True, max_length=500, verbose_name="rejection reason"),
        ),
        migrations.AddField(
            model_name="consultationattachment",
            name="storage_deleted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When retention processing removed underlying file bytes.",
                null=True,
                verbose_name="storage deleted at",
            ),
        ),
        migrations.AlterField(
            model_name="attachmentauditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("uploaded", "Uploaded"),
                    ("validated", "Validated"),
                    ("scan_started", "Scan Started"),
                    ("scan_completed", "Scan Completed"),
                    ("viewed", "Viewed"),
                    ("downloaded", "Downloaded"),
                    ("deleted", "Deleted"),
                    ("restored", "Restored"),
                    ("rejected", "Rejected"),
                    ("storage_error", "Storage Error"),
                    ("admin_viewed", "Admin Viewed"),
                    ("rescan_requested", "Rescan Requested"),
                    ("released", "Released"),
                    ("retention_deleted", "Retention Deleted"),
                    ("admin_action_failed", "Admin Action Failed"),
                ],
                max_length=30,
                verbose_name="event type",
            ),
        ),
    ]
