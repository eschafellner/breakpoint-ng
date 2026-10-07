import hashlib
from django.contrib import messages
from django.contrib.auth.views import PasswordResetConfirmView
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.core.services import log_audit
from .forms import AccountRecoveryForm
from .services import request_account_recovery, reset_failed_logins
from .tokens import account_access_token_generator


def recovery_allowed(email, ip_address):
    email_key = (
        "account-recovery-email:" + hashlib.sha256(email.lower().encode()).hexdigest()
    )
    ip_key = (
        "account-recovery-ip:"
        + hashlib.sha256(ip_address.encode()).hexdigest()
        + f":{int(timezone.now().timestamp()) // 60}"
    )
    cache.add(ip_key, 0, timeout=120)
    if cache.incr(ip_key) > 10:
        return False
    return cache.add(email_key, True, timeout=60)


@never_cache
@require_http_methods(["GET", "POST"])
def account_recovery_view(request):
    form = AccountRecoveryForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if recovery_allowed(email, request.META.get("REMOTE_ADDR", "")):
            request_account_recovery(
                email, site_url=request.build_absolute_uri("/").rstrip("/")
            )
        return redirect("accounts:account_recovery_done")
    return render(
        request, "accounts/recovery.html", {"form": form, "title": "Zugang anfordern"}
    )


@never_cache
def account_recovery_done_view(request):
    return render(
        request, "accounts/recovery_done.html", {"title": "Zugang angefordert"}
    )


class AccountAccessConfirmView(PasswordResetConfirmView):
    template_name = "accounts/access_confirm.html"
    success_url = reverse_lazy("accounts:login")
    token_generator = account_access_token_generator

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        return user if user and user.is_active else None

    @transaction.atomic
    def form_valid(self, form):
        # Recheck the session token while holding the account lock.
        from django.contrib.auth.views import INTERNAL_RESET_SESSION_TOKEN
        from .models import User

        user = User.objects.select_for_update().get(pk=self.user.pk)
        if not user.is_active or not self.token_generator.check_token(
            user, self.request.session.get(INTERNAL_RESET_SESSION_TOKEN)
        ):
            form.add_error(None, "Der Link ist ungültig oder wurde bereits verwendet.")
            return self.form_invalid(form)
        form.user = user
        response = super().form_valid(form)
        user.email_verified = True
        user.email_verification_token = ""
        user.save(update_fields=["email_verified", "email_verification_token"])
        reset_failed_logins(user)
        log_audit(
            user=user,
            action="SET_ACCOUNT_PASSWORD",
            entity_type="User",
            entity_id=user.pk,
        )
        messages.success(
            self.request,
            "Dein Passwort wurde gespeichert. Du kannst dich jetzt anmelden.",
        )
        return response
