import pytest
from datetime import date, time
from decimal import Decimal
from apps.accounts.models import User
from apps.core.models import ClubSettings
from apps.courts.models import Court, OpeningHours
from apps.billing.models import PriceRule, BookingExtra
from apps.members.models import MembershipType, Membership


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def club_settings(db):
    settings = ClubSettings.get_settings()
    settings.name = "TC Musterdorf"
    settings.advance_days_member = 7
    settings.advance_days_guest = 2
    settings.max_open_bookings = 2
    settings.max_duration_minutes = 120
    settings.free_cancel_hours = 4
    settings.prorated_membership_fees = True
    settings.save()
    return settings


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        email="admin@tc-musterdorf.at",
        password="adminpassword123",
        first_name="Admin",
        last_name="Vorstand",
    )
    return user


@pytest.fixture
def member_user(db):
    user = User.objects.create_user(
        email="mitglied@tc-musterdorf.at",
        password="memberpassword123",
        first_name="Max",
        last_name="Mustermann",
        account_type=User.AccountType.MEMBER,
        email_verified=True,
    )
    m_type, _ = MembershipType.objects.get_or_create(
        name="Erwachsener",
        defaults={
            "fee_amount": Decimal("180.00"),
            "billing_interval": MembershipType.BillingInterval.YEARLY,
        },
    )
    Membership.objects.create(
        user=user,
        type=m_type,
        member_number="TCM-0001",
        start_date=date(2020, 1, 1),
        status=Membership.Status.ACTIVE,
    )
    return user


@pytest.fixture
def member_user2(db, member_user):
    user = User.objects.create_user(
        email="mitglied2@tc-musterdorf.at",
        password="memberpassword123",
        first_name="Erika",
        last_name="Musterfrau",
        account_type=User.AccountType.MEMBER,
        email_verified=True,
    )
    m_type = MembershipType.objects.first()
    Membership.objects.create(
        user=user,
        type=m_type,
        member_number="TCM-0002",
        start_date=date(2020, 1, 1),
        status=Membership.Status.ACTIVE,
    )
    return user


@pytest.fixture
def guest_user(db):
    return User.objects.create_user(
        email="gast@example.com",
        password="guestpassword123",
        first_name="Gustav",
        last_name="Gast",
        account_type=User.AccountType.GUEST,
        email_verified=True,
    )


@pytest.fixture
def court_sand(db):
    court = Court.objects.create(
        name="Platz 1",
        surface=Court.Surface.SAND,
        is_indoor=False,
        has_floodlight=True,
        is_active=True,
        order=1,
    )
    for w in range(7):
        OpeningHours.objects.create(
            court=court,
            weekday=w,
            open_time=time(8, 0),
            close_time=time(21, 0),
            slot_minutes=60,
        )
    # Price rules: Guest 15€/h, Guest of member 5€/person
    PriceRule.objects.create(
        court=court,
        applies_to=PriceRule.AppliesTo.GUEST,
        price_per_hour=Decimal("15.00"),
    )
    PriceRule.objects.create(
        court=court,
        applies_to=PriceRule.AppliesTo.GUEST_OF_MEMBER,
        price_per_person=Decimal("5.00"),
    )
    return court


@pytest.fixture
def court_halle(db):
    court = Court.objects.create(
        name="Halle 1",
        surface=Court.Surface.HALLE,
        is_indoor=True,
        has_floodlight=True,
        is_active=True,
        order=2,
    )
    for w in range(7):
        OpeningHours.objects.create(
            court=court,
            weekday=w,
            open_time=time(8, 0),
            close_time=time(22, 0),
            slot_minutes=60,
        )
    # Extra for Halle: automatic 10€
    BookingExtra.objects.create(
        name="Hallengebühr",
        price_member=Decimal("10.00"),
        price_guest=Decimal("15.00"),
        unit=BookingExtra.Unit.PER_HOUR,
        mode=BookingExtra.Mode.AUTOMATIC,
        is_active=True,
    )
    return court
