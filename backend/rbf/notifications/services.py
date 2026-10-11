from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.users.models import User, UserRole


def email_configured() -> bool:
    """Best-effort check that an SMTP backend is actually reachable to send."""
    if settings.DEBUG:
        return True
    return bool(
        (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
        or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
    )


RMT_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
PSC_ROLES = {UserRole.UNDP_DONOR}
SUPER_ADMIN_ROLES = {UserRole.ADMIN}

# Legacy pseudo-recipient placeholders -> real role sets.
PSEUDO_RECIPIENT_ROLES = {
    'rmt': RMT_ROLES,
    'psc': PSC_ROLES,
    'super_admin': SUPER_ADMIN_ROLES,
}


class NotificationService:
    """Central, production-grade helper for creating in-app notifications.

    All notification creation should route through here so that event naming,
    deduplication, recipient resolution and future channel fan-out (email, push)
    stay consistent.
    """

    @staticmethod
    def _recipient_name(user) -> str:
        if user is None:
            return ''
        return (user.full_name or user.username or user.email or str(getattr(user, 'id', '')))

    @classmethod
    def notify_user(
        cls,
        *,
        recipient=None,
        recipient_id: str | None = None,
        recipient_name: str | None = None,
        title: str,
        body: str,
        event: str,
        linked_entity_id: str = '',
        dedupe: bool = False,
        dedupe_key: str = '',
    ) -> Notification | None:
        """Create a single in-app notification for one user.

        Every call records a new notification unless `dedupe` is set (skip when the user already
        has this event for this entity) or `dedupe_key` is given (at most one per user and key).
        """
        user_id = str(getattr(recipient, 'id', None)) if recipient is not None else None
        user_id = user_id or (str(recipient_id) if recipient_id is not None else '')
        if not user_id:
            return None
        name = recipient_name or (cls._recipient_name(recipient) if recipient is not None else str(recipient_id))
        entity_key = str(linked_entity_id or '')
        if dedupe and cls.dedupe_exists(recipient_id=user_id, event=event, linked_entity_id=entity_key):
            return None
        try:
            # Savepoint: a duplicate dedupe_key must not break the caller's transaction.
            with transaction.atomic():
                return Notification.objects.create(
                    recipient_id=user_id,
                    recipient_name=name,
                    type=NotificationChannel.IN_APP,
                    event=event,
                    title=title[:500],
                    body=body,
                    status=NotificationStatus.SENT,
                    linked_entity_id=entity_key,
                    dedupe_key=dedupe_key[:191],
                )
        except IntegrityError:
            # Only dedupe_key is unique: this user was already notified for that key.
            return Notification.objects.filter(recipient_id=user_id, dedupe_key=dedupe_key).first()

    @classmethod
    def notify_users(
        cls,
        *,
        users,
        title: str,
        body: str,
        event: str,
        linked_entity_id: str = '',
        exclude_user_id=None,
        dedupe: bool = False,
    ) -> list:
        """Bulk-create in-app notifications for an explicit list of active users.

        With `dedupe`, users who already have this event for this entity are skipped
        (used for announcements such as a tender being published).
        """
        users = [u for u in users if u is not None and getattr(u, 'is_active', True)]
        if exclude_user_id:
            users = [u for u in users if str(getattr(u, 'id', '')) != str(exclude_user_id)]
        if not users:
            return []
        entity_key = str(linked_entity_id or '')
        existing = set(
            Notification.objects.filter(
                recipient_id__in=[str(u.id) for u in users],
                event=event,
                linked_entity_id=entity_key,
            ).values_list('recipient_id', flat=True)
        ) if dedupe else set()
        notifications = [
            Notification(
                recipient_id=str(user.id),
                recipient_name=cls._recipient_name(user),
                type=NotificationChannel.IN_APP,
                event=event,
                title=title[:500],
                body=body,
                status=NotificationStatus.SENT,
                linked_entity_id=entity_key,
            )
            for user in users
            if str(user.id) not in existing
        ]
        if notifications:
            Notification.objects.bulk_create(notifications)
        return users

    @classmethod
    def notify_roles(
        cls,
        *,
        roles,
        title: str,
        body: str,
        event: str,
        linked_entity_id: str = '',
        exclude_user_id=None,
        dedupe: bool = False,
    ) -> list[User]:
        """Bulk-create in-app notifications for every active user in the given roles."""
        users = list(
            User.objects.filter(role__in=set(roles), is_active=True)
            .distinct()
            .only('id', 'full_name', 'username', 'email')
        )
        return cls.notify_users(
            users=users,
            title=title,
            body=body,
            event=event,
            linked_entity_id=linked_entity_id,
            exclude_user_id=exclude_user_id,
            dedupe=dedupe,
        )

    @classmethod
    def notify_pseudo(cls, pseudo: str, *, title: str, body: str, event: str, linked_entity_id: str = ''):
        """Resolve a legacy 'rmt'/'psc'/'super_admin' placeholder to real users."""
        roles = cls.resolve_pseudo_recipients(pseudo)
        if not roles:
            return []
        return cls.notify_roles(
            roles=roles,
            title=title,
            body=body,
            event=event,
            linked_entity_id=linked_entity_id,
        )

    @classmethod
    def resolve_pseudo_recipients(cls, pseudo: str) -> set:
        return set(PSEUDO_RECIPIENT_ROLES.get(str(pseudo or '').lower(), set()))

    @classmethod
    def dedupe_exists(cls, *, recipient_id, event: str, linked_entity_id: str = '') -> bool:
        return Notification.objects.filter(
            recipient_id=str(recipient_id),
            event=event,
            linked_entity_id=str(linked_entity_id or ''),
        ).exists()

    @staticmethod
    def dispatch_email(subject: str, message: str, recipient_list) -> int:
        """Deliver an outbound email, enqueuing to Celery when EMAIL_ASYNC is on.

        Returns the number of recipients the email was sent to (or enqueued
        for). Returns 0 when email is not configured, there are no recipients,
        or delivery could not be dispatched at all.
        """
        recipient_list = list(dict.fromkeys(r.strip() for r in recipient_list if r and r.strip()))
        if not recipient_list or not email_configured():
            return 0
        if getattr(settings, 'EMAIL_ASYNC', False):
            try:
                from rbf.notifications.tasks import send_notification_email_task

                send_notification_email_task.delay(subject, message, recipient_list)
                return len(recipient_list)
            except Exception:
                # Broker unreachable: fall back to an immediate synchronous send.
                pass
        try:
            return send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=False,
            )
        except Exception:
            return 0

    @classmethod
    def send(
        cls,
        recipient_id: str,
        title: str,
        body: str,
        level: str = 'info',
        module: str = '',
        record_id: int | None = None,
    ) -> Notification | None:
        """Backward-compatible wrapper used by existing call sites."""
        recipient = User.objects.filter(id=recipient_id).only('id', 'full_name', 'username', 'email').first()
        return cls.notify_user(
            recipient=recipient,
            recipient_id=recipient_id,
            title=title,
            body=body,
            event=f'{module or "general"}_{level}',
            linked_entity_id=record_id or '',
        )
