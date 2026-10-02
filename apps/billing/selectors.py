from decimal import Decimal
from typing import Optional, Dict, Any
from django.db.models import Sum, Q
from django.utils import timezone
from apps.accounts.models import User
from .models import Charge, PriceRule, BookingExtra

def get_user_charges(user: User):
    """Return all charges for a specific user."""
    return Charge.objects.filter(user=user).prefetch_related("payments").order_by("-due_date", "-id")

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
    today = timezone.now().date()
    all_charges = Charge.objects.all()

    total_amount = all_charges.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    open_amount_agg = all_charges.filter(
        status__in=[Charge.Status.OPEN, Charge.Status.PARTIAL]
    ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    paid_amount_agg = all_charges.filter(
        status=Charge.Status.PAID
    ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
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

def get_applicable_price_rule(*, court, applies_to: str, booking_time, season=None) -> Optional[PriceRule]:
    """Find the best matching price rule for a given court and participant type."""
    rules = PriceRule.objects.filter(applies_to=applies_to)
    if court:
        # Match specific court or fallback to null (all courts)
        court_rules = rules.filter(court=court)
        if court_rules.exists():
            return court_rules.first()
    return rules.filter(court__isnull=True).first()

def get_booking_extras_for_court(court=None):
    """Return active extras for the specified court or global."""
    qs = BookingExtra.objects.filter(is_active=True)
    if court:
        qs = qs.filter(Q(courts=court) | Q(courts__isnull=True)).distinct()
    return qs
