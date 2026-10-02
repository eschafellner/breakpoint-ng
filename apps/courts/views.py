from datetime import datetime, date, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.accounts.permissions import is_court_manager
from apps.billing.models import BookingExtra
from .models import Court, Booking, Blocking
from .services import create_booking, cancel_booking, create_blocking
from .selectors import get_calendar_matrix, get_active_courts

def calendar_view(request):
    """Interaktiver Buchungskalender mit Tagesansicht (P-4, P-11)."""
    date_str = request.GET.get("date")
    if date_str:
        try:
            current_day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            current_day = timezone.now().date()
    else:
        current_day = timezone.now().date()

    calendar_data = get_calendar_matrix(current_day, user=request.user)
    extras = BookingExtra.objects.filter(is_active=True)

    # Days for the date picker strip (today + next 7 days)
    today = timezone.now().date()
    days_strip = [
        {
            "date": today + timedelta(days=i),
            "date_str": (today + timedelta(days=i)).isoformat(),
            "weekday_short": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][(today + timedelta(days=i)).weekday()],
            "is_current": (today + timedelta(days=i) == current_day),
        }
        for i in range(8)
    ]

    return render(
        request,
        "courts/calendar.html",
        {
            "title": "Platzbuchung",
            "calendar_data": calendar_data,
            "current_day": current_day,
            "days_strip": days_strip,
            "extras": extras,
        },
    )

@login_required
def book_slot_view(request):
    """Slot buchen per POST."""
    if request.method == "POST":
        court_id = request.POST.get("court_id")
        start_str = request.POST.get("start")
        end_str = request.POST.get("end")
        guest_names_raw = request.POST.get("guest_names", "")
        extra_ids_raw = request.POST.getlist("extras")

        court = get_object_or_404(Court, pk=court_id)

        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt)

            guest_names = [g.strip() for g in guest_names_raw.split(",") if g.strip()]
            extra_ids = [int(e) for e in extra_ids_raw if e.isdigit()]

            booking = create_booking(
                court=court,
                booked_by=request.user,
                start=start_dt,
                end=end_dt,
                guest_names=guest_names,
                selected_extra_ids=extra_ids,
            )
            messages.success(
                request,
                _("Buchung erfolgreich! Platz %(court)s am %(date)s reserviert (Kosten: %(cost)s €).")
                % {
                    "court": court.name,
                    "date": f"{start_dt:%d.%m. %H:%M}",
                    "cost": f"{booking.total_price:.2f}",
                },
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        except Exception as e:
            messages.error(request, str(e))

    return redirect(f"/courts/calendar/?date={request.POST.get('redirect_date', '')}")

@login_required
def cancel_booking_view(request, booking_id):
    """Buchung stornieren."""
    booking = get_object_or_404(Booking, pk=booking_id)
    if request.method == "POST":
        try:
            cancel_booking(booking=booking, user=request.user)
            messages.success(request, _("Deine Buchung wurde erfolgreich storniert."))
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, str(e))

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "courts:calendar"
    return redirect(next_url)

@login_required
def blockings_view(request):
    """Platzwart-Verwaltung für Sperrzeiten (P-3, AP-06)."""
    if not is_court_manager(request.user):
        raise PermissionDenied(_("Zugriff nur für Platzwarte und Administratoren."))

    courts = get_active_courts()
    blockings = Blocking.objects.select_related("court", "created_by").order_by("-start")[:50]

    if request.method == "POST":
        court_id = request.POST.get("court_id")
        start_str = request.POST.get("start")
        end_str = request.POST.get("end")
        reason = request.POST.get("reason", Blocking.Reason.TRAINING)
        note = request.POST.get("note", "")

        court = get_object_or_404(Court, pk=court_id)
        try:
            start_dt = timezone.make_aware(datetime.fromisoformat(start_str))
            end_dt = timezone.make_aware(datetime.fromisoformat(end_str))
            blocking, cancelled = create_blocking(
                court=court,
                start=start_dt,
                end=end_dt,
                reason=reason,
                note=note,
                created_by=request.user,
                cancel_overlapping=True,
            )
            msg = _("Sperre erfolgreich eingetragen.")
            if cancelled:
                msg += _(" Es wurden %(cnt)d Buchungen automatisch storniert und die Nutzer benachrichtigt.") % {"cnt": len(cancelled)}
            messages.success(request, msg)
            return redirect("courts:blockings")
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "courts/blockings.html",
        {
            "title": "Platzsperren verwalten",
            "courts": courts,
            "blockings": blockings,
            "reasons": Blocking.Reason.choices,
        },
    )
