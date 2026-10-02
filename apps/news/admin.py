from django.contrib import admin
from .models import Category, Article, ArticleImage

class ArticleImageInline(admin.TabularInline):
    model = ArticleImage
    extra = 1
    fields = ("image", "alt_text", "caption", "order")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "visibility", "publish_at", "is_pinned", "author")
    list_filter = ("status", "visibility", "is_pinned", "category")
    search_fields = ("title", "teaser", "body")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ArticleImageInline]

@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    list_display = ("article", "alt_text", "caption", "order")
