from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _
from apps.accounts.permissions import is_member, is_club_admin
from .models import MembershipApplication
from .services import approve_application, reject_application, import_members_from_csv
from .selectors import get_active_members_directory, get_pending_applications


def directory_view(request):
    """
    M-12a: Internal member directory with search.
    Strictly restricted to active members.
    Anonymous users are redirected to login.
    Guests and applicants receive HTTP 403 Forbidden.
    """
    if not request.user.is_authenticated:
        return redirect(f"{settings_login_url()}?next={request.path}")

    if not is_member(request.user):
        return HttpResponseForbidden(
            _(
                "Zugriff verweigert: Nur aktive Mitglieder haben Zugriff auf die Mitgliederliste."
            )
        )

    query = request.GET.get("q", "")
    memberships = get_active_members_directory(query)

    return render(
        request,
        "members/directory.html",
        {
            "title": "Interne Mitgliederliste",
            "memberships": memberships,
            "query": query,
        },
    )


def settings_login_url():
    from django.conf import settings
    from django.urls import reverse

    url_or_name = getattr(settings, "LOGIN_URL", "accounts:login")
    try:
        return reverse(url_or_name)
    except Exception:
        return url_or_name


@login_required
def applications_list_view(request):
    """Admin view to review open membership applications."""
    if not is_club_admin(request.user):
        raise PermissionDenied(_("Nur Administratoren können Anträge verwalten."))

    applications = get_pending_applications()
    return render(
        request,
        "members/applications_list.html",
        {
            "title": "Offene Mitgliedsanträge",
            "applications": applications,
        },
    )


@login_required
def approve_application_view(request, pk):
    """Admin action to approve application."""
    if not is_club_admin(request.user):
        raise PermissionDenied(_("Nur Administratoren können Anträge genehmigen."))

    application = get_object_or_404(MembershipApplication, pk=pk)
    if request.method == "POST":
        try:
            membership = approve_application(
                application=application, reviewer=request.user
            )
            messages.success(
                request,
                _("Antrag genehmigt! Mitgliedsnummer %(nr)s vergeben.")
                % {"nr": membership.member_number},
            )
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("members:applications")


@login_required
def reject_application_view(request, pk):
    """Admin action to reject application with reason."""
    if not is_club_admin(request.user):
        raise PermissionDenied(_("Nur Administratoren können Anträge ablehnen."))

    application = get_object_or_404(MembershipApplication, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("rejection_reason", "").strip()
        if not reason:
            messages.error(
                request, _("Bitte gib eine Begründung für die Ablehnung an.")
            )
        else:
            try:
                reject_application(
                    application=application, reviewer=request.user, reason=reason
                )
                messages.warning(
                    request,
                    _(
                        "Antrag abgelehnt. Der Antragsteller wurde per E-Mail informiert."
                    ),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
    return redirect("members:applications")


@login_required
def csv_import_view(request):
    """Admin view for bulk CSV import."""
    if not is_club_admin(request.user):
        raise PermissionDenied(_("Nur Administratoren können Mitglieder importieren."))

    results = None
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        csv_text = request.POST.get("csv_text", "")

        content = ""
        if csv_file:
            content = csv_file.read().decode("utf-8", errors="replace")
        elif csv_text:
            content = csv_text

        if content:
            results = import_members_from_csv(content, reviewer=request.user)
            if results["created"] > 0:
                messages.success(
                    request,
                    _("%(count)d Mitglieder erfolgreich importiert.")
                    % {"count": results["created"]},
                )
            if results["errors"]:
                messages.warning(
                    request,
                    _("%(count)d Zeilen konnten nicht importiert werden.")
                    % {"count": len(results["errors"])},
                )
        else:
            messages.error(
                request, _("Bitte lade eine CSV-Datei hoch oder füge CSV-Inhalt ein.")
            )

    return render(
        request,
        "members/csv_import.html",
        {
            "title": "Mitglieder per CSV importieren",
            "results": results,
        },
    )
