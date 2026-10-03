import csv
import io
from datetime import date
from typing import Optional, Dict, Any
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.accounts.models import User
from apps.core.services import log_audit, send_mail_after_commit
from apps.core.models import ClubSettings
from apps.accounts.permissions import is_club_admin
from .models import Membership, MembershipApplication, MembershipType


def get_next_member_number() -> str:
    """Generate the next sequential member number, e.g. TCM-0001."""
    numbers = Membership.objects.filter(member_number__startswith="TCM-").values_list(
        "member_number", flat=True
    )
    next_id = (
        max((int(number[4:]) for number in numbers if number[4:].isdigit()), default=0)
        + 1
    )
    return f"TCM-{next_id:04d}"


def lock_member_numbers():
    """Serialize number allocation across approvals and CSV imports."""
    singleton = ClubSettings.get_settings()
    ClubSettings.objects.select_for_update().get(pk=singleton.pk)


@transaction.atomic
def approve_application(
    *,
    application: MembershipApplication,
    reviewer: User,
    start_date: Optional[date] = None,
) -> Membership:
    """Approve a pending membership application and activate member status."""
    if not is_club_admin(reviewer):
        raise PermissionDenied(_("Nur Administratoren können Anträge genehmigen."))
    lock_member_numbers()
    application = (
        MembershipApplication.objects.select_for_update()
        .select_related("requested_type")
        .get(pk=application.pk)
    )
    if application.status != MembershipApplication.Status.PENDING:
        raise ValueError(_("Nur ausstehende Anträge können genehmigt werden."))

    user = User.objects.select_for_update().get(pk=application.user_id)
    if not user.is_active or not application.requested_type.is_active:
        raise ValueError(_("Benutzer oder Mitgliedschaftsart ist inaktiv."))
    if Membership.objects.filter(user=user, status=Membership.Status.ACTIVE).exists():
        raise ValueError(
            _("Für diesen Benutzer besteht bereits eine aktive Mitgliedschaft.")
        )
    effective_start = start_date or timezone.localdate()
    member_number = get_next_member_number()

    # Create membership
    membership = Membership.objects.create(
        user=application.user,
        type=application.requested_type,
        member_number=member_number,
        start_date=effective_start,
        status=Membership.Status.ACTIVE,
    )

    # Update application
    application.status = MembershipApplication.Status.APPROVED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    # Update user account type
    user.account_type = User.AccountType.MEMBER
    user.save(update_fields=["account_type"])

    # Log audit
    log_audit(
        user=reviewer,
        action="APPROVE_MEMBERSHIP_APPLICATION",
        entity_type="MembershipApplication",
        entity_id=str(application.pk),
        changes={"member_number": member_number, "user_id": user.pk},
    )

    # Send confirmation email
    subject = "Herzlich willkommen! Dein Mitgliedsantrag wurde genehmigt"
    message = (
        f"Hallo {user.first_name},\n\n"
        f"wir freuen uns sehr, dich als Mitglied im TC Musterdorf begrüßen zu dürfen!\n"
        f"Deine Mitgliedsnummer lautet: {member_number}\n"
        f"Mitgliedschaftsart: {membership.type.name}\n"
        f"Gültig ab: {effective_start:%d.%m.%Y}\n\n"
        f"Du hast ab sofort vollen Zugriff auf die Platzbuchung und den internen Mitgliederbereich.\n\n"
        f"Sportliche Grüße,\n"
        f"Der Vorstand des TC Musterdorf"
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

    return membership


@transaction.atomic
def reject_application(
    *,
    application: MembershipApplication,
    reviewer: User,
    reason: str,
) -> MembershipApplication:
    """Reject a pending membership application with mandatory explanation."""
    if not is_club_admin(reviewer):
        raise PermissionDenied(_("Nur Administratoren können Anträge ablehnen."))
    application = MembershipApplication.objects.select_for_update().get(
        pk=application.pk
    )
    if not reason or not reason.strip():
        raise ValueError(_("Eine Begründung für die Ablehnung ist erforderlich."))

    if application.status != MembershipApplication.Status.PENDING:
        raise ValueError(_("Nur ausstehende Anträge können abgelehnt werden."))

    application.status = MembershipApplication.Status.REJECTED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.rejection_reason = reason.strip()
    application.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"]
    )

    # Log audit
    log_audit(
        user=reviewer,
        action="REJECT_MEMBERSHIP_APPLICATION",
        entity_type="MembershipApplication",
        entity_id=str(application.pk),
        changes={
            "reason": application.rejection_reason,
            "user_id": application.user.pk,
        },
    )

    # Send notification email
    user = application.user
    subject = "Information zu deinem Mitgliedsantrag beim TC Musterdorf"
    message = (
        f"Hallo {user.first_name},\n\n"
        f"dein Mitgliedsantrag beim TC Musterdorf konnte leider nicht genehmigt werden.\n\n"
        f"Begründung:\n{application.rejection_reason}\n\n"
        f"Dein Gast-Konto bleibt weiterhin bestehen, sodass du Plätze als Gast buchen kannst.\n"
        f"Bei Fragen wende dich bitte an den Vorstand.\n\n"
        f"Sportliche Grüße,\n"
        f"TC Musterdorf"
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

    return application


def import_members_from_csv(
    csv_content: str, reviewer: Optional[User] = None
) -> Dict[str, Any]:
    """
    Import members from CSV text.
    Expected header: email, first_name, last_name, phone, membership_type
    Returns {'created': count, 'errors': [{'line': int, 'error': str}]}
    """
    results = {"created": 0, "errors": []}
    if reviewer is not None and not is_club_admin(reviewer):
        raise PermissionDenied(_("Nur Administratoren können Mitglieder importieren."))
    f = io.StringIO(csv_content.lstrip("\ufeff").strip())
    reader = csv.DictReader(f)

    if not reader.fieldnames:
        results["errors"].append(
            {"line": 1, "error": _("CSV-Datei ist leer oder hat ungültige Kopfzeilen.")}
        )
        return results

    required_fields = {"email", "first_name", "last_name", "membership_type"}
    missing = required_fields - set(k.strip().lower() for k in reader.fieldnames)
    if missing:
        results["errors"].append(
            {
                "line": 1,
                "error": f"Fehlende Pflichtspalten in CSV: {', '.join(missing)}",
            }
        )
        return results

    for line_num, row in enumerate(reader, start=2):
        if None in row:
            results["errors"].append(
                {"line": line_num, "error": "Zeile enthält zu viele Spalten."}
            )
            continue
        cleaned_row = {
            k.strip().lower(): (v.strip() if v else "") for k, v in row.items()
        }
        email = cleaned_row.get("email")
        first_name = cleaned_row.get("first_name")
        last_name = cleaned_row.get("last_name")
        phone = cleaned_row.get("phone", "")
        type_name = cleaned_row.get("membership_type")

        if not email or not first_name or not last_name or not type_name:
            results["errors"].append(
                {
                    "line": line_num,
                    "error": "Zeile enthält leere Pflichtfelder (email, first_name, last_name, membership_type).",
                }
            )
            continue

        try:
            validate_email(email)
            mem_type = MembershipType.objects.filter(
                name__iexact=type_name, is_active=True
            ).first()
            if not mem_type:
                results["errors"].append(
                    {
                        "line": line_num,
                        "error": f"Unbekannte Mitgliedschaftsart '{type_name}'.",
                    }
                )
                continue

            with transaction.atomic():
                lock_member_numbers()
                user, _created = User.objects.get_or_create(
                    email__iexact=email,
                    defaults={
                        "email": email.lower(),
                        "first_name": first_name,
                        "last_name": last_name,
                        "phone": phone,
                        "account_type": User.AccountType.MEMBER,
                        "email_verified": True,
                    },
                )
                user = User.objects.select_for_update().get(pk=user.pk)
                if _created:
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                if not _created:
                    user.account_type = User.AccountType.MEMBER
                    user.first_name = first_name
                    user.last_name = last_name
                    if phone:
                        user.phone = phone
                    user.email_verified = True
                    user.save()

                # If no active membership exists, create one
                if not Membership.objects.filter(
                    user=user, status=Membership.Status.ACTIVE
                ).exists():
                    Membership.objects.create(
                        user=user,
                        type=mem_type,
                        member_number=get_next_member_number(),
                        start_date=timezone.localdate(),
                        status=Membership.Status.ACTIVE,
                    )
                results["created"] += 1
        except Exception as e:
            results["errors"].append(
                {
                    "line": line_num,
                    "error": str(e),
                }
            )

    if reviewer:
        log_audit(
            user=reviewer,
            action="CSV_IMPORT_MEMBERS",
            entity_type="Membership",
            entity_id="bulk",
            changes={
                "created": results["created"],
                "error_count": len(results["errors"]),
            },
        )

    return results


def end_expired_memberships() -> int:
    """Daily job to terminate expired memberships and demote account_type to GUEST if needed."""
    today = timezone.localdate()
    expired_users = (
        Membership.objects.filter(status=Membership.Status.ACTIVE, end_date__lt=today)
        .values_list("user_id", flat=True)
        .distinct()
    )
    count = 0
    for user_id in list(expired_users):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            expired = Membership.objects.select_for_update().filter(
                user=user, status=Membership.Status.ACTIVE, end_date__lt=today
            )
            for mem in expired:
                mem.status = Membership.Status.ENDED
                mem.save(update_fields=["status"])
                count += 1
                log_audit(
                    action="MEMBERSHIP_EXPIRED",
                    entity_type="Membership",
                    entity_id=str(mem.pk),
                    changes={"user_id": user.pk, "end_date": str(mem.end_date)},
                )
            if not Membership.objects.filter(
                user=user, status=Membership.Status.ACTIVE
            ).exists():
                user.account_type = User.AccountType.GUEST
                user.save(update_fields=["account_type"])

    return count
