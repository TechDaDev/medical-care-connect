"""Custom DRF exception handler for consistent API error responses."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.accounts.authentication import CSRFFailure
from apps.core.security_events import (
    csrf_failed,
    permission_denied,
    throttle_exceeded,
)


def custom_exception_handler(exc, context):
    """DRF exception handler that normalizes error responses.

    Includes request_id for correlation when available.

    Returns:
        {
            "detail": "Human-readable message",
            "code": "error_code",
            "fields": { ... },   # validation errors per field (optional)
            "request_id": "uuid"  # correlation ID (optional)
        }
    """
    response = exception_handler(exc, context)

    if response is not None:
        detail = _extract_detail(response.data)
        errors = {
            "detail": detail,
            "code": _get_code(exc),
        }

        # Attach request_id from request if available
        request = context.get("request") if isinstance(context, dict) else None
        if request and hasattr(request, "request_id"):
            errors["request_id"] = request.request_id

        # Preserve DRF field-level validation errors
        if isinstance(response.data, dict) and any(
            isinstance(v, (list, dict)) for v in response.data.values()
        ):
            errors["fields"] = response.data

        response.data = errors

        # Log security events
        _log_security_event(exc, request)
    else:
        # Handle non-DRF exceptions gracefully
        response = _handle_unhandled_exception(exc, context)

    return response


def _log_security_event(exc, request):
    """Log security events for CSRF, permission, and throttle failures."""
    if isinstance(exc, CSRFFailure):
        user_id = str(request.user.id) if request and request.user.is_authenticated else ""
        path = request.path if request else ""
        csrf_failed(user_id=user_id, path=path)
        return

    if isinstance(exc, (exceptions.PermissionDenied, DjangoPermissionDenied)):
        user_id = str(request.user.id) if request and request.user.is_authenticated else ""
        role = request.user.role if request and request.user.is_authenticated else ""
        path = request.path if request else ""
        permission_denied(user_id=user_id, role=role, path=path)
        return

    if isinstance(exc, exceptions.Throttled):
        user_id = str(request.user.id) if request and request.user.is_authenticated else ""
        path = request.path if request else ""
        rate = getattr(exc, "wait", None)
        throttle_exceeded(user_id=user_id, path=path, rate=str(rate) if rate else "")
        return


def _extract_detail(data):
    """Extract a readable detail string from DRF error data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        item = data[0]
        return str(item) if isinstance(item, str) else str(item[0]) if isinstance(item, (list, tuple)) else str(item)
    if isinstance(data, dict):
        # Look for a top-level "detail" key
        if "detail" in data:
            return _extract_detail(data["detail"])
        # Pick the first field error
        first_key = next(iter(data), None)
        if first_key:
            return _extract_detail(data[first_key])
    return "An error occurred."


def _get_code(exc):
    """Map exception types to error codes."""
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    if isinstance(exc, CSRFFailure):
        return "csrf_failed"
    if isinstance(exc, exceptions.AuthenticationFailed):
        return "authentication_failed"
    if isinstance(exc, exceptions.NotAuthenticated):
        return "not_authenticated"
    if isinstance(exc, exceptions.PermissionDenied):
        return "permission_denied"
    if isinstance(exc, DjangoPermissionDenied):
        return "permission_denied"
    if isinstance(exc, Http404):
        return "not_found"
    if isinstance(exc, exceptions.NotFound):
        return "not_found"
    if isinstance(exc, exceptions.MethodNotAllowed):
        return "method_not_allowed"
    if isinstance(exc, exceptions.Throttled):
        return "throttled"
    if isinstance(exc, exceptions.APIException):
        # Check for specific status codes
        if getattr(exc, "status_code", None) == status.HTTP_409_CONFLICT:
            return "conflict"
        return "api_error"
    return "internal_error"


def _handle_unhandled_exception(exc, context=None):
    """Handle unhandled exceptions without exposing internals."""
    request_id = ""
    if context and isinstance(context, dict):
        request = context.get("request")
        if request and hasattr(request, "request_id"):
            request_id = request.request_id
    body = {"detail": "Unable to complete the request.", "code": "internal_error"}
    if request_id:
        body["request_id"] = request_id
    if isinstance(exc, Http404):
        return Response(
            {"detail": "Not found.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        body,
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
