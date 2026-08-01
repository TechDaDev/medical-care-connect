from typing import TypedDict

import uuid

from django.db.models import (
    Case,
    CharField,
    Count,
    DateTimeField,
    Exists,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.ai_intake.models import IntakeSessionStatus
from apps.consultations.models import Consultation, ConsultationStatus
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.medical_records.serializers import (
    PatientMedicalRecordListSerializer,
    PatientMedicalRecordSerializer,
)
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.patients.serializers import (
    PatientMessageThreadSerializer,
    PatientMedicalRecordQuerySerializer,
    PatientMessageThreadQuerySerializer,
    PatientProfileCompositeSerializer,
    PatientProfileUpdateSerializer,
)
from apps.patients.services.profile_completion import calculate_profile_completion

ACTIVE_PATIENT_STATUSES = (
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    ConsultationStatus.EMERGENCY_ESCALATED,
)

PATIENT_ATTENTION_STATUSES = (
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    ConsultationStatus.EMERGENCY_ESCALATED,
)

TERMINAL_STATUSES = (
    ConsultationStatus.COMPLETED,
    ConsultationStatus.CANCELLED,
    ConsultationStatus.TRANSFERRED,
)

INCOMPLETE_INTAKE_STATUSES = (
    IntakeSessionStatus.NOT_STARTED,
    IntakeSessionStatus.IN_PROGRESS,
    IntakeSessionStatus.AWAITING_PATIENT,
    IntakeSessionStatus.FAILED,
)


class AttentionConfig(TypedDict):
    title_key: str
    description_key: str
    severity: str


ATTENTION_CONFIG: dict[str, AttentionConfig] = {
    ConsultationStatus.AWAITING_PATIENT_RESPONSE: {
        "title_key": "patientDashboard.attention.awaitingPatient.title",
        "description_key": "patientDashboard.attention.awaitingPatient.description",
        "severity": "warning",
    },
    ConsultationStatus.FOLLOW_UP_REQUIRED: {
        "title_key": "patientDashboard.attention.followUp.title",
        "description_key": "patientDashboard.attention.followUp.description",
        "severity": "warning",
    },
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED: {
        "title_key": "patientDashboard.attention.physicalVisit.title",
        "description_key": "patientDashboard.attention.physicalVisit.description",
        "severity": "danger",
    },
    ConsultationStatus.EMERGENCY_ESCALATED: {
        "title_key": "patientDashboard.attention.emergency.title",
        "description_key": "patientDashboard.attention.emergency.description",
        "severity": "danger",
    },
}


def _dashboard_consultations(consultations, user):
    medical_record = MedicalRecordDraft.objects.filter(
        consultation_id=OuterRef("pk")
    )
    unread_count = (
        ConsultationMessage.objects.filter(consultation_id=OuterRef("pk"))
        .exclude(sender=user)
        .exclude(read_receipts__user=user)
        .order_by()
        .values("consultation_id")
        .annotate(total=Count("id", distinct=True))
        .values("total")
    )
    return consultations.annotate(
        unread_messages=Coalesce(
            Subquery(unread_count, output_field=IntegerField()),
            0,
        ),
        last_message_at=Max("messages__sent_at"),
        has_medical_record=Exists(
            medical_record
        ),
        medical_record_id=Subquery(medical_record.values("id")[:1]),
    )


class PatientPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _as_uuid(value):
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return None


def _composite_profile(profile):
    return PatientProfileCompositeSerializer(
        profile,
        context={
            "completion": calculate_profile_completion(profile.user, profile),
            "generated_at": timezone.now(),
        },
    ).data


def _attention_item(
    *,
    item_type: str,
    consultation_id,
    title_key: str,
    description_key: str,
    count: int,
    severity: str,
    created_at,
    action_path: str,
) -> dict:
    return {
        "type": item_type,
        "consultation_id": consultation_id,
        "title_key": title_key,
        "description_key": description_key,
        "count": count,
        "severity": severity,
        "created_at": created_at,
        "action_path": action_path,
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsPatient])
def my_patient_profile(request: Request) -> Response:
    """Get or update the authenticated patient's own profile."""
    profile = getattr(request.user, "patient_profile", None)
    if profile is None:
        return Response(
            {"detail": "Patient profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(_composite_profile(profile))

    serializer = PatientProfileUpdateSerializer(
        profile,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(_composite_profile(profile))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def my_medical_records(request: Request) -> Response:
    profile = request.user.patient_profile
    query_serializer = PatientMedicalRecordQuerySerializer(
        data=request.query_params
    )
    query_serializer.is_valid(raise_exception=True)
    filters = query_serializer.validated_data
    records = MedicalRecordDraft.objects.filter(
        consultation__patient=profile,
        status=RecordStatus.FINALIZED,
    ).select_related(
        "consultation__doctor__user",
        "consultation__specialty",
    )

    if value := filters.get("status"):
        records = records.filter(status=value)
    if value := filters.get("doctor"):
        records = records.filter(consultation__doctor_id=value)
    if value := filters.get("specialty"):
        records = records.filter(consultation__specialty_id=value)
    if value := filters.get("created_after"):
        records = records.filter(created_at__date__gte=value)
    if value := filters.get("created_before"):
        records = records.filter(created_at__date__lte=value)
    if search := filters.get("search"):
        search_filter = (
            Q(consultation__doctor__user__first_name__icontains=search)
            | Q(consultation__doctor__user__last_name__icontains=search)
            | Q(consultation__specialty__name__icontains=search)
        )
        if identifier := _as_uuid(search):
            search_filter |= Q(id=identifier) | Q(consultation_id=identifier)
        records = records.filter(search_filter)

    ordering = filters.get("ordering")
    if ordering:
        records = records.order_by(ordering)
    else:
        records = records.annotate(
            finalized_first=Case(
                When(status=RecordStatus.FINALIZED, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("finalized_first", "-updated_at")

    paginator = PatientPageNumberPagination()
    page = paginator.paginate_queryset(records, request)
    data = PatientMedicalRecordListSerializer(page, many=True).data
    return paginator.get_paginated_response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def my_medical_record_detail(request: Request, id) -> Response:
    record = get_object_or_404(
        MedicalRecordDraft.objects.select_related(
            "consultation__doctor__user",
            "consultation__specialty",
        ),
        id=id,
        consultation__patient=request.user.patient_profile,
        status=RecordStatus.FINALIZED,
    )
    return Response(PatientMedicalRecordSerializer(record).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def my_message_threads(request: Request) -> Response:
    query_serializer = PatientMessageThreadQuerySerializer(
        data=request.query_params
    )
    query_serializer.is_valid(raise_exception=True)
    filters = query_serializer.validated_data
    latest_messages = ConsultationMessage.objects.filter(
        consultation_id=OuterRef("pk")
    ).order_by("-sent_at", "-created_at")
    unread = (
        ConsultationMessage.objects.filter(consultation_id=OuterRef("pk"))
        .exclude(sender=request.user)
        .exclude(read_receipts__user=request.user)
        .order_by()
        .values("consultation_id")
        .annotate(total=Count("id", distinct=True))
        .values("total")
    )
    threads = Consultation.objects.filter(
        patient=request.user.patient_profile
    ).select_related(
        "doctor__user",
        "specialty",
    ).annotate(
        unread_count=Coalesce(
            Subquery(unread, output_field=IntegerField()),
            0,
        ),
        last_message_at=Subquery(
            latest_messages.values("sent_at")[:1],
            output_field=DateTimeField(),
        ),
        last_message_content=Subquery(
            latest_messages.values("content")[:1],
            output_field=CharField(),
        ),
        last_message_sender_role=Subquery(
            latest_messages.values("sender__role")[:1],
            output_field=CharField(),
        ),
    ).filter(last_message_at__isnull=False)

    if filters.get("unread_only"):
        threads = threads.filter(unread_count__gt=0)
    if value := filters.get("consultation_status"):
        threads = threads.filter(status=value)
    if value := filters.get("doctor"):
        threads = threads.filter(doctor_id=value)
    if search := filters.get("search"):
        search_filter = (
            Q(doctor__user__first_name__icontains=search)
            | Q(doctor__user__last_name__icontains=search)
            | Q(specialty__name__icontains=search)
        )
        if identifier := _as_uuid(search):
            search_filter |= Q(id=identifier)
        threads = threads.filter(search_filter)

    ordering = filters.get("ordering")
    if ordering in {"last_message_at", "-last_message_at"}:
        threads = threads.order_by(ordering)
    elif ordering in {"unread_count", "-unread_count"}:
        threads = threads.order_by(ordering, "-last_message_at")
    else:
        threads = threads.order_by("-unread_count", "-last_message_at")

    paginator = PatientPageNumberPagination()
    page = paginator.paginate_queryset(threads, request)
    data = PatientMessageThreadSerializer(page, many=True).data
    return paginator.get_paginated_response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def my_patient_dashboard(request: Request) -> Response:
    """Dashboard summary for the authenticated patient."""
    profile = getattr(request.user, "patient_profile", None)
    if profile is None:
        return Response(
            {"detail": "Patient profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    consultations = Consultation.objects.filter(patient=profile)
    consultation_counts = consultations.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status__in=ACTIVE_PATIENT_STATUSES)),
        awaiting_patient=Count(
            "id",
            filter=Q(status=ConsultationStatus.AWAITING_PATIENT_RESPONSE),
        ),
        awaiting_doctor=Count(
            "id",
            filter=Q(status=ConsultationStatus.AWAITING_DOCTOR_RESPONSE),
        ),
        intake_in_progress=Count(
            "id",
            filter=Q(status=ConsultationStatus.INTAKE_IN_PROGRESS),
        ),
        doctor_review=Count(
            "id",
            filter=Q(status=ConsultationStatus.DOCTOR_REVIEW),
        ),
        follow_up_required=Count(
            "id",
            filter=Q(status=ConsultationStatus.FOLLOW_UP_REQUIRED),
        ),
        physical_visit_required=Count(
            "id",
            filter=Q(status=ConsultationStatus.PHYSICAL_VISIT_REQUIRED),
        ),
        emergency_escalated=Count(
            "id",
            filter=Q(status=ConsultationStatus.EMERGENCY_ESCALATED),
        ),
        completed=Count(
            "id",
            filter=Q(status=ConsultationStatus.COMPLETED),
        ),
        cancelled=Count(
            "id",
            filter=Q(status=ConsultationStatus.CANCELLED),
        ),
    )

    unread_messages = (
        ConsultationMessage.objects.filter(consultation__patient=profile)
        .exclude(sender=request.user)
        .exclude(read_receipts__user=request.user)
    )
    unread_total = unread_messages.aggregate(
        total=Count("id", distinct=True)
    )["total"]
    unread_by_consultation = list(
        unread_messages.order_by()
        .values("consultation_id")
        .annotate(
            unread_count=Count("id", distinct=True),
            last_message_at=Max("sent_at"),
        )
    )

    dashboard_consultations = _dashboard_consultations(
        consultations,
        request.user,
    )
    recent_threads = [
        {
            "consultation_id": consultation.id,
            "doctor_name": consultation.doctor.user.full_name,
            "specialty_name": (
                consultation.specialty.name if consultation.specialty else None
            ),
            "unread_count": consultation.unread_messages,
            "last_message_at": consultation.last_message_at,
        }
        for consultation in dashboard_consultations.filter(
            last_message_at__isnull=False
        )
        .select_related("doctor__user", "specialty")
        .order_by("-unread_messages", "-last_message_at")[:5]
    ]

    attention_items = []
    attention_consultations = consultations.filter(
        Q(status__in=PATIENT_ATTENTION_STATUSES)
        | Q(status=ConsultationStatus.INTAKE_IN_PROGRESS)
    ).select_related("intake_session")
    for consultation in attention_consultations.order_by("-updated_at"):
        config = ATTENTION_CONFIG.get(consultation.status)
        if config:
            attention_items.append(
                _attention_item(
                    item_type=consultation.status,
                    consultation_id=consultation.id,
                    count=1,
                    created_at=consultation.updated_at,
                    action_path=(
                        f"/app/patient/consultations/{consultation.id}"
                    ),
                    **config,
                )
            )
        intake_session = getattr(consultation, "intake_session", None)
        if (
            consultation.status == ConsultationStatus.INTAKE_IN_PROGRESS
            and intake_session is not None
            and intake_session.status in INCOMPLETE_INTAKE_STATUSES
        ):
            attention_items.append(
                _attention_item(
                    item_type="intake_incomplete",
                    consultation_id=consultation.id,
                    title_key="patientDashboard.attention.intake.title",
                    description_key=(
                        "patientDashboard.attention.intake.description"
                    ),
                    count=1,
                    severity="warning",
                    created_at=intake_session.updated_at,
                    action_path=(
                        f"/app/patient/consultations/{consultation.id}/intake"
                    ),
                )
            )
    for row in unread_by_consultation:
        attention_items.append(
            _attention_item(
                item_type="unread_messages",
                consultation_id=row["consultation_id"],
                title_key="patientDashboard.attention.unreadMessages.title",
                description_key=(
                    "patientDashboard.attention.unreadMessages.description"
                ),
                count=row["unread_count"],
                severity="info",
                created_at=row["last_message_at"],
                action_path=(
                    f"/app/patient/messages/{row['consultation_id']}"
                ),
            )
        )
    attention_items.sort(
        key=lambda item: item["created_at"] or timezone.now(),
        reverse=True,
    )

    notifications = Notification.objects.filter(recipient=request.user)
    recent_notifications = [
        {
            "id": notification.id,
            "notification_type": notification.notification_type,
            "title": notification.title,
            "body": notification.body,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
            "consultation_id": notification.consultation_id,
        }
        for notification in notifications.order_by("-created_at")[:5]
    ]

    recent_consultations = [
        {
            "id": consultation.id,
            "status": consultation.status,
            "doctor_name": consultation.doctor.user.full_name,
            "specialty_name": (
                consultation.specialty.name if consultation.specialty else None
            ),
            "created_at": consultation.created_at,
            "updated_at": consultation.updated_at,
            "unread_messages": consultation.unread_messages,
            "needs_patient_action": (
                consultation.status in PATIENT_ATTENTION_STATUSES
                or (
                    consultation.status
                    == ConsultationStatus.INTAKE_IN_PROGRESS
                    and getattr(consultation, "intake_session", None) is not None
                    and consultation.intake_session.status
                    in INCOMPLETE_INTAKE_STATUSES
                )
            ),
            "has_medical_record": consultation.has_medical_record,
            "medical_record_id": consultation.medical_record_id,
        }
        for consultation in dashboard_consultations.select_related(
            "doctor__user",
            "specialty",
            "intake_session",
        ).order_by("-created_at")[:5]
    ]

    completion = calculate_profile_completion(request.user, profile)
    return Response({
        "consultations": consultation_counts,
        "attention": {
            "total": len(attention_items),
            "items": attention_items,
        },
        "messages": {
            "unread_total": unread_total,
            "recent_threads": recent_threads,
        },
        "notifications": {
            "unread_total": notifications.filter(is_read=False).count(),
            "recent": recent_notifications,
        },
        "profile": {
            "completion_percent": completion["percent"],
            "missing_fields": completion["missing_fields"],
            "emergency_contact_complete": (
                completion["emergency_contact_complete"]
            ),
            "basic_health_complete": completion["basic_health_complete"],
        },
        "recent_consultations": recent_consultations,
        "generated_at": timezone.now(),
    })
