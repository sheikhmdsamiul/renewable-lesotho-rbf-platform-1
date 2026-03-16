from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, UserRole


@receiver(post_save, sender=User)
def enforce_official_password_reset(sender, instance: User, created: bool, **kwargs):
    """
    Ensure admin-created officials must reset password on first login.
    """
    if not created:
        return
    if instance.role != UserRole.VENDOR and not instance.must_change_password:
        instance.must_change_password = True
        instance.save(update_fields=['must_change_password'])
