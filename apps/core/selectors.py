from .models import ClubSettings, AuditLog

def get_club_settings() -> ClubSettings:
    """Return the global ClubSettings instance."""
    return ClubSettings.get_settings()

def get_recent_audit_logs(limit: int = 50):
    """Return recent audit logs."""
    return AuditLog.objects.select_related("user").order_by("-created_at")[:limit]
