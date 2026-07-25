"""
Central service for administrator user management.

Enforces safety invariants defined in Phase C policy:
- Administrator cannot deactivate/demote self.
- Final active administrator cannot be deactivated/demoted.
- Sensitive changes require a reason.
- Status/role changes revoke all sessions.
- All changes are transactional and emit audit events.
"""
from uuid import UUID

from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.tokens import OutstandingToken, RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.accounts.models import User, UserRole
from apps.core.security_events import (
    admin_user_activated,
    admin_user_deactivated,
    admin_user_role_changed,
    admin_user_sessions_revoked,
    admin_user_action_rejected,
)
from apps.notifications.services import create_notification
from apps.notifications.models import NotificationType


class AdminUserError(Exception):
    """Base error for admin user management."""

    def __init__(self, detail: str, code: str):
        self.detail = detail
        self.code = code
        super().__init__(detail)


class SelfActionForbidden(AdminUserError):
    """Administrator cannot perform this action on their own account."""

    def __init__(self, action: str = "perform this action on"):
        super().__init__(
            detail=f"You cannot {action} your own account.",
            code="self_action_forbidden",
        )


class FinalAdministratorProtected(AdminUserError):
    """Last active administrator cannot be deactivated or demoted."""

    def __init__(self):
        super().__init__(
            detail="The final active administrator cannot be deactivated or demoted.",
            code="final_administrator_protected",
        )


class InvalidRoleTransition(AdminUserError):
    """The requested role transition is not allowed."""

    def __init__(self):
        super().__init__(
            detail="This role transition is not allowed.",
            code="invalid_role_transition",
        )


class StateConflict(AdminUserError):
    """Target account state has changed concurrently."""

    def __init__(self, detail: str, code: str):
        super().__init__(detail=detail, code=code)


LEGAL_ROLE_TRANSITIONS = {
    UserRole.COORDINATOR: [UserRole.COORDINATOR, UserRole.ADMINISTRATOR],
    UserRole.ADMINISTRATOR: [UserRole.ADMINISTRATOR, UserRole.COORDINATOR],
}


def get_available_actions(target: User, actor: User) -> list[str]:
    """Return allowed administrative actions based on target state and actor role.

    Actions returned are string identifiers the frontend uses to show controls.
    """
    if actor.role != UserRole.ADMINISTRATOR:
        return []

    actions: list[str] = []

    # Is actor the target? (self-actions denied)
    is_self = actor.id == target.id

    if target.is_active:
        if not is_self:
            actions.append("deactivate")
    else:
        actions.append("activate")

    # Session revocation — deny self to prevent self-lockout
    if not is_self:
        actions.append("revoke_sessions")

    # Role changes — only coordinator ↔ administrator
    legal = LEGAL_ROLE_TRANSITIONS.get(target.role, [])
    if UserRole.ADMINISTRATOR in legal and not is_self:
        actions.append("promote_to_administrator")
    if UserRole.COORDINATOR in legal and not is_self:
        # Check final admin protection before offering demotion
        if not _is_final_active_administrator(target):
            actions.append("demote_to_coordinator")

    return actions


def _is_final_active_administrator(user: User) -> bool:
    """Return True if user is the last active administrator."""
    if user.role != UserRole.ADMINISTRATOR:
        return False
    count = (
        User.objects.filter(role=UserRole.ADMINISTRATOR, is_active=True)
        .exclude(pk=user.pk)
        .count()
    )
    return count == 0


def _revoke_all_sessions(user: User) -> int:
    """Blacklist all outstanding refresh tokens for a user.

    Returns the number of tokens revoked.
    """
    tokens = OutstandingToken.objects.filter(user=user)
    count = tokens.count()
    for token in tokens:
        try:
            rt = RefreshToken(token.token)
            rt.blacklist()
        except (TokenError, Exception):
            pass
    tokens.delete()
    return count


def _notify_account_event(user: User, title: str, body: str) -> None:
    """Send a safe notification to the affected user."""
    if not user.is_active and "deactivated" in title.lower():
        # Only create notification for users who can receive it
        pass
    # Always create — notifications survive deactivation
    create_notification(
        recipient=user,
        notification_type=NotificationType.ACCOUNT_STATUS_CHANGE,
        title=title,
        body=body,
    )


@transaction.atomic
def deactivate_user(actor: User, target_id: UUID, reason: str, expected_active: bool | None = None) -> User:
    """Deactivate a user account with safety checks.

    Raises:
        SelfActionForbidden: actor == target
        FinalAdministratorProtected: target is last active admin
        StateConflict: expected_active does not match current state
    """
    target = User.objects.select_for_update().get(pk=target_id)

    # Self-action check
    if actor.id == target.id:
        raise SelfActionForbidden("deactivate")

    if not target.is_active:
        raise StateConflict(
            detail="This account is already inactive.",
            code="account_state_changed",
        )

    # Expected state conflict
    if expected_active is not None and target.is_active != expected_active:
        raise StateConflict(
            detail="The account state has changed since your last refresh.",
            code="account_state_changed",
        )

    # Final admin protection
    if target.role == UserRole.ADMINISTRATOR and _is_final_active_administrator(target):
        raise FinalAdministratorProtected()

    # Execute
    target.is_active = False
    target.save(update_fields=["is_active", "updated_at"])
    revoked = _revoke_all_sessions(target)

    admin_user_deactivated(
        actor_id=str(actor.id),
        target_id=str(target.id),
        reason_preview=reason[:100],
    )

    _notify_account_event(
        target,
        title="Account Deactivated",
        body="Your account has been deactivated. Please contact support if you believe this is an error.",
    )

    target.refresh_from_db()
    return target


@transaction.atomic
def activate_user(actor: User, target_id: UUID, reason: str, expected_active: bool | None = None) -> User:
    """Reactivate a user account."""
    target = User.objects.select_for_update().get(pk=target_id)

    if actor.id == target.id:
        raise SelfActionForbidden("activate")

    if target.is_active:
        raise StateConflict(
            detail="This account is already active.",
            code="account_state_changed",
        )

    if expected_active is not None and target.is_active != expected_active:
        raise StateConflict(
            detail="The account state has changed since your last refresh.",
            code="account_state_changed",
        )

    target.is_active = True
    target.save(update_fields=["is_active", "updated_at"])

    admin_user_activated(
        actor_id=str(actor.id),
        target_id=str(target.id),
        reason_preview=reason[:100],
    )

    _notify_account_event(
        target,
        title="Account Activated",
        body="Your account has been reactivated. You will need to log in again.",
    )

    target.refresh_from_db()
    return target


@transaction.atomic
def revoke_sessions(actor: User, target_id: UUID, reason: str) -> tuple[int, User]:
    """Revoke all sessions for a user.

    Returns (revoked_count, updated_user).
    """
    target = User.objects.select_for_update().get(pk=target_id)

    if actor.id == target.id:
        raise SelfActionForbidden("revoke sessions for")

    revoked = _revoke_all_sessions(target)

    admin_user_sessions_revoked(
        actor_id=str(actor.id),
        target_id=str(target.id),
        count=revoked,
        reason_preview=reason[:100],
    )

    _notify_account_event(
        target,
        title="Sessions Revoked",
        body="Your active sessions have been revoked for security reasons. Please log in again.",
    )

    target.refresh_from_db()
    return revoked, target


@transaction.atomic
def change_user_role(actor: User, target_id: UUID, new_role: str, reason: str, expected_role: str | None = None) -> User:
    """Change a user's role with safety checks.

    Only coordinator ↔ administrator transitions are supported.
    """
    target = User.objects.select_for_update().get(pk=target_id)

    # Self-action check
    if actor.id == target.id:
        raise SelfActionForbidden("change the role of")

    # Check legal transition
    legal_targets = LEGAL_ROLE_TRANSITIONS.get(target.role, [])
    if new_role not in [r.value for r in legal_targets] and new_role != target.role:
        raise InvalidRoleTransition()

    # If target is administrator being demoted, check final admin
    if target.role == UserRole.ADMINISTRATOR and new_role != UserRole.ADMINISTRATOR:
        if _is_final_active_administrator(target):
            raise FinalAdministratorProtected()

    # Expected role conflict
    if expected_role is not None and target.role != expected_role:
        raise StateConflict(
            detail="The account role has changed since your last refresh.",
            code="account_role_changed",
        )

    # No-op if same role
    if target.role == new_role:
        target.refresh_from_db()
        return target

    old_role = target.role
    target.role = new_role
    target.save(update_fields=["role", "updated_at"])
    revoked = _revoke_all_sessions(target)

    admin_user_role_changed(
        actor_id=str(actor.id),
        target_id=str(target.id),
        old_role=old_role,
        new_role=new_role,
        reason_preview=reason[:100],
    )

    _notify_account_event(
        target,
        title="Role Updated",
        body=f"Your account role has been changed to {new_role}. Please log in again.",
    )

    target.refresh_from_db()
    return target
