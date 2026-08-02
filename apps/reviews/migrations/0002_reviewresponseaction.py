import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("doctors", "0005_add_licensedocument_model"),
        ("reviews", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewResponseAction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(choices=[("create", "Create"), ("update", "Update")], max_length=10)),
                ("client_request_id", models.UUIDField()),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("doctor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_response_actions", to="doctors.doctorprofile")),
                ("review", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="response_actions", to="reviews.consultationreview")),
            ],
        ),
        migrations.AddConstraint(
            model_name="reviewresponseaction",
            constraint=models.UniqueConstraint(fields=("doctor", "client_request_id"), name="review_response_action_unique_doctor_request"),
        ),
        migrations.AddIndex(
            model_name="reviewresponseaction",
            index=models.Index(fields=["review", "action"], name="reviews_rev_review__7355cf_idx"),
        ),
    ]
