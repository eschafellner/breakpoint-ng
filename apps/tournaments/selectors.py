from typing import Optional, Dict, Any
from .models import Tournament, Competition, HonorRollEntry
from .services import calculate_round_robin_standings
from apps.accounts.permissions import is_tournament_director


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
        "standings": standings,
    }


def get_honor_roll_entries():
    """Return past champions honor roll."""
    return HonorRollEntry.objects.all().order_by("-year", "competition_name")
