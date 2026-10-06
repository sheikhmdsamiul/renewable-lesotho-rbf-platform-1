from django.db.models.signals import post_save
from django.dispatch import receiver

from .lot_status import derive_lot_status, sync_lot_statuses
from .models import Tender, TenderLot


@receiver(post_save, sender=Tender)
def keep_lot_statuses_in_step(sender, instance: Tender, raw=False, **kwargs):
    """Any tender status change (publish, close, evaluation, award...) re-derives its lots."""
    if not raw:
        sync_lot_statuses(instance)


@receiver(post_save, sender=TenderLot)
def derive_saved_lot_status(sender, instance: TenderLot, raw=False, **kwargs):
    """A lot saved on its own (created, edited, intent issued...) gets its status re-derived."""
    if raw:
        return
    status = derive_lot_status(instance, instance.tender)
    if instance.status != status:
        instance.status = status
        TenderLot.objects.filter(pk=instance.pk).update(status=status)
