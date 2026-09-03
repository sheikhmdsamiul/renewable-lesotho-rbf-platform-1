from django.core.management.base import BaseCommand
from django.utils import timezone

from rbf.projects.integrations import previous_quarter_period, queue_periodic_project_reports
from rbf.projects.models import AuditLog


class Command(BaseCommand):
    help = 'Queue quarterly Prospect pushReport records for the previous quarter for all eligible projects.'

    def handle(self, *args, **options):
        report_start, report_end = previous_quarter_period(timezone.localdate())
        queued = queue_periodic_project_reports(
            period_type='quarterly',
            report_start=report_start,
            report_end=report_end,
        )
        quarter = ((report_start.month - 1) // 3) + 1
        AuditLog.objects.create(
            actor=None,
            actor_role='system',
            action='quarterly_prospect_report_dispatched',
            module='prospect_sync',
            entity_type='Project',
            entity_id='*',
            record_type='project',
            notes=f'Dispatched {queued} report jobs for {report_start.year}-Q{quarter}.',
            details={
                'period_type': 'quarterly',
                'report_start': report_start.isoformat(),
                'report_end': report_end.isoformat(),
                'queued_jobs': queued,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Queued quarterly Prospect reports for {queued} project(s) '
                f'covering {report_start.isoformat()} to {report_end.isoformat()}.'
            )
        )
