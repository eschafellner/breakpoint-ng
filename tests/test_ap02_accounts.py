import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from apps.accounts.models import User
from apps.accounts.services import (
    register_user,
    verify_email,
    record_failed_login,
    reset_failed_logins,
)
from apps.members.models import MembershipType, MembershipApplication

@pytest.mark.django_db
def test_standard_groups_exist_automatically():
    """AP-02: Gruppen existieren nach migrate automatisch."""
    expected = ["Redakteur", "Platzwart", "Kassier", "Turnierleiter", "Administrator"]
    for role in expected:
        assert Group.objects.filter(name=role).exists(), f"Group {role} missing"

@pytest.mark.django_db
def test_guest_registration_and_email_verification(client):
    """
    AP-02:
    - Nutzer kann sich als Gast registrieren.
    - Ohne bestätigte E-Mail kein Login.
    - Nach E-Mail-Bestätigung ist Login möglich.
    """
    user = register_user(
        email="neu-gast@example.com",
        password="securepassword123",
        first_name="Felix",
        last_name="Neugast",
        account_type=User.AccountType.GUEST,
    )
    assert not user.email_verified
    assert user.email_verification_token

    # 1. Attempt login before verification -> must fail
    resp = client.post(reverse("accounts:login"), {
        "email": "neu-gast@example.com",
        "password": "securepassword123",
    })
    assert resp.status_code == 200
    assert not resp.context["user"].is_authenticated

    # 2. Verify email via token
    verified_user = verify_email(user.email_verification_token)
    assert verified_user is not None
    assert verified_user.email_verified

    # 3. Attempt login after verification -> must succeed
    resp_success = client.post(reverse("accounts:login"), {
        "email": "neu-gast@example.com",
        "password": "securepassword123",
    }, follow=True)
    assert resp_success.status_code == 200
    assert resp_success.context["user"].is_authenticated

@pytest.mark.django_db
def test_member_application_on_registration():
    """AP-02: Wählt Nutzer „Mitgliedschaft beantragen“, entsteht eine MembershipApplication mit Status PENDING."""
    m_type = MembershipType.objects.create(name="Erwachsener", fee_amount=150)
    user = register_user(
        email="antragsteller@example.com",
        password="securepassword123",
        first_name="Klara",
        last_name="Wartend",
        account_type=User.AccountType.MEMBER,
        apply_membership_type_id=m_type.id,
        sepa_iban="AT1234567890",
    )
    app = MembershipApplication.objects.filter(user=user).first()
    assert app is not None
    assert app.status == MembershipApplication.Status.PENDING
    assert app.requested_type == m_type
    assert app.sepa_iban == "AT1234567890"

@pytest.mark.django_db
def test_rate_limiting_locks_account_after_5_failed_logins(client):
    """AP-02: Nach 5 fehlgeschlagenen Logins in 15 Min. wird gesperrt."""
    user = User.objects.create_user(
        email="target@example.com",
        password="correctpassword123",
        first_name="Target",
        last_name="User",
        email_verified=True,
    )

    for i in range(4):
        record_failed_login("target@example.com")
        user.refresh_from_db()
        assert not user.is_locked

    # 5th attempt locks account
    is_locked = record_failed_login("target@example.com")
    user.refresh_from_db()
    assert is_locked
    assert user.is_locked
    assert user.locked_until is not None

    # Login attempt while locked fails even with correct password
    resp = client.post(reverse("accounts:login"), {
        "email": "target@example.com",
        "password": "correctpassword123",
    })
    assert not resp.context["user"].is_authenticated

    # Resetting unlocks
    reset_failed_logins(user)
    user.refresh_from_db()
    assert not user.is_locked
