from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rbf.projects.models import GeneratedReport


class Command(BaseCommand):
    help = (
        'Delete generated report files older than a retention period. Reports only, unless --apply is given. '
        'No retention period is set by default: agree one with the programme (SRS gives none) before applying.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--older-than-days', type=int, required=True)
        parser.add_argument('--apply', action='store_true', help='Delete the files and their history rows.')

    def handle(self, *args, **options):
        days = options['older_than_days']
        if days < 30:
            raise CommandError('Use a retention period of at least 30 days.')
        old = GeneratedReport.objects.filter(generated_at__lt=timezone.now() - timedelta(days=days))
        count = old.count()
        if options['apply']:
            for report in old.iterator():
                if report.file:
                    report.file.delete(save=False)
            old.delete()
        verb = 'Deleted' if options['apply'] else 'Would delete'
        self.stdout.write(self.style.SUCCESS(f'{verb} {count} generated report(s) older than {days} days.'))
