from __future__ import annotations

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.users.models import User


class NotificationService:
    @staticmethod
    def send(
        recipient_id: str,
        title: str,
        body: str,
        level: str = 'info',
        module: str = '',
        record_id: int | None = None,
    ) -> Notification:
        recipient = User.objects.filter(id=recipient_id).only('full_name', 'username').first()
        return Notification.objects.create(
            recipient_id=str(recipient_id),
            recipient_name=(recipient.full_name or recipient.username) if recipient else str(recipient_id),
            type=NotificationChannel.IN_APP,
            event=f'{module or "general"}_{level}',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(record_id or ''),
        )
