from django.core.management.base import BaseCommand

from rbf.projects.integrations import SyncToProspectJob
from rbf.projects.models import ProspectSyncLog, ProspectSyncStatus


class Command(BaseCommand):
    help = 'Retry failed or pending Prospect sync jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        limit = options['limit']
        logs = ProspectSyncLog.objects.filter(
            status__in=[ProspectSyncStatus.PENDING, ProspectSyncStatus.FAILED]
        ).order_by('created_at')[:limit]

        retried = 0
        for log in logs:
            SyncToProspectJob(
                log.method_name,
                log.payload,
                record_id=log.record_id,
                record_type=log.record_type,
                log_id=log.id,
            ).run()
            retried += 1

        self.stdout.write(self.style.SUCCESS(f'Retried {retried} Prospect sync job(s).'))
