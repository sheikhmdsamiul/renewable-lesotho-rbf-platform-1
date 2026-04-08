from __future__ import annotations

import logging
from typing import Any

from .middleware import get_current_request
from .models import AuditLog


logger = logging.getLogger(__name__)


class AuditLogger:
    @staticmethod
    def _ip_address(request) -> str:
        if request is None:
            return ''
        forwarded_for = str(request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return str(request.META.get('REMOTE_ADDR') or '').strip()

    @staticmethod
    def log(
        action: str,
        module: str,
        record_id: int | None = None,
        record_type: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        notes: str | None = None,
    ) -> AuditLog | None:
        request = get_current_request()
        actor = getattr(request, 'user', None)
        if actor is not None and not getattr(actor, 'is_authenticated', False):
            actor = None

        try:
            return AuditLog.objects.create(
                actor=actor,
                actor_role=str(getattr(actor, 'role', '') or ''),
                action=str(action or ''),
                module=str(module or ''),
                entity_type=str(record_type or ''),
                entity_id=str(record_id or ''),
                record_id=record_id,
                record_type=str(record_type or ''),
                old_status=str(old_status or ''),
                new_status=str(new_status or ''),
                notes=str(notes or ''),
                ip_address=AuditLogger._ip_address(request),
                details={},
            )
        except Exception:  # noqa: BLE001
            logger.exception('Audit logging failed for action=%s module=%s record_id=%s', action, module, record_id)
            return None


def log_audit(actor, action: str, entity: Any, details: dict | None = None) -> AuditLog | None:
    entity_type = entity.__class__.__name__
    entity_id = getattr(entity, 'id', None)
    details = details or {}

    request = get_current_request()
    try:
        return AuditLog.objects.create(
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            actor_role=str(getattr(actor, 'role', '') or ''),
            action=action,
            module=str(details.get('module') or entity_type.lower()),
            entity_type=entity_type,
            entity_id=str(entity_id or ''),
            record_id=int(entity_id) if entity_id not in {None, ''} and str(entity_id).isdigit() else None,
            record_type=entity_type,
            old_status=str(details.get('old_status') or ''),
            new_status=str(details.get('new_status') or ''),
            notes=str(details.get('notes') or ''),
            ip_address=AuditLogger._ip_address(request),
            details=details,
        )
    except Exception:  # noqa: BLE001
        logger.exception('Audit logging failed for action=%s entity=%s', action, entity_type)
        return None
