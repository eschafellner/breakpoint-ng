from celery import shared_task
from django.utils import timezone

from .models import OutgoingEmail
from .services import deliver_outgoing_email


@shared_task
def deliver_email(email_id):
    return deliver_outgoing_email(email_id)


@shared_task
def deliver_pending_emails():
    ids = list(
        OutgoingEmail.objects.filter(
            status=OutgoingEmail.Status.PENDING,
            next_attempt_at__lte=timezone.now(),
        )
        .order_by("next_attempt_at", "pk")
        .values_list("pk", flat=True)[:100]
    )
    return sum(deliver_outgoing_email(pk) for pk in ids)
