import time
from datetime import datetime

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run auto scheduler for monthly and quarterly Prospect report dispatch."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds.")
        parser.add_argument("--once", action="store_true", help="Run one scheduler tick and exit.")

    def _run_tick(self) -> None:
        now = timezone.localtime()
        # Trigger window: first day of month between 00:01 and 00:09 local time.
        in_window = now.day == 1 and now.hour == 0 and 1 <= now.minute <= 9
        if not in_window:
            return

        monthly_key = f"prospect:reports:monthly:{now.strftime('%Y-%m')}"
        if cache.add(monthly_key, "1", timeout=60 * 60 * 24 * 45):
            self.stdout.write(self.style.NOTICE(f"[{now.isoformat()}] Running monthly report dispatch."))
            call_command("push_monthly_kpi_reports")

        if now.month in {1, 4, 7, 10}:
            quarter = ((now.month - 1) // 3) + 1
            quarterly_key = f"prospect:reports:quarterly:{now.year}-Q{quarter}"
            if cache.add(quarterly_key, "1", timeout=60 * 60 * 24 * 400):
                self.stdout.write(self.style.NOTICE(f"[{now.isoformat()}] Running quarterly report dispatch."))
                call_command("push_quarterly_kpi_reports")

    def handle(self, *args, **options):
        interval = max(10, int(options.get("interval") or 60))
        run_once = bool(options.get("once"))

        self.stdout.write(self.style.SUCCESS(f"Report scheduler started. interval={interval}s once={run_once}"))

        if run_once:
            self._run_tick()
            self.stdout.write(self.style.SUCCESS("Report scheduler tick completed."))
            return

        while True:
            try:
                self._run_tick()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.WARNING(f"Scheduler tick failed: {exc}"))
            time.sleep(interval)
