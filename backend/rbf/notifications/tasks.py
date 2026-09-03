import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification_email_task(self, subject, message, recipient_list):
    """Deliver an outbound notification email, retrying transient failures."""
    try:
        return send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(recipient_list or []),
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Notification email to %s failed", recipient_list)
        raise self.retry(exc=exc)
