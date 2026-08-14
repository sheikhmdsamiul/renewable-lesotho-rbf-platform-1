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
    recipient_id = models.CharField(max_length=64)
    recipient_name = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=NotificationChannel.choices)
    event = models.CharField(max_length=128)
    title = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.SENT)
    timestamp = models.DateTimeField(auto_now_add=True)
    linked_entity_id = models.CharField(max_length=64, blank=True, default='')

    def __str__(self):
        return f"{self.type} - {self.title} ({self.status})"

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["recipient_id", "status"]),
            models.Index(fields=["event"]),
            models.Index(fields=["timestamp"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient_id", "event", "linked_entity_id"],
                condition=Q(linked_entity_id__gt=""),
                name="uniq_notification_recipient_event_entity",
            ),
        ]
