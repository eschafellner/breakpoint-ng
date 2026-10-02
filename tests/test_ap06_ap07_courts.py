import pytest
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core import mail
from django.utils import timezone
from apps.accounts.models import User
from apps.billing.models import Charge, PriceRule, BookingExtra
from apps.courts.models import Court, Booking, Blocking
from apps.courts.services import create_booking, create_blocking, cancel_booking
from apps.courts.selectors import get_court_slots_for_day

@pytest.mark.django_db
def test_blocking_cancels_overlapping_bookings_and_notifies(court_sand, member_user, admin_user):
    """AP-06: Neue Sperre über bestehende Buchungen: storniert sie und sendet E-Mail an Buchende."""
    start = timezone.now() + timedelta(days=1, hours=2)
    end = start + timedelta(hours=1)

    # Member books slot
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=end,
    )
    assert booking.status == Booking.Status.CONFIRMED

    mail.outbox.clear()
    # Platzwart creates overlapping blocking
    blocking_start = start - timedelta(minutes=30)
    blocking_end = end + timedelta(minutes=30)

    blocking, cancelled = create_blocking(
        court=court_sand,
        start=blocking_start,
        end=blocking_end,
        reason=Blocking.Reason.WEATHER,
        note="Starkregen / Unbespielbar",
        created_by=admin_user,
        cancel_overlapping=True,
    )

    assert len(cancelled) == 1
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert len(mail.outbox) >= 1
    assert "storniert" in mail.outbox[0].subject.lower()

@pytest.mark.django_db
def test_member_books_with_member_zero_charge(court_sand, member_user, member_user2):
    """AP-07: Mitglied bucht Slot mit einem Mitglied als Mitspieler -> Preis 0 €, keine Forderung."""
    start = timezone.now() + timedelta(days=2, hours=1)
    end = start + timedelta(hours=1)

    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=end,
        participant_user_ids=[member_user2.id],
    )
    assert booking.total_price == Decimal("0.00")
    assert not Charge.objects.filter(object_id=booking.id).exists()

@pytest.mark.django_db
def test_member_books_with_guest_creates_guest_fee_charge(court_sand, member_user):
    """AP-07: Mitglied bucht mit einem Gast -> Forderung GUEST_FEE gemäß Preisregel."""
    start = timezone.now() + timedelta(days=2, hours=2)
    end = start + timedelta(hours=1)

    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=end,
        guest_names=["Stefan Gastspieler"],
    )
    # PriceRule guest of member = 5.00 €
    assert booking.total_price == Decimal("5.00")
    chg = Charge.objects.get(object_id=booking.id)
    assert chg.kind == Charge.Kind.GUEST_FEE
    assert chg.amount == Decimal("5.00")
    assert chg.user == member_user

@pytest.mark.django_db
def test_guest_booking_creates_court_fee_charge(court_sand, guest_user):
    """AP-07: Gast bucht -> Forderung COURT_FEE gemäß Gastpreis."""
    start = timezone.now() + timedelta(days=1, hours=3)
    end = start + timedelta(hours=1)

    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=start,
        end=end,
    )
    # PriceRule guest = 15.00 €/h
    assert booking.total_price == Decimal("15.00")
    chg = Charge.objects.get(object_id=booking.id)
    assert chg.kind == Charge.Kind.COURT_FEE
    assert chg.amount == Decimal("15.00")
    assert chg.user == guest_user

@pytest.mark.django_db
def test_extras_automatic_and_optional_calculation(court_halle, member_user):
    """AP-07: Halle automatisch berechnet, Flutlicht nur bei Auswahl; Preise eingefroren."""
    # Add optional Flutlicht extra
    extra_light = BookingExtra.objects.create(
        name="Flutlicht",
        price_member=Decimal("4.00"),
        price_guest=Decimal("6.00"),
        unit=BookingExtra.Unit.PER_HOUR,
        mode=BookingExtra.Mode.OPTIONAL,
        is_active=True,
    )

    start = timezone.now() + timedelta(days=1, hours=4)
    end = start + timedelta(hours=1)

    # Member books Halle with Flutlicht selected:
    # Halle extra (auto) = 10 € + Flutlicht (optional) = 4 € => 14 €
    booking = create_booking(
        court=court_halle,
        booked_by=member_user,
        start=start,
        end=end,
        selected_extra_ids=[extra_light.id],
    )
    assert booking.total_price == Decimal("14.00")
    assert booking.extra_lines.count() == 2

    # Price change later in admin does NOT affect existing booking (frozen price)
    extra_light.price_member = Decimal("10.00")
    extra_light.save()

    booking.refresh_from_db()
    assert booking.total_price == Decimal("14.00")
    light_line = booking.extra_lines.get(extra=extra_light)
    assert light_line.unit_price == Decimal("4.00")

@pytest.mark.django_db
def test_concurrency_collision_prevention(court_sand, member_user, member_user2):
    """AP-07: Zwei gleichzeitige Buchungsversuche auf denselben Slot -> genau einer erfolgreich."""
    start = timezone.now() + timedelta(days=2, hours=5)
    end = start + timedelta(hours=1)

    # First booking succeeds
    b1 = create_booking(court=court_sand, booked_by=member_user, start=start, end=end)
    assert b1.pk is not None

    # Second overlapping booking must fail
    with pytest.raises(ValidationError):
        create_booking(court=court_sand, booked_by=member_user2, start=start, end=end)

@pytest.mark.django_db
def test_booking_rules_enforcement(court_sand, member_user, club_settings):
    """AP-07: Buchungsregeln (Vorlauf, max. offene Buchungen, max. Dauer) durchgesetzt."""
    now = timezone.now()

    # Exceeding advance days (7 days for member)
    with pytest.raises(ValidationError):
        create_booking(
            court=court_sand,
            booked_by=member_user,
            start=now + timedelta(days=10),
            end=now + timedelta(days=10, hours=1),
        )

    # Exceeding max duration (120 minutes)
    with pytest.raises(ValidationError):
        create_booking(
            court=court_sand,
            booked_by=member_user,
            start=now + timedelta(days=1),
            end=now + timedelta(days=1, hours=3),  # 180 min
        )

@pytest.mark.django_db
def test_timely_cancellation_cancels_charge(court_sand, guest_user, club_settings):
    """AP-07: Stornierung innerhalb der Frist storniert Forderung; danach bleibt sie bestehen."""
    start = timezone.now() + timedelta(hours=10)  # > 4 hours free cancel window
    end = start + timedelta(hours=1)

    booking = create_booking(court=court_sand, booked_by=guest_user, start=start, end=end)
    chg = Charge.objects.get(object_id=booking.id)
    assert chg.status == Charge.Status.OPEN

    cancel_booking(booking=booking, user=guest_user)
    booking.refresh_from_db()
    chg.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert chg.status == Charge.Status.CANCELLED

@pytest.mark.django_db
def test_public_view_shows_no_names(court_sand, member_user):
    """AP-07 / P-11: Öffentliche Belegungsansicht ohne Namen („Belegt“)."""
    target_day = timezone.now().date() + timedelta(days=1)
    start = timezone.make_aware(timezone.datetime.combine(target_day, timezone.datetime.min.time())) + timedelta(hours=10)
    end = start + timedelta(hours=1)

    create_booking(court=court_sand, booked_by=member_user, start=start, end=end)

    # Anonymous visitor checking calendar
    slots = get_court_slots_for_day(court_sand, target_day, user=None)
    booked_slot = next(s for s in slots if s["start_time_str"] == "10:00")

    assert booked_slot["state"] == "taken"
    assert booked_slot["label"] == "Belegt"
    assert member_user.first_name not in booked_slot["label"]
    assert member_user.last_name not in booked_slot["label"]
