import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
import subprocess

from rbf.notifications.models import Notification
from rbf.projects.models import AuditLog, Milestone, Project, ProjectStatus
from rbf.users.models import PlatformConfiguration, PrequalificationStatus, User, UserRole, VendorPrequalification

from .models import (
    BidStage,
    BidStatus,
    ContractSignatureStatus,
    ContractStatus,
    EvaluationStage,
    EvaluationStatus,
    EvaluationSubmissionStatus,
    EvaluationRevisionAction,
    Tender,
    TenderBid,
    TenderBidEvaluation,
    TenderBidEvaluationRevision,
    TenderBidLotOffer,
    TenderBidSite,
    TenderBoqItem,
    TenderContract,
    TenderEvaluationCommitteeMember,
    TenderLot,
    TenderStatus,
    EvaluationConflictOfInterest,
)
from .pba_pdf import _annex_section_html, _main_agreement_html, _pdfa_merge, generate_contract_pdf
from .serializers import TenderBidSiteSerializer, TenderContractSerializer


def _close_tender_for_evaluation(tender):
    """Simulate the submission deadline passing so evaluation may begin."""
    tender.status = TenderStatus.CLOSED
    tender.save(update_fields=['status'])


class TenderApiTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="tender_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Tender Admin",
        )

    def test_list_tenders(self):
        Tender.objects.create(
            reference_number="REF-100001",
            name="Sample Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now(),
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/tenders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["reference_number"], "REF-100001")

    def test_create_tender_accepts_frontend_optional_null_and_empty_values(self):
        self.client.force_authenticate(self.admin_user)
        payload = {
            "reference_number": "REF-100002",
            "name": "Frontend Payload Tender",
            "department": "RBF",
            "category": "Mini-Grid",
            "status": "Draft",
            "procurement_method": "National",
            "address_for_document": "Addr",
            "address_for_security": "Addr",
            "place_for_opening": "Maseru",
            "bidders_eligibility": "All",
            "time_for_completion": "12 months",
            "invited_by": "RBF",
            "bidding_currency": "LSL",
            "instruction": "Read carefully. " * 10,
            "contact_details": "123",
            "target_site_type": "Community",
            "application_type": "Application Window",
            "bidders_schedule_purchase": None,
            "tender_security_required": None,
            "is_verified": None,
            "technology_types": ["SHS"],
            "target_districts": ["Maseru"],
            "procurement_workflow": "sequential",
            "eoi_deadline": (timezone.now() + timedelta(days=3)).isoformat(),
            "technical_deadline": (timezone.now() + timedelta(days=6)).isoformat(),
            "financial_deadline": (timezone.now() + timedelta(days=9)).isoformat(),
        }

        response = self.client.post("/api/tenders/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["application_type"], "Application Window")
        self.assertEqual(response.data["bidding_currency"], "LSL")
        self.assertFalse(response.data["bidders_schedule_purchase"])
        self.assertFalse(response.data["tender_security_required"])
        self.assertFalse(response.data["is_verified"])
        self.assertEqual(response.data["technology_types"], ["SHS"])
        self.assertIsNotNone(response.data["eoi_deadline"])
        self.assertIsNotNone(response.data["deadline"])

    @override_settings(API_REQUIRE_AUTH=True)
    def test_create_tender_requires_auth_when_production_auth_enabled(self):
        payload = {
            "reference_number": "REF-100099",
            "name": "Restricted Tender",
            "department": "RBF",
            "category": "SHS",
            "status": "Draft",
            "deadline": timezone.now().isoformat(),
        }

        response = self.client.post("/api/tenders/", payload, format="json")

        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    @patch("rbf.tenders.views.generate_contract_pdf")
    def test_tender_lifecycle_verify_publish_award_generates_contract(self, mock_generate_contract_pdf):
        self.client.force_authenticate(self.admin_user)
        vendor = User.objects.create_user(
            username="awarded_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Awarded Vendor",
            organization_name="Solar Lease Ltd",
            email="vendor@example.com",
        )
        tender = Tender.objects.create(
            reference_number="REF-100200",
            name="Lifecycle Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now(),
            is_verified=False,
            technology_types=["Solar Home System"],
        )
        bid = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            vendor_email=vendor.email,
            bid_amount=125000,
            status=BidStatus.SUBMITTED,
        )
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=self.admin_user,
            status=EvaluationStatus.SCORED,
            technical_score=78,
            financial_score=74,
            feasibility_score=76,
            kpi_score=75,
            gender_score=80,
            environmental_score=73,
            om_score=72,
            inclusivity_score=77,
            total_score=76,
        )

        verify_response = self.client.post(f"/api/tenders/{tender.id}/verify/", {}, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.data["is_verified"])

        request_response = self.client.post(f"/api/tenders/{tender.id}/request_publish_approval/", {}, format="json")
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(request_response.data["publish_approval_status"], "pending")

        approve_response = self.client.post(f"/api/tenders/{tender.id}/approve_publish/", {}, format="json")
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["publish_approval_status"], "approved")

        publish_response = self.client.post(f"/api/tenders/{tender.id}/publish/", {}, format="json")

        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(publish_response.data["status"], TenderStatus.PUBLISHED)

        award_response = self.client.post(
            f"/api/tenders/{tender.id}/award/",
            {
                "bid_id": str(bid.id),
                "awarded_vendor_id": str(vendor.id),
                "awarded_vendor_name": vendor.full_name,
            },
            format="json",
        )

        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.assertEqual(award_response.data["status"], TenderStatus.STANDSTILL)

        tender.refresh_from_db()
        self.assertEqual(tender.status, TenderStatus.STANDSTILL)
        self.assertEqual(str(tender.intent_to_award_bid_id), str(bid.id))
        self.assertIsNotNone(tender.cooling_off_until)
        mock_generate_contract_pdf.assert_not_called()

        tender.cooling_off_until = timezone.now() - timedelta(minutes=1)
        tender.save(update_fields=["cooling_off_until"])

        confirm_response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], TenderStatus.AWARDED)
        self.assertIn("generated_contract", confirm_response.data)
        self.assertEqual(confirm_response.data["generated_contract"]["vendor_id"], str(vendor.id))
        self.assertEqual(confirm_response.data["generated_contract"]["bid"], str(bid.id))

        contract = TenderContract.objects.get(tender=tender, vendor_id=str(vendor.id))
        self.assertEqual(contract.status, ContractStatus.GENERATED)
        self.assertEqual(contract.bid_id, bid.id)
        self.assertIsNone(tender.cooling_off_until)
        mock_generate_contract_pdf.assert_called_once()

    def test_publish_approval_request_changes_returns_tender_to_draft_for_resubmission(self):
        """Super Admin can send a tender back for revisions (distinct from an outright
        reject) and the RBF can then resubmit it for approval without re-verifying."""
        self.client.force_authenticate(self.admin_user)
        tender = Tender.objects.create(
            reference_number="REF-CHANGES-001",
            name="Changes Requested Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now(),
            is_verified=True,
            technology_types=["Solar Home System"],
        )

        request_response = self.client.post(f"/api/tenders/{tender.id}/request_publish_approval/", {}, format="json")
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(request_response.data["publish_approval_status"], "pending")

        changes_response = self.client.post(
            f"/api/tenders/{tender.id}/request_publish_changes/",
            {"notes": "Please fix the budget figure and re-attach the BOQ."},
            format="json",
        )
        self.assertEqual(changes_response.status_code, status.HTTP_200_OK)
        self.assertEqual(changes_response.data["publish_approval_status"], "changes_requested")
        self.assertEqual(changes_response.data["status"], TenderStatus.DRAFT)

        tender.refresh_from_db()
        self.assertEqual(tender.publish_approval_status, "changes_requested")
        self.assertEqual(tender.publish_approval_notes, "Please fix the budget figure and re-attach the BOQ.")
        self.assertIsNotNone(tender.publish_approval_reviewed_at)

        # Sent back to Draft (not rejected outright) so the RBF can resubmit directly.
        resubmit_response = self.client.post(f"/api/tenders/{tender.id}/request_publish_approval/", {}, format="json")
        self.assertEqual(resubmit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(resubmit_response.data["publish_approval_status"], "pending")

    def test_publish_approval_request_changes_requires_admin_role(self):
        vendor = User.objects.create_user(
            username="changes_test_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Non Admin Vendor",
        )
        tender = Tender.objects.create(
            reference_number="REF-CHANGES-002",
            name="Non Admin Changes Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.PENDING_PUBLISH_APPROVAL,
            deadline=timezone.now(),
            is_verified=True,
            publish_approval_status="pending",
        )
        self.client.force_authenticate(vendor)
        response = self.client.post(f"/api/tenders/{tender.id}/request_publish_changes/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_award_changes_status_to_standstill(self):
        self.client.force_authenticate(self.admin_user)
        vendor = User.objects.create_user(
            username="standstill_test_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Standstill Test Vendor",
        )
        tender = Tender.objects.create(
            reference_number="STNDST-001",
            name="Standstill Test",
            department="DoE",
            category="SHS",
            status=TenderStatus.EVALUATION,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
        )
        bid = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_amount=100000,
            status=BidStatus.SUBMITTED,
        )
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            total_score=62,
        )
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=74,
            financial_score_auto_calculated=True,
            total_score=74,
        )

        response = self.client.post(
            f"/api/tenders/{tender.id}/award/",
            {"bid_id": str(bid.id), "awarded_vendor_id": str(vendor.id), "awarded_vendor_name": vendor.full_name},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], TenderStatus.STANDSTILL)
        tender.refresh_from_db()
        self.assertEqual(tender.status, TenderStatus.STANDSTILL)
        self.assertIsNotNone(tender.cooling_off_until)

    def test_confirm_award_rejects_disputed_status(self):
        self.client.force_authenticate(self.admin_user)
        vendor = User.objects.create_user(
            username="disputed_confirm_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Disputed Confirm Vendor",
        )
        tender = Tender.objects.create(
            reference_number="DSP-CNF-001",
            name="Disputed Confirm",
            department="DoE",
            category="SHS",
            status=TenderStatus.DISPUTED,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
            intent_to_award_bid=None,
            cooling_off_until=timezone.now() - timedelta(days=1),
        )

        response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dispute", response.data["detail"].lower())

    def test_confirm_award_rejects_cooling_off_not_expired(self):
        self.client.force_authenticate(self.admin_user)
        vendor = User.objects.create_user(
            username="cooling_not_expired",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Cooling Not Expired",
        )
        tender = Tender.objects.create(
            reference_number="COOL-001",
            name="Cooling Not Expired",
            department="DoE",
            category="SHS",
            status=TenderStatus.STANDSTILL,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
        )
        bid = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_amount=100000,
            status=BidStatus.SUBMITTED,
        )
        tender.intent_to_award_bid = bid
        tender.cooling_off_until = timezone.now() + timedelta(days=7)
        tender.save()

        response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cooling-off", response.data["detail"].lower())

    def test_confirm_award_rejects_already_awarded(self):
        self.client.force_authenticate(self.admin_user)
        tender = Tender.objects.create(
            reference_number="ALR-AWD-001",
            name="Already Awarded",
            department="DoE",
            category="SHS",
            status=TenderStatus.AWARDED,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
        )

        response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been awarded", response.data["detail"].lower())

    def test_confirm_award_rejects_no_intent(self):
        self.client.force_authenticate(self.admin_user)
        tender = Tender.objects.create(
            reference_number="NO-INT-001",
            name="No Intent",
            department="DoE",
            category="SHS",
            status=TenderStatus.STANDSTILL,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
        )

        response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("intent to award must be issued", response.data["detail"].lower())

    def test_confirm_award_rejects_closed_tender(self):
        self.client.force_authenticate(self.admin_user)
        tender = Tender.objects.create(
            reference_number="CLS-CNF-001",
            name="Closed Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.CLOSED,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
        )

        response = self.client.post(
            f"/api/tenders/{tender.id}/confirm_award/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("closed tender", response.data["detail"].lower())

    def test_award_ranking_recommends_best_value_not_lowest_price(self):
        self.client.force_authenticate(self.admin_user)
        vendor_a = User.objects.create_user(
            username="best_value_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Best Value Vendor",
            organization_name="Best Value Vendor Ltd",
        )
        vendor_b = User.objects.create_user(
            username="lowest_price_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Lowest Price Vendor",
            organization_name="Lowest Price Vendor Ltd",
        )
        VendorPrequalification.objects.create(
            vendor=vendor_a,
            company_name="Best Value Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            female_beneficiary_target=60,
        )
        VendorPrequalification.objects.create(
            vendor=vendor_b,
            company_name="Lowest Price Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            female_beneficiary_target=50,
        )
        tender = Tender.objects.create(
            reference_number="REF-RANK-001",
            name="Weighted Ranking Tender",
            department="DoE",
            category="Mini-Grid",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now(),
            technical_weight=70,
            financial_weight=30,
            technical_threshold=70,
            cooling_off_days=7,
        )
        bid_a = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor_a.id),
            vendor_name=vendor_a.full_name,
            bid_amount=100000,
            status=BidStatus.SUBMITTED,
        )
        bid_b = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor_b.id),
            vendor_name=vendor_b.full_name,
            bid_amount=90000,
            status=BidStatus.SUBMITTED,
        )
        TenderBidEvaluation.objects.create(
            bid=bid_a,
            evaluator=self.admin_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=80,
            feasibility_score=80,
            kpi_score=80,
            gender_score=75,
            environmental_score=80,
            om_score=80,
            inclusivity_score=75,
            total_score=80,
        )
        TenderBidEvaluation.objects.create(
            bid=bid_a,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=70,
            financial_score_auto_calculated=True,
            total_score=70,
        )
        TenderBidEvaluation.objects.create(
            bid=bid_b,
            evaluator=self.admin_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=75,
            feasibility_score=75,
            kpi_score=75,
            gender_score=60,
            environmental_score=75,
            om_score=75,
            inclusivity_score=65,
            total_score=75,
        )
        TenderBidEvaluation.objects.create(
            bid=bid_b,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=80,
            financial_score_auto_calculated=True,
            total_score=80,
        )

        ranking_response = self.client.get(f"/api/tenders/{tender.id}/award_ranking/")

        self.assertEqual(ranking_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ranking_response.data["recommended"]["bid_id"], str(bid_a.id))
        self.assertEqual(ranking_response.data["recommended"]["vendor_id"], str(vendor_a.id))
        self.assertGreater(
            ranking_response.data["rows"][0]["combined_score"],
            ranking_response.data["rows"][1]["combined_score"],
        )

    def test_award_ranking_uses_latest_active_bid_per_vendor(self):
        self.client.force_authenticate(self.admin_user)
        vendor = User.objects.create_user(
            username="single_vendor_versions",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Single Vendor",
            organization_name="Single Vendor Ltd",
        )
        VendorPrequalification.objects.create(
            vendor=vendor,
            company_name="Single Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            female_beneficiary_target=55,
        )
        tender = Tender.objects.create(
            reference_number="REF-RANK-002",
            name="Latest Bid Ranking Tender",
            department="DoE",
            category="Mini-Grid",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now(),
            technical_weight=70,
            financial_weight=30,
            technical_threshold=70,
            cooling_off_days=7,
        )
        older_bid = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_amount=15000,
            status=BidStatus.ACCEPTED,
            version_number=1,
        )
        latest_bid = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_amount=15000,
            status=BidStatus.SUBMITTED,
            version_number=2,
        )
        TenderBidEvaluation.objects.create(
            bid=latest_bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=8,
            total_score=85,
        )
        TenderBidEvaluation.objects.create(
            bid=latest_bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=24,
            financial_score_auto_calculated=True,
            total_score=24,
        )

        ranking_response = self.client.get(f"/api/tenders/{tender.id}/award_ranking/")

        self.assertEqual(ranking_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ranking_response.data["rows"]), 1)
        self.assertEqual(ranking_response.data["rows"][0]["bid_id"], str(latest_bid.id))
        self.assertEqual(ranking_response.data["recommended"]["bid_id"], str(latest_bid.id))


class TenderBidSubmissionTests(APITestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username="bid_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Bid Vendor",
            organization_name="Bid Vendor Ltd",
            email="bid-vendor@example.com",
        )
        self.rmt_user = User.objects.create_user(
            username="rmt_eval",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="RMT Evaluator",
            email="rmt-eval@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="Bid Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )
        self.prequal_tender = Tender.objects.create(
            reference_number="REF-BID-001",
            name="Pre-Qualification Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=7),
            eoi_deadline=timezone.now() + timedelta(days=7),
            stage_type="pre_qualification",
            technology_types=["SHS"],
        )
        self.site_specific_tender = Tender.objects.create(
            reference_number="REF-BID-002",
            name="Site Specific Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=7),
            eoi_deadline=timezone.now() + timedelta(days=7),
            stage_type="site_specific",
            technology_types=["SHS"],
        )
        self.client.force_authenticate(self.vendor)

    def _submission_basics(self):
        return {
            "subsidy_requested": "100000.00",
            "device_brand_model": "SunPower SPX-200",
            "tech_tier": "Tier 3",
            "energy_target": "450.00",
            "warranty_period": "24",
        }

    def _eoi_upload(self, name):
        return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")

    def _eoi_fields(self):
        return {
            "eoi_narrative": "Expression of interest for community clean energy installations. " * 16,
            "company_credentials_file": self._eoi_upload("credentials.pdf"),
            "financial_standing_file": self._eoi_upload("standing.pdf"),
            "technical_experience_file": self._eoi_upload("experience.pdf"),
            "track_record_file": self._eoi_upload("track.pdf"),
            "female_target_pct": 55,
            "vulnerable_target_pct": 35,
            "low_income_target_pct": 60,
            "inclusion_commitment_confirmed": "true",
        }

    def _valid_eoi_payload(self, **overrides):
        payload = {
            "tender": str(self.prequal_tender.id),
            "bid_stage": "eoi",
            "status": BidStatus.SUBMITTED,
            **self._eoi_fields(),
        }
        payload.update(overrides)
        return payload

    def _valid_technical_payload(self, **overrides):
        payload = {
            "tender": str(self.site_specific_tender.id),
            "bid_stage": "technical",
            "bid_amount": "180000.00",
            **self._submission_basics(),
            "technical_proposal": "Technical approach narrative. " * 20,
            "financial_proposal": "Financial approach narrative. " * 20,
            "system_configuration": json.dumps({
                "technology_type": "SHS",
                "rated_power_w": 250,
                "battery_capacity_wh": 1200,
                "pv_panel_size_w": 300,
                "inverter_type": "Hybrid",
            }),
            "boq_items": json.dumps([
                {"item_number": 1, "description": "Solar kit", "qty": 100, "unit": "set", "unit_price": 1800, "total": 180000},
            ]),
            "om_strategy_summary": "O&M strategy covering preventative maintenance and local technicians. " * 6,
            "female_target_pct": 55,
            "vulnerable_target_pct": 35,
            "low_income_target_pct": 60,
            "inclusion_commitment_confirmed": "true",
            "sites": json.dumps([
                {
                    "site_name": "Roma Cluster",
                    "district": "Maseru",
                    "village_sub_district": "Roma",
                    "latitude": -29.45,
                    "longitude": 27.71,
                    "number_of_households": 40,
                    "target_beneficiary_type": "female_headed",
                    "estimated_energy_demand_kwh_month": 450,
                    "road_access_available": True,
                    "notes": "Good road access.",
                }
            ]),
            "technical_proposal_file": self._eoi_upload("technical.pdf"),
            "financial_proposal_file": self._eoi_upload("financial.pdf"),
            "boq_file": self._eoi_upload("boq.xlsx"),
            "gender_action_plan_file": self._eoi_upload("gap.pdf"),
            "implementation_plan_file": self._eoi_upload("implementation.pdf"),
            "om_plan_file": self._eoi_upload("om.pdf"),
            "status": BidStatus.SUBMITTED,
        }
        payload.update(overrides)
        return payload

    def _create_technical_draft(self, tender=None):
        """Create a valid EOI bid, accept it as RMT, return the unlocked technical draft."""
        tender = tender or self.site_specific_tender
        self.client.force_authenticate(self.vendor)
        resp = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Expression of interest for community clean energy installations. " * 16,
                "company_credentials_file": self._eoi_upload("credentials.pdf"),
                "financial_standing_file": self._eoi_upload("standing.pdf"),
                "technical_experience_file": self._eoi_upload("experience.pdf"),
                "track_record_file": self._eoi_upload("track.pdf"),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{resp.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        self.client.force_authenticate(self.vendor)
        draft = TenderBid.objects.filter(
            tender=tender,
            vendor_id=str(self.vendor.id),
            bid_stage="technical",
            status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(draft)
        return draft

    def test_prequalification_submission_uses_tender_stage_and_records_audit(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                **self._valid_eoi_payload(),
                "bid_amount": "150000.00",
                "system_configuration": json.dumps({
                    "technology_type": "SHS",
                    "rated_power_w": 250,
                    "battery_capacity_wh": 1200,
                    "pv_panel_size_w": 300,
                    "inverter_type": "Hybrid",
                }),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bid = TenderBid.objects.get(id=response.data["id"])
        self.assertEqual(bid.bid_stage, BidStage.EOI)
        self.assertEqual(response.data["stage"], "EOI")
        self.assertEqual(response.data["stage_key"], "eoi")
        self.assertEqual(response.data["technology_type"], "SHS")
        self.assertEqual(bid.system_configuration["rated_power_w"], 250)
        self.assertTrue(
            AuditLog.objects.filter(
                action="bid_submitted",
                record_id=bid.id,
            ).exists()
        )

    def test_restricted_tender_rejects_non_invited_vendor(self):
        from .models import ProcurementMethod
        self.prequal_tender.procurement_method = ProcurementMethod.RESTRICTED
        self.prequal_tender.save(update_fields=["procurement_method"])

        response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("only specifically invited vendors can bid", str(response.data))

    def test_restricted_tender_allows_invited_vendor(self):
        from .models import ProcurementMethod, TenderInvitedVendor
        self.prequal_tender.procurement_method = ProcurementMethod.RESTRICTED
        self.prequal_tender.save(update_fields=["procurement_method"])
        TenderInvitedVendor.objects.create(tender=self.prequal_tender, vendor=self.vendor)

        response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_restricted_tender_hidden_from_non_invited_vendor_list(self):
        from .models import ProcurementMethod, TenderInvitedVendor
        self.prequal_tender.procurement_method = ProcurementMethod.RESTRICTED
        self.prequal_tender.save(update_fields=["procurement_method"])

        response = self.client.get("/api/tenders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        tender_ids = [str(t["id"]) for t in response.data.get("results", response.data)]
        self.assertNotIn(str(self.prequal_tender.id), tender_ids)
        self.assertIn(str(self.site_specific_tender.id), tender_ids)

        TenderInvitedVendor.objects.create(tender=self.prequal_tender, vendor=self.vendor)
        response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in response.data.get("results", response.data)]
        self.assertIn(str(self.prequal_tender.id), tender_ids)

    def test_custom_restricted_procurement_method_gates_visibility_and_bidding(self):
        """A Super-Admin-configured CUSTOM procurement method (not the built-in
        'Restricted Tendering' string) must drive the same restricted-vendor gating
        as the built-in — proving the gate is a dynamic config lookup, not a
        hardcoded string comparison."""
        PlatformConfiguration.objects.create(
            procurement_methods=[{"value": "Selective Tendering", "visibilityMode": "restricted"}],
        )
        self.prequal_tender.procurement_method = "Selective Tendering"
        self.prequal_tender.save(update_fields=["procurement_method"])

        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertNotIn(str(self.prequal_tender.id), tender_ids)

        bid_response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_400_BAD_REQUEST, bid_response.data)
        self.assertIn("only specifically invited vendors can bid", str(bid_response.data))

        from .models import TenderInvitedVendor
        TenderInvitedVendor.objects.create(tender=self.prequal_tender, vendor=self.vendor)
        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertIn(str(self.prequal_tender.id), tender_ids)

        bid_response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_201_CREATED, bid_response.data)

    def test_rfq_procurement_method_behaves_like_restricted(self):
        """RFQ mode reuses the exact same invited-vendor gate as Restricted — it has
        no gating logic of its own, only a different label/convention."""
        PlatformConfiguration.objects.create(
            procurement_methods=[{"value": "Request for Quotation", "visibilityMode": "rfq"}],
        )
        self.prequal_tender.procurement_method = "Request for Quotation"
        self.prequal_tender.save(update_fields=["procurement_method"])

        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertNotIn(str(self.prequal_tender.id), tender_ids)

        from .models import TenderInvitedVendor
        TenderInvitedVendor.objects.create(tender=self.prequal_tender, vendor=self.vendor)
        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertIn(str(self.prequal_tender.id), tender_ids)

        bid_response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_201_CREATED, bid_response.data)

    def test_limited_single_source_procurement_method_caps_invites_at_one(self):
        """Limited/Single-Source uses the same invited-vendor gate as Restricted, but
        the invite-management endpoint must reject directing it to more than one
        vendor."""
        PlatformConfiguration.objects.create(
            procurement_methods=[{"value": "Sole Source", "visibilityMode": "limited"}],
        )
        self.prequal_tender.procurement_method = "Sole Source"
        self.prequal_tender.save(update_fields=["procurement_method"])

        other_vendor = User.objects.create_user(
            username="sole_source_other_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Other Vendor",
            email="sole-source-other@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=other_vendor,
            company_name="Other Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
        )

        self.client.force_authenticate(self.rmt_user)
        two_vendor_response = self.client.post(
            f"/api/tenders/{self.prequal_tender.id}/invited_vendors/",
            {"vendor_ids": [str(self.vendor.id), str(other_vendor.id)]},
            format="json",
        )
        self.assertEqual(two_vendor_response.status_code, status.HTTP_400_BAD_REQUEST, two_vendor_response.data)

        one_vendor_response = self.client.post(
            f"/api/tenders/{self.prequal_tender.id}/invited_vendors/",
            {"vendor_ids": [str(self.vendor.id)]},
            format="json",
        )
        self.assertEqual(one_vendor_response.status_code, status.HTTP_200_OK, one_vendor_response.data)

        self.client.force_authenticate(self.vendor)
        bid_response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_201_CREATED, bid_response.data)

    def test_framework_procurement_method_gates_by_tier_and_technology_with_no_invite_list(self):
        """Framework/Pre-Qualified Pool has no invite list at all — visibility and
        bidding are gated purely by the vendor's own approved pre-qualification tier
        and technology types against the tender's minimum_service_tier/technology_types."""
        PlatformConfiguration.objects.create(
            procurement_methods=[{"value": "Framework Agreement", "visibilityMode": "framework"}],
        )
        self.prequal_tender.procurement_method = "Framework Agreement"
        self.prequal_tender.technology_types = ["SHS"]
        self.prequal_tender.minimum_service_tier = "Tier 3"
        self.prequal_tender.save(update_fields=["procurement_method", "technology_types", "minimum_service_tier"])

        # self.vendor is prequalified at "Level 3" per setUp — align its
        # technology_types to SHS explicitly for this test.
        prequal = VendorPrequalification.objects.filter(vendor=self.vendor).order_by('-submitted_at', '-id').first()
        prequal.tech_tier = "Level 3"
        prequal.technology_types = ["SHS"]
        prequal.save(update_fields=["tech_tier", "technology_types"])

        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertIn(str(self.prequal_tender.id), tender_ids)

        bid_response = self.client.post(
            "/api/tender-bids/",
            {**self._valid_eoi_payload(), "bid_amount": "150000.00"},
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_201_CREATED, bid_response.data)

        # A lower-tier / non-matching-technology vendor must not see or be able to bid.
        low_tier_vendor = User.objects.create_user(
            username="framework_low_tier_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Low Tier Vendor",
            email="framework-low-tier@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=low_tier_vendor,
            company_name="Low Tier Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 1",
            technology_types=["SHS"],
        )
        self.client.force_authenticate(low_tier_vendor)
        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertNotIn(str(self.prequal_tender.id), tender_ids)

        bid_response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_stage": "eoi",
                **self._eoi_fields(),
            },
            format="multipart",
        )
        self.assertEqual(bid_response.status_code, status.HTTP_400_BAD_REQUEST, bid_response.data)

        non_matching_tech_vendor = User.objects.create_user(
            username="framework_gmg_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="GMG Vendor",
            email="framework-gmg@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=non_matching_tech_vendor,
            company_name="GMG Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 5",
            technology_types=["GMG"],
        )
        self.client.force_authenticate(non_matching_tech_vendor)
        list_response = self.client.get("/api/tenders/")
        tender_ids = [str(t["id"]) for t in list_response.data.get("results", list_response.data)]
        self.assertNotIn(str(self.prequal_tender.id), tender_ids)

    def test_site_specific_submission_requires_all_documents_and_summaries(self):
        from .models import TenderRequiredDocument
        TenderRequiredDocument.objects.create(
            tender=self.site_specific_tender, name="Technical Proposal",
            bid_stage="technical", field_key="technical_proposal_file", position=1,
        )
        TenderRequiredDocument.objects.create(
            tender=self.site_specific_tender, name="Bill of Quantities",
            bid_stage="technical", field_key="boq_file", position=2,
        )
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload()
        for key in ("technical_proposal_file", "boq_file"):
            payload.pop(key, None)
        response = self.client.patch(
            f"/api/tender-bids/{draft.id}/",
            payload,
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("technical_proposal_file", response.data)
        self.assertIn("boq_file", response.data)
        # The Financial Proposal document is no longer required at the Technical stage.
        self.assertNotIn("financial_proposal_file", response.data)

    def test_stage_one_submission_requires_inclusion_confirmation(self):
        payload = self._valid_eoi_payload(inclusion_commitment_confirmed="false")
        response = self.client.post(
            "/api/tender-bids/",
            payload,
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("inclusion_commitment_confirmed", response.data)

    def test_stage_one_submission_does_not_require_sites(self):
        payload = self._valid_eoi_payload(sites=json.dumps([]))
        response = self.client.post(
            "/api/tender-bids/",
            payload,
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["stage_key"], BidStage.EOI)
        self.assertEqual(response.data["sites"], [])

    def test_stage_one_submission_requires_minimum_concept_note_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            self._valid_eoi_payload(eoi_narrative="Too short"),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("eoi_narrative", response.data)

    def test_stage_one_submission_rejects_concept_note_under_200_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            self._valid_eoi_payload(eoi_narrative="A" * 199),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("eoi_narrative", response.data)

    def test_stage_one_submission_accepts_concept_note_at_200_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            self._valid_eoi_payload(eoi_narrative="A" * 200),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_site_specific_submission_rejects_coordinates_outside_lesotho(self):
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload(
            sites=json.dumps([
                {
                    "site_name": "Outside Lesotho",
                    "district": "Maseru",
                    "latitude": -26.2041,
                    "longitude": 28.0473,
                    "target_beneficiary_type": "female_headed",
                    "number_of_households": 15,
                }
            ]),
        )
        response = self.client.patch(
            f"/api/tender-bids/{draft.id}/",
            payload,
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sites", response.data)

    def test_site_specific_submission_rejects_tier_above_prequalification(self):
        draft = self._create_technical_draft()
        response = self.client.patch(
            f"/api/tender-bids/{draft.id}/",
            self._valid_technical_payload(tech_tier="Tier 4"),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tech_tier", response.data)

    def test_technical_bid_with_boq_template_locks_description_unit_quantity(self):
        """When the RBF designed a BOQ for this tender, only the vendor's unit price is
        trusted; description/unit/quantity always come from the template even if the
        vendor's submitted row tries to override them."""
        item1 = TenderBoqItem.objects.create(
            tender=self.site_specific_tender, description="Solar kit A", unit="set", quantity=Decimal("10"), position=0,
        )
        item2 = TenderBoqItem.objects.create(
            tender=self.site_specific_tender, description="Cabling", unit="m", quantity=Decimal("50"), position=1,
        )
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload(
            boq_items=json.dumps([
                {"template_item_id": item1.id, "description": "TAMPERED", "qty": 999, "unit_price": 500},
                {"template_item_id": item2.id, "unit_price": 20},
            ]),
        )
        response = self.client.patch(f"/api/tender-bids/{draft.id}/", payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        bid = TenderBid.objects.get(id=draft.id)
        by_id = {row["template_item_id"]: row for row in bid.boq_items}
        self.assertEqual(by_id[item1.id]["description"], "Solar kit A")
        self.assertEqual(by_id[item1.id]["qty"], "10.00")
        self.assertEqual(by_id[item1.id]["unit_price"], "500")
        self.assertEqual(by_id[item1.id]["total"], "5000.00")
        self.assertEqual(by_id[item2.id]["description"], "Cabling")
        self.assertEqual(by_id[item2.id]["total"], "1000.00")

    def test_technical_bid_with_boq_template_rejects_missing_unit_price(self):
        item1 = TenderBoqItem.objects.create(
            tender=self.site_specific_tender, description="Solar kit A", unit="set", quantity=Decimal("10"), position=0,
        )
        TenderBoqItem.objects.create(
            tender=self.site_specific_tender, description="Cabling", unit="m", quantity=Decimal("50"), position=1,
        )
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload(
            boq_items=json.dumps([
                {"template_item_id": item1.id, "unit_price": 500},
            ]),
        )
        response = self.client.patch(f"/api/tender-bids/{draft.id}/", payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("boq_items", response.data)
        self.assertIn("Cabling", str(response.data["boq_items"]))

    def test_technical_bid_submission_persists_every_submitted_field(self):
        """End-to-end guard: everything a vendor enters on the Technical stage must
        actually be saved and readable back afterwards, not just accepted by the write
        request. Submits a full Technical payload, then re-fetches the bid with a fresh
        GET (not the write response) to prove it was actually persisted to the database."""
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload(
            system_configuration=json.dumps({
                "technology_type": "SHS",
                "device_brand": "SunPower",
                "device_model": "SPX-200",
                "rated_power_w": 250,
                "battery_capacity_wh": 1200,
                "pv_panel_size_w": 300,
                "inverter_type": "Hybrid",
            }),
            warranty_period_months="24",
            local_technicians_to_be_trained="3",
            offer_paygo="true",
            paygo_platform="M-KOPA",
            daily_payment_amount_lsl="12.50",
            collection_method="Mobile Money",
        )
        response = self.client.patch(f"/api/tender-bids/{draft.id}/", payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Re-fetch with a separate GET so this proves persistence, not just an echo of
        # the write request/response.
        refetched = self.client.get(f"/api/tender-bids/{draft.id}/")
        self.assertEqual(refetched.status_code, status.HTTP_200_OK)
        data = refetched.data

        self.assertEqual(data["status"], BidStatus.SUBMITTED)
        self.assertEqual(data["device_brand_model"], "SunPower SPX-200")
        self.assertEqual(data["tech_tier"], "Tier 3")
        self.assertEqual(Decimal(str(data["energy_target_kwh_month"])), Decimal("450.00"))
        self.assertEqual(data["warranty_period_months"], 24)
        self.assertEqual(data["local_technicians_to_be_trained"], 3)
        self.assertTrue(data["offer_paygo"])
        self.assertEqual(data["paygo_platform"], "M-KOPA")
        self.assertEqual(Decimal(str(data["daily_payment_amount_lsl"])), Decimal("12.50"))
        self.assertEqual(data["collection_method"], "Mobile Money")
        self.assertEqual(data["female_target_pct"], 55)
        self.assertEqual(data["vulnerable_target_pct"], 35)
        self.assertEqual(data["low_income_target_pct"], 60)
        self.assertTrue(data["om_strategy_summary"].startswith("O&M strategy"))

        sysconfig = data["system_configuration"]
        self.assertEqual(sysconfig["technology_type"], "SHS")
        self.assertEqual(sysconfig["device_brand"], "SunPower")
        self.assertEqual(sysconfig["device_model"], "SPX-200")
        self.assertEqual(sysconfig["rated_power_w"], 250)
        self.assertEqual(sysconfig["battery_capacity_wh"], 1200)
        self.assertEqual(sysconfig["pv_panel_size_w"], 300)
        self.assertEqual(sysconfig["inverter_type"], "Hybrid")

        self.assertEqual(len(data["boq_items"]), 1)
        boq_row = data["boq_items"][0]
        self.assertEqual(boq_row["description"], "Solar kit")
        self.assertEqual(int(boq_row["qty"]), 100)
        self.assertEqual(boq_row["unit"], "set")
        self.assertEqual(Decimal(str(boq_row["unit_price"])), Decimal("1800"))

        self.assertEqual(len(data["sites"]), 1)
        site = data["sites"][0]
        self.assertEqual(site["site_name"], "Roma Cluster")
        self.assertEqual(site["district"], "Maseru")
        self.assertEqual(site["village_sub_district"], "Roma")
        self.assertEqual(Decimal(str(site["latitude"])), Decimal("-29.450000"))
        self.assertEqual(Decimal(str(site["longitude"])), Decimal("27.710000"))
        self.assertEqual(site["number_of_households"], 40)
        self.assertEqual(site["target_beneficiary_type"], "female_headed")
        self.assertEqual(Decimal(str(site["estimated_energy_demand_kwh_month"])), Decimal("450"))
        self.assertTrue(site["road_access_available"])
        self.assertEqual(site["notes"], "Good road access.")

        for key in (
            "technical_proposal_file", "financial_proposal_file", "boq_file",
            "gender_action_plan_file", "implementation_plan_file", "om_plan_file",
        ):
            self.assertTrue(data[key], f"{key} was not persisted")

    def test_financial_submission_after_technical_pass_is_not_blocked_as_duplicate(self):
        """Regression guard: each *_source_bid field only points one hop back (a
        Financial draft's financial_stage_source_bid points at the Technical bid, not
        the EOI bid further up the chain). The duplicate-submission check must walk the
        FULL lineage, not just one hop, or a vendor's own earlier, already-decided EOI
        bid gets mistaken for "an existing submitted bid" and blocks Financial
        submission with 'You have already submitted a bid for this tender.'"""
        draft = self._create_technical_draft()
        technical_response = self.client.patch(
            f"/api/tender-bids/{draft.id}/", self._valid_technical_payload(), format="multipart"
        )
        self.assertEqual(technical_response.status_code, status.HTTP_200_OK, technical_response.data)

        ec_user = User.objects.create_user(
            username="tac_financial_unblock",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Financial Unblock",
            email="tac-financial-unblock@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        self.client.force_authenticate(ec_user)
        review_response = self.client.post(f"/api/tender-bids/{draft.id}/review/", {}, format="json")
        self.assertEqual(review_response.status_code, status.HTTP_200_OK, review_response.data)
        score_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(draft.id),
                "stage": "technical",
                "technical_score": 20,
                "feasibility_score": 15,
                "kpi_score": 10,
                "gender_score": 10,
                "environmental_score": 5,
                "om_score": 10,
                "inclusivity_score": 0,
                "comments": "Clears threshold.",
            },
            format="json",
        )
        self.assertEqual(score_response.status_code, status.HTTP_201_CREATED, score_response.data)

        self.client.force_authenticate(self.rmt_user)
        open_response = self.client.post(
            f"/api/tenders/{self.site_specific_tender.id}/open_financial_stage/", {}, format="json"
        )
        self.assertEqual(open_response.status_code, status.HTTP_200_OK, open_response.data)

        financial_draft = TenderBid.objects.filter(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            bid_stage="financial",
            status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(financial_draft)

        self.client.force_authenticate(self.vendor)
        submit_response = self.client.patch(
            f"/api/tender-bids/{financial_draft.id}/",
            {"bid_amount": "180000.00", "subsidy_requested": "100000.00", "status": "Submitted"},
            format="multipart",
        )
        self.assertEqual(submit_response.status_code, status.HTTP_200_OK, submit_response.data)
        self.assertEqual(submit_response.data["status"], BidStatus.SUBMITTED)

    def test_rmt_financial_evaluation_requires_technical_threshold_pass(self):
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            status=BidStatus.SUBMITTED,
        )
        ec_user = self.vendor.__class__.objects.create_user(
            username="tac_low",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Low Score",
            email="tac-low@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=ec_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=60,
            feasibility_score=60,
            kpi_score=60,
            gender_score=60,
            environmental_score=60,
            om_score=60,
            inclusivity_score=60,
            total_score=60,
        )

        _close_tender_for_evaluation(self.site_specific_tender)
        self.client.force_authenticate(ec_user)
        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "stage": "financial", "comments": "Ready for finance review."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_rmt_financial_evaluation_is_allowed_after_technical_threshold_pass(self):
        self.site_specific_tender.technical_threshold = 70
        self.site_specific_tender.save(update_fields=["technical_threshold"])
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
        )
        tac_user = self.vendor.__class__.objects.create_user(
            username="tac_pass",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Pass Score",
            email="tac-pass@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=tac_user, coi_attested=True, coi_attested_at=timezone.now())
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=tac_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=20,
            feasibility_score=15,
            kpi_score=10,
            gender_score=10,
            environmental_score=5,
            om_score=10,
            inclusivity_score=0,
            total_score=70,
        )

        _close_tender_for_evaluation(self.site_specific_tender)
        self.client.force_authenticate(tac_user)
        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "financial",
                "comments": "Financial review complete.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # This is the only qualifying bid for the tender, so it is its own lowest price:
        # 100 x (its own bid_amount) / (its own bid_amount) = 100.
        self.assertEqual(response.data["financial_score"], 100)

    def test_financial_scoring_converts_bids_to_base_currency_before_comparing(self):
        # Deliberately crafted so the RAW numbers would rank the wrong bid as cheapest:
        # bid A is 180000 (base currency, blank bid_currency), bid B is 9500 USD at a
        # rate of 20 -> 190000 in base-currency terms. A is genuinely cheaper once
        # converted, even though its raw number (180000) is far larger than B's (9500).
        # If currency conversion were NOT applied, B's raw 9500 would be treated as the
        # lowest price and score 100, with A scoring a tiny fraction — the opposite of
        # the correct outcome asserted below.
        self.site_specific_tender.technical_threshold = 70
        self.site_specific_tender.bidding_currency = "LSL"
        self.site_specific_tender.currency_rates = {"USD": "20"}
        self.site_specific_tender.save(update_fields=["technical_threshold", "bidding_currency", "currency_rates"])

        competitor = self.vendor.__class__.objects.create_user(
            username="currency_competitor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Currency Competitor",
            organization_name="Currency Competitor Ltd",
            email="currency-competitor@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=competitor,
            company_name="Currency Competitor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
        )

        bid_a = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            bid_currency="",
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
        )
        bid_b = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(competitor.id),
            vendor_name=competitor.full_name,
            vendor_email=competitor.email,
            bid_amount=9500,
            bid_currency="USD",
            subsidy_requested=5000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
        )

        tac_user = self.vendor.__class__.objects.create_user(
            username="tac_currency",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Currency Score",
            email="tac-currency@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=tac_user, coi_attested=True, coi_attested_at=timezone.now())
        for bid in (bid_a, bid_b):
            TenderBidEvaluation.objects.create(
                bid=bid,
                evaluator=tac_user,
                stage=EvaluationStage.TECHNICAL,
                status=EvaluationStatus.SCORED,
                technical_score=20,
                feasibility_score=15,
                kpi_score=10,
                gender_score=10,
                environmental_score=5,
                om_score=10,
                inclusivity_score=0,
                total_score=70,
            )

        _close_tender_for_evaluation(self.site_specific_tender)
        self.client.force_authenticate(tac_user)

        response_a = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid_a.id), "stage": "financial", "comments": "Financial review complete."},
            format="json",
        )
        response_b = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid_b.id), "stage": "financial", "comments": "Financial review complete."},
            format="json",
        )

        self.assertEqual(response_a.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response_b.status_code, status.HTTP_201_CREATED)
        # A (180000 base) is the true lowest once converted, so it scores 100; B (9500
        # USD -> 190000 base) scores 100 * 180000/190000 ~= 94.7.
        self.assertEqual(response_a.data["financial_score"], 100)
        self.assertAlmostEqual(response_b.data["financial_score"], 100 * 180000 / 190000, places=0)

    def test_bid_currency_not_accepted_by_tender_is_rejected(self):
        self.site_specific_tender.bidding_currency = "LSL"
        self.site_specific_tender.currency_rates = {"USD": "20"}
        self.site_specific_tender.save(update_fields=["bidding_currency", "currency_rates"])

        response = self.client.post(
            "/api/tender-bids/",
            {"tender": str(self.site_specific_tender.id), "bid_currency": "ZAR", "status": BidStatus.DRAFT},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("bid_currency", response.data)

    def test_rmt_can_issue_intent_to_award_for_stage_two_recommended_winner_after_both_evaluations(self):
        competitor = User.objects.create_user(
            username="stage_two_competitor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Stage Two Competitor",
            organization_name="Competitor Ltd",
            email="competitor@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=competitor,
            company_name="Competitor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=40,
        )
        winning_bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            stage="Stage 2: Detailed",
            status=BidStatus.SUBMITTED,
            version_number=2,
        )
        competing_bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(competitor.id),
            vendor_name=competitor.full_name,
            vendor_email=competitor.email,
            bid_amount=175000,
            subsidy_requested=98000,
            stage="Stage 2: Detailed",
            status=BidStatus.SUBMITTED,
            version_number=2,
        )
        tac_user = User.objects.create_user(
            username="tac_award_stage_two",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Award Stage Two",
            email="tac-award-stage-two@example.com",
        )
        TenderBidEvaluation.objects.create(
            bid=winning_bid,
            evaluator=tac_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            inclusivity_score=0,
            total_score=62,
        )
        TenderBidEvaluation.objects.create(
            bid=competing_bid,
            evaluator=tac_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=17,
            feasibility_score=13,
            kpi_score=8,
            gender_score=7,
            environmental_score=4,
            om_score=8,
            inclusivity_score=0,
            total_score=57,
        )
        TenderBidEvaluation.objects.create(
            bid=winning_bid,
            evaluator=self.rmt_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=30,
            total_score=30,
        )
        TenderBidEvaluation.objects.create(
            bid=competing_bid,
            evaluator=self.rmt_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=26,
            total_score=26,
        )

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            f"/api/tenders/{self.site_specific_tender.id}/award/",
            {
                "bid_id": str(winning_bid.id),
                "awarded_vendor_id": str(self.vendor.id),
                "awarded_vendor_name": self.vendor.full_name,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.site_specific_tender.refresh_from_db()
        self.assertEqual(str(self.site_specific_tender.intent_to_award_bid_id), str(winning_bid.id))
        self.assertEqual(self.site_specific_tender.awarded_vendor_id, str(self.vendor.id))
        self.assertEqual(self.site_specific_tender.awarded_vendor_name, self.vendor.full_name)

    def test_rmt_can_shortlist_stage_one_bid_via_bid_action_endpoint(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.ACCEPTED)
        self.assertTrue(
            TenderBid.objects.filter(
                tender=self.prequal_tender,
                vendor_id=str(self.vendor.id),
                stage_two_unlocked=True,
                status=BidStatus.DRAFT,
            ).exclude(id=bid.id).exists()
        )

    def test_rmt_can_mark_stage_one_bid_partial_conformity_via_bid_action_endpoint(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tender-bids/{bid.id}/partial_conformity/",
            {"rejection_reason": "Please clarify the proposed site readiness plan."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.REVISION_REQUIRED)
        self.assertEqual(bid.rejection_reason, "Please clarify the proposed site readiness plan.")

    def test_rmt_can_reject_stage_one_bid_via_bid_action_endpoint(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tender-bids/{bid.id}/reject/",
            {"rejection_reason": "The submission does not meet the Stage 1 threshold."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.REJECTED)
        self.assertEqual(bid.rejection_reason, "The submission does not meet the Stage 1 threshold.")

    def test_stage_one_shortlist_is_allowed_while_tender_is_published(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.ACCEPTED)
        self.prequal_tender.refresh_from_db()
        self.assertEqual(self.prequal_tender.status, TenderStatus.PUBLISHED)
        self.assertTrue(
            TenderBid.objects.filter(
                tender=self.prequal_tender,
                vendor_id=str(self.vendor.id),
                stage_two_unlocked=True,
                status=BidStatus.DRAFT,
            ).exclude(id=bid.id).exists()
        )

    def test_technical_and_financial_evaluation_is_allowed_while_tender_is_published(self):
        # Technical/Financial submissions unlock per-bid via the staged EOI -> Technical ->
        # Financial workflow (each stage has its own deadline), not by the tender's overall
        # status reaching Closed — that only happens once the *last* staged deadline passes,
        # i.e. after Financial too. Requiring Closed here would make it impossible to ever
        # evaluate Technical/Financial proposals in time, so both must be allowed while the
        # tender is still Published.
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
            financial_sealed=False,
        )
        ec_user = User.objects.create_user(
            username="tac_blocked",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Blocked",
            email="tac-blocked@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())

        self.client.force_authenticate(ec_user)
        technical_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Technical score while published.",
            },
            format="json",
        )
        self.assertEqual(technical_response.status_code, status.HTTP_201_CREATED)

        financial_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "stage": "financial", "comments": "Ready for finance review."},
            format="json",
        )
        self.assertEqual(financial_response.status_code, status.HTTP_201_CREATED)

        self.site_specific_tender.refresh_from_db()
        self.assertEqual(self.site_specific_tender.status, TenderStatus.PUBLISHED)

    def test_stage_one_evaluation_is_allowed_while_tender_is_published(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        ec_user = User.objects.create_user(
            username="tac_stage_one",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Stage One",
            email="tac-stage-one@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.prequal_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())

        self.client.force_authenticate(ec_user)
        technical_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Stage 1 technical score while published.",
            },
            format="json",
        )
        self.assertEqual(technical_response.status_code, status.HTTP_201_CREATED)

        financial_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "stage": "financial", "comments": "Stage 1 finance review while published."},
            format="json",
        )
        self.assertEqual(financial_response.status_code, status.HTTP_201_CREATED)

        self.prequal_tender.refresh_from_db()
        self.assertEqual(self.prequal_tender.status, TenderStatus.PUBLISHED)

    def test_technical_evaluation_is_allowed_while_tender_is_published(self):
        # Technical/Financial submissions unlock per-bid via the staged EOI -> Technical
        # -> Financial workflow, not by the tender's overall status reaching Closed (that
        # only happens once the *last* staged deadline passes, i.e. after Financial too).
        # The Evaluation Committee must be able to score a Technical proposal while the
        # tender is still Published, otherwise Financial could never open in time.
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
        )
        ec_user = User.objects.create_user(
            username="tac_technical_published",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Technical Published",
            email="tac-technical-published@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())

        self.client.force_authenticate(ec_user)
        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Technical score while tender is still published.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.site_specific_tender.refresh_from_db()
        self.assertEqual(self.site_specific_tender.status, TenderStatus.PUBLISHED)

    def test_stage_two_evaluation_is_allowed_while_tender_is_published(self):
        # stage_two_unlocked is the legacy (pre-EOI/Technical/Financial-split) two-envelope
        # flag; it goes through the same "detailed" evaluation gate as bid_stage=technical/
        # combined and is subject to the same corrected rule: evaluation must not require
        # the tender's overall status to be Closed (see
        # test_technical_and_financial_evaluation_is_allowed_while_tender_is_published).
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=120000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
            stage_two_unlocked=True,
            financial_sealed=False,
        )
        ec_user = User.objects.create_user(
            username="tac_stage_two",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Stage Two",
            email="tac-stage-two@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.prequal_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())

        self.client.force_authenticate(ec_user)
        technical_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Stage 2 technical score while published.",
            },
            format="json",
        )
        self.assertEqual(technical_response.status_code, status.HTTP_201_CREATED)
        self.prequal_tender.refresh_from_db()
        self.assertEqual(self.prequal_tender.status, TenderStatus.PUBLISHED)

    def test_evaluation_auto_closes_application_window_tender_when_deadline_has_passed(self):
        self.prequal_tender.application_type = "Application Window"
        self.prequal_tender.eoi_deadline = timezone.now() - timedelta(days=1)
        self.prequal_tender.save(update_fields=["application_type", "eoi_deadline"])
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        ec_user = User.objects.create_user(
            username="tac_auto_close",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Auto Close",
            email="tac-auto-close@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.prequal_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        self.client.force_authenticate(ec_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Scored after deadline.",
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        self.prequal_tender.refresh_from_db()
        self.assertIn(self.prequal_tender.status, {TenderStatus.CLOSED, TenderStatus.EVALUATION})

    def test_application_window_tender_with_passed_deadline_is_closed_on_bid_submission_attempt(self):
        self.site_specific_tender.application_type = "Application Window"
        self.site_specific_tender.eoi_deadline = timezone.now() - timedelta(days=1)
        self.site_specific_tender.save(update_fields=["application_type", "eoi_deadline"])
        self.client.force_authenticate(self.vendor)

        response = self.client.post(
            "/api/tender-bids/",
            {"tender": str(self.site_specific_tender.id)},
            format="json",
        )

        self.site_specific_tender.refresh_from_db()
        self.assertEqual(self.site_specific_tender.status, TenderStatus.CLOSED)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_access_window_tender_is_not_auto_closed_when_deadline_passes(self):
        self.prequal_tender.eoi_deadline = timezone.now() - timedelta(days=1)
        self.prequal_tender.save(update_fields=["eoi_deadline"])
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        ec_user = User.objects.create_user(
            username="ec_access_window",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Access Window",
            email="ec-access-window@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.prequal_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        self.client.force_authenticate(ec_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "stage": "financial", "comments": "Attempt before manual close."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.prequal_tender.refresh_from_db()
        self.assertEqual(self.prequal_tender.status, TenderStatus.PUBLISHED)

    def test_technical_evaluation_is_allowed_once_tender_is_closed(self):
        _close_tender_for_evaluation(self.site_specific_tender)
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
            financial_sealed=False,
        )
        ec_user = User.objects.create_user(
            username="tac_closed_ok",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Closed OK",
            email="tac-closed-ok@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        self.client.force_authenticate(ec_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Scored after closure.",
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        self.site_specific_tender.refresh_from_db()
        self.assertEqual(self.site_specific_tender.status, TenderStatus.EVALUATION)

    def test_tac_resubmission_updates_existing_technical_evaluation(self):
        bid = TenderBid.objects.create(
            tender=self.site_specific_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=180000,
            subsidy_requested=100000,
            status=BidStatus.SUBMITTED,
        )
        tac_user = self.vendor.__class__.objects.create_user(
            username="tac_editable",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Editable",
            email="tac-editable@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.site_specific_tender, member=tac_user, coi_attested=True, coi_attested_at=timezone.now())
        self.client.force_authenticate(tac_user)
        _close_tender_for_evaluation(self.site_specific_tender)

        first_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 16,
                "feasibility_score": 12,
                "kpi_score": 8,
                "gender_score": 7,
                "environmental_score": 4,
                "om_score": 8,
                "inclusivity_score": 0,
                "comments": "Initial TAC score.",
            },
            format="json",
        )
        second_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "stage": "technical",
                "technical_score": 18,
                "feasibility_score": 14,
                "kpi_score": 9,
                "gender_score": 8,
                "environmental_score": 4,
                "om_score": 9,
                "inclusivity_score": 0,
                "comments": "Updated TAC score.",
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["id"], second_response.data["id"])
        self.assertEqual(TenderBidEvaluation.objects.filter(bid=bid, evaluator=tac_user).count(), 1)
        saved = TenderBidEvaluation.objects.get(bid=bid, evaluator=tac_user)
        self.assertEqual(saved.technical_score, 18)
        self.assertEqual(saved.comments, "Updated TAC score.")

    def test_stage_one_technical_pass_creates_stage_two_draft_for_vendor(self):
        self.client.force_authenticate(self.vendor)
        resp = self.client.post("/api/tender-bids/", self._valid_eoi_payload(), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        bid = TenderBid.objects.get(id=resp.data["id"])
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Pilot Village",
            district="Maseru",
            number_of_households=20,
        )
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)

        draft = TenderBid.objects.filter(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        ).exclude(id=bid.id).first()
        self.assertIsNotNone(draft)
        self.assertEqual(draft.bid_stage, "technical")
        self.assertEqual(draft.stage_two_source_bid_id, bid.id)
        self.assertEqual(draft.sites.count(), 1)

    def test_rmt_can_submit_financial_evaluation_for_stage_two_bid_after_stage_one_pass(self):
        stage_one_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.ACCEPTED,
        )
        ec_user = User.objects.create_user(
            username="tac_stage_two_financial_gate",
            password="securePass123",
            role=UserRole.EVALUATION_COMMITTEE,
            status="Active",
            full_name="EC Stage Two Gate",
            email="tac-stage-two-gate@example.com",
        )
        TenderEvaluationCommitteeMember.objects.create(tender=self.prequal_tender, member=ec_user, coi_attested=True, coi_attested_at=timezone.now())
        TenderBidEvaluation.objects.create(
            bid=stage_one_bid,
            evaluator=ec_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=80,
            feasibility_score=80,
            kpi_score=80,
            gender_score=80,
            environmental_score=80,
            om_score=80,
            inclusivity_score=80,
            total_score=80,
        )
        stage_two_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=155000,
            subsidy_requested=102000,
            stage="Stage 2: Detailed",
            bid_stage="technical",
            status=BidStatus.SUBMITTED,
            version_number=2,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=stage_one_bid,
        )
        TenderBidEvaluation.objects.create(
            bid=stage_two_bid,
            evaluator=ec_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            inclusivity_score=0,
            total_score=62,
        )
        self.client.force_authenticate(ec_user)
        _close_tender_for_evaluation(self.prequal_tender)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(stage_two_bid.id),
                "stage": "financial",
                "comments": "Financial evaluation completed for Stage 2.",
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        saved = TenderBidEvaluation.objects.get(bid=stage_two_bid, evaluator=ec_user, stage=EvaluationStage.FINANCIAL)
        # Only qualifying (bid_stage=technical, threshold-passed) bid for this tender, so
        # it is its own lowest price: 100 x (its own bid_amount) / (its own bid_amount) = 100.
        self.assertEqual(saved.financial_score, 100)

    def test_stage_two_draft_submission_excludes_shortlisted_stage_one_source_from_duplicate_check(self):
        stage_one_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            concept_note="Implementation strategy " * 30,
            status=BidStatus.ACCEPTED,
        )
        stage_two_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=155000,
            subsidy_requested=102000,
            stage="Stage 2: Detailed",
            status=BidStatus.DRAFT,
            version_number=2,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=stage_one_bid,
            concept_note="Detailed proposal narrative",
            tech_tier="Tier 3",
            om_strategy_summary="Detailed O&M strategy summary.",
            inclusion_commitment_confirmed=True,
            female_target_pct=55,
            vulnerable_target_pct=35,
            low_income_target_pct=60,
            system_configuration={
                "technology_type": "SHS",
                "device_brand": "SunPower",
                "device_model": "SPX-300",
                "co_financing_amount_lsl": 53000,
            },
            boq_items=[
                {
                    "item_number": 1,
                    "description": "Solar kit",
                    "qty": 1,
                    "unit": "lot",
                    "unit_price": 155000,
                    "total": 155000,
                }
            ],
            boq_details=[
                {
                    "item_number": 1,
                    "description": "Solar kit",
                    "qty": 1,
                    "unit": "lot",
                    "unit_price": 155000,
                    "total": 155000,
                }
            ],
            technical_proposal_file=SimpleUploadedFile("technical.pdf", b"technical", content_type="application/pdf"),
            financial_proposal_file=SimpleUploadedFile("financial.pdf", b"financial", content_type="application/pdf"),
            boq_file=SimpleUploadedFile("boq.xlsx", b"boq", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            gender_action_plan_file=SimpleUploadedFile("gender.pdf", b"gender", content_type="application/pdf"),
            implementation_plan_file=SimpleUploadedFile("implementation.pdf", b"implementation", content_type="application/pdf"),
            om_plan_file=SimpleUploadedFile("om.pdf", b"om", content_type="application/pdf"),
        )
        TenderBidSite.objects.create(
            bid=stage_two_bid,
            site_name="Ha Thetsane Cluster",
            district="Maseru",
            village_sub_district="Ha Thetsane",
            latitude=Decimal("-29.316700"),
            longitude=Decimal("27.483300"),
            number_of_households=25,
            target_beneficiary_type="female_headed",
            road_access_available=True,
        )

        response = self.client.patch(
            f"/api/tender-bids/{stage_two_bid.id}/",
            {"status": BidStatus.SUBMITTED},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stage_two_bid.refresh_from_db()
        self.assertEqual(stage_two_bid.status, BidStatus.SUBMITTED)

    def test_stage_one_pass_notifies_vendor_in_app_and_email(self):
        self.client.force_authenticate(self.vendor)
        resp = self.client.post("/api/tender-bids/", self._valid_eoi_payload(), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        bid = TenderBid.objects.get(id=resp.data["id"])
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        self.assertTrue(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                event="stage_one_shortlisted",
                linked_entity_id=str(bid.tender.id),
            ).exists()
        )
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.ACCEPTED)
        self.assertIsNotNone(bid.reviewed_at)

    def test_stage_one_fail_notifies_vendor_in_app_and_email(self):
        self.client.force_authenticate(self.vendor)
        resp = self.client.post("/api/tender-bids/", self._valid_eoi_payload(), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        bid = TenderBid.objects.get(id=resp.data["id"])
        self.client.force_authenticate(self.rmt_user)
        reject = self.client.post(
            f"/api/tender-bids/{bid.id}/reject/",
            {"rejection_reason": "The EOI submission did not meet the Stage 1 technical threshold."},
            format="json",
        )
        self.assertEqual(reject.status_code, status.HTTP_200_OK, reject.data)
        self.assertTrue(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                event="bid_rejected",
                linked_entity_id=str(bid.tender.id),
            ).exists()
        )
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.REJECTED)
        self.assertTrue(bool(bid.rejection_reason))
        self.assertFalse(
            TenderBid.objects.filter(
                tender=self.prequal_tender,
                vendor_id=str(self.vendor.id),
                stage_two_unlocked=True,
                status=BidStatus.DRAFT,
            ).exclude(id=bid.id).exists()
        )

    def test_vendor_bid_list_includes_stage_two_draft_for_same_vendor_only(self):
        other_vendor = User.objects.create_user(
            username="other_bid_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Other Bid Vendor",
            organization_name="Other Bid Vendor Ltd",
            email="other-bid-vendor@example.com",
        )
        own_submitted_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(days=1),
        )
        own_stage_two_draft = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("155000.00"),
            stage="Stage 2: Detailed",
            version_number=2,
            status=BidStatus.DRAFT,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=own_submitted_bid,
        )
        TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(other_vendor.id),
            vendor_name=other_vendor.full_name,
            vendor_email=other_vendor.email,
            bid_amount=Decimal("160000.00"),
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )

        response = self.client.get("/api/tender-bids/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 2)
        self.assertEqual(str(results[0]["id"]), str(own_stage_two_draft.id))
        self.assertTrue(results[0]["stage_two_unlocked"])
        self.assertEqual(str(results[1]["id"]), str(own_submitted_bid.id))

    def test_vendor_bid_list_backfills_stage_two_draft_after_passed_technical_review(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.ACCEPTED,
            submitted_at=timezone.now() - timedelta(days=1),
        )
        tac_user = User.objects.create_user(
            username="tac_backfill",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Backfill",
            email="tac-backfill@example.com",
        )
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=tac_user,
            status=EvaluationStatus.SCORED,
            technical_score=80,
            feasibility_score=80,
            kpi_score=80,
            gender_score=80,
            environmental_score=80,
            om_score=80,
            inclusivity_score=80,
            total_score=80,
        )

        response = self.client.get("/api/tender-bids/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        backfilled_draft = TenderBid.objects.filter(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        ).exclude(id=bid.id).first()
        self.assertIsNotNone(backfilled_draft)
        results = response.data["results"]
        self.assertEqual(str(results[0]["id"]), str(backfilled_draft.id))
        self.assertTrue(results[0]["stage_two_unlocked"])

    def test_vendor_bid_list_backfills_stage_two_draft_for_stage_one_concept_label(self):
        self.prequal_tender.stage_type = "Stage 1: Concept"
        self.prequal_tender.save(update_fields=["stage_type"])
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.ACCEPTED,
            submitted_at=timezone.now() - timedelta(days=1),
        )
        tac_user = User.objects.create_user(
            username="tac_backfill_stage_one_label",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Backfill Stage One Label",
            email="tac-backfill-stage-one-label@example.com",
        )
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=tac_user,
            status=EvaluationStatus.SCORED,
            technical_score=80,
            feasibility_score=80,
            kpi_score=80,
            gender_score=80,
            environmental_score=80,
            om_score=80,
            inclusivity_score=80,
            total_score=80,
        )

        response = self.client.get("/api/tender-bids/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        backfilled_draft = TenderBid.objects.filter(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        ).exclude(id=bid.id).first()
        self.assertIsNotNone(backfilled_draft)
        results = response.data["results"]
        self.assertEqual(str(results[0]["id"]), str(backfilled_draft.id))
        self.assertTrue(results[0]["stage_two_unlocked"])

    def test_stage_two_draft_copies_uploaded_documents_from_stage_one(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            subsidy_requested=Decimal("100000.00"),
            bid_stage="eoi",
            concept_note="Implementation strategy " * 30,
            technical_proposal_file=SimpleUploadedFile("technical.pdf", b"technical", content_type="application/pdf"),
            financial_proposal_file=SimpleUploadedFile("financial.pdf", b"financial", content_type="application/pdf"),
            gender_action_plan_file=SimpleUploadedFile("gap.pdf", b"gap", content_type="application/pdf"),
            implementation_plan_file=SimpleUploadedFile("om.pdf", b"om", content_type="application/pdf"),
            status=BidStatus.SUBMITTED,
        )
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Pilot Village",
            district="Maseru",
            number_of_households=20,
        )
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)

        draft = TenderBid.objects.filter(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        ).exclude(id=bid.id).first()
        self.assertIsNotNone(draft)
        self.assertTrue(bool(draft.technical_proposal_file))
        self.assertTrue(bool(draft.financial_proposal_file))
        self.assertTrue(bool(draft.gender_action_plan_file))
        self.assertTrue(bool(draft.implementation_plan_file))

    def test_existing_stage_two_draft_backfills_stage_one_sites_when_missing(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            bid_stage="eoi",
            concept_note="Implementation strategy " * 30,
            status=BidStatus.SUBMITTED,
        )
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Saved Stage One Village",
            district="Maseru",
            number_of_households=18,
        )
        existing_draft = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            bid_stage="technical",
            status=BidStatus.DRAFT,
            version_number=2,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=bid,
        )
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{bid.id}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)

        existing_draft.refresh_from_db()
        self.assertEqual(existing_draft.sites.count(), 1)
        copied_site = existing_draft.sites.first()
        self.assertEqual(copied_site.site_name, "Saved Stage One Village")
        self.assertEqual(copied_site.district, "Maseru")
        self.assertEqual(copied_site.number_of_households, 18)

    def test_stage_two_site_target_technology_is_saved(self):
        payload = {
            "site_name": "Detailed Village",
            "district": "Maseru",
            "number_of_households": 12,
            "target_technology": "SHS",
            "latitude": "-29.310000",
            "longitude": "27.480000",
        }
        serializer = TenderBidSiteSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["system_configuration"]["target_technology"], "SHS")

    def test_stage_one_site_alias_fields_are_accepted(self):
        payload = {
            "site_name": "Alias Village",
            "district": "Maseru",
            "village": "Ha Abia",
            "estimated_households": 14,
            "primary_beneficiary_type": "female_headed",
            "road_access": True,
            "latitude": "-29.310000",
            "longitude": "27.480000",
        }
        serializer = TenderBidSiteSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["village_sub_district"], "Ha Abia")
        self.assertEqual(serializer.validated_data["number_of_households"], 14)
        self.assertEqual(serializer.validated_data["target_beneficiary_type"], "female_headed")
        self.assertTrue(serializer.validated_data["road_access_available"])

    def test_latest_prequalification_must_be_approved_before_bid_access(self):
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="Bid Vendor Ltd",
            status=PrequalificationStatus.REJECTED,
            tech_tier="Level 3",
        )

        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "150000.00",
                **self._submission_basics(),
                "concept_note": "Community-focused clean energy rollout for underserved households. " * 12,
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Ha Thetsane Cluster",
                        "district": "Maseru",
                        "estimated_households": 85,
                        "primary_beneficiary_type": "female_headed",
                    }
                ]),
                "status": BidStatus.DRAFT,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Complete pre-qualification first")

    def test_vendor_cannot_submit_second_final_bid_for_same_tender(self):
        TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            subsidy_requested=Decimal("100000.00"),
            concept_note="Implementation strategy " * 30,
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )

        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "155000.00",
                **self._submission_basics(),
                "concept_note": "Community-focused clean energy rollout for underserved households. " * 12,
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Second Attempt",
                        "district": "Maseru",
                        "estimated_households": 22,
                        "primary_beneficiary_type": "female_headed",
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["tender"], "You have already submitted a bid for this tender.")

    def test_resubmitting_bid_does_not_500_on_duplicate_notification(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=Decimal("150000.00"),
            subsidy_requested=Decimal("100000.00"),
            concept_note="Implementation strategy " * 30,
            stage="Stage 1: Concept",
            version_number=1,
            status=BidStatus.DRAFT,
        )

        first = self.client.post(f"/api/tender-bids/{bid.id}/submit/")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.SUBMITTED)

        bid.status = BidStatus.REVISION_REQUIRED
        bid.save(update_fields=["status"])
        second = self.client.post(f"/api/tender-bids/{bid.id}/submit/")
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        self.assertEqual(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                event="bid_submitted",
                linked_entity_id=str(self.prequal_tender.id),
            ).count(),
            1,
            "Resubmitting must not create a duplicate vendor notification or raise.",
        )

    def test_submitted_bid_is_locked_from_updates(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            device_brand_model="Locked Device",
            tech_tier="Tier 2",
            energy_target_kwh_month=Decimal("300.00"),
            warranty_period_months=24,
            concept_note="Submitted note",
            status=BidStatus.ACCEPTED,
        )

        response = self.client.patch(
            f"/api/tender-bids/{bid.id}/",
            {"bid_amount": "170000.00"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(response.data["detail"]).lower())

    def test_non_owner_cannot_delete_bid(self):
        other_vendor = User.objects.create_user(
            username="other_bid_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Other Vendor",
            email="other-vendor@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=other_vendor,
            company_name="Other Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Tier 2",
        )
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=100000,
            subsidy_requested=50000,
            status=BidStatus.DRAFT,
        )

        self.client.force_authenticate(other_vendor)
        response = self.client.delete(f"/api/tender-bids/{bid.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_cannot_delete_submitted_bid(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=100000,
            subsidy_requested=50000,
            status=BidStatus.SUBMITTED,
        )

        response = self.client.delete(f"/api/tender-bids/{bid.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_vendor_can_delete_own_draft_bid(self):
        bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=100000,
            subsidy_requested=50000,
            status=BidStatus.DRAFT,
        )

        response = self.client.delete(f"/api/tender-bids/{bid.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TenderBid.objects.filter(id=bid.id).exists())

    def test_stage_two_final_submit_requires_required_files(self):
        from .models import TenderRequiredDocument
        TenderRequiredDocument.objects.create(
            tender=self.site_specific_tender, name="Technical Proposal",
            bid_stage="technical", field_key="technical_proposal_file", position=1,
        )
        TenderRequiredDocument.objects.create(
            tender=self.site_specific_tender, name="Bill of Quantities",
            bid_stage="technical", field_key="boq_file", position=2,
        )
        draft = self._create_technical_draft()
        payload = self._valid_technical_payload()
        payload.pop("technical_proposal_file")
        payload.pop("boq_file")

        response = self.client.patch(
            f"/api/tender-bids/{draft.id}/",
            payload,
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("technical_proposal_file", response.data)
        self.assertIn("boq_file", response.data)


class TenderContractPdfTests(APITestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username="vendor_pdf",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Lesotho Solar Vendor",
            organization_name="Lesotho Solar Vendor",
            organization_type="Private Company",
            region="Maseru",
            email="vendor-pdf@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="Lesotho Solar Vendor",
            status=PrequalificationStatus.APPROVED,
            female_beneficiary_target=62,
            vulnerable_group_target=35,
        )
        self.tender = Tender.objects.create(
            reference_number="REF-PDF-001",
            name="Grid Extension PBA",
            department="Department of Energy",
            category="Mini-Grid",
            status=TenderStatus.AWARDED,
            deadline=timezone.now(),
            awarded_vendor_id=str(self.vendor.id),
            awarded_vendor_name=self.vendor.full_name,
            awarded_at=timezone.now(),
            budget=150000,
            technology_types=["Solar Mini-Grid"],
            instruction="Deliver all installations in accordance with the approved results framework and reporting obligations.",
        )
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            status=BidStatus.AWARDED,
        )
        self.contract = TenderContract.objects.create(
            tender=self.tender,
            bid=self.bid,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            reference_number=f"CTR-{self.tender.reference_number}-{self.vendor.id}",
            template_name="Performance-Based Agreement",
            status=ContractStatus.GENERATED,
        )

    def test_main_agreement_html_contains_professional_contract_sections(self):
        html = _main_agreement_html(self.contract, self.tender, self.bid, self.vendor, None)

        self.assertIn("Renewable Lesotho Results-Based Financing Agreement", html)
        self.assertIn("Contract Reference ID", html)
        self.assertIn("Vendor Authorized Signatory", html)
        self.assertIn("RBF Authorized Signatory", html)
        self.assertIn("Total Subsidy Amount", html)
        self.assertIn("Mobilization", html)
        self.assertIn("Installation", html)
        self.assertIn("Performance", html)
        self.assertIn("Social Inclusion Commitments", html)
        self.assertIn("Female-Headed Household Target", html)
        self.assertIn("62%", html)
        self.assertIn("35%", html)

    def test_annex_c_uses_project_milestones_when_project_exists(self):
        project = Project.objects.create(
            tender=self.tender,
            project_title=self.tender.name,
            project_reference="PRJ-PDF-001",
            milestone_plan_id="MS-PDF-001",
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            tech_type="Solar Mini-Grid",
            region="Maseru",
            district="Maseru Urban",
            status=ProjectStatus.INSTALLATION,
            budget=150000,
        )
        Milestone.objects.create(
            project=project,
            name="Mobilization",
            percentage=20,
            amount=30000,
            description="Signed field survey required.",
        )
        Milestone.objects.create(
            project=project,
            name="Installation",
            percentage=50,
            amount=75000,
            description="Installation completion evidence.",
        )
        Milestone.objects.create(
            project=project,
            name="Performance",
            percentage=30,
            amount=45000,
            description="Smart meter data sync.",
        )
        self.contract.project_id = str(project.id)
        self.contract.save(update_fields=["project_id"])

        html = _annex_section_html(
            self.contract,
            annex_part=type(
                "AnnexPartStub",
                (),
                {
                    "field_name": "annex_c_file",
                    "label": "Annex C",
                    "title": "Payment Terms",
                    "description": "Includes the BOQ and generated disbursement table.",
                    "source_path": None,
                },
            )(),
            total_award=self.bid.bid_amount,
        )

        self.assertIn("PRJ-PDF-001", _main_agreement_html(self.contract, self.tender, self.bid, self.vendor, project))
        self.assertIn("LSL 30,000.00", html)
        self.assertIn("LSL 75,000.00", html)
        self.assertIn("LSL 45,000.00", html)
        self.assertIn("Smart meter data sync", html)

    def test_contract_serializer_resolves_annexes_from_awarded_bid_documents(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.bid.gender_action_plan_file.save("gender-plan.pdf", SimpleUploadedFile("gender-plan.pdf", b"%PDF-1.4 annex a"), save=True)
                self.bid.implementation_plan_file.save("implementation-plan.pdf", SimpleUploadedFile("implementation-plan.pdf", b"%PDF-1.4 annex b"), save=True)
                self.bid.financial_proposal_file.save("payment-terms.pdf", SimpleUploadedFile("payment-terms.pdf", b"%PDF-1.4 annex c"), save=True)
                self.bid.reporting_templates_file.save("reporting-templates.pdf", SimpleUploadedFile("reporting-templates.pdf", b"%PDF-1.4 annex d"), save=True)
                self.bid.technical_proposal_file.save("technical-standards.pdf", SimpleUploadedFile("technical-standards.pdf", b"%PDF-1.4 annex e"), save=True)
                self.bid.save()

                request = type("RequestStub", (), {"build_absolute_uri": lambda self, url: f"http://testserver{url}"})()
                data = TenderContractSerializer(self.contract, context={"request": request}).data

                self.assertTrue(data["annex_a_file"].endswith("gender-plan.pdf"))
                self.assertTrue(data["annex_b_file"].endswith("implementation-plan.pdf"))
                self.assertTrue(data["annex_c_file"].endswith("payment-terms.pdf"))
                self.assertTrue(data["annex_d_file"].endswith("reporting-templates.pdf"))
                self.assertTrue(data["annex_e_file"].endswith("technical-standards.pdf"))

    def test_generate_contract_pdf_merges_generated_pages_and_source_annex_pdfs(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.bid.gender_action_plan_file.save("annex-a.pdf", SimpleUploadedFile("annex-a.pdf", b"%PDF-1.4 annex a"), save=True)
                self.bid.implementation_plan_file.save("annex-b.pdf", SimpleUploadedFile("annex-b.pdf", b"%PDF-1.4 annex b"), save=True)
                self.bid.financial_proposal_file.save("annex-c.pdf", SimpleUploadedFile("annex-c.pdf", b"%PDF-1.4 annex c"), save=True)
                self.bid.reporting_templates_file.save("annex-d.pdf", SimpleUploadedFile("annex-d.pdf", b"%PDF-1.4 annex d"), save=True)
                self.bid.technical_proposal_file.save("annex-e.pdf", SimpleUploadedFile("annex-e.pdf", b"%PDF-1.4 annex e"), save=True)
                self.bid.save()

                self.contract.annex_a_file = self.bid.gender_action_plan_file.name
                self.contract.annex_b_file = self.bid.implementation_plan_file.name
                self.contract.annex_c_file = self.bid.financial_proposal_file.name
                self.contract.annex_d_file = self.bid.reporting_templates_file.name
                self.contract.annex_e_file = self.bid.technical_proposal_file.name
                self.contract.save()

                def fake_render(_html, output_path, _contract_reference):
                    Path(output_path).write_bytes(b"%PDF-1.4 generated")

                def fake_merge(parts, output_path):
                    output_path.write_bytes(b"%PDF-1.4 merged")
                    fake_merge.parts = [Path(part).name for part in parts]

                with patch("rbf.tenders.pba_pdf._render_pdf", side_effect=fake_render) as mock_render:
                    with patch("rbf.tenders.pba_pdf._pdfa_merge", side_effect=fake_merge):
                        generate_contract_pdf(self.contract, self.tender, self.bid, self.vendor)

                self.assertEqual(mock_render.call_count, 6)
                self.assertEqual(fake_merge.parts[0], "01_main_agreement.pdf")
                self.assertIn("annex-a.pdf", fake_merge.parts)
                self.assertIn("annex-b.pdf", fake_merge.parts)
                self.assertIn("annex-c.pdf", fake_merge.parts)
                self.assertIn("annex-d.pdf", fake_merge.parts)
                self.assertIn("annex-e.pdf", fake_merge.parts)
                self.contract.refresh_from_db()
                self.assertTrue(self.contract.generated_file.name.endswith(".pdf"))

    def test_pdfa_merge_falls_back_to_standard_pdf_merge(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            part_a = temp_path / "a.pdf"
            part_b = temp_path / "b.pdf"
            output = temp_path / "merged.pdf"
            part_a.write_bytes(b"%PDF-1.4 a")
            part_b.write_bytes(b"%PDF-1.4 b")

            calls = []

            def fake_run(cmd, check, capture_output, text):
                calls.append(cmd)
                if len(calls) == 1:
                    raise subprocess.CalledProcessError(1, cmd, stderr="PDF/A conversion failed")
                output.write_bytes(b"%PDF-1.7 merged")
                return None

            with patch("rbf.tenders.pba_pdf.subprocess.run", side_effect=fake_run):
                _pdfa_merge([part_a, part_b], output)

            self.assertEqual(len(calls), 2)
            self.assertTrue(any("-dPDFA=2" in arg for arg in calls[0]))
            self.assertFalse(any("-dPDFA=2" in arg for arg in calls[1]))
            self.assertTrue(output.exists())


class TenderContractSigningTests(APITestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username="sign_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Signing Vendor",
            organization_name="Signing Vendor Ltd",
            email="signing-vendor@example.com",
        )
        self.admin = User.objects.create_user(
            username="sign_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Signing Admin",
        )
        self.tender = Tender.objects.create(
            reference_number="REF-SIGN-001",
            name="Signing Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.AWARDED,
            deadline=timezone.now(),
            awarded_vendor_id=str(self.vendor.id),
            awarded_vendor_name=self.vendor.full_name,
            awarded_at=timezone.now(),
        )
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=90000,
            status=BidStatus.AWARDED,
        )
        self.contract = TenderContract.objects.create(
            tender=self.tender,
            bid=self.bid,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            reference_number=f"CTR-{self.tender.reference_number}-{self.vendor.id}",
            template_name="Performance-Based Agreement",
            status=ContractStatus.GENERATED,
        )
        self.contract.annex_a_file = "tender_contracts/annexes/a.pdf"
        self.contract.annex_b_file = "tender_contracts/annexes/b.pdf"
        self.contract.annex_c_file = "tender_contracts/annexes/c.pdf"
        self.contract.annex_d_file = "tender_contracts/annexes/d.pdf"
        self.contract.annex_e_file = "tender_contracts/annexes/e.pdf"
        self.contract.save()

    def test_vendor_must_upload_signed_contract_as_pdf(self):
        self.client.force_authenticate(self.vendor)

        response = self.client.post(
            f"/api/tender-contracts/{self.contract.id}/sign/",
            {"signed_file": SimpleUploadedFile("signed.docx", b"fake-docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PDF", str(response.data["signed_file"]))

    def test_vendor_signed_contract_must_not_exceed_ten_mb(self):
        self.client.force_authenticate(self.vendor)

        response = self.client.post(
            f"/api/tender-contracts/{self.contract.id}/sign/",
            {"signed_file": SimpleUploadedFile("signed.pdf", b"x" * (10 * 1024 * 1024 + 1), content_type="application/pdf")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("10MB", str(response.data["signed_file"]))

    def test_vendor_upload_sets_signature_status_uploaded(self):
        self.client.force_authenticate(self.vendor)

        response = self.client.post(
            f"/api/tender-contracts/{self.contract.id}/sign/",
            {"signed_file": SimpleUploadedFile("signed.pdf", b"%PDF-1.4 test", content_type="application/pdf")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.signature_status, ContractSignatureStatus.UPLOADED)


class TenderContractAssignmentTests(APITestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username="assigned_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Assigned Vendor",
            organization_name="Assigned Vendor Ltd",
            email="assigned-vendor@example.com",
            region="Maseru",
            verification_zone="Maseru Urban",
        )
        self.rmt_user = User.objects.create_user(
            username="rmt_assignment",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="RMT Assignment User",
        )
        self.admin = User.objects.create_user(
            username="assignment_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Assignment Admin",
        )
        self.tender = Tender.objects.create(
            reference_number="REF-ASG-001",
            name="Assignment Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.AWARDED,
            deadline=timezone.now(),
            awarded_vendor_id=str(self.vendor.id),
            awarded_vendor_name=self.vendor.full_name,
            awarded_at=timezone.now(),
            technology_types=["SHS"],
        )
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=120000,
            status=BidStatus.AWARDED,
        )
        self.contract = TenderContract.objects.create(
            tender=self.tender,
            bid=self.bid,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            reference_number=f"CTR-{self.tender.reference_number}-{self.vendor.id}",
            template_name="Performance-Based Agreement",
            status=ContractStatus.APPROVED,
            signature_status=ContractSignatureStatus.APPROVED,
            signed_file="tender_contracts/signed.pdf",
            approved_at=timezone.now(),
            approved_by=self.rmt_user.full_name,
        )

    def test_assign_get_is_rmt_only(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(f"/api/tender-contracts/{self.contract.id}/assign/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_requires_contract_to_be_approved(self):
        self.contract.status = ContractStatus.SUBMITTED
        self.contract.signature_status = ContractSignatureStatus.UPLOADED
        self.contract.save(update_fields=["status", "signature_status", "updated_at"])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tender-contracts/{self.contract.id}/assign/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("approved", str(response.data["detail"]).lower())

    def test_assign_get_returns_contract_and_assignment_defaults(self):
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tender-contracts/{self.contract.id}/assign/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["contract"]["id"], self.contract.id)
        self.assertEqual(response.data["assignment_defaults"]["technology_type"], "SHS")
        self.assertEqual(response.data["assignment_defaults"]["verification_method"], "manual")
        self.assertEqual(response.data["assignment_defaults"]["female_target_pct"], 50)
        self.assertEqual(response.data["contract_details"]["contract_ref"], self.contract.reference_number)
        self.assertEqual(response.data["assignment_fields"]["technology_type_read_only"], True)
        self.assertEqual(response.data["disbursement_preview"]["milestone_1_amount_lsl"], "24000.00")

    def test_assign_get_prefills_districts_from_tender_target_districts(self):
        self.tender.target_districts = ["Maseru", "Thaba-Tseka"]
        self.tender.save(update_fields=["target_districts", "updated_at"])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tender-contracts/{self.contract.id}/assign/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assignment_defaults"]["district_zones"], ["Maseru", "Thaba-Tseka"])
        self.assertEqual(response.data["assignment_defaults"]["district_zone"], "Maseru, Thaba-Tseka")

    def test_assign_get_fetches_multi_selected_tender_technology_types(self):
        self.tender.technology_types = ["SHS", "GMG"]
        self.tender.save(update_fields=["technology_types", "updated_at"])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tender-contracts/{self.contract.id}/assign/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assignment_fields"]["technology_type"], ["SHS", "GMG"])
        self.assertEqual(response.data["assignment_defaults"]["technology_type"], "SHS")
        self.assertEqual(response.data["assignment_fields"]["technology_type_read_only"], False)

    @patch("rbf.tenders.views.queue_project_targets_sync")
    def test_assign_post_creates_project_milestones_audit_and_notification(self, queue_targets):
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tender-contracts/{self.contract.id}/assign/",
            {
                "project_duration_months": 12,
                "installation_target": 250,
                "technology_type": "SHS",
                "energy_output_target_kwh": "20000.00",
                "district_zones": ["Maseru Urban", "Leribe"],
                "verification_method": "iot",
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "start_date": "2026-04-05",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(contract=self.contract)
        self.contract.refresh_from_db()
        self.assertEqual(response.data["message"], f"Project PRJ-{project.id} assigned successfully.")
        self.assertTrue(response.data["redirect_url"].endswith(f"/api/projects/{project.id}/"))
        self.assertEqual(project.status, ProjectStatus.SETUP_PENDING)
        self.assertEqual(project.installation_target, 250)
        self.assertEqual(project.technology_type, "SHS")
        self.assertEqual(str(project.energy_output_target_kwh), "20000.00")
        self.assertEqual(project.district, "Maseru Urban")
        self.assertEqual(project.district_zone, "Maseru Urban, Leribe")
        self.assertEqual(project.verification_method, "iot")
        self.assertEqual(project.female_target_pct, 50)
        self.assertEqual(project.vulnerable_target_pct, 30)
        self.assertEqual(project.low_income_target_pct, 60)
        self.assertEqual(self.contract.project_id, str(project.id))
        self.assertEqual(self.contract.status, ContractStatus.APPROVED)
        self.assertEqual(project.project_reference, f"PRJ-{self.tender.reference_number}-{self.vendor.id}")

        milestones = list(project.milestones.order_by("milestone_number"))
        self.assertEqual(len(milestones), 3)
        self.assertEqual([m.disbursement_pct for m in milestones], [20, 50, 30])
        self.assertEqual([m.status for m in milestones], ["pending", "locked", "locked"])
        self.assertEqual([str(m.amount_lsl) for m in milestones], ["24000.00", "60000.00", "36000.00"])

        self.assertTrue(
            AuditLog.objects.filter(
                action="milestone_assigned",
                module="projects",
                record_id=project.id,
                record_type="project",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                title="Project Assigned",
                body=f"You have been assigned to Project PRJ-{project.id}. Complete setup to begin.",
                linked_entity_id=str(project.id),
            ).exists()
        )
        queue_targets.assert_called_once_with(str(project.id), run_immediately=True, record_type="project")

    @patch("rbf.tenders.views.queue_project_targets_sync")
    def test_assign_post_normalizes_legacy_mini_grid_label(self, queue_targets):
        self.tender.category = "Mini-Grid"
        self.tender.technology_types = ["Solar Mini-Grid"]
        self.tender.save(update_fields=["category", "technology_types", "updated_at"])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tender-contracts/{self.contract.id}/assign/",
            {
                "project_duration_months": 12,
                "installation_target": 250,
                "technology_type": "Mini-grid",
                "energy_output_target_kwh": "20000.00",
                "district_zones": ["Maseru"],
                "verification_method": "manual",
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(contract=self.contract)
        self.assertEqual(project.technology_type, "GMG")
        self.assertEqual(project.tech_type, "GMG")
        queue_targets.assert_called_once_with(str(project.id), run_immediately=True, record_type="project")


class StandstillTransitionTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="ststill_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Standstill Admin",
        )
        self.vendor = User.objects.create_user(
            username="ststill_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Standstill Vendor",
        )
        self.tender = Tender.objects.create(
            reference_number="STTRANS-001",
            name="Standstill Transitions",
            department="DoE",
            category="SHS",
            status=TenderStatus.EVALUATION,
            deadline=timezone.now(),
            technology_types=["Solar Home System"],
            cooling_off_days=14,
        )
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            bid_amount=100000,
            status=BidStatus.SUBMITTED,
        )
        TenderBidEvaluation.objects.create(
            bid=self.bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.TECHNICAL,
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            total_score=62,
        )
        TenderBidEvaluation.objects.create(
            bid=self.bid,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=74,
            financial_score_auto_calculated=True,
            total_score=74,
        )

    def test_resolve_challenge_dismissed_returns_to_standstill(self):
        self.client.force_authenticate(self.admin_user)

        award_response = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {"bid_id": str(self.bid.id), "awarded_vendor_id": str(self.vendor.id), "awarded_vendor_name": self.vendor.full_name},
            format="json",
        )
        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.assertEqual(award_response.data["status"], TenderStatus.STANDSTILL)

        challenge_response = self.client.post(
            f"/api/tenders/{self.tender.id}/create_challenge/",
            {
                "filed_by_vendor_id": str(self.vendor.id),
                "filed_by_vendor_name": "Other Vendor",
                "grounds": "Evaluation scoring error in financial criteria.",
            },
            format="json",
        )
        self.assertEqual(challenge_response.status_code, status.HTTP_201_CREATED)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.DISPUTED)

        challenge_id = challenge_response.data["id"]

        resolve_response = self.client.post(
            f"/api/tenders/{self.tender.id}/resolve_challenge/",
            {"challenge_id": challenge_id, "outcome": "dismissed", "resolution_notes": "No evidence of scoring error."},
            format="json",
        )
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)
        self.assertIsNotNone(self.tender.cooling_off_until)
        self.assertIsNone(self.tender.dispute_started_at)

    def test_resolve_challenge_upheld_returns_to_standstill_with_new_intent(self):
        self.client.force_authenticate(self.admin_user)

        award_response = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {"bid_id": str(self.bid.id), "awarded_vendor_id": str(self.vendor.id), "awarded_vendor_name": self.vendor.full_name},
            format="json",
        )
        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.assertEqual(award_response.data["status"], TenderStatus.STANDSTILL)

        challenger = User.objects.create_user(
            username="challenger_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Challenger Vendor",
        )
        challenger_bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(challenger.id),
            vendor_name=challenger.full_name,
            bid_amount=95000,
            status=BidStatus.SUBMITTED,
        )

        challenge_response = self.client.post(
            f"/api/tenders/{self.tender.id}/create_challenge/",
            {
                "filed_by_vendor_id": str(challenger.id),
                "filed_by_vendor_name": challenger.full_name,
                "grounds": "Evaluation scoring error",
                "challenger_bid_id": str(challenger_bid.id),
            },
            format="json",
        )
        self.assertEqual(challenge_response.status_code, status.HTTP_201_CREATED)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.DISPUTED)
        challenge_id = challenge_response.data["id"]

        resolve_response = self.client.post(
            f"/api/tenders/{self.tender.id}/resolve_challenge/",
            {"challenge_id": challenge_id, "outcome": "upheld", "resolution_notes": "Scoring error confirmed."},
            format="json",
        )
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)
        self.assertEqual(str(self.tender.intent_to_award_bid_id), str(challenger_bid.id))
        self.assertEqual(self.tender.awarded_vendor_id, str(challenger.id))
        self.assertEqual(self.tender.awarded_vendor_name, challenger.full_name)
        self.assertIsNotNone(self.tender.cooling_off_until)
        self.assertIsNone(self.tender.dispute_started_at)

    def test_award_standstill_confirm_full_cycle(self):
        self.client.force_authenticate(self.admin_user)

        award_response = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {"bid_id": str(self.bid.id), "awarded_vendor_id": str(self.vendor.id), "awarded_vendor_name": self.vendor.full_name},
            format="json",
        )
        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.assertEqual(award_response.data["status"], TenderStatus.STANDSTILL)

        self.tender.refresh_from_db()
        self.tender.cooling_off_until = timezone.now() - timedelta(minutes=1)
        self.tender.save(update_fields=["cooling_off_until"])

        confirm_response = self.client.post(
            f"/api/tenders/{self.tender.id}/confirm_award/",
            {},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], TenderStatus.AWARDED)

        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.AWARDED)
        self.assertIsNone(self.tender.cooling_off_until)
        self.assertIsNone(self.tender.dispute_started_at)

    def test_standstill_tender_pause_and_resume_cycle(self):
        """Verify: EVALUATION -> award() -> STANDSTILL -> pause_award() -> DISPUTED -> resolve_challenge(dismissed) -> STANDSTILL -> confirm_award() -> AWARDED"""
        self.client.force_authenticate(self.admin_user)

        award_response = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {"bid_id": str(self.bid.id), "awarded_vendor_id": str(self.vendor.id), "awarded_vendor_name": self.vendor.full_name},
            format="json",
        )
        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)

        pause_response = self.client.post(
            f"/api/tenders/{self.tender.id}/pause_award/",
            {},
            format="json",
        )
        self.assertEqual(pause_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.DISPUTED)

        challenge_response = self.client.post(
            f"/api/tenders/{self.tender.id}/create_challenge/",
            {
                "filed_by_vendor_id": str(self.vendor.id),
                "filed_by_vendor_name": "Other Vendor",
                "grounds": "Scoring error",
            },
            format="json",
        )
        self.assertEqual(challenge_response.status_code, status.HTTP_201_CREATED)
        challenge_id = challenge_response.data["id"]

        resolve_response = self.client.post(
            f"/api/tenders/{self.tender.id}/resolve_challenge/",
            {"challenge_id": challenge_id, "outcome": "dismissed", "resolution_notes": "No merit."},
            format="json",
        )
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)

        self.tender.cooling_off_until = timezone.now() - timedelta(minutes=1)
        self.tender.save(update_fields=["cooling_off_until"])

        confirm_response = self.client.post(
            f"/api/tenders/{self.tender.id}/confirm_award/",
            {},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.AWARDED)
        self.assertIsNone(self.tender.cooling_off_until)
        self.assertIsNone(self.tender.dispute_started_at)


class ProcurementWorkflowTests(APITestCase):
    """Focused smoke tests for the new 3-stage procurement workflow."""

    def setUp(self):
        self.vendor = User.objects.create_user(
            username="wf_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="WF Vendor",
            organization_name="WF Vendor Ltd",
            email="wf-vendor@example.com",
        )
        self.rmt_user = User.objects.create_user(
            username="wf_rmt",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="WF RMT",
            email="wf-rmt@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="WF Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )

    def _upload(self):
        return SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

    def test_sequential_eoi_submission_serializes_workflow_and_deadlines(self):
        tender = Tender.objects.create(
            reference_number="WF-SEQ-001",
            name="Sequential Three Stage",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="sequential",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
            financial_deadline=timezone.now() + timedelta(days=30),
        )
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["stage_key"], "eoi")
        self.assertEqual(response.data["tender_procurement_workflow"], "sequential")
        self.assertIsNotNone(response.data["deadline"])

        # RMT shortlists -> technical draft unlocked
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{response.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        technical_draft = TenderBid.objects.filter(
            tender=tender, vendor_id=str(self.vendor.id), bid_stage="technical",
            status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(technical_draft)
        self.assertTrue(technical_draft.technical_stage_unlocked)

    def test_tender_workflow_validation_requires_staged_deadlines(self):
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            {
                "name": "Missing Deadlines",
                "department": "DoE",
                "category": "SHS",
                "status": "Draft",
                "application_type": "Application Window",
                "procurement_method": "National",
                "address_for_document": "Addr",
                "address_for_security": "Addr",
                "place_for_opening": "Maseru",
                "bidders_eligibility": "All",
                "time_for_completion": "12 months",
                "invited_by": "RBF",
                "bidding_currency": "LSL",
                "instruction": "Read carefully. " * 10,
                "contact_details": "123",
                "target_site_type": "Community",
                "deadline": timezone.now().isoformat(),
                "technology_types": ["SHS"],
                "target_districts": ["Maseru"],
                "procurement_workflow": "sequential",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("technical_deadline", response.data)
        self.assertIn("financial_deadline", response.data)

    def test_open_financial_stage_unlocks_technical_passing_bidders(self):
        tender = Tender.objects.create(
            reference_number="WF-SEQ-002",
            name="Open Financial Stage",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.CLOSED,
            deadline=timezone.now() - timedelta(days=1),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="sequential",
            technical_threshold=70,
            eoi_deadline=timezone.now() - timedelta(days=10),
            technical_deadline=timezone.now() - timedelta(days=5),
            financial_deadline=timezone.now() + timedelta(days=5),
        )
        eoi = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_stage="eoi",
            status=BidStatus.ACCEPTED,
            version_number=1,
        )
        tech = TenderBid.objects.create(
            tender=tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_stage="technical",
            status=BidStatus.ACCEPTED,
            version_number=2,
            technical_stage_unlocked=True,
            technical_stage_source_bid=eoi,
        )
        tac_user = User.objects.create_user(
            username="wf_tac",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="WF TAC",
            email="wf-tac@example.com",
        )
        TenderBidEvaluation.objects.create(
            bid=tech,
            evaluator=tac_user,
            status=EvaluationStatus.SCORED,
            technical_score=80,
            total_score=80,
        )
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(f"/api/tenders/{tender.id}/open_financial_stage/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["opened_bids"], [str(tech.id)])
        financial_draft = TenderBid.objects.filter(
            tender=tender, vendor_id=str(self.vendor.id), bid_stage="financial",
            status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(financial_draft)
        self.assertTrue(financial_draft.financial_stage_unlocked)
        tech.refresh_from_db()
        self.assertTrue(tech.financial_stage_unlocked)

    def test_eoi_combined_tender_forces_restricted_method_on_create(self):
        from .models import ProcurementMethod, ProcurementWorkflow

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            {
                "name": "EOI Combined Tender",
                "department": "DoE",
                "category": "SHS",
                "status": "Draft",
                "application_type": "Application Window",
                "procurement_method": "National",
                "address_for_document": "Addr",
                "address_for_security": "Addr",
                "place_for_opening": "Maseru",
                "bidders_eligibility": "All",
                "time_for_completion": "12 months",
                "invited_by": "RBF",
                "bidding_currency": "LSL",
                "instruction": "Read carefully. " * 10,
                "contact_details": "123",
                "target_site_type": "Community",
                "deadline": (timezone.now() + timedelta(days=30)).isoformat(),
                "technology_types": ["SHS"],
                "target_districts": ["Maseru"],
                "procurement_workflow": "eoi_combined",
                "eoi_deadline": (timezone.now() + timedelta(days=10)).isoformat(),
                "technical_deadline": (timezone.now() + timedelta(days=20)).isoformat(),
                "financial_deadline": (timezone.now() + timedelta(days=20)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["procurement_workflow"], "eoi_combined")
        # Procurement method auto-locked to Restricted Tendering regardless of input.
        self.assertEqual(response.data["procurement_method"], ProcurementMethod.RESTRICTED)
        # financial deadline is not used for a combined-style workflow.
        self.assertIsNone(response.data["financial_deadline"])

    def test_single_stage_combined_tender_allows_open_method_and_opens_directly(self):
        from .models import ProcurementWorkflow

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            {
                "name": "Single Stage Combined Tender",
                "department": "DoE",
                "category": "SHS",
                "status": "Draft",
                "application_type": "Application Window",
                "procurement_method": "National",
                "address_for_document": "Addr",
                "address_for_security": "Addr",
                "place_for_opening": "Maseru",
                "bidders_eligibility": "All",
                "time_for_completion": "12 months",
                "invited_by": "RBF",
                "bidding_currency": "LSL",
                "instruction": "Read carefully. " * 10,
                "contact_details": "123",
                "target_site_type": "Community",
                "deadline": (timezone.now() + timedelta(days=30)).isoformat(),
                "technology_types": ["SHS"],
                "target_districts": ["Maseru"],
                "procurement_workflow": "combined",
                "technical_deadline": (timezone.now() + timedelta(days=20)).isoformat(),
                "financial_deadline": (timezone.now() + timedelta(days=20)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["procurement_workflow"], "combined")
        # Single-stage Combined is not auto-locked to Restricted — the method is kept.
        self.assertEqual(response.data["procurement_method"], "National")
        self.assertIsNone(response.data["eoi_deadline"])
        self.assertIsNone(response.data["financial_deadline"])

        # Publish it directly (mirroring a real RBF publish flow) so a pre-qualified
        # vendor can open the Combined stage without any EOI step.
        Tender.objects.filter(id=response.data["id"]).update(status=TenderStatus.PUBLISHED, published_at=timezone.now())
        self.client.force_authenticate(self.vendor)
        bid_resp = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(response.data["id"]),
                "bid_stage": "combined",
                "technical_proposal": "Tech design summary. " * 20,
                "system_configuration": json.dumps({
                    "technology_type": "SHS",
                    "rated_power_w": 250,
                    "battery_capacity_wh": 1200,
                    "pv_panel_size_w": 300,
                    "inverter_type": "Hybrid",
                }),
                "boq_items": json.dumps([
                    {"item_number": 1, "description": "Solar kit", "qty": 100, "unit": "set", "unit_price": 1800, "total": 180000},
                ]),
                "om_strategy_summary": "O&M strategy covering preventative maintenance and local technicians. " * 6,
                "sites": json.dumps([
                    {
                        "site_name": "Roma Cluster",
                        "district": "Maseru",
                        "latitude": -29.45,
                        "longitude": 27.74,
                        "number_of_households": 120,
                        "target_beneficiary_type": "standard",
                    }
                ]),
                "status": "Draft",
            },
            format="json",
        )
        self.assertEqual(bid_resp.status_code, status.HTTP_201_CREATED, bid_resp.data)
        self.assertEqual(bid_resp.data["stage_key"], "combined")
        self.assertEqual(bid_resp.data["tender_procurement_workflow"], "combined")

    def test_eoi_combined_shortlist_auto_invites_and_opens_combined_stage(self):
        from .models import ProcurementWorkflow, TenderInvitedVendor

        tender = Tender.objects.create(
            reference_number="WF-EOI-C-001",
            name="EOI Combined Restricted",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
        )
        # The EOI stage of a Restricted 'EOI → Combined' tender is open to all approved
        # vendors, even without an invite.
        self.client.force_authenticate(self.vendor)
        eoi = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(eoi.status_code, status.HTTP_201_CREATED, eoi.data)
        self.assertEqual(eoi.data["stage_key"], "eoi")
        self.assertEqual(eoi.data["tender_procurement_workflow"], "eoi_combined")

        # Shortlist -> combined draft unlocked AND the vendor auto-added to the roster.
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{eoi.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        self.assertTrue(
            TenderInvitedVendor.objects.filter(tender=tender, vendor_id=str(self.vendor.id)).exists(),
            "Shortlisting an EOI on a Restricted tender should auto-invite the vendor",
        )
        combined_draft = TenderBid.objects.filter(
            tender=tender, vendor_id=str(self.vendor.id), bid_stage="combined",
            status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(combined_draft)
        self.assertTrue(combined_draft.technical_stage_unlocked)

    def _standard_tender_payload(self, **overrides):
        payload = {
            "name": "Standard Tender",
            "department": "DoE",
            "category": "SHS",
            "status": "Draft",
            "application_type": "Application Window",
            "procurement_method": "National",
            "address_for_document": "Addr",
            "address_for_security": "Addr",
            "place_for_opening": "Maseru",
            "bidders_eligibility": "All",
            "time_for_completion": "12 months",
            "invited_by": "RBF",
            "bidding_currency": "LSL",
            "instruction": "Read carefully. " * 10,
            "contact_details": "123",
            "target_site_type": "Community",
            "deadline": (timezone.now() + timedelta(days=30)).isoformat(),
            "technology_types": ["SHS"],
            "target_districts": ["Maseru"],
        }
        payload.update(overrides)
        return payload

    def test_is_eoi_invite_only_tender_skips_technical_deadline_requirement(self):
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Solar Rollout EOI Invite",
                is_eoi_invite_only=True,
                eoi_deadline=(timezone.now() + timedelta(days=10)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["procurement_workflow"], "eoi_combined")
        self.assertTrue(response.data["is_eoi_invite_only"])
        self.assertIsNone(response.data["technical_deadline"])

    def test_is_eoi_invite_only_tender_does_not_require_place_for_opening(self):
        """An EOI Invite never holds a bid-opening event, so 'Place for Tender Opening' —
        required for every normal tender — must not be required for one. Regression
        guard: the payload deliberately omits place_for_opening entirely (rather than
        relying on _standard_tender_payload's default), since earlier test payloads
        always sent it and so never actually exercised this relaxation."""
        self.client.force_authenticate(self.rmt_user)
        payload = self._standard_tender_payload(
            name="No Opening Venue EOI Invite",
            is_eoi_invite_only=True,
            eoi_deadline=(timezone.now() + timedelta(days=10)).isoformat(),
        )
        payload.pop("place_for_opening", None)
        response = self.client.post("/api/tenders/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # A normal tender still requires it.
        normal_payload = self._standard_tender_payload(name="Normal Tender Needs Opening Venue")
        normal_payload.pop("place_for_opening", None)
        normal_response = self.client.post("/api/tenders/", normal_payload, format="json")
        self.assertEqual(normal_response.status_code, status.HTTP_400_BAD_REQUEST, normal_response.data)
        self.assertIn("place_for_opening", normal_response.data)

    def test_is_eoi_invite_only_requires_eoi_deadline(self):
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Missing EOI Deadline Invite",
                is_eoi_invite_only=True,
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("eoi_deadline", response.data)

    def _create_shortlisted_eoi_invite_tender(self):
        """An EOI Invite tender with self.vendor already shortlisted on it."""
        from .models import TenderInvitedVendor

        eoi_tender = Tender.objects.create(
            reference_number="WF-EOI-INV-001",
            name="District Solar EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
        )
        self.client.force_authenticate(self.vendor)
        eoi = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(eoi_tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(eoi.status_code, status.HTTP_201_CREATED, eoi.data)
        self.client.force_authenticate(self.rmt_user)
        accept = self.client.post(f"/api/tender-bids/{eoi.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        self.assertTrue(
            TenderInvitedVendor.objects.filter(tender=eoi_tender, vendor_id=str(self.vendor.id)).exists()
        )
        return eoi_tender

    def test_linked_eoi_tender_copies_invited_vendors_and_locks_name(self):
        from .models import TenderInvitedVendor

        eoi_tender = self._create_shortlisted_eoi_invite_tender()

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="A Totally Different Name",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # The tender name always matches the EOI Invite it's linked to, regardless of
        # what was submitted.
        self.assertEqual(response.data["name"], eoi_tender.name)
        self.assertTrue(response.data["skips_eoi_stage"])
        self.assertTrue(
            TenderInvitedVendor.objects.filter(tender_id=response.data["id"], vendor_id=str(self.vendor.id)).exists()
        )

        # The EOI Invite tender's own detail should list the tender(s) linked to it, so
        # an RBF Official can trace an EOI Invite forward to the RFP it produced.
        eoi_detail = self.client.get(f"/api/tenders/{eoi_tender.id}/")
        self.assertEqual(eoi_detail.status_code, status.HTTP_200_OK, eoi_detail.data)
        linked_ids = [row["id"] for row in eoi_detail.data["linked_tenders_summary"]]
        self.assertIn(str(response.data["id"]), linked_ids)

    def test_eoi_invite_cannot_be_linked_to_two_tenders(self):
        from .models import TenderInvitedVendor

        eoi_tender = self._create_shortlisted_eoi_invite_tender()

        # First link succeeds
        self.client.force_authenticate(self.rmt_user)
        resp1 = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="First Linked Tender",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.data)

        # Second link to the same EOI Invite must fail
        resp2 = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Second Linked Tender",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=25)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST, resp2.data)
        self.assertIn("already been used", str(resp2.data))

        # The used EOI Invite should no longer appear in candidates list
        candidates = self.client.get("/api/tenders/eoi_invite_candidates/")
        self.assertEqual(candidates.status_code, status.HTTP_200_OK)
        candidate_ids = [c["id"] for c in candidates.data]
        self.assertNotIn(str(eoi_tender.id), candidate_ids)

    def test_eoi_invite_list_exposes_linked_tender_count(self):
        """The tender list reports how many tenders each EOI Invite has already been
        linked to, so the EOI Invites UI can flag/blur used invites."""
        eoi_tender = self._create_shortlisted_eoi_invite_tender()

        # Unlinked EOI Invite → linked_tender_count 0
        self.client.force_authenticate(self.rmt_user)
        listing = self.client.get(f"/api/tenders/?is_eoi_invite_only=true")
        self.assertEqual(listing.status_code, status.HTTP_200_OK, listing.data)
        row = next(r for r in listing.data["results"] if str(r["id"]) == str(eoi_tender.id))
        self.assertEqual(row["linked_tender_count"], 0)

        # After linking → 1
        linked = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Linked Tender for Count",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(linked.status_code, status.HTTP_201_CREATED, linked.data)
        listing2 = self.client.get(f"/api/tenders/?is_eoi_invite_only=true")
        self.assertEqual(listing2.status_code, status.HTTP_200_OK, listing2.data)
        row2 = next(r for r in listing2.data["results"] if str(r["id"]) == str(eoi_tender.id))
        self.assertEqual(row2["linked_tender_count"], 1)

    def test_new_bid_on_linked_tender_opens_at_combined_not_eoi(self):
        eoi_tender = self._create_shortlisted_eoi_invite_tender()

        self.client.force_authenticate(self.rmt_user)
        create_resp = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Linked Combined Tender",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        linked_tender_id = create_resp.data["id"]
        Tender.objects.filter(id=linked_tender_id).update(status=TenderStatus.PUBLISHED, published_at=timezone.now())

        # The already-shortlisted vendor can submit a Combined bid directly - no EOI
        # step on this tender at all.
        self.client.force_authenticate(self.vendor)
        bid_resp = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(linked_tender_id),
                "bid_stage": "combined",
                "technical_proposal": "Tech design summary. " * 20,
                "system_configuration": json.dumps({
                    "technology_type": "SHS",
                    "rated_power_w": 250,
                    "battery_capacity_wh": 1200,
                    "pv_panel_size_w": 300,
                    "inverter_type": "Hybrid",
                }),
                "boq_items": json.dumps([
                    {"item_number": 1, "description": "Solar kit", "qty": 100, "unit": "set", "unit_price": 1800, "total": 180000},
                ]),
                "om_strategy_summary": "O&M strategy covering preventative maintenance and local technicians. " * 6,
                "sites": json.dumps([
                    {
                        "site_name": "Roma Cluster",
                        "district": "Maseru",
                        "latitude": -29.45,
                        "longitude": 27.74,
                        "number_of_households": 120,
                        "target_beneficiary_type": "standard",
                    }
                ]),
                "status": "Draft",
            },
            format="json",
        )
        self.assertEqual(bid_resp.status_code, status.HTTP_201_CREATED, bid_resp.data)
        self.assertEqual(bid_resp.data["stage_key"], "combined")

        # A different, non-shortlisted approved vendor must NOT be able to bid.
        other_vendor = User.objects.create_user(
            username="wf_vendor_other",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="WF Vendor Other",
            email="wf-vendor-other@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=other_vendor,
            company_name="WF Vendor Other Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )
        self.client.force_authenticate(other_vendor)
        rejected_resp = self.client.post(
            "/api/tender-bids/",
            {"tender": str(linked_tender_id), "bid_stage": "combined", "status": "Draft"},
            format="json",
        )
        self.assertEqual(rejected_resp.status_code, status.HTTP_400_BAD_REQUEST, rejected_resp.data)
        self.assertIn("only specifically invited vendors can bid", str(rejected_resp.data))

    def test_eoi_invite_candidates_lists_only_shortlisted_eoi_invite_tenders(self):
        eoi_tender = self._create_shortlisted_eoi_invite_tender()
        Tender.objects.create(
            reference_number="WF-EOI-INV-002",
            name="Unshortlisted EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
        )
        Tender.objects.create(
            reference_number="WF-NORMAL-001",
            name="Normal Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
        )

        # Link a tender to the shortlisted EOI Invite
        self.client.force_authenticate(self.rmt_user)
        link_resp = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Linked Tender",
                procurement_workflow="eoi_combined",
                linked_eoi_tender=str(eoi_tender.id),
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(link_resp.status_code, status.HTTP_201_CREATED, link_resp.data)

        response = self.client.get("/api/tenders/eoi_invite_candidates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        names = [row["name"] for row in response.data]
        # After linking, the used EOI Invite should no longer appear in candidates
        self.assertNotIn("District Solar EOI Invite", names)
        self.assertNotIn("Unshortlisted EOI Invite", names)
        self.assertNotIn("Normal Tender", names)

    def test_procurement_metadata_fields_round_trip_on_create(self):
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Metadata Round Trip Tender",
                procurement_workflow="combined",
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
                language_of_bid_submission="English",
                budget_disclosure="published",
                clarification_deadline=(timezone.now() + timedelta(days=5)).isoformat(),
                site_visit_date=(timezone.now() + timedelta(days=7)).isoformat(),
                bid_validity_period_days=90,
                document_fee_amount="150.00",
                document_fee_type="Bank Draft",
                document_fee_refundable=True,
                minimum_warranty_period_months=24,
                submission_method="hybrid",
                digital_signature_required=False,
                advertisement_channels=["National Gazette", "Local Newspaper"],
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["language_of_bid_submission"], "English")
        self.assertEqual(response.data["budget_disclosure"], "published")
        self.assertIsNotNone(response.data["clarification_deadline"])
        self.assertIsNotNone(response.data["site_visit_date"])
        self.assertEqual(response.data["bid_validity_period_days"], 90)
        self.assertEqual(str(response.data["document_fee_amount"]), "150.00")
        self.assertEqual(response.data["document_fee_type"], "Bank Draft")
        self.assertTrue(response.data["document_fee_refundable"])
        self.assertEqual(response.data["minimum_warranty_period_months"], 24)
        self.assertEqual(response.data["submission_method"], "hybrid")
        self.assertFalse(response.data["digital_signature_required"])
        self.assertEqual(
            set(response.data["advertisement_channels"]), {"National Gazette", "Local Newspaper"}
        )

    def test_procurement_metadata_fields_are_optional_with_sane_defaults(self):
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tenders/",
            self._standard_tender_payload(
                name="Minimal Metadata Tender",
                procurement_workflow="combined",
                technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["language_of_bid_submission"], "")
        self.assertEqual(response.data["budget_disclosure"], "")
        self.assertIsNone(response.data["clarification_deadline"])
        self.assertIsNone(response.data["site_visit_date"])
        self.assertIsNone(response.data["bid_validity_period_days"])
        self.assertIsNone(response.data["document_fee_amount"])
        self.assertEqual(response.data["document_fee_type"], "")
        self.assertFalse(response.data["document_fee_refundable"])
        self.assertIsNone(response.data["minimum_warranty_period_months"])
        self.assertEqual(response.data["submission_method"], "online_only")
        self.assertTrue(response.data["digital_signature_required"])
        self.assertIsNone(response.data["max_vendors_to_shortlist"])
        self.assertEqual(response.data["advertisement_channels"], [])

    def _open_tender_with_budget(self, budget_disclosure="", ref="WF-BUDGET-001"):
        return Tender.objects.create(
            reference_number=ref,
            name="Budget Disclosure Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            procurement_method="Open Tendering",
            procurement_workflow="combined",
            technical_deadline=timezone.now() + timedelta(days=20),
            budget=50000,
            budget_disclosure=budget_disclosure,
        )

    def test_budget_hidden_from_vendor_by_default_and_when_confidential(self):
        for disclosure in ("", "confidential"):
            tender = self._open_tender_with_budget(disclosure, ref=f"WF-BUDGET-HIDE-{disclosure or 'blank'}")
            self.client.force_authenticate(self.vendor)
            detail = self.client.get(f"/api/tenders/{tender.id}/")
            self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
            self.assertNotIn("budget", detail.data)
            listing = self.client.get("/api/tenders/")
            self.assertEqual(listing.status_code, status.HTTP_200_OK, listing.data)
            row = next(r for r in listing.data["results"] if str(r["id"]) == str(tender.id))
            self.assertNotIn("budget", row)

    def test_budget_visible_to_vendor_when_published(self):
        tender = self._open_tender_with_budget("published", ref="WF-BUDGET-PUB-001")
        self.client.force_authenticate(self.vendor)
        detail = self.client.get(f"/api/tenders/{tender.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(str(detail.data["budget"]), "50000.00")
        listing = self.client.get("/api/tenders/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK, listing.data)
        row = next(r for r in listing.data["results"] if str(r["id"]) == str(tender.id))
        self.assertEqual(str(row["budget"]), "50000.00")

    def test_rbf_official_always_sees_budget_regardless_of_disclosure(self):
        tender = self._open_tender_with_budget("confidential", ref="WF-BUDGET-RMT-001")
        self.client.force_authenticate(self.rmt_user)
        detail = self.client.get(f"/api/tenders/{tender.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(str(detail.data["budget"]), "50000.00")

    def test_lot_budget_hidden_from_vendor_unless_published(self):
        tender = self._open_tender_with_budget("confidential", ref="WF-LOTBUDGET-001")
        TenderLot.objects.create(tender=tender, name="Lot A", position=0, budget=20000)
        self.client.force_authenticate(self.vendor)
        detail = self.client.get(f"/api/tenders/{tender.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(len(detail.data["lots"]), 1)
        self.assertNotIn("budget", detail.data["lots"][0])

    def test_lot_budget_visible_to_vendor_when_published(self):
        tender = self._open_tender_with_budget("published", ref="WF-LOTBUDGET-PUB-001")
        TenderLot.objects.create(tender=tender, name="Lot A", position=0, budget=20000)
        self.client.force_authenticate(self.vendor)
        detail = self.client.get(f"/api/tenders/{tender.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(str(detail.data["lots"][0]["budget"]), "20000.00")

    def test_tender_update_activity_log_records_before_after_field_changes(self):
        self.client.force_authenticate(self.rmt_user)
        create_payload = self._standard_tender_payload(
            name="Activity Diff Tender", budget=50000,
            procurement_workflow="combined", technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
        )
        created = self.client.post("/api/tenders/", create_payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        tender_id = created.data["id"]

        # Real edits resubmit the whole form — only "name" and "budget" actually change.
        update_payload = {**create_payload, "name": "Renamed Activity Diff Tender", "budget": 99999}
        response = self.client.put(f"/api/tenders/{tender_id}/", update_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        activity = self.client.get(f"/api/tenders/{tender_id}/activity/")
        self.assertEqual(activity.status_code, status.HTTP_200_OK, activity.data)
        entry = next(e for e in activity.data if e["action"] == "tender_updated")
        changes = {c["field"]: c for c in entry["details"]["field_changes"]}

        self.assertEqual(changes["name"]["old"], "Activity Diff Tender")
        self.assertEqual(changes["name"]["new"], "Renamed Activity Diff Tender")
        self.assertEqual(changes["name"]["label"], "Tender Name")
        self.assertEqual(changes["budget"]["old"], "50000.00")
        self.assertEqual(changes["budget"]["new"], "99999.00")
        self.assertEqual(changes["budget"]["label"], "Budget Estimate")
        # Unchanged fields that were still part of the resubmitted form must not appear.
        self.assertNotIn("department", changes)
        self.assertNotIn("category", changes)

    def test_tender_update_activity_log_omits_unchanged_submitted_fields(self):
        self.client.force_authenticate(self.rmt_user)
        create_payload = self._standard_tender_payload(
            name="Activity Diff Tender 2", budget=50000,
            procurement_workflow="combined", technical_deadline=(timezone.now() + timedelta(days=20)).isoformat(),
        )
        created = self.client.post("/api/tenders/", create_payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        tender_id = created.data["id"]

        update_payload = {**create_payload, "budget": 99999}
        response = self.client.put(f"/api/tenders/{tender_id}/", update_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        activity = self.client.get(f"/api/tenders/{tender_id}/activity/")
        entry = next(e for e in activity.data if e["action"] == "tender_updated")
        changed_fields = {c["field"] for c in entry["details"]["field_changes"]}
        self.assertNotIn("name", changed_fields)
        self.assertIn("budget", changed_fields)

    def test_max_vendors_to_shortlist_is_advisory_not_enforced(self):
        """An EOI Invite with max_vendors_to_shortlist=1 can still have 2 vendors
        shortlisted - the cap is advisory (shown to the RBF Official), never enforced
        server-side."""
        from .models import TenderInvitedVendor

        eoi_tender = Tender.objects.create(
            reference_number="WF-EOI-INV-003",
            name="Capped Shortlist EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
            max_vendors_to_shortlist=1,
        )
        second_vendor = User.objects.create_user(
            username="wf_vendor_second",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="WF Vendor Second",
            email="wf-vendor-second@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=second_vendor,
            company_name="WF Vendor Second Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )

        def _submit_and_accept(vendor):
            self.client.force_authenticate(vendor)
            eoi = self.client.post(
                "/api/tender-bids/",
                {
                    "tender": str(eoi_tender.id),
                    "bid_stage": "eoi",
                    "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                    "company_credentials_file": self._upload(),
                    "financial_standing_file": self._upload(),
                    "technical_experience_file": self._upload(),
                    "track_record_file": self._upload(),
                    "female_target_pct": 55,
                    "vulnerable_target_pct": 35,
                    "low_income_target_pct": 60,
                    "inclusion_commitment_confirmed": "true",
                    "status": "Submitted",
                },
                format="multipart",
            )
            self.assertEqual(eoi.status_code, status.HTTP_201_CREATED, eoi.data)
            self.client.force_authenticate(self.rmt_user)
            accept = self.client.post(f"/api/tender-bids/{eoi.data['id']}/accept/", {}, format="json")
            self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)

        _submit_and_accept(self.vendor)
        _submit_and_accept(second_vendor)

        self.assertEqual(
            TenderInvitedVendor.objects.filter(tender=eoi_tender).count(), 2
        )

    @patch("rbf.tenders.views.NotificationService.dispatch_email", return_value=1)
    @patch("rbf.tenders.views.email_configured", return_value=True)
    def test_eoi_invite_publish_skips_verify_and_approval_gate(self, _mock_email_configured, _mock_dispatch_email):
        """An EOI Invite has no award/financial risk, so it can be published directly —
        unlike a real tender, it never needs is_verified or Super Admin publish
        approval first."""
        eoi_tender = Tender.objects.create(
            reference_number="WF-EOI-PUB-001",
            name="Direct Publish EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            target_districts=["Maseru"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
            is_verified=False,
        )
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(f"/api/tenders/{eoi_tender.id}/publish/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], TenderStatus.PUBLISHED)
        eoi_tender.refresh_from_db()
        self.assertEqual(eoi_tender.status, TenderStatus.PUBLISHED)
        self.assertIsNotNone(eoi_tender.published_at)

    def test_real_tender_publish_still_requires_verification_first(self):
        """Confirms the EOI-invite exemption above didn't loosen the gate for real
        tenders — an unverified real tender is still rejected."""
        tender = Tender.objects.create(
            reference_number="WF-REAL-PUB-001",
            name="Needs Verification Tender",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            target_districts=["Maseru"],
            is_verified=False,
        )
        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(f"/api/tenders/{tender.id}/publish/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        tender.refresh_from_db()
        self.assertEqual(tender.status, TenderStatus.DRAFT)

    def test_published_eoi_invite_visible_to_any_approved_vendor(self):
        """The vendor queryset has no is_eoi_invite_only filter at all — a published EOI
        Invite is visible to every approved vendor, same as the existing Restricted +
        EOI_COMBINED exemption already covers for real tenders."""
        eoi_tender = Tender.objects.create(
            reference_number="WF-EOI-VIS-001",
            name="Vendor-Visible EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            target_districts=["Maseru"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
            published_at=timezone.now(),
        )
        self.client.force_authenticate(self.vendor)
        response = self.client.get("/api/tenders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ids = [str(row["id"]) for row in response.data.get("results", response.data)]
        self.assertIn(str(eoi_tender.id), ids)

    def test_vendor_can_submit_eoi_bid_on_eoi_invite_tender_without_prior_invite(self):
        """_assert_vendor_submission_access's open-EOI-stage exemption is keyed on
        procurement_workflow == EOI_COMBINED, which is true for is_eoi_invite_only
        tenders too — no prior shortlist/invite should be required to submit."""
        eoi_tender = Tender.objects.create(
            reference_number="WF-EOI-SUB-001",
            name="Open Submission EOI Invite",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["SHS"],
            target_districts=["Maseru"],
            procurement_workflow="eoi_combined",
            procurement_method="Restricted Tendering",
            is_eoi_invite_only=True,
            eoi_deadline=timezone.now() + timedelta(days=10),
            published_at=timezone.now(),
        )
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(eoi_tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Unsolicited-but-open EOI submission. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class BidStageGatingTests(APITestCase):
    """Stage-sequence behavior: bid_stage persists correctly, and stage access is
    gated on prior-stage clearance (via the view-level access checks)."""

    def setUp(self):
        self.vendor = User.objects.create_user(
            username="gate_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Gate Vendor",
            organization_name="Gate Vendor Ltd",
            email="gate-vendor@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="Gate Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 4",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )
        self.workflow_endpoint = "/api/tender-bids/"

    def _upload(self):
        return SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

    def _sequential_tender(self, **kwargs):
        defaults = dict(
            reference_number="GATE-SEQ-001",
            name="Gate Sequential",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="sequential",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
            financial_deadline=timezone.now() + timedelta(days=30),
        )
        defaults.update(kwargs)
        return Tender.objects.create(**defaults)

    def _combined_tender(self, **kwargs):
        defaults = dict(
            reference_number="GATE-COMB-001",
            name="Gate Combined",
            department="Department of Energy",
            category="SHS",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            stage_type="pre_qualification",
            technology_types=["SHS"],
            procurement_workflow="combined",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
            financial_deadline=timezone.now() + timedelta(days=20),
        )
        defaults.update(kwargs)
        return Tender.objects.create(**defaults)

    def test_new_bid_persists_requested_bid_stage(self):
        """Regression: bid_stage was read-only and silently saved as EOI."""
        tender = self._sequential_tender()
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "status": "Draft",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["stage_key"], "eoi")
        self.assertEqual(response.data["bid_stage"], "eoi")

    def test_combined_tender_creates_combined_record(self):
        """Combined tenders store bid_stage=combined (not a separate technical record)."""
        tender = self._combined_tender()
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "status": "Draft",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["stage_key"], "eoi")

    def test_vendor_blocked_from_technical_before_eoi_cleared(self):
        """A vendor cannot create a technical record until their EOI is accepted."""
        tender = self._sequential_tender()
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "technical",
                "tech_tier": "Tier 4",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_sequential_eoi_accept_unlocks_submittable_technical_draft(self):
        """After RMT accepts the EOI, a technical draft exists and the vendor may submit it."""
        tender = self._sequential_tender()
        rmt = User.objects.create_user(
            username="gate_rmt",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="Gate RMT",
            email="gate-rmt@example.com",
        )
        self.client.force_authenticate(self.vendor)
        eoi = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "tech_tier": "Tier 4",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(eoi.status_code, status.HTTP_201_CREATED, eoi.data)
        self.assertEqual(eoi.data["stage_key"], "eoi")

        # RMT accepts -> technical draft unlocked
        self.client.force_authenticate(rmt)
        accept = self.client.post(f"/api/tender-bids/{eoi.data['id']}/accept/", {}, format="json")
        self.assertEqual(accept.status_code, status.HTTP_200_OK, accept.data)
        technical_draft = TenderBid.objects.filter(
            tender=tender, vendor_id=str(self.vendor.id), bid_stage="technical", status=BidStatus.DRAFT,
        ).first()
        self.assertIsNotNone(technical_draft)
        self.assertTrue(technical_draft.technical_stage_unlocked)

    def test_submitted_bid_requires_tender_stage_custom_documents(self):
        """Per-stage required documents are enforced server-side on submission."""
        from .models import TenderRequiredDocument
        tender = self._sequential_tender()
        TenderRequiredDocument.objects.create(
            tender=tender, name="Tax Clearance", expected_type="pdf", bid_stage="eoi", position=1,
        )
        TenderRequiredDocument.objects.create(
            tender=tender, name="Safety Certificate", expected_type="pdf",
            bid_stage="technical", position=2,
        )
        self.client.force_authenticate(self.vendor)
        # Submit EOI without the required "Tax Clearance" custom document -> rejected.
        response = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "tech_tier": "Tier 4",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("custom_documents.Tax Clearance", response.data)

        # Same EOI but with the custom doc uploaded -> accepted.
        response = self.client.post(
            self.workflow_endpoint,
            {
                "tender": str(tender.id),
                "bid_stage": "eoi",
                "eoi_narrative": "Community clean energy rollout narrative. " * 14,
                "company_credentials_file": self._upload(),
                "financial_standing_file": self._upload(),
                "technical_experience_file": self._upload(),
                "track_record_file": self._upload(),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "tech_tier": "Tier 4",
                "status": "Submitted",
                "custom_documents": json.dumps([{"name": "Tax Clearance", "expected_type": "pdf", "file_name": "tax.pdf"}]),
                "custom_documents_files": self._upload(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class LotWiseTenderTests(APITestCase):
    """Lot-wise tendering: creating a tender with lots, per-lot bid pricing, per-lot
    award ranking, and awarding different lots to different vendors."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="lot_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Lot Admin",
        )
        self.vendor_a = User.objects.create_user(
            username="lot_vendor_a",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Lot Vendor A",
            organization_name="Vendor A Ltd",
            email="vendor-a@example.com",
        )
        self.vendor_b = User.objects.create_user(
            username="lot_vendor_b",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Lot Vendor B",
            organization_name="Vendor B Ltd",
            email="vendor-b@example.com",
        )
        for vendor in (self.vendor_a, self.vendor_b):
            VendorPrequalification.objects.create(
                vendor=vendor,
                company_name=vendor.organization_name,
                status=PrequalificationStatus.APPROVED,
                tech_tier="Level 3",
                female_beneficiary_target=55,
                vulnerable_group_target=35,
            )
        self.tender = Tender.objects.create(
            reference_number="LOT-TND-001",
            name="Lot-Wise Mini-Grid Tender",
            department="Department of Energy",
            category="GMG",
            status=TenderStatus.PUBLISHED,
            deadline=timezone.now() + timedelta(days=30),
            technology_types=["GMG"],
            procurement_workflow="sequential",
            eoi_deadline=timezone.now() + timedelta(days=10),
            technical_deadline=timezone.now() + timedelta(days=20),
            financial_deadline=timezone.now() + timedelta(days=30),
            max_lots_per_bidder=2,
        )
        self.lot1 = TenderLot.objects.create(tender=self.tender, name="Lot 1: Maseru", position=0)
        self.lot2 = TenderLot.objects.create(tender=self.tender, name="Lot 2: Leribe", position=1)

    def _submitted_financial_bid(self, vendor, offers):
        """Create a Financial-stage bid with lot offers, bypassing the wizard's earlier
        stages — mirrors how other award-ranking tests seed bids directly via the ORM."""
        bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_stage="financial",
            status=BidStatus.SUBMITTED,
        )
        for lot, amount in offers.items():
            TenderBidLotOffer.objects.create(bid=bid, lot=lot, bid_amount=amount)
        return bid

    def _score_technical(self, bid, score=80):
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=self.admin_user,
            status=EvaluationStatus.SCORED,
            technical_score=score,
            feasibility_score=score,
            kpi_score=score,
            gender_score=70,
            environmental_score=score,
            om_score=score,
            total_score=score,
        )

    def _score_financial_for_lot(self, bid, lot, score):
        TenderBidEvaluation.objects.create(
            bid=bid,
            lot=lot,
            evaluator=self.admin_user,
            stage=EvaluationStage.FINANCIAL,
            status=EvaluationStatus.SCORED,
            financial_score=score,
            financial_score_auto_calculated=True,
            total_score=score,
        )

    def test_tender_creation_accepts_lots_payload(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.post(
            "/api/tenders/",
            {
                "name": "Lot Creation Tender",
                "department": "DoE",
                "application_type": "Application Window",
                "procurement_method": "National",
                "address_for_document": "Addr",
                "place_for_opening": "Maseru",
                "bidders_eligibility": "All",
                "time_for_completion": "12 months",
                "invited_by": "RBF",
                "bidding_currency": "LSL",
                "instruction": "Read carefully. " * 10,
                "contact_details": "123",
                "target_site_type": "Community",
                "technology_types": ["GMG"],
                "target_districts": ["Maseru"],
                "procurement_workflow": "sequential",
                "eoi_deadline": (timezone.now() + timedelta(days=3)).isoformat(),
                "technical_deadline": (timezone.now() + timedelta(days=6)).isoformat(),
                "financial_deadline": (timezone.now() + timedelta(days=9)).isoformat(),
                "max_lots_per_bidder": 1,
                "lots": json.dumps([
                    {"name": "Lot A", "description": "Northern region", "position": 0},
                    {"name": "Lot B", "description": "Southern region", "position": 1},
                ]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data["lots"]), 2)
        self.assertEqual({lot["name"] for lot in response.data["lots"]}, {"Lot A", "Lot B"})
        self.assertEqual(response.data["max_lots_per_bidder"], 1)

    def test_bid_submission_requires_at_least_one_lot_offer(self):
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "financial",
                "status": "Submitted",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lot_offers", response.data)

    def test_bid_submission_enforces_max_lots_per_bidder(self):
        lot3 = TenderLot.objects.create(tender=self.tender, name="Lot 3: Berea", position=2)
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "financial",
                "status": "Submitted",
                "lot_offers": json.dumps([
                    {"lot": self.lot1.id, "bid_amount": "100000"},
                    {"lot": self.lot2.id, "bid_amount": "120000"},
                    {"lot": lot3.id, "bid_amount": "90000"},
                ]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lot_offers", response.data)

    def test_bid_submission_accepts_partial_lot_selection(self):
        """Bidders may price a subset of lots (here: only Lot 1 of 2)."""
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "financial",
                "status": "Submitted",
                "lot_offers": json.dumps([
                    {"lot": self.lot1.id, "bid_amount": "100000", "subsidy_requested": "60000"},
                ]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bid = TenderBid.objects.get(id=response.data["id"])
        self.assertEqual(bid.lot_offers.count(), 1)
        self.assertEqual(bid.lot_offers.first().lot_id, self.lot1.id)

    def test_lot_offer_with_boq_template_locks_items_and_computes_amount_per_lot(self):
        """Each lot can have its own independent BOQ design; a vendor's per-lot unit
        prices are resolved against that lot's own template, and the lot's bid amount
        is computed from the template — never trusted from the client."""
        lot1_item = TenderBoqItem.objects.create(
            tender=self.tender, lot=self.lot1, description="Panel A", unit="pcs", quantity=Decimal("5"), position=0,
        )
        lot2_item = TenderBoqItem.objects.create(
            tender=self.tender, lot=self.lot2, description="Panel B", unit="pcs", quantity=Decimal("8"), position=0,
        )
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "financial",
                "status": "Submitted",
                "lot_offers": json.dumps([
                    {
                        "lot": self.lot1.id,
                        "bid_amount": "999999",  # must be ignored - server computes from template
                        "boq_items": [{"template_item_id": lot1_item.id, "unit_price": 1000}],
                    },
                    {
                        "lot": self.lot2.id,
                        "boq_items": [{"template_item_id": lot2_item.id, "unit_price": 500}],
                    },
                ]),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bid = TenderBid.objects.get(id=response.data["id"])
        offers = {o.lot_id: o for o in bid.lot_offers.all()}
        self.assertEqual(str(offers[self.lot1.id].bid_amount), "5000.00")
        self.assertEqual(offers[self.lot1.id].boq_items[0]["description"], "Panel A")
        self.assertEqual(offers[self.lot1.id].boq_items[0]["qty"], "5.00")
        self.assertEqual(str(offers[self.lot2.id].bid_amount), "4000.00")
        self.assertEqual(offers[self.lot2.id].boq_items[0]["description"], "Panel B")

    def test_lot_offer_with_boq_template_rejects_missing_unit_price(self):
        lot1_item = TenderBoqItem.objects.create(
            tender=self.tender, lot=self.lot1, description="Panel A", unit="pcs", quantity=Decimal("5"), position=0,
        )
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "financial",
                "status": "Submitted",
                "lot_offers": json.dumps([
                    {"lot": self.lot1.id, "boq_items": []},
                ]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lot_offers", response.data)
        self.assertIn("Panel A", str(response.data["lot_offers"]))

    def test_award_ranking_is_grouped_per_lot_with_independent_winners(self):
        # Vendor A has the better weighted (technical + financial) score on Lot 1,
        # Vendor B has the better weighted score on Lot 2.
        bid_a = self._submitted_financial_bid(self.vendor_a, {self.lot1: 100000, self.lot2: 200000})
        bid_b = self._submitted_financial_bid(self.vendor_b, {self.lot1: 150000, self.lot2: 120000})
        self._score_technical(bid_a, score=80)
        self._score_technical(bid_b, score=75)
        self._score_financial_for_lot(bid_a, self.lot1, 100)
        self._score_financial_for_lot(bid_b, self.lot1, 67)
        self._score_financial_for_lot(bid_b, self.lot2, 100)
        self._score_financial_for_lot(bid_a, self.lot2, 60)

        self.client.force_authenticate(self.admin_user)
        response = self.client.get(f"/api/tenders/{self.tender.id}/award_ranking/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["is_lot_wise"])
        lots_by_name = {lot["lot_name"]: lot for lot in response.data["lots"]}
        self.assertEqual(lots_by_name["Lot 1: Maseru"]["recommended"]["vendor_id"], str(self.vendor_a.id))
        self.assertEqual(lots_by_name["Lot 2: Leribe"]["recommended"]["vendor_id"], str(self.vendor_b.id))

    def test_award_lot_and_confirm_award_creates_separate_contracts_per_vendor(self):
        bid_a = self._submitted_financial_bid(self.vendor_a, {self.lot1: 100000, self.lot2: 200000})
        bid_b = self._submitted_financial_bid(self.vendor_b, {self.lot1: 150000, self.lot2: 120000})
        self._score_technical(bid_a, score=80)
        self._score_technical(bid_b, score=75)
        self._score_financial_for_lot(bid_a, self.lot1, 100)
        self._score_financial_for_lot(bid_b, self.lot1, 67)
        self._score_financial_for_lot(bid_b, self.lot2, 100)
        self._score_financial_for_lot(bid_a, self.lot2, 60)

        self.client.force_authenticate(self.admin_user)
        award1 = self.client.post(
            f"/api/tenders/{self.tender.id}/award_lot/",
            {"lot_id": str(self.lot1.id), "bid_id": str(bid_a.id)},
            format="json",
        )
        self.assertEqual(award1.status_code, status.HTTP_200_OK, award1.data)
        award2 = self.client.post(
            f"/api/tenders/{self.tender.id}/award_lot/",
            {"lot_id": str(self.lot2.id), "bid_id": str(bid_b.id)},
            format="json",
        )
        self.assertEqual(award2.status_code, status.HTTP_200_OK, award2.data)

        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)
        self.lot1.refresh_from_db()
        self.lot2.refresh_from_db()
        self.assertEqual(self.lot1.awarded_vendor_id, str(self.vendor_a.id))
        self.assertEqual(self.lot2.awarded_vendor_id, str(self.vendor_b.id))

        # Cooling-off is 0 days by default in this setup's tender -> confirm immediately.
        self.tender.cooling_off_until = timezone.now() - timedelta(minutes=1)
        self.tender.save(update_fields=["cooling_off_until"])

        confirm = self.client.post(f"/api/tenders/{self.tender.id}/confirm_award/", {}, format="json")
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, confirm.data)
        self.assertEqual(len(confirm.data["generated_contracts"]), 2)
        contract_vendor_ids = {c["vendor_id"] for c in confirm.data["generated_contracts"]}
        self.assertEqual(contract_vendor_ids, {str(self.vendor_a.id), str(self.vendor_b.id)})

        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.AWARDED)
        contracts = TenderContract.objects.filter(tender=self.tender)
        self.assertEqual(contracts.count(), 2)
        self.assertEqual({c.lot_id for c in contracts}, {self.lot1.id, self.lot2.id})

    def test_award_action_rejects_lot_wise_tender(self):
        bid_a = self._submitted_financial_bid(self.vendor_a, {self.lot1: 100000})
        self._score_technical(bid_a, score=80)
        self.client.force_authenticate(self.admin_user)
        response = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {"bid_id": str(bid_a.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("award_lot", response.data["detail"])

    def test_contract_award_value_uses_the_awarded_lots_own_bid_amount(self):
        """A lot-wise contract's award value must be that specific lot's winning bid
        amount, not the tender's overall budget — the bug this test guards against
        would otherwise silently report the whole-tender budget on the PBA/contract."""
        self.tender.budget = 999999
        self.tender.save(update_fields=["budget"])

        bid_a = self._submitted_financial_bid(self.vendor_a, {self.lot1: 100000, self.lot2: 200000})
        self._score_technical(bid_a, score=80)
        self._score_financial_for_lot(bid_a, self.lot1, 100)

        self.client.force_authenticate(self.admin_user)
        award = self.client.post(
            f"/api/tenders/{self.tender.id}/award_lot/",
            {"lot_id": str(self.lot1.id), "bid_id": str(bid_a.id)},
            format="json",
        )
        self.assertEqual(award.status_code, status.HTTP_200_OK, award.data)

        self.tender.cooling_off_until = timezone.now() - timedelta(minutes=1)
        self.tender.save(update_fields=["cooling_off_until"])
        confirm = self.client.post(f"/api/tenders/{self.tender.id}/confirm_award/", {}, format="json")
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, confirm.data)

        contract = TenderContract.objects.get(tender=self.tender, lot=self.lot1)
        self.assertEqual(contract.resolved_award_value(), Decimal("100000"))

    def test_eoi_submission_requires_declared_lots_for_lot_wise_tender(self):
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "eoi",
                "status": "Submitted",
                "eoi_narrative": "A" * 200,
                "female_target_pct": "55",
                "vulnerable_target_pct": "35",
                "low_income_target_pct": "60",
                "inclusion_commitment_confirmed": "true",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("declared_lots", response.data)

    def test_eoi_submission_enforces_max_lots_per_bidder_on_declared_lots(self):
        lot3 = TenderLot.objects.create(tender=self.tender, name="Lot 3: Berea", position=2)
        self.client.force_authenticate(self.vendor_a)
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.tender.id),
                "bid_stage": "eoi",
                "status": "Submitted",
                "eoi_narrative": "A" * 200,
                "female_target_pct": "55",
                "vulnerable_target_pct": "35",
                "low_income_target_pct": "60",
                "inclusion_commitment_confirmed": "true",
                "declared_lots": json.dumps([self.lot1.id, self.lot2.id, lot3.id]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("declared_lots", response.data)

    def _draft_bid_at_stage(self, vendor, stage, declared_lots):
        return TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.full_name,
            bid_stage=stage,
            status=BidStatus.DRAFT,
            declared_lots=[str(lot.id) for lot in declared_lots],
            technical_stage_unlocked=True,
            financial_stage_unlocked=True,
        )

    def test_technical_stage_site_rejects_lot_outside_declared_lots(self):
        lot3 = TenderLot.objects.create(tender=self.tender, name="Lot 3: Berea", position=2)
        bid = self._draft_bid_at_stage(self.vendor_a, "technical", [self.lot1])
        self.client.force_authenticate(self.vendor_a)
        response = self.client.patch(
            f"/api/tender-bids/{bid.id}/",
            {
                "status": "Submitted",
                "om_strategy_summary": "Quarterly maintenance visits.",
                "boq_items": json.dumps([{"description": "Panel", "qty": 1, "unit": "pcs", "unit_price": 100}]),
                "sites": json.dumps([{
                    "site_name": "Site 1",
                    "district": "Maseru",
                    "target_beneficiary_type": "standard",
                    "number_of_households": 5,
                    "latitude": "-29.3",
                    "longitude": "27.7",
                    "lot": lot3.id,
                }]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("sites", response.data)

    def test_technical_stage_site_accepts_declared_lot(self):
        bid = self._draft_bid_at_stage(self.vendor_a, "technical", [self.lot1])
        self.client.force_authenticate(self.vendor_a)
        response = self.client.patch(
            f"/api/tender-bids/{bid.id}/",
            {
                "status": "Submitted",
                "om_strategy_summary": "Quarterly maintenance visits.",
                "boq_items": json.dumps([{"description": "Panel", "qty": 1, "unit": "pcs", "unit_price": 100}]),
                "sites": json.dumps([{
                    "site_name": "Site 1",
                    "district": "Maseru",
                    "target_beneficiary_type": "standard",
                    "number_of_households": 5,
                    "latitude": "-29.3",
                    "longitude": "27.7",
                    "lot": self.lot1.id,
                }]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_financial_stage_rejects_lot_outside_declared_lots(self):
        bid = self._draft_bid_at_stage(self.vendor_a, "financial", [self.lot1])
        self.client.force_authenticate(self.vendor_a)
        response = self.client.patch(
            f"/api/tender-bids/{bid.id}/",
            {
                "status": "Submitted",
                "lot_offers": json.dumps([
                    {"lot": self.lot1.id, "bid_amount": "100000"},
                    {"lot": self.lot2.id, "bid_amount": "120000"},
                ]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("lot_offers", response.data)


class EvaluationCommitteeOversightTests(APITestCase):
    """RBF Official / Super Admin oversight of each Evaluation Committee member's marks,
    plus the RBF Official's post-evaluation comment (only writable once the whole
    committee evaluation is complete)."""

    def setUp(self):
        self.rmt_user = User.objects.create_user(
            username="rmt_oversight",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="RBF Oversight Official",
        )
        self.admin_user = User.objects.create_user(
            username="admin_oversight",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Admin Oversight",
        )
        self.ec_members = [
            User.objects.create_user(
                username=f"ec_oversight_{i}",
                password="securePass123",
                role=UserRole.EVALUATION_COMMITTEE,
                status="Active",
                full_name=f"EC Member {i}",
            )
            for i in range(3)
        ]
        self.vendor = User.objects.create_user(
            username="vendor_oversight",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Oversight Vendor",
            organization_name="Oversight Vendor Ltd",
        )
        self.tender = Tender.objects.create(
            reference_number="REF-OVERSIGHT-001",
            name="Oversight Tender",
            department="DoE",
            category="Mini-Grid",
            status=TenderStatus.EVALUATION,
            deadline=timezone.now(),
            technical_weight=70,
            financial_weight=30,
            technical_threshold=70,
            cooling_off_days=7,
            bidding_currency="LSL",
            technology_types=["Mini-Grid"],
            target_districts=["Maseru"],
            procurement_method="Open Tendering",
        )
        for member in self.ec_members:
            TenderEvaluationCommitteeMember.objects.create(tender=self.tender, member=member, coi_attested=True, coi_attested_at=timezone.now())
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            bid_stage=BidStage.TECHNICAL,
            status=BidStatus.SUBMITTED,
        )

    def _score_technical(self, members):
        for member in members:
            TenderBidEvaluation.objects.create(
                bid=self.bid,
                evaluator=member,
                stage=EvaluationStage.TECHNICAL,
                status=EvaluationStatus.SCORED,
                technical_score=18,
                feasibility_score=14,
                kpi_score=9,
                gender_score=8,
                environmental_score=4,
                om_score=9,
                inclusivity_score=0,
                total_score=62,
            )

    def _finalize_financial(self, members):
        for member in members:
            TenderBidEvaluation.objects.create(
                bid=self.bid,
                evaluator=member,
                stage=EvaluationStage.FINANCIAL,
                status=EvaluationStatus.SCORED,
                financial_score=100,
                financial_score_auto_calculated=True,
                total_score=100,
            )

    def test_evaluation_scores_visible_to_rmt_official(self):
        self._score_technical([self.ec_members[0], self.ec_members[1]])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tenders/{self.tender.id}/evaluation_scores/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["committee_members"]), 3)
        self.assertEqual(response.data["quorum"], 2)
        self.assertEqual(len(response.data["bids"]), 1)
        bid_row = response.data["bids"][0]
        self.assertEqual(bid_row["vendor_name"], self.vendor.full_name)
        self.assertTrue(bid_row["technical_quorum_met"])
        self.assertEqual(len(bid_row["evaluations"]), 2)
        self.assertIn("evaluator_name", bid_row["evaluations"][0])
        self.assertEqual(bid_row["evaluations"][0]["technical_score"], 18)

    def test_evaluation_scores_blocked_for_committee_and_vendor(self):
        self.client.force_authenticate(self.ec_members[0])
        self.assertEqual(
            self.client.get(f"/api/tenders/{self.tender.id}/evaluation_scores/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.vendor)
        self.assertEqual(
            self.client.get(f"/api/tenders/{self.tender.id}/evaluation_scores/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_evaluation_scores_lot_wise_grouping(self):
        """On a lot-wise tender the scoreboard must expose the lot list, name every
        financial row with its lot, and report per-lot financial finalization so the
        management view can present marks grouped by lot."""
        lot = TenderLot.objects.create(tender=self.tender, name="Lot A - South")
        lot_bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=f"{self.vendor.id}-lot",
            vendor_name=f"{self.vendor.full_name} (Lot A)",
            vendor_email=self.vendor.email,
            bid_amount=100000,
            bid_stage=BidStage.TECHNICAL,
            status=BidStatus.SUBMITTED,
        )
        TenderBidLotOffer.objects.create(bid=lot_bid, lot=lot, bid_amount=100000, subsidy_requested=60000)
        for member in self.ec_members[:2]:
            TenderBidEvaluation.objects.create(
                bid=lot_bid,
                evaluator=member,
                stage=EvaluationStage.TECHNICAL,
                status=EvaluationStatus.SCORED,
                technical_score=18,
                feasibility_score=14,
                kpi_score=9,
                gender_score=8,
                environmental_score=4,
                om_score=9,
                inclusivity_score=0,
                total_score=62,
            )
            TenderBidEvaluation.objects.create(
                bid=lot_bid,
                evaluator=member,
                stage=EvaluationStage.FINANCIAL,
                lot=lot,
                status=EvaluationStatus.SCORED,
                financial_score=100,
                financial_score_auto_calculated=True,
                total_score=100,
            )

        self.client.force_authenticate(self.rmt_user)
        response = self.client.get(f"/api/tenders/{self.tender.id}/evaluation_scores/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_lot_wise"])
        self.assertEqual(response.data["lots"], [{"lot_id": str(lot.id), "lot_name": "Lot A - South"}])
        bid_row = next(b for b in response.data["bids"] if b["bid_id"] == str(lot_bid.id))
        self.assertTrue(bid_row["lot_financial_finalized"][str(lot.id)])
        financial_rows = [e for e in bid_row["evaluations"] if e["stage"] == "financial"]
        self.assertEqual(len(financial_rows), 2)
        self.assertEqual(financial_rows[0]["lot_name"], "Lot A - South")
        self.assertEqual(financial_rows[0]["lot"], str(lot.id))

    def test_rmt_comment_blocked_until_evaluation_complete(self):
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tenders/{self.tender.id}/evaluation_comment/",
            {"comment": "Good work."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["evaluation_complete"])
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.evaluation_comment, "")

    def test_rmt_comment_saved_once_evaluation_complete(self):
        self._score_technical([self.ec_members[0], self.ec_members[1]])
        self._finalize_financial([self.ec_members[0], self.ec_members[1]])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            f"/api/tenders/{self.tender.id}/evaluation_comment/",
            {"comment": "The committee finished scoring. Proceed to award."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["evaluation_complete"])
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.evaluation_comment, "The committee finished scoring. Proceed to award.")
        self.assertEqual(self.tender.evaluation_comment_author, self.rmt_user.full_name)
        self.assertIsNotNone(self.tender.evaluation_comment_updated_at)

        get_response = self.client.get(f"/api/tenders/{self.tender.id}/evaluation_comment/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertTrue(get_response.data["evaluation_complete"])
        self.assertEqual(get_response.data["comment"], "The committee finished scoring. Proceed to award.")

    def test_comment_rides_along_in_tender_payload(self):
        self.tender.evaluation_comment = "Approved by RMT."
        self.tender.evaluation_comment_author = self.rmt_user.full_name
        self.tender.save(update_fields=["evaluation_comment", "evaluation_comment_author"])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.get(f"/api/tenders/{self.tender.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["evaluation_comment"], "Approved by RMT.")
        self.assertEqual(response.data["evaluation_comment_author"], self.rmt_user.full_name)

    def test_comment_not_writable_through_generic_tender_endpoint(self):
        self._score_technical([self.ec_members[0], self.ec_members[1]])
        self._finalize_financial([self.ec_members[0], self.ec_members[1]])
        self.client.force_authenticate(self.rmt_user)

        response = self.client.patch(
            f"/api/tenders/{self.tender.id}/",
            {"evaluation_comment": "hacked through generic endpoint"},
            format="json",
        )

        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST))
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.evaluation_comment, "")


class EvaluationIntegrityAndLockingTests(APITestCase):
    """Phase 1 production-grade integrity controls for Evaluation Committee scoring:
    conflict-of-interest attestation & declarations, unique (bid, evaluator, stage)
    rows, submit-to-finalize locking, audit revisions, and per-criterion justification
    requirements."""

    COMPLETE_JUSTIFICATIONS = {
        "technical_score": "Design is technically sound.",
        "feasibility_score": "Technology tier appropriate.",
        "kpi_score": "Implementation plan credible.",
        "gender_score": "Inclusion approach strong.",
        "environmental_score": "Local capacity shown.",
        "om_score": "O&M strategy feasible.",
    }

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="integrity_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Integrity Admin",
        )
        self.ec_members = [
            User.objects.create_user(
                username=f"integrity_ec_{i}",
                password="securePass123",
                role=UserRole.EVALUATION_COMMITTEE,
                status="Active",
                full_name=f"Integrity EC {i}",
            )
            for i in range(3)
        ]
        self.vendor = User.objects.create_user(
            username="integrity_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Integrity Vendor",
            organization_name="Integrity Vendor Ltd",
        )
        self.tender = Tender.objects.create(
            reference_number="REF-INTEGRITY-001",
            name="Integrity Tender",
            department="DoE",
            category="Mini-Grid",
            status=TenderStatus.EVALUATION,
            deadline=timezone.now() + timedelta(days=1),
            technical_weight=70,
            financial_weight=30,
            technical_threshold=70,
            cooling_off_days=7,
            bidding_currency="LSL",
            technology_types=["Mini-Grid"],
            target_districts=["Maseru"],
            procurement_method="Open Tendering",
        )
        self.bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=150000,
            subsidy_requested=100000,
            bid_stage=BidStage.TECHNICAL,
            status=BidStatus.SUBMITTED,
        )

    def _assign(self, member, attested=True):
        return TenderEvaluationCommitteeMember.objects.create(
            tender=self.tender,
            member=member,
            coi_attested=attested,
            coi_attested_at=timezone.now() if attested else None,
        )

    def _technical_payload(self, score=18):
        return {
            "bid": str(self.bid.id),
            "stage": "technical",
            "technical_score": score,
            "feasibility_score": 14,
            "kpi_score": 9,
            "gender_score": 8,
            "environmental_score": 4,
            "om_score": 9,
            "inclusivity_score": 0,
            "comments": "Draft scores for integrity testing.",
        }

    def test_unattested_member_cannot_score(self):
        member = self.ec_members[0]
        self._assign(member, attested=False)
        self.client.force_authenticate(member)

        response = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("conflict of interest", str(response.data["detail"]).lower())

    def test_attestation_unlocks_scoring_and_is_recalled_by_status_endpoint(self):
        member = self.ec_members[0]
        self._assign(member, attested=False)
        self.client.force_authenticate(member)

        attest = self.client.post(f"/api/tenders/{self.tender.id}/attest_coi/", {}, format="json")
        self.assertEqual(attest.status_code, status.HTTP_200_OK)

        coi_status = self.client.get(f"/api/tenders/{self.tender.id}/coi_status/")
        self.assertEqual(coi_status.status_code, status.HTTP_200_OK)
        self.assertTrue(coi_status.data["committee"][0]["coi_attested"])

        response = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_submit_requires_justification_for_every_criterion(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        evaluation_id = created.data["id"]

        rejected = self.client.post(f"/api/tender-bid-evaluations/{evaluation_id}/submit/", {}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("justifications", json.dumps(rejected.data))
        self.assertIn("Missing", json.dumps(rejected.data))

        submitted = self.client.post(
            f"/api/tender-bid-evaluations/{evaluation_id}/submit/",
            {"justifications": self.COMPLETE_JUSTIFICATIONS},
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["submission_status"], EvaluationSubmissionStatus.SUBMITTED)
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["submission_status"], EvaluationSubmissionStatus.SUBMITTED)
        self.assertIsNotNone(submitted.data["submitted_at"])
        self.assertEqual(submitted.data["justifications"]["technical_score"], self.COMPLETE_JUSTIFICATIONS["technical_score"])

    def test_submitted_evaluation_is_locked_and_submit_is_idempotent(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        evaluation_id = created.data["id"]
        first_submit = self.client.post(
            f"/api/tender-bid-evaluations/{evaluation_id}/submit/",
            {"justifications": self.COMPLETE_JUSTIFICATIONS},
            format="json",
        )
        self.assertEqual(first_submit.status_code, status.HTTP_200_OK)

        # Editing the submitted row is forbidden for the member...
        patch = self.client.patch(
            f"/api/tender-bid-evaluations/{evaluation_id}/",
            {"technical_score": 20},
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        # ...as is re-creating it through the create endpoint.
        again = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(score=20), format="json")
        self.assertEqual(again.status_code, status.HTTP_403_FORBIDDEN)
        # Submitting an already-submitted row is a no-op success.
        second_submit = self.client.post(f"/api/tender-bid-evaluations/{evaluation_id}/submit/", {}, format="json")
        self.assertEqual(second_submit.status_code, status.HTTP_200_OK)

    def test_admin_can_unlock_and_reopen_leaves_revision_history(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        evaluation_id = created.data["id"]
        self.client.post(
            f"/api/tender-bid-evaluations/{evaluation_id}/submit/",
            {"justifications": self.COMPLETE_JUSTIFICATIONS},
            format="json",
        )

        self.client.force_authenticate(self.admin_user)
        unlocked = self.client.post(f"/api/tender-bid-evaluations/{evaluation_id}/unlock/", {}, format="json")
        self.assertEqual(unlocked.status_code, status.HTTP_200_OK)
        self.assertEqual(unlocked.data["submission_status"], EvaluationSubmissionStatus.DRAFT)

        evaluation = TenderBidEvaluation.objects.get(id=evaluation_id)
        revision_actions = list(evaluation.revisions.values_list("action", flat=True))
        self.assertIn(EvaluationRevisionAction.REOPENED, revision_actions)
        # A submitted -> reopened pair must appear in the revision trail.
        self.assertIn(EvaluationRevisionAction.SUBMITTED, revision_actions)

    def test_draft_edits_accumulate_before_after_revisions(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(score=18), format="json")
        evaluation_id = created.data["id"]

        self.client.patch(
            f"/api/tender-bid-evaluations/{evaluation_id}/",
            {"technical_score": 20},
            format="json",
        )

        evaluation = TenderBidEvaluation.objects.get(id=evaluation_id)
        revisions = list(evaluation.revisions.order_by("created_at"))
        self.assertEqual(len(revisions), 2)  # create + the score edit
        edit_rev = [
            rev for rev in revisions
            if rev.action == EvaluationRevisionAction.DRAFT_SAVED
            and rev.before and rev.after
            and rev.before.get("technical_score") != rev.after.get("technical_score")
        ][0]
        self.assertEqual(edit_rev.before.get("technical_score"), 18)
        self.assertEqual(edit_rev.after.get("technical_score"), 20)

    def test_duplicate_save_returns_the_same_row(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        first = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        second = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(TenderBidEvaluation.objects.count(), 1)
        self.assertEqual(TenderBidEvaluationRevision.objects.filter(evaluation_id=first.data["id"]).count(), 1)

    def test_declared_conflict_blocks_scoring_until_resolved(self):
        member = self.ec_members[0]
        self._assign(member)
        self.client.force_authenticate(member)

        declared = self.client.post(
            f"/api/tenders/{self.tender.id}/declare_coi/",
            {"vendor_id": str(self.vendor.id), "relationship": "business", "details": "Previous employer."},
            format="json",
        )
        self.assertEqual(declared.status_code, status.HTTP_201_CREATED)
        coi_id = declared.data["id"]

        blocked = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("conflict", str(blocked.data["detail"]).lower())

        self.client.force_authenticate(self.admin_user)
        resolved = self.client.post(
            f"/api/tenders/{self.tender.id}/resolve_coi/",
            {"coi_id": coi_id, "resolution_notes": "Reviewed, no material conflict."},
            format="json",
        )
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(member)
        allowed = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)

    def test_financial_evaluation_submits_without_justifications(self):
        for member in self.ec_members[:2]:
            self._assign(member)
            self.client.force_authenticate(member)
            created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
            self.client.post(
                f"/api/tender-bid-evaluations/{created.data['id']}/submit/",
                {"justifications": self.COMPLETE_JUSTIFICATIONS},
                format="json",
            )

        member = self.ec_members[0]
        self.client.force_authenticate(member)
        financial = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(self.bid.id), "stage": "financial", "comments": "Verified."},
            format="json",
        )
        self.assertEqual(financial.status_code, status.HTTP_201_CREATED)
        submitted = self.client.post(
            f"/api/tender-bid-evaluations/{financial.data['id']}/submit/", {"comments": "Verified."}, format="json"
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertEqual(submitted.data["submission_status"], EvaluationSubmissionStatus.SUBMITTED)
        self.assertTrue(submitted.data["financial_score_auto_calculated"])

    def test_financial_finalize_locks_row_until_admin_unlock(self):
        for member in self.ec_members[:2]:
            self._assign(member)
            self.client.force_authenticate(member)
            created = self.client.post("/api/tender-bid-evaluations/", self._technical_payload(), format="json")
            self.client.post(
                f"/api/tender-bid-evaluations/{created.data['id']}/submit/",
                {"justifications": self.COMPLETE_JUSTIFICATIONS},
                format="json",
            )

        member = self.ec_members[0]
        self.client.force_authenticate(member)
        finalize = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(self.bid.id), "stage": "financial", "submission_status": "submitted", "comments": "Verified."},
            format="json",
        )
        self.assertEqual(finalize.status_code, status.HTTP_201_CREATED)
        self.assertEqual(finalize.data["submission_status"], EvaluationSubmissionStatus.SUBMITTED)

        again = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(self.bid.id), "stage": "financial", "submission_status": "submitted"},
            format="json",
        )
        self.assertEqual(again.status_code, status.HTTP_403_FORBIDDEN)

        screen = self.client.get(f"/api/tenders/{self.tender.id}/financial_evaluation/")
        self.assertEqual(screen.status_code, status.HTTP_200_OK)
        row = next(r for r in screen.data["rows"] if r["bid_id"] == str(self.bid.id))
        self.assertEqual(row["submission_status"], EvaluationSubmissionStatus.SUBMITTED)
        self.assertTrue(row["finalized"])
        self.assertTrue(row["finalized_by_me"])
        self.assertIsNotNone(row["submitted_at"])

        self.client.force_authenticate(self.admin_user)
        unlocked = self.client.post(f"/api/tender-bid-evaluations/{finalize.data['id']}/unlock/", {}, format="json")
        self.assertEqual(unlocked.status_code, status.HTTP_200_OK)
        self.assertEqual(unlocked.data["submission_status"], EvaluationSubmissionStatus.DRAFT)

        self.client.force_authenticate(member)
        screen = self.client.get(f"/api/tenders/{self.tender.id}/financial_evaluation/")
        self.assertEqual(screen.status_code, status.HTTP_200_OK)
        row = next(r for r in screen.data["rows"] if r["bid_id"] == str(self.bid.id))
        self.assertEqual(row["submission_status"], EvaluationSubmissionStatus.DRAFT)
        self.assertIsNone(row["submitted_at"])


class CommitteeAwardGatingTests(APITestCase):
    """Corrected committee flow: the RMT's batch 'Open Financial stage' action is gated
    on technical quorum; the financial evaluation screen lists sequential financial bids
    (never the technical record); intent-to-award (whole-tender and per-lot) is blocked
    until committee evaluation is complete; and award ranking reads financial content
    from the vendor's distinct financial bid."""

    def setUp(self):
        self.rmt_user = User.objects.create_user(
            username="gate_rmt",
            password="securePass123",
            role=UserRole.RBF_OFFICIAL,
            status="Active",
            full_name="RBF Gate Official",
            email="gate-rmt@example.com",
        )
        self.admin_user = User.objects.create_user(
            username="gate_admin",
            password="securePass123",
            role=UserRole.ADMIN,
            status="Active",
            full_name="Gate Admin",
            email="gate-admin@example.com",
        )
        self.ec_members = [
            User.objects.create_user(
                username=f"gate_ec_{i}",
                password="securePass123",
                role=UserRole.EVALUATION_COMMITTEE,
                status="Active",
                full_name=f"Gate EC {i}",
            )
            for i in range(3)
        ]
        self.vendor = User.objects.create_user(
            username="gate_vendor",
            password="securePass123",
            role=UserRole.VENDOR,
            status="Active",
            full_name="Gate Vendor",
            organization_name="Gate Vendor Ltd",
            email="gate-vendor@example.com",
        )
        VendorPrequalification.objects.create(
            vendor=self.vendor,
            company_name="Gate Vendor Ltd",
            status=PrequalificationStatus.APPROVED,
            tech_tier="Level 3",
            female_beneficiary_target=55,
            vulnerable_group_target=35,
        )
        self.tender = Tender.objects.create(
            reference_number="REF-GATE-001",
            name="Gate Tender",
            department="DoE",
            category="Mini-Grid",
            status=TenderStatus.EVALUATION,
            deadline=timezone.now() + timedelta(days=1),
            technical_weight=70,
            financial_weight=30,
            technical_threshold=70,
            cooling_off_days=7,
            bidding_currency="LSL",
            technology_types=["Mini-Grid"],
            target_districts=["Maseru"],
            procurement_method="Open Tendering",
            procurement_workflow="sequential",
        )
        for member in self.ec_members:
            TenderEvaluationCommitteeMember.objects.create(tender=self.tender, member=member, coi_attested=True, coi_attested_at=timezone.now())
        self.tech_bid = TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_stage=BidStage.TECHNICAL,
            status=BidStatus.SUBMITTED,
            version_number=1,
        )

    def _financial_bid(self, amount=180000):
        return TenderBid.objects.create(
            tender=self.tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=amount,
            subsidy_requested=100000,
            bid_stage=BidStage.FINANCIAL,
            status=BidStatus.SUBMITTED,
            version_number=2,
            financial_stage_unlocked=True,
            financial_stage_source_bid=self.tech_bid,
        )

    def _score_technical(self, members):
        for member in members:
            TenderBidEvaluation.objects.create(
                bid=self.tech_bid,
                evaluator=member,
                stage=EvaluationStage.TECHNICAL,
                status=EvaluationStatus.SCORED,
                technical_score=20,
                feasibility_score=15,
                kpi_score=10,
                gender_score=10,
                environmental_score=5,
                om_score=10,
                inclusivity_score=0,
                total_score=70,
            )

    def _finalize_financial(self, financial_bid):
        for member in self.ec_members:
            TenderBidEvaluation.objects.create(
                bid=financial_bid,
                evaluator=member,
                stage=EvaluationStage.FINANCIAL,
                status=EvaluationStatus.SCORED,
                financial_score=100,
                financial_score_auto_calculated=True,
                total_score=100,
            )

    def test_open_financial_stage_blocked_until_technical_quorum(self):
        self._score_technical([self.ec_members[0]])
        self.client.force_authenticate(self.rmt_user)
        blocked = self.client.post(f"/api/tenders/{self.tender.id}/open_financial_stage/", {}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(self.vendor.full_name, blocked.data["pending"])
        self.assertFalse(
            TenderBid.objects.filter(
                tender=self.tender, vendor_id=str(self.vendor.id), bid_stage=BidStage.FINANCIAL, status=BidStatus.DRAFT
            ).exists()
        )

        self._score_technical([self.ec_members[1]])
        opened = self.client.post(f"/api/tenders/{self.tender.id}/open_financial_stage/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)
        self.assertEqual(opened.data["opened_bids"], [str(self.tech_bid.id)])
        draft = TenderBid.objects.filter(
            tender=self.tender, vendor_id=str(self.vendor.id), bid_stage=BidStage.FINANCIAL, status=BidStatus.DRAFT
        ).first()
        self.assertIsNotNone(draft)
        self.assertTrue(draft.financial_stage_unlocked)

    def test_sequential_financial_evaluation_lists_financial_bid(self):
        financial_bid = self._financial_bid()
        self._score_technical(self.ec_members)
        self.client.force_authenticate(self.ec_members[0])

        response = self.client.get(f"/api/tenders/{self.tender.id}/financial_evaluation/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid_ids = [row["bid_id"] for row in response.data["rows"]]
        self.assertEqual(bid_ids, [str(financial_bid.id)])
        self.assertNotIn(str(self.tech_bid.id), bid_ids)
        row = response.data["rows"][0]
        self.assertEqual(row["vendor_id"], str(self.vendor.id))
        self.assertEqual(row["bid_amount"], 180000.0)

    def test_award_blocked_until_financial_finalized_then_succeeds(self):
        financial_bid = self._financial_bid()
        self._score_technical(self.ec_members)
        self.client.force_authenticate(self.rmt_user)

        ranking = self.client.get(f"/api/tenders/{self.tender.id}/award_ranking/")
        self.assertEqual(ranking.status_code, status.HTTP_200_OK)
        self.assertEqual(ranking.data["evaluation_status"]["complete"], False)
        self.assertEqual(ranking.data["evaluation_status"]["committee_size"], 2)
        self.assertEqual(ranking.data["rows"][0]["bid_id"], str(self.tech_bid.id))
        self.assertIn("Awaiting more committee financial scores", ranking.data["rows"][0]["disqualification_reason"])

        blocked = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {
                "bid_id": str(self.tech_bid.id),
                "awarded_vendor_id": str(self.vendor.id),
                "awarded_vendor_name": self.vendor.full_name,
            },
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("reasons", blocked.data)

        self._finalize_financial(financial_bid)
        complete_ranking = self.client.get(f"/api/tenders/{self.tender.id}/award_ranking/")
        self.assertEqual(complete_ranking.data["evaluation_status"]["complete"], True)
        self.assertEqual(complete_ranking.data["recommended"]["bid_id"], str(self.tech_bid.id))

        awarded = self.client.post(
            f"/api/tenders/{self.tender.id}/award/",
            {
                "bid_id": str(self.tech_bid.id),
                "awarded_vendor_id": str(self.vendor.id),
                "awarded_vendor_name": self.vendor.full_name,
            },
            format="json",
        )
        self.assertEqual(awarded.status_code, status.HTTP_200_OK, awarded.data)
        self.tender.refresh_from_db()
        self.assertEqual(self.tender.status, TenderStatus.STANDSTILL)
        self.assertEqual(str(self.tender.intent_to_award_bid_id), str(self.tech_bid.id))

    def test_lot_intent_to_award_blocked_until_evaluation_complete(self):
        lot = TenderLot.objects.create(tender=self.tender, name="Lot A - South")
        TenderBidLotOffer.objects.create(bid=self.tech_bid, lot=lot, bid_amount=100000, subsidy_requested=60000)
        self.client.force_authenticate(self.rmt_user)

        ranking = self.client.get(f"/api/tenders/{self.tender.id}/award_ranking/")
        self.assertEqual(ranking.status_code, status.HTTP_200_OK)
        self.assertTrue(ranking.data["is_lot_wise"])
        self.assertFalse(ranking.data["evaluation_status"]["complete"])

        blocked = self.client.post(
            f"/api/tenders/{self.tender.id}/award_lot/",
            {"lot_id": str(lot.id), "bid_id": str(self.tech_bid.id)},
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("reasons", blocked.data)
