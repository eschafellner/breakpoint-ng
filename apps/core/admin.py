from django.contrib import admin


class ServiceManagedAdminMixin:
    """Operational changes must run through the validated application services."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


from .models import ClubSettings, AuditLog, OutgoingEmail


@admin.register(ClubSettings)
class ClubSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Allgemein", {"fields": ("name", "short_name", "tagline", "logo")}),
        ("Kontakt", {"fields": ("email", "phone", "address")}),
        (
            "Bankverbindung",
            {"fields": ("bank_name", "iban", "bic", "payment_reference_prefix")},
        ),
        (
            "Buchungsregeln",
            {
                "fields": (
                    "advance_days_member",
                    "advance_days_guest",
                    "max_open_bookings",
                    "max_duration_minutes",
                    "free_cancel_hours",
                )
            },
        ),
        ("Beitragsregeln", {"fields": ("prorated_membership_fees",)}),
        ("Rechtliches", {"fields": ("imprint_text", "privacy_text")}),
        ("PWA & Offline-Modus", {"fields": ("offline_emergency_info",)}),
    )

    def has_add_permission(self, request):
        # Disallow adding more than one instance
        if ClubSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "action",
        "entity_type",
        "entity_id",
        "ip_address",
    )
    list_filter = ("action", "entity_type", "created_at")
    search_fields = ("entity_id", "user__email", "changes")
    readonly_fields = (
        "created_at",
        "user",
        "action",
        "entity_type",
        "entity_id",
        "changes",
        "ip_address",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutgoingEmail)
class OutgoingEmailAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = ("subject", "status", "attempts", "next_attempt_at", "sent_at")
    list_filter = ("status",)
    actions = ["retry_delivery"]

    @admin.action(permissions=["view"], description="Fehlgeschlagene E-Mails erneut zum Versand vormerken")
    def retry_delivery(self, request, queryset):
        from django.utils import timezone
        from .services import log_audit

        count = queryset.filter(status=OutgoingEmail.Status.FAILED).update(
            status=OutgoingEmail.Status.PENDING, attempts=0,
            next_attempt_at=timezone.now(), last_error="",
        )
        log_audit(user=request.user, action="RETRY_EMAIL_DELIVERY", entity_type="OutgoingEmail",
                  entity_id="bulk", changes={"count": count})
        self.message_user(request, f"{count} E-Mails erneut vorgemerkt.")
