from django.contrib import admin
from .models import Charge, Payment, PriceRule, BookingExtra, BookingExtraLine
from apps.core.admin import ServiceManagedAdminMixin
from .forms import ChargeCreationForm
from .services import create_charge, waive_charge
from apps.accounts.permissions import is_cashier
from django.contrib import messages


class PaymentInline(ServiceManagedAdminMixin, admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Charge)
class ChargeAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    form = ChargeCreationForm
    actions = ["waive_open_charges"]
    list_display = (
        "id",
        "user",
        "kind",
        "amount",
        "due_date",
        "status",
        "total_paid",
        "open_amount",
    )
    list_filter = ("kind", "status", "due_date")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "description",
    )
    inlines = [PaymentInline]
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return admin.ModelAdmin.has_add_permission(self, request)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return (
                "status",
                "content_type",
                "object_id",
                "dunning_level",
                "created_at",
                "updated_at",
            )
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        created = create_charge(
            user=obj.user,
            kind=obj.kind,
            amount=obj.amount,
            due_date=obj.due_date,
            description=obj.description,
            period_start=obj.period_start,
            period_end=obj.period_end,
        )
        obj.__dict__.update(created.__dict__)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not is_cashier(request.user):
            actions.pop("waive_open_charges", None)
        return actions

    @admin.action(
        description="Offene, unbezahlte Forderungen erlassen", permissions=["view"]
    )
    def waive_open_charges(self, request, queryset):
        count = 0
        for charge in queryset:
            try:
                waive_charge(
                    charge=charge,
                    actor=request.user,
                    reason="Erlass durch Kassier im Admin",
                )
                count += 1
            except ValueError as exc:
                self.message_user(request, str(exc), messages.ERROR)
        self.message_user(request, f"{count} Forderungen erlassen.", messages.SUCCESS)


@admin.register(Payment)
class PaymentAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "charge",
        "amount",
        "method",
        "paid_at",
        "recorded_by",
        "reference",
    )
    list_filter = ("method", "paid_at")
    search_fields = ("charge__user__email", "reference")


@admin.register(PriceRule)
class PriceRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "court", "applies_to", "price_per_hour", "price_per_person")
    list_filter = ("applies_to", "court")


@admin.register(BookingExtra)
class BookingExtraAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "unit", "price_member", "price_guest", "is_active")
    list_filter = ("mode", "unit", "is_active")
    search_fields = ("name",)


@admin.register(BookingExtraLine)
class BookingExtraLineAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = ("booking", "extra", "quantity", "unit_price", "total")
