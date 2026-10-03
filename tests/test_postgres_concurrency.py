"""Real concurrent transactions; executed by the PostgreSQL CI job."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Charge
from apps.billing.services import (
    create_charge,
    record_payment,
    generate_membership_fees,
)
from apps.courts.models import Booking, Court
from apps.courts.services import create_booking

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Requires PostgreSQL row locks"
    ),
]


def concurrent_calls(callback):
    barrier = Barrier(2, timeout=10)

    def run():
        close_old_connections()
        try:
            barrier.wait()
            return callback()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


def test_concurrent_payments_cannot_overpay(member_user):
    charge = create_charge(
        user=member_user,
        kind="OTHER",
        amount=20,
        due_date=timezone.localdate(),
        description="Concurrency",
    )

    def pay():
        try:
            record_payment(charge=Charge.objects.get(pk=charge.pk), amount=15)
            return "paid"
        except ValueError:
            return "rejected"

    assert sorted(concurrent_calls(pay)) == ["paid", "rejected"]
    assert charge.total_paid == 15


def test_concurrent_same_court_booking_has_one_winner(
    court_sand, member_user, member_user2
):
    start = timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=1), time(10))
    )
    users = iter([member_user.pk, member_user2.pk])
    from threading import Lock

    lock = Lock()

    def book():
        with lock:
            user_id = next(users)
        try:
            create_booking(
                court=Court.objects.get(pk=court_sand.pk),
                booked_by=User.objects.get(pk=user_id),
                start=start,
                end=start + timedelta(hours=1),
            )
            return "booked"
        except ValidationError:
            return "rejected"

    assert sorted(concurrent_calls(book)) == ["booked", "rejected"]
    assert Booking.objects.count() == 1


def test_concurrent_different_courts_respect_member_quota(
    court_sand, court_halle, member_user, club_settings
):
    club_settings.max_open_bookings = 1
    club_settings.save()
    start = timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=1), time(10))
    )
    courts = iter([court_sand.pk, court_halle.pk])
    from threading import Lock

    lock = Lock()

    def book():
        with lock:
            court_id = next(courts)
        try:
            create_booking(
                court=Court.objects.get(pk=court_id),
                booked_by=User.objects.get(pk=member_user.pk),
                start=start,
                end=start + timedelta(hours=1),
            )
            return "booked"
        except ValidationError:
            return "rejected"

    assert sorted(concurrent_calls(book)) == ["booked", "rejected"]
    assert Booking.objects.filter(booked_by=member_user).count() == 1


def test_concurrent_fee_runs_do_not_duplicate_charges(member_user):
    results = concurrent_calls(
        lambda: len(generate_membership_fees(year=timezone.localdate().year))
    )
    assert sorted(results) == [0, 1]
    assert Charge.objects.count() == 1


def test_concurrent_approvals_allocate_distinct_member_numbers(admin_user, guest_user):
    from apps.members.models import MembershipApplication, MembershipType, Membership
    from apps.members.services import approve_application

    other = User.objects.create_user(
        email="other-applicant@example.com", email_verified=True
    )
    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    applications = iter(
        [
            MembershipApplication.objects.create(
                user=user, requested_type=membership_type
            ).pk
            for user in [guest_user, other]
        ]
    )
    from threading import Lock

    lock = Lock()

    def approve():
        with lock:
            pk = next(applications)
        return approve_application(
            application=MembershipApplication.objects.get(pk=pk),
            reviewer=User.objects.get(pk=admin_user.pk),
        ).member_number

    assert sorted(concurrent_calls(approve)) == ["TCM-0001", "TCM-0002"]
    assert Membership.objects.count() == 2


def test_concurrent_repeat_approval_creates_one_membership(admin_user, guest_user):
    from apps.members.models import MembershipApplication, MembershipType, Membership
    from apps.members.services import approve_application

    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    application = MembershipApplication.objects.create(
        user=guest_user, requested_type=membership_type
    )

    def approve():
        try:
            approve_application(
                application=MembershipApplication.objects.get(pk=application.pk),
                reviewer=User.objects.get(pk=admin_user.pk),
            )
            return "approved"
        except ValueError:
            return "rejected"

    assert sorted(concurrent_calls(approve)) == ["approved", "rejected"]
    assert Membership.objects.count() == 1


def test_concurrent_tournament_registrations_respect_capacity(
    member_user, member_user2
):
    from apps.tournaments.models import Tournament, Competition, Entry
    from apps.tournaments.services import register_for_competition

    tournament = Tournament.objects.create(
        name="Race",
        status="OPEN",
        start_date=timezone.localdate() + timedelta(days=1),
        end_date=timezone.localdate() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(hours=1),
        fee_member=0,
    )
    competition = Competition.objects.create(
        tournament=tournament, name="Einzel", max_entries=1
    )
    users = iter([member_user.pk, member_user2.pk])
    from threading import Lock

    lock = Lock()

    def register():
        with lock:
            user_id = next(users)
        return register_for_competition(
            competition=Competition.objects.get(pk=competition.pk),
            player1=User.objects.get(pk=user_id),
        ).status

    assert sorted(concurrent_calls(register)) == sorted(
        [Entry.Status.CONFIRMED, Entry.Status.WAITLIST]
    )
    assert Entry.objects.filter(status=Entry.Status.CONFIRMED).count() == 1
