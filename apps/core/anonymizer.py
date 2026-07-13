"""
UserDataAnonymizer — reports what would be anonymized/deleted/retained.

Current implementation: PreviewOnlyAnonymizer — no destructive mutation.
"""

from dataclasses import dataclass, field


@dataclass
class AnonymizationPreview:
    to_delete: list[str] = field(default_factory=list)
    to_anonymize: list[str] = field(default_factory=list)
    to_retain: list[str] = field(default_factory=list)
    blocked_by_retention: list[str] = field(default_factory=list)


class UserDataAnonymizer:
    """Interface for account data anonymization."""

    def preview(self, user) -> AnonymizationPreview:
        """Return preview of what would happen. No mutations."""
        raise NotImplementedError

    def execute(self, user) -> AnonymizationPreview:
        """Execute anonymization. Current impl refuses."""
        raise NotImplementedError


class PreviewOnlyAnonymizer(UserDataAnonymizer):
    """Preview-only anonymizer. Reports affected records without mutation."""

    def preview(self, user) -> AnonymizationPreview:
        preview = AnonymizationPreview()

        # Identifiable user fields
        has_name = bool(user.first_name or user.last_name)
        if has_name:
            preview.to_anonymize.append("user.name")
        if user.phone_number:
            preview.to_anonymize.append("user.phone_number")

        # Patient profile
        if hasattr(user, "patient_profile"):
            preview.to_anonymize.append("patient_profile")

        # Consultations — retain for legal/medical
        consultations = user.consultations_as_patient.all()  # type: ignore
        if consultations.exists():
            preview.to_retain.append(f"consultation ({consultations.count()} records)")

        # Messages — anonymize sender name, retain content for continuity
        from apps.messaging.models import Message
        msg_count = Message.objects.filter(sender=user).count()
        if msg_count:
            preview.to_anonymize.append(f"message.sender ({msg_count} messages)")

        # Notifications
        from apps.notifications.models import Notification
        notif_count = Notification.objects.filter(recipient=user).count()
        if notif_count:
            preview.to_delete.append(f"notification ({notif_count} records)")

        # Medical records — retain for legal
        from apps.medical_records.models import MedicalRecord
        mr_count = MedicalRecord.objects.filter(consultation__patient=user).count()
        if mr_count:
            preview.blocked_by_retention.append(f"medical_record ({mr_count} records)")

        # Attachments — retain if linked to retained consultations
        from apps.attachments.models import ConsultationAttachment
        att_count = ConsultationAttachment.objects.filter(
            uploaded_by=user, deleted_at__isnull=True
        ).count()
        if att_count:
            preview.blocked_by_retention.append(f"attachment ({att_count} records)")

        # Audit events — retain reference
        from apps.attachments.models import AttachmentAuditEvent
        audit_count = AttachmentAuditEvent.objects.filter(actor=user).count()
        if audit_count:
            preview.to_retain.append(f"audit_event ({audit_count} records)")

        # Export requests — delete
        from apps.privacy.models import DataExportRequest
        export_count = DataExportRequest.objects.filter(subject_user=user).count()
        if export_count:
            preview.to_delete.append(f"data_export_request ({export_count} records)")

        return preview

    def execute(self, user) -> AnonymizationPreview:
        """Preview only — no destructive execution."""
        return self.preview(user)
