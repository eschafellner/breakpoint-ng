from typing import Any, Optional
import logging
from ipaddress import ip_address as parse_ip
from django.core.mail import send_mail
from django.db import transaction
from .models import AuditLog


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
    """Do not announce changes rolled back later; log delivery failures."""

    def deliver():
        try:
            send_mail(**{**kwargs, "fail_silently": False})
        except Exception:
            logging.getLogger(__name__).exception(
                "E-Mail konnte nach dem Commit nicht versendet werden"
            )

    transaction.on_commit(deliver)
