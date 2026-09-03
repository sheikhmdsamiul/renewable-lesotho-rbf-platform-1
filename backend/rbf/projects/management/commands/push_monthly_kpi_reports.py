from django.core.management.base import BaseCommand
from django.utils import timezone

from rbf.projects.integrations import previous_month_period, queue_periodic_project_reports
from rbf.projects.models import AuditLog


class Command(BaseCommand):
    help = 'Queue monthly Prospect pushReport records for the previous month for all eligible projects.'

    def handle(self, *args, **options):
        report_start, report_end = previous_month_period(timezone.localdate())
        queued = queue_periodic_project_reports(
            period_type='monthly',
            report_start=report_start,
            report_end=report_end,
        )
        AuditLog.objects.create(
            actor=None,
            actor_role='system',
            action='monthly_prospect_report_dispatched',
            module='prospect_sync',
            entity_type='Project',
            entity_id='*',
            record_type='project',
            notes=f'Dispatched {queued} report jobs for month {report_start.strftime("%Y-%m")}.',
            details={
                'period_type': 'monthly',
                'report_start': report_start.isoformat(),
                'report_end': report_end.isoformat(),
                'queued_jobs': queued,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Queued monthly Prospect reports for {queued} project(s) '
                f'covering {report_start.isoformat()} to {report_end.isoformat()}.'
            )
        )
