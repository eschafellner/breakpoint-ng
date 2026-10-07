"""Regression coverage for the security and MVP workflow review."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.models import User
from apps.accounts.services import (
    request_account_recovery,
    send_account_access_email,
    verify_email,
)
from apps.accounts.tokens import account_access_token_generator
from apps.billing.models import Charge, Payment
from apps.billing.selectors import get_billing_summary, get_cashier_charges
from apps.billing.services import generate_membership_fees, record_payment
from apps.core.models import AuditLog, ClubSettings, OutgoingEmail
from apps.core.services import deliver_outgoing_email, send_mail_after_commit
from apps.courts.models import Booking, Blocking
from apps.courts.tasks import send_booking_reminders
from apps.members.models import MembershipType
from apps.members.services import import_members_from_csv
from apps.tournaments.models import Competition, Entry, Tournament
from apps.tournaments.selectors import get_potential_partners
from apps.tournaments.services import draw_competition, draw_review_token

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("state", ["unverified", "locked", "inactive"])
def test_admin_login_enforces_account_state(client, admin_user, state):
    if state == "unverified":
        admin_user.email_verified = False
    elif state == "locked":
        admin_user.locked_until = timezone.now() + timedelta(minutes=15)
    else:
        admin_user.is_active = False
    admin_user.save()
    response = client.post(
        reverse("admin:login"),
        {
            "username": admin_user.email,
            "password": "adminpassword123",
            "next": "/admin/",
        },
    )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert authenticate(username=admin_user.email, password="adminpassword123") is None


def test_public_and_admin_logins_share_failure_limit(client, admin_user):
    for i in range(5):
        if i % 2:
            client.post(
                reverse("admin:login"),
                {"username": admin_user.email, "password": "wrong"},
            )
        else:
            client.post(
                reverse("accounts:login"),
                {"email": admin_user.email, "password": "wrong"},
            )
    admin_user.refresh_from_db()
    assert admin_user.failed_login_attempts == 5
    assert admin_user.is_locked
    assert authenticate(username=admin_user.email, password="adminpassword123") is None
    with freeze_time(timezone.now() + timedelta(minutes=16)):
        assert authenticate(
            username=admin_user.email.upper(), password="adminpassword123"
        )
    admin_user.refresh_from_db()
    assert admin_user.failed_login_attempts == 0


def access_path(user):
    email = OutgoingEmail.objects.filter(recipients=[user.email]).latest("pk")
    return re.search(r"https?://[^\s]+(/accounts/access/[^\s]+)", email.message).group(
        1
    )


def test_imported_user_can_set_password_once(client, member_user, admin_user):
    result = import_members_from_csv(
        "email,first_name,last_name,membership_type\nnew@example.at,Neu,Mitglied,Erwachsener",
        reviewer=admin_user,
    )
    assert result == {"created": 1, "errors": []}
    user = User.objects.get(email="new@example.at")
    assert not user.has_usable_password()
    path = access_path(user)
    response = client.get(path)
    assert response.status_code == 302
    response = client.post(
        response.url,
        {
            "new_password1": "NewSafePassword!984",
            "new_password2": "NewSafePassword!984",
        },
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.email_verified
    assert user.check_password("NewSafePassword!984")
    assert authenticate(username=user.email, password="NewSafePassword!984")
    assert not client.get(path).context["validlink"]


def test_access_token_expiry_renewal_and_inactive_account(client, guest_user):
    send_account_access_email(guest_user)
    guest_user.refresh_from_db()
    old_token = account_access_token_generator.make_token(guest_user)
    old_path = access_path(guest_user)
    with freeze_time(timezone.now() + timedelta(seconds=61)):
        assert send_account_access_email(guest_user)
        guest_user.refresh_from_db()
        assert not account_access_token_generator.check_token(guest_user, old_token)
        new_token = account_access_token_generator.make_token(guest_user)
        with freeze_time(timezone.now() + timedelta(hours=25)):
            assert not account_access_token_generator.check_token(guest_user, new_token)
    assert not client.get(old_path).context["validlink"]
    new_path = access_path(guest_user)
    guest_user.is_active = False
    guest_user.save()
    assert not client.get(new_path).context["validlink"]


def test_verification_resend_expiry_and_one_time_use(guest_user):
    guest_user.email_verified = False
    guest_user.save()
    first = guest_user.generate_verification_token()
    with freeze_time(timezone.now() + timedelta(hours=25)):
        assert verify_email(first) is None
        request_account_recovery(guest_user.email)
        guest_user.refresh_from_db()
        replacement = guest_user.email_verification_token
        assert replacement != first
        assert verify_email(first) is None
        assert verify_email(replacement).pk == guest_user.pk
        assert verify_email(replacement) is None


def test_recovery_response_is_neutral_and_throttled(client, guest_user):
    cache.clear()
    known = client.post(
        reverse("accounts:account_recovery"), {"email": guest_user.email}
    )
    unknown = client.post(
        reverse("accounts:account_recovery"), {"email": "absent@example.at"}
    )
    repeated = client.post(
        reverse("accounts:account_recovery"), {"email": guest_user.email}
    )
    assert known.url == unknown.url == repeated.url
    assert OutgoingEmail.objects.count() == 1
    guest_user.refresh_from_db()
    assert send_account_access_email(guest_user) is False


def make_email():
    return OutgoingEmail.objects.create(
        subject="Test",
        message="Body",
        from_email="club@example.at",
        recipients=["player@example.at"],
    )


def test_mail_failure_is_saved_retried_and_not_sent_twice(mailoutbox):
    email = make_email()
    with patch("apps.core.services.send_mail", side_effect=OSError("SMTP unavailable")):
        assert not deliver_outgoing_email(email.pk)
    email.refresh_from_db()
    assert email.status == OutgoingEmail.Status.PENDING
    assert email.attempts == 1 and "SMTP unavailable" in email.last_error
    assert not deliver_outgoing_email(email.pk)
    with freeze_time(email.next_attempt_at + timedelta(seconds=1)):
        assert deliver_outgoing_email(email.pk)
        assert not deliver_outgoing_email(email.pk)
    assert len(mailoutbox) == 1


def test_mail_zero_deliveries_and_retry_exhaustion():
    email = make_email()
    with patch("apps.core.services.send_mail", return_value=0):
        for attempt in range(8):
            email.refresh_from_db()
            with freeze_time(email.next_attempt_at + timedelta(seconds=1)):
                assert not deliver_outgoing_email(email.pk)
    email.refresh_from_db()
    assert email.status == OutgoingEmail.Status.FAILED and email.attempts == 8


def test_mail_outbox_rolls_back_with_business_transaction(
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(ValueError), transaction.atomic():
            send_mail_after_commit(
                subject="Test",
                message="Body",
                from_email="club@example.at",
                recipient_list=["player@example.at"],
            )
            raise ValueError("business operation failed")
    assert callbacks == []
    assert not OutgoingEmail.objects.exists()


def test_broker_failure_does_not_lose_mail(
    settings, django_capture_on_commit_callbacks
):
    settings.MAIL_DELIVERY_ASYNC = True
    with patch(
        "apps.core.tasks.deliver_email.delay", side_effect=OSError("broker unavailable")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            email = send_mail_after_commit(
                subject="Test",
                message="Body",
                from_email="club@example.at",
                recipient_list=["player@example.at"],
            )
    email.refresh_from_db()
    assert email.status == OutgoingEmail.Status.PENDING
    from apps.core.tasks import deliver_pending_emails

    assert deliver_pending_emails() == 1


def test_audit_admin_cannot_delete_even_as_superuser(client, admin_user):
    log = AuditLog.objects.create(action="TEST", entity_type="User", entity_id="1")
    client.force_login(admin_user)
    assert (
        client.get(reverse("admin:core_auditlog_delete", args=[log.pk])).status_code
        == 403
    )
    response = client.post(
        reverse("admin:core_auditlog_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": [log.pk],
            "post": "yes",
        },
    )
    assert response.status_code == 200
    assert AuditLog.objects.filter(pk=log.pk).exists()


@pytest.mark.parametrize(
    "url_name,field",
    [("core:imprint", "imprint_text"), ("core:privacy", "privacy_text")],
)
def test_legal_pages_sanitize_legacy_html(client, club_settings, url_name, field):
    unsafe = '<p>Allowed text</p><script>alert(1)</script><a href="javascript:alert(2)" onclick="alert(3)">link</a><img src="x" onerror="alert(4)">'
    ClubSettings.objects.filter(pk=club_settings.pk).update(**{field: unsafe})
    body = client.get(reverse(url_name)).content.decode()
    assert "Allowed text" in body
    assert (
        "javascript:" not in body and "onclick=" not in body and "onerror=" not in body
    )
    assert "alert(1)" not in body
    club_settings.refresh_from_db()
    club_settings.save()
    assert "<script>" not in getattr(club_settings, field)


@pytest.fixture
def competition(member_user, member_user2):
    tournament = Tournament.objects.create(
        name="Review Cup",
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        eligibility=Tournament.Eligibility.MEMBERS_ONLY,
        status=Tournament.Status.OPEN,
    )
    competition = Competition.objects.create(
        tournament=tournament, name="Einzel", discipline="SINGLES", format="ROUND_ROBIN"
    )
    for user in [member_user, member_user2]:
        Entry.objects.create(
            competition=competition, player1=user, status=Entry.Status.CONFIRMED
        )
    return competition


def test_partner_visibility_requires_eligibility_and_opt_in(
    competition, member_user, member_user2, guest_user
):
    tournament = competition.tournament
    assert not get_potential_partners(tournament, member_user).exists()
    member_user2.allow_partner_search = True
    member_user2.save()
    assert list(get_potential_partners(tournament, member_user)) == [member_user2]
    assert not get_potential_partners(tournament, AnonymousUser()).exists()
    assert not get_potential_partners(tournament, guest_user).exists()
    member_user2.memberships.update(status="INACTIVE")
    assert not get_potential_partners(tournament, member_user).exists()


def test_partner_names_are_hidden_on_public_detail_and_forged_post(
    client, competition, member_user, member_user2
):
    competition.discipline = "DOUBLES"
    competition.save()
    competition.entries.all().delete()
    assert (
        member_user2.get_full_name()
        not in client.get(
            reverse("tournaments:detail", args=[competition.tournament.slug])
        ).content.decode()
    )
    client.force_login(member_user)
    assert (
        client.post(
            reverse("tournaments:register", args=[competition.pk]),
            {"partner_id": member_user2.pk},
        ).status_code
        == 404
    )
    assert not competition.entries.exists()


def test_draw_review_requires_permission_confirmation_and_current_list(
    client, competition, admin_user, guest_user
):
    url = reverse("tournaments:draw", args=[competition.pk])
    client.force_login(guest_user)
    assert client.get(url).status_code == 403
    client.force_login(admin_user)
    response = client.get(url)
    assert response.status_code == 200
    token = response.context["form"].initial["snapshot"]
    assert client.post(url, {"snapshot": token}).status_code == 200
    assert not competition.matches.exists()
    Entry.objects.filter(competition=competition).update(seed=1)
    response = client.post(url, {"snapshot": token, "confirm": "on"})
    assert response.status_code == 200 and not competition.matches.exists()
    fresh = client.get(url).context["form"].initial["snapshot"]
    assert client.post(url, {"snapshot": fresh, "confirm": "on"}).status_code == 302
    assert competition.matches.count() == 1
    competition.tournament.refresh_from_db()
    assert competition.tournament.status == Tournament.Status.DRAWN
    assert AuditLog.objects.filter(action="DRAW_COMPETITION").exists()


def test_round_robin_result_and_schedule_controls_work(
    client, competition, admin_user, court_sand
):
    draw_competition(
        competition=competition,
        actor=admin_user,
        review_token=draw_review_token(competition),
    )
    match = competition.matches.get()
    client.force_login(admin_user)
    url = reverse("tournaments:detail", args=[competition.tournament.slug])
    html = client.get(url).content.decode()
    result_url = reverse("tournaments:match_result", args=[match.pk])
    schedule_url = reverse("tournaments:schedule_match", args=[match.pk])
    assert result_url in html and schedule_url in html
    start = timezone.localdate() + timedelta(days=1)
    response = client.post(
        schedule_url,
        {"court_id": court_sand.pk, "start": f"{start}T10:00", "duration": "90"},
    )
    assert response.status_code == 302
    match.refresh_from_db()
    assert match.scheduled_court_id == court_sand.pk
    assert Blocking.objects.filter(
        court=court_sand, start=match.scheduled_start
    ).exists()
    assert (
        client.post(
            result_url,
            {
                "winner_id": match.entry_a_id,
                "set1": "6:4",
                "set2": "6:2",
                "result_type": "NORMAL",
            },
        ).status_code
        == 302
    )
    match.refresh_from_db()
    assert match.winner_id == match.entry_a_id
    with pytest.raises(ValidationError):
        draw_competition(
            competition=competition,
            actor=admin_user,
            review_token=draw_review_token(competition),
        )


@pytest.mark.parametrize(
    "instant,expected",
    [("2027-07-10T08:00:00Z", "10:00"), ("2027-01-10T08:00:00Z", "09:00")],
)
def test_reminder_retries_missed_window_and_uses_vienna_time(
    instant, expected, member_user, court_sand, mailoutbox
):
    start = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    booking = Booking.objects.create(
        booked_by=member_user,
        court=court_sand,
        start=start,
        end=start + timedelta(hours=1),
        status="CONFIRMED",
    )
    with freeze_time(start - timedelta(hours=24, minutes=30)):
        with patch("apps.courts.tasks.send_mail", side_effect=OSError("offline")):
            assert send_booking_reminders() == "Sent 0 reminders."
    with freeze_time(start - timedelta(hours=23, minutes=30)):
        assert send_booking_reminders() == "Sent 1 reminders."
        assert send_booking_reminders() == "Sent 0 reminders."
    assert expected in mailoutbox[0].subject and expected in mailoutbox[0].body
    booking.refresh_from_db()
    assert booking.reminder_sent_at


def test_monthly_fee_not_due_before_joining(member_user, club_settings):
    membership = member_user.memberships.get()
    monthly = MembershipType.objects.create(
        name="Monthly", fee_amount=Decimal("20.00"), billing_interval="MONTHLY"
    )
    membership.type = monthly
    membership.start_date = date(2027, 7, 20)
    membership.save()
    charges = generate_membership_fees(year=2027, month=7)
    assert len(charges) == 1 and charges[0].due_date == date(2027, 7, 20)
    assert len(generate_membership_fees(year=2027, month=7)) == 0


def test_finance_query_count_and_partial_payments(
    member_user, django_assert_num_queries
):
    charges = Charge.objects.bulk_create(
        [
            Charge(
                user=member_user,
                kind="OTHER",
                description=f"Fee {i}",
                amount=Decimal("20.00"),
                due_date=date(2020, 1, 1),
                status="PARTIAL",
            )
            for i in range(101)
        ]
    )
    Payment.objects.bulk_create(
        [
            Payment(charge=charge, amount=Decimal("3.00"), method="CASH")
            for charge in charges
            for _ in range(2)
        ]
    )
    with django_assert_num_queries(2):
        summary = get_billing_summary()
    assert summary == {
        "total_amount": Decimal("2020.00"),
        "open_amount": Decimal("1414.00"),
        "paid_amount": Decimal("606.00"),
        "overdue_count": 101,
    }
    with django_assert_num_queries(1):
        rows = list(get_cashier_charges())
        assert sum(row.open_amount for row in rows) == Decimal("1414.00")
    record_payment(charge=rows[0], amount=Decimal("2.00"), method="CASH")
    assert rows[0].open_amount == Decimal("12.00")


def test_finance_pagination_reaches_records_beyond_100(client, member_user, admin_user):
    Charge.objects.bulk_create(
        [
            Charge(
                user=member_user,
                kind="OTHER",
                description=f"Fee {i}",
                amount=Decimal("20.00"),
                due_date=date(2020, 1, 1),
            )
            for i in range(101)
        ]
    )
    client.force_login(admin_user)
    response = client.get(reverse("billing:dashboard"), {"page": 3, "q": "Fee"})
    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 101
    assert len(response.context["charges"]) == 1
    assert "q=Fee" in response.content.decode()


def test_offline_page_is_anonymous_and_updates_contact_info(
    client, admin_user, club_settings
):
    client.force_login(admin_user)
    url = reverse("core:offline")
    response = client.get(url)
    html = response.content.decode()
    assert response["X-Breakpoint-Offline"] == "public"
    assert "Cookie" not in response.get("Vary", "")
    assert admin_user.email not in html and "csrfmiddlewaretoken" not in html
    assert "/admin/" not in html and "Abmelden" not in html
    club_settings.offline_emergency_info = "Neuer Notfallkontakt 0664 123456"
    club_settings.save()
    assert "Neuer Notfallkontakt 0664 123456" in client.get(url).content.decode()
