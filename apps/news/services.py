import io
from pathlib import Path
from PIL import Image
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
    img = Image.open(image_field)
    img = img.convert("RGB")
    img.thumbnail(max_size, Image.Resampling.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85, optimize=True)
    output.seek(0)
    return ContentFile(output.read())

def create_article(
    *,
    title: str,
    body: str,
    author,
    teaser: str = "",
    cover_image = None,
    cover_image_alt: str = "",
    category: Category = None,
    visibility: str = Article.Visibility.PUBLIC,
    status: str = Article.Status.PUBLISHED,
    publish_at = None,
    is_pinned: bool = False,
) -> Article:
    """Create a news article with sanitized body and validated alt texts."""
    clean_body = sanitize_html(body)

    if cover_image and not cover_image_alt:
        raise ValidationError(_("Ein Alt-Text ist für das Titelbild verpflichtend (Barrierefreiheit)."))

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
) -> ArticleImage:
    """Add a gallery image to article and generate thumbnail & medium sizes."""
    if not alt_text or not alt_text.strip():
        raise ValidationError(_("Alt-Text ist Pflicht (Barrierefreiheit)."))

    gallery_img = ArticleImage(
        article=article,
        alt_text=alt_text.strip(),
        caption=caption.strip(),
        order=order,
    )
    # Save original
    file_name = Path(image_file.name).stem
    gallery_img.image.save(f"{file_name}_large.jpg", image_file, save=False)

    # Generate Medium (800x600)
    image_file.seek(0)
    med_content = resize_image(image_file, (800, 600))
    gallery_img.image_medium.save(f"{file_name}_med.jpg", med_content, save=False)

    # Generate Thumbnail (300x200)
    image_file.seek(0)
    thumb_content = resize_image(image_file, (300, 200))
    gallery_img.image_thumb.save(f"{file_name}_thumb.jpg", thumb_content, save=False)

    gallery_img.save()
    return gallery_img
