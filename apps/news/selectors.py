from typing import Optional
from django.db.models import Count, Q
from apps.accounts.permissions import is_member, is_editor
from django.utils import timezone
from .models import Article, Category


def get_published_articles(user=None, category_slug: Optional[str] = None):
    """
    Return published articles visible to the given user.
    - If publish_at is in the future, it is hidden.
    - If visibility is MEMBERS, only authenticated users with account_type == 'MEMBER' can see it.
    """
    now = timezone.now()
    qs = Article.objects.filter(
        status=Article.Status.PUBLISHED,
        publish_at__lte=now,
    ).select_related("category", "author")

    # Visibility filter
    is_user_member = is_member(user)
    if not is_user_member:
        qs = qs.filter(visibility=Article.Visibility.PUBLIC)

    if category_slug:
        qs = qs.filter(category__slug=category_slug)

    return qs.order_by("-is_pinned", "-publish_at")


def get_article_by_slug(slug: str, user=None) -> Optional[Article]:
    """Retrieve single article ensuring proper visibility permissions."""
    now = timezone.now()
    try:
        article = (
            Article.objects.select_related("category", "author")
            .prefetch_related("gallery_images")
            .get(slug=slug)
        )
    except Article.DoesNotExist:
        return None

    # Draft / scheduled checks (unless author/editor)
    is_user_editor = is_editor(user)
    if not is_user_editor:
        if article.status != Article.Status.PUBLISHED or article.publish_at > now:
            return None

        # Member-only check
        is_user_member = is_member(user)
        if article.visibility == Article.Visibility.MEMBERS and not is_user_member:
            return None

    return article


def get_categories(user=None):
    """List categories with count of published articles."""
    visible = Q(
        articles__status=Article.Status.PUBLISHED,
        articles__publish_at__lte=timezone.now(),
    )
    if not is_member(user):
        visible &= Q(articles__visibility=Article.Visibility.PUBLIC)
    return Category.objects.annotate(
        article_count=Count("articles", filter=visible)
    ).order_by("name")
