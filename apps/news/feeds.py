from django.contrib.syndication.views import Feed
from django.utils import timezone
from django.urls import reverse
from apps.core.models import ClubSettings
from .models import Article

class LatestNewsFeed(Feed):
    def title(self):
        settings_obj = ClubSettings.get_settings()
        return f"{settings_obj.name} – Neuigkeiten"

    def link(self):
        return reverse("news:list")

    def description(self):
        settings_obj = ClubSettings.get_settings()
        return f"Aktuelle Nachrichten und Berichte des {settings_obj.name}."

    def items(self):
        return Article.objects.filter(
            status=Article.Status.PUBLISHED,
            visibility=Article.Visibility.PUBLIC,
            publish_at__lte=timezone.now(),
        ).order_by("-publish_at")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.teaser or item.body[:200]

    def item_pubdate(self, item):
        return item.publish_at

    def item_link(self, item):
        return reverse("news:detail", kwargs={"slug": item.slug})
