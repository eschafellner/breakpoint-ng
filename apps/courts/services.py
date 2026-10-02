from datetime import datetime, timedelta, date, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.accounts.models import User
from apps.core.models import ClubSettings
from apps.core.services import log_audit
from apps.billing.models import Charge, PriceRule, BookingExtra, BookingExtraLine
from apps.billing.services import create_charge, cancel_charge, quantize_amount
from .models import Court, Season, OpeningHours, Blocking, Booking, BookingParticipant

CENT = Decimal("0.01")

def get_slot_interval_times(day: date, open_time: time, close_time: time, slot_minutes: int):
    """Generate all slot (start, end) time ranges for a given day and opening hours."""
    slots = []
    current_dt = timezone.make_aware(datetime.combine(day, open_time))
    close_dt = timezone.make_aware(datetime.combine(day, close_time))
    slot_delta = timedelta(minutes=slot_minutes)

    while current_dt + slot_delta <= close_dt:
        slots.append((current_dt, current_dt + slot_delta))
        current_dt += slot_delta
    return slots

@transaction.atomic
def create_blocking(
    *,
    court: Court,
    start: datetime,
    end: datetime,
    reason: str = Blocking.Reason.TRAINING,
    note: str = "",
    recurrence_rule: str = "",
    created_by: Optional[User] = None,
    cancel_overlapping: bool = True,
) -> Tuple[Blocking, List[Booking]]:
    """
    Create a court blocking.
    If cancel_overlapping is True, existing confirmed bookings overlapping this window
    are cancelled and bookers are notified.
    """
    if start >= end:
        raise ValidationError(_("Der Beginn der Sperre muss vor dem Ende liegen."))

    blocking = Blocking.objects.create(
        court=court,
        start=start,
        end=end,
        reason=reason,
        note=note,
        recurrence_rule=recurrence_rule,
        created_by=created_by,
    )

    cancelled_bookings = []
    if cancel_overlapping:
        overlapping = Booking.objects.filter(
            court=court,
            status=Booking.Status.CONFIRMED,
            start__lt=end,
            end__gt=start,
        ).select_related("booked_by")

        for b in overlapping:
            b.status = Booking.Status.CANCELLED
            b.cancelled_at = timezone.now()
            b.save(update_fields=["status", "cancelled_at"])
            cancelled_bookings.append(b)

            # Cancel associated charges
            for chg in Charge.objects.filter(
                content_type__model="booking",
                object_id=b.pk,
                status=Charge.Status.OPEN,
            ):
                cancel_charge(chg, reason=f"Sperre {blocking.get_reason_display()}")

            # Send cancellation email to booker
            subject = f"Wichtiger Hinweis: Deine Buchung auf {court.name} wurde storniert"
            msg = (
                f"Hallo {b.booked_by.first_name},\n\n"
                f"deine Buchung auf {court.name} am {b.start:%d.%m.%Y} von {b.start:%H:%M} bis {b.end:%H:%M} Uhr "
                f"musste leider aufgrund einer Platzsperre ({blocking.get_reason_display()}) storniert werden.\n\n"
                f"Grund / Bemerkung: {note or 'Keine Angabe'}\n\n"
                f"Eventuell angefallene Gebühren wurden storniert.\n"
                f"Sportliche Grüße,\n"
                f"TC Musterdorf"
            )
            send_mail(
                subject=subject,
                message=msg,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"),
                recipient_list=[b.booked_by.email],
                fail_silently=True,
            )

    log_audit(
        user=created_by,
        action="CREATE_BLOCKING",
        entity_type="Blocking",
        entity_id=str(blocking.pk),
        changes={
            "court_id": court.pk,
            "start": str(start),
            "end": str(end),
            "reason": reason,
            "cancelled_bookings": len(cancelled_bookings),
        },
    )

    return blocking, cancelled_bookings

@transaction.atomic
def create_booking(
    *,
    court: Court,
    booked_by: User,
    start: datetime,
    end: datetime,
    participant_user_ids: Optional[List[int]] = None,
    guest_names: Optional[List[str]] = None,
    selected_extra_ids: Optional[List[int]] = None,
) -> Booking:
    """
    Create a court booking with rules validation, extra calculations,
    concurrency locking, and central billing charge creation.
    """
    now = timezone.now()
    if start < now:
        raise ValidationError(_("Buchungen können nicht in der Vergangenheit liegen."))
    if start >= end:
        raise ValidationError(_("Der Beginn der Buchung muss vor dem Ende liegen."))

    club_settings = ClubSettings.get_settings()
    duration_min = int((end - start).total_seconds() / 60)

    # 1. Rule: Max duration
    if duration_min > club_settings.max_duration_minutes:
        raise ValidationError(
            _("Die maximale Buchungsdauer beträgt %(max)d Minuten.")
            % {"max": club_settings.max_duration_minutes}
        )

    # 2. Rule: Advance booking window
    is_booker_member = (booked_by.account_type == User.AccountType.MEMBER)
    allowed_advance_days = club_settings.advance_days_member if is_booker_member else club_settings.advance_days_guest
    max_advance_dt = now + timedelta(days=allowed_advance_days)
    if start > max_advance_dt:
        raise ValidationError(
            _("Buchungen sind für dich maximal %(days)d Tage im Voraus möglich.")
            % {"days": allowed_advance_days}
        )

    # 3. Rule: Max open future bookings
    if is_booker_member:
        open_count = Booking.objects.filter(
            booked_by=booked_by,
            status=Booking.Status.CONFIRMED,
            end__gt=now,
        ).count()
        if open_count >= club_settings.max_open_bookings:
            raise ValidationError(
                _("Du hast bereits das Maximum von %(max)d aktiven Buchungen erreicht.")
                % {"max": club_settings.max_open_bookings}
            )

    # 4. Concurrency lock on Court row to prevent race conditions
    locked_court = Court.objects.select_for_update().get(pk=court.pk)
    if not locked_court.is_active:
        raise ValidationError(_("Dieser Platz ist derzeit nicht aktiv."))

    # 5. Overlap collision checks
    overlapping_booking = Booking.objects.filter(
        court=locked_court,
        status=Booking.Status.CONFIRMED,
        start__lt=end,
        end__gt=start,
    ).exists()
    if overlapping_booking:
        raise ValidationError(_("Dieser Platz ist im gewünschten Zeitraum bereits gebucht."))

    overlapping_blocking = Blocking.objects.filter(
        court=locked_court,
        start__lt=end,
        end__gt=start,
    ).exists()
    if overlapping_blocking:
        raise ValidationError(_("Dieser Platz ist im gewünschten Zeitraum gesperrt."))

    # 6. Price Calculation
    duration_hours = Decimal(duration_min) / Decimal(60)
    total_price = Decimal("0.00")
    charge_kind = Charge.Kind.OTHER

    # Determine court base price
    if not is_booker_member:
        # Guest pays court fee
        charge_kind = Charge.Kind.COURT_FEE
        rule = PriceRule.objects.filter(
            applies_to=PriceRule.AppliesTo.GUEST
        ).filter(models.Q(court=locked_court) | models.Q(court__isnull=True)).first()
        base_rate = rule.price_per_hour if rule else Decimal("15.00")
        total_price += (base_rate * duration_hours).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        # Member plays free on court base
        total_price += Decimal("0.00")

    # Guest participants (if member plays with guests)
    guest_players_count = 0
    if guest_names:
        guest_players_count += len([g for g in guest_names if g.strip()])

    if is_booker_member and guest_players_count > 0:
        charge_kind = Charge.Kind.GUEST_FEE
        rule = PriceRule.objects.filter(
            applies_to__in=[PriceRule.AppliesTo.GUEST_OF_MEMBER, PriceRule.AppliesTo.GUEST]
        ).filter(models.Q(court=locked_court) | models.Q(court__isnull=True)).first()
        guest_fee_per_person = rule.price_per_person if rule and rule.price_per_person > 0 else Decimal("5.00")
        total_price += (guest_fee_per_person * Decimal(guest_players_count)).quantize(CENT, rounding=ROUND_HALF_UP)

    # 7. Extras calculation (automatic + selected optional)
    extra_lines_to_create = []
    active_extras = BookingExtra.objects.filter(is_active=True).filter(
        models.Q(courts=locked_court) | models.Q(courts__isnull=True)
    ).distinct()

    selected_ids = set(selected_extra_ids or [])
    for extra in active_extras:
        should_add = (extra.mode == BookingExtra.Mode.AUTOMATIC) or (extra.id in selected_ids)
        if should_add:
            unit_price = extra.price_member if is_booker_member else extra.price_guest
            qty = duration_hours if extra.unit == BookingExtra.Unit.PER_HOUR else Decimal("1.00")
            line_total = (unit_price * qty).quantize(CENT, rounding=ROUND_HALF_UP)
            total_price += line_total
            extra_lines_to_create.append({
                "extra": extra,
                "quantity": qty,
                "unit_price": unit_price,
                "total": line_total,
            })

    total_price = quantize_amount(total_price)

    # 8. Create Booking
    booking = Booking.objects.create(
        court=locked_court,
        booked_by=booked_by,
        start=start,
        end=end,
        status=Booking.Status.CONFIRMED,
        total_price=total_price,
    )

    # 9. Create Extra Lines (freeze prices)
    for line in extra_lines_to_create:
        BookingExtraLine.objects.create(
            booking=booking,
            extra=line["extra"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            total=line["total"],
        )

    # 10. Create Participants
    BookingParticipant.objects.create(
        booking=booking,
        user=booked_by,
        is_guest=(not is_booker_member),
    )
    if participant_user_ids:
        for u_id in participant_user_ids:
            try:
                p_user = User.objects.get(pk=u_id)
                BookingParticipant.objects.create(
                    booking=booking,
                    user=p_user,
                    is_guest=(p_user.account_type == User.AccountType.GUEST),
                )
            except User.DoesNotExist:
                pass

    if guest_names:
        for g_name in guest_names:
            if g_name.strip():
                BookingParticipant.objects.create(
                    booking=booking,
                    guest_name=g_name.strip(),
                    is_guest=True,
                )

    # 11. Central Billing Charge Creation (if fee applicable)
    if total_price > Decimal("0.00"):
        desc = f"Platzbuchung {locked_court.name} am {start:%d.%m.%Y} ({start:%H:%M}–{end:%H:%M})"
        create_charge(
            user=booked_by,
            kind=charge_kind,
            amount=total_price,
            due_date=start.date(),
            description=desc,
            source=booking,
        )

    # 12. Send Confirmation Email
    bank_info = (
        f"Bankverbindung:\nIBAN: {club_settings.iban}\nBIC: {club_settings.bic}\nBank: {club_settings.bank_name}\n"
        if total_price > 0 else ""
    )
    subject = f"Buchungsbestätigung: {locked_court.name} am {start:%d.%m.%Y}"
    msg = (
        f"Hallo {booked_by.first_name},\n\n"
        f"deine Platzbuchung war erfolgreich!\n"
        f"Platz: {locked_court.name}\n"
        f"Zeit: {start:%d.%m.%Y} von {start:%H:%M} bis {end:%H:%M} Uhr\n"
        f"Gesamtbetrag: {total_price:.2f} €\n\n"
        f"{bank_info}\n"
        f"Stornierungen sind bis {club_settings.free_cancel_hours} Stunden vor Spielbeginn kostenlos möglich.\n\n"
        f"Viel Spaß beim Spielen,\n"
        f"TC Musterdorf"
    )
    send_mail(
        subject=subject,
        message=msg,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"),
        recipient_list=[booked_by.email],
        fail_silently=True,
    )

    log_audit(
        user=booked_by,
        action="CREATE_BOOKING",
        entity_type="Booking",
        entity_id=str(booking.pk),
        changes={
            "court_id": locked_court.pk,
            "start": str(start),
            "end": str(end),
            "total_price": str(total_price),
        },
    )

    return booking

@transaction.atomic
def cancel_booking(*, booking: Booking, user: User) -> bool:
    """
    Cancel an existing booking.
    If within free cancellation window, associated open charge is cancelled.
    """
    if booking.status != Booking.Status.CONFIRMED:
        return False

    is_booker = (booking.booked_by == user)
    is_manager = user.is_staff or user.groups.filter(name__in=["Platzwart", "Administrator"]).exists()
    if not (is_booker or is_manager):
        raise ValidationError(_("Keine Berechtigung zur Stornierung dieser Buchung."))

    club_settings = ClubSettings.get_settings()
    now = timezone.now()
    hours_until_start = (booking.start - now).total_seconds() / 3600.0

    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = now
    booking.save(update_fields=["status", "cancelled_at"])

    # If within free cancel hours, cancel any open charge
    if hours_until_start >= club_settings.free_cancel_hours or is_manager:
        for chg in Charge.objects.filter(
            content_type__model="booking",
            object_id=booking.pk,
            status=Charge.Status.OPEN,
        ):
            cancel_charge(chg, reason=_("Kostenlose Stornierung durch Nutzer."))

    log_audit(
        user=user,
        action="CANCEL_BOOKING",
        entity_type="Booking",
        entity_id=str(booking.pk),
        changes={"hours_until_start": hours_until_start},
    )

    return True
