from django.contrib import admin
from .models import MembershipType, MembershipApplication, Membership

@admin.register(MembershipType)
class MembershipTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_amount", "billing_interval", "min_age", "max_age", "is_active")
    list_filter = ("billing_interval", "is_active")
    search_fields = ("name",)

@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "requested_type", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "requested_type", "created_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("member_number", "user", "type", "start_date", "end_date", "status")
    list_filter = ("status", "type", "start_date")
    search_fields = ("member_number", "user__email", "user__first_name", "user__last_name")
