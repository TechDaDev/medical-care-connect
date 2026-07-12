from django.conf import settings
from rest_framework.response import Response


def set_auth_cookies(response: Response, access_token: str, refresh_token: str | None = None) -> None:
    """Set HTTP-only JWT cookies on the response."""
    jwt_settings = settings.SIMPLE_JWT
    secure = jwt_settings.get("AUTH_COOKIE_SECURE", False)
    httponly = jwt_settings.get("AUTH_COOKIE_HTTP_ONLY", True)
    samesite = jwt_settings.get("AUTH_COOKIE_SAMESITE", "Lax")
    path = jwt_settings.get("AUTH_COOKIE_PATH", "/")

    response.set_cookie(
        key=jwt_settings["AUTH_COOKIE"],
        value=access_token,
        max_age=int(jwt_settings["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        secure=secure,
        httponly=httponly,
        samesite=samesite,
        path=path,
    )

    if refresh_token is not None:
        response.set_cookie(
            key=jwt_settings["AUTH_COOKIE_REFRESH"],
            value=refresh_token,
            max_age=int(jwt_settings["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            secure=secure,
            httponly=httponly,
            samesite=samesite,
            path=path,
        )


def clear_auth_cookies(response: Response) -> None:
    """Clear JWT auth cookies on the response."""
    jwt_settings = settings.SIMPLE_JWT
    response.delete_cookie(jwt_settings["AUTH_COOKIE"], path=jwt_settings.get("AUTH_COOKIE_PATH", "/"))
    response.delete_cookie(jwt_settings["AUTH_COOKIE_REFRESH"], path=jwt_settings.get("AUTH_COOKIE_PATH", "/"))
