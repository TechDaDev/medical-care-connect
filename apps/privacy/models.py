"""
Privacy models: DataExportRequest, AccountDeletionRequest.

No medical content, passwords, or tokens stored here.
"""

import uuid

from django.conf import settings
from django.db import models


class ExportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"
    DELETED = "deleted", "Deleted"


class DataExportRequest(models.Model):
    """Privacy data export request."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="export_requests_made",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="export_requests",
    )
    status = models.CharField(
        max_length=20, choices=ExportStatus.choices, default=ExportStatus.PENDING
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    storage_provider = models.CharField(max_length=50, blank=True, default="")
    storage_key = models.CharField(max_length=500, blank=True, default="")
    checksum = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=100, blank=True, default="")
    created_by_staff = models.BooleanField(default=False)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Export {self.id} [{self.status}]"


class DeletionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class AccountDeletionRequest(models.Model):
    """Account deletion request — does not immediately erase data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deletion_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="deletion_requests_made",
    )
    status = models.CharField(
        max_length=20, choices=DeletionStatus.choices, default=DeletionStatus.PENDING
    )
    reason = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_reviews",
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    failure_code = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Deletion {self.id} [{self.status}]"
