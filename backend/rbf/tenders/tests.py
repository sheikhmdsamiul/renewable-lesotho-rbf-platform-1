from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
import subprocess

from rbf.projects.models import Milestone, Project, ProjectStatus
from rbf.users.models import PrequalificationStatus, User, UserRole, VendorPrequalification

from .models import (
    BidStatus,
    ContractStatus,
    EvaluationStatus,
    Tender,
    TenderBid,
    TenderBidEvaluation,
    TenderContract,
    TenderStatus,
)
from .pba_pdf import _annex_section_html, _main_agreement_html, _pdfa_merge, generate_contract_pdf
from .serializers import TenderContractSerializer


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
        self.assertEqual(award_response.data["status"], TenderStatus.PUBLISHED)

        tender.refresh_from_db()
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
        mock_generate_contract_pdf.assert_called_once()

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
