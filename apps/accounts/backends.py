from django.contrib.auth.backends import ModelBackend
from django.db import transaction

from .models import User
from .services import record_failed_login, reset_failed_logins


class ClubAuthenticationBackend(ModelBackend):
    """Use the same account checks and failure window for every login route."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get(User.USERNAME_FIELD)
        if not email or password is None:
            return None
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=email.strip())
                .first()
            )
            if user is None:
                # Match Django's password-hashing cost for unknown accounts.
                User().set_password(password)
                return None
            if user.is_locked:
                return None
            if not user.check_password(password):
                record_failed_login(
                    user.email,
                    ip_address=request.META.get("REMOTE_ADDR") if request else None,
                )
                return None
            if not self.user_can_authenticate(user):
                return None
            reset_failed_logins(user)
            return user

    def user_can_authenticate(self, user):
        return (
            super().user_can_authenticate(user)
            and user.email_verified
            and not user.is_locked
        )
