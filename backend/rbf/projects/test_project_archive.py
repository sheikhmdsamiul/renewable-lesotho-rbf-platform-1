"""Project archive: completion archives the whole lifecycle (tender to contract closure) read-only."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.tenders.models import ContractStatus, Tender, TenderBid, TenderContract, TenderStatus
from rbf.users.models import User
from .archive import archive_project
from .models import InstallationReport, Milestone, PaymentClaim, Project, ProjectArchive, ProjectStatus
from .views import mark_project_completed


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, password="securePass123", role=role, status="Active", **extra)


def no_dossier(record):
    raise RuntimeError("renderer not available in tests")


@mock.patch("rbf.projects.lifecycle_dossier.render_dossier", side_effect=no_dossier)
class ProjectArchiveTests(APITestCase):
    def setUp(self):
        self.admin = make_user("arc_admin", "Platform Administrator (Super Admin)")
        self.rmt = make_user("arc_rmt", "RBF Management Team")
        self.psc = make_user("arc_psc", "Project Steering Committee")
        self.auditor = make_user("arc_auditor", "Auditor")
        self.doe = make_user("arc_doe", "DoE Officer", region="Maseru")
        self.vendor = make_user("arc_vendor", "Vendor", region="Maseru")
        self.tender = Tender.objects.create(
            reference_number="ARC-TND-1", name="Archive Tender", department="DoE", category="SHS",
            status=TenderStatus.AWARDED, deadline=timezone.now() - timedelta(days=60),
            published_at=timezone.now() - timedelta(days=90), awarded_at=timezone.now() - timedelta(days=40),
        )
        Tender.objects.filter(pk=self.tender.pk).update(created_at=timezone.now() - timedelta(days=120))
        self.tender.refresh_from_db()
        self.bid = TenderBid.objects.create(
            tender=self.tender, vendor_id=str(self.vendor.id), vendor_name="Sun Co", status="Awarded", bid_amount=1000,
        )
        self.contract = TenderContract.objects.create(
            tender=self.tender, bid=self.bid, vendor_id=str(self.vendor.id), vendor_name="Sun Co",
            reference_number="ARC-CON-1", status=ContractStatus.APPROVED, approved_at=timezone.now() - timedelta(days=35),
        )
        self.project = Project.objects.create(
            tender=self.tender, contract=self.contract, vendor_id=str(self.vendor.id), vendor_name="Sun Co",
            tech_type="SHS", region="Maseru", district="Maseru", project_reference="PRJ-ARC-1", status=ProjectStatus.ACTIVE,
        )
        self.contract.project_id = str(self.project.id)
        self.contract.save(update_fields=["project_id"])
        self.milestone = Milestone.objects.create(project=self.project, name="M1", percentage=100, amount=1000, status="paid")
        self.claim = PaymentClaim.objects.create(
            project=self.project, vendor=self.vendor, milestone=self.milestone, claim_amount=1000, status="Completed",
        )
        self.report = InstallationReport.objects.create(
            project=self.project, vendor=self.vendor, gps_lat=-29.3, gps_lng=27.5, serial_number="SN-ARC-1", beneficiary_id="B1",
        )

    def complete(self):
        mark_project_completed(self.project, self.rmt)
        self.project.refresh_from_db()

    def test_completion_archives_the_whole_lifecycle(self, _render):
        self.complete()
        self.assertEqual(self.project.status, ProjectStatus.COMPLETED)
        self.assertIsNotNone(self.project.archived_at)
        record = ProjectArchive.objects.get(project=self.project)
        self.assertEqual(record.lifecycle_started_at, self.tender.created_at)
        phases = [event["phase"] for event in record.timeline]
        self.assertEqual(record.timeline[0]["title"], "Tender created")
        for phase in ("Procurement", "Award", "Contract", "Delivery", "Completion"):
            self.assertIn(phase, phases)
        snap = record.snapshot
        self.assertEqual(snap["tender"]["reference"], "ARC-TND-1")
        self.assertEqual(snap["bids"][0]["vendor_name"], "Sun Co")
        self.assertEqual(snap["contract"]["status"], ContractStatus.CLOSED)
        self.assertEqual(snap["contract_status_before_closure"], ContractStatus.APPROVED)
        self.assertEqual(snap["payment_claims"][0]["id"], self.claim.id)
        self.assertEqual(snap["installations"]["total"], 1)

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, ContractStatus.CLOSED)
        self.assertIsNotNone(self.contract.closed_at)
        # Its only project is archived and the tender is fully awarded, so the tender is archived too.
        self.tender.refresh_from_db()
        self.assertIsNotNone(self.tender.archived_at)

    def test_archived_records_are_read_only(self, _render):
        self.complete()
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.patch(f"/api/projects/milestones/{self.milestone.id}/", {"name": "Changed"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(f"/api/projects/{self.project.id}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.patch(f"/api/tenders/{self.tender.id}/", {"name": "Renamed"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.doe)
        response = self.client.post("/api/projects/kpi-reviews/", {
            "project": self.project.id, "review_period": "2026-09", "rating": "on_track",
            "summary": "Reviewing an archived project.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_oversight_and_audit_still_work_on_archived_projects(self, _render):
        self.complete()
        self.client.force_authenticate(self.psc)
        response = self.client.post("/api/projects/oversight-reviews/", {
            "subject_type": "project", "review_status": "compliant", "project": self.project.id,
            "comment": "Closed out as planned.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.client.force_authenticate(self.auditor)
        response = self.client.post("/api/projects/audit-cases/", {
            "audit_area": "disbursement", "title": "Post-completion review", "project": self.project.id,
            "scope": "Sample the archived claims of this project.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_archived_records_leave_operational_lists(self, _render):
        self.complete()
        self.client.force_authenticate(self.rmt)
        ids = lambda url: {row["id"] for row in self.client.get(url).data["results"]}  # noqa: E731
        self.assertNotIn(self.project.id, ids("/api/projects/"))
        self.assertIn(self.project.id, ids("/api/projects/?archived=1"))
        self.assertNotIn(self.report.id, ids("/api/projects/installations/"))
        self.assertIn(self.report.id, ids(f"/api/projects/installations/?project={self.project.id}"))
        self.assertNotIn(self.claim.id, ids("/api/projects/claims/"))
        self.assertEqual(self.client.get(f"/api/projects/{self.project.id}/").status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.auditor)
        self.assertIn(self.project.id, ids("/api/projects/"))

    def test_archive_endpoint_returns_lifecycle(self, _render):
        self.complete()
        self.client.force_authenticate(self.psc)
        response = self.client.get(f"/api/projects/{self.project.id}/archive/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["tender_reference"], "ARC-TND-1")
        self.assertEqual(response.data[0]["contract_reference"], "ARC-CON-1")
        self.assertTrue(response.data[0]["timeline"])

    def test_only_super_admin_restores_and_restore_reopens_contract(self, _render):
        self.complete()
        self.client.force_authenticate(self.rmt)
        self.assertEqual(
            self.client.post(f"/api/projects/{self.project.id}/restore_archive/", {"reason": "Fix a typo in claim."}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/projects/{self.project.id}/restore_archive/", {"reason": "Correct the final claim reference."}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.project.refresh_from_db()
        self.contract.refresh_from_db()
        self.tender.refresh_from_db()
        self.assertIsNone(self.project.archived_at)
        self.assertEqual(self.contract.status, ContractStatus.APPROVED)
        self.assertIsNone(self.tender.archived_at)
        self.assertIsNotNone(ProjectArchive.objects.get(project=self.project).superseded_at)
        self.assertEqual(
            self.client.patch(f"/api/projects/milestones/{self.milestone.id}/", {"name": "Corrected"}, format="json").status_code,
            status.HTTP_200_OK,
        )
        # Archiving again writes a fresh record and keeps the superseded one.
        archive_project(self.project, self.admin)
        self.assertEqual(ProjectArchive.objects.filter(project=self.project).count(), 2)

    def test_tender_stays_open_while_another_project_is_live(self, _render):
        Project.objects.create(
            tender=self.tender, vendor_id=str(self.vendor.id), vendor_name="Sun Co", tech_type="SHS",
            region="Maseru", project_reference="PRJ-ARC-2", status=ProjectStatus.ACTIVE,
        )
        self.complete()
        self.tender.refresh_from_db()
        self.assertIsNone(self.tender.archived_at)

    def test_dossier_is_saved_when_renderer_succeeds(self, _render):
        pdf = Path(tempfile.mkdtemp()) / "dossier.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%test\n")
        _render.side_effect = None
        _render.return_value = pdf
        self.complete()
        record = ProjectArchive.objects.get(project=self.project)
        self.assertTrue(record.dossier)
        self.client.force_authenticate(self.auditor)
        response = self.client.get(f"/api/projects/{self.project.id}/archive/{record.id}/dossier/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
