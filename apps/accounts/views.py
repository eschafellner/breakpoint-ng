import json
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _
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
            messages.success(request, _("Willkommen zurück, %(name)s!") % {"name": user.first_name or user.email})
            next_url = request.GET.get("next") or "core:home"
            return redirect(next_url)
        else:
            # Check if this email exists to track failed attempts
            is_locked = record_failed_login(email, ip_address=request.META.get("REMOTE_ADDR"))
            if is_locked:
                messages.error(
                    request,
                    _("Zu viele Fehlversuche. Dein Konto wurde für 15 Minuten vorübergehend gesperrt."),
                )
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "title": "Anmelden"})

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
                apply_membership_type_id=int(data["membership_type"]) if data.get("membership_type") else None,
                sepa_iban=data.get("sepa_iban", ""),
                consent_privacy=data["consent_privacy"],
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return render(
                request,
                "accounts/registered_success.html",
                {"user": user, "title": "Registrierung erfolgreich"},
            )
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form, "title": "Registrieren"})

def verify_email_view(request, token):
    """Handle verification link."""
    user = verify_email(token)
    if user:
        messages.success(request, _("Deine E-Mail-Adresse wurde erfolgreich bestätigt! Du kannst dich jetzt anmelden."))
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

    # Load user's bookings and charges for profile view
    recent_bookings = []
    charges = []
    try:
        from apps.courts.models import Booking
        recent_bookings = Booking.objects.filter(booked_by=user).order_by("-start")[:5]
    except Exception:
        pass

    try:
        from apps.billing.models import Charge
        charges = Charge.objects.filter(user=user).order_by("-due_date")[:10]
    except Exception:
        pass

    # Membership info
    membership = None
    try:
        from apps.members.models import Membership
        membership = Membership.objects.filter(user=user, status=Membership.Status.ACTIVE).first()
    except Exception:
        pass

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
    response["Content-Disposition"] = f'attachment; filename="datenexport_{user.pk}.json"'
    return response
