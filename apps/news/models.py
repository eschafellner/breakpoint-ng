from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel

class Category(TimeStampedModel):
    name = models.CharField(_("Kategoriename"), max_length=100)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True)

    class Meta:
        verbose_name = _("News-Kategorie")
        verbose_name_plural = _("News-Kategorien")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Article(TimeStampedModel):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", _("Öffentlich")
        MEMBERS = "MEMBERS", _("Nur Mitglieder")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Entwurf")
        PUBLISHED = "PUBLISHED", _("Veröffentlicht")
        ARCHIVED = "ARCHIVED", _("Archiviert")

    title = models.CharField(_("Titel"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True, blank=True)
    teaser = models.TextField(_("Teaser / Vorschautext"), blank=True)
    body = models.TextField(_("Inhalt (HTML)"))
    
    cover_image = models.ImageField(_("Titelbild"), upload_to="news/covers/", null=True, blank=True)
    cover_image_alt = models.CharField(_("Alt-Text für Titelbild"), max_length=255, blank=True)
    
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Kategorie"),
    )
    visibility = models.CharField(
        _("Sichtbarkeit"),
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    publish_at = models.DateTimeField(_("Veröffentlichungsdatum"), default=timezone.now)
    is_pinned = models.BooleanField(_("Oben anheften (Sticky)"), default=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Autor"),
    )

    class Meta:
        verbose_name = _("Artikel")
        verbose_name_plural = _("Artikel")
        ordering = ["-is_pinned", "-publish_at"]

    def __str__(self):
        return f"{self.title} [{self.get_status_display()}]"

    def clean(self):
        if self.cover_image and not self.cover_image_alt:
            raise ValidationError({"cover_image_alt": _("Ein Alt-Text ist für das Titelbild verpflichtend (Barrierefreiheit).")})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "artikel"
            candidate = base_slug
            idx = 1
            while Article.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{idx}"
                idx += 1
            self.slug = candidate
        self.clean()
        super().save(*args, **kwargs)

class ArticleImage(TimeStampedModel):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        verbose_name=_("Artikel"),
    )
    image = models.ImageField(_("Originalbild (Groß)"), upload_to="news/gallery/large/")
    image_medium = models.ImageField(_("Mittelgroßes Bild"), upload_to="news/gallery/medium/", blank=True)
    image_thumb = models.ImageField(_("Vorschaubild (Thumbnail)"), upload_to="news/gallery/thumbs/", blank=True)
    alt_text = models.CharField(_("Alt-Text"), max_length=255)
    caption = models.CharField(_("Bildunterschrift"), max_length=255, blank=True)
    order = models.PositiveIntegerField(_("Reihenfolge"), default=0)

    class Meta:
        verbose_name = _("Galeriebild")
        verbose_name_plural = _("Galeriebilder")
        ordering = ["order", "id"]

    def clean(self):
        if not self.alt_text or not self.alt_text.strip():
            raise ValidationError({"alt_text": _("Alt-Text ist Pflicht (Barrierefreiheit).")})

    def __str__(self):
        return f"Bild zu {self.article.title} ({self.alt_text})"
