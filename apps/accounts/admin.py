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
