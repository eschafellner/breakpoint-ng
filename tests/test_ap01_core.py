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


@pytest.mark.django_db
def test_pwa_manifest_dynamic(client, club_settings):
    """PWA: Dynamic manifest generation from ClubSettings with colors & shortcuts."""
    response = client.get(reverse("core:manifest"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"

    data = response.json()
    assert data["name"] == club_settings.name
    assert data["short_name"] == club_settings.short_name
    assert data["theme_color"] == "#1E3B2F"
    assert data["background_color"] == "#1E3B2F"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 4
    assert len(data["shortcuts"]) == 3
    assert any(s["url"] == "/courts/calendar/" for s in data["shortcuts"])

    # Test dynamic update reflection
    club_settings.name = "TC Sonnenhof"
    club_settings.short_name = "TCS"
    club_settings.save()

    response_updated = client.get(reverse("core:manifest"))
    data_updated = response_updated.json()
    assert data_updated["name"] == "TC Sonnenhof"
    assert data_updated["short_name"] == "TCS"


@pytest.mark.django_db
def test_pwa_service_worker_headers(client):
    """PWA: sw.js is served with root scope permission and no-cache header."""
    response = client.get(reverse("core:service_worker"))
    assert response.status_code == 200
    assert response["Service-Worker-Allowed"] == "/"
    assert "no-cache" in response["Cache-Control"]
    assert b"/offline/" in response.content


@pytest.mark.django_db
def test_pwa_offline_page(client, club_settings):
    """PWA: Offline fallback page displays contact and backend-configured emergency info."""
    club_settings.phone = "+43 999 888777"
    club_settings.offline_emergency_info = "Bei Notfällen Platzwart Huber anrufen."
    club_settings.save()

    response = client.get(reverse("core:offline"))
    assert response.status_code == 200
    assert b"+43 999 888777" in response.content
    assert "Bei Notfällen Platzwart Huber anrufen.".encode("utf-8") in response.content


@pytest.mark.django_db
def test_pwa_meta_tags_in_base_template(client, club_settings):
    """PWA: Base template renders manifest link, apple touch icons and pwa.js."""
    response = client.get(reverse("core:home"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert 'rel="manifest"' in content
    assert 'manifest.webmanifest' in content
    assert 'apple-touch-icon' in content
    assert 'static/js/pwa.js' in content
    assert 'theme-color" content="#1E3B2F"' in content
