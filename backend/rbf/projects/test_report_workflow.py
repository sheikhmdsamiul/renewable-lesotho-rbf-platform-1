"""Report sign-off (draft, review, approval, versions), distribution, and schedules."""

from datetime import date, datetime
from unittest import mock

from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.notifications.models import Notification
from rbf.users.models import User
from . import report_queue, report_workflow
from .models import GeneratedReport, PaymentClaim, Project, ReportSchedule


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, password="securePass123", role=role, status="Active",
                                    email=f"{username}@example.org", **extra)


@mock.patch("rbf.notifications.services.email_configured", return_value=True)
@mock.patch("rbf.projects.report_pdf.render_report_pdf", return_value=b"%PDF-1.4 test")
class ReportWorkflowTests(APITestCase):
    def setUp(self):
        self.preparer = make_user("wf_rmt1", "RBF Management Team")
        self.reviewer = make_user("wf_rmt2", "RBF Management Team")
        self.admin = make_user("wf_admin", "Platform Administrator (Super Admin)")
        self.psc = make_user("wf_psc", "Project Steering Committee")
        self.vendor = make_user("wf_vendor", "Vendor")
        project = Project.objects.create(vendor_id=str(self.vendor.id), vendor_name="Sun Co", tech_type="SHS", region="Maseru",
                                         district="Maseru", project_reference="PRJ-WF-1", status="active", budget=1000)
        PaymentClaim.objects.create(project=project, vendor=self.vendor, claim_amount=500, status="Completed")

    def generate(self, user, report_type="programme_results", fmt="pdf"):
        self.client.force_authenticate(user)
        queued = self.client.post("/api/projects/reports/generate/", {"report_type": report_type, "format": fmt, "filters": {}}, format="json")
        self.assertEqual(queued.status_code, status.HTTP_202_ACCEPTED, getattr(queued, "data", ""))
        report_queue.process()
        return GeneratedReport.objects.get(id=queued.data["id"])

    def step(self, user, report, step, **data):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/projects/reports/{report.id}/{step}/", data, format="json")

    def test_formal_report_goes_through_review_and_approval_with_separation_of_duties(self, _pdf, _mail):
        report = self.generate(self.preparer)
        self.assertEqual(report.approval_status, "draft")
        self.assertEqual(self.step(self.reviewer, report, "submit").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.step(self.preparer, report, "submit").data["approvalStatus"], "in_review")
        self.assertTrue(Notification.objects.filter(event="report_review_needed", recipient_id=str(self.reviewer.id)).exists())
        self.assertEqual(self.step(self.preparer, report, "review").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.step(self.psc, report, "review").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.reviewer)
        inbox = self.client.get("/api/projects/reports/inbox/").data
        self.assertEqual([r["id"] for r in inbox["awaiting"]], [str(report.id)])
        self.assertEqual(self.client.get(f"/api/projects/reports/{report.id}/download/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.step(self.reviewer, report, "review", notes="Figures checked.").data["approvalStatus"], "reviewed")
        self.assertEqual(self.step(self.reviewer, report, "approve").status_code, status.HTTP_403_FORBIDDEN)
        approved = self.step(self.admin, report, "approve", notes="Approved for PSC.")
        self.assertEqual(approved.data["approvalStatus"], "approved")
        self.assertEqual(approved.data["approvedBy"], "wf_admin")
        self.assertIn("Figures checked.", approved.data["reviewNotes"])

    def test_returned_report_gets_a_new_version(self, _pdf, _mail):
        report = self.generate(self.preparer)
        self.step(self.preparer, report, "submit")
        self.assertEqual(self.step(self.reviewer, report, "review", decision="return").status_code, status.HTTP_400_BAD_REQUEST)
        returned = self.step(self.reviewer, report, "review", decision="return", notes="Targets missing for OUT1.")
        self.assertEqual(returned.data["approvalStatus"], "returned")
        successor = self.step(self.preparer, report, "new-version")
        self.assertEqual(successor.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual((successor.data["version"], successor.data["supersedesId"]), (2, str(report.id)))
        report_queue.process()
        self.assertEqual(GeneratedReport.objects.get(id=successor.data["id"]).approval_status, "draft")

    def test_distribution_requires_approval_and_shares_with_recipients(self, _pdf, _mail):
        report = self.generate(self.preparer)
        self.assertEqual(self.step(self.preparer, report, "distribute", roles=["Project Steering Committee"]).status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.psc)
        self.assertEqual(self.client.get(f"/api/projects/reports/{report.id}/download/").status_code, status.HTTP_403_FORBIDDEN)
        self.step(self.preparer, report, "submit")
        self.step(self.reviewer, report, "review", notes="ok")
        self.step(self.admin, report, "approve", notes="ok")
        shared = self.step(self.preparer, report, "distribute", roles=["Project Steering Committee"])
        self.assertEqual(shared.data["recipients"], 1)
        self.client.force_authenticate(self.psc)
        self.assertEqual([r["id"] for r in self.client.get("/api/projects/reports/inbox/").data["shared"]], [str(report.id)])
        self.assertEqual(self.client.get(f"/api/projects/reports/{report.id}/download/").status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["wf_psc@example.org"])
        self.assertNotIn("%PDF", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].attachments, [])

    def test_non_formal_reports_need_no_sign_off(self, _pdf, _mail):
        report = self.generate(self.preparer, "rmt_financial_disbursement")
        self.assertEqual(report.approval_status, "not_required")
        self.assertEqual(self.step(self.preparer, report, "submit").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.step(self.preparer, report, "distribute", roles=["Auditor"]).status_code, status.HTTP_200_OK)

    # --- schedules ----------------------------------------------------------------------

    def schedule(self, **overrides):
        self.client.force_authenticate(self.admin)
        payload = {"name": "Monthly PSC briefing", "report_type": "psc_briefing", "format": "pdf", "frequency": "monthly",
                   "run_day": 5, "prepared_by": self.preparer.id, "recipient_roles": ["Project Steering Committee"], **overrides}
        return self.client.post("/api/projects/report-schedules/", payload, format="json")

    def test_schedule_validation_and_admin_only(self, _pdf, _mail):
        self.client.force_authenticate(self.preparer)
        self.assertEqual(self.client.post("/api/projects/report-schedules/", {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.schedule(report_type="rmt_kpi_project").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.schedule(report_type="rmt_portfolio_summary").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.schedule(recipient_roles=["Vendor"]).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.schedule(prepared_by=self.psc.id, report_type="auditor_full_audit").status_code, status.HTTP_400_BAD_REQUEST)
        created = self.schedule()
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertIsNotNone(created.data["next_run_at"])

    def test_periods_and_next_runs(self, _pdf, _mail):
        self.assertEqual(report_workflow.previous_period("monthly", date(2026, 10, 5)), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(report_workflow.previous_period("quarterly", date(2026, 10, 5)), (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(report_workflow.previous_period("quarterly", date(2026, 2, 10)), (date(2025, 10, 1), date(2025, 12, 31)))
        tz = timezone.get_current_timezone()
        quarterly = ReportSchedule(frequency="quarterly", run_day=5)
        after = timezone.make_aware(datetime(2026, 10, 6, 9, 0), tz)
        self.assertEqual(timezone.localtime(report_workflow.next_run(quarterly, after)).date(), date(2027, 1, 5))
        monthly = ReportSchedule(frequency="monthly", run_day=5)
        self.assertEqual(timezone.localtime(report_workflow.next_run(monthly, after)).date(), date(2026, 11, 5))

    def test_scheduled_formal_report_goes_to_review_then_to_recipients(self, _pdf, _mail):
        schedule = ReportSchedule.objects.get(id=self.schedule().data["id"])
        ReportSchedule.objects.filter(id=schedule.id).update(next_run_at=timezone.now() - timezone.timedelta(minutes=1))
        self.assertEqual(report_workflow.run_due_schedules(), 1)
        self.assertEqual(report_workflow.run_due_schedules(), 0)
        report_queue.process()
        report = GeneratedReport.objects.get(schedule=schedule)
        self.assertEqual(report.approval_status, "in_review")
        self.assertTrue(report.filters["from"].endswith("-01"))
        self.step(self.reviewer, report, "review", notes="ok")
        self.step(self.admin, report, "approve", notes="ok")
        report.refresh_from_db()
        self.assertEqual(list(report.distributed_to.values_list("username", flat=True)), ["wf_psc"])
        self.assertTrue(Notification.objects.filter(event="report_shared", recipient_id=str(self.psc.id)).exists())

    def test_scheduled_ordinary_report_is_distributed_when_ready(self, _pdf, _mail):
        created = self.schedule(name="Monthly disbursements", report_type="rmt_financial_disbursement", recipient_roles=["Auditor"],
                                recipient_users=[self.psc.id])
        schedule = ReportSchedule.objects.get(id=created.data["id"])
        report_workflow.run_schedule(schedule)
        report_queue.process()
        report = GeneratedReport.objects.get(schedule=schedule)
        self.assertEqual(report.approval_status, "not_required")
        self.assertEqual(list(report.distributed_to.values_list("username", flat=True)), ["wf_psc"])
