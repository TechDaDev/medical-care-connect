from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("attachments", "0002_admin_quarantine_fields"),
    ]

    operations = [
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
                    ("quarantined", "Quarantined"),
                    ("released", "Released"),
                    ("retention_deleted", "Retention Deleted"),
                    ("admin_action_failed", "Admin Action Failed"),
                ],
                max_length=30,
                verbose_name="event type",
            ),
        ),
    ]
