import json
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from .forms import LoginForm, RegistrationForm, ProfileForm
from .services import (
    register_user,
    verify_email,
    record_failed_login,
    reset_failed_logins,
    export_user_data,
)
from apps.core.services import log_audit


def login_view(request):
    """Email + password login with lock-out protection."""
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = LoginForm(request.POST)
        email = request.POST.get("email", "")
        if form.is_valid():
            user = form.user
            reset_failed_logins(user)
            login(request, user)
            messages.success(
                request,
                _("Willkommen zurück, %(name)s!")
                % {"name": user.first_name or user.email},
            )
            next_url = request.POST.get("next") or request.GET.get("next")
            if not next_url or not url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                next_url = "core:home"
            return redirect(next_url)
        else:
            # Check if this email exists to track failed attempts
            is_locked = False
            if not getattr(form, "credentials_valid", False):
                is_locked = record_failed_login(
                    email, ip_address=request.META.get("REMOTE_ADDR")
                )
            if is_locked:
                messages.error(
                    request,
                    _(
                        "Zu viele Fehlversuche. Dein Konto wurde für 15 Minuten vorübergehend gesperrt."
                    ),
                )
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "title": "Anmelden"})


@require_POST
def logout_view(request):
    """User logout."""
    logout(request)
    messages.info(request, _("Du hast dich erfolgreich abgemeldet."))
    return redirect("core:home")


def register_view(request):
    """Self-registration as guest or member applicant."""
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                user = register_user(
                    email=data["email"],
                    password=data["password"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    phone=data.get("phone", ""),
                    birth_date=data.get("birth_date"),
                    address_street=data.get("address_street", ""),
                    address_zip=data.get("address_zip", ""),
                    address_city=data.get("address_city", ""),
                    account_type=data["account_type"],
                    apply_membership_type_id=(
                        int(data["membership_type"])
                        if data.get("membership_type")
                        else None
                    ),
                    sepa_iban=data.get("sepa_iban", ""),
                    consent_privacy=data["consent_privacy"],
                    ip_address=request.META.get("REMOTE_ADDR"),
                    site_url=request.build_absolute_uri("/").rstrip("/"),
                )
            except (ValidationError, IntegrityError):
                form.add_error(
                    None,
                    _(
                        "Registrierung nicht möglich. Bitte prüfe E-Mail und Mitgliedschaftsart."
                    ),
                )
            else:
                return render(
                    request,
                    "accounts/registered_success.html",
                    {
                        "user": user,
                        "membership_requested": data["account_type"] == "MEMBER",
                        "title": "Registrierung erfolgreich",
                    },
                )
    else:
        form = RegistrationForm()

    return render(
        request, "accounts/register.html", {"form": form, "title": "Registrieren"}
    )


def verify_email_view(request, token):
    """Handle verification link."""
    user = verify_email(token)
    if user:
        messages.success(
            request,
            _(
                "Deine E-Mail-Adresse wurde erfolgreich bestätigt! Du kannst dich jetzt anmelden."
            ),
        )
        return redirect("accounts:login")
    else:
        messages.error(request, _("Der Bestätigungslink ist ungültig oder abgelaufen."))
        return redirect("accounts:login")


@login_required
def profile_view(request):
    """User profile details and editing."""
    user = request.user
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            log_audit(
                user=user,
                action="UPDATE_PROFILE",
                entity_type="User",
                entity_id=str(user.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, _("Dein Profil wurde erfolgreich aktualisiert."))
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=user)

    from apps.courts.models import Booking
    from apps.billing.models import Charge
    from apps.members.selectors import get_active_members_directory

    recent_bookings = Booking.objects.filter(booked_by=user).order_by("-start")[:5]
    charges = Charge.objects.filter(user=user).order_by("-due_date")[:10]
    membership = get_active_members_directory().filter(user=user).first()

    context = {
        "title": "Mein Profil",
        "form": form,
        "membership": membership,
        "recent_bookings": recent_bookings,
        "charges": charges,
    }
    return render(request, "accounts/profile.html", context)


@login_required
def export_data_view(request):
    """DSGVO Art. 15: Download personal data as JSON."""
    user = request.user
    data = export_user_data(user)
    log_audit(
        user=user,
        action="DATA_EXPORT",
        entity_type="User",
        entity_id=str(user.pk),
        ip_address=request.META.get("REMOTE_ADDR"),
    )
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    response = HttpResponse(json_data, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="datenexport_{user.pk}.json"'
    )
    return response
