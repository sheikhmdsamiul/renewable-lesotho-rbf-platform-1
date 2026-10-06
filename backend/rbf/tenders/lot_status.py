"""Lot-wise status for lot-wise tenders.

Each lot of a lot-wise tender is awarded on its own, so each carries its own status:

* before award it follows the tender (Draft, Published, Closed, Evaluation...);
* Standstill once its own intent to award is issued;
* Disputed while the tender-level dispute/challenge is open and its intent is pending;
* Awarded once its award is confirmed.

The tender's status is then rolled up from its lots once award has started, so a
lot-wise tender is only Awarded when every lot is awarded.
"""
from django.db import transaction
from django.utils import timezone

from .models import Tender, TenderLot, TenderStatus

# Tender statuses that mean "the award stage has started"; before it, lots follow the tender.
AWARD_STAGE = {TenderStatus.STANDSTILL, TenderStatus.DISPUTED, TenderStatus.AWARDED}


def derive_lot_status(lot: TenderLot, tender: Tender) -> str:
    if lot.awarded_at:
        return TenderStatus.AWARDED
    if lot.intent_to_award_bid_id:
        return TenderStatus.DISPUTED if tender.status == TenderStatus.DISPUTED else TenderStatus.STANDSTILL
    if tender.status in AWARD_STAGE:
        # Other lots are in award, this one is still being evaluated.
        return TenderStatus.EVALUATION
    return tender.status


def rolled_up_tender_status(tender: Tender, lot_statuses: list[str]) -> str:
    """The tender status implied by its lots, once award has started."""
    if lot_statuses and all(status == TenderStatus.AWARDED for status in lot_statuses):
        return TenderStatus.AWARDED
    if TenderStatus.DISPUTED in lot_statuses:
        return TenderStatus.DISPUTED
    if TenderStatus.STANDSTILL in lot_statuses:
        return TenderStatus.STANDSTILL
    return TenderStatus.EVALUATION


def sync_lot_statuses(tender: Tender) -> list[TenderLot]:
    """Recompute and store every lot's status from its own award state and the tender."""
    lots = list(TenderLot.objects.filter(tender=tender))
    for lot in lots:
        status = derive_lot_status(lot, tender)
        if lot.status != status:
            lot.status = status
            TenderLot.objects.filter(pk=lot.pk).update(status=status)
    return lots


def sync_lot_wise_tender(tender: Tender) -> Tender:
    """Bring a lot-wise tender's lots and its own status in line with each other.

    Call after any award-stage change (intent, confirmation, revocation, dispute).
    Tenders without lots are left untouched.
    """
    with transaction.atomic():
        lots = sync_lot_statuses(tender)
        if not lots:
            return tender
        started = tender.status in AWARD_STAGE or any(l.intent_to_award_bid_id or l.awarded_at for l in lots)
        if not started:
            return tender
        target = rolled_up_tender_status(tender, [lot.status for lot in lots])
        if target != tender.status:
            fields = ['status', 'updated_at']
            tender.status = target
            if target == TenderStatus.AWARDED:
                tender.awarded_at = tender.awarded_at or timezone.now()
                tender.cooling_off_until = None
                tender.dispute_started_at = None
                fields += ['awarded_at', 'cooling_off_until', 'dispute_started_at']
            elif target == TenderStatus.EVALUATION:
                tender.cooling_off_until = None
                tender.dispute_started_at = None
                fields += ['cooling_off_until', 'dispute_started_at']
            tender.save(update_fields=fields)
            # A Disputed -> Evaluation/Standstill roll-up can change pending lots again.
            sync_lot_statuses(tender)
    return tender
