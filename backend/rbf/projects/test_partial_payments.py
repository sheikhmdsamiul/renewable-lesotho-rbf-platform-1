from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.notifications.models import Notification

from .models import (
    CarryOverStatus,
    Disbursement,
    InstallationReport,
    InstallationStatus,
    MilestoneCarryOver,
    MilestoneCompletionReview,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
)

DEFICIENCY = [{"description": "20 households not yet installed", "required_action": "Install and submit for verification"}]


class PartialMilestonePaymentTests(APITestCase):
    """Target 100 installations: M2 needs 80 verified (its own 80 units), M3 needs all
    100 (its own 20 units, plus anything carried over from M2). M2 and M3 start
    claimable so the tests exercise RMT's delivery check rather than KPI unlocking."""

    def setUp(self):
        User = get_user_model()
        self.vendor = User.objects.create_user(username="pp_vendor", password="securePass123", role="Vendor", status="Active")
        self.other_vendor = User.objects.create_user(username="pp_vendor2", password="securePass123", role="Vendor", status="Active")
        self.rmt = User.objects.create_user(username="pp_rmt", password="securePass123", role="RBF Management Team", status="Active")
        self.tac = User.objects.create_user(username="pp_tac", password="securePass123", role="TAC Member", status="Active")
        self.psc = User.objects.create_user(username="pp_psc", password="securePass123", role="Project Steering Committee", status="Active")
        self.project = Project.objects.create(
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            project_reference="PRJ-PARTIAL-001",
            target_installations=100,
        )
        self.m1 = self.project.milestones.create(name="M1", milestone_number=1, percentage=20, amount=1000, status="paid")
        self.m2 = self.project.milestones.create(
            name="M2", milestone_number=2, percentage=40, amount=2000, status="claimable", required_installation_pct=80,
        )
        self.m3 = self.project.milestones.create(
            name="M3", milestone_number=3, percentage=40, amount=3000, status="claimable", required_installation_pct=100,
        )
        MilestoneCompletionReview.objects.create(
            milestone=self.m1, project=self.project, status="decided", decision="proceed",
        )
        self.serial = 0
        cache.clear()

    def _verified_installations(self, count):
        rows = []
        for _ in range(count):
            self.serial += 1
            rows.append(InstallationReport(
                project=self.project, vendor=self.vendor, gps_lat=-29.3, gps_lng=27.5,
                serial_number=f"SN-{self.serial}", beneficiary_id=f"BEN-{self.serial}", status=InstallationStatus.VERIFIED,
            ))
        InstallationReport.objects.bulk_create(rows)

    def _submit(self, milestone, amount):
        self.client.force_authenticate(self.vendor)
        return self.client.post(
            "/api/projects/claims/",
            {"project": self.project.id, "milestone": milestone.id, "claim_amount": str(amount), "declaration_accepted": True},
            format="json",
        )

    def _pay(self, claim_id):
        self.client.force_authenticate(self.tac)
        self.assertEqual(self.client.post(f"/api/projects/claims/{claim_id}/approve/", {}, format="json").status_code, 200)
        self.client.force_authenticate(self.psc)
        self.assertEqual(self.client.post(f"/api/projects/claims/{claim_id}/approve/", {}, format="json").status_code, 200)
        self.client.force_authenticate(self.rmt)
        response = self.client.post(f"/api/projects/claims/{claim_id}/confirm-paid/", {"payment_reference": f"REF-{claim_id}"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def _verify(self, claim_id, **payload):
        self.client.force_authenticate(self.rmt)
        return self.client.post(f"/api/projects/claims/{claim_id}/verify/", payload, format="json")

    def test_assessment_reports_verified_share_of_milestone(self):
        self._verified_installations(60)
        claim_id = self._submit(self.m2, 2000).data["id"]
        self.client.force_authenticate(self.rmt)
        response = self.client.get(f"/api/projects/claims/{claim_id}/assessment/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["expected_units"], 80)
        self.assertEqual(response.data["verified_units"], 60)
        self.assertEqual(response.data["completion_pct"], 75.0)
        self.assertTrue(response.data["partial_allowed"])
        self.assertEqual(response.data["partial_amount"], "1500.00")

        self.client.force_authenticate(self.vendor)
        self.assertEqual(self.client.get(f"/api/projects/claims/{claim_id}/assessment/").status_code, 403)

    def test_partial_payment_carries_shortfall_into_next_milestone(self):
        self._verified_installations(60)
        claim_id = self._submit(self.m2, 2000).data["id"]

        response = self._verify(claim_id, decision="partial")
        self.assertEqual(response.status_code, 400)
        self.assertIn("List what is still missing", response.data["detail"])

        response = self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_partial"])
        self.assertEqual(response.data["approved_amount"], "1500.00")
        self.assertEqual(response.data["shortfall_amount"], "500.00")
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.vendor.id), title="Milestone Claim Partially Approved By RMT").exists())

        self._pay(claim_id)
        self.assertEqual(Disbursement.objects.get(claim_id=claim_id).amount, Decimal("1500.00"))
        carry = MilestoneCarryOver.objects.get(from_claim_id=claim_id)
        self.assertEqual(carry.to_milestone, self.m3)
        self.assertEqual(carry.shortfall_amount, Decimal("500.00"))
        self.assertEqual(carry.shortfall_units, 20)
        self.assertEqual(carry.status, CarryOverStatus.PENDING)

        self.client.force_authenticate(self.rmt)
        response = self.client.post(
            f"/api/projects/milestones/{self.m2.id}/completion-review/",
            {"decision": "proceed", "verification_notes": "Proceed; 20 units owed."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        # M3 claim includes the carried shortfall: own 20 units + 20 carried = 40 expected.
        response = self._submit(self.m3, 3000)
        self.assertEqual(response.status_code, 201, response.data)
        m3_claim_id = response.data["id"]
        self.assertEqual(response.data["claim_amount"], "3500.00")
        self.assertEqual(response.data["carry_in_amount"], "500.00")
        self.assertEqual(response.data["carry_in_units"], 20)

        self._verified_installations(40)
        self.client.force_authenticate(self.rmt)
        assessment = self.client.get(f"/api/projects/claims/{m3_claim_id}/assessment/").data
        self.assertEqual((assessment["expected_units"], assessment["verified_units"]), (40, 40))
        self.assertTrue(assessment["is_final_milestone"])
        self.assertFalse(assessment["partial_allowed"])

        self.assertEqual(self._verify(m3_claim_id, decision="full").status_code, 200)
        self._pay(m3_claim_id)
        carry.refresh_from_db()
        self.assertEqual(carry.status, CarryOverStatus.SETTLED)
        self.assertEqual(carry.settled_by_claim_id, m3_claim_id)
        self.assertEqual(Disbursement.objects.get(claim_id=m3_claim_id).amount, Decimal("3500.00"))

    def test_partial_refused_below_minimum_and_claim_can_be_returned_and_resubmitted(self):
        self._verified_installations(52)  # 65% of M2's 80 units
        claim_id = self._submit(self.m2, 2000).data["id"]
        response = self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY)
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 70%", response.data["detail"])

        self.client.force_authenticate(self.rmt)
        response = self.client.post(f"/api/projects/claims/{claim_id}/return/", {"deficiencies": []}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            f"/api/projects/claims/{claim_id}/return/", {"deficiencies": DEFICIENCY, "remarks": "Finish installs"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], PaymentClaimStatus.RETURNED)
        self.assertEqual(response.data["verified_units"], 52)
        self.assertEqual(response.data["deficiencies"][0]["description"], DEFICIENCY[0]["description"])
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.vendor.id), event="payment_claim_returned").exists())
        self.m2.refresh_from_db()
        self.assertEqual(self.m2.status, "claimed")

        # A returned claim is resubmitted, not duplicated.
        response = self._submit(self.m2, 2000)
        self.assertEqual(response.status_code, 400)
        self.assertIn("resubmit", response.data["detail"])

        self.client.force_authenticate(self.other_vendor)
        self.assertEqual(self.client.post(f"/api/projects/claims/{claim_id}/resubmit/", {}, format="json").status_code, 404)

        self._verified_installations(28)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            f"/api/projects/claims/{claim_id}/resubmit/", {"implementation_notes": "All 80 installed."}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], PaymentClaimStatus.SUBMITTED)
        self.assertEqual(response.data["resubmission_count"], 1)
        self.assertEqual(self.client.post(f"/api/projects/claims/{claim_id}/resubmit/", {}, format="json").status_code, 400)

        response = self._verify(claim_id, decision="full")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["approved_amount"], "2000.00")
        self.assertFalse(response.data["is_partial"])

    def test_vendor_cannot_set_claim_status_or_approved_amount(self):
        claim_id = self._submit(self.m2, 2000).data["id"]
        self.client.force_authenticate(self.vendor)
        self.client.patch(
            f"/api/projects/claims/{claim_id}/",
            {"status": "Completed", "approved_amount": "9999.00", "declaration_accepted": True},
            format="json",
        )
        claim = PaymentClaim.objects.get(id=claim_id)
        self.assertEqual(claim.status, PaymentClaimStatus.SUBMITTED)
        self.assertIsNone(claim.approved_amount)

    def test_final_milestone_cannot_be_paid_partially(self):
        self.m2.status = "paid"
        self.m2.save()
        MilestoneCompletionReview.objects.create(milestone=self.m2, project=self.project, status="decided", decision="proceed")
        self._verified_installations(95)  # M3 own units 20; 15 verified = 75%
        claim_id = self._submit(self.m3, 3000).data["id"]
        response = self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY)
        self.assertEqual(response.status_code, 400)
        self.assertIn("final milestone", response.data["detail"])

    def test_milestone_without_installation_target_needs_assessed_pct(self):
        self.m1.status = "claimable"
        self.m1.save()
        MilestoneCompletionReview.objects.all().delete()
        claim_id = self._submit(self.m1, 1000).data["id"]
        response = self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY)
        self.assertEqual(response.status_code, 400)
        self.assertIn("assessed completion percentage", response.data["detail"])
        response = self._verify(claim_id, decision="partial", assessed_pct=80, deficiencies=DEFICIENCY)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["approved_amount"], "800.00")

    def test_rejection_after_partial_approval_clears_it(self):
        self._verified_installations(60)
        claim_id = self._submit(self.m2, 2000).data["id"]
        self.assertEqual(self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY).status_code, 200)
        self.client.force_authenticate(self.tac)
        response = self.client.post(f"/api/projects/claims/{claim_id}/reject/", {"remarks": "Recheck"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], PaymentClaimStatus.SUBMITTED)
        self.assertIsNone(response.data["approved_amount"])
        self.assertFalse(response.data["is_partial"])

    def test_closing_project_forfeits_pending_carry_over(self):
        self._verified_installations(60)
        claim_id = self._submit(self.m2, 2000).data["id"]
        self._verify(claim_id, decision="partial", deficiencies=DEFICIENCY)
        self._pay(claim_id)
        self.client.force_authenticate(self.rmt)
        response = self.client.post(
            f"/api/projects/milestones/{self.m2.id}/completion-review/",
            {"decision": "close", "verification_notes": "Vendor withdrew."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MilestoneCarryOver.objects.get(from_claim_id=claim_id).status, CarryOverStatus.FORFEITED)


class ClaimWriteProtectionTests(APITestCase):
    """Vendors cannot set money fields: claim amounts come from the milestone, claims are
    never edited or deleted in place, and milestones / projects are not vendor-writable."""

    def setUp(self):
        User = get_user_model()
        self.vendor = User.objects.create_user(username="wp_vendor", password="securePass123", role="Vendor", status="Active")
        self.tac = User.objects.create_user(username="wp_tac", password="securePass123", role="TAC Member", status="Active")
        self.project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name=self.vendor.username, tech_type="SHS",
            region="Maseru", district="Maseru", status=ProjectStatus.ACTIVE, project_reference="PRJ-WP-001",
        )
        self.m1 = self.project.milestones.create(name="M1", milestone_number=1, percentage=20, amount=1000, status="claimable")
        self.m2 = self.project.milestones.create(name="M2", milestone_number=2, percentage=80, amount=4000, status="locked")
        self.other_project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name=self.vendor.username, tech_type="SHS",
            region="Maseru", district="Maseru", status=ProjectStatus.ACTIVE, project_reference="PRJ-WP-002",
        )
        self.other_milestone = self.other_project.milestones.create(
            name="M1", milestone_number=1, percentage=100, amount=50000, status="claimable",
        )
        cache.clear()
        self.client.force_authenticate(self.vendor)

    def _claim(self, milestone=None, amount="999999.00", project=None):
        payload = {"project": (project or self.project).id, "claim_amount": amount, "declaration_accepted": True}
        if milestone is not None:
            payload["milestone"] = milestone.id
        return self.client.post("/api/projects/claims/", payload, format="json")

    def test_claim_amount_comes_from_the_milestone_not_the_vendor(self):
        response = self._claim(self.m1)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["claim_amount"], "1000.00")

    def test_claim_requires_a_claimable_milestone_of_the_same_project(self):
        self.assertEqual(self._claim(None).status_code, 400)
        response = self._claim(self.other_milestone)
        self.assertEqual(response.status_code, 400)
        self.assertIn("milestone", response.data)
        # M2 is still locked: its KPI conditions are not met.
        MilestoneCompletionReview.objects.create(milestone=self.m1, project=self.project, status="decided", decision="proceed")
        response = self._claim(self.m2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not claimable", response.data["detail"])
        self.assertFalse(PaymentClaim.objects.filter(milestone=self.m2).exists())

    def test_claims_cannot_be_edited_or_deleted(self):
        claim_id = self._claim(self.m1).data["id"]
        url = f"/api/projects/claims/{claim_id}/"
        self.assertEqual(self.client.patch(url, {"claim_amount": "5.00"}, format="json").status_code, 405)
        self.assertEqual(self.client.put(url, {"claim_amount": "5.00"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(PaymentClaim.objects.get(id=claim_id).claim_amount, Decimal("1000.00"))

    def test_vendor_cannot_write_milestones(self):
        url = f"/api/projects/milestones/{self.m2.id}/"
        self.assertEqual(self.client.patch(url, {"amount": "1.00", "status": "claimable"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        response = self.client.post(
            "/api/projects/milestones/", {"project": self.project.id, "name": "M4", "percentage": 10, "amount": "100.00"}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.m2.refresh_from_db()
        self.assertEqual((self.m2.status, self.m2.amount), ("locked", Decimal("4000.00")))

    def test_only_rmt_or_super_admin_create_projects_directly(self):
        payload = {"vendor_id": str(self.vendor.id), "vendor_name": "x", "tech_type": "SHS", "region": "Maseru"}
        self.assertEqual(self.client.post("/api/projects/", payload, format="json").status_code, 403)
        self.client.force_authenticate(self.tac)
        self.assertEqual(self.client.post("/api/projects/", payload, format="json").status_code, 403)
