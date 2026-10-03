from datetime import timedelta
from typing import Optional, Dict, Any
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.core.services import log_audit, send_mail_after_commit
from .models import User
from .permissions import ALL_ROLES

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15


def create_standard_groups() -> None:
    """Ensure standard groups exist in the database."""
    for role_name in ALL_ROLES:
        Group.objects.get_or_create(name=role_name)


@transaction.atomic
def register_user(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str = "",
    birth_date=None,
    address_street: str = "",
    address_zip: str = "",
    address_city: str = "",
    account_type: str = User.AccountType.GUEST,
    apply_membership_type_id: Optional[int] = None,
    sepa_iban: str = "",
    consent_privacy: bool = True,
    ip_address: Optional[str] = None,
    site_url: Optional[str] = None,
) -> User:
    """Register a new user and generate verification token."""
    from apps.members.models import MembershipType, MembershipApplication

    email = email.strip().lower()
    validate_email(email)
    if account_type not in User.AccountType.values or not consent_privacy:
        raise ValidationError(
            _("Registrierungsart oder Datenschutzeinwilligung ungültig.")
        )
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError(_("Diese E-Mail-Adresse ist bereits registriert."))
    mem_type = None
    if account_type == User.AccountType.MEMBER:
        mem_type = MembershipType.objects.filter(
            pk=apply_membership_type_id, is_active=True
        ).first()
        if not mem_type:
            raise ValidationError(_("Bitte wähle eine aktive Mitgliedschaftsart."))
    elif apply_membership_type_id:
        raise ValidationError(
            _("Mitgliedschaftsantrag erfordert die Registrierungsart Mitglied.")
        )
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        birth_date=birth_date,
        address_street=address_street,
        address_zip=address_zip,
        address_city=address_city,
        account_type=User.AccountType.GUEST,  # Applicants also start with GUEST permissions until approved
        email_verified=False,
        consent_privacy_at=timezone.now() if consent_privacy else None,
    )
    user.full_clean()
    token = user.generate_verification_token()

    # If membership application requested, create MembershipApplication
    if mem_type:
        application = MembershipApplication.objects.create(
            user=user,
            requested_type=mem_type,
            status=MembershipApplication.Status.PENDING,
            sepa_iban=sepa_iban,
            sepa_mandate_date=timezone.localdate() if sepa_iban else None,
        )
        application.full_clean()

    log_audit(
        user=user,
        action="REGISTER",
        entity_type="User",
        entity_id=str(user.pk),
        changes={"email": user.email, "account_type": account_type},
        ip_address=ip_address,
    )

    send_verification_email(user, token, site_url=site_url)
    return user


def send_verification_email(
    user: User, token: str, site_url: Optional[str] = None
) -> None:
    """Send double-opt-in email with verification link."""
    base_url = (
        getattr(settings, "PUBLIC_SITE_URL", "") or site_url or "http://localhost:8000"
    ).rstrip("/")
    verification_link = f"{base_url}/accounts/verify-email/{token}/"
    subject = "Bitte bestätige deine E-Mail-Adresse beim TC Musterdorf"
    message = (
        f"Hallo {user.first_name},\n\n"
        f"vielen Dank für deine Registrierung beim TC Musterdorf.\n"
        f"Bitte klicke auf den folgenden Link, um deine E-Mail-Adresse zu bestätigen:\n\n"
        f"{verification_link}\n\n"
        f"Sportliche Grüße,\n"
        f"Dein TC Musterdorf Team"
    )
    send_mail_after_commit(
        subject=subject,
        message=message,
        from_email=getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"
        ),
        recipient_list=[user.email],
        fail_silently=True,
    )


@transaction.atomic
def verify_email(token: str) -> Optional[User]:
    """Verify email via token and activate login capability."""
    if not token:
        return None
    try:
        user = User.objects.select_for_update().get(email_verification_token=token)
        user.email_verified = True
        user.email_verification_token = ""
        user.save(update_fields=["email_verified", "email_verification_token"])
        log_audit(
            user=user,
            action="EMAIL_VERIFIED",
            entity_type="User",
            entity_id=str(user.pk),
        )
        return user
    except User.DoesNotExist:
        return None


@transaction.atomic
def record_failed_login(email: str, ip_address: Optional[str] = None) -> bool:
    """Record a failed login. If limit reached, lock account for 15 minutes."""
    try:
        user = User.objects.select_for_update().get(email__iexact=email.strip())
        now = timezone.now()
        if user.is_locked:
            return True
        if (
            user.locked_until
            or not user.failed_login_window_started_at
            or user.failed_login_window_started_at
            <= now - timedelta(minutes=LOCK_DURATION_MINUTES)
        ):
            user.failed_login_attempts = 0
            user.locked_until = None
            user.failed_login_window_started_at = now
        user.last_failed_login_at = now
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = timezone.now() + timedelta(
                minutes=LOCK_DURATION_MINUTES
            )
            log_audit(
                user=user,
                action="ACCOUNT_LOCKED",
                entity_type="User",
                entity_id=str(user.pk),
                changes={
                    "reason": f"{user.failed_login_attempts} failed logins",
                    "locked_until": str(user.locked_until),
                },
                ip_address=ip_address,
            )
        user.save(
            update_fields=[
                "failed_login_attempts",
                "locked_until",
                "last_failed_login_at",
                "failed_login_window_started_at",
            ]
        )
        return user.is_locked
    except User.DoesNotExist:
        return False


def reset_failed_logins(user: User) -> None:
    """Reset failed attempts on successful login."""
    if user.failed_login_attempts > 0 or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_failed_login_at = None
        user.failed_login_window_started_at = None
        user.save(
            update_fields=[
                "failed_login_attempts",
                "locked_until",
                "last_failed_login_at",
                "failed_login_window_started_at",
            ]
        )


def export_user_data(user: User) -> Dict[str, Any]:
    """Export all personal data of user according to Art. 15 GDPR."""
    data = {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "birth_date": str(user.birth_date) if user.birth_date else None,
        "address": {
            "street": user.address_street,
            "zip": user.address_zip,
            "city": user.address_city,
        },
        "account_type": user.account_type,
        "email_verified": user.email_verified,
        "consent_privacy_at": (
            str(user.consent_privacy_at) if user.consent_privacy_at else None
        ),
        "date_joined": str(user.date_joined),
    }

    from apps.members.models import Membership
    from apps.billing.models import Charge
    from apps.courts.models import Booking
    from apps.tournaments.models import Entry
    from django.db.models import Q

    data["memberships"] = [
        {
            "member_number": membership.member_number,
            "type": membership.type.name,
            "start_date": str(membership.start_date),
            "end_date": str(membership.end_date) if membership.end_date else None,
            "status": membership.status,
        }
        for membership in Membership.objects.filter(user=user).select_related("type")
    ]
    active = next(
        (
            membership
            for membership in data["memberships"]
            if membership["status"] == Membership.Status.ACTIVE
        ),
        None,
    )
    if active:
        data["membership"] = active
    data["membership_applications"] = [
        {
            "id": application.pk,
            "requested_type": application.requested_type.name,
            "status": application.status,
            "created_at": str(application.created_at),
            "reviewed_at": (
                str(application.reviewed_at) if application.reviewed_at else None
            ),
            "rejection_reason": application.rejection_reason,
            "sepa_iban": application.sepa_iban,
            "sepa_mandate_date": (
                str(application.sepa_mandate_date)
                if application.sepa_mandate_date
                else None
            ),
        }
        for application in user.membership_applications.select_related("requested_type")
    ]
    data["charges"] = [
        {
            "id": charge.pk,
            "kind": charge.kind,
            "amount": str(charge.amount),
            "due_date": str(charge.due_date),
            "status": charge.status,
            "description": charge.description,
            "payments": [
                {
                    "id": payment.pk,
                    "amount": str(payment.amount),
                    "method": payment.method,
                    "paid_at": str(payment.paid_at),
                    "reference": payment.reference,
                }
                for payment in charge.payments.all()
            ],
        }
        for charge in Charge.objects.filter(user=user).prefetch_related("payments")
    ]
    data["bookings"] = [
        {
            "id": booking.pk,
            "court": booking.court.name,
            "start": str(booking.start),
            "end": str(booking.end),
            "status": booking.status,
            "total_price": str(booking.total_price),
            "booked_by_me": booking.booked_by_id == user.pk,
        }
        for booking in Booking.objects.filter(
            Q(booked_by=user) | Q(participants__user=user)
        )
        .select_related("court")
        .distinct()
    ]
    data["tournament_entries"] = [
        {
            "id": entry.pk,
            "competition": entry.competition.name,
            "tournament": entry.competition.tournament.name,
            "status": entry.status,
            "created_at": str(entry.created_at),
        }
        for entry in Entry.objects.filter(
            Q(player1=user) | Q(player2=user)
        ).select_related("competition__tournament")
    ]

    return data
