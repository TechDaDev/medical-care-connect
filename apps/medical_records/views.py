from uuid import UUID

from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from apps.accounts.permissions import IsApprovedDoctor, IsPatient
from apps.consultations.models import Consultation
from apps.medical_records.doctor_services import (
    MedicalRecordWorkflowError,
    finalize_record,
    get_or_create_record,
    update_record,
)
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.medical_records.serializers import (
    MedicalRecordDraftSerializer,
    MedicalRecordDraftUpdateSerializer,
    PatientMedicalRecordSerializer,
    RecordConfirmSerializer,
    CreateMedicalRecordSerializer,
    DoctorMedicalRecordDetailSerializer,
    DoctorMedicalRecordListSerializer,
    DoctorMedicalRecordQuerySerializer,
    FinalizeDoctorMedicalRecordSerializer,
    UpdateDoctorMedicalRecordSerializer,
)


class DoctorMedicalRecordPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _workflow_error(error):
    body = {"detail": error.code, "code": error.code}
    if error.details:
        body["errors"] = error.details
    return Response(body, status=error.http_status)


def _doctor_record_queryset(user):
    return MedicalRecordDraft.objects.filter(
        consultation__doctor=user.doctor_profile
    ).select_related(
        "consultation__patient__user",
        "consultation__doctor__user",
        "consultation__specialty",
        "intake_session",
        "created_by",
        "finalized_by",
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_medical_record_list(request: Request) -> Response:
    query = DoctorMedicalRecordQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    values = query.validated_data
    records = _doctor_record_queryset(request.user)
    if value := values.get("record_status"):
        records = records.filter(status=value)
    if value := values.get("consultation_status"):
        records = records.filter(consultation__status=value)
    if value := values.get("patient"):
        records = records.filter(consultation__patient_id=value)
    if value := values.get("specialty"):
        records = records.filter(consultation__specialty_id=value)
    if "needs_doctor_action" in request.query_params:
        records = records.filter(
            status=RecordStatus.DRAFT if values["needs_doctor_action"] else RecordStatus.FINALIZED
        )
    if value := values.get("created_after"):
        records = records.filter(created_at__date__gte=value)
    if value := values.get("created_before"):
        records = records.filter(created_at__date__lte=value)
    if value := values.get("updated_after"):
        records = records.filter(updated_at__date__gte=value)
    if search := values.get("search"):
        try:
            identifier = UUID(search)
        except (ValueError, TypeError, AttributeError):
            identifier = None
        if identifier:
            records = records.filter(Q(id=identifier) | Q(consultation_id=identifier))
        else:
            records = records.filter(
                Q(consultation__patient__user__first_name__icontains=search)
                | Q(consultation__patient__user__last_name__icontains=search)
                | Q(consultation__specialty__name__icontains=search)
            )
    if ordering := values.get("ordering"):
        records = records.order_by(ordering)
    else:
        records = records.annotate(
            action_rank=Case(
                When(status=RecordStatus.DRAFT, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("action_rank", "-updated_at")
    paginator = DoctorMedicalRecordPagination()
    page = paginator.paginate_queryset(records, request)
    return paginator.get_paginated_response(
        DoctorMedicalRecordListSerializer(page, many=True).data
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_medical_record_detail(request: Request, record_id) -> Response:
    if request.method == "GET":
        record = get_object_or_404(_doctor_record_queryset(request.user), pk=record_id)
    else:
        serializer = UpdateDoctorMedicalRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            record, _ = update_record(
                record_id=record_id,
                doctor=request.user.doctor_profile,
                actor=request.user,
                values=values["doctor_authored"],
                expected_version=values["expected_version"],
                client_request_id=values["client_request_id"],
                request_id=getattr(request, "request_id", ""),
            )
        except MedicalRecordDraft.DoesNotExist:
            return Response(
                {"detail": "medical_record_not_found", "code": "medical_record_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except MedicalRecordWorkflowError as error:
            return _workflow_error(error)
        record = get_object_or_404(_doctor_record_queryset(request.user), pk=record.pk)
    return Response(DoctorMedicalRecordDetailSerializer(record).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def create_consultation_medical_record(request: Request, consultation_id) -> Response:
    serializer = CreateMedicalRecordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        record, created = get_or_create_record(
            consultation_id=consultation_id,
            doctor=request.user.doctor_profile,
            actor=request.user,
            client_request_id=serializer.validated_data["client_request_id"],
            request_id=getattr(request, "request_id", ""),
        )
    except Consultation.DoesNotExist:
        return Response(
            {"detail": "not_found", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except MedicalRecordWorkflowError as error:
        return _workflow_error(error)
    record = get_object_or_404(_doctor_record_queryset(request.user), pk=record.pk)
    return Response(
        DoctorMedicalRecordDetailSerializer(record).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def finalize_doctor_medical_record(request: Request, record_id) -> Response:
    serializer = FinalizeDoctorMedicalRecordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        record, _ = finalize_record(
            record_id=record_id,
            doctor=request.user.doctor_profile,
            actor=request.user,
            expected_version=values["expected_version"],
            client_request_id=values["client_request_id"],
            confirmation=values["confirmation"],
            request_id=getattr(request, "request_id", ""),
        )
    except MedicalRecordDraft.DoesNotExist:
        return Response(
            {"detail": "medical_record_not_found", "code": "medical_record_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except MedicalRecordWorkflowError as error:
        return _workflow_error(error)
    record = get_object_or_404(_doctor_record_queryset(request.user), pk=record.pk)
    return Response(DoctorMedicalRecordDetailSerializer(record).data)


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
        if (
            is_owner
            and record.status != RecordStatus.FINALIZED
            and record.created_by_id is not None
        ):
            return Response(
                {"detail": "medical_record_not_found", "code": "medical_record_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer_class = (
            PatientMedicalRecordSerializer
            if is_owner
            else MedicalRecordDraftSerializer
        )
        serializer = serializer_class(record)
        return Response(serializer.data)

    # PATCH — doctor only, not on finalized records
    if not is_assigned:
        return Response(
            {"detail": "Only the assigned doctor can update this record."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if record.created_by_id is not None:
        return Response(
            {
                "detail": "use_doctor_medical_record_endpoint",
                "code": "use_doctor_medical_record_endpoint",
            },
            status=status.HTTP_409_CONFLICT,
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

    if record.created_by_id is not None:
        return Response(
            {"detail": "doctor_finalization_required", "code": "doctor_finalization_required"},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        if not serializer.validated_data["confirmed"]:
            # Patient declined — reset for revision
            record.status = RecordStatus.DRAFT
            record.doctor_notes = (
                (record.doctor_notes or "")
                + "\n[Patient requested revision.]"
            )
            record.save(update_fields=["status", "doctor_notes"])

            # Notify doctor
            from apps.notifications.services import notify_record_revision_requested
            notify_record_revision_requested(record)
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

        # Notify doctor
        from apps.notifications.services import notify_record_confirmed
        notify_record_confirmed(record)

    return Response(
        {"detail": "Record confirmed.", "status": record.status},
        status=status.HTTP_200_OK,
    )
