import csv
import io
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, List, Any
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied
from apps.accounts.permissions import is_cashier
from apps.accounts.models import User
from apps.core.models import ClubSettings
from apps.core.services import log_audit
from .models import Charge, Payment

CENT = Decimal("0.01")


def quantize_amount(val: Any) -> Decimal:
    """Safely convert any numeric value to quantized 2-decimal Decimal."""
    try:
        val = Decimal(str(val))
        if not val.is_finite():
            raise ValueError(_("Ungültiger Geldbetrag."))
        result = val.quantize(CENT, rounding=ROUND_HALF_UP)
        if abs(result) >= Decimal("100000000"):
            raise ValueError(_("Geldbetrag überschreitet den zulässigen Bereich."))
        return result
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(_("Ungültiger Geldbetrag.")) from exc


@transaction.atomic
def create_charge(
    *,
    user: User,
    kind: str,
    amount: Decimal,
    due_date: date,
    description: str,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    source: Optional[Any] = None,
) -> Charge:
    """
    Central service to create a billing charge.
    Other apps must always use this function and never access billing models directly.
    """
    amount = quantize_amount(amount)
    if amount <= Decimal("0.00"):
        raise ValueError(_("Der Forderungsbetrag muss größer als 0 sein."))
    if kind not in Charge.Kind.values:
        raise ValueError(_("Ungültige Forderungsart."))
    if period_start and period_end and period_start > period_end:
        raise ValueError(_("Ungültiger Abrechnungszeitraum."))

    content_type = ContentType.objects.get_for_model(source) if source else None
    object_id = getattr(source, "pk", None) if source else None

    charge = Charge.objects.create(
        user=user,
        kind=kind,
        amount=amount,
        due_date=due_date,
        period_start=period_start,
        period_end=period_end,
        description=description,
        content_type=content_type,
        object_id=object_id,
        status=Charge.Status.OPEN,
    )

    log_audit(
        action="CREATE_CHARGE",
        entity_type="Charge",
        entity_id=str(charge.pk),
        changes={
            "user_id": user.pk,
            "kind": kind,
            "amount": str(amount),
            "due_date": str(due_date),
            "description": description,
        },
    )

    return charge


@transaction.atomic
def record_payment(
    *,
    charge: Charge,
    amount: Decimal,
    method: str = Payment.Method.TRANSFER,
    recorded_by: Optional[User] = None,
    reference: str = "",
    paid_at: Optional[timezone.datetime] = None,
) -> Payment:
    """Record a payment towards a charge and update its status."""
    amount = quantize_amount(amount)
    if amount <= Decimal("0.00"):
        raise ValueError(_("Der Zahlungsbetrag muss größer als 0 sein."))
    current = Charge.objects.select_for_update().get(pk=charge.pk)
    if current.status not in (Charge.Status.OPEN, Charge.Status.PARTIAL):
        raise ValueError(_("Diese Forderung kann nicht mehr bezahlt werden."))
    if method not in Payment.Method.values:
        raise ValueError(_("Ungültige Zahlungsmethode."))
    if amount > current.open_amount:
        raise ValueError(_("Die Zahlung überschreitet den offenen Betrag."))

    payment = Payment.objects.create(
        charge=current,
        amount=amount,
        method=method,
        recorded_by=recorded_by,
        reference=reference,
        paid_at=paid_at or timezone.now(),
    )

    total_paid = current.total_paid
    if total_paid >= current.amount:
        current.status = Charge.Status.PAID
    elif total_paid > Decimal("0.00"):
        current.status = Charge.Status.PARTIAL
    else:
        current.status = Charge.Status.OPEN
    current.save(update_fields=["status"])
    charge.status = current.status

    # Discard the caller's earlier dashboard snapshot after recording a payment.
    charge.__dict__.pop("_payment_total", None)
    getattr(charge, "_prefetched_objects_cache", {}).pop("payments", None)

    log_audit(
        user=recorded_by,
        action="RECORD_PAYMENT",
        entity_type="Payment",
        entity_id=str(payment.pk),
        changes={
            "charge_id": charge.pk,
            "amount": str(amount),
            "charge_status": charge.status,
        },
    )

    return payment


@transaction.atomic
def cancel_charge(charge: Charge, reason: str = "") -> None:
    """Cancel a charge (e.g. upon timely court booking cancellation)."""
    current = Charge.objects.select_for_update().get(pk=charge.pk)
    charge.status = current.status
    if current.status != Charge.Status.OPEN or current.total_paid > 0:
        return  # Cannot cancel already partially/fully paid charge directly
    charge.status = Charge.Status.CANCELLED
    charge.save(update_fields=["status"])
    log_audit(
        action="CANCEL_CHARGE",
        entity_type="Charge",
        entity_id=str(charge.pk),
        changes={"reason": reason},
    )


@transaction.atomic
def generate_membership_fees(*, year: int, month: Optional[int] = None) -> List[Charge]:
    """
    Idempotent fee run for membership fees (M-7, M-9, AP-05).
    - Yearly memberships: exactly 1 charge per year. If already created, skip.
    - Monthly memberships: 1 charge per month (or 12 for the whole year if month=None).
    - Prorated calculation for new members joining mid-year if enabled in ClubSettings.
    """
    from apps.members.models import Membership, MembershipType

    if (
        type(year) is not int
        or not 1 <= year <= 9999
        or (month is not None and (type(month) is not int or not 1 <= month <= 12))
    ):
        raise ValueError(_("Ungültiges Jahr oder ungültiger Monat."))
    settings_obj = ClubSettings.get_settings()
    created_charges = []
    # A deterministic lock order also covers simultaneous yearly/monthly runs.
    user_ids = (
        Membership.objects.filter(status=Membership.Status.ACTIVE)
        .values_list("user_id", flat=True)
        .distinct()
    )
    list(User.objects.select_for_update().filter(pk__in=user_ids).order_by("pk"))

    # Process yearly memberships
    if month is None:
        period_start = date(year, 1, 1)
        period_end = date(year, 12, 31)
        due_date = date(year, 1, 15)

        yearly_memberships = (
            Membership.objects.filter(
                status=Membership.Status.ACTIVE,
                type__billing_interval=MembershipType.BillingInterval.YEARLY,
                start_date__lte=period_end,
            )
            .filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gte=period_start)
            )
            .select_related("user", "type")
            .order_by("user_id", "pk")
        )

        for mem in yearly_memberships:
            # Idempotency check: does a charge for this user & year already exist?
            already_charged = Charge.objects.filter(
                user=mem.user,
                kind=Charge.Kind.MEMBERSHIP_FEE,
                period_start__year=year,
            ).exists()
            if already_charged:
                continue

            fee = mem.type.fee_amount
            # Prorated calculation
            if settings_obj.prorated_membership_fees and mem.start_date.year == year:
                # E.g., joined July 1st -> (12 - 7 + 1) = 6 months remaining
                months_remaining = 12 - mem.start_date.month + 1
                if months_remaining < 12:
                    fraction = Decimal(months_remaining) / Decimal(12)
                    fee = (fee * fraction).quantize(CENT, rounding=ROUND_HALF_UP)

            if fee <= Decimal("0.00"):
                continue

            chg = create_charge(
                user=mem.user,
                kind=Charge.Kind.MEMBERSHIP_FEE,
                amount=fee,
                due_date=max(due_date, mem.start_date),
                period_start=period_start,
                period_end=period_end,
                description=f"Mitgliedsbeitrag {mem.type.name} {year}",
                source=mem,
            )
            created_charges.append(chg)

    # Process monthly memberships
    monthly_memberships = (
        Membership.objects.filter(
            status=Membership.Status.ACTIVE,
            type__billing_interval=MembershipType.BillingInterval.MONTHLY,
        )
        .select_related("user", "type")
        .order_by("user_id", "pk")
    )

    target_months = [month] if month is not None else list(range(1, 13))

    for m in target_months:
        import calendar

        weekday, last_day = calendar.monthrange(year, m)
        m_start = date(year, m, 1)
        m_end = date(year, m, last_day)
        due = date(year, m, 5)

        for mem in monthly_memberships:
            # Check membership active during this month
            if mem.start_date > m_end:
                continue
            if mem.end_date and mem.end_date < m_start:
                continue

            already_charged = Charge.objects.filter(
                user=mem.user,
                kind=Charge.Kind.MEMBERSHIP_FEE,
                period_start=m_start,
            ).exists()
            if already_charged:
                continue

            fee = mem.type.fee_amount
            if fee <= 0:
                continue
            chg = create_charge(
                user=mem.user,
                kind=Charge.Kind.MEMBERSHIP_FEE,
                amount=fee,
                due_date=max(due, mem.start_date),
                period_start=m_start,
                period_end=m_end,
                description=f"Mitgliedsbeitrag {mem.type.name} {m:02d}/{year}",
                source=mem,
            )
            created_charges.append(chg)

    return created_charges


@transaction.atomic
def waive_charge(*, charge: Charge, actor: User, reason: str):
    if not is_cashier(actor):
        raise PermissionDenied(
            _("Nur Kassier oder Administrator dürfen Forderungen erlassen.")
        )
    if not reason.strip():
        raise ValueError(_("Eine Begründung für den Erlass ist erforderlich."))
    current = Charge.objects.select_for_update().get(pk=charge.pk)
    if current.status != Charge.Status.OPEN or current.total_paid > 0:
        raise ValueError(
            _("Nur offene, unbezahlte Forderungen können erlassen werden.")
        )
    current.status = Charge.Status.WAIVED
    current.save(update_fields=["status"])
    charge.status = current.status
    log_audit(
        user=actor,
        action="WAIVE_CHARGE",
        entity_type="Charge",
        entity_id=current.pk,
        changes={"reason": reason.strip()},
    )


def export_charges_to_csv(charges) -> str:
    """Export charges to standard CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Mitglied/Nutzer",
            "E-Mail",
            "Art",
            "Betrag (€)",
            "Fälligkeit",
            "Status",
            "Bezahlt (€)",
            "Offen (€)",
            "Beschreibung",
        ]
    )
    for c in charges:
        values = [
            c.pk,
            c.user.get_full_name() or c.user.email,
            c.user.email,
            c.get_kind_display(),
            f"{c.amount:.2f}",
            c.due_date.isoformat(),
            c.get_status_display(),
            f"{c.total_paid:.2f}",
            f"{c.open_amount:.2f}",
            c.description,
        ]
        writer.writerow(
            [
                (
                    "'" + value
                    if isinstance(value, str)
                    and value.lstrip().startswith(("=", "+", "-", "@"))
                    else value
                )
                for value in values
            ]
        )
    return output.getvalue()
