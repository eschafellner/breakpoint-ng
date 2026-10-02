import pytest
from datetime import date
from decimal import Decimal
from apps.accounts.models import User
from apps.billing.models import Charge, Payment
from apps.billing.services import (
    create_charge,
    record_payment,
    generate_membership_fees,
    quantize_amount,
)
from apps.billing.selectors import get_user_charges
from apps.members.models import Membership, MembershipType

@pytest.mark.django_db
def test_membership_fee_run_idempotency(member_user, member_user2):
    """
    AP-05:
    - Beitragslauf erzeugt pro aktivem Jahresmitglied genau eine Forderung.
    - Zweiter Lauf erzeugt keine Duplikate (idempotent).
    """
    year = 2027
    charges1 = generate_membership_fees(year=year)
    assert len(charges1) == 2

    # Second run for same year must create 0 new charges
    charges2 = generate_membership_fees(year=year)
    assert len(charges2) == 0

    assert Charge.objects.filter(period_start__year=year).count() == 2

@pytest.mark.django_db
def test_monthly_membership_fee_run():
    """AP-05: Monatsmitglieder erhalten 12 Forderungen pro Jahr bzw. eine pro Monatslauf."""
    m_type = MembershipType.objects.create(
        name="Monatszahler",
        fee_amount=Decimal("20.00"),
        billing_interval=MembershipType.BillingInterval.MONTHLY,
    )
    user = User.objects.create_user(
        email="monat@test.at",
        password="pass",
        first_name="Monika",
        last_name="Monat",
        account_type=User.AccountType.MEMBER,
    )
    Membership.objects.create(
        user=user,
        type=m_type,
        member_number="TCM-M01",
        start_date=date(2027, 1, 1),
        status=Membership.Status.ACTIVE,
    )

    # Full year run for monthly member -> 12 charges
    charges = generate_membership_fees(year=2027)
    assert len(charges) == 12

    # Rerun for same year -> 0
    assert len(generate_membership_fees(year=2027)) == 0

@pytest.mark.django_db
def test_prorated_fee_calculation(club_settings):
    """AP-05: Eintritt am 1. Juli bei aktivierter Anteiligkeit -> 50 % des Jahresbeitrags."""
    club_settings.prorated_membership_fees = True
    club_settings.save()

    m_type = MembershipType.objects.create(
        name="Jahreszahler",
        fee_amount=Decimal("240.00"),
        billing_interval=MembershipType.BillingInterval.YEARLY,
    )
    user = User.objects.create_user(
        email="juli@test.at",
        password="pass",
        first_name="Julian",
        last_name="Juli",
        account_type=User.AccountType.MEMBER,
    )
    # Starts July 1st -> 6 months remaining in year -> 50% of 240 = 120.00 €
    Membership.objects.create(
        user=user,
        type=m_type,
        member_number="TCM-JULI",
        start_date=date(2027, 7, 1),
        status=Membership.Status.ACTIVE,
    )

    charges = generate_membership_fees(year=2027)
    assert len(charges) == 1
    assert charges[0].amount == Decimal("120.00")

@pytest.mark.django_db
def test_partial_and_full_payment(member_user, admin_user):
    """AP-05: Teilzahlung setzt Status PARTIAL; Restzahlung setzt PAID."""
    charge = create_charge(
        user=member_user,
        kind=Charge.Kind.MEMBERSHIP_FEE,
        amount=Decimal("150.00"),
        due_date=date(2027, 1, 15),
        description="Jahresbeitrag 2027",
    )
    assert charge.status == Charge.Status.OPEN

    # 1. Partial payment of 50 €
    p1 = record_payment(
        charge=charge,
        amount=Decimal("50.00"),
        method=Payment.Method.TRANSFER,
        recorded_by=admin_user,
    )
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PARTIAL
    assert charge.total_paid == Decimal("50.00")
    assert charge.open_amount == Decimal("100.00")

    # 2. Remaining payment of 100 €
    p2 = record_payment(
        charge=charge,
        amount=Decimal("100.00"),
        method=Payment.Method.CASH,
        recorded_by=admin_user,
    )
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert charge.total_paid == Decimal("150.00")
    assert charge.open_amount == Decimal("0.00")

@pytest.mark.django_db
def test_decimal_rounding_cases(member_user):
    """AP-05: Alle Beträge Decimal; Test mit Rundungsfällen (z. B. 100 € / 3)."""
    raw_amount = Decimal("100.00") / Decimal("3")
    quantized = quantize_amount(raw_amount)
    assert quantized == Decimal("33.33")

    charge = create_charge(
        user=member_user,
        kind=Charge.Kind.OTHER,
        amount=raw_amount,
        due_date=date(2027, 2, 1),
        description="Rundungstest",
    )
    assert charge.amount == Decimal("33.33")

@pytest.mark.django_db
def test_member_sees_only_own_charges(member_user, guest_user):
    """AP-05: Mitglied sieht nur eigene Forderungen."""
    c1 = create_charge(user=member_user, kind=Charge.Kind.MEMBERSHIP_FEE, amount=Decimal("100"), due_date=date(2027, 1, 1), description="Mem charge")
    c2 = create_charge(user=guest_user, kind=Charge.Kind.COURT_FEE, amount=Decimal("20"), due_date=date(2027, 1, 1), description="Guest charge")

    member_charges = list(get_user_charges(member_user))
    assert c1 in member_charges
    assert c2 not in member_charges
