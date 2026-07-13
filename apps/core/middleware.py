"""
Request correlation ID middleware.

- Accepts X-Request-ID only if UUID-safe
- Generates UUID otherwise
- Attaches to request as request.request_id
- Adds X-Request-ID header to every response
- Exposes to structured logger
"""

import re
import uuid

from django.utils.deprecation import MiddlewareMixin


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z",
    re.IGNORECASE,
)


class RequestIDMiddleware(MiddlewareMixin):
    """Attach correlation ID to each request/response cycle."""

    def process_request(self, request):
        raw = request.META.get("HTTP_X_REQUEST_ID", "")
        if raw and UUID_RE.match(raw.strip()):
            request.request_id = raw.strip()
        else:
            request.request_id = str(uuid.uuid4())

    def process_response(self, request, response):
        rid = getattr(request, "request_id", "")
        response["X-Request-ID"] = rid
        return response
