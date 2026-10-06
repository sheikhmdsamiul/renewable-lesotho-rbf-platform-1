"""DoE / PSC / Auditor separation over the shared monitoring, verification and audit records."""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.users.models import User
from .models import (
    AuditCase,
    AuditLog,
    FieldVerification,
    InstallationReport,
    KpiReview,
    OversightReview,
    PaymentClaim,
    Project,
    VerificationStatus,
    VerificationTask,
)

PDF_BYTES = b"%PDF-1.4\n%test\n"


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, password="securePass123", role=role, status="Active", **extra)


class SharedOversightFixture(APITestCase):
    def setUp(self):
        self.vendor = make_user("ov_vendor", "Vendor", region="Maseru")
        self.verifier = make_user("ov_verifier", "Field Verifier", region="Maseru")
        self.doe = make_user("ov_doe", "DoE Officer", region="Maseru")
        self.far_doe = make_user("ov_doe_far", "DoE Officer", region="Mokhotlong")
        self.psc = make_user("ov_psc", "Project Steering Committee")
        self.auditor = make_user("ov_auditor", "Auditor")
        self.rmt = make_user("ov_rmt", "RBF Management Team")
        self.project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name="Sun Co", tech_type="SHS", region="Maseru",
            district="Maseru", project_reference="PRJ-OV-1", status="active",
        )
        self.report = InstallationReport.objects.create(
            project=self.project, vendor=self.vendor, gps_lat=-29.31, gps_lng=27.48,
            serial_number="SN-OV-1", beneficiary_id="B-1", district="Maseru",
        )
        self.task = VerificationTask.objects.create(
            report=self.report, assigned_verifier=self.verifier, vendor_lat=-29.31, vendor_lng=27.48,
        )
        self.claim = PaymentClaim.objects.create(project=self.project, vendor=self.vendor, claim_amount=1000)

    def submit_verification(self):
        self.client.force_authenticate(self.verifier)
        return self.client.post(
            f"/api/projects/verification-tasks/{self.task.id}/verify/",
            {"verifier_lat": "-29.31", "verifier_lng": "27.48", "verification_status": "verified", "system_working": "true"},
            format="multipart",
        )


class FieldVerificationFlowTests(SharedOversightFixture):
    def test_submitted_verification_is_locked_until_reverification(self):
        self.assertEqual(self.submit_verification().status_code, status.HTTP_200_OK)
        again = self.submit_verification()
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.doe)
        response = self.client.post(
            f"/api/projects/verification-tasks/{self.task.id}/request_reverification/",
            {"reason": "Photos do not show the serial plate."}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, VerificationStatus.REVERIFICATION_REQUIRED)
        self.assertEqual(self.task.verification_round, 2)

        self.assertEqual(self.submit_verification().status_code, status.HTTP_200_OK)
        rounds = sorted(FieldVerification.objects.filter(installation=self.report).values_list("verification_round", flat=True))
        self.assertEqual(rounds, [1, 2])
        request_review = OversightReview.objects.get(verification_task=self.task, review_status="reverification_requested")
        self.assertEqual(request_review.follow_up_status, "resolved")

    def test_only_doe_and_rmt_review_verifications_and_doe_only_in_region(self):
        self.submit_verification()
        for user in (self.psc, self.auditor, self.far_doe):
            self.client.force_authenticate(user)
            response = self.client.post(f"/api/projects/verification-tasks/{self.task.id}/acknowledge/", {}, format="json")
            self.assertIn(response.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND}, user.role)
        self.client.force_authenticate(self.doe)
        response = self.client.post(f"/api/projects/verification-tasks/{self.task.id}/acknowledge/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_verification_evidence_cannot_be_edited_or_deleted_by_reviewers(self):
        self.submit_verification()
        for user in (self.doe, self.psc, self.auditor):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.patch(f"/api/projects/verification-tasks/{self.task.id}/", {"status": "Verified"}, format="json").status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            self.assertEqual(
                self.client.delete(f"/api/projects/verification-tasks/{self.task.id}/").status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )

    def test_psc_and_auditor_read_verification_records(self):
        self.submit_verification()
        for user in (self.psc, self.auditor):
            self.client.force_authenticate(user)
            response = self.client.get("/api/projects/verification-tasks/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["results"][0]["field_verification"]["verification_round"], 1)


class OversightReviewRoleTests(SharedOversightFixture):
    def test_psc_records_governance_review_on_a_disbursement(self):
        self.client.force_authenticate(self.psc)
        response = self.client.post("/api/projects/oversight-reviews/", {
            "subject_type": "disbursement", "review_status": "delayed", "payment_claim": self.claim.id,
            "comment": "Payment is two months behind schedule.", "action_required": "RMT to explain the delay.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["project"], self.project.id)
        self.assertEqual(response.data["follow_up_status"], "open")
        self.assertEqual(response.data["reviewer_role"], "Project Steering Committee")

    def test_doe_cannot_use_psc_governance_statuses(self):
        self.client.force_authenticate(self.doe)
        response = self.client.post("/api/projects/oversight-reviews/", {
            "subject_type": "project", "review_status": "compliant", "project": self.project.id, "comment": "All good here.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auditor_reads_but_cannot_write_oversight_reviews(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/projects/oversight-reviews/").status_code, status.HTTP_200_OK)
        response = self.client.post("/api/projects/oversight-reviews/", {
            "subject_type": "project", "review_status": "flagged", "project": self.project.id, "comment": "Looks wrong.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_oversight_reviews_are_never_deleted(self):
        review = OversightReview.objects.create(
            reviewer=self.psc, reviewer_role=self.psc.role, subject_type="project", review_status="flagged",
            project=self.project, comment="Flag",
        )
        self.client.force_authenticate(self.psc)
        self.assertEqual(
            self.client.delete(f"/api/projects/oversight-reviews/{review.id}/").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_psc_cannot_create_or_edit_kpi_reviews_or_monitoring_records(self):
        review = KpiReview.objects.create(project=self.project, reviewer=self.doe, review_period="2026-09", rating="on_track", summary="ok")
        self.client.force_authenticate(self.psc)
        self.assertEqual(
            self.client.patch(f"/api/projects/kpi-reviews/{review.id}/", {"summary": "PSC rewrote the DoE summary."}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post("/api/projects/kpi-reviews/", {
                "project": self.project.id, "review_period": "2026-10", "rating": "at_risk",
                "summary": "Uptime is falling across the regional sites.",
            }, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )


class VendorPerformanceTests(SharedOversightFixture):
    def test_vendor_performance_is_region_scoped_for_doe(self):
        self.submit_verification()
        self.client.force_authenticate(self.doe)
        rows = self.client.get("/api/projects/vendor-performance/").data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["installations"], 1)
        self.assertEqual(rows[0]["verified"], 1)
        self.client.force_authenticate(self.far_doe)
        self.assertEqual(self.client.get("/api/projects/vendor-performance/").data, [])
        self.client.force_authenticate(self.psc)
        self.assertEqual(len(self.client.get("/api/projects/vendor-performance/").data), 1)

    def test_vendor_cannot_read_vendor_performance(self):
        self.client.force_authenticate(self.vendor)
        self.assertEqual(self.client.get("/api/projects/vendor-performance/").status_code, status.HTTP_403_FORBIDDEN)


class AuditCaseWorkflowTests(SharedOversightFixture):
    def open_case(self, **extra):
        self.client.force_authenticate(self.auditor)
        payload = {
            "audit_area": "disbursement", "title": "Claim approval chain", "payment_claim": self.claim.id,
            "scope": "Check the approval chain for the first milestone claim.", **extra,
        }
        response = self.client.post("/api/projects/audit-cases/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def post(self, case_id, step, data=None, user=None):
        self.client.force_authenticate(user or self.auditor)
        return self.client.post(f"/api/projects/audit-cases/{case_id}/{step}/", data or {}, format="json")

    def test_full_audit_workflow_with_management_response(self):
        case = self.open_case()
        self.assertTrue(case["reference"].startswith("AUD-"))
        self.assertEqual(case["project"], self.project.id)
        self.assertEqual(case["status"], "draft")

        self.assertEqual(self.post(case["id"], "start_review").data["status"], "under_review")
        self.assertEqual(self.post(case["id"], "evidence_collected").status_code, status.HTTP_400_BAD_REQUEST)
        evidence = self.post(case["id"], "evidence", {
            "kind": "record", "description": "Claim approval log", "source_type": "PaymentClaim", "source_id": str(self.claim.id),
        })
        self.assertEqual(evidence.status_code, status.HTTP_201_CREATED, evidence.data)
        self.assertEqual(self.post(case["id"], "evidence_collected").data["status"], "evidence_collected")

        missing_action = self.post(case["id"], "record_finding", {
            "finding_type": "exception", "risk_level": "major", "finding": "PSC approval recorded before TAC endorsement.",
        })
        self.assertEqual(missing_action.status_code, status.HTTP_400_BAD_REQUEST)
        finding = self.post(case["id"], "record_finding", {
            "finding_type": "exception", "risk_level": "major", "finding": "PSC approval recorded before TAC endorsement.",
            "corrective_action": "Enforce the approval order.", "corrective_action_owner": "RMT",
        })
        self.assertEqual(finding.data["status"], "finding_recorded")
        self.assertEqual(finding.data["corrective_action_status"], "open")
        self.assertEqual(self.post(case["id"], "finalize", {"conclusion": "Exception confirmed."}).status_code, status.HTTP_400_BAD_REQUEST)

        # RMT and PSC cannot see the working papers until a response is requested.
        self.client.force_authenticate(self.rmt)
        self.assertEqual(self.client.get("/api/projects/audit-cases/").data["count"], 0)
        self.assertEqual(self.post(case["id"], "request_response").data["status"], "management_response")
        self.client.force_authenticate(self.psc)
        self.assertEqual(self.client.get("/api/projects/audit-cases/").data["count"], 1)

        self.assertEqual(self.post(case["id"], "finalize", {"conclusion": "Too early."}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.post(case["id"], "respond", {"management_response": "Agreed; fixing it."}, user=self.psc).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        responded = self.post(case["id"], "respond", {
            "management_response": "Agreed; the approval order is now enforced.", "corrective_action_status": "implemented",
        }, user=self.rmt)
        self.assertEqual(responded.status_code, status.HTTP_200_OK, responded.data)

        finalized = self.post(case["id"], "finalize", {"conclusion": "Exception confirmed and addressed."})
        self.assertEqual(finalized.data["status"], "finalized")
        self.assertEqual(self.post(case["id"], "close").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.post(case["id"], "corrective_action_progress", {"corrective_action_status": "verified"}).data["corrective_action_status"],
            "verified",
        )
        self.assertEqual(self.post(case["id"], "close").data["status"], "closed")

        actions = list(AuditLog.objects.filter(entity_type="AuditCase", entity_id=str(case["id"])).values_list("action", flat=True))
        self.assertIn("audit_case_finalized", actions)
        history = self.client.get(f"/api/projects/audit-cases/{case['id']}/history/")
        self.assertEqual(history.status_code, status.HTTP_200_OK)

    def test_compliant_finding_can_be_finalized_without_response(self):
        case = self.open_case(case_type="compliance_review", audit_area="verification")
        self.assertTrue(case["reference"].startswith("CR-"))
        self.post(case["id"], "start_review")
        upload = SimpleUploadedFile("sample.pdf", PDF_BYTES, content_type="application/pdf")
        self.client.force_authenticate(self.auditor)
        added = self.client.post(
            f"/api/projects/audit-cases/{case['id']}/evidence/",
            {"kind": "file", "description": "Sampled GPS trace", "file": upload}, format="multipart",
        )
        self.assertEqual(added.status_code, status.HTTP_201_CREATED, added.data)
        self.post(case["id"], "evidence_collected")
        self.post(case["id"], "record_finding", {"finding_type": "compliant", "risk_level": "observation", "finding": "All sampled GPS traces fall within 50 m."})
        self.assertEqual(self.post(case["id"], "finalize", {"conclusion": "Compliant."}).data["status"], "finalized")
        self.assertEqual(self.post(case["id"], "close").data["status"], "closed")

    def test_finalized_case_is_locked_and_cases_are_never_deleted(self):
        case = self.open_case()
        AuditCase.objects.filter(id=case["id"]).update(status="finalized")
        self.client.force_authenticate(self.auditor)
        self.assertEqual(
            self.client.patch(f"/api/projects/audit-cases/{case['id']}/", {"title": "Changed title"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(f"/api/projects/audit-cases/{case['id']}/").status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            self.post(case["id"], "evidence", {"kind": "note", "description": "Late note"}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_only_auditor_opens_cases(self):
        for user in (self.doe, self.psc, self.rmt):
            self.client.force_authenticate(user)
            response = self.client.post("/api/projects/audit-cases/", {
                "audit_area": "kpi", "title": "Not mine to open", "scope": "Should not be possible.",
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.role)

    def test_auditor_cannot_change_source_records(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(
            self.client.patch(f"/api/projects/{self.project.id}/", {"progress": 10}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        for step in ("verify", "approve", "pay"):
            response = self.client.post(f"/api/projects/claims/{self.claim.id}/{step}/", {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, step)
        self.assertEqual(
            self.client.post(f"/api/projects/verification-tasks/{self.task.id}/verify/", {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(f"/api/projects/audit-logs/{AuditLog.objects.create(action='x').id}/").status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)


class SystemAccessAuditTests(APITestCase):
    def test_logins_are_audited(self):
        make_user("login_user", "Auditor")
        self.client.post("/api/users/auth/token/", {"username": "login_user", "password": "wrong"}, format="json")
        self.client.post("/api/users/auth/token/", {"username": "login_user", "password": "securePass123"}, format="json")
        actions = set(AuditLog.objects.filter(module="system_access").values_list("action", flat=True))
        self.assertEqual(actions, {"login_failed", "login_succeeded"})
