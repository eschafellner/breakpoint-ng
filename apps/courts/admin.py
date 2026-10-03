from django.contrib import admin
from .models import Court, Season, OpeningHours, Blocking, Booking, BookingParticipant
from apps.core.admin import ServiceManagedAdminMixin


class OpeningHoursInline(admin.TabularInline):
    model = OpeningHours
    extra = 7


class BookingParticipantInline(ServiceManagedAdminMixin, admin.TabularInline):
    model = BookingParticipant
    extra = 1


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "surface",
        "is_indoor",
        "has_floodlight",
        "is_active",
        "order",
    )
    list_filter = ("surface", "is_indoor", "has_floodlight", "is_active")
    inlines = [OpeningHoursInline]


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date")


@admin.register(Blocking)
class BlockingAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = ("court", "reason", "start", "end", "note", "created_by")
    list_filter = ("reason", "court", "start")
    search_fields = ("note", "court__name")


@admin.register(Booking)
class BookingAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "court", "booked_by", "start", "end", "total_price", "status")
    list_filter = ("status", "court", "start")
    search_fields = (
        "booked_by__email",
        "booked_by__first_name",
        "booked_by__last_name",
        "court__name",
    )
    inlines = [BookingParticipantInline]
