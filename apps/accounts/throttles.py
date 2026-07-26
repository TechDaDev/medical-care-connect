from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class RegisterRateThrottle(AnonRateThrottle):
    scope = "register"


class RefreshRateThrottle(AnonRateThrottle):
    scope = "refresh"


class AdminSensitiveWriteThrottle(UserRateThrottle):
    """Stricter throttle for sensitive administrator actions."""
    scope = "admin_sensitive_write"


class PrivacySensitiveWriteThrottle(UserRateThrottle):
    """Throttle for privacy-sensitive administrative actions."""
    scope = "privacy_sensitive_write"


class AuditExportThrottle(UserRateThrottle):
    """Throttle for audit CSV export."""
    scope = "audit_export"
