from django.db import models
from django.db.models import Q


class NotificationChannel(models.TextChoices):
    EMAIL = 'Email'
    SMS = 'SMS'
    IN_APP = 'In-App'


class NotificationStatus(models.TextChoices):
    SENT = 'Sent'
    DELIVERED = 'Delivered'
    READ = 'Read'
    FAILED = 'Failed'


class Notification(models.Model):
    """One in-app message to one user.

    Every event produces its own row so the recipient keeps the full history (a project's
    second claim is a separate notification from its first). `dedupe_key` is set only by
    senders that must notify at most once (for example the daily overdue sweep); it is unique
    per recipient when present.
    """

    recipient_id = models.CharField(max_length=64)
    recipient_name = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=NotificationChannel.choices)
    event = models.CharField(max_length=128)
    title = models.CharField(max_length=500)
    body = models.TextField()
    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.SENT)
    timestamp = models.DateTimeField(auto_now_add=True)
    linked_entity_id = models.CharField(max_length=64, blank=True, default='')
    dedupe_key = models.CharField(max_length=191, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.type} - {self.title} ({self.status})"

    @property
    def is_read(self) -> bool:
        return self.status == NotificationStatus.READ

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["recipient_id", "status"]),
            models.Index(fields=["recipient_id", "archived_at", "timestamp"]),
            models.Index(fields=["event"]),
            models.Index(fields=["timestamp"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient_id", "dedupe_key"],
                condition=Q(dedupe_key__gt=""),
                name="uniq_notification_recipient_dedupe_key",
            ),
        ]
