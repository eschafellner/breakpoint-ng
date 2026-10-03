from django.contrib import admin
from .models import Tournament, Competition, Entry, Match, HonorRollEntry
from apps.core.admin import ServiceManagedAdminMixin


class CompetitionInline(admin.TabularInline):
    model = Competition
    extra = 1


class MatchInline(ServiceManagedAdminMixin, admin.TabularInline):
    model = Match
    extra = 0
    fields = (
        "round",
        "position",
        "entry_a",
        "entry_b",
        "winner",
        "result_type",
        "scheduled_court",
        "scheduled_start",
    )


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "start_date",
        "end_date",
        "registration_deadline",
        "eligibility",
        "status",
    )
    list_filter = ("status", "eligibility", "start_date")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CompetitionInline]


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "tournament", "discipline", "format", "max_entries")
    list_filter = ("discipline", "format", "tournament")
    inlines = [MatchInline]


@admin.register(Entry)
class EntryAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = ("competition", "player1", "player2", "seed", "status", "created_at")
    list_filter = ("status", "competition")
    search_fields = ("player1__email", "player1__last_name", "player2__last_name")

    def get_readonly_fields(self, request, obj=None):
        return tuple(
            field.name for field in self.model._meta.fields if field.name != "seed"
        )

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)


@admin.register(Match)
class MatchAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "competition",
        "round",
        "position",
        "entry_a",
        "entry_b",
        "winner",
        "result_type",
        "scheduled_court",
    )
    list_filter = ("competition", "round", "result_type")


@admin.register(HonorRollEntry)
class HonorRollEntryAdmin(admin.ModelAdmin):
    list_display = (
        "year",
        "competition_name",
        "winner_name",
        "runner_up_name",
        "score",
    )
    list_filter = ("year",)
