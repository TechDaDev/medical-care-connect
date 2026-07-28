from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0006_alter_notification_notification_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("new_consultation", "New Consultation"),
                    ("new_message", "New Message"),
                    ("consultation_accepted", "Consultation Accepted"),
                    ("emergency_escalated", "Emergency Escalated"),
                    ("consultation_cancelled", "Consultation Cancelled"),
                    ("intake_completed", "Intake Completed"),
                    ("record_confirmed", "Record Confirmed"),
                    ("record_revision_requested", "Record Revision Requested"),
                    ("status_change", "Status Change"),
                    ("review_available", "Review Available"),
                    ("review_response", "Review Response"),
                    ("moderation_state", "Moderation State"),
                    ("report_resolution", "Report Resolution"),
                    ("doctor_application", "Doctor Application"),
                    ("doctor_application_status", "Doctor Application Status"),
                    ("account_status_change", "Account Status Change"),
                    ("privacy_deletion_approved", "Privacy Deletion Approved"),
                    ("privacy_deletion_rejected", "Privacy Deletion Rejected"),
                ],
                max_length=40,
                verbose_name="notification type",
            ),
        ),
    ]
