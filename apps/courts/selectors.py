from datetime import date, datetime, timedelta, time
from typing import List, Dict, Any, Optional
from django.utils import timezone
from .models import Court, OpeningHours, Blocking, Booking

def get_active_courts():
    """Return all active courts sorted by order."""
    return Court.objects.filter(is_active=True).order_by("order", "id")

def get_opening_hours_for_court(court: Court, day: date) -> Optional[OpeningHours]:
    """Find opening hours for court on given weekday."""
    weekday = day.weekday()
    return OpeningHours.objects.filter(court=court, weekday=weekday).first()

def get_court_slots_for_day(court: Court, day: date, user=None) -> List[Dict[str, Any]]:
    """
    Generate slots for a court on a specific day.
    Anonymizes bookings for visitors / guests (P-11: 'Öffentliche Ansicht zeigt keine Namen').
    """
    op = get_opening_hours_for_court(court, day)
    open_time = op.open_time if op else time(8, 0)
    close_time = op.close_time if op else time(21, 0)
    slot_minutes = op.slot_minutes if op else 60

    # Build aware datetimes for start of day slots
    day_start = timezone.make_aware(datetime.combine(day, open_time))
    day_end = timezone.make_aware(datetime.combine(day, close_time))

    # Fetch confirmed bookings and blockings for this court & day
    bookings = Booking.objects.filter(
        court=court,
        status=Booking.Status.CONFIRMED,
        start__lt=day_end,
        end__gt=day_start,
    ).select_related("booked_by").prefetch_related("participants")

    blockings = Blocking.objects.filter(
        court=court,
        start__lt=day_end,
        end__gt=day_start,
    )

    slots = []
    current_dt = day_start
    slot_delta = timedelta(minutes=slot_minutes)

    while current_dt + slot_delta <= day_end:
        slot_end = current_dt + slot_delta
        
        # Check blocking
        blocking_match = None
        for blk in blockings:
            if blk.start < slot_end and blk.end > current_dt:
                blocking_match = blk
                break

        # Check booking
        booking_match = None
        for b in bookings:
            if b.start < slot_end and b.end > current_dt:
                booking_match = b
                break

        slot_state = "free"
        label = "Frei"
        can_book = True

        if blocking_match:
            slot_state = "blocked"
            label = blocking_match.get_reason_display()
            can_book = False
        elif booking_match:
            is_mine = bool(user and user.is_authenticated and (booking_match.booked_by == user))
            if is_mine:
                slot_state = "mine"
                label = "Meine Buchung"
            else:
                slot_state = "taken"
                # P-11: Public view shows no names, just 'Belegt'
                label = "Belegt"
            can_book = False
        elif current_dt < timezone.now():
            slot_state = "past"
            label = "–"
            can_book = False

        slots.append({
            "start": current_dt,
            "end": slot_end,
            "start_time_str": current_dt.strftime("%H:%M"),
            "end_time_str": slot_end.strftime("%H:%M"),
            "state": slot_state,
            "label": label,
            "can_book": can_book,
            "court_id": court.id,
            "booking_id": booking_match.id if booking_match else None,
        })
        current_dt += slot_delta

    return slots

def get_calendar_matrix(day: date, user=None) -> Dict[str, Any]:
    """
    Returns a matrix suitable for rendering the table of courts & time slots.
    Rows = time labels (e.g. 08:00, 09:00...), Columns = courts.
    """
    courts = list(get_active_courts())
    court_slots = {}
    time_keys = []

    for c in courts:
        slots = get_court_slots_for_day(c, day, user=user)
        court_slots[c.id] = {s["start_time_str"]: s for s in slots}
        for s in slots:
            if s["start_time_str"] not in time_keys:
                time_keys.append(s["start_time_str"])

    time_keys.sort()

    matrix_rows = []
    for t in time_keys:
        row = {"time": t, "slots": []}
        for c in courts:
            slot = court_slots.get(c.id, {}).get(t)
            row["slots"].append({"court": c, "slot": slot})
        matrix_rows.append(row)

    return {
        "date": day,
        "courts": courts,
        "matrix_rows": matrix_rows,
    }
