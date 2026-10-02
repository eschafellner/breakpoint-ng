import pytest
from django.urls import reverse
from apps.core.models import ClubSettings
from apps.core.services import log_audit

@pytest.mark.django_db
def test_home_page_accessible(client, club_settings):
    """AP-01: Startseite erreichbar und liefert Status 200."""
    response = client.get(reverse("core:home"))
    assert response.status_code == 200
    assert club_settings.name.encode() in response.content

@pytest.mark.django_db
def test_club_settings_singleton_and_context(client, club_settings):
    """AP-01: ClubSettings im Admin/DB editierbar und im Template Kontext verfügbar."""
    s1 = ClubSettings.get_settings()
    s1.name = "TC Antigravity"
    s1.save()

    s2 = ClubSettings.get_settings()
    assert s2.name == "TC Antigravity"
    assert ClubSettings.objects.count() == 1

    response = client.get(reverse("core:home"))
    assert b"TC Antigravity" in response.content

@pytest.mark.django_db
def test_imprint_and_privacy_pages(client, club_settings):
    """AP-01: Impressum und Datenschutz mit ClubSettings Texten."""
    resp_imp = client.get(reverse("core:imprint"))
    assert resp_imp.status_code == 200
    assert b"Impressum" in resp_imp.content

    resp_priv = client.get(reverse("core:privacy"))
    assert resp_priv.status_code == 200
    assert b"Datenschutz" in resp_priv.content

@pytest.mark.django_db
def test_real_ip_middleware(client):
    """AP-01 / AP-10: Cloudflare CF-Connecting-IP header is properly recognized."""
    response = client.get(reverse("core:home"), HTTP_CF_CONNECTING_IP="198.51.100.42")
    assert response.status_code == 200
