"""Services for in-app notifications."""

from django.db import transaction

from apps.notifications.models import Notification, NotificationType


def create_notification(
    *,
    recipient,
    notification_type: str,
    title: str,
    body: str = "",
    consultation=None,
    related_message=None,
) -> Notification:
    """Create a notification for a user."""
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        consultation=consultation,
        related_message=related_message,
    )


def notify_doctor_application(profile) -> None:
    """Notify authorized staff without exposing application PII."""
    from apps.accounts.models import User, UserRole
    from apps.notifications.models import NotificationType

    recipients = User.objects.filter(
        role__in=(UserRole.COORDINATOR, UserRole.ADMINISTRATOR), is_active=True
    )
    for recipient in recipients:
        create_notification(
            recipient=recipient,
            notification_type=NotificationType.DOCTOR_APPLICATION,
            title="New doctor application",
            body="A doctor application is ready for review.",
        )


def notify_doctor_application_status(profile) -> None:
    from apps.notifications.models import NotificationType

    status = profile.approval_status
    title = "Doctor application approved" if status == "approved" else "Doctor application update"
    body = (
        "Your application has been approved. Enable consultations when ready."
        if status == "approved"
        else "Your application was not approved. Contact support if you need help."
    )
    create_notification(
        recipient=profile.user,
        notification_type=NotificationType.DOCTOR_APPLICATION_STATUS,
        title=title,
        body=body,
    )


def notify_new_message(message):
    """Notify the consultation participants (excluding sender) about a new message."""
    consultation = message.consultation
    sender = message.sender
    participants = set()

    patient_user = consultation.patient.user
    doctor_user = consultation.doctor.user

    if sender != patient_user:
        participants.add(patient_user)
    if sender != doctor_user:
        participants.add(doctor_user)

    for user in participants:
        create_notification(
            recipient=user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="New Message",
            body=message.content[:200],
            consultation=consultation,
            related_message=message,
        )


def notify_consultation_accepted(consultation):
    """Notify the patient that their consultation was accepted."""
    create_notification(
        recipient=consultation.patient.user,
        notification_type=NotificationType.CONSULTATION_ACCEPTED,
        title="Consultation Accepted",
        body="Your consultation has been accepted by the doctor.",
        consultation=consultation,
    )


def notify_consultation_cancelled(consultation):
    """Notify participants about a cancellation."""
    patient_user = consultation.patient.user
    doctor_user = consultation.doctor.user

    for user in (patient_user, doctor_user):
        create_notification(
            recipient=user,
            notification_type=NotificationType.CONSULTATION_CANCELLED,
            title="Consultation Cancelled",
            body=f"Consultation cancelled. Reason: {consultation.cancellation_reason}",
            consultation=consultation,
        )


def notify_intake_completed(consultation):
    """Notify the doctor that AI intake is complete."""
    create_notification(
        recipient=consultation.doctor.user,
        notification_type=NotificationType.INTAKE_COMPLETED,
        title="Intake Completed",
        body="AI-assisted intake has been completed for this consultation.",
        consultation=consultation,
    )


def notify_record_confirmed(record):
    """Notify the doctor that the patient confirmed the record."""
    consultation = record.consultation
    create_notification(
        recipient=consultation.doctor.user,
        notification_type=NotificationType.RECORD_CONFIRMED,
        title="Record Confirmed by Patient",
        body="The patient has confirmed the medical record.",
        consultation=consultation,
    )


def notify_record_revision_requested(record):
    """Notify the doctor that the patient requested a revision."""
    consultation = record.consultation
    create_notification(
        recipient=consultation.doctor.user,
        notification_type=NotificationType.RECORD_REVISION_REQUESTED,
        title="Record Revision Requested",
        body="The patient has requested a revision of the medical record.",
        consultation=consultation,
    )
