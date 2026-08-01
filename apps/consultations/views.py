from django.db import transaction
from django.db.models import (
    Case, Count, IntegerField, Max, OuterRef, Q, Subquery, Value, When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsApprovedDoctor, IsPatient
from apps.ai_intake.serializers import StartIntakeResponseSerializer
from apps.ai_intake.services.base import AIProviderDisabled
from apps.ai_intake.services.intake import start_intake_session
from apps.consultations.models import Consultation, ConsultationStatus
from apps.consultations.doctor_actions import (
    DOCTOR_ACTION_STATUSES,
    STATUS_GROUPS,
    DoctorWorkflowError,
    perform_doctor_action,
)
from apps.consultations.doctor_serializers import (
    DoctorAcceptSerializer,
    DoctorConsultationDetailSerializer,
    DoctorConsultationQueueSerializer,
    DoctorIntakeSerializer,
    DoctorTransitionSerializer,
)
from apps.consultations.serializers import (
    ConsultationCancelSerializer,
    ConsultationCreateSerializer,
    ConsultationCreateResponseSerializer,
    ConsultationDetailSerializer,
    PatientConsultationDetailSerializer,
    PatientConsultationListSerializer,
    ConsultationSerializer,
)
from apps.consultations.services import (
    ConsultationCreationError,
    create_patient_consultation,
)


# ── Consultation Collection ─────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def consultation_collection(request: Request) -> Response:
    """List or create consultations.

    GET  → list based on user role (patient owns, doctor assigned, staff all).
    POST → create a new consultation (patient-only).
    """
    if request.method == "GET":
        return _list_consultations(request)

    return _create_consultation(request)


def _list_consultations(request: Request) -> Response:
    """List consultations based on user role."""
    user = request.user
    queryset = Consultation.objects.select_related(
        "patient__user", "doctor__user", "specialty"
    )

    if user.role == UserRole.PATIENT and hasattr(user, "patient_profile"):
        from apps.messaging.models import ConsultationMessage

        unread = (
            ConsultationMessage.objects
            .filter(consultation_id=OuterRef("pk"))
            .exclude(sender=user)
            .exclude(read_receipts__user=user)
            .values("consultation_id")
            .annotate(total=Count("id"))
            .values("total")[:1]
        )
        queryset = (
            queryset
            .filter(patient=user.patient_profile)
            .select_related(
                "doctor__specialty", "intake_session", "medical_record", "review"
            )
            .annotate(unread_messages=Coalesce(Subquery(unread), Value(0)))
        )
        queryset = _filter_patient_consultations(queryset, request)
        paginator = PatientConsultationPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PatientConsultationListSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)
    elif user.role == UserRole.DOCTOR and hasattr(user, "doctor_profile"):
        queryset = queryset.filter(doctor=user.doctor_profile)
    elif user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return Response(
            {"detail": "You do not have permission to view consultations."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ConsultationSerializer(queryset, many=True)
    return Response(serializer.data)


class PatientConsultationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class DoctorConsultationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _doctor_unread_subquery(user):
    from apps.messaging.models import ConsultationMessage

    return (
        ConsultationMessage.objects
        .filter(consultation_id=OuterRef("pk"))
        .exclude(sender=user)
        .exclude(read_receipts__user=user)
        .values("consultation_id")
        .annotate(total=Count("id", distinct=True))
        .values("total")[:1]
    )


def _doctor_consultation_queryset(user):
    from apps.attachments.choices import AttachmentStatus, ScanStatus

    return (
        Consultation.objects
        .filter(doctor=user.doctor_profile)
        .select_related(
            "patient__user", "doctor__user", "doctor__specialty", "specialty",
            "intake_session", "medical_record",
        )
        .prefetch_related("doctor_actions")
        .annotate(
            unread_messages=Coalesce(
                Subquery(_doctor_unread_subquery(user)), Value(0)
            ),
            last_message_at=Max("messages__sent_at"),
            attachment_count=Count(
                "attachments", filter=Q(attachments__is_deleted=False), distinct=True
            ),
            attachment_total=Count(
                "attachments", filter=Q(attachments__is_deleted=False), distinct=True
            ),
            attachment_available=Count(
                "attachments",
                filter=Q(
                    attachments__is_deleted=False,
                    attachments__status=AttachmentStatus.AVAILABLE,
                ),
                distinct=True,
            ),
            attachment_pending=Count(
                "attachments",
                filter=Q(
                    attachments__is_deleted=False,
                    attachments__scan_status=ScanStatus.PENDING,
                ),
                distinct=True,
            ),
            attachment_quarantined=Count(
                "attachments",
                filter=Q(attachments__status=AttachmentStatus.QUARANTINED),
                distinct=True,
            ),
            attachment_rejected=Count(
                "attachments",
                filter=Q(attachments__status=AttachmentStatus.REJECTED),
                distinct=True,
            ),
            internal_note_count=Count("internal_notes", distinct=True),
            latest_internal_note_at=Max("internal_notes__created_at"),
        )
    )


def _filter_doctor_consultations(queryset, request):
    params = request.query_params
    if params.get("status"):
        queryset = queryset.filter(status=params["status"])
    if params.get("status_group"):
        statuses = STATUS_GROUPS.get(params["status_group"])
        queryset = queryset.filter(status__in=statuses or [])
    for parameter, field in (
        ("priority", "priority"),
        ("patient", "patient_id"),
        ("specialty", "specialty_id"),
        ("created_after", "created_at__gte"),
        ("created_before", "created_at__lte"),
    ):
        if params.get(parameter):
            queryset = queryset.filter(**{field: params[parameter]})
    if params.get("needs_doctor_action", "").lower() == "true":
        queryset = queryset.filter(
            Q(status__in=DOCTOR_ACTION_STATUSES) | Q(unread_messages__gt=0)
        )
    if params.get("has_unread_messages", "").lower() == "true":
        queryset = queryset.filter(unread_messages__gt=0)
    if params.get("has_completed_intake", "").lower() == "true":
        queryset = queryset.filter(
            intake_session__status__in=["ready_for_review", "confirmed"]
        )
    if params.get("has_medical_record", "").lower() == "true":
        queryset = queryset.filter(medical_record__isnull=False)

    search = params.get("search", "").strip()
    if search:
        query = (
            Q(patient__user__first_name__icontains=search)
            | Q(patient__user__last_name__icontains=search)
            | Q(specialty__name__icontains=search)
            | Q(specialty__name_en__icontains=search)
            | Q(specialty__name_ar__icontains=search)
            | Q(specialty__name_ckb__icontains=search)
        )
        try:
            import uuid
            query |= Q(id=uuid.UUID(search))
        except ValueError:
            pass
        queryset = queryset.filter(query)

    ordering = params.get("ordering")
    allowed = {
        "created_at", "-created_at", "updated_at", "-updated_at",
        "submitted_at", "-submitted_at", "priority", "-priority",
    }
    if ordering in allowed:
        return queryset.order_by(ordering, "-updated_at")
    return queryset.annotate(
        emergency_rank=Case(
            When(status=ConsultationStatus.EMERGENCY_ESCALATED, then=Value(0)),
            When(priority="urgent", then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        ),
        action_rank=Case(
            When(status__in=DOCTOR_ACTION_STATUSES, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        ),
        unread_rank=Case(
            When(unread_messages__gt=0, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        ),
    ).order_by("emergency_rank", "action_rank", "unread_rank", "-updated_at")


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_consultation_queue(request: Request) -> Response:
    queryset = _filter_doctor_consultations(
        _doctor_consultation_queryset(request.user), request
    )
    paginator = DoctorConsultationPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = DoctorConsultationQueueSerializer(
        page,
        many=True,
        context={
            "request": request,
            "doctor": request.user.doctor_profile,
        },
    )
    return paginator.get_paginated_response(serializer.data)


def _filter_patient_consultations(queryset, request):
    params = request.query_params
    status_value = params.get("status")
    if status_value:
        queryset = queryset.filter(status=status_value)

    active = [
        value for value, _ in ConsultationStatus.choices
        if value not in {
            ConsultationStatus.DRAFT,
            ConsultationStatus.COMPLETED,
            ConsultationStatus.CANCELLED,
        }
    ]
    status_group = params.get("status_group")
    if status_group == "active":
        queryset = queryset.filter(status__in=active)
    elif status_group == "needs_action":
        queryset = queryset.filter(
            Q(status__in=[
                ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                ConsultationStatus.FOLLOW_UP_REQUIRED,
                ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
                ConsultationStatus.EMERGENCY_ESCALATED,
                ConsultationStatus.INTAKE_IN_PROGRESS,
            ])
            | Q(unread_messages__gt=0)
        )
    elif status_group == "completed":
        queryset = queryset.filter(status=ConsultationStatus.COMPLETED)
    elif status_group == "cancelled":
        queryset = queryset.filter(status=ConsultationStatus.CANCELLED)

    for parameter, field in (
        ("doctor", "doctor_id"),
        ("specialty", "specialty_id"),
        ("created_after", "created_at__gte"),
        ("created_before", "created_at__lte"),
    ):
        if params.get(parameter):
            queryset = queryset.filter(**{field: params[parameter]})
    if params.get("has_unread_messages", "").lower() == "true":
        queryset = queryset.filter(unread_messages__gt=0)
    if params.get("needs_patient_action", "").lower() == "true":
        queryset = queryset.filter(
            Q(status__in=[
                    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                    ConsultationStatus.FOLLOW_UP_REQUIRED,
                    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
                    ConsultationStatus.EMERGENCY_ESCALATED,
                    ConsultationStatus.INTAKE_IN_PROGRESS,
                ])
            | Q(unread_messages__gt=0)
        )

    search = params.get("search", "").strip()
    if search:
        query = (
            Q(doctor__user__first_name__icontains=search)
            | Q(doctor__user__last_name__icontains=search)
            | Q(specialty__name__icontains=search)
            | Q(specialty__name_en__icontains=search)
            | Q(specialty__name_ar__icontains=search)
            | Q(specialty__name_ckb__icontains=search)
        )
        try:
            import uuid
            query |= Q(id=uuid.UUID(search))
        except ValueError:
            pass
        queryset = queryset.filter(query)

    ordering = params.get("ordering")
    allowed = {
        "created_at", "-created_at", "updated_at", "-updated_at",
        "submitted_at", "-submitted_at",
    }
    if ordering in allowed:
        return queryset.order_by(ordering)
    action_statuses = [
        ConsultationStatus.AWAITING_PATIENT_RESPONSE,
        ConsultationStatus.FOLLOW_UP_REQUIRED,
        ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
        ConsultationStatus.EMERGENCY_ESCALATED,
        ConsultationStatus.INTAKE_IN_PROGRESS,
    ]
    return queryset.annotate(
        patient_action_rank=Case(
            When(status__in=action_statuses, then=Value(0)),
            When(unread_messages__gt=0, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        terminal_rank=Case(
            When(
                status__in=[ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED],
                then=Value(1),
            ),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by("patient_action_rank", "terminal_rank", "-updated_at")


def _create_consultation(request: Request) -> Response:
    """Create a new consultation. Patient-only."""
    if request.user.role != UserRole.PATIENT:
        return Response(
            {
                "detail": "patient_role_required",
                "code": "patient_role_required",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    patient_profile = getattr(request.user, "patient_profile", None)
    if patient_profile is None:
        return Response(
            {
                "detail": "patient_profile_unavailable",
                "code": "patient_profile_unavailable",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ConsultationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        result = create_patient_consultation(
            patient=patient_profile,
            doctor_id=values["doctor"],
            description=values["description"],
            client_request_id=values["client_request_id"],
            priority=values["priority"],
            specialty_id=values.get("specialty"),
            expected_doctor_updated_at=values.get(
                "expected_doctor_updated_at"
            ),
            request_id=getattr(request, "request_id", ""),
        )
    except ConsultationCreationError as error:
        conflict_codes = {
            "doctor_not_accepting",
            "doctor_state_changed",
            "specialty_inactive",
            "duplicate_request",
        }
        response_status = (
            status.HTTP_409_CONFLICT
            if error.code in conflict_codes
            else status.HTTP_400_BAD_REQUEST
        )
        return Response(
            {
                "detail": error.code,
                "code": error.code,
                "fields": {error.field: [error.code]},
            },
            status=response_status,
        )

    output = ConsultationCreateResponseSerializer(
        result.consultation,
        context={"request": request},
    )
    return Response(
        output.data,
        status=(
            status.HTTP_201_CREATED
            if result.created
            else status.HTTP_200_OK
        ),
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def consultation_detail(request: Request, pk: str) -> Response:
    """Get a single consultation. Role-scoped access."""
    queryset = Consultation.objects.select_related(
            "patient__user", "doctor__user", "specialty",
            "doctor__specialty", "intake_session", "medical_record", "review",
        ).prefetch_related("messages", "attachments")
    if request.user.role == UserRole.PATIENT:
        from apps.messaging.models import ConsultationMessage
        unread = (
            ConsultationMessage.objects
            .filter(consultation_id=OuterRef("pk"))
            .exclude(sender=request.user)
            .exclude(read_receipts__user=request.user)
            .values("consultation_id")
            .annotate(total=Count("id"))
            .values("total")[:1]
        )
        queryset = queryset.filter(patient__user=request.user).annotate(
            unread_messages=Coalesce(Subquery(unread), Value(0))
        )
    consultation = get_object_or_404(
        queryset,
        pk=pk,
    )

    user = request.user
    is_participant = (
        (hasattr(user, "patient_profile") and consultation.patient == user.patient_profile)
        or (hasattr(user, "doctor_profile") and consultation.doctor == user.doctor_profile)
    )
    if not is_participant and user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return Response(
            {"detail": "You do not have permission to view this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer_class = (
        PatientConsultationDetailSerializer
        if request.user.role == UserRole.PATIENT
        else ConsultationDetailSerializer
    )
    serializer = serializer_class(
        consultation, context={"request": request}
    )
    return Response(serializer.data)


def _doctor_detail_response(request: Request, pk) -> Response:
    consultation = get_object_or_404(
        _doctor_consultation_queryset(request.user), pk=pk
    )
    serializer = DoctorConsultationDetailSerializer(
        consultation,
        context={
            "request": request,
            "doctor": request.user.doctor_profile,
        },
    )
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_consultation_detail(request: Request, pk: str) -> Response:
    return _doctor_detail_response(request, pk)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_consultation_intake(request: Request, pk: str) -> Response:
    consultation = get_object_or_404(
        _doctor_consultation_queryset(request.user).prefetch_related(
            "intake_session__messages"
        ),
        pk=pk,
    )
    try:
        session = consultation.intake_session
    except AttributeError:
        return Response(
            {"detail": "intake_not_found", "code": "intake_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    serializer = DoctorIntakeSerializer(
        session,
        context={"doctor": request.user.doctor_profile},
    )
    return Response(serializer.data)


# ── Consultation Actions ────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def accept_consultation(request: Request, pk: str) -> Response:
    """Accept assigned consultation with locking and idempotency."""
    serializer = DoctorAcceptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        perform_doctor_action(
            consultation_id=pk,
            doctor=request.user.doctor_profile,
            actor=request.user,
            action="accept",
            client_request_id=values["client_request_id"],
            expected_status=values["expected_status"],
            expected_updated_at=values.get("expected_updated_at"),
            request_id=getattr(request, "request_id", ""),
        )
    except Consultation.DoesNotExist:
        return Response(
            {"detail": "not_found", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except DoctorWorkflowError as error:
        return Response(
            {"detail": error.code, "code": error.code},
            status=error.http_status,
        )
    return _doctor_detail_response(request, pk)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_consultation_transition(request: Request, pk: str) -> Response:
    serializer = DoctorTransitionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        consultation, _ = perform_doctor_action(
            consultation_id=pk,
            doctor=request.user.doctor_profile,
            actor=request.user,
            action=values["action"],
            client_request_id=values["client_request_id"],
            expected_status=values["expected_status"],
            expected_updated_at=values.get("expected_updated_at"),
            reason=values.get("reason", ""),
            target_doctor_id=values.get("target_doctor_id"),
            request_id=getattr(request, "request_id", ""),
        )
    except Consultation.DoesNotExist:
        return Response(
            {"detail": "not_found", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except DoctorWorkflowError as error:
        return Response(
            {"detail": error.code, "code": error.code},
            status=error.http_status,
        )
    return _doctor_detail_response(request, consultation.id)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def cancel_consultation(request: Request, pk: str) -> Response:
    """Cancel an owned consultation with optimistic concurrency control."""
    serializer = ConsultationCancelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from apps.consultations.patient_actions import PATIENT_CANCELLABLE
    from apps.core.audit_service import create_audit_event
    from apps.core.models import AuditEventCategory

    with transaction.atomic():
        consultation = get_object_or_404(
            Consultation.objects.select_for_update(of=("self",)).select_related(
                "patient__user", "doctor__user", "doctor__specialty", "specialty",
                "intake_session", "medical_record", "review",
            ).prefetch_related("messages", "attachments"),
            pk=pk,
            patient__user=request.user,
        )
        if consultation.status == ConsultationStatus.CANCELLED:
            output = PatientConsultationDetailSerializer(
                consultation, context={"request": request}
            )
            return Response(
                {**output.data, "code": "already_cancelled"},
                status=status.HTTP_200_OK,
            )
        expected_status = serializer.validated_data.get(
            "expected_status", consultation.status
        )
        if consultation.status != expected_status:
            return Response(
                {"detail": "consultation_state_changed", "code": "consultation_state_changed"},
                status=status.HTTP_409_CONFLICT,
            )
        if consultation.status not in PATIENT_CANCELLABLE:
            code = (
                "consultation_completed"
                if consultation.status == ConsultationStatus.COMPLETED
                else "emergency_escalated"
                if consultation.status == ConsultationStatus.EMERGENCY_ESCALATED
                else "cancellation_not_allowed"
            )
            return Response(
                {"detail": code, "code": code},
                status=status.HTTP_409_CONFLICT,
            )

        consultation.status = ConsultationStatus.CANCELLED
        consultation.cancellation_reason = serializer.validated_data["reason"]
        consultation.cancelled_at = timezone.now()
        consultation.save(update_fields=[
            "status", "cancellation_reason", "cancelled_at", "updated_at"
        ])
        from apps.notifications.services import notify_consultation_cancelled
        notify_consultation_cancelled(consultation)
        create_audit_event(
            "patient_consultation_cancelled",
            AuditEventCategory.CONSULTATION,
            actor_id=str(request.user.id),
            actor_role=request.user.role,
            target_type="consultation",
            target_id=str(consultation.id),
            request_id=getattr(request, "request_id", ""),
            metadata={"previous_status": expected_status},
        )

    output = PatientConsultationDetailSerializer(
        consultation, context={"request": request}
    )
    return Response(output.data)


# ── AI Intake Start ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def start_intake(request: Request, pk) -> Response:
    """Start (or resume) an AI intake session for a consultation.

    Returns 503 when AI intake is disabled.
    """
    consultation = get_object_or_404(
        Consultation,
        id=pk,
        patient__user=request.user,
    )
    from apps.consultations.patient_actions import patient_action_policy
    policy = patient_action_policy(consultation)
    existing = getattr(consultation, "intake_session", None)
    allowed_resume_state = (
        existing is not None
        and existing.status in {
            "ready_for_review", "confirmed", "emergency_stopped"
        }
    )
    if (
        existing is None
        and not policy.actions["can_start_intake"]
    ) or (
        existing is not None
        and not policy.actions["can_continue_intake"]
        and not allowed_resume_state
    ):
        return Response(
            {
                "detail": policy.reasons["intake"],
                "code": policy.reasons["intake"],
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        language = request.data.get("language", "en")
        session = start_intake_session(consultation, language=str(language))
    except AIProviderDisabled:
        return Response(
            {"detail": "AI-assisted intake is currently unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    data = StartIntakeResponseSerializer({
        "session_id": session.id,
        "session_status": session.status,
        "current_question": session.current_question or "",
        "question_count": session.question_count,
        "emergency_detected": session.emergency_detected,
        "emergency_level": session.emergency_level,
        "language": session.language,
    }).data

    return Response(data, status=status.HTTP_200_OK)
