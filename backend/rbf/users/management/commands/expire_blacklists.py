from django.core.management.base import BaseCommand
from django.utils import timezone

from rbf.users.blacklisting import release_blacklist_case
from rbf.users.models import BlacklistCaseStatus, VendorBlacklistCase


class Command(BaseCommand):
    help = "Release temporary blacklisting cases whose expiry date has passed."

    def handle(self, *args, **options):
        today = timezone.localdate()
        cases = VendorBlacklistCase.objects.filter(
            status=BlacklistCaseStatus.BLACKLISTED,
            is_permanent=False,
            expiry_date__isnull=False,
            expiry_date__lt=today,
        )
        count = 0
        for case in cases:
            release_blacklist_case(case, actor=None, expired=True)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Expired blacklist cases released: {count}"))
