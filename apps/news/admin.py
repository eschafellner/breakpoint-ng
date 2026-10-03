from django.contrib import admin
from .models import Category, Article, ArticleImage
from .services import add_gallery_image


def save_gallery_image(obj):
    add_gallery_image(
        article=obj.article,
        image_file=obj.image,
        alt_text=obj.alt_text,
        caption=obj.caption,
        order=obj.order,
        instance=obj,
    )


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
    list_display = (
        "title",
        "category",
        "status",
        "visibility",
        "publish_at",
        "is_pinned",
        "author",
    )
    list_filter = ("status", "visibility", "is_pinned", "category")
    search_fields = ("title", "teaser", "body")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ArticleImageInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            changed = next(
                (
                    inline_form.changed_data
                    for inline_form in formset.forms
                    if inline_form.instance is obj
                ),
                [],
            )
            if not obj.pk or "image" in changed:
                save_gallery_image(obj)
            else:
                obj.save()
        formset.save_m2m()


@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    list_display = ("article", "alt_text", "caption", "order")

    def save_model(self, request, obj, form, change):
        if not change or "image" in form.changed_data:
            save_gallery_image(obj)
        else:
            super().save_model(request, obj, form, change)
