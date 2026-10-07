from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .forms import AdminAccountCreationForm, AdminAccountChangeForm


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = AdminAccountCreationForm
    form = AdminAccountChangeForm
    list_display = (
        "email",
        "first_name",
        "last_name",
        "account_type",
        "email_verified",
        "is_staff",
        "failed_login_attempts",
    )
    list_filter = ("account_type", "email_verified", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("email",)
    actions = ["send_access_links"]

    @admin.action(description="Einladungs- oder Bestätigungslink senden")
    def send_access_links(self, request, queryset):
        from .services import request_account_recovery

        for user in queryset:
            request_account_recovery(user.email, request.build_absolute_uri("/").rstrip("/"))
        self.message_user(request, "Die Zugangsanfragen wurden verarbeitet.")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and not obj.email_verified:
            from .services import request_account_recovery

            request_account_recovery(obj.email, request.build_absolute_uri("/").rstrip("/"))

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Persönliche Daten",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone",
                    "birth_date",
                    "address_street",
                    "address_zip",
                    "address_city",
                    "avatar",
                )
            },
        ),
        (
            "Status & Typ",
            {
                "fields": (
                    "account_type",
                    "email_verified",
                    "email_verification_token",
                    "consent_privacy_at",
                )
            },
        ),
        ("Sicherheit & Sperren", {"fields": ("failed_login_attempts", "locked_until")}),
        (
            "Berechtigungen",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Wichtige Daten", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "account_type",
                ),
            },
        ),
    )
