import time
from datetime import datetime

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Run the report scheduler: generates queued platform reports every few seconds, and dispatches the "
        "monthly and quarterly Prospect reports."
    )

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds for Prospect dispatch.")
        parser.add_argument("--queue-poll", type=int, default=3, help="Seconds between checks of the report queue.")
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

    def _process_queue(self) -> None:
        from django.db import close_old_connections

        from rbf.projects import report_queue, report_workflow

        close_old_connections()
        scheduled = report_workflow.run_due_schedules()
        if scheduled:
            self.stdout.write(f"[{timezone.localtime().isoformat()}] Queued {scheduled} scheduled report(s).")
        processed = report_queue.process()
        if processed:
            self.stdout.write(f"[{timezone.localtime().isoformat()}] Generated {processed} queued report(s).")

    def handle(self, *args, **options):
        interval = max(10, int(options.get("interval") or 60))
        queue_poll = max(1, int(options.get("queue_poll") or 3))
        run_once = bool(options.get("once"))

        self.stdout.write(self.style.SUCCESS(f"Report scheduler started. interval={interval}s queue_poll={queue_poll}s once={run_once}"))

        if run_once:
            self._process_queue()
            self._run_tick()
            self.stdout.write(self.style.SUCCESS("Report scheduler tick completed."))
            return

        last_tick = 0.0
        while True:
            try:
                self._process_queue()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.WARNING(f"Report queue failed: {exc}"))
            if time.monotonic() - last_tick >= interval:
                last_tick = time.monotonic()
                try:
                    self._run_tick()
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(self.style.WARNING(f"Scheduler tick failed: {exc}"))
            time.sleep(queue_poll)
