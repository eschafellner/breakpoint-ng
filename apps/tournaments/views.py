import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import is_tournament_director
from apps.accounts.models import User
from apps.core.view_utils import positive_pk
from apps.courts.models import Court
from django.utils import timezone
from datetime import datetime
from .models import Competition, Entry, Match
from .services import (
    register_for_competition,
    record_match_result,
    confirm_partner_entry,
    withdraw_entry,
    schedule_tournament_match,
    draw_competition,
    draw_review_token,
)
from .selectors import (
    get_tournaments,
    get_tournament_by_slug,
    get_competition_bracket_view,
    get_honor_roll_entries,
    get_potential_partners,
    can_register_for_tournament,
)
from .forms import DrawCompetitionForm


def tournament_list_view(request):
    """Übersicht aller Turniere und Meisterschaften."""
    tournaments = get_tournaments()
    return render(
        request,
        "tournaments/list.html",
        {
            "title": "Turniere & Meisterschaften",
            "tournaments": tournaments,
        },
    )


def tournament_detail_view(request, slug):
    """Detailansicht mit Konkurrenz-Tabs, Bracket und Anmeldung (T-4, T-8)."""
    tournament = get_tournament_by_slug(slug, user=request.user)
    if not tournament:
        from django.http import Http404

        raise Http404(_("Turnier nicht gefunden."))

    selected_comp_id = request.GET.get("comp")
    competitions = tournament.competitions.all()

    current_comp = None
    if selected_comp_id and selected_comp_id.isdigit():
        current_comp = competitions.filter(pk=selected_comp_id).first()
    if not current_comp and competitions.exists():
        current_comp = competitions.first()

    bracket_data = None
    if current_comp:
        bracket_data = get_competition_bracket_view(current_comp)

    # Check if current user is registered
    user_entry = None
    if request.user.is_authenticated and current_comp:
        from django.db.models import Q

        user_entry = (
            current_comp.entries.filter(
                Q(player1=request.user) | Q(player2=request.user)
            )
            .exclude(status=Entry.Status.WITHDRAWN)
            .first()
        )

    potential_partners = get_potential_partners(tournament, request.user)

    return render(
        request,
        "tournaments/detail.html",
        {
            "title": f"{tournament.name} – Spielplan & Anmeldung",
            "tournament": tournament,
            "competitions": competitions,
            "current_comp": current_comp,
            "bracket_data": bracket_data,
            "user_entry": user_entry,
            "potential_partners": potential_partners,
            "can_register": can_register_for_tournament(tournament, request.user),
            "available_courts": Court.objects.filter(is_active=True),
        },
    )


@login_required
def register_view(request, comp_id):
    """Spieler meldet sich für eine Konkurrenz an (T-4, AP-08)."""
    competition = get_object_or_404(Competition, pk=comp_id)

    if request.method == "POST":
        partner_id = request.POST.get("partner_id")
        partner = None
        if partner_id:
            partner = get_object_or_404(get_potential_partners(competition.tournament, request.user), pk=positive_pk(partner_id))

        try:
            entry = register_for_competition(
                competition=competition,
                player1=request.user,
                player2=partner,
            )
            if entry.status == Entry.Status.CONFIRMED:
                messages.success(
                    request,
                    _("Erfolgreich angemeldet für %(comp)s!")
                    % {"comp": competition.name},
                )
            elif entry.status == Entry.Status.PENDING_PARTNER:
                messages.info(
                    request, _("Anmeldung vorgemerkt – Partner muss noch bestätigen.")
                )
            elif entry.status == Entry.Status.WAITLIST:
                messages.warning(
                    request, _("Teilnehmerlimit erreicht – Du bist auf der Warteliste.")
                )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        except Exception:
            logging.getLogger(__name__).exception("Turnieranmeldung für Konkurrenz #%s fehlgeschlagen", competition.pk)
            messages.error(request, _("Die Anmeldung konnte nicht gespeichert werden. Bitte versuche es erneut."))

    return redirect(
        f"/tournaments/{competition.tournament.slug}/?comp={competition.id}"
    )


@login_required
@require_POST
def confirm_partner_view(request, entry_id):
    entry = get_object_or_404(Entry, pk=entry_id)
    if entry.player2_id != request.user.pk:
        raise PermissionDenied(_("Du bist nicht der angegebene Partner."))
    try:
        confirm_partner_entry(entry, request.user)
        messages.success(request, _("Teilnahme bestätigt."))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(
        f"/tournaments/{entry.competition.tournament.slug}/?comp={entry.competition_id}"
    )


@login_required
@require_POST
def withdraw_entry_view(request, entry_id):
    entry = get_object_or_404(Entry, pk=entry_id)
    if request.user.pk not in (
        entry.player1_id,
        entry.player2_id,
    ) and not is_tournament_director(request.user):
        raise PermissionDenied(_("Keine Berechtigung für diese Abmeldung."))
    try:
        withdraw_entry(entry, actor=request.user)
        messages.success(request, _("Turnieranmeldung zurückgezogen."))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(
        f"/tournaments/{entry.competition.tournament.slug}/?comp={entry.competition_id}"
    )


def honor_roll_view(request):
    """Ehrentafel der Ortsmeister über die Jahre (T-8)."""
    entries = get_honor_roll_entries()
    return render(
        request,
        "tournaments/honor_roll.html",
        {
            "title": "Ehrentafel der Ortsmeister",
            "entries": entries,
        },
    )


@login_required
def manage_match_result_view(request, match_id):
    """Turnierleiter trägt Ergebnis ein (T-7)."""
    if not is_tournament_director(request.user):
        raise PermissionDenied(_("Nur Turnierleiter können Ergebnisse erfassen."))

    match = get_object_or_404(Match, pk=match_id)
    if request.method == "POST":
        winner_id = request.POST.get("winner_id")
        score_set1 = request.POST.get("set1", "")  # e.g. "6:4"
        score_set2 = request.POST.get("set2", "")  # e.g. "7:5"
        score_set3 = request.POST.get("set3", "")  # e.g. "10:8"
        result_type = request.POST.get("result_type", Match.ResultType.NORMAL)

        winner = get_object_or_404(
            Entry, pk=positive_pk(winner_id), competition=match.competition
        )
        try:
            parsed_score = []
            seen_empty = False
            for raw in [score_set1, score_set2, score_set3]:
                value = raw.strip()
                if not value:
                    seen_empty = True
                    continue
                parts = value.split(":")
                if (
                    seen_empty
                    or len(parts) != 2
                    or not all(part.isdecimal() for part in parts)
                ):
                    raise ValidationError(
                        _("Bitte gib die Sätze vollständig im Format 6:4 ein.")
                    )
                parsed_score.append({"a": int(parts[0]), "b": int(parts[1])})
            record_match_result(
                match=match,
                score=parsed_score,
                winner=winner,
                result_type=result_type,
                actor=request.user,
            )
            messages.success(
                request,
                _("Ergebnis für %(m)s erfolgreich gespeichert!") % {"m": str(match)},
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        except Exception:
            logging.getLogger(__name__).exception("Ergebnis für Spiel #%s fehlgeschlagen", match.pk)
            messages.error(request, _("Das Ergebnis konnte nicht gespeichert werden. Bitte versuche es erneut."))

    return redirect(
        f"/tournaments/{match.competition.tournament.slug}/?comp={match.competition.id}"
    )


@login_required
@require_POST
def schedule_match_view(request, match_id):
    if not is_tournament_director(request.user):
        raise PermissionDenied(_("Nur Turnierleiter können Spiele ansetzen."))
    match = get_object_or_404(Match, pk=match_id)
    court = get_object_or_404(Court, pk=positive_pk(request.POST.get("court_id")))
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        schedule_tournament_match(
            match=match,
            court=court,
            start_dt=start,
            duration_minutes=int(request.POST.get("duration", "90")),
            actor=request.user,
        )
        messages.success(request, _("Spieltermin gespeichert."))
    except (ValueError, ValidationError):
        messages.error(
            request,
            _(
                "Der Termin ist ungültig oder überschneidet sich mit einer Buchung oder Sperre."
            ),
        )
    return redirect(
        f"/tournaments/{match.competition.tournament.slug}/?comp={match.competition_id}"
    )


@login_required
@require_http_methods(["GET", "POST"])
def draw_competition_view(request, comp_id):
    if not is_tournament_director(request.user):
        raise PermissionDenied(_("Nur Turnierleiter können auslosen."))
    competition = get_object_or_404(Competition.objects.select_related("tournament"), pk=comp_id)
    form = DrawCompetitionForm(request.POST if request.method == "POST" else None,
                               initial={"snapshot": draw_review_token(competition)})
    if request.method == "POST" and form.is_valid():
        try:
            matches = draw_competition(competition=competition, actor=request.user,
                                       review_token=form.cleaned_data["snapshot"])
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, f"Auslosung abgeschlossen: {len(matches)} Spiele erstellt.")
            return redirect(f"/tournaments/{competition.tournament.slug}/?comp={competition.pk}")
    return render(request, "tournaments/draw.html", {
        "title": "Auslosung prüfen", "competition": competition, "form": form,
        "entries": competition.entries.filter(status=Entry.Status.CONFIRMED).select_related("player1", "player2").order_by("seed", "pk"),
        "pending_count": competition.entries.filter(status=Entry.Status.PENDING_PARTNER).count(),
        "waitlist_count": competition.entries.filter(status=Entry.Status.WAITLIST).count(),
    })
