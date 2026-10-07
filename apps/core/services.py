from typing import Any, Optional
from datetime import timedelta
import logging
from ipaddress import ip_address as parse_ip
from django.core.mail import send_mail
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from .models import AuditLog, OutgoingEmail


def log_audit(
    *,
    user: Optional[Any] = None,
    action: str,
    entity_type: str,
    entity_id: str,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Record an audit log entry for changes or critical actions."""
    if ip_address:
        try:
            ip_address = str(parse_ip(ip_address))
        except ValueError:
            ip_address = None
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        changes=changes or {},
        ip_address=ip_address,
    )


def send_mail_after_commit(**kwargs):
    """Persist delivery in the same transaction, then dispatch after commit."""
    email = OutgoingEmail.objects.create(
        subject=kwargs["subject"],
        message=kwargs["message"],
        from_email=kwargs["from_email"],
        recipients=list(kwargs["recipient_list"]),
    )

    def dispatch():
        if not getattr(settings, "MAIL_DELIVERY_ASYNC", False):
            deliver_outgoing_email(email.pk)
            return
        try:
            from .tasks import deliver_email

            deliver_email.delay(email.pk)
        except Exception:
            logging.getLogger(__name__).exception(
                "E-Mail #%s konnte nicht an den Worker übergeben werden; der Versandauftrag bleibt gespeichert",
                email.pk,
            )

    transaction.on_commit(dispatch)
    return email


@transaction.atomic
def deliver_outgoing_email(email_id):
    """Serialize delivery attempts; SMTP failures stay eligible for retry."""
    email = OutgoingEmail.objects.select_for_update().get(pk=email_id)
    now = timezone.now()
    if email.status != OutgoingEmail.Status.PENDING or email.next_attempt_at > now:
        return False
    email.attempts += 1
    try:
        delivered = send_mail(
            subject=email.subject,
            message=email.message,
            from_email=email.from_email,
            recipient_list=email.recipients,
            fail_silently=False,
        )
        if not delivered:
            raise RuntimeError("Der E-Mail-Dienst hat den Versand nicht bestätigt.")
    except Exception as exc:
        email.last_error = str(exc)[:1000]
        email.next_attempt_at = now + timedelta(minutes=min(2 ** (email.attempts - 1), 60))
        if email.attempts >= 8:
            email.status = OutgoingEmail.Status.FAILED
        logging.getLogger(__name__).exception("E-Mail #%s konnte nicht versendet werden", email.pk)
    else:
        email.status = OutgoingEmail.Status.SENT
        email.sent_at = now
        email.last_error = ""
    email.save(update_fields=["status", "attempts", "next_attempt_at", "sent_at", "last_error", "updated_at"])
    return email.status == OutgoingEmail.Status.SENT
