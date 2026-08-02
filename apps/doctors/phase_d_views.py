"""Doctor Phase D operational endpoints."""

from django.db import transaction
from django.db.models import (
    Avg,
    BooleanField,
    Case,
    CharField,
    Count,
    DateTimeField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsApprovedDoctor
from apps.accounts.models import UserRole
from apps.attachments.services.factory import get_storage_backend
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory, AuditEventResult, AuditEventSeverity, RetentionClass
from apps.doctors.phase_d_serializers import (
    DoctorDataExportSerializer,
    DoctorDeletionCreateSerializer,
    DoctorDeletionRequestSerializer,
    DoctorMessageThreadQuerySerializer,
    DoctorMessageThreadSerializer,
    DoctorNotificationQuerySerializer,
    DoctorNotificationSerializer,
    DoctorReviewItemSerializer,
    DoctorReviewQuerySerializer,
    DoctorReviewResponseCreateSerializer,
    DoctorReviewResponseUpdateSerializer,
)
from apps.doctors.phase_d_services import (
    DoctorPhaseDError,
    create_doctor_review_response,
    update_doctor_review_response,
)
from apps.doctors.services import DOCTOR_ACTIVE_STATUSES, doctor_profile_completeness
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification
from apps.privacy.models import (
    AccountDeletionRequest,
    DataExportRequest,
    DeletionStatus,
    ExportStatus,
)
from apps.reviews.models import ConsultationReview, ReviewStatus


class DoctorPhaseDPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _doctor(request):
    return request.user.doctor_profile


def _as_uuid(value):
    from uuid import UUID

    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_message_threads(request: Request) -> Response:
    params = DoctorMessageThreadQuerySerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    values = params.validated_data
    latest_messages = ConsultationMessage.objects.filter(
        consultation_id=OuterRef("pk"), is_system_message=False
    ).order_by("-sent_at", "-created_at")
    unread = (
        ConsultationMessage.objects.filter(consultation_id=OuterRef("pk"), is_system_message=False)
        .exclude(sender=request.user)
        .exclude(read_receipts__user=request.user)
        .order_by()
        .values("consultation_id")
        .annotate(total=Count("id", distinct=True))
        .values("total")
    )
    threads = (
        Consultation.objects.filter(doctor=_doctor(request))
        .select_related("patient__user", "specialty")
        .annotate(
            unread_count=Coalesce(Subquery(unread, output_field=IntegerField()), 0),
            last_message_at=Subquery(latest_messages.values("sent_at")[:1], output_field=DateTimeField()),
            last_message_content=Subquery(latest_messages.values("content")[:1], output_field=CharField()),
            last_message_sender_role=Subquery(latest_messages.values("sender__role")[:1], output_field=CharField()),
        )
        .annotate(
            patient_awaiting_response=Case(
                When(last_message_sender_role=UserRole.PATIENT, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .filter(last_message_at__isnull=False)
    )
    if values.get("unread_only"):
        threads = threads.filter(unread_count__gt=0)
    if "patient_awaiting_response" in request.query_params:
        threads = threads.filter(patient_awaiting_response=values["patient_awaiting_response"])
    if values.get("group") == "active":
        threads = threads.filter(status__in=DOCTOR_ACTIVE_STATUSES)
    elif values.get("group") == "closed":
        threads = threads.filter(status__in=[ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED])
    for key in ("consultation_status", "priority"):
        if value := values.get(key):
            threads = threads.filter(**({"status": value} if key == "consultation_status" else {key: value}))
    if value := values.get("patient"):
        threads = threads.filter(patient_id=value)
    if value := values.get("specialty"):
        threads = threads.filter(specialty_id=value)
    if search := values.get("search"):
        search_filter = (
            Q(patient__user__first_name__icontains=search)
            | Q(patient__user__last_name__icontains=search)
            | Q(specialty__name__icontains=search)
            | Q(specialty__name_en__icontains=search)
            | Q(specialty__name_ar__icontains=search)
            | Q(specialty__name_ckb__icontains=search)
        )
        if identifier := _as_uuid(search):
            search_filter |= Q(id=identifier)
        threads = threads.filter(search_filter)
    ordering = values.get("ordering")
    if ordering == "patient":
        threads = threads.order_by("patient__user__first_name", "patient__user__last_name", "-last_message_at")
    elif ordering in {"last_message_at", "-last_message_at", "unread_count", "-unread_count"}:
        threads = threads.order_by(ordering, "-last_message_at")
    else:
        threads = threads.order_by("-patient_awaiting_response", "-unread_count", F("last_message_at").desc(nulls_last=True))
    paginator = DoctorPhaseDPagination()
    page = paginator.paginate_queryset(threads, request)
    return paginator.get_paginated_response(
        DoctorMessageThreadSerializer(page, many=True, context={"request": request}).data
    )


def _doctor_notification_queryset(request):
    return Notification.objects.filter(recipient=request.user).select_related(
        "consultation", "consultation__medical_record"
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_notifications(request: Request) -> Response:
    params = DoctorNotificationQuerySerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    values = params.validated_data
    queryset = _doctor_notification_queryset(request)
    if values.get("unread"):
        queryset = queryset.filter(is_read=False)
    if value := values.get("type"):
        queryset = queryset.filter(notification_type=value)
    if value := values.get("created_after"):
        queryset = queryset.filter(created_at__date__gte=value)
    if value := values.get("created_before"):
        queryset = queryset.filter(created_at__date__lte=value)
    queryset = queryset.order_by(values.get("ordering", "-created_at"))
    paginator = DoctorPhaseDPagination()
    page = paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(DoctorNotificationSerializer(page, many=True).data)
    response.data["unread_count"] = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_notification_read(request: Request, notification_id) -> Response:
    notification = _doctor_notification_queryset(request).filter(id=notification_id).first()
    if notification is None:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at", "updated_at"])
    return Response(DoctorNotificationSerializer(notification).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_notifications_read_all(request: Request) -> Response:
    updated = Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return Response({"marked_read": updated})


def _review_summary(queryset):
    data = queryset.filter(status=ReviewStatus.PUBLISHED).aggregate(
        average_rating=Avg("rating"),
        total_published=Count("id"),
        awaiting_response=Count("id", filter=Q(has_response=False)),
        responded=Count("id", filter=Q(has_response=True)),
        rating_1=Count("id", filter=Q(rating=1)),
        rating_2=Count("id", filter=Q(rating=2)),
        rating_3=Count("id", filter=Q(rating=3)),
        rating_4=Count("id", filter=Q(rating=4)),
        rating_5=Count("id", filter=Q(rating=5)),
    )
    return {
        "average_rating": round(float(data["average_rating"] or 0), 2),
        "total_published": data["total_published"],
        "awaiting_response": data["awaiting_response"],
        "responded": data["responded"],
        "rating_distribution": {str(value): data[f"rating_{value}"] for value in range(1, 6)},
    }


def _doctor_review_queryset(request):
    return ConsultationReview.objects.filter(consultation__doctor=_doctor(request)).select_related(
        "reviewer__user", "response"
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_reviews(request: Request) -> Response:
    params = DoctorReviewQuerySerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    values = params.validated_data
    base = _doctor_review_queryset(request)
    summary = _review_summary(base)
    reviews = base
    if "responded" in request.query_params:
        reviews = reviews.filter(has_response=values["responded"])
    if values.get("awaiting_response"):
        reviews = reviews.filter(has_response=False, status=ReviewStatus.PUBLISHED)
    if value := values.get("rating"):
        reviews = reviews.filter(rating=value)
    if value := values.get("minimum_rating"):
        reviews = reviews.filter(rating__gte=value)
    if value := values.get("maximum_rating"):
        reviews = reviews.filter(rating__lte=value)
    if value := values.get("status"):
        reviews = reviews.filter(status=value)
    if value := values.get("created_after"):
        reviews = reviews.filter(created_at__date__gte=value)
    if value := values.get("created_before"):
        reviews = reviews.filter(created_at__date__lte=value)
    ordering = values.get("ordering")
    reviews = reviews.order_by("has_response", "-created_at") if ordering == "priority" else reviews.order_by(ordering)
    paginator = DoctorPhaseDPagination()
    page = paginator.paginate_queryset(reviews, request)
    return Response(
        {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "summary": summary,
            "results": DoctorReviewItemSerializer(page, many=True).data,
        }
    )


def _review_error(error: DoctorPhaseDError):
    return Response({"detail": error.code, "code": error.code}, status=error.http_status)


@api_view(["POST", "PATCH"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_review_response(request: Request, review_id) -> Response:
    serializer_class = DoctorReviewResponseCreateSerializer if request.method == "POST" else DoctorReviewResponseUpdateSerializer
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        if request.method == "POST":
            _response, created = create_doctor_review_response(
                doctor=_doctor(request), review_id=review_id, **serializer.validated_data
            )
        else:
            _response, created = update_doctor_review_response(
                doctor=_doctor(request), review_id=review_id, **serializer.validated_data
            )
    except DoctorPhaseDError as error:
        return _review_error(error)
    review = _doctor_review_queryset(request).get(id=review_id)
    return Response(DoctorReviewItemSerializer(review).data, status=201 if request.method == "POST" and created else 200)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_privacy_overview(request: Request) -> Response:
    profile = _doctor(request)
    active_export = DataExportRequest.objects.filter(
        subject_user=request.user, status__in=[ExportStatus.PENDING, ExportStatus.PROCESSING]
    ).exists()
    active_deletion = AccountDeletionRequest.objects.filter(
        subject_user=request.user,
        status__in=[DeletionStatus.PENDING, DeletionStatus.APPROVED, DeletionStatus.PROCESSING],
    ).first()
    return Response(
        {
            "profile_visibility": "public" if profile.is_approved and request.user.is_active else "private",
            "profile_completion": doctor_profile_completeness(profile),
            "active_export": active_export,
            "active_deletion_request": DoctorDeletionRequestSerializer(active_deletion).data if active_deletion else None,
            "retention": {"clinical_records_may_be_retained": True, "audit_records_may_be_retained": True},
            "links": {
                "exports": "/app/doctor/privacy/exports",
                "deletion": "/app/doctor/privacy/deletion",
                "profile": "/app/doctor/profile",
            },
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_privacy_exports(request: Request) -> Response:
    if request.method == "POST":
        with transaction.atomic():
            type(request.user).objects.select_for_update().get(pk=request.user.pk)
            if DataExportRequest.objects.filter(
                subject_user=request.user, status__in=[ExportStatus.PENDING, ExportStatus.PROCESSING]
            ).exists():
                return Response({"detail": "active_export_exists", "code": "active_export_exists"}, status=409)
            export = DataExportRequest.objects.create(
                requested_by=request.user, subject_user=request.user, status=ExportStatus.PENDING
            )
        from apps.core.security_events import data_export_requested

        data_export_requested(str(request.user.id))
        return Response(DoctorDataExportSerializer(export).data, status=201)
    queryset = DataExportRequest.objects.filter(subject_user=request.user).order_by("-requested_at")
    paginator = DoctorPhaseDPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(DoctorDataExportSerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_privacy_export_download(request: Request, export_id) -> HttpResponse | Response:
    export = DataExportRequest.objects.filter(id=export_id, subject_user=request.user).first()
    if export is None:
        return Response({"detail": "not_found", "code": "not_found"}, status=404)
    if export.status == ExportStatus.EXPIRED:
        return Response({"detail": "expired", "code": "expired"}, status=410)
    if export.status != ExportStatus.COMPLETED:
        return Response({"detail": "not_ready", "code": "not_ready"}, status=409)
    if not export.storage_key or not export.storage_provider:
        return Response({"detail": "storage_error", "code": "storage_error"}, status=503)
    try:
        stored = get_storage_backend().open(export.storage_key)
        if stored is None:
            raise FileNotFoundError
        content = stored.read()
        stored.close()
    except Exception:
        return Response({"detail": "storage_error", "code": "storage_error"}, status=503)
    response = HttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="doctor-data-export-{export.id}.zip"'
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_privacy_deletion_requests(request: Request) -> Response:
    if request.method == "POST":
        serializer = DoctorDeletionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            type(request.user).objects.select_for_update().get(pk=request.user.pk)
            if AccountDeletionRequest.objects.filter(
                subject_user=request.user,
                status__in=[DeletionStatus.PENDING, DeletionStatus.APPROVED, DeletionStatus.PROCESSING],
            ).exists():
                return Response({"detail": "active_deletion_request_exists", "code": "active_deletion_request_exists"}, status=409)
            deletion = AccountDeletionRequest.objects.create(
                subject_user=request.user,
                requested_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        create_audit_event(
            event_type="privacy.deletion.requested",
            category=AuditEventCategory.PRIVACY,
            severity=AuditEventSeverity.INFO,
            result=AuditEventResult.SUCCESS,
            actor_id=str(request.user.id),
            actor_role=request.user.role,
            target_type="AccountDeletionRequest",
            target_id=str(deletion.id),
            summary="Doctor submitted account deletion request.",
            metadata={"reason_present": True},
            retention_class=RetentionClass.PRIVACY_DECISION,
        )
        return Response(DoctorDeletionRequestSerializer(deletion).data, status=201)
    queryset = AccountDeletionRequest.objects.filter(subject_user=request.user).order_by("-requested_at")
    paginator = DoctorPhaseDPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(DoctorDeletionRequestSerializer(page, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def doctor_privacy_deletion_cancel(request: Request, deletion_id) -> Response:
    with transaction.atomic():
        deletion = AccountDeletionRequest.objects.select_for_update().filter(
            id=deletion_id, subject_user=request.user
        ).first()
        if deletion is None:
            return Response({"detail": "not_found", "code": "not_found"}, status=404)
        if deletion.status != DeletionStatus.PENDING:
            return Response({"detail": "cannot_cancel", "code": "cannot_cancel"}, status=409)
        deletion.status = DeletionStatus.CANCELLED
        deletion.save(update_fields=["status"])
    return Response(DoctorDeletionRequestSerializer(deletion).data)
