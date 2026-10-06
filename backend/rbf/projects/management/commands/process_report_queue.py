from django.core.management.base import BaseCommand

from rbf.projects import report_queue


class Command(BaseCommand):
    help = 'Generate queued reports now (the report scheduler normally does this every few seconds).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        processed = report_queue.process(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(f'Generated {processed} queued report(s).'))
