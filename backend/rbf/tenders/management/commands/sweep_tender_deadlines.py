from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from rbf.notifications.services import NotificationService
from rbf.tenders.models import BidStatus, Tender, TenderBid, TenderStatus
from rbf.tenders.views import _auto_close_tender_on_deadline, _bid_stage_spec
from rbf.users.models import User, UserRole

REMINDER_WINDOW = timedelta(hours=48)


class Command(BaseCommand):
    help = (
        "Close Published tenders whose submission deadline has passed (application-window "
        "tenders) and remind vendors with unsubmitted bids 48 hours before a deadline. "
        "Idempotent; run by run_report_scheduler on every tick."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        closed = reminded = 0
        for tender in Tender.objects.filter(status=TenderStatus.PUBLISHED):
            if _auto_close_tender_on_deadline(tender):
                closed += 1
                NotificationService.notify_roles(
                    roles={UserRole.RBF_OFFICIAL, UserRole.ADMIN},
                    title=f'Submissions closed: {tender.reference_number}',
                    body=(
                        f'The submission deadline for "{tender.name}" has passed and it is now closed. '
                        + ('Review and shortlist the EOI responses.' if tender.is_eoi_invite_only else 'It is ready for evaluation.')
                    ),
                    event='tender_auto_closed',
                    linked_entity_id=str(tender.id),
                    dedupe=True,
                )
                continue
            deadline = _bid_stage_spec(None, tender)['deadline']
            if deadline and now < deadline <= now + REMINDER_WINDOW:
                reminded += self._remind(tender, deadline)
        if closed or reminded:
            self.stdout.write(f'Tender deadline sweep: closed {closed}, reminded {reminded} vendor(s).')

    def _remind(self, tender, deadline) -> int:
        """Vendors with a started-but-unsubmitted bid, plus invited vendors who have
        not submitted anything yet. One reminder per vendor per tender."""
        bids = TenderBid.objects.filter(tender=tender)
        submitted = set(
            bids.exclude(status__in={BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN})
            .values_list('vendor_id', flat=True)
        )
        pending = set(
            bids.filter(status__in={BidStatus.DRAFT, BidStatus.REVISION_REQUIRED}).values_list('vendor_id', flat=True)
        ) | {str(v) for v in tender.invited_vendors.values_list('vendor_id', flat=True)}
        vendor_ids = [v for v in pending - submitted if str(v).isdigit()]
        vendors = list(User.objects.filter(id__in=vendor_ids, role=UserRole.VENDOR))
        notified = NotificationService.notify_users(
            users=vendors,
            title=f'Deadline approaching: {tender.reference_number}',
            body=(
                f'Submissions for "{tender.name}" close on {timezone.localtime(deadline):%Y-%m-%d %H:%M}. '
                'You have not submitted yet.'
            ),
            event='tender_deadline_reminder',
            linked_entity_id=str(tender.id),
            dedupe=True,
        )
        return len(notified)
