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
    # Catch up unsent reminders after SMTP/worker outages until play starts.
    window_end = now + timedelta(hours=25)

    upcoming_bookings = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start__gt=now,
        start__lt=window_end,
        reminder_sent_at__isnull=True,
    ).select_related("booked_by", "court")

    count = 0
    for b in upcoming_bookings:
        local_start, local_end = timezone.localtime(b.start), timezone.localtime(b.end)
        subject = f"Erinnerung: Deine Tennis-Buchung am {local_start:%d.%m.} um {local_start:%H:%M} Uhr"
        msg = (
            f"Hallo {b.booked_by.first_name},\n\n"
            f"wir erinnern dich an deine Platzbuchung:\n"
            f"Platz: {b.court.name}\n"
            f"Zeit: {local_start:%d.%m.%Y} von {local_start:%H:%M} bis {local_end:%H:%M} Uhr\n\n"
            f"Wir wünschen dir ein tolles Match!\n\n"
            f"TC Musterdorf"
        )
        with transaction.atomic():
            current = Booking.objects.select_for_update().get(pk=b.pk)
            if current.status != Booking.Status.CONFIRMED or current.reminder_sent_at or current.start <= timezone.now():
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
