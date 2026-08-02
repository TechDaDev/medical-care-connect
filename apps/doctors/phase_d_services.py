"""Transactional Doctor Phase D mutations."""

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory, AuditEventResult, AuditEventSeverity
from apps.reviews.models import (
    ConsultationReview,
    DoctorReviewResponse,
    ReviewResponseAction,
    ReviewStatus,
)
from apps.reviews.services import notify_review_response


class DoctorPhaseDError(Exception):
    def __init__(self, code: str, *, http_status: int = 400):
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _audit_response_action(*, event_type: str, doctor, review, changed_fields: list[str]):
    create_audit_event(
        event_type=event_type,
        category=AuditEventCategory.CONSULTATION,
        severity=AuditEventSeverity.INFO,
        result=AuditEventResult.SUCCESS,
        actor_id=str(doctor.user_id),
        actor_role=doctor.user.role,
        target_type="review",
        target_id=str(review.id),
        summary="Doctor review response changed.",
        metadata={"changed_fields": changed_fields},
    )


def _replay_response_action(*, doctor, review_id, action, client_request_id, fingerprint):
    prior = ReviewResponseAction.objects.filter(
        doctor=doctor, client_request_id=client_request_id
    ).first()
    if prior is None:
        return None
    if prior.action != action or prior.review_id != review_id or prior.request_fingerprint != fingerprint:
        raise DoctorPhaseDError("duplicate_request", http_status=409)
    response = DoctorReviewResponse.objects.filter(review_id=review_id, doctor=doctor).first()
    if response:
        return response, False
    raise DoctorPhaseDError("review_not_found", http_status=404)


@transaction.atomic
def create_doctor_review_response(*, doctor, review_id, body, client_request_id):
    fingerprint = _fingerprint({"action": "create", "review_id": review_id, "body": body})
    replay = _replay_response_action(
        doctor=doctor, review_id=review_id, action=ReviewResponseAction.Action.CREATE,
        client_request_id=client_request_id, fingerprint=fingerprint,
    )
    if replay:
        return replay

    review = (
        ConsultationReview.objects.select_for_update()
        .select_related("consultation__doctor", "consultation__patient__user")
        .filter(id=review_id, consultation__doctor=doctor)
        .first()
    )
    if review is None:
        raise DoctorPhaseDError("review_not_found", http_status=404)
    replay = _replay_response_action(
        doctor=doctor, review_id=review_id, action=ReviewResponseAction.Action.CREATE,
        client_request_id=client_request_id, fingerprint=fingerprint,
    )
    if replay:
        return replay
    if review.status != ReviewStatus.PUBLISHED:
        raise DoctorPhaseDError("review_not_eligible", http_status=409)
    if DoctorReviewResponse.objects.filter(review=review).exists():
        raise DoctorPhaseDError("response_already_exists", http_status=409)

    response = DoctorReviewResponse.objects.create(review=review, doctor=doctor, body=body)
    review.has_response = True
    review.save(update_fields=["has_response", "updated_at"])
    ReviewResponseAction.objects.create(
        review=review,
        doctor=doctor,
        action=ReviewResponseAction.Action.CREATE,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    _audit_response_action(
        event_type="doctor_review_response_created",
        doctor=doctor,
        review=review,
        changed_fields=["body"],
    )
    notify_review_response(review, response)
    return response, True


@transaction.atomic
def update_doctor_review_response(
    *, doctor, review_id, body, expected_updated_at, client_request_id
):
    fingerprint = _fingerprint(
        {
            "action": "update",
            "review_id": review_id,
            "body": body,
            "expected_updated_at": expected_updated_at,
        }
    )
    replay = _replay_response_action(
        doctor=doctor, review_id=review_id, action=ReviewResponseAction.Action.UPDATE,
        client_request_id=client_request_id, fingerprint=fingerprint,
    )
    if replay:
        return replay

    review = (
        ConsultationReview.objects.select_for_update()
        .select_related("consultation__doctor")
        .filter(id=review_id, consultation__doctor=doctor)
        .first()
    )
    if review is None:
        raise DoctorPhaseDError("review_not_found", http_status=404)
    replay = _replay_response_action(
        doctor=doctor, review_id=review_id, action=ReviewResponseAction.Action.UPDATE,
        client_request_id=client_request_id, fingerprint=fingerprint,
    )
    if replay:
        return replay
    if review.status != ReviewStatus.PUBLISHED:
        raise DoctorPhaseDError("review_not_eligible", http_status=409)
    response = DoctorReviewResponse.objects.select_for_update().filter(review=review, doctor=doctor).first()
    if response is None:
        raise DoctorPhaseDError("review_not_found", http_status=404)
    if timezone.now() > response.created_at + timedelta(hours=72):
        raise DoctorPhaseDError("response_edit_window_closed", http_status=409)
    if response.updated_at != expected_updated_at:
        raise DoctorPhaseDError("response_changed", http_status=409)

    response.body = body
    response.save(update_fields=["body", "updated_at"])
    ReviewResponseAction.objects.create(
        review=review,
        doctor=doctor,
        action=ReviewResponseAction.Action.UPDATE,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    _audit_response_action(
        event_type="doctor_review_response_updated",
        doctor=doctor,
        review=review,
        changed_fields=["body"],
    )
    return response, True
