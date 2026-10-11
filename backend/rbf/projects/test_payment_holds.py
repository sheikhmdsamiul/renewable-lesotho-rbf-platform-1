from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.notifications.models import Notification

from .models import (
    AnomalyFlag,
    AnomalyFlagStatus,
    AuditCase,
    AuditCaseStatus,
    InstallationReport,
    InstallationStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
    SiteMonitoringVisit,
    SiteVisitFollowUpStatus,
)
from .payment_holds import escalate_overdue_findings


class PaymentHoldTests(APITestCase):
    """Open serious findings hold a claim at every approval and payment step, and vendors
    answer anomaly requests before their due date or the request escalates."""

    def setUp(self):
        User = get_user_model()
        self.vendor = User.objects.create_user(username="ph_vendor", password="securePass123", role="Vendor", status="Active")
        self.other_vendor = User.objects.create_user(username="ph_vendor2", password="securePass123", role="Vendor", status="Active")
        self.rmt = User.objects.create_user(username="ph_rmt", password="securePass123", role="RBF Management Team", status="Active")
        self.tac = User.objects.create_user(username="ph_tac", password="securePass123", role="TAC Member", status="Active")
        self.psc = User.objects.create_user(username="ph_psc", password="securePass123", role="Project Steering Committee", status="Active")
        self.doe = User.objects.create_user(
            username="ph_doe", password="securePass123", role="DoE Officer", status="Active", verification_zone="Maseru",
        )
        self.auditor = User.objects.create_user(username="ph_auditor", password="securePass123", role="Auditor", status="Active")
        self.project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name=self.vendor.username, tech_type="SHS", region="Maseru",
            district="Maseru", status=ProjectStatus.INSTALLATION, project_reference="PRJ-HOLD-001", target_installations=10,
        )
        self.m1 = self.project.milestones.create(name="M1", milestone_number=1, percentage=20, amount=1000, status="claimable")
        self.installation = InstallationReport.objects.create(
            project=self.project, vendor=self.vendor, gps_lat=-29.3, gps_lng=27.5,
            serial_number="SN-H1", beneficiary_id="BEN-H1", status=InstallationStatus.VERIFIED,
        )
        cache.clear()

    def _claim(self, claim_status=PaymentClaimStatus.SUBMITTED):
        return PaymentClaim.objects.create(
            project=self.project, vendor=self.vendor, milestone=self.m1, claim_amount=1000,
            declaration_accepted=True, status=claim_status,
        )

    def _flag(self, **fields):
        defaults = {"installation": self.installation, "project": self.project, "flag_type": "no_data", "severity": "medium"}
        return AnomalyFlag.objects.create(**{**defaults, **fields})

    def _post(self, user, url, data=None):
        self.client.force_authenticate(user)
        return self.client.post(url, data or {}, format="json")

    def test_high_severity_anomaly_holds_rmt_approval_until_resolved(self):
        claim = self._claim()
        self._flag(severity="low")
        flag = self._flag(severity="high")

        response = self._post(self.rmt, f"/api/projects/claims/{claim.id}/verify/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual([b["id"] for b in response.data["blockers"]], [str(flag.id)])
        self.assertIn("Payment is on hold", response.data["detail"])

        assessment = self.client.get(f"/api/projects/claims/{claim.id}/assessment/").data
        self.assertEqual(len(assessment["payment_blockers"]), 1)

        AnomalyFlag.objects.filter(id=flag.id).update(is_resolved=True, status=AnomalyFlagStatus.RESOLVED)
        self.assertEqual(self._post(self.rmt, f"/api/projects/claims/{claim.id}/verify/").status_code, status.HTTP_200_OK)

    def test_oversight_flag_on_disbursement_holds_payment_until_follow_up_resolved(self):
        claim = self._claim(PaymentClaimStatus.RMT_APPROVED)
        # A project concern recorded without a payment hold does not block.
        response = self._post(self.rmt, "/api/projects/oversight-reviews/", {
            "subject_type": "project", "review_status": "flagged", "project": self.project.id, "comment": "Site signage missing.",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(response.data["holds_payment"])

        response = self._post(self.psc, "/api/projects/oversight-reviews/", {
            "subject_type": "disbursement", "review_status": "flagged", "payment_claim": claim.id,
            "comment": "Disbursement amount does not match the verified count.",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data["holds_payment"])
        review_id = response.data["id"]

        self.assertEqual(self._post(self.tac, f"/api/projects/claims/{claim.id}/approve/").status_code, status.HTTP_409_CONFLICT)

        response = self._post(self.rmt, f"/api/projects/oversight-reviews/{review_id}/follow_up/", {
            "follow_up_status": "resolved", "resolution_note": "Recounted; the amount matches.",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._post(self.tac, f"/api/projects/claims/{claim.id}/approve/").status_code, status.HTTP_200_OK)

    def test_audit_on_claim_holds_psc_approval_and_is_hidden_from_vendor(self):
        claim = self._claim(PaymentClaimStatus.TAC_ENDORSED)
        case = AuditCase.objects.create(
            reference="AUD-T-1", audit_area="disbursement", title="Claim test", scope="Check claim",
            status=AuditCaseStatus.DRAFT, auditor=self.auditor, project=self.project, payment_claim=claim,
        )
        # A draft is the auditor's private working paper and does not hold anything yet.
        self.assertEqual(self._post(self.psc, f"/api/projects/claims/{claim.id}/approve/").status_code, status.HTTP_200_OK)

        claim.status = PaymentClaimStatus.TAC_ENDORSED
        claim.save(update_fields=["status"])
        AuditCase.objects.filter(id=case.id).update(status=AuditCaseStatus.UNDER_REVIEW)
        response = self._post(self.psc, f"/api/projects/claims/{claim.id}/approve/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["blockers"][0]["source"], "audit")
        self.assertNotIn("Claim test", response.data["detail"])

        self.client.force_authenticate(self.vendor)
        self.assertEqual(self.client.get(f"/api/projects/claims/{claim.id}/blockers/").data["blockers"], [])

    def test_failed_site_visit_holds_confirm_paid(self):
        claim = self._claim(PaymentClaimStatus.PSC_APPROVED)
        visit = SiteMonitoringVisit.objects.create(
            project=self.project, installation=self.installation, visited_by=self.doe, visit_date=timezone.localdate(),
            system_working=False, observations="Inverter dead.", follow_up_status=SiteVisitFollowUpStatus.OPEN,
        )
        url = f"/api/projects/claims/{claim.id}/confirm-paid/"
        self.assertEqual(self._post(self.rmt, url, {"payment_reference": "REF-1"}).status_code, status.HTTP_409_CONFLICT)
        SiteMonitoringVisit.objects.filter(id=visit.id).update(follow_up_status=SiteVisitFollowUpStatus.CLOSED)
        self.assertEqual(self._post(self.rmt, url, {"payment_reference": "REF-1"}).status_code, status.HTTP_200_OK)

    def test_vendor_responds_to_correction_request(self):
        flag = self._flag(status=AnomalyFlagStatus.UNDER_INVESTIGATION, assigned_to=self.rmt)
        url = f"/api/projects/anomaly-flags/{flag.id}/respond/"
        self.assertEqual(self._post(self.vendor, url, {"response": "Nothing was asked yet."}).status_code, status.HTTP_400_BAD_REQUEST)

        response = self._post(self.rmt, f"/api/projects/anomaly-flags/{flag.id}/review/", {
            "status": "awaiting_evidence", "investigation_notes": "Send a photo of the meter display.",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["due_date"], (timezone.localdate() + timedelta(days=14)).isoformat())

        self.assertEqual(self._post(self.other_vendor, url, {"response": "Not my project at all."}).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._post(self.vendor, url, {"response": "short"}).status_code, status.HTTP_400_BAD_REQUEST)

        response = self._post(self.vendor, url, {"response": "Meter was offline during a grid outage; photo attached."})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], AnomalyFlagStatus.UNDER_INVESTIGATION)
        self.assertIn("grid outage", response.data["vendor_response"])
        self.assertEqual(response.data["review_events"][0]["actor_role"], "Vendor")
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.rmt.id), event="anomaly_vendor_responded").exists())

    def test_overdue_vendor_request_escalates_and_holds_payment(self):
        claim = self._claim()
        flag = self._flag(status=AnomalyFlagStatus.CORRECTION_REQUESTED, due_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self._post(self.rmt, f"/api/projects/claims/{claim.id}/verify/").status_code, status.HTTP_200_OK)

        result = escalate_overdue_findings()
        self.assertEqual(result["anomalies_escalated"], 1)
        flag.refresh_from_db()
        self.assertEqual(flag.status, AnomalyFlagStatus.ESCALATED)
        self.assertIsNotNone(flag.escalated_at)
        self.assertEqual(flag.review_events.first().actor_role, "System")
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.psc.id), event="anomaly_escalated").exists())
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.vendor.id), event="anomaly_escalated_vendor").exists())

        # Medium severity, but escalated: TAC endorsement is now held.
        self.assertEqual(self._post(self.tac, f"/api/projects/claims/{claim.id}/approve/").status_code, status.HTTP_409_CONFLICT)

        # Re-running the sweep does not escalate or notify twice.
        self.assertEqual(escalate_overdue_findings()["anomalies_escalated"], 0)
        self.assertEqual(Notification.objects.filter(recipient_id=str(self.psc.id), event="anomaly_escalated").count(), 1)
