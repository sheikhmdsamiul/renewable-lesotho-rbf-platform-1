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
from rbf.users.models import PrequalificationStatus, User, UserRole, VendorPrequalification

from .models import (
    BidStatus,
    ContractSignatureStatus,
    ContractStatus,
    EvaluationStatus,
    Tender,
    TenderBid,
    TenderBidEvaluation,
    TenderBidSite,
    TenderContract,
    TenderStatus,
)
from .pba_pdf import _annex_section_html, _main_agreement_html, _pdfa_merge, generate_contract_pdf
from .serializers import TenderBidSiteSerializer, TenderContractSerializer


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
            "deadline": timezone.now().isoformat(),
            "application_type": None,
            "bidding_currency": None,
            "last_date_security": "",
            "bidders_schedule_purchase": None,
            "tender_security_required": None,
            "is_verified": None,
            "technology_types": None,
        }

        response = self.client.post("/api/tenders/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["application_type"], "")
        self.assertEqual(response.data["bidding_currency"], "")
        self.assertIsNone(response.data["last_date_security"])
        self.assertFalse(response.data["bidders_schedule_purchase"])
        self.assertFalse(response.data["tender_security_required"])
        self.assertFalse(response.data["is_verified"])
        self.assertEqual(response.data["technology_types"], [])

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
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            financial_score=74,
            total_score=62,
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
            status=EvaluationStatus.SCORED,
            technical_score=80,
            financial_score=70,
            feasibility_score=80,
            kpi_score=80,
            gender_score=75,
            environmental_score=80,
            om_score=80,
            inclusivity_score=75,
            total_score=80,
        )
        TenderBidEvaluation.objects.create(
            bid=bid_b,
            evaluator=self.admin_user,
            status=EvaluationStatus.SCORED,
            technical_score=75,
            financial_score=80,
            feasibility_score=75,
            kpi_score=75,
            gender_score=60,
            environmental_score=75,
            om_score=75,
            inclusivity_score=65,
            total_score=75,
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
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=8,
            financial_score=24,
            total_score=85,
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
            last_date_submission=timezone.now() + timedelta(days=7),
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
            last_date_submission=timezone.now() + timedelta(days=7),
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

    def test_prequalification_submission_uses_tender_stage_and_records_audit(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "150000.00",
                **self._submission_basics(),
                "stage": "Site-Specific",
                "concept_note": "Community-focused clean energy rollout for underserved households. " * 12,
                "system_configuration": json.dumps({
                    "technology_type": "SHS",
                    "rated_power_w": 250,
                    "battery_capacity_wh": 1200,
                    "pv_panel_size_w": 300,
                    "inverter_type": "Hybrid",
                }),
                "boq_items": json.dumps([
                    {"item_number": 1, "description": "Solar kit", "qty": 100, "unit": "set", "unit_price": 1200, "total": 120000},
                ]),
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Ha Thetsane Cluster",
                        "district": "Maseru",
                        "village_sub_district": "Ha Thetsane",
                        "latitude": -29.3611,
                        "longitude": 27.5144,
                        "number_of_households": 85,
                        "target_beneficiary_type": "female_headed",
                        "estimated_energy_demand_kwh_month": 450,
                        "road_access_available": True,
                        "notes": "Good road access.",
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        bid = TenderBid.objects.get(id=response.data["id"])
        self.assertEqual(bid.stage, "Stage 1: Concept")
        self.assertEqual(response.data["stage"], "Stage 1: Concept")
        self.assertEqual(response.data["stage_badge"], "Stage 1: Concept")
        self.assertEqual(response.data["technology_type"], "SHS")
        self.assertEqual(bid.system_configuration["rated_power_w"], 250)
        self.assertEqual(len(bid.boq_items), 1)
        self.assertEqual(bid.sites.count(), 1)
        self.assertTrue(
            AuditLog.objects.filter(
                action="bid_submitted",
                record_id=bid.id,
            ).exists()
        )

    def test_site_specific_submission_requires_all_documents_and_summaries(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.site_specific_tender.id),
                "bid_amount": "180000.00",
                **self._submission_basics(),
                "concept_note": "",
                "technical_proposal": "",
                "financial_proposal": "",
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Roma Cluster",
                        "district": "Maseru",
                        "latitude": -29.45,
                        "longitude": 27.71,
                        "number_of_households": 40,
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("technical_proposal_file", response.data)
        self.assertIn("financial_proposal_file", response.data)
        self.assertIn("boq_file", response.data)
        self.assertIn("gender_action_plan_file", response.data)
        self.assertIn("implementation_plan_file", response.data)

    def test_stage_one_submission_requires_inclusion_confirmation_only(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "125000.00",
                **self._submission_basics(),
                "concept_note": "Implementation strategy " * 30,
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "false",
                "sites": json.dumps([
                    {
                        "site_name": "Pilot Village",
                        "district": "Maseru",
                        "number_of_households": 25,
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inclusion_commitment_confirmed", response.data)
        self.assertNotIn("sites", response.data)

    def test_stage_one_submission_requires_minimum_concept_note_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "125000.00",
                **self._submission_basics(),
                "concept_note": "Too short",
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("concept_note", response.data)

    def test_stage_one_submission_rejects_concept_note_under_200_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "125000.00",
                **self._submission_basics(),
                "concept_note": "A" * 199,
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("concept_note", response.data)

    def test_stage_one_submission_accepts_concept_note_at_200_characters(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.prequal_tender.id),
                "bid_amount": "125000.00",
                **self._submission_basics(),
                "concept_note": "A" * 200,
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Pilot Village",
                        "district": "Maseru",
                        "number_of_households": 25,
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_site_specific_submission_rejects_coordinates_outside_lesotho(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.site_specific_tender.id),
                "bid_amount": "125000.00",
                **self._submission_basics(),
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Outside Lesotho",
                        "district": "Maseru",
                        "latitude": -26.2041,
                        "longitude": 28.0473,
                        "number_of_households": 15,
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sites", response.data)

    def test_site_specific_submission_rejects_tier_above_prequalification(self):
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.site_specific_tender.id),
                "bid_amount": "180000.00",
                "subsidy_requested": "100000.00",
                "device_brand_model": "SunPower SPX-200",
                "tech_tier": "Tier 4",
                "energy_target": "450.00",
                "warranty_period": "24",
                "female_target_pct": 55,
                "vulnerable_target_pct": 35,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "sites": json.dumps([
                    {
                        "site_name": "Roma Cluster",
                        "district": "Maseru",
                        "latitude": -29.45,
                        "longitude": 27.71,
                        "number_of_households": 40,
                        "target_technology": "SHS",
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tech_tier", response.data)

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
        TenderBidEvaluation.objects.create(
            bid=bid,
            evaluator=self.vendor.__class__.objects.create_user(
                username="tac_low",
                password="securePass123",
                role=UserRole.TAC,
                status="Active",
                full_name="TAC Low Score",
                email="tac-low@example.com",
            ),
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

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "financial_score": 80, "comments": "Ready for finance review."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("financial_score", response.data)

    def test_rmt_financial_evaluation_is_allowed_after_technical_threshold_pass(self):
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
            username="tac_pass",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Pass Score",
            email="tac-pass@example.com",
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

        self.client.force_authenticate(self.rmt_user)
        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {"bid": str(bid.id), "financial_score": 85, "comments": "Financial review complete."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["financial_score"], 85)

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
            status=EvaluationStatus.SCORED,
            technical_score=10,
            feasibility_score=10,
            kpi_score=5,
            gender_score=5,
            financial_score=30,
            total_score=30,
        )
        TenderBidEvaluation.objects.create(
            bid=competing_bid,
            evaluator=self.rmt_user,
            status=EvaluationStatus.SCORED,
            technical_score=10,
            feasibility_score=10,
            kpi_score=5,
            gender_score=5,
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
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Editable",
            email="tac-editable@example.com",
        )
        self.client.force_authenticate(tac_user)

        first_response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
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
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Pilot Village",
            district="Maseru",
            number_of_households=20,
        )
        tac_user = self.vendor.__class__.objects.create_user(
            username="tac_unlock",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Unlock",
            email="tac-unlock@example.com",
        )
        self.client.force_authenticate(tac_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "technical_score": 80,
                "feasibility_score": 80,
                "kpi_score": 80,
                "gender_score": 80,
                "environmental_score": 80,
                "om_score": 80,
                "inclusivity_score": 80,
                "comments": "Stage 1 passed.",
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        draft = TenderBid.objects.filter(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        ).exclude(id=bid.id).first()
        self.assertIsNotNone(draft)
        self.assertEqual(draft.stage, "Stage 2: Detailed")
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
        tac_user = User.objects.create_user(
            username="tac_stage_two_financial_gate",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Stage Two Gate",
            email="tac-stage-two-gate@example.com",
        )
        TenderBidEvaluation.objects.create(
            bid=stage_one_bid,
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
        stage_two_bid = TenderBid.objects.create(
            tender=self.prequal_tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.full_name,
            vendor_email=self.vendor.email,
            bid_amount=155000,
            subsidy_requested=102000,
            stage="Stage 2: Detailed",
            status=BidStatus.SUBMITTED,
            version_number=2,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=stage_one_bid,
        )
        TenderBidEvaluation.objects.create(
            bid=stage_two_bid,
            evaluator=tac_user,
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
        self.client.force_authenticate(self.rmt_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(stage_two_bid.id),
                "technical_score": 10,
                "feasibility_score": 10,
                "kpi_score": 5,
                "gender_score": 5,
                "comments": "Financial evaluation completed for Stage 2.",
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        saved = TenderBidEvaluation.objects.get(bid=stage_two_bid, evaluator=self.rmt_user)
        self.assertEqual(saved.financial_score, 30)

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

    @patch("rbf.tenders.views.send_mail")
    def test_stage_one_pass_notifies_vendor_in_app_and_email(self, mock_send_mail):
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
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Pilot Village",
            district="Maseru",
            number_of_households=20,
        )
        tac_user = User.objects.create_user(
            username="tac_notify_pass",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Notify Pass",
            email="tac-notify-pass@example.com",
        )
        self.client.force_authenticate(tac_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "technical_score": 80,
                "feasibility_score": 80,
                "kpi_score": 80,
                "gender_score": 80,
                "environmental_score": 80,
                "om_score": 80,
                "inclusivity_score": 80,
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        self.assertTrue(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                event="stage_one_passed",
                linked_entity_id=str(bid.id),
            ).exists()
        )
        bid.refresh_from_db()
        self.assertEqual(bid.status, BidStatus.ACCEPTED)
        self.assertIsNotNone(bid.reviewed_at)
        mock_send_mail.assert_called()

    @patch("rbf.tenders.views.send_mail")
    def test_stage_one_fail_notifies_vendor_in_app_and_email(self, mock_send_mail):
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
        TenderBidSite.objects.create(
            bid=bid,
            site_name="Pilot Village",
            district="Maseru",
            number_of_households=20,
        )
        tac_user = User.objects.create_user(
            username="tac_notify_fail",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Notify Fail",
            email="tac-notify-fail@example.com",
        )
        self.client.force_authenticate(tac_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "technical_score": 40,
                "feasibility_score": 40,
                "kpi_score": 40,
                "gender_score": 40,
                "environmental_score": 40,
                "om_score": 40,
                "inclusivity_score": 40,
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        self.assertTrue(
            Notification.objects.filter(
                recipient_id=str(self.vendor.id),
                event="stage_one_failed",
                linked_entity_id=str(bid.id),
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
        mock_send_mail.assert_called()

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
            status=BidStatus.SUBMITTED,
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
            status=BidStatus.SUBMITTED,
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
        tac_user = User.objects.create_user(
            username="tac_doc_clone",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Doc Clone",
            email="tac-doc-clone@example.com",
        )
        self.client.force_authenticate(tac_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "technical_score": 80,
                "feasibility_score": 80,
                "kpi_score": 80,
                "gender_score": 80,
                "environmental_score": 80,
                "om_score": 80,
                "inclusivity_score": 80,
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
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
            stage="Stage 2: Detailed",
            status=BidStatus.DRAFT,
            version_number=2,
            stage_two_unlocked=True,
            stage_two_unlocked_at=timezone.now(),
            stage_two_source_bid=bid,
        )
        tac_user = self.vendor.__class__.objects.create_user(
            username="tac_existing_stage_two",
            password="securePass123",
            role=UserRole.TAC,
            status="Active",
            full_name="TAC Existing Stage Two",
            email="tac-existing-stage-two@example.com",
        )
        self.client.force_authenticate(tac_user)

        response = self.client.post(
            "/api/tender-bid-evaluations/",
            {
                "bid": str(bid.id),
                "technical_score": 80,
                "feasibility_score": 80,
                "kpi_score": 80,
                "gender_score": 80,
                "environmental_score": 80,
                "om_score": 80,
                "inclusivity_score": 80,
            },
            format="json",
        )

        self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
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
            status=BidStatus.SUBMITTED,
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
        response = self.client.post(
            "/api/tender-bids/",
            {
                "tender": str(self.site_specific_tender.id),
                "bid_amount": "180000.00",
                **self._submission_basics(),
                "concept_note": "",
                "technical_proposal": "",
                "financial_proposal": "",
                "female_target_pct": 50,
                "vulnerable_target_pct": 30,
                "low_income_target_pct": 60,
                "inclusion_commitment_confirmed": "true",
                "om_strategy_summary": "Regular maintenance schedule with local technicians.",
                "sites": json.dumps([
                    {
                        "site_name": "Roma Cluster",
                        "district": "Maseru",
                        "latitude": -29.45,
                        "longitude": 27.71,
                        "number_of_households": 40,
                    }
                ]),
                "status": BidStatus.SUBMITTED,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("technical_proposal_file", response.data)
        self.assertIn("financial_proposal_file", response.data)
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
            status=EvaluationStatus.SCORED,
            technical_score=18,
            feasibility_score=14,
            kpi_score=9,
            gender_score=8,
            environmental_score=4,
            om_score=9,
            financial_score=74,
            total_score=62,
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
