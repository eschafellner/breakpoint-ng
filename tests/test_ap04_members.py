import json
import pytest
from datetime import date, timedelta
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import export_user_data
from apps.core.models import AuditLog
from apps.members.models import Membership, MembershipApplication, MembershipType
from apps.members.services import (
    approve_application,
    reject_application,
    import_members_from_csv,
    end_expired_memberships,
)

@pytest.mark.django_db
def test_application_approval_flow(admin_user):
    """
    AP-04:
    - Freischalten erzeugt Membership mit fortlaufender Mitgliedsnummer.
    - setzt account_type=MEMBER.
    - versendet E-Mail.
    - Audit-Log-Eintrag.
    """
    m_type = MembershipType.objects.create(name="Erwachsener", fee_amount=200)
    applicant = User.objects.create_user(
        email="antrag@test.at",
        password="password123",
        first_name="Hannes",
        last_name="Antrag",
        account_type=User.AccountType.GUEST,
    )
    application = MembershipApplication.objects.create(
        user=applicant,
        requested_type=m_type,
        status=MembershipApplication.Status.PENDING,
    )

    mail.outbox.clear()
    membership = approve_application(application=application, reviewer=admin_user)

    assert membership.member_number.startswith("TCM-")
    assert membership.status == Membership.Status.ACTIVE
    assert membership.type == m_type

    applicant.refresh_from_db()
    assert applicant.account_type == User.AccountType.MEMBER

    application.refresh_from_db()
    assert application.status == MembershipApplication.Status.APPROVED
    assert application.reviewed_by == admin_user

    # Email sent
    assert len(mail.outbox) >= 1
    assert "genehmigt" in mail.outbox[0].subject.lower()

    # Audit log
    assert AuditLog.objects.filter(action="APPROVE_MEMBERSHIP_APPLICATION").exists()

@pytest.mark.django_db
def test_application_rejection_requires_reason(admin_user):
    """AP-04: Ablehnen erfordert Begründung und versendet E-Mail."""
    m_type = MembershipType.objects.create(name="Jugend", fee_amount=80)
    applicant = User.objects.create_user(
        email="abgelehnt@test.at",
        password="password123",
        first_name="Paul",
        last_name="Pech",
        account_type=User.AccountType.GUEST,
    )
    application = MembershipApplication.objects.create(
        user=applicant,
        requested_type=m_type,
        status=MembershipApplication.Status.PENDING,
    )

    # Missing reason raises ValueError
    with pytest.raises(ValueError):
        reject_application(application=application, reviewer=admin_user, reason="")

    mail.outbox.clear()
    reject_application(
        application=application,
        reviewer=admin_user,
        reason="Aufnahmestopp für die Altersklasse.",
    )

    application.refresh_from_db()
    assert application.status == MembershipApplication.Status.REJECTED
    assert application.rejection_reason == "Aufnahmestopp für die Altersklasse."

    # Email sent with reason
    assert len(mail.outbox) >= 1
    assert "Aufnahmestopp" in mail.outbox[0].body

@pytest.mark.django_db
def test_csv_import_handles_valid_and_invalid_rows(admin_user):
    """AP-04: CSV-Import legt Mitglieder an und meldet fehlerhafte Zeilen, ohne abzubrechen."""
    MembershipType.objects.create(name="Erwachsener", fee_amount=200)

    csv_data = (
        "email,first_name,last_name,phone,membership_type\n"
        "neu1@club.at,Bernd,Bauer,+4312345,Erwachsener\n"
        "neu2@club.at,Carla,Chef,,UnbekannteArt\n"  # Invalid type
        "neu3@club.at,David,Dachs,+4399999,Erwachsener\n"
    )

    res = import_members_from_csv(csv_data, reviewer=admin_user)
    assert res["created"] == 2
    assert len(res["errors"]) == 1
    assert res["errors"][0]["line"] == 3
    assert "UnbekannteArt" in res["errors"][0]["error"]

    assert User.objects.filter(email="neu1@club.at", account_type=User.AccountType.MEMBER).exists()
    assert User.objects.filter(email="neu3@club.at", account_type=User.AccountType.MEMBER).exists()

@pytest.mark.django_db
def test_end_expired_memberships_task():
    """AP-04: Austritt mit Enddatum: nach Enddatum verliert Nutzer Mitgliederrechte."""
    m_type = MembershipType.objects.create(name="Student", fee_amount=100)
    user = User.objects.create_user(
        email="alt@test.at",
        password="password123",
        first_name="Otto",
        last_name="Alt",
        account_type=User.AccountType.MEMBER,
    )
    yesterday = timezone.now().date() - timedelta(days=1)
    Membership.objects.create(
        user=user,
        type=m_type,
        member_number="TCM-9999",
        start_date=yesterday - timedelta(days=365),
        end_date=yesterday,
        status=Membership.Status.ACTIVE,
    )

    count = end_expired_memberships()
    assert count == 1

    user.refresh_from_db()
    assert user.account_type == User.AccountType.GUEST

@pytest.mark.django_db
def test_member_directory_permissions(client, member_user, guest_user):
    """
    AP-04 / M-12a:
    - Mitgliederliste für aktive Mitglieder erreichbar.
    - Gast / Besucher erhalten keinen Zugriff (HTTP 403 bzw. Weiterleitung zum Login).
    """
    # 1. Anonymous visitor -> redirect to login
    resp_anon = client.get(reverse("members:directory"))
    assert resp_anon.status_code == 302
    assert "login" in resp_anon.url

    # 2. Guest user -> HTTP 403 Forbidden
    client.force_login(guest_user)
    resp_guest = client.get(reverse("members:directory"))
    assert resp_guest.status_code == 403

    # 3. Active member -> HTTP 200 OK
    client.force_login(member_user)
    resp_member = client.get(reverse("members:directory"))
    assert resp_member.status_code == 200
    assert member_user.email.encode() in resp_member.content

@pytest.mark.django_db
def test_gdpr_json_data_export(member_user):
    """AP-04 / M-14: Nutzer kann eigenen Datenexport (JSON) herunterladen."""
    data = export_user_data(member_user)
    assert data["email"] == member_user.email
    assert data["account_type"] == "MEMBER"
    assert "membership" in data
    assert data["membership"]["member_number"] == "TCM-0001"
