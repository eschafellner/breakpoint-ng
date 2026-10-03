from datetime import datetime, timedelta, date, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.accounts.models import User
from apps.accounts.permissions import is_member, is_court_manager
from apps.core.models import ClubSettings
from apps.core.services import log_audit, send_mail_after_commit
from apps.billing.models import Charge, PriceRule, BookingExtra, BookingExtraLine
from apps.billing.services import create_charge, cancel_charge, quantize_amount
from apps.billing.selectors import get_applicable_price_rule
from .models import Court, Blocking, Booking, BookingParticipant

CENT = Decimal("0.01")


def get_slot_interval_times(
    day: date, open_time: time, close_time: time, slot_minutes: int
):
    """Generate all slot (start, end) time ranges for a given day and opening hours."""
    if slot_minutes <= 0 or open_time >= close_time:
        raise ValidationError(_("Ungültige Öffnungszeiten oder Slot-Dauer."))
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
    if recurrence_rule:
        raise ValidationError(
            _(
                "Wiederkehrende Sperren werden noch nicht unterstützt. Bitte lege einzelne Termine an."
            )
        )
    if (
        timezone.is_naive(start)
        or timezone.is_naive(end)
        or reason not in Blocking.Reason.values
    ):
        raise ValidationError(_("Ungültige Sperrzeit oder Sperrgrund."))
    if created_by is not None and not is_court_manager(created_by):
        raise ValidationError(_("Keine Berechtigung für Platzsperren."))
    court = Court.objects.select_for_update().get(pk=court.pk)
    if (
        not cancel_overlapping
        and Booking.objects.filter(
            court=court, status=Booking.Status.CONFIRMED, start__lt=end, end__gt=start
        ).exists()
    ):
        raise ValidationError(_("Die Sperre überschneidet sich mit einer Buchung."))

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
            subject = (
                f"Wichtiger Hinweis: Deine Buchung auf {court.name} wurde storniert"
            )
            msg = (
                f"Hallo {b.booked_by.first_name},\n\n"
                f"deine Buchung auf {court.name} am {b.start:%d.%m.%Y} von {b.start:%H:%M} bis {b.end:%H:%M} Uhr "
                f"musste leider aufgrund einer Platzsperre ({blocking.get_reason_display()}) storniert werden.\n\n"
                f"Grund / Bemerkung: {note or 'Keine Angabe'}\n\n"
                f"Offene, unbezahlte Gebühren wurden storniert. Bereits verbuchte Zahlungen prüft der Kassier.\n"
                f"Sportliche Grüße,\n"
                f"TC Musterdorf"
            )
            send_mail_after_commit(
                subject=subject,
                message=msg,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"
                ),
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


def calculate_booking_price(
    *, court, booked_by, start, end, guest_players_count=0, selected_extra_ids=None
):
    """Shared price calculation for the preview and the committed booking."""
    from .selectors import get_opening_hours_for_court

    if timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
        raise ValidationError(_("Ungültige Buchungszeiten."))
    opening = get_opening_hours_for_court(court, timezone.localtime(start).date())
    if not opening or opening.slot_minutes <= 0:
        raise ValidationError(_("Der Platz ist geschlossen."))
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    opens = timezone.make_aware(datetime.combine(local_start.date(), opening.open_time))
    closes = timezone.make_aware(
        datetime.combine(local_start.date(), opening.close_time)
    )
    if (
        not court.is_active
        or local_start.date() != local_end.date()
        or start < opens
        or end > closes
        or (start - opens).total_seconds() % (opening.slot_minutes * 60)
        or (end - opens).total_seconds() % (opening.slot_minutes * 60)
    ):
        raise ValidationError(
            _("Bitte buche vollständige Slots innerhalb der Öffnungszeiten.")
        )
    is_booker_member = is_member(booked_by)
    duration_hours = Decimal(str((end - start).total_seconds())) / Decimal(3600)
    total_price = Decimal("0.00")
    charge_kind = Charge.Kind.OTHER

    # Determine court base price
    if not is_booker_member:
        charge_kind = Charge.Kind.COURT_FEE
    price_type = (
        PriceRule.AppliesTo.MEMBER if is_booker_member else PriceRule.AppliesTo.GUEST
    )
    # Include tariff boundaries even when they occur inside a calendar slot.
    boundaries = [end]
    for rule in PriceRule.objects.filter(applies_to=price_type).filter(
        models.Q(court=court) | models.Q(court__isnull=True)
    ):
        for boundary_time in (rule.time_from, rule.time_to):
            if boundary_time:
                boundary = timezone.make_aware(
                    datetime.combine(local_start.date(), boundary_time)
                )
                if start < boundary < end:
                    boundaries.append(boundary)
    current = start
    while current < end:
        rule = get_applicable_price_rule(
            court=court, applies_to=price_type, booking_time=current
        )
        if not rule and not is_booker_member:
            raise ValidationError(
                _("Für diesen Zeitraum ist kein Gasttarif konfiguriert.")
            )
        segment_end = min(
            [current + timedelta(minutes=opening.slot_minutes)]
            + [boundary for boundary in boundaries if boundary > current]
        )
        hours = Decimal(str((segment_end - current).total_seconds())) / Decimal(3600)
        if rule:
            if rule.price_per_hour < 0:
                raise ValidationError(_("Der konfigurierte Tarif ist ungültig."))
            total_price += rule.price_per_hour * hours
        current = segment_end

    # Guest participants (if member plays with guests)

    if is_booker_member and guest_players_count > 0:
        charge_kind = Charge.Kind.GUEST_FEE
        rule = get_applicable_price_rule(
            court=court,
            applies_to=PriceRule.AppliesTo.GUEST_OF_MEMBER,
            booking_time=start,
        )
        if not rule:
            raise ValidationError(_("Für Gastmitspieler ist kein Tarif konfiguriert."))
        guest_fee_per_person = rule.price_per_person
        if guest_fee_per_person < 0:
            raise ValidationError(_("Der konfigurierte Gasttarif ist ungültig."))
        total_price += (guest_fee_per_person * Decimal(guest_players_count)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )

    # 7. Extras calculation (automatic + selected optional)
    extra_lines_to_create = []
    active_extras = (
        BookingExtra.objects.filter(is_active=True)
        .filter(models.Q(courts=court) | models.Q(courts__isnull=True))
        .distinct()
    )

    selected_ids = set(selected_extra_ids or [])
    if not selected_ids <= set(active_extras.values_list("pk", flat=True)):
        raise ValidationError(
            _("Unbekanntes oder für diesen Platz nicht verfügbares Extra.")
        )
    for extra in active_extras:
        should_add = (extra.mode == BookingExtra.Mode.AUTOMATIC) or (
            extra.id in selected_ids
        )
        if should_add:
            unit_price = extra.price_member if is_booker_member else extra.price_guest
            if unit_price < 0:
                raise ValidationError(_("Der konfigurierte Zusatzpreis ist ungültig."))
            qty = (
                duration_hours
                if extra.unit == BookingExtra.Unit.PER_HOUR
                else Decimal("1.00")
            )
            line_total = (unit_price * qty).quantize(CENT, rounding=ROUND_HALF_UP)
            total_price += line_total
            extra_lines_to_create.append(
                {
                    "extra": extra,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "total": line_total,
                }
            )

    total_price = quantize_amount(total_price)

    return total_price, charge_kind, extra_lines_to_create


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
    expected_total: Optional[Decimal] = None,
) -> Booking:
    """
    Create a court booking with rules validation, extra calculations,
    concurrency locking, and central billing charge creation.
    """
    now = timezone.now()
    if timezone.is_naive(start) or timezone.is_naive(end):
        raise ValidationError(_("Buchungszeiten müssen eine Zeitzone enthalten."))
    booked_by = User.objects.select_for_update().get(pk=booked_by.pk)
    if not booked_by.is_active or not booked_by.email_verified:
        raise ValidationError(
            _("Nur aktive Benutzer mit bestätigter E-Mail können buchen.")
        )
    if start < now:
        raise ValidationError(_("Buchungen können nicht in der Vergangenheit liegen."))
    if start >= end:
        raise ValidationError(_("Der Beginn der Buchung muss vor dem Ende liegen."))

    club_settings = ClubSettings.get_settings()
    duration_min = (end - start).total_seconds() / 60

    # 1. Rule: Max duration
    if duration_min > club_settings.max_duration_minutes:
        raise ValidationError(
            _("Die maximale Buchungsdauer beträgt %(max)d Minuten.")
            % {"max": club_settings.max_duration_minutes}
        )

    # 2. Rule: Advance booking window
    is_booker_member = is_member(booked_by)
    allowed_advance_days = (
        club_settings.advance_days_member
        if is_booker_member
        else club_settings.advance_days_guest
    )
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
    from .selectors import get_opening_hours_for_court

    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    opening = get_opening_hours_for_court(locked_court, local_start.date())
    if not opening or local_start.date() != local_end.date():
        raise ValidationError(_("Der Platz ist an diesem Tag geschlossen."))
    opening_start = timezone.make_aware(
        datetime.combine(local_start.date(), opening.open_time)
    )
    opening_end = timezone.make_aware(
        datetime.combine(local_start.date(), opening.close_time)
    )
    slot_seconds = opening.slot_minutes * 60
    if (
        slot_seconds <= 0
        or start < opening_start
        or end > opening_end
        or (start - opening_start).total_seconds() % slot_seconds
        or (end - opening_start).total_seconds() % slot_seconds
    ):
        raise ValidationError(
            _("Bitte buche vollständige Slots innerhalb der Öffnungszeiten.")
        )
    participant_ids = participant_user_ids or []
    if (
        len(set(participant_ids)) != len(participant_ids)
        or booked_by.pk in participant_ids
    ):
        raise ValidationError(_("Mitspieler dürfen nicht doppelt angegeben werden."))
    participants = list(
        User.objects.filter(pk__in=participant_ids, is_active=True, email_verified=True)
    )
    if len(participants) != len(participant_ids):
        raise ValidationError(_("Unbekannter oder inaktiver Mitspieler."))
    guest_names = [name.strip() for name in (guest_names or []) if name.strip()]
    if any(len(name) > 100 for name in guest_names) or len(set(guest_names)) != len(
        guest_names
    ):
        raise ValidationError(_("Gastnamen sind ungültig oder doppelt angegeben."))

    # 5. Overlap collision checks
    overlapping_booking = Booking.objects.filter(
        court=locked_court,
        status=Booking.Status.CONFIRMED,
        start__lt=end,
        end__gt=start,
    ).exists()
    if overlapping_booking:
        raise ValidationError(
            _("Dieser Platz ist im gewünschten Zeitraum bereits gebucht.")
        )

    overlapping_blocking = Blocking.objects.filter(
        court=locked_court,
        start__lt=end,
        end__gt=start,
    ).exists()
    if overlapping_blocking:
        raise ValidationError(_("Dieser Platz ist im gewünschten Zeitraum gesperrt."))

    total_price, charge_kind, extra_lines_to_create = calculate_booking_price(
        court=locked_court,
        booked_by=booked_by,
        start=start,
        end=end,
        guest_players_count=len(guest_names)
        + sum(not is_member(user) for user in participants),
        selected_extra_ids=selected_extra_ids,
    )
    if expected_total is not None and quantize_amount(expected_total) != total_price:
        raise ValidationError(
            _("Der Preis hat sich geändert. Bitte prüfe die aktuelle Preisvorschau.")
        )

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
    for p_user in participants:
        BookingParticipant.objects.create(
            booking=booking, user=p_user, is_guest=not is_member(p_user)
        )

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
            due_date=local_start.date(),
            description=desc,
            source=booking,
        )

    # 12. Send Confirmation Email
    bank_info = (
        f"Bankverbindung:\nIBAN: {club_settings.iban}\nBIC: {club_settings.bic}\nBank: {club_settings.bank_name}\n"
        if total_price > 0
        else ""
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
    send_mail_after_commit(
        subject=subject,
        message=msg,
        from_email=getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@tc-musterdorf.local"
        ),
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
    Court.objects.select_for_update().get(pk=booking.court_id)
    current = Booking.objects.select_for_update().get(pk=booking.pk)
    is_booker = current.booked_by == user and user.is_active
    is_manager = is_court_manager(user)
    if not (is_booker or is_manager):
        raise ValidationError(_("Keine Berechtigung zur Stornierung dieser Buchung."))
    if current.status != Booking.Status.CONFIRMED:
        booking.status = current.status
        return False
    booking = current

    club_settings = ClubSettings.get_settings()
    now = timezone.now()
    if booking.start <= now and not is_manager:
        raise ValidationError(
            _("Bereits begonnene Buchungen können nicht mehr storniert werden.")
        )
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
