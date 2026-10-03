from .models import ClubSettings
from apps.accounts.permissions import (
    is_club_admin,
    is_cashier,
    is_court_manager,
    is_tournament_director,
)


def club_settings(request):
    """Context processor making ClubSettings available in all templates."""
    try:
        settings_obj = ClubSettings.get_settings()
    except Exception:
        settings_obj = None
    return {
        "club_settings": settings_obj,
        "can_manage_members": is_club_admin(request.user),
        "can_access_billing": is_cashier(request.user),
        "can_manage_courts": is_court_manager(request.user),
        "can_manage_tournaments": is_tournament_director(request.user),
    }
