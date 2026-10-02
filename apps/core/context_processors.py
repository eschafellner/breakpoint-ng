from .models import ClubSettings

def club_settings(request):
    """Context processor making ClubSettings available in all templates."""
    try:
        settings_obj = ClubSettings.get_settings()
    except Exception:
        settings_obj = None
    return {
        "club_settings": settings_obj,
    }
