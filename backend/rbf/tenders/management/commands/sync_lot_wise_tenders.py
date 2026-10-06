from django.core.management.base import BaseCommand

from rbf.tenders.lot_status import AWARD_STAGE, rolled_up_tender_status, sync_lot_statuses, sync_lot_wise_tender
from rbf.tenders.models import Tender


class Command(BaseCommand):
    help = (
        'Re-derive lot statuses and roll lot-wise tender statuses up from their lots. '
        'Fixes tenders that were marked Awarded while some lots were never awarded. '
        'Reports only, unless --apply is given.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the corrected statuses.')

    def handle(self, *args, **options):
        apply = options['apply']
        changed = 0
        for tender in Tender.objects.filter(lots__isnull=False).distinct():
            lots = sync_lot_statuses(tender) if apply else list(tender.lots.all())
            started = tender.status in AWARD_STAGE or any(l.intent_to_award_bid_id or l.awarded_at for l in lots)
            if not started:
                continue
            expected = rolled_up_tender_status(tender, [lot.status for lot in lots])
            if expected == tender.status:
                continue
            changed += 1
            self.stdout.write(f'{tender.reference_number}: {tender.status} -> {expected} '
                              f'(lots: {", ".join(f"{l.name}={l.status}" for l in lots)})')
            if apply:
                sync_lot_wise_tender(tender)
        verb = 'Updated' if apply else 'Would update'
        self.stdout.write(self.style.SUCCESS(f'{verb} {changed} tender(s).'))
