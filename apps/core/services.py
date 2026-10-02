from typing import Any, Optional
from .models import AuditLog

def log_audit(
    *,
    user: Optional[Any] = None,
    action: str,
    entity_type: str,
    entity_id: str,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Record an audit log entry for changes or critical actions."""
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        changes=changes or {},
        ip_address=ip_address,
    )
