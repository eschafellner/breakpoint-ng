"""Positive and negative regressions found during the application audit."""

import csv
import io
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_member
from apps.accounts.services import register_user, record_failed_login, verify_email
from apps.billing.models import Charge, Payment, PriceRule
from apps.billing.selectors import get_billing_summary
from apps.billing.services import (
    create_charge,
    record_payment,
    quantize_amount,
    generate_membership_fees,
    export_charges_to_csv,
)
from apps.courts.models import Booking, OpeningHours
from apps.courts.services import create_booking, cancel_booking
from apps.courts.tasks import send_booking_reminders
from apps.news.services import add_gallery_image
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from apps.members.models import Membership, MembershipApplication, MembershipType
from apps.members.selectors import get_active_members_directory
from apps.members.services import (
    approve_application,
    reject_application,
    import_members_from_csv,
    get_next_member_number,
)
from apps.news.models import Article, Category
from apps.news.selectors import get_article_by_slug, get_categories
from apps.tournaments.models import Tournament, Competition, Entry, Match
from apps.tournaments.services import (
    register_for_competition,
    validate_tennis_score,
    record_match_result,
    schedule_tournament_match,
    generate_knockout_draw,
)

pytestmark = pytest.mark.django_db


def slot(days=1, hour=10):
    return timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=days), time(hour))
    )


@pytest.fixture
def charge(member_user):
    return create_charge(
        user=member_user,
        kind=Charge.Kind.OTHER,
        amount=Decimal("20"),
        due_date=timezone.localdate(),
        description="Test",
    )


@pytest.fixture
def competition():
    tournament = Tournament.objects.create(
        name="Audit Cup",
        start_date=timezone.localdate() + timedelta(days=7),
        end_date=timezone.localdate() + timedelta(days=8),
        registration_deadline=timezone.now() + timedelta(days=3),
        status=Tournament.Status.OPEN,
        fee_member=0,
        fee_guest=0,
    )
    return Competition.objects.create(tournament=tournament, name="Einzel")


@pytest.mark.parametrize(
    "case", ["expired", "future", "ended", "inactive", "unverified"]
)
def test_invalid_membership_has_no_member_access(client, member_user, case):
    membership = member_user.memberships.first()
    if case == "expired":
        membership.end_date = timezone.localdate() - timedelta(days=1)
    elif case == "future":
        membership.start_date = timezone.localdate() + timedelta(days=1)
    elif case == "ended":
        membership.status = Membership.Status.ENDED
    else:
        setattr(
            member_user, "is_active" if case == "inactive" else "email_verified", False
        )
        member_user.save()
    membership.save()
    assert not is_member(member_user)
    assert not get_active_members_directory().filter(user=member_user).exists()
    article = Article.objects.create(
        title="Intern",
        body="Intern",
        status=Article.Status.PUBLISHED,
        visibility=Article.Visibility.MEMBERS,
    )
    assert get_article_by_slug(article.slug, user=member_user) is None
    client.force_login(member_user)
    assert client.get(reverse("members:directory")).status_code in (302, 403)


def test_login_next_rejects_external_redirect_and_accepts_local(client, guest_user):
    credentials = {"email": guest_user.email, "password": "guestpassword123"}
    response = client.post(
        reverse("accounts:login") + "?next=https://attacker.example/", credentials
    )
    assert response.url == "/"
    client.logout()
    response = client.post(
        reverse("accounts:login") + "?next=/accounts/profile/", credentials
    )
    assert response.url == "/accounts/profile/"


def test_login_email_is_case_insensitive(client, guest_user):
    response = client.post(
        reverse("accounts:login"),
        {"email": guest_user.email.upper(), "password": "guestpassword123"},
    )
    assert response.status_code == 302


def test_logout_requires_post(client, guest_user):
    client.force_login(guest_user)
    assert client.get(reverse("accounts:logout")).status_code == 405
    assert "_auth_user_id" in client.session
    assert client.post(reverse("accounts:logout")).status_code == 302
    assert "_auth_user_id" not in client.session


def test_lockout_does_not_extend_and_expiry_resets_counter(guest_user):
    now = timezone.now()
    guest_user.failed_login_attempts = 5
    guest_user.locked_until = now + timedelta(minutes=10)
    guest_user.save()
    record_failed_login(guest_user.email)
    guest_user.refresh_from_db()
    assert guest_user.locked_until == now + timedelta(minutes=10)
    guest_user.locked_until = now - timedelta(seconds=1)
    guest_user.save()
    assert record_failed_login(guest_user.email) is False
    guest_user.refresh_from_db()
    assert guest_user.failed_login_attempts == 1


def test_invalid_membership_registration_rolls_back():
    with pytest.raises(ValidationError):
        register_user(
            email="invalid@example.com",
            password="Secure123!foobar",
            first_name="A",
            last_name="B",
            account_type="MEMBER",
            apply_membership_type_id=99999,
        )
    assert not User.objects.filter(email="invalid@example.com").exists()


def test_verification_email_has_absolute_url(
    settings, django_capture_on_commit_callbacks
):
    settings.PUBLIC_SITE_URL = "https://tennis.example"
    with django_capture_on_commit_callbacks(execute=True):
        user = register_user(
            email="verify@example.com",
            password="Secure123!foobar",
            first_name="A",
            last_name="B",
        )
    assert (
        f"https://tennis.example/accounts/verify-email/{user.email_verification_token}/"
        in mail.outbox[-1].body
    )
    token = user.email_verification_token
    assert verify_email(token) is not None
    assert verify_email(token) is None
    assert verify_email("invalid-token") is None


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-Infinity", "not-money", "100000000.00"]
)
def test_invalid_money_is_rejected(value):
    with pytest.raises(ValueError):
        quantize_amount(value)


@pytest.mark.parametrize(
    "status", [Charge.Status.CANCELLED, Charge.Status.WAIVED, Charge.Status.PAID]
)
def test_terminal_charge_rejects_payment(charge, status):
    charge.status = status
    charge.save()
    with pytest.raises(ValueError):
        record_payment(charge=charge, amount=1)
    assert not Payment.objects.filter(charge=charge).exists()
    charge.refresh_from_db()
    assert charge.status == status


def test_overpayment_and_invalid_method_do_not_create_payment(charge):
    for kwargs in [{"amount": 21}, {"amount": 1, "method": "INVALID"}]:
        with pytest.raises(ValueError):
            record_payment(charge=charge, **kwargs)
    assert charge.payments.count() == 0


def test_stale_charge_payment_uses_current_state(charge):
    stale = Charge.objects.get(pk=charge.pk)
    record_payment(charge=charge, amount=15)
    with pytest.raises(ValueError):
        record_payment(charge=stale, amount=10)
    record_payment(charge=stale, amount=5)
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert charge.total_paid == Decimal("20")


def test_billing_summary_counts_actual_payments(charge):
    record_payment(charge=charge, amount=5)
    summary = get_billing_summary()
    assert summary["open_amount"] == Decimal("15")
    assert summary["paid_amount"] == Decimal("5")


def test_yearly_fees_exclude_memberships_outside_year(member_user):
    membership = member_user.memberships.get()
    membership.start_date = timezone.localdate().replace(year=2028, month=1, day=1)
    membership.save()
    assert generate_membership_fees(year=2027) == []
    membership.start_date = timezone.localdate().replace(year=2025, month=1, day=1)
    membership.end_date = timezone.localdate().replace(year=2025, month=12, day=31)
    membership.save()
    assert generate_membership_fees(year=2027) == []


def test_zero_monthly_fee_is_skipped(member_user):
    membership = member_user.memberships.get()
    membership.type.billing_interval = MembershipType.BillingInterval.MONTHLY
    membership.type.fee_amount = 0
    membership.type.save()
    assert generate_membership_fees(year=2026, month=10) == []


def test_csv_export_neutralizes_formulas(charge):
    charge.description = '=HYPERLINK("https://attacker.example")'
    charge.save()
    rows = list(csv.reader(io.StringIO(export_charges_to_csv([charge]))))
    assert rows[1][-1].startswith("'=HYPERLINK")


def test_membership_review_uses_fresh_state(admin_user, guest_user):
    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    application = MembershipApplication.objects.create(
        user=guest_user, requested_type=membership_type
    )
    stale = MembershipApplication.objects.get(pk=application.pk)
    reject_application(
        application=application, reviewer=admin_user, reason="Keine Aufnahme"
    )
    with pytest.raises(ValueError):
        approve_application(application=stale, reviewer=admin_user)
    assert not Membership.objects.filter(user=guest_user).exists()


def test_member_number_accounts_for_imported_numbers(member_user):
    Membership.objects.filter(user=member_user).update(member_number="TCM-0100")
    assert get_next_member_number() == "TCM-0101"


def test_malformed_csv_row_does_not_abort_following_rows(admin_user):
    MembershipType.objects.create(name="Adult", fee_amount=10)
    result = import_members_from_csv(
        "email,first_name,last_name,membership_type\nbroken@example.com,A,B,Adult,extra\nvalid@example.com,A,B,Adult\ninvalid-email,A,B,Adult\n",
        reviewer=admin_user,
    )
    assert result["created"] == 1
    assert [error["line"] for error in result["errors"]] == [2, 4]
    assert User.objects.get(email="valid@example.com").has_usable_password() is False
    assert not User.objects.filter(email="invalid-email").exists()


@pytest.mark.parametrize("hour,minutes", [(7, 60), (20, 120), (10, 121)])
def test_booking_rejects_outside_hours_or_duration(
    court_sand, member_user, hour, minutes
):
    start = slot(hour=hour)
    with pytest.raises(ValidationError):
        create_booking(
            court=court_sand,
            booked_by=member_user,
            start=start,
            end=start + timedelta(minutes=minutes),
        )
    assert not Booking.objects.exists()


def test_booking_rejects_partial_slots(court_sand, member_user):
    start = slot() + timedelta(seconds=1)
    with pytest.raises(ValidationError):
        create_booking(
            court=court_sand,
            booked_by=member_user,
            start=start,
            end=start + timedelta(hours=2),
        )


def test_booking_with_registered_guest_is_charged(court_sand, member_user, guest_user):
    start = slot()
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
        participant_user_ids=[guest_user.pk],
    )
    assert booking.total_price == Decimal("5")
    assert booking.participants.get(user=guest_user).is_guest


def test_zero_guest_fee_is_respected(court_sand, member_user):
    PriceRule.objects.filter(
        court=court_sand, applies_to=PriceRule.AppliesTo.GUEST_OF_MEMBER
    ).update(price_per_person=0)
    start = slot()
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
        guest_names=["Gast"],
    )
    assert booking.total_price == 0


def test_booking_rejects_unknown_or_duplicate_participants(
    court_sand, member_user, guest_user
):
    start = slot()
    for ids in [[99999], [member_user.pk], [guest_user.pk, guest_user.pk]]:
        with pytest.raises(ValidationError):
            create_booking(
                court=court_sand,
                booked_by=member_user,
                start=start,
                end=start + timedelta(hours=1),
                participant_user_ids=ids,
            )
    assert not Booking.objects.exists()


def test_staff_without_court_role_cannot_cancel(court_sand, member_user, guest_user):
    start = slot()
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
    )
    guest_user.is_staff = True
    guest_user.save()
    with pytest.raises(ValidationError):
        cancel_booking(booking=booking, user=guest_user)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_stale_booking_cancellation_is_idempotent(court_sand, member_user):
    start = slot()
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=1),
    )
    stale = Booking.objects.get(pk=booking.pk)
    assert cancel_booking(booking=booking, user=member_user) is True
    assert cancel_booking(booking=stale, user=member_user) is False


def test_article_save_sanitizes_admin_edits():
    article = Article.objects.create(
        title="XSS", body='<p onclick="alert(1)">Text</p><script>alert(1)</script>'
    )
    article.refresh_from_db()
    assert "<script" not in article.body
    assert "onclick" not in article.body
    assert "<p>Text</p>" in article.body


def test_staff_without_editor_role_cannot_read_drafts(guest_user):
    guest_user.is_staff = True
    guest_user.save()
    article = Article.objects.create(title="Draft", body="Private")
    assert get_article_by_slug(article.slug, user=guest_user) is None


def test_category_counts_exclude_unpublished_and_private():
    category = Category.objects.create(name="News")
    Article.objects.create(
        title="Public", body="Text", category=category, status=Article.Status.PUBLISHED
    )
    Article.objects.create(
        title="Private",
        body="Text",
        category=category,
        status=Article.Status.PUBLISHED,
        visibility=Article.Visibility.MEMBERS,
    )
    Article.objects.create(title="Draft", body="Text", category=category)
    assert get_categories().get(pk=category.pk).article_count == 1


@pytest.mark.parametrize(
    "score",
    [
        [{"a": 6, "b": 0}] * 3,
        [{"a": 6, "b": 0}, {"a": 6, "b": 0}, {"a": 0, "b": 10}],
        [{"a": 6, "b": 0}] * 4,
        [{"a": "6", "b": 0}, {"a": 6, "b": 0}],
        [{"a": 6.5, "b": 0}, {"a": 6, "b": 0}],
        [None, {"a": 6, "b": 0}],
        {"a": 6, "b": 0},
    ],
)
def test_invalid_scores_return_validation_failure(score):
    valid, error = validate_tennis_score(score)
    assert valid is False
    assert error


def test_score_cannot_disagree_with_declared_winner(
    competition, member_user, guest_user
):
    a = Entry.objects.create(competition=competition, player1=member_user)
    b = Entry.objects.create(competition=competition, player1=guest_user)
    match = Match.objects.create(competition=competition, entry_a=a, entry_b=b)
    with pytest.raises(ValidationError):
        record_match_result(
            match=match, score=[{"a": 6, "b": 0}, {"a": 6, "b": 0}], winner=b
        )
    match.refresh_from_db()
    assert match.winner is None


@pytest.mark.parametrize(
    "status",
    [Tournament.Status.DRAFT, Tournament.Status.DRAWN, Tournament.Status.FINISHED],
)
def test_registration_rejects_closed_tournaments(competition, member_user, status):
    competition.tournament.status = status
    competition.tournament.save()
    with pytest.raises(ValidationError):
        register_for_competition(competition=competition, player1=member_user)
    assert not Entry.objects.exists()


def test_doubles_rejects_self_and_duplicate_partner(
    competition, member_user, member_user2
):
    competition.discipline = Competition.Discipline.DOUBLES
    competition.save()
    with pytest.raises(ValidationError):
        register_for_competition(
            competition=competition, player1=member_user, player2=member_user
        )
    register_for_competition(
        competition=competition, player1=member_user, player2=member_user2
    )
    with pytest.raises(ValidationError):
        register_for_competition(
            competition=competition, player1=member_user2, player2=member_user
        )
    assert Entry.objects.count() == 1


def test_schedule_rejects_negative_duration(competition, court_sand):
    match = Match.objects.create(competition=competition)
    with pytest.raises(ValidationError):
        schedule_tournament_match(
            match=match, court=court_sand, start_dt=slot(), duration_minutes=-90
        )
    assert not court_sand.blockings.exists()


def test_completed_draw_cannot_be_destroyed(competition, member_user, guest_user):
    Entry.objects.create(competition=competition, player1=member_user)
    Entry.objects.create(competition=competition, player1=guest_user)
    matches = generate_knockout_draw(competition)
    record_match_result(
        match=matches[0],
        score=[{"a": 6, "b": 0}, {"a": 6, "b": 0}],
        winner=matches[0].entry_a,
    )
    with pytest.raises(ValidationError):
        generate_knockout_draw(competition)
    assert Match.objects.filter(pk=matches[0].pk, winner__isnull=False).exists()


def test_reminders_are_not_sent_twice(court_sand, guest_user):
    now = timezone.now()
    Booking.objects.create(
        court=court_sand,
        booked_by=guest_user,
        start=now + timedelta(hours=24, minutes=30),
        end=now + timedelta(hours=25, minutes=30),
    )
    with patch("apps.courts.tasks.timezone.now", return_value=now):
        assert send_booking_reminders() == "Sent 1 reminders."
        assert send_booking_reminders() == "Sent 0 reminders."
    assert len(mail.outbox) == 1


def test_failed_reminder_is_not_counted(court_sand, guest_user):
    Booking.objects.create(
        court=court_sand,
        booked_by=guest_user,
        start=timezone.now() + timedelta(hours=24, minutes=30),
        end=timezone.now() + timedelta(hours=25, minutes=30),
    )
    with patch("apps.courts.tasks.send_mail", return_value=0):
        assert send_booking_reminders() == "Sent 0 reminders."


def test_booking_email_is_not_sent_on_rollback(
    court_sand, member_user, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                create_booking(
                    court=court_sand,
                    booked_by=member_user,
                    start=slot(),
                    end=slot() + timedelta(hours=1),
                )
                raise RuntimeError("Rollback")
    assert mail.outbox == []
    assert not Booking.objects.exists()


def test_admin_user_creation_hashes_password(client, admin_user):
    client.force_login(admin_user)
    url = reverse("admin:accounts_user_add")
    assert client.get(url).status_code == 200
    response = client.post(
        url,
        {
            "email": "admin-created@example.com",
            "first_name": "Test",
            "last_name": "User",
            "account_type": "GUEST",
            "usable_password": "true",
            "password1": "Uncommon789!secret",
            "password2": "Uncommon789!secret",
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="admin-created@example.com")
    assert user.check_password("Uncommon789!secret")


def test_gallery_png_is_stored_as_actual_jpeg_and_invalid_upload_leaves_no_files(
    settings,
):
    article = Article.objects.create(title="Gallery", body="Text")
    stream = io.BytesIO()
    Image.new("RGB", (1000, 900), "blue").save(stream, format="PNG")
    image = add_gallery_image(
        article=article,
        image_file=SimpleUploadedFile("picture.png", stream.getvalue()),
        alt_text="Bild",
    )
    for field in [image.image, image.image_medium, image.image_thumb]:
        with Image.open(field) as stored:
            assert stored.format == "JPEG"
    from pathlib import Path

    before = set(Path(settings.MEDIA_ROOT).rglob("*"))
    with pytest.raises(ValidationError):
        add_gallery_image(
            article=article,
            image_file=SimpleUploadedFile("bad.jpg", b"not an image"),
            alt_text="Bild",
        )
    assert set(Path(settings.MEDIA_ROOT).rglob("*")) == before


def test_draft_tournament_is_not_public(client, competition):
    competition.tournament.status = Tournament.Status.DRAFT
    competition.tournament.save()
    assert (
        client.get(
            reverse("tournaments:detail", args=[competition.tournament.slug])
        ).status_code
        == 404
    )


def test_invalid_competition_query_does_not_crash(client, competition):
    response = client.get(
        reverse("tournaments:detail", args=[competition.tournament.slug])
        + "?comp=bad-id"
    )
    assert response.status_code == 200


def test_repeat_membership_review_is_handled_in_view(client, admin_user, guest_user):
    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    application = MembershipApplication.objects.create(
        user=guest_user, requested_type=membership_type
    )
    client.force_login(admin_user)
    url = reverse("members:approve_application", args=[application.pk])
    assert client.post(url).status_code == 302
    assert client.post(url).status_code == 302
    assert Membership.objects.filter(user=guest_user).count() == 1


def test_fees_view_rejects_invalid_period(client, admin_user):
    client.force_login(admin_user)
    response = client.post(
        reverse("billing:run_fees"), {"year": "bad-year", "month": "13"}
    )
    assert response.status_code == 302
    assert not Charge.objects.exists()


def test_cancellation_redirect_rejects_external_host(client, court_sand, guest_user):
    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=slot(),
        end=slot() + timedelta(hours=1),
    )
    client.force_login(guest_user)
    response = client.post(
        reverse("courts:cancel", args=[booking.pk]),
        {"next": "https://attacker.example/"},
    )
    assert response.url == reverse("courts:calendar")


@pytest.mark.parametrize("method", ["get", "post"])
def test_payment_requires_cashier_permission(client, member_user, charge, method):
    client.force_login(member_user)
    response = getattr(client, method)(
        reverse("billing:record_payment", args=[charge.pk]), {"amount": "1"}
    )
    assert response.status_code == 403
    assert not charge.payments.exists()


def test_price_rules_respect_time_weekday_season_and_court(court_sand, guest_user):
    from apps.courts.models import Season
    from apps.billing.selectors import get_applicable_price_rule

    start = slot()
    season = Season.objects.create(
        name="Future",
        start_date=timezone.localdate() + timedelta(days=10),
        end_date=timezone.localdate() + timedelta(days=20),
    )
    PriceRule.objects.filter(
        court=court_sand, applies_to=PriceRule.AppliesTo.GUEST
    ).update(price_per_hour=17)
    PriceRule.objects.create(
        court=court_sand,
        applies_to=PriceRule.AppliesTo.GUEST,
        season=season,
        price_per_hour=99,
    )
    PriceRule.objects.create(
        court=court_sand,
        applies_to=PriceRule.AppliesTo.GUEST,
        time_from=time(12),
        time_to=time(15),
        price_per_hour=88,
    )
    PriceRule.objects.create(
        court=court_sand,
        applies_to=PriceRule.AppliesTo.GUEST,
        weekday_mask="0000000",
        price_per_hour=77,
    )
    assert (
        get_applicable_price_rule(
            court=court_sand, applies_to="GUEST", booking_time=start
        ).price_per_hour
        == 17
    )
    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=start,
        end=start + timedelta(hours=1),
    )
    assert booking.total_price == 17


def test_slot_price_change_is_applied(court_sand, guest_user):
    PriceRule.objects.create(
        court=court_sand,
        applies_to="GUEST",
        time_from=time(11),
        time_to=time(21),
        price_per_hour=30,
    )
    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=slot(),
        end=slot() + timedelta(hours=2),
    )
    assert booking.total_price == Decimal("45")


def test_case_insensitive_email_unique_constraint(guest_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(email=guest_user.email.upper())


def test_old_failed_attempts_do_not_accumulate_forever(guest_user):
    guest_user.failed_login_attempts = 4
    guest_user.last_failed_login_at = timezone.now() - timedelta(hours=1)
    guest_user.save()
    assert record_failed_login(guest_user.email) is False
    guest_user.refresh_from_db()
    assert guest_user.failed_login_attempts == 1


def test_quote_and_booking_have_identical_configured_prices(
    client, court_sand, member_user
):
    from apps.billing.models import BookingExtra

    PriceRule.objects.filter(court=court_sand, applies_to="GUEST_OF_MEMBER").update(
        price_per_person=8
    )
    extra = BookingExtra.objects.create(
        name="Light", price_member=3, price_guest=5, unit="PER_BOOKING", mode="OPTIONAL"
    )
    extra.courts.add(court_sand)
    start = slot()
    client.force_login(member_user)
    response = client.get(
        reverse("courts:quote"),
        {
            "court_id": court_sand.pk,
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
            "guest_names": "Gast",
            "extras": [extra.pk],
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == "11.00"
    assert not Booking.objects.exists()
    booking = create_booking(
        court=court_sand,
        booked_by=member_user,
        start=start,
        end=start + timedelta(hours=2),
        guest_names=["Gast"],
        selected_extra_ids=[extra.pk],
    )
    assert str(booking.total_price) == response.json()["total"]


@pytest.mark.parametrize(
    "params",
    [{"court_id": "bad"}, {"court_id": 99999}, {"start": "bad"}, {"extras": ["bad"]}],
)
def test_quote_rejects_invalid_parameters(client, court_sand, params):
    data = {
        "court_id": court_sand.pk,
        "start": slot().isoformat(),
        "end": (slot() + timedelta(hours=1)).isoformat(),
    }
    data.update(params)
    response = client.get(reverse("courts:quote"), data)
    assert response.status_code == 400
    assert not Booking.objects.exists()
    assert not Charge.objects.exists()


def test_zero_slot_duration_cannot_hang_calendar(court_sand):
    from apps.courts.selectors import get_court_slots_for_day

    OpeningHours.objects.filter(court=court_sand).update(slot_minutes=0)
    assert get_court_slots_for_day(court_sand, timezone.localdate()) == []


def test_closed_season_has_no_slots(court_sand):
    from apps.courts.models import Season
    from apps.courts.selectors import get_court_slots_for_day

    season = Season.objects.create(
        name="Closed",
        start_date=timezone.localdate() - timedelta(days=20),
        end_date=timezone.localdate() - timedelta(days=10),
    )
    OpeningHours.objects.filter(court=court_sand).update(season=season)
    assert get_court_slots_for_day(court_sand, timezone.localdate()) == []


def test_sepa_is_encrypted_in_database_and_supports_key_rotation(settings, guest_user):
    from django.db import connection

    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    old_key = settings.SECRET_KEY
    application = MembershipApplication.objects.create(
        user=guest_user, requested_type=membership_type, sepa_iban="AT1234567890"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sepa_iban FROM members_membershipapplication WHERE id = %s",
            [application.pk],
        )
        stored = cursor.fetchone()[0]
    assert stored.startswith("fernet:")
    assert "AT1234567890" not in stored
    settings.SECRET_KEY = "new-secret-key-for-rotation"
    settings.SECRET_KEY_FALLBACKS = [old_key]
    application.refresh_from_db()
    assert application.sepa_iban == "AT1234567890"
    settings.SECRET_KEY_FALLBACKS = []
    with pytest.raises(ValueError):
        application.refresh_from_db()


@pytest.mark.parametrize("month", [0, 13, "1", True])
def test_fee_run_rejects_invalid_month(month):
    with pytest.raises(ValueError):
        generate_membership_fees(year=2026, month=month)
    assert not Charge.objects.exists()


def test_admin_financial_edits_cannot_bypass_services(client, admin_user, charge):
    client.force_login(admin_user)
    assert client.get(reverse("admin:billing_payment_add")).status_code == 403
    assert client.get(reverse("admin:courts_booking_add")).status_code == 403
    response = client.post(
        reverse("admin:billing_charge_change", args=[charge.pk]),
        {"amount": "999", "status": "PAID", "_save": "Save"},
    )
    assert response.status_code == 403
    charge.refresh_from_db()
    assert charge.amount == 20
    assert charge.status == Charge.Status.OPEN


def test_role_permissions_are_specific(client, guest_user):
    from django.contrib.auth.models import Group

    guest_user.is_staff = True
    guest_user.save()
    guest_user.groups.add(Group.objects.get(name="Redakteur"))
    client.force_login(guest_user)
    assert client.get(reverse("admin:news_article_add")).status_code == 200
    assert client.get(reverse("admin:billing_charge_changelist")).status_code == 403


def test_partner_confirmation_and_withdrawal_endpoints(
    client, competition, member_user, member_user2, guest_user
):
    competition.discipline = Competition.Discipline.DOUBLES
    competition.save()
    competition.tournament.fee_member = 20
    competition.tournament.save()
    entry = register_for_competition(
        competition=competition, player1=member_user, player2=member_user2
    )
    fee = Charge.objects.get(user=member_user)
    client.force_login(guest_user)
    assert (
        client.post(reverse("tournaments:confirm_partner", args=[entry.pk])).status_code
        == 403
    )
    assert (
        client.post(reverse("tournaments:withdraw", args=[entry.pk])).status_code == 403
    )
    client.force_login(member_user2)
    assert (
        client.get(reverse("tournaments:confirm_partner", args=[entry.pk])).status_code
        == 405
    )
    assert (
        client.post(reverse("tournaments:confirm_partner", args=[entry.pk])).status_code
        == 302
    )
    entry.refresh_from_db()
    assert entry.status == Entry.Status.CONFIRMED
    response = client.get(
        reverse("tournaments:detail", args=[competition.tournament.slug])
    )
    assert response.context["user_entry"] == entry
    assert (
        client.post(reverse("tournaments:withdraw", args=[entry.pk])).status_code == 302
    )
    entry.refresh_from_db()
    fee.refresh_from_db()
    assert entry.status == Entry.Status.WITHDRAWN
    assert fee.status == Charge.Status.CANCELLED


def test_export_contains_history_and_payments_but_no_other_user_data(
    member_user, guest_user, charge
):
    from apps.accounts.services import export_user_data

    Membership.objects.filter(user=member_user).update(status=Membership.Status.ENDED)
    record_payment(charge=charge, amount=5)
    create_charge(
        user=guest_user,
        kind="OTHER",
        amount=10,
        due_date=timezone.localdate(),
        description="Other user secret",
    )
    data = export_user_data(member_user)
    assert data["memberships"][0]["status"] == Membership.Status.ENDED
    assert data["charges"][0]["payments"][0]["amount"] == "5.00"
    assert "Other user secret" not in str(data)


def test_retired_match_partial_set_is_not_counted_as_won(
    competition, member_user, guest_user
):
    from apps.tournaments.services import calculate_round_robin_standings

    a = Entry.objects.create(competition=competition, player1=member_user)
    b = Entry.objects.create(competition=competition, player1=guest_user)
    match = Match.objects.create(competition=competition, entry_a=a, entry_b=b)
    record_match_result(
        match=match,
        score=[{"a": 6, "b": 4}, {"a": 2, "b": 1}],
        winner=a,
        result_type="RETIRED",
    )
    leader = calculate_round_robin_standings(competition)[0]
    assert leader["won"] == 1
    assert leader["sets_won"] == 1


@pytest.mark.parametrize(
    "scores",
    [
        [{"a": 6, "b": 4}, {"a": 0, "b": 6}, {"a": 10, "b": 8}],
        [{"a": 0, "b": 6}, {"a": 6, "b": 4}, {"a": 9, "b": 11}],
    ],
)
def test_valid_three_set_scores(scores):
    assert validate_tennis_score(scores) == (True, None)


@pytest.mark.parametrize(
    "model_name",
    ["opening", "season", "price", "extra", "membership_type", "competition"],
)
def test_admin_configuration_rejects_invalid_values(court_sand, model_name):
    from apps.courts.models import Season
    from apps.billing.models import BookingExtra

    values = {
        "opening": OpeningHours(
            court=court_sand,
            weekday=0,
            open_time=time(8),
            close_time=time(20),
            slot_minutes=0,
        ),
        "season": Season(
            name="Bad",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() - timedelta(days=1),
        ),
        "price": PriceRule(weekday_mask="bad-mask", price_per_hour=1),
        "extra": BookingExtra(name="Bad", price_member=-1),
        "membership_type": MembershipType(name="Bad", fee_amount=-1),
        "competition": Competition(name="Bad", max_entries=0),
    }
    with pytest.raises(ValidationError):
        values[model_name].clean()


def test_price_boundary_inside_hour_slot_is_applied(court_sand, guest_user):
    PriceRule.objects.create(
        court=court_sand,
        applies_to="GUEST",
        time_from=time(10, 30),
        time_to=time(21),
        price_per_hour=30,
    )
    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=slot(),
        end=slot() + timedelta(hours=1),
    )
    assert booking.total_price == Decimal("22.50")


def test_existing_unsafe_article_is_sanitized_when_rendered(client):
    article = Article.objects.create(title="Legacy", body="Text", status="PUBLISHED")
    Article.objects.filter(pk=article.pk).update(
        body='<p>Text</p><script>alert("legacy-xss")</script>'
    )
    response = client.get(reverse("news:detail", args=[article.slug]))
    assert response.status_code == 200
    assert b"legacy-xss" not in response.content
    assert b"<p>Text</p>" in response.content


def test_admin_gallery_upload_generates_all_sizes(client, admin_user):
    from apps.news.models import ArticleImage

    client.force_login(admin_user)
    article = Article.objects.create(title="Admin gallery", body="Text")
    stream = io.BytesIO()
    Image.new("RGB", (1000, 900), "blue").save(stream, format="PNG")
    response = client.post(
        reverse("admin:news_articleimage_add"),
        {
            "article": article.pk,
            "image": SimpleUploadedFile("test.png", stream.getvalue()),
            "alt_text": "Bild",
            "caption": "",
            "order": 0,
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    image = ArticleImage.objects.get(article=article)
    for field in [image.image, image.image_medium, image.image_thumb]:
        with Image.open(field) as stored:
            assert stored.format == "JPEG"


def test_sepa_rotation_command_reencrypts_existing_values(settings, guest_user):
    from django.core.management import call_command

    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    application = MembershipApplication.objects.create(
        user=guest_user, requested_type=membership_type, sepa_iban="AT1234567890"
    )
    settings.SECRET_KEY_FALLBACKS = [settings.SECRET_KEY]
    settings.SECRET_KEY = "new-key-for-command"
    call_command("rotate_sepa_keys", stdout=io.StringIO())
    settings.SECRET_KEY_FALLBACKS = []
    application.refresh_from_db()
    assert application.sepa_iban == "AT1234567890"


def test_partner_application_expires_after_deadline(
    competition, member_user, member_user2
):
    from apps.tournaments.tasks import expire_pending_partners

    competition.discipline = Competition.Discipline.DOUBLES
    competition.save()
    competition.tournament.fee_member = 20
    competition.tournament.save()
    entry = register_for_competition(
        competition=competition, player1=member_user, player2=member_user2
    )
    competition.tournament.registration_deadline = timezone.now() - timedelta(seconds=1)
    competition.tournament.save()
    assert expire_pending_partners() == 1
    assert expire_pending_partners() == 0
    entry.refresh_from_db()
    assert entry.status == Entry.Status.WITHDRAWN
    assert Charge.objects.get(user=member_user).status == Charge.Status.CANCELLED


def test_invalid_audit_ip_and_mail_failure_are_handled(
    member_user, caplog, django_capture_on_commit_callbacks
):
    from apps.core.services import log_audit, send_mail_after_commit

    log = log_audit(
        user=member_user,
        action="TEST",
        entity_type="User",
        entity_id=member_user.pk,
        ip_address="malformed-ip",
    )
    assert log.ip_address is None
    with patch(
        "apps.core.services.send_mail", side_effect=RuntimeError("SMTP unavailable")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            send_mail_after_commit(
                subject="Test",
                message="Test",
                from_email="club@example.com",
                recipient_list=[member_user.email],
            )
    assert "nicht versendet" in caplog.text


def test_seed_command_refuses_production(settings):
    from django.core.management import call_command, CommandError

    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_data", stdout=io.StringIO())
    assert not User.objects.exists()


def test_price_change_requires_review_before_booking(court_sand, guest_user):
    PriceRule.objects.filter(court=court_sand, applies_to="GUEST").update(
        price_per_hour=20
    )
    with pytest.raises(ValidationError, match="Preis hat sich geändert"):
        create_booking(
            court=court_sand,
            booked_by=guest_user,
            start=slot(),
            end=slot() + timedelta(hours=1),
            expected_total=15,
        )
    assert not Booking.objects.exists()
    booking = create_booking(
        court=court_sand,
        booked_by=guest_user,
        start=slot(),
        end=slot() + timedelta(hours=1),
        expected_total=20,
    )
    assert booking.total_price == 20


@pytest.mark.parametrize(
    "value", ["bad-id", "", "-1", "99999999999999999999999999999999"]
)
def test_bad_court_identifiers_return_404(client, guest_user, value):
    client.force_login(guest_user)
    assert (
        client.post(
            reverse("courts:book"),
            {
                "court_id": value,
                "start": slot().isoformat(),
                "end": (slot() + timedelta(hours=1)).isoformat(),
            },
        ).status_code
        == 404
    )
    assert not Booking.objects.exists()


@pytest.mark.parametrize("third", ["nonsense", "6:4:extra", "6:-1"])
def test_result_view_does_not_ignore_malformed_sets(
    client, admin_user, competition, member_user, member_user2, third
):
    a = Entry.objects.create(competition=competition, player1=member_user)
    b = Entry.objects.create(competition=competition, player1=member_user2)
    match = Match.objects.create(competition=competition, entry_a=a, entry_b=b)
    client.force_login(admin_user)
    response = client.post(
        reverse("tournaments:match_result", args=[match.pk]),
        {"winner_id": a.pk, "set1": "6:4", "set2": "6:3", "set3": third},
    )
    assert response.status_code == 302
    match.refresh_from_db()
    assert match.winner is None


def test_correct_password_before_email_verification_does_not_lock_account(
    client, guest_user
):
    guest_user.email_verified = False
    guest_user.save()
    for attempt in range(6):
        assert (
            client.post(
                reverse("accounts:login"),
                {"email": guest_user.email, "password": "guestpassword123"},
            ).status_code
            == 200
        )
    guest_user.refresh_from_db()
    assert guest_user.failed_login_attempts == 0
    assert not guest_user.is_locked


def test_login_failure_window_counts_only_fifteen_minutes(guest_user):
    now = timezone.now()
    for minutes in [0, 4, 8, 12, 16]:
        with patch(
            "apps.accounts.services.timezone.now",
            return_value=now + timedelta(minutes=minutes),
        ):
            assert record_failed_login(guest_user.email) is False
    guest_user.refresh_from_db()
    assert guest_user.failed_login_attempts == 1


def test_unsupported_recurrence_is_not_silently_ignored(court_sand, admin_user):
    from apps.courts.services import create_blocking

    with pytest.raises(ValidationError, match="Wiederkehrende"):
        create_blocking(
            court=court_sand,
            start=slot(),
            end=slot() + timedelta(hours=1),
            created_by=admin_user,
            recurrence_rule="WEEKLY",
        )
    assert not court_sand.blockings.exists()


@pytest.mark.parametrize(
    "format", [Competition.Format.ROUND_ROBIN, Competition.Format.GROUPS_KO]
)
def test_knockout_draw_rejects_wrong_format(competition, format):
    competition.format = format
    competition.save()
    with pytest.raises(ValidationError):
        generate_knockout_draw(competition)
    assert not competition.matches.exists()


def test_schedule_endpoint_requires_role_and_preserves_old_blocking_on_conflict(
    client, competition, court_sand, guest_user, admin_user
):
    from apps.courts.models import Blocking

    match = Match.objects.create(competition=competition)
    url = reverse("tournaments:schedule_match", args=[match.pk])
    params = {"court_id": court_sand.pk, "start": slot().isoformat(), "duration": "90"}
    client.force_login(guest_user)
    assert client.post(url, params).status_code == 403
    client.force_login(admin_user)
    assert client.post(url, params).status_code == 302
    match.refresh_from_db()
    first = match.blocking_id
    Blocking.objects.create(court=court_sand, start=slot(hour=13), end=slot(hour=14))
    params["start"] = slot(hour=13).isoformat()
    assert client.post(url, params).status_code == 302
    match.refresh_from_db()
    assert match.blocking_id == first
    assert Blocking.objects.filter(pk=first).exists()


def test_top_seeds_get_byes(competition):
    for seed in range(1, 12):
        user = User.objects.create_user(email=f"bye{seed}@example.com")
        Entry.objects.create(
            competition=competition, player1=user, seed=seed if seed <= 5 else None
        )
    matches = generate_knockout_draw(competition)
    assert sorted(
        match.winner.seed for match in matches if match.round == 1 and match.winner
    ) == [1, 2, 3, 4, 5]


def test_manual_membership_in_admin_updates_account_rights(
    client, admin_user, guest_user
):
    membership_type = MembershipType.objects.create(name="Adult", fee_amount=10)
    client.force_login(admin_user)
    response = client.post(
        reverse("admin:members_membership_add"),
        {
            "user": guest_user.pk,
            "type": membership_type.pk,
            "member_number": "TCM-0100",
            "start_date": timezone.localdate().isoformat(),
            "end_date": "",
            "status": "ACTIVE",
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    guest_user.refresh_from_db()
    assert is_member(guest_user)


def test_manual_charge_in_admin_uses_validated_service(client, admin_user, guest_user):
    from apps.core.models import AuditLog

    client.force_login(admin_user)
    url = reverse("admin:billing_charge_add")
    page = client.get(url)
    assert page.status_code == 200
    data = {
        "user": guest_user.pk,
        "kind": "OTHER",
        "amount": "12.50",
        "due_date": timezone.localdate().isoformat(),
        "description": "Manual fee",
        "_save": "Save",
    }
    for inline in page.context["inline_admin_formsets"]:
        prefix = inline.formset.prefix
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "0",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    invalid = client.post(url, {**data, "amount": "-1"})
    assert invalid.status_code == 200
    assert not Charge.objects.exists()
    response = client.post(url, data)
    assert response.status_code == 302
    assert Charge.objects.get(user=guest_user).amount == Decimal("12.50")
    assert AuditLog.objects.filter(action="CREATE_CHARGE").exists()


def test_waiver_preserves_paid_charges_and_requires_role(
    charge, admin_user, guest_user
):
    from apps.billing.services import waive_charge
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        waive_charge(charge=charge, actor=guest_user, reason="No permission")
    record_payment(charge=charge, amount=5)
    with pytest.raises(ValueError):
        waive_charge(charge=charge, actor=admin_user, reason="Paid charge")
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PARTIAL
    assert charge.total_paid == 5


def test_admin_waiver_uses_service(client, charge, admin_user):
    from apps.core.models import AuditLog

    client.force_login(admin_user)
    response = client.post(
        reverse("admin:billing_charge_changelist"),
        {"action": "waive_open_charges", "_selected_action": [charge.pk], "index": "0"},
    )
    assert response.status_code == 302
    charge.refresh_from_db()
    assert charge.status == Charge.Status.WAIVED
    assert AuditLog.objects.filter(action="WAIVE_CHARGE", user=admin_user).exists()
