"""Regression tests for the findings of the October 2026 code review."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.models import User
from apps.billing.models import Charge
from apps.billing.services import create_charge, generate_membership_fees
from apps.courts.models import Booking, OpeningHours, Season
from apps.courts.selectors import get_opening_hours_for_court
from apps.tournaments.models import Competition, Entry, Match, Tournament
from apps.tournaments.services import (
    calculate_round_robin_standings,
    draw_competition,
    draw_review_token,
    register_for_competition,
    withdraw_entry,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def open_cup():
    return Tournament.objects.create(
        name="Review Cup",
        start_date=timezone.localdate() + timedelta(days=7),
        end_date=timezone.localdate() + timedelta(days=8),
        registration_deadline=timezone.now() + timedelta(days=3),
        status=Tournament.Status.OPEN,
        eligibility=Tournament.Eligibility.MEMBERS_AND_GUESTS,
        fee_member=Decimal("10.00"),
        fee_guest=Decimal("15.00"),
    )


def make_players(count):
    return [
        User.objects.create_user(
            email=f"spieler{i}@test.at", password="p", email_verified=True
        )
        for i in range(count)
    ]


def test_seasonal_opening_hours_override_default(court_sand):
    day = timezone.localdate() + timedelta(days=1)
    season = Season.objects.create(
        name="Sommer", start_date=day - timedelta(days=30), end_date=day + timedelta(days=30)
    )
    seasonal = OpeningHours.objects.create(
        court=court_sand,
        weekday=day.weekday(),
        season=season,
        open_time=time(7, 0),
        close_time=time(22, 0),
        slot_minutes=60,
    )
    assert get_opening_hours_for_court(court_sand, day) == seasonal


def test_waitlist_entry_is_billed_only_after_promotion(open_cup):
    competition = Competition.objects.create(
        tournament=open_cup, name="Einzel", max_entries=2
    )
    p1, p2, p3 = make_players(3)
    first = register_for_competition(competition=competition, player1=p1)
    register_for_competition(competition=competition, player1=p2)
    waiting = register_for_competition(competition=competition, player1=p3)

    assert waiting.status == Entry.Status.WAITLIST
    assert not Charge.objects.filter(user=p3).exists()

    withdraw_entry(first)
    waiting.refresh_from_db()
    assert waiting.status == Entry.Status.CONFIRMED
    fee = Charge.objects.get(user=p3)
    assert fee.kind == Charge.Kind.TOURNAMENT_FEE
    assert fee.amount == Decimal("15.00")


def test_waitlist_entry_stays_unbilled_after_draw(open_cup, admin_user):
    competition = Competition.objects.create(
        tournament=open_cup, name="Einzel", max_entries=2
    )
    players = make_players(3)
    for player in players:
        register_for_competition(competition=competition, player1=player)
    draw_competition(
        competition=competition,
        actor=admin_user,
        review_token=draw_review_token(competition),
    )
    assert not Charge.objects.filter(user=players[2]).exists()


def test_draw_keeps_other_competitions_open(open_cup, admin_user):
    herren = Competition.objects.create(tournament=open_cup, name="Herren")
    damen = Competition.objects.create(tournament=open_cup, name="Damen")
    p1, p2, p3, p4 = make_players(4)
    register_for_competition(competition=herren, player1=p1)
    register_for_competition(competition=herren, player1=p2)

    draw_competition(
        competition=herren, actor=admin_user, review_token=draw_review_token(herren)
    )
    open_cup.refresh_from_db()
    assert open_cup.status == Tournament.Status.OPEN

    # Drawn competition is closed, the other one still accepts entries.
    with pytest.raises(ValidationError, match="geschlossen"):
        register_for_competition(competition=herren, player1=p3)
    register_for_competition(competition=damen, player1=p3)
    register_for_competition(competition=damen, player1=p4)

    draw_competition(
        competition=damen, actor=admin_user, review_token=draw_review_token(damen)
    )
    open_cup.refresh_from_db()
    assert open_cup.status == Tournament.Status.DRAWN


@freeze_time("2026-10-26 23:30:00+00:00")
def test_calendar_uses_local_date(client):
    # 23:30 UTC is already 00:30 on the next day in Vienna.
    response = client.get(reverse("courts:calendar"))
    assert response.context["current_day"] == date(2026, 10, 27)
    assert response.context["days_strip"][0]["date"] == date(2026, 10, 27)


def test_match_tiebreak_points_are_not_counted_as_games(open_cup):
    competition = Competition.objects.create(
        tournament=open_cup, name="Gruppe", format=Competition.Format.ROUND_ROBIN
    )
    p1, p2 = make_players(2)
    e1 = Entry.objects.create(competition=competition, player1=p1, status="CONFIRMED")
    e2 = Entry.objects.create(competition=competition, player1=p2, status="CONFIRMED")
    Match.objects.create(
        competition=competition,
        round=1,
        position=1,
        entry_a=e1,
        entry_b=e2,
        winner=e1,
        score=[{"a": 6, "b": 4}, {"a": 4, "b": 6}, {"a": 10, "b": 8}],
    )
    rows = {row["entry"].pk: row for row in calculate_round_robin_standings(competition)}
    assert (rows[e1.pk]["games_won"], rows[e1.pk]["games_lost"]) == (10, 10)
    assert (rows[e1.pk]["sets_won"], rows[e1.pk]["sets_lost"]) == (2, 1)


def test_validation_messages_are_shown_as_plain_text(
    client, court_sand, member_user, guest_user
):
    start = timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=2), time(10, 0))
    )
    booking = Booking.objects.create(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
        status=Booking.Status.CONFIRMED,
        total_price=Decimal("0.00"),
    )
    client.force_login(guest_user)
    response = client.post(reverse("courts:cancel", args=[booking.pk]))
    texts = [str(message) for message in get_messages(response.wsgi_request)]
    assert texts == ["Keine Berechtigung zur Stornierung dieser Buchung."]


def test_yearly_fee_is_billed_despite_earlier_monthly_fee(member_user):
    create_charge(
        user=member_user,
        kind=Charge.Kind.MEMBERSHIP_FEE,
        amount=Decimal("15.00"),
        due_date=date(2026, 1, 5),
        description="Mitgliedsbeitrag 01/2026 (alte Monatsmitgliedschaft)",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    created = generate_membership_fees(year=2026)
    assert [charge.user for charge in created] == [member_user]
    assert generate_membership_fees(year=2026) == []
