from datetime import timedelta
import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db import transaction
from .models import Booking


@shared_task
def send_booking_reminders():
    """Send reminder emails to players 24 hours prior to booking start."""
    now = timezone.now()
    target_start = now + timedelta(hours=24)
    window_end = target_start + timedelta(minutes=60)

    upcoming_bookings = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start__gte=target_start,
        start__lt=window_end,
        reminder_sent_at__isnull=True,
    ).select_related("booked_by", "court")

    count = 0
    for b in upcoming_bookings:
        subject = f"Erinnerung: Deine Tennis-Buchung morgen um {b.start:%H:%M} Uhr"
        msg = (
            f"Hallo {b.booked_by.first_name},\n\n"
            f"wir erinnern dich an deine Platzbuchung morgen:\n"
            f"Platz: {b.court.name}\n"
            f"Zeit: {b.start:%d.%m.%Y} von {b.start:%H:%M} bis {b.end:%H:%M} Uhr\n\n"
            f"Wir wünschen dir ein tolles Match!\n\n"
            f"TC Musterdorf"
        )
        with transaction.atomic():
            current = Booking.objects.select_for_update().get(pk=b.pk)
            if current.status != Booking.Status.CONFIRMED or current.reminder_sent_at:
                continue
            try:
                delivered = send_mail(
                    subject=subject,
                    message=msg,
                    from_email=getattr(
                        settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"
                    ),
                    recipient_list=[b.booked_by.email],
                    fail_silently=False,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Buchungserinnerung #%s konnte nicht versendet werden", b.pk
                )
                continue
            if delivered:
                current.reminder_sent_at = timezone.now()
                current.save(update_fields=["reminder_sent_at"])
                count += 1

    return f"Sent {count} reminders."
