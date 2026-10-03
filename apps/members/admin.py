from django.contrib import admin
from .models import MembershipType, MembershipApplication, Membership
from apps.core.admin import ServiceManagedAdminMixin
from apps.accounts.models import User
from apps.core.services import log_audit
from django.db import transaction


@admin.register(MembershipType)
class MembershipTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "fee_amount",
        "billing_interval",
        "min_age",
        "max_age",
        "is_active",
    )
    list_filter = ("billing_interval", "is_active")
    search_fields = ("name",)


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(ServiceManagedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "requested_type",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("status", "requested_type", "created_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("member_number", "user", "type", "start_date", "end_date", "status")
    list_filter = ("status", "type", "start_date")
    search_fields = (
        "member_number",
        "user__email",
        "user__first_name",
        "user__last_name",
    )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        old_user_id = (
            Membership.objects.filter(pk=obj.pk)
            .values_list("user_id", flat=True)
            .first()
            if change
            else None
        )
        owners = list(
            User.objects.select_for_update()
            .filter(pk__in={obj.user_id, old_user_id} - {None})
            .order_by("pk")
        )
        super().save_model(request, obj, form, change)
        for owner in owners:
            owner.account_type = (
                User.AccountType.MEMBER
                if Membership.objects.filter(
                    user=owner, status=Membership.Status.ACTIVE
                ).exists()
                else User.AccountType.GUEST
            )
            owner.save(update_fields=["account_type"])
        log_audit(
            user=request.user,
            action="UPDATE_MEMBERSHIP",
            entity_type="Membership",
            entity_id=obj.pk,
            changes={"status": obj.status, "user_id": obj.user_id},
        )
