from django.core.management.base import BaseCommand
from django.utils import timezone

from rbf.projects.integrations import SyncToProspectJob
from rbf.projects.kpi import KpiService
from rbf.projects.models import Project, ProjectStatus


class Command(BaseCommand):
    help = 'Generate monthly KPI summaries and push Prospect report records in the background.'

    def handle(self, *args, **options):
        month_key = timezone.localdate().strftime('%Y_%m')
        projects = Project.objects.exclude(status__in=[ProjectStatus.HALTED]).order_by('id')
        queued = 0
        for project in projects:
            KpiService.for_project(str(project.id)).getFullKpiSummary()
            SyncToProspectJob.dispatch_async(
                'pushReport',
                {
                    'external_id': f'report_{project.id}_{month_key}',
                    'country': 'LS',
                    'reporting_phase': f'PRJ-{project.id}',
                },
            )
            queued += 1
        self.stdout.write(self.style.SUCCESS(f'Queued monthly KPI Prospect reports for {queued} project(s).'))
