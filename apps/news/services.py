import io
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
import nh3
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _
from .models import Article, ArticleImage, Category


def sanitize_html(html_content: str) -> str:
    """Sanitize HTML content to prevent XSS attacks while keeping formatting."""
    if not html_content:
        return ""
    return nh3.clean(html_content)


def resize_image(image_field, max_size: tuple[int, int]) -> ContentFile:
    """Resize an image to fit max_size preserving aspect ratio."""
    output = io.BytesIO()
    try:
        with Image.open(image_field) as source:
            img = ImageOps.exif_transpose(source).convert("RGB")
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(output, format="JPEG", quality=85, optimize=True)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValidationError(_("Die Datei enthält kein gültiges Bild.")) from exc
    output.seek(0)
    return ContentFile(output.read())


def create_article(
    *,
    title: str,
    body: str,
    author,
    teaser: str = "",
    cover_image=None,
    cover_image_alt: str = "",
    category: Category = None,
    visibility: str = Article.Visibility.PUBLIC,
    status: str = Article.Status.PUBLISHED,
    publish_at=None,
    is_pinned: bool = False,
) -> Article:
    """Create a news article with sanitized body and validated alt texts."""
    clean_body = sanitize_html(body)

    if cover_image and not cover_image_alt:
        raise ValidationError(
            _("Ein Alt-Text ist für das Titelbild verpflichtend (Barrierefreiheit).")
        )

    article = Article.objects.create(
        title=title,
        teaser=teaser,
        body=clean_body,
        cover_image=cover_image,
        cover_image_alt=cover_image_alt,
        category=category,
        visibility=visibility,
        status=status,
        publish_at=publish_at or timezone.now(),
        is_pinned=is_pinned,
        author=author,
    )
    return article


def add_gallery_image(
    *,
    article: Article,
    image_file,
    alt_text: str,
    caption: str = "",
    order: int = 0,
    instance=None,
) -> ArticleImage:
    """Add a gallery image to article and generate thumbnail & medium sizes."""
    if not alt_text or not alt_text.strip():
        raise ValidationError(_("Alt-Text ist Pflicht (Barrierefreiheit)."))

    gallery_img = instance or ArticleImage(article=article)
    gallery_img.alt_text = alt_text.strip()
    gallery_img.caption = caption.strip()
    gallery_img.order = order
    # Decode all variants before writing files, including a JPEG large image.
    file_name = Path(image_file.name).stem
    image_file.seek(0)
    large_content = resize_image(image_file, (1920, 1440))

    # Generate Medium (800x600)
    image_file.seek(0)
    med_content = resize_image(image_file, (800, 600))

    # Generate Thumbnail (300x200)
    image_file.seek(0)
    thumb_content = resize_image(image_file, (300, 200))
    fields = []
    try:
        for field, name, content in [
            (gallery_img.image, f"{file_name}_large.jpg", large_content),
            (gallery_img.image_medium, f"{file_name}_med.jpg", med_content),
            (gallery_img.image_thumb, f"{file_name}_thumb.jpg", thumb_content),
        ]:
            field.save(name, content, save=False)
            fields.append(field)
        gallery_img.save()
    except Exception:
        for field in fields:
            field.delete(save=False)
        raise
    return gallery_img
