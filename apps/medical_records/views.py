from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.medical_records.serializers import (
    MedicalRecordDraftSerializer,
    MedicalRecordDraftUpdateSerializer,
    RecordConfirmSerializer,
)


# ── Get / Update Draft Record ──────────────────────────────────────────────


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def draft_record(request: Request, record_id) -> Response:
    """Retrieve or update the medical record draft by record ID.

    GET   → patient or doctor can read.
    PATCH → doctor only can update.
    """
    record = get_object_or_404(
        MedicalRecordDraft,
        id=record_id,
    )

    # Authorisation
    user = request.user
    is_owner = (
        hasattr(user, "patient_profile")
        and record.consultation.patient == user.patient_profile
    )
    is_assigned = (
        hasattr(user, "doctor_profile")
        and record.consultation.doctor == user.doctor_profile
    )
    if not (is_owner or is_assigned):
        return Response(
            {"detail": "You do not have access to this record."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        serializer = MedicalRecordDraftSerializer(record)
        return Response(serializer.data)

    # PATCH — doctor only, not on finalized records
    if not is_assigned:
        return Response(
            {"detail": "Only the assigned doctor can update this record."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if record.status == RecordStatus.FINALIZED:
        return Response(
            {"detail": "Cannot update a finalized record."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = MedicalRecordDraftUpdateSerializer(
        record, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(MedicalRecordDraftSerializer(record).data)


# ── Confirm Record ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def confirm_record(request: Request, record_id) -> Response:
    """Patient confirms the draft record is accurate."""
    record = get_object_or_404(
        MedicalRecordDraft,
        id=record_id,
        consultation__patient__user=request.user,
    )

    serializer = RecordConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        if not serializer.validated_data["confirmed"]:
            # Patient declined — reset for revision
            record.status = RecordStatus.DRAFT
            record.doctor_notes = (
                (record.doctor_notes or "")
                + "\n[Patient requested revision.]"
            )
            record.save(update_fields=["status", "doctor_notes"])
            return Response(
                {"detail": "Record marked for revision.", "status": record.status},
                status=status.HTTP_200_OK,
            )

        record.status = RecordStatus.FINALIZED
        record.finalized_at = timezone.now()
        record.save(update_fields=["status", "finalized_at"])

        # Update intake session
        if record.intake_session:
            record.intake_session.status = "confirmed"
            record.intake_session.confirmed_at = timezone.now()
            record.intake_session.save(update_fields=["status", "confirmed_at"])

    return Response(
        {"detail": "Record confirmed.", "status": record.status},
        status=status.HTTP_200_OK,
    )
