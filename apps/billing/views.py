import logging
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from .permissions import can_access_billing
from .models import Charge, Payment
from .services import record_payment, generate_membership_fees, export_charges_to_csv
from .selectors import get_cashier_charges, get_billing_summary


@login_required
def cashier_dashboard_view(request):
    """Kassier-Dashboard: Übersicht aller Forderungen, Status-Filter, Beitragslauf-Trigger."""
    if not can_access_billing(request.user):
        raise PermissionDenied(_("Zugriff nur für Kassier oder Administratoren."))

    status = request.GET.get("status", "")
    search = request.GET.get("q", "")
    charges = get_cashier_charges(status=status, search=search)
    summary = get_billing_summary()
    page = Paginator(charges, 50).get_page(request.GET.get("page"))

    return render(
        request,
        "billing/dashboard.html",
        {
            "title": "Kassier-Dashboard",
            "charges": page,
            "page_obj": page,
            "summary": summary,
            "status_filter": status,
            "search_query": search,
            "statuses": Charge.Status.choices,
            "current_year": timezone.localdate().year,
        },
    )


@login_required
def record_payment_view(request, charge_id):
    """Kassier erfasst Zahlung für eine Forderung."""
    if not can_access_billing(request.user):
        raise PermissionDenied(_("Zugriff nur für Kassier oder Administratoren."))

    charge = get_object_or_404(Charge, pk=charge_id)

    if request.method == "POST":
        amount_raw = request.POST.get("amount", str(charge.open_amount)).replace(
            ",", "."
        )
        method = request.POST.get("method", Payment.Method.TRANSFER)
        reference = request.POST.get("reference", "")

        try:
            amount = Decimal(amount_raw)
            payment = record_payment(
                charge=charge,
                amount=amount,
                method=method,
                recorded_by=request.user,
                reference=reference,
            )
            messages.success(
                request,
                _("Zahlung von %(amt)s € erfasst. Neuer Status: %(status)s.")
                % {
                    "amt": f"{payment.amount:.2f}",
                    "status": charge.get_status_display(),
                },
            )
        except (ValidationError, ValueError) as e:
            messages.error(request, str(e))
        except InvalidOperation:
            messages.error(request, _("Bitte gib einen gültigen Zahlungsbetrag an."))
        except Exception:
            logging.getLogger(__name__).exception("Zahlung für Forderung #%s fehlgeschlagen", charge.pk)
            messages.error(request, _("Die Zahlung konnte nicht gespeichert werden. Bitte versuche es erneut."))

    return redirect("billing:dashboard")


@login_required
def run_fees_view(request):
    """Kassier stößt den automatischen Beitragslauf an."""
    if not can_access_billing(request.user):
        raise PermissionDenied(_("Zugriff nur für Kassier oder Administratoren."))

    if request.method == "POST":
        try:
            year = int(request.POST.get("year", timezone.localdate().year))
            month_raw = request.POST.get("month", "")
            month = int(month_raw) if month_raw else None
            created = generate_membership_fees(year=year, month=month)
            messages.success(
                request,
                _(
                    "Beitragslauf für %(yr)s erfolgreich durchgeführt! %(cnt)d neue Forderungen erstellt."
                )
                % {"yr": year, "cnt": len(created)},
            )
        except ValueError:
            messages.error(
                request,
                _("Bitte gib ein gültiges Jahr und einen Monat zwischen 1 und 12 an."),
            )

    return redirect("billing:dashboard")


@login_required
def export_csv_view(request):
    """Exportiert Forderungen als CSV."""
    if not can_access_billing(request.user):
        raise PermissionDenied(_("Zugriff nur für Kassier oder Administratoren."))

    status = request.GET.get("status", "")
    search = request.GET.get("q", "")
    charges = get_cashier_charges(status=status, search=search)
    csv_data = export_charges_to_csv(charges)

    response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="forderungen_export.csv"'
    return response
