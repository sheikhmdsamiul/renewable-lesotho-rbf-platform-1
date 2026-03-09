from typing import Any

from .models import AuditLog


def log_audit(actor, action: str, entity: Any, details: dict | None = None) -> AuditLog:
    entity_type = entity.__class__.__name__
    entity_id = getattr(entity, 'id', '')
    return AuditLog.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
    )
