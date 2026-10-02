import io
import pytest
from datetime import timedelta
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from apps.news.models import Article, ArticleImage, Category
from apps.news.services import create_article, add_gallery_image, sanitize_html
from apps.news.selectors import get_published_articles

def create_test_image(color="blue", size=(1000, 1000)):
    f = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(f, format="JPEG")
    f.seek(0)
    return SimpleUploadedFile("test.jpg", f.read(), content_type="image/jpeg")

@pytest.mark.django_db
def test_article_creation_with_gallery_images_3_sizes(admin_user):
    """AP-03: Artikel mit Titelbild und Galeriebildern; Bilder in 3 Größen erzeugt."""
    cover = create_test_image(color="green")
    article = create_article(
        title="Saisoneröffnung 2027",
        body="<p>Willkommen zur neuen Saison!</p>",
        teaser="Vorschau auf die Saison",
        cover_image=cover,
        cover_image_alt="Sandplatz in der Morgensonne",
        author=admin_user,
    )
    assert article.cover_image
    assert article.cover_image_alt == "Sandplatz in der Morgensonne"

    # Add 3 gallery images
    for i in range(3):
        img_file = create_test_image(color="red", size=(1200, 900))
        g_img = add_gallery_image(
            article=article,
            image_file=img_file,
            alt_text=f"Spielszene {i+1}",
            caption=f"Foto {i+1}",
        )
        assert g_img.image  # Original
        assert g_img.image_medium  # 800x600 medium
        assert g_img.image_thumb  # 300x200 thumb

@pytest.mark.django_db
def test_upload_without_alt_text_rejected(admin_user):
    """AP-03: Upload ohne Alt-Text wird abgelehnt."""
    article = create_article(
        title="Testartikel",
        body="Text",
        author=admin_user,
    )
    img_file = create_test_image()
    with pytest.raises(ValidationError):
        add_gallery_image(
            article=article,
            image_file=img_file,
            alt_text="",  # Empty alt text must be rejected
        )

@pytest.mark.django_db
def test_scheduled_publishing(admin_user):
    """AP-03: Artikel mit publish_at in der Zukunft öffentlich nicht sichtbar, danach schon."""
    now = timezone.now()
    future_article = create_article(
        title="Zukunfts-News",
        body="Geheim",
        author=admin_user,
        publish_at=now + timedelta(days=2),
    )
    past_article = create_article(
        title="Aktuelle News",
        body="Bereits da",
        author=admin_user,
        publish_at=now - timedelta(hours=1),
    )

    published = list(get_published_articles())
    assert past_article in published
    assert future_article not in published

@pytest.mark.django_db
def test_members_only_article_visibility(client, admin_user, guest_user, member_user):
    """AP-03: Artikel „nur Mitglieder“ ist für Gäste/Besucher nicht sichtbar (404)."""
    members_article = create_article(
        title="Internes Vereinstreffen",
        body="Nur für Mitglieder!",
        author=admin_user,
        visibility=Article.Visibility.MEMBERS,
        status=Article.Status.PUBLISHED,
    )

    # Visitor (anonymous) -> 404
    resp_anon = client.get(reverse("news:detail", kwargs={"slug": members_article.slug}))
    assert resp_anon.status_code == 404

    # Guest user -> 404
    client.force_login(guest_user)
    resp_guest = client.get(reverse("news:detail", kwargs={"slug": members_article.slug}))
    assert resp_guest.status_code == 404

    # Member user -> 200
    client.force_login(member_user)
    resp_member = client.get(reverse("news:detail", kwargs={"slug": members_article.slug}))
    assert resp_member.status_code == 200
    assert b"Internes Vereinstreffen" in resp_member.content

@pytest.mark.django_db
def test_html_sanitizing_in_article_body():
    """AP-03: HTML im Body wird sanitisiert (kein <script>)."""
    malicious = '<p>Hallo!</p><script>alert("hacked")</script><img src="x" onerror="alert(1)">'
    clean = sanitize_html(malicious)
    assert "<script>" not in clean
    assert "alert" not in clean
    assert "<p>Hallo!</p>" in clean

@pytest.mark.django_db
def test_rss_feed_contains_only_public_published_articles(client, admin_user):
    """AP-03: RSS-Feed enthält nur öffentliche, veröffentlichte Artikel."""
    public_art = create_article(
        title="Öffentlicher Post",
        body="Öffentlich",
        author=admin_user,
        visibility=Article.Visibility.PUBLIC,
    )
    private_art = create_article(
        title="Privater Post",
        body="Nur Mitglieder",
        author=admin_user,
        visibility=Article.Visibility.MEMBERS,
    )

    resp = client.get(reverse("news:feed"))
    assert resp.status_code == 200
    assert b"<![CDATA[\xc3\x96ffentlicher Post]]>" in resp.content or b"\xc3\x96ffentlicher Post" in resp.content or "Öffentlicher Post".encode("utf-8") in resp.content
    assert "Privater Post".encode("utf-8") not in resp.content
