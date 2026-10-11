from django.core.management.base import BaseCommand

from rbf.projects.payment_holds import escalate_overdue_findings


class Command(BaseCommand):
    help = (
        "Escalate anomaly flags the vendor did not answer by their due date, and alert owners of overdue "
        "oversight follow-ups and audit corrective actions. Run daily (the report scheduler does this)."
    )

    def handle(self, *args, **options):
        result = escalate_overdue_findings()
        self.stdout.write(self.style.SUCCESS(
            f"Escalated {result['anomalies_escalated']} anomaly flag(s); "
            f"{result['oversight_overdue']} oversight follow-up(s) and {result['audit_overdue']} audit action(s) overdue."
        ))
