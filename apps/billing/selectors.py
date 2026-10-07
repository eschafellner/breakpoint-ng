from decimal import Decimal
from typing import Optional, Dict, Any
from django.db.models import Sum, Q, OuterRef, Subquery, DecimalField, Value, F, Case, When, Count
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from apps.accounts.models import User
from .models import Charge, Payment, PriceRule, BookingExtra


def charges_with_payment_totals():
    # A subquery avoids multiplying charge amounts by the payment join.
    sums = Payment.objects.filter(charge_id=OuterRef("pk")).order_by().values("charge_id").annotate(
        total=Sum("amount")
    ).values("total")
    money = DecimalField(max_digits=10, decimal_places=2)
    return Charge.objects.annotate(_payment_total=Coalesce(
        Subquery(sums, output_field=money), Value(Decimal("0.00")), output_field=money
    ))


def get_user_charges(user: User):
    """Return all charges for a specific user."""
    return (
        charges_with_payment_totals().filter(user=user)
        .order_by("-due_date", "-id")
    )


def get_cashier_charges(status: Optional[str] = None, search: Optional[str] = None):
    """Filtered charges query for cashier dashboard."""
    qs = charges_with_payment_totals().select_related("user")
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
    pending = Q(status__in=[Charge.Status.OPEN, Charge.Status.PARTIAL])
    money = DecimalField(max_digits=12, decimal_places=2)
    zero = Value(Decimal("0.00"), output_field=money)
    all_charges = charges_with_payment_totals().annotate(_outstanding=Case(
        When(pending, then=Greatest(F("amount") - F("_payment_total"), zero)),
        default=zero, output_field=money,
    ))
    summary = all_charges.aggregate(
        total=Sum("amount"), outstanding=Sum("_outstanding"),
        overdue=Count("pk", filter=pending & Q(due_date__lt=today)),
    )
    paid_amount_agg = Payment.objects.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    return {
        "total_amount": summary["total"] or Decimal("0.00"),
        "open_amount": summary["outstanding"] or Decimal("0.00"),
        "paid_amount": paid_amount_agg,
        "overdue_count": summary["overdue"],
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
