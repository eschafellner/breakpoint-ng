from typing import Optional
from django.db.models import Q
from apps.accounts.models import User
from .models import Membership, MembershipApplication

def get_pending_applications():
    """Return all pending applications for admin review."""
    return MembershipApplication.objects.filter(
        status=MembershipApplication.Status.PENDING
    ).select_related("user", "requested_type").order_by("created_at")

def get_active_members_directory(query: Optional[str] = None):
    """
    Return active members directory (M-12a).
    Only active members have access.
    Returns queryset of active users with memberships.
    """
    memberships = Membership.objects.filter(
        status=Membership.Status.ACTIVE
    ).select_related("user", "type")

    if query:
        query = query.strip()
        memberships = memberships.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(member_number__icontains=query)
        )

    return memberships.order_by("user__last_name", "user__first_name")
