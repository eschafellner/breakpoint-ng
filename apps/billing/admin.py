from django.contrib import admin
from .models import Charge, Payment, PriceRule, BookingExtra, BookingExtraLine

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("created_at",)

@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "amount", "due_date", "status", "total_paid", "open_amount")
    list_filter = ("kind", "status", "due_date")
    search_fields = ("user__email", "user__first_name", "user__last_name", "description")
    inlines = [PaymentInline]
    readonly_fields = ("created_at", "updated_at")

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "charge", "amount", "method", "paid_at", "recorded_by", "reference")
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
class BookingExtraLineAdmin(admin.ModelAdmin):
    list_display = ("booking", "extra", "quantity", "unit_price", "total")
