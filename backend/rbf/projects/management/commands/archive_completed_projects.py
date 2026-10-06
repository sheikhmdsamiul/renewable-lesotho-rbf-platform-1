from django.core.management.base import BaseCommand

from rbf.projects.archive import archive_project
from rbf.projects.models import Project, ProjectStatus


class Command(BaseCommand):
    help = (
        'Archive projects that were completed before archiving existed: writes the full lifecycle '
        'record (tender creation to completion), closes the contract and freezes the records. '
        'Reports only, unless --apply is given.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Archive the listed projects.')

    def handle(self, *args, **options):
        projects = Project.objects.filter(
            status__in=[ProjectStatus.COMPLETED, ProjectStatus.LEGACY_COMPLETED], archived_at__isnull=True,
        ).select_related('tender').order_by('id')
        for project in projects:
            self.stdout.write(
                f'{project.project_reference or project.id}: {project.vendor_name}'
                f' (tender {project.tender.reference_number if project.tender_id else "-"})'
            )
            if options['apply']:
                archive_project(project, None, reason='Project completed before archiving was introduced.')
        verb = 'Archived' if options['apply'] else 'Would archive'
        self.stdout.write(self.style.SUCCESS(f'{verb} {projects.count() if not options["apply"] else len(projects)} project(s).'))
