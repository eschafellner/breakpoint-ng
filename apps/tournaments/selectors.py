from typing import Optional, Dict, Any
from .models import Tournament, Competition, HonorRollEntry
from .services import calculate_round_robin_standings
from apps.accounts.permissions import is_tournament_director
from apps.accounts.permissions import is_member
from apps.accounts.models import User
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone


def can_register_for_tournament(tournament, user):
    return bool(user and user.is_authenticated and user.is_active and user.email_verified and (
        tournament.eligibility == Tournament.Eligibility.MEMBERS_AND_GUESTS or is_member(user)
    ))


def get_potential_partners(tournament, user):
    if not can_register_for_tournament(tournament, user):
        return User.objects.none()
    users = User.objects.filter(is_active=True, email_verified=True, allow_partner_search=True).exclude(pk=user.pk)
    if tournament.eligibility == Tournament.Eligibility.MEMBERS_ONLY:
        from apps.members.models import Membership

        today = timezone.localdate()
        active = Membership.objects.filter(user_id=OuterRef("pk"), status="ACTIVE", start_date__lte=today).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        users = users.filter(account_type="MEMBER").annotate(_eligible=Exists(active)).filter(_eligible=True)
    return users.only("id", "first_name", "last_name").order_by("last_name", "first_name", "pk")


def get_tournaments():
    """Return all public tournaments."""
    return Tournament.objects.exclude(status=Tournament.Status.DRAFT).order_by(
        "-start_date"
    )


def get_tournament_by_slug(slug: str, user=None) -> Optional[Tournament]:
    """Retrieve tournament with competitions preloaded."""
    try:
        tournaments = Tournament.objects.prefetch_related(
            "competitions__entries__player1", "competitions__entries__player2"
        )
        if not is_tournament_director(user):
            tournaments = tournaments.exclude(status=Tournament.Status.DRAFT)
        return tournaments.get(slug=slug)
    except Tournament.DoesNotExist:
        return None


def get_competition_bracket_view(competition: Competition) -> Dict[str, Any]:
    """
    Format competition matches for the tournament bracket UI (matching Design_Template_Tennisverein.html).
    Returns rounds mapping: {round_num: [matches...]}.
    """
    matches = competition.matches.select_related(
        "entry_a__player1",
        "entry_a__player2",
        "entry_b__player1",
        "entry_b__player2",
        "winner",
        "scheduled_court",
    ).order_by("round", "position")

    rounds_data = {}
    for m in matches:
        rounds_data.setdefault(m.round, []).append(m)

    standings = []
    if competition.format == Competition.Format.ROUND_ROBIN:
        standings = calculate_round_robin_standings(competition)

    return {
        "competition": competition,
        "rounds": rounds_data,
        "matches": list(matches),
        "standings": standings,
    }


def get_honor_roll_entries():
    """Return past champions honor roll."""
    return HonorRollEntry.objects.all().order_by("-year", "competition_name")
