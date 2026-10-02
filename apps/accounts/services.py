from datetime import timedelta
from typing import Optional, Dict, Any
from django.contrib.auth.models import Group
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from apps.core.services import log_audit
from .models import User
from .permissions import ALL_ROLES

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15

def create_standard_groups() -> None:
    """Ensure standard groups exist in the database."""
    for role_name in ALL_ROLES:
        Group.objects.get_or_create(name=role_name)

def register_user(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str = "",
    birth_date = None,
    address_street: str = "",
    address_zip: str = "",
    address_city: str = "",
    account_type: str = User.AccountType.GUEST,
    apply_membership_type_id: Optional[int] = None,
    sepa_iban: str = "",
    consent_privacy: bool = True,
    ip_address: Optional[str] = None,
) -> User:
    """Register a new user and generate verification token."""
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
    token = user.generate_verification_token()

    # If membership application requested, create MembershipApplication
    if apply_membership_type_id:
        try:
            from apps.members.models import MembershipType, MembershipApplication
            mem_type = MembershipType.objects.get(pk=apply_membership_type_id)
            MembershipApplication.objects.create(
                user=user,
                requested_type=mem_type,
                status=MembershipApplication.Status.PENDING,
                sepa_iban=sepa_iban,
                sepa_mandate_date=timezone.now().date() if sepa_iban else None,
            )
        except Exception:
            pass

    log_audit(
        user=user,
        action="REGISTER",
        entity_type="User",
        entity_id=str(user.pk),
        changes={"email": user.email, "account_type": account_type},
        ip_address=ip_address,
    )

    send_verification_email(user, token)
    return user

def send_verification_email(user: User, token: str) -> None:
    """Send double-opt-in email with verification link."""
    verification_link = f"/accounts/verify-email/{token}/"
    subject = "Bitte bestätige deine E-Mail-Adresse beim TC Musterdorf"
    message = (
        f"Hallo {user.first_name},\n\n"
        f"vielen Dank für deine Registrierung beim TC Musterdorf.\n"
        f"Bitte klicke auf den folgenden Link, um deine E-Mail-Adresse zu bestätigen:\n\n"
        f"{verification_link}\n\n"
        f"Sportliche Grüße,\n"
        f"Dein TC Musterdorf Team"
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"),
        recipient_list=[user.email],
        fail_silently=True,
    )

def verify_email(token: str) -> Optional[User]:
    """Verify email via token and activate login capability."""
    if not token:
        return None
    try:
        user = User.objects.get(email_verification_token=token)
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

def record_failed_login(email: str, ip_address: Optional[str] = None) -> bool:
    """Record a failed login. If limit reached, lock account for 15 minutes."""
    try:
        user = User.objects.get(email__iexact=email)
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = timezone.now() + timedelta(minutes=LOCK_DURATION_MINUTES)
            log_audit(
                user=user,
                action="ACCOUNT_LOCKED",
                entity_type="User",
                entity_id=str(user.pk),
                changes={"reason": f"{user.failed_login_attempts} failed logins", "locked_until": str(user.locked_until)},
                ip_address=ip_address,
            )
        user.save(update_fields=["failed_login_attempts", "locked_until"])
        return user.is_locked
    except User.DoesNotExist:
        return False

def reset_failed_logins(user: User) -> None:
    """Reset failed attempts on successful login."""
    if user.failed_login_attempts > 0 or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])

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
        "consent_privacy_at": str(user.consent_privacy_at) if user.consent_privacy_at else None,
        "date_joined": str(user.date_joined),
    }

    # Membership data
    try:
        from apps.members.models import Membership
        membership = Membership.objects.filter(user=user, status=Membership.Status.ACTIVE).first()
        if membership:
            data["membership"] = {
                "member_number": membership.member_number,
                "type": membership.type.name,
                "start_date": str(membership.start_date),
                "end_date": str(membership.end_date) if membership.end_date else None,
                "status": membership.status,
            }
    except Exception:
        pass

    # Billing / charges data
    try:
        from apps.billing.models import Charge
        charges = Charge.objects.filter(user=user)
        data["charges"] = [
            {
                "id": c.pk,
                "kind": c.kind,
                "amount": str(c.amount),
                "due_date": str(c.due_date),
                "status": c.status,
                "description": c.description,
            }
            for c in charges
        ]
    except Exception:
        pass

    return data
