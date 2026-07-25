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
