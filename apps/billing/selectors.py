from decimal import Decimal
from typing import Optional, Dict, Any
from django.db.models import Sum, Q
from django.utils import timezone
from apps.accounts.models import User
from .models import Charge, Payment, PriceRule, BookingExtra


def get_user_charges(user: User):
    """Return all charges for a specific user."""
    return (
        Charge.objects.filter(user=user)
        .prefetch_related("payments")
        .order_by("-due_date", "-id")
    )


def get_cashier_charges(status: Optional[str] = None, search: Optional[str] = None):
    """Filtered charges query for cashier dashboard."""
    qs = Charge.objects.select_related("user").prefetch_related("payments")
    if status:
        qs = qs.filter(status=status)
    if search:
        search = search.strip()
        qs = qs.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__email__icontains=search)
            | Q(description__icontains=search)
        )
    return qs.order_by("-due_date", "-id")


def get_billing_summary() -> Dict[str, Any]:
    """Summary figures for Kassier dashboard."""
    today = timezone.localdate()
    all_charges = Charge.objects.all()

    total_amount = all_charges.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    outstanding = all_charges.filter(
        status__in=[Charge.Status.OPEN, Charge.Status.PARTIAL]
    ).prefetch_related("payments")
    open_amount_agg = sum((c.open_amount for c in outstanding), Decimal("0.00"))
    paid_amount_agg = Payment.objects.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    overdue_count = all_charges.filter(
        status__in=[Charge.Status.OPEN, Charge.Status.PARTIAL],
        due_date__lt=today,
    ).count()

    return {
        "total_amount": total_amount,
        "open_amount": open_amount_agg,
        "paid_amount": paid_amount_agg,
        "overdue_count": overdue_count,
    }


def get_applicable_price_rule(
    *, court, applies_to: str, booking_time, season=None
) -> Optional[PriceRule]:
    """Find the best matching price rule for a given court and participant type."""
    local = timezone.localtime(booking_time)
    rules = (
        PriceRule.objects.filter(applies_to=applies_to)
        .filter(Q(court=court) | Q(court__isnull=True))
        .select_related("season")
    )
    candidates = []
    for rule in rules:
        if len(rule.weekday_mask) != 7 or rule.weekday_mask[local.weekday()] != "1":
            continue
        if (
            rule.season
            and not rule.season.start_date <= local.date() <= rule.season.end_date
        ):
            continue
        if season and rule.season_id and rule.season_id != season.pk:
            continue
        if rule.time_from and local.time() < rule.time_from:
            continue
        if rule.time_to and local.time() >= rule.time_to:
            continue
        candidates.append(rule)
    candidates.sort(
        key=lambda rule: (
            rule.court_id is not None,
            rule.season_id is not None,
            bool(rule.time_from or rule.time_to),
            rule.weekday_mask != "1111111",
            -rule.pk,
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def get_booking_extras_for_court(court=None):
    """Return active extras for the specified court or global."""
    qs = BookingExtra.objects.filter(is_active=True)
    if court:
        qs = qs.filter(Q(courts=court) | Q(courts__isnull=True)).distinct()
    return qs
