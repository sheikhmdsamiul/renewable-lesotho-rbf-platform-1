from datetime import timedelta
from pathlib import Path
import shutil
import uuid
from types import SimpleNamespace

from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from unittest.mock import patch

from rbf.notifications.models import Notification
from .models import (
    AuditLog,
    AnomalyFlag,
    InstallationReport,
    InstallationStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectSetup,
    ProjectStatus,
    ProjectUpdate,
    SmartMeterReading,
    VerificationStatus,
    VerificationTask,
)
from .gis import GpsValidator
from .kpi import KpiService
from .integrations import ProspectService, queue_installation_sync, queue_project_targets_sync
from rbf.tenders.models import ContractStatus, Tender, TenderContract


class ProjectApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="project_admin",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        self.test_geojson_root = settings.BASE_DIR / "tmp_test_geojson" / str(uuid.uuid4())
        self.geojson_dir = self.test_geojson_root / "geojson"
        self.geojson_dir.mkdir(parents=True, exist_ok=True)
        self.geojson_path = self.geojson_dir / "lesotho.geojson"
        self.settings_override = override_settings(LESOTHO_BOUNDARY_PATH=str(self.geojson_path.relative_to(settings.BASE_DIR)))
        self.settings_override.enable()
        self.geojson_path.write_text(
            """
            {
              "type": "Feature",
              "properties": {"ISO_A2": "LS"},
              "geometry": {
                "type": "Polygon",
                "coordinates": [[[27.0, -30.5], [29.5, -30.5], [29.5, -28.0], [27.0, -28.0], [27.0, -30.5]]]
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        GpsValidator._feature_cache = None

    def tearDown(self):
        GpsValidator._feature_cache = None
        self.settings_override.disable()
        shutil.rmtree(self.test_geojson_root, ignore_errors=True)
        super().tearDown()

    def _project_payload(self):
        return {
            "vendor_id": "V-001",
            "vendor_name": "SolarLease Ltd",
            "tech_type": "SHS",
            "region": "Maseru",
            "status": ProjectStatus.PRE_QUALIFICATION,
            "progress": 15,
            "energy_output": 42.5,
            "uptime": 98.2,
            "gender_impact": 51.0,
        }

    def _create_completed_setup(self, project, vendor):
        return ProjectSetup.objects.update_or_create(
            project=project,
            defaults={
                "vendor": vendor,
                "team_roster_file": "project_setup/team_rosters/test.pdf",
                "equipment_plan_file": "project_setup/equipment_plans/test.pdf",
                "compliance_docs_file": "project_setup/compliance_docs/test.pdf",
                "insurance_certificate_file": "project_setup/insurance/test.pdf",
                "site_status": "ready",
                "work_schedule_start": timezone.now().date(),
                "work_schedule_end": timezone.now().date() + timedelta(days=10),
                "device_brand": "SolarCo",
                "device_model": "SHS-100",
                "tech_tier": 2,
                "manual_verification_confirmed": True,
                "checklist_team_ready": True,
                "checklist_equipment_ready": True,
                "checklist_site_ready": True,
                "checklist_safety_ready": True,
                "checklist_logistics_ready": True,
                "setup_completed_at": timezone.now(),
            },
        )[0]

    def _write_district_geojson(self):
        self.geojson_path.write_text(
            """
            {
              "type": "FeatureCollection",
              "features": [
                {
                  "type": "Feature",
                  "properties": {"district": "Maseru"},
                  "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[27.0, -30.5], [28.0, -30.5], [28.0, -29.5], [27.0, -29.5], [27.0, -30.5]]]
                  }
                },
                {
                  "type": "Feature",
                  "properties": {"district": "Berea"},
                  "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[28.0, -30.5], [29.0, -30.5], [29.0, -29.5], [28.0, -29.5], [28.0, -30.5]]]
                  }
                }
              ]
            }
            """.strip(),
            encoding="utf-8",
        )
        GpsValidator._feature_cache = None

    def test_projects_list_endpoint(self):
        Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["vendor_id"], "V-001")

    @patch("rbf.projects.views.queue_project_targets_sync")
    def test_project_create_queues_prospect_targets(self, queue_targets):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post("/api/projects/", self._project_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        queue_targets.assert_called_once_with(str(response.data["id"]))

    @patch("rbf.projects.views.queue_project_targets_sync")
    def test_project_prospect_sync_endpoint_queues_target_sync(self, queue_targets):
        project = Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            f"/api/projects/{project.id}/prospect-sync/",
            {"action": "push_target"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        queue_targets.assert_called_once_with(str(project.id))
        self.assertEqual(response.data["queued_methods"], ["pushTarget"])

    @patch("rbf.projects.views.queue_project_targets_sync")
    def test_project_update_queues_prospect_targets_when_target_fields_change(self, queue_targets):
        project = Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"installation_target": 275},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        queue_targets.assert_called_once_with(str(project.id))

    def test_milestones_endpoint_is_reachable_and_creates_record(self):
        project = Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)
        payload = {
            "project": project.id,
            "name": "Installation Complete",
            "description": "Complete installation and commission the deployed units.",
            "percentage": 40,
            "status": "Pending",
            "amount": "12500.00",
            "progress_percentage": 50,
            "target_date": "2026-04-15",
        }

        create_response = self.client.post("/api/projects/milestones/", payload, format="json")
        list_response = self.client.get("/api/projects/milestones/")

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(len(list_response.data["results"]), 1)
        self.assertEqual(list_response.data["results"][0]["project"], project.id)
        self.assertEqual(list_response.data["results"][0]["description"], payload["description"])
        self.assertEqual(list_response.data["results"][0]["progress_percentage"], payload["progress_percentage"])
        self.assertEqual(list_response.data["results"][0]["target_date"], payload["target_date"])
        self.assertTrue(
            ProjectUpdate.objects.filter(
                project=project,
                title="Milestone Added",
            ).exists()
        )

    def test_vendor_setup_draft_creates_project_update_entry(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="setup_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        payload = self._project_payload()
        payload.update({
            "vendor_id": str(vendor.id),
            "vendor_name": vendor.username,
            "status": ProjectStatus.SETUP_PENDING,
        })
        project = Project.objects.create(**payload)
        self.client.force_authenticate(vendor)

        response = self.client.post(
            f"/api/projects/{project.id}/setup/",
            {"site_status": "in_progress"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ProjectUpdate.objects.filter(
                project=project,
                title="Project Setup Draft Saved",
            ).exists()
        )

    def test_vendor_project_list_includes_dashboard_widget_fields(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="widget_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        other_vendor = User.objects.create_user(
            username="other_widget_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        own_project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            technology_type="SHS",
            region="Maseru",
            district="Maseru",
            district_zone="Maseru Urban",
            status=ProjectStatus.SETUP_PENDING,
            installation_target=120,
            project_duration_months=12,
        )
        own_project.milestones.create(name="Mobilization", milestone_number=1, disbursement_pct=20, percentage=20, amount=1000, status="pending")
        own_project.milestones.create(name="Implementation", milestone_number=2, disbursement_pct=50, percentage=50, amount=2000, status="locked")
        own_project.milestones.create(name="Final", milestone_number=3, disbursement_pct=30, percentage=30, amount=1000, status="locked")
        Project.objects.create(
            vendor_id=str(other_vendor.id),
            vendor_name=other_vendor.username,
            tech_type="ICS",
            technology_type="ICS",
            region="Butha-Buthe",
            district="Butha-Buthe",
            status=ProjectStatus.SETUP_PENDING,
        )
        self.client.force_authenticate(vendor)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        widget = response.data["results"][0]["vendor_dashboard_widget"]
        self.assertEqual(widget["project_id"], own_project.id)
        self.assertEqual(widget["technology_type"], "SHS")
        self.assertEqual(widget["assigned_district"], "Maseru Urban")
        self.assertEqual(widget["installation_target"], 120)
        self.assertEqual(widget["project_duration_months"], 12)
        self.assertEqual(widget["setup_status"], "INCOMPLETE")
        self.assertTrue(widget["submit_installation_disabled"])
        self.assertEqual([item["disbursement_pct"] for item in widget["milestone_plan"]], [20, 50, 30])

    def test_setup_get_returns_project_and_form_sections(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="setup_widget_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            technology_type="SHS",
            region="Maseru",
            district="Maseru",
            district_zone="Maseru Urban",
            status=ProjectStatus.SETUP_PENDING,
            verification_method="iot",
        )
        self.client.force_authenticate(vendor)

        response = self.client.get(f"/api/projects/{project.id}/setup/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["project"]["id"], project.id)
        self.assertEqual(response.data["project"]["setup_status"], "INCOMPLETE")
        self.assertEqual(response.data["form_sections"][0]["key"], "team_resources")
        self.assertEqual(response.data["form_sections"][3]["mode"], "iot")
        self.assertIn("test_connection", response.data["form_sections"][3]["fields"])
        self.assertTrue(response.data["submit_installation_disabled"])

    def test_project_setup_submit_requires_all_sections_and_contract_approval(self):
        tender = Tender.objects.create(
            reference_number="TND-SETUP-001",
            name="Setup Tender",
            department="Dept",
            category="SHS",
            status="Awarded",
            deadline=timezone.now(),
        )
        User = get_user_model()
        vendor = User.objects.create_user(
            username="vendor_setup_complete",
            password="securePass123",
            role="Vendor",
            status="Active",
            gender="Female",
            region="Maseru",
        )
        project = Project.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.SETUP_PENDING,
            verification_method="manual",
            energy_output=100,
            uptime=99,
            gender_impact=0,
        )
        TenderContract.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            reference_number="CTR-SETUP-001",
            status=ContractStatus.APPROVED,
            project_id=str(project.id),
        )
        self.client.force_authenticate(vendor)

        response = self.client.post(
            f"/api/projects/{project.id}/setup/submit/",
            {
                "site_status": "ready",
                "work_schedule_start": "2026-04-01",
                "work_schedule_end": "2026-04-30",
                "device_brand": "SolarCo",
                "device_model": "SHS-100",
                "tech_tier": 2,
                "manual_verification_confirmed": True,
                "checklist_team_ready": True,
                "checklist_equipment_ready": True,
                "checklist_site_ready": True,
                "checklist_safety_ready": True,
                "checklist_logistics_ready": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            f"/api/projects/{project.id}/setup/submit/",
            {
                "team_roster_file": SimpleUploadedFile("team.pdf", b"team", content_type="application/pdf"),
                "equipment_plan_file": SimpleUploadedFile("equipment.pdf", b"equipment", content_type="application/pdf"),
                "compliance_docs_file": SimpleUploadedFile("permits.pdf", b"permits", content_type="application/pdf"),
                "insurance_certificate_file": SimpleUploadedFile("insurance.pdf", b"insurance", content_type="application/pdf"),
                "site_status": "ready",
                "work_schedule_start": "2026-04-01",
                "work_schedule_end": "2026-04-30",
                "device_brand": "SolarCo",
                "device_model": "SHS-100",
                "tech_tier": 2,
                "manual_verification_confirmed": True,
                "checklist_team_ready": True,
                "checklist_equipment_ready": True,
                "checklist_site_ready": True,
                "checklist_safety_ready": True,
                "checklist_logistics_ready": True,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        setup = ProjectSetup.objects.get(project=project)
        setup.refresh_from_db()
        self.assertIsNotNone(project.setup_completed_at)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        self.assertIsNotNone(setup.setup_completed_at)
        self.assertTrue(
            Notification.objects.filter(
                event="project_setup_completed",
                body=f"Vendor {project.vendor_name} completed setup for Project #{project.id}.",
                linked_entity_id=str(project.id),
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="project_setup_completed",
                details__project_id=str(project.id),
                details__actor_id=str(vendor.id),
            ).exists()
        )

    def test_payment_claim_workflow_verify_approve_pay_with_audit(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="claim_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        verifier = User.objects.create_user(
            username="rmt_reviewer",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
        )
        approver = User.objects.create_user(
            username="tac_reviewer",
            password="securePass123",
            role="TAC Member",
            status="Active",
        )
        psc_approver = User.objects.create_user(
            username="psc_reviewer",
            password="securePass123",
            role="Project Steering Committee",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=60,
            energy_output=120.5,
            uptime=97.0,
            gender_impact=55.0,
        )

        self.client.force_authenticate(vendor)
        create_response = self.client.post(
            "/api/projects/claims/",
            {
                "project": project.id,
                "vendor": vendor.id,
                "claim_amount": "15000.00",
                "actual_beneficiaries": 50,
                "actual_female_beneficiaries": 28,
                "declaration_accepted": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        claim_id = create_response.data["id"]
        self.assertEqual(create_response.data["status"], "Submitted")

        self.client.force_authenticate(verifier)
        verify_response = self.client.post(f"/api/projects/claims/{claim_id}/verify/", {}, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["status"], "RMT Approved")

        self.client.force_authenticate(approver)
        approve_response = self.client.post(f"/api/projects/claims/{claim_id}/approve/", {}, format="json")
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], "TAC Endorsed")

        self.client.force_authenticate(psc_approver)
        psc_response = self.client.post(f"/api/projects/claims/{claim_id}/approve/", {}, format="json")
        self.assertEqual(psc_response.status_code, status.HTTP_200_OK)
        self.assertEqual(psc_response.data["status"], "PSC Approved")

        self.client.force_authenticate(verifier)
        confirm_response = self.client.post(
            f"/api/projects/claims/{claim_id}/confirm-paid/",
            {"payment_reference": "BANK-REF-001"},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], "Completed")
        self.assertEqual(confirm_response.data["payment_reference"], "BANK-REF-001")

    def test_psc_bank_view_is_masked_by_default_and_can_reveal_full_number_with_audit_log(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="bank_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            organization_name="Banked Vendor Ltd",
            bank_name="First National Bank",
            bank_branch="Maseru Main",
            bank_account_name="Banked Vendor Ltd",
            bank_account_number="123456789012",
            bank_swift_code="FNBLLSMX",
            bank_sort_code="12-34-56",
        )
        psc_user = User.objects.create_user(
            username="psc_bank_viewer",
            password="securePass123",
            role="Project Steering Committee",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.DISBURSEMENT,
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="9000.00",
            status=PaymentClaimStatus.TAC_ENDORSED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(psc_user)
        detail_response = self.client.get(f"/api/projects/claims/{claim.id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["vendor_account_number"], "********9012")

        view_response = self.client.post(
            f"/api/projects/claims/{claim.id}/view_bank_details/",
            {"reveal_full": True},
            format="json",
        )
        self.assertEqual(view_response.status_code, status.HTTP_200_OK)
        self.assertEqual(view_response.data["vendor_account_number"], "123456789012")
        self.assertTrue(
            AuditLog.objects.filter(
                action="claim_vendor_bank_details_viewed",
                entity_id=str(claim.id),
                details__requested_by="PSC",
                details__visibility="full_reveal",
            ).exists()
        )

    def test_confirm_paid_requires_payment_reference(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="no_ref_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        rmt_user = User.objects.create_user(
            username="rmt_no_ref",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.DISBURSEMENT,
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="4000.00",
            status=PaymentClaimStatus.PSC_APPROVED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(rmt_user)
        response = self.client.post(f"/api/projects/claims/{claim.id}/confirm-paid/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payment_reference", str(response.data))

    def test_rmt_can_view_disbursement_sheet_after_psc_approval(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="sheet_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            organization_name="Sheet Vendor Ltd",
        )
        rmt_user = User.objects.create_user(
            username="rmt_sheet_viewer",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.DISBURSEMENT,
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="7650.00",
            status=PaymentClaimStatus.PSC_APPROVED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(rmt_user)
        response = self.client.post(f"/api/projects/claims/{claim.id}/disbursement-sheet/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["claim_id"], str(claim.id))
        self.assertEqual(response.data["vendor_legal_name"], "Sheet Vendor Ltd")
        self.assertEqual(response.data["total_approved_amount"], "7650.00")
        self.assertTrue(
            AuditLog.objects.filter(
                action="claim_disbursement_sheet_viewed",
                entity_id=str(claim.id),
                details__requested_by="RMT",
                details__visibility="full",
            ).exists()
        )

    def test_final_milestone_payment_marks_project_completed_without_queuing_live_prospect_report(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="final_claim_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        psc_approver = User.objects.create_user(
            username="final_psc_reviewer",
            password="securePass123",
            role="Project Steering Committee",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.DISBURSEMENT,
            project_reference="PRJ-FINAL-001",
            energy_output=100,
            uptime=97,
            gender_impact=50,
        )
        project.milestones.create(name="M1", milestone_number=1, percentage=20, amount=1000, status="paid")
        project.milestones.create(name="M2", milestone_number=2, percentage=50, amount=2000, status="paid")
        milestone3 = project.milestones.create(name="M3", milestone_number=3, percentage=30, amount=3000, status="approved")
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            milestone=milestone3,
            claim_amount="3000.00",
            status=PaymentClaimStatus.TAC_ENDORSED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(psc_approver)
        approve_response = self.client.post(f"/api/projects/claims/{claim.id}/approve/", {}, format="json")
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(User.objects.create_user(
            username="final_rmt_reviewer",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
        ))
        confirm_response = self.client.post(
            f"/api/projects/claims/{claim.id}/confirm-paid/",
            {"payment_reference": "BANK-REF-FINAL-001"},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        milestone3.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(milestone3.status, "paid")
        self.assertTrue(
            AuditLog.objects.filter(action="project_completed", details__project_id=str(project.id)).exists()
        )

    @patch("rbf.projects.views.SyncToProspectJob.dispatch_async")
    def test_meter_csv_upload_returns_invalid_rows_and_creates_anomalies(self, dispatch_async):
        tender = Tender.objects.create(
            reference_number="TND-METER-001",
            name="Meter Tender",
            department="Dept",
            category="SHS",
            status="Awarded",
            deadline=timezone.now(),
        )
        User = get_user_model()
        vendor = User.objects.create_user(
            username="meter_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
        )
        project = Project.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.ACTIVE,
        )
        TenderContract.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            reference_number="CTR-METER-001",
            status=ContractStatus.APPROVED,
            project_id=str(project.id),
        )
        self._create_completed_setup(project, vendor)
        installation = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-METER-1",
            beneficiary_id="BEN-METER-1",
            meter_id="MTR-CSV-001",
            status=InstallationStatus.VERIFIED,
        )
        stale_installation = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.32,
            gps_lng=27.49,
            serial_number="SERIAL-METER-2",
            beneficiary_id="BEN-METER-2",
            meter_id="MTR-CSV-002",
            status=InstallationStatus.VERIFIED,
        )
        SmartMeterReading.objects.create(
            project=project,
            installation=installation,
            meter_id="MTR-CSV-001",
            kwh=100,
            uptime_pct=98,
            recorded_at=timezone.now() - timedelta(days=3),
        )
        SmartMeterReading.objects.create(
            project=project,
            installation=stale_installation,
            meter_id="MTR-CSV-002",
            kwh=90,
            uptime_pct=95,
            recorded_at=timezone.now() - timedelta(days=3),
        )

        csv_bytes = (
            "meter_id,installation_id,kwh_generated,uptime_pct,latitude,longitude,reading_datetime\n"
            f"MTR-CSV-001,{installation.id},106,0,-29.31,27.48,2026-04-16T08:30:00Z\n"
            "BAD-METER,,12,101,-29.31,27.48,not-a-date\n"
        ).encode("utf-8")
        self.client.force_authenticate(vendor)

        response = self.client.post(
            f"/api/projects/{project.id}/meter-csv-upload/",
            {"file": SimpleUploadedFile("meter.csv", csv_bytes, content_type="text/csv")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["rows_ingested"], 1)
        self.assertEqual(response.data["rows_rejected"], 1)
        self.assertEqual(len(response.data["invalid_rows"]), 1)
        self.assertEqual(response.data["anomaly_counts"]["zero_uptime"], 1)
        self.assertEqual(response.data["anomaly_counts"]["no_data"], 1)
        self.assertEqual(response.data["anomaly_counts"]["output_deviation"], 1)
        self.assertTrue(AnomalyFlag.objects.filter(installation=installation, flag_type="zero_uptime").exists())
        self.assertTrue(AnomalyFlag.objects.filter(installation=stale_installation, flag_type="no_data").exists())
        self.assertTrue(AnomalyFlag.objects.filter(installation=installation, flag_type="output_deviation").exists())
        dispatch_async.assert_called()
        sync_method, payload = dispatch_async.call_args[0][:2]
        self.assertEqual(sync_method, "pushInstallationTimeSeries")
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["serial_number"], "MTR-CSV-001")
        self.assertEqual(payload["data"][0]["output_energy_interval_wh"], 106000.0)
        self.assertEqual(payload["data"][0]["output_energy_cumulative_wh"], 206000.0)
        self.assertEqual(payload["data"][0]["output_power_w"], None)
        self.assertTrue(payload["data"][0]["metered_at"].endswith("+00:00"))

    @patch("rbf.projects.views.SyncToProspectJob.dispatch_async")
    def test_meter_csv_upload_accepts_non_numeric_installation_identifier(self, dispatch_async):
        tender = Tender.objects.create(
            reference_number="TND-METER-ALT-ID",
            name="Meter Tender Alt Id",
            department="Dept",
            category="SHS",
            status="Awarded",
            deadline=timezone.now(),
        )
        vendor = get_user_model().objects.create_user(
            username="meter_alt_id_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            bank_name="Test Bank",
            bank_account_name="Vendor Test",
            bank_account_number="1234567890",
        )
        project = Project.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.ACTIVE,
        )
        TenderContract.objects.create(
            tender=tender,
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            reference_number="CTR-METER-ALT-ID",
            status=ContractStatus.APPROVED,
            project_id=str(project.id),
        )
        self._create_completed_setup(project, vendor)
        installation = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="INS-001",
            beneficiary_id="BEN-ALT-001",
            meter_id="MTR-ALT-001",
            status=InstallationStatus.VERIFIED,
        )

        csv_bytes = (
            "meter_id,installation_id,kwh_generated,uptime_pct,latitude,longitude,reading_datetime\n"
            "MTR-ALT-001,INS-001,12,99,-29.31,27.48,2026-04-16T08:30:00Z\n"
        ).encode("utf-8")
        self.client.force_authenticate(vendor)

        response = self.client.post(
            f"/api/projects/{project.id}/meter-csv-upload/",
            {"file": SimpleUploadedFile("meter.csv", csv_bytes, content_type="text/csv")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reading = SmartMeterReading.objects.get(project=project, meter_id="MTR-ALT-001")
        self.assertEqual(reading.installation_id, installation.id)
        dispatch_async.assert_called()

    def test_duplicate_milestone_claim_is_locked_after_submission(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="claim_lock_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.INSTALLATION,
            energy_output=1,
            uptime=1,
            gender_impact=0,
        )
        milestone = project.milestones.create(name="Mobilization", percentage=20, amount=1000)

        self.client.force_authenticate(vendor)
        first = self.client.post(
            "/api/projects/claims/",
            {
                "project": project.id,
                "milestone": milestone.id,
                "claim_amount": "1000.00",
                "actual_beneficiaries": 10,
                "actual_female_beneficiaries": 5,
                "declaration_accepted": True,
            },
            format="json",
        )
        second = self.client.post(
            "/api/projects/claims/",
            {
                "project": project.id,
                "milestone": milestone.id,
                "claim_amount": "1000.00",
                "actual_beneficiaries": 10,
                "actual_female_beneficiaries": 5,
                "declaration_accepted": True,
            },
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(second.data["detail"]).lower())

    def test_installation_report_rejects_coordinates_outside_lesotho(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="gis_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            gender="Male",
            mobile_number="26650000001",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=0,
            gender_impact=0,
        )
        self._create_completed_setup(project, vendor)
        self.client.force_authenticate(vendor)

        response = self.client.post(
            "/api/projects/installations/",
            {
                "project": project.id,
                "gps_lat": -10.0,
                "gps_lng": 10.0,
                "serial_number": "SERIAL-OUTSIDE-1",
                "beneficiary_id": "BEN-OUTSIDE-1",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertFalse(InstallationReport.objects.filter(project=project).exists())

    def test_installation_report_duplicate_gps_creates_warning_and_anomaly_flag(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="dup_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            gender="Male",
            mobile_number="26650000002",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=97,
            gender_impact=0,
        )
        self._create_completed_setup(project, vendor)
        InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-BASE-1",
            beneficiary_id="BEN-BASE-1",
            installation_date="2025-01-01",
        )
        self.client.force_authenticate(vendor)

        response = self.client.post(
            "/api/projects/installations/",
            {
                "project": project.id,
                "gps_lat": -29.31001,
                "gps_lng": 27.48001,
                "serial_number": "SERIAL-DUP-2",
                "beneficiary_id": "BEN-DUP-2",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("warning", response.data)
        created_id = response.data["data"]["id"]
        self.assertTrue(AnomalyFlag.objects.filter(installation_id=created_id, flag_type="duplicate_gps").exists())

    def test_installation_report_rejects_coordinates_outside_project_district(self):
        self._write_district_geojson()
        User = get_user_model()
        vendor = User.objects.create_user(
            username="district_locked_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            gender="Male",
            mobile_number="26650000008",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=0,
            gender_impact=0,
        )
        self._create_completed_setup(project, vendor)
        self.client.force_authenticate(vendor)

        response = self.client.post(
            "/api/projects/installations/",
            {
                "project": project.id,
                "gps_lat": -30.0,
                "gps_lng": 28.5,
                "serial_number": "SERIAL-DISTRICT-OUT-1",
                "beneficiary_id": "BEN-DISTRICT-OUT-1",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("assigned project district", str(response.data["errors"]["gps_lat"][0]))
        self.assertFalse(InstallationReport.objects.filter(project=project).exists())

    def test_installation_report_accepts_coordinates_inside_project_district(self):
        self._write_district_geojson()
        User = get_user_model()
        vendor = User.objects.create_user(
            username="district_ok_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            gender="Male",
            mobile_number="26650000009",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=0,
            gender_impact=0,
        )
        self._create_completed_setup(project, vendor)
        self.client.force_authenticate(vendor)

        response = self.client.post(
            "/api/projects/installations/",
            {
                "project": project.id,
                "gps_lat": -30.0,
                "gps_lng": 27.5,
                "serial_number": "SERIAL-DISTRICT-IN-1",
                "beneficiary_id": "BEN-DISTRICT-IN-1",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(InstallationReport.objects.filter(project=project, serial_number="SERIAL-DISTRICT-IN-1").exists())

    def test_map_installations_endpoint_returns_summary_and_vendor_scope(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="map_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            gender="Female",
            mobile_number="26650000003",
        )
        other_vendor = User.objects.create_user(
            username="other_map_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Berea",
            gender="Male",
            mobile_number="26650000004",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=98.1,
            gender_impact=0,
        )
        other_project = Project.objects.create(
            vendor_id=str(other_vendor.id),
            vendor_name=other_vendor.username,
            tech_type="ICS",
            region="Berea",
            district="Berea",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=88.0,
            gender_impact=0,
        )
        own_report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-MAP-1",
            beneficiary_id="BEN-MAP-1",
            beneficiary_name="Jane Mokoena",
            household_type="female_headed",
            installation_date="2025-01-15",
            status=InstallationStatus.VERIFIED,
            gis_status="green",
        )
        InstallationReport.objects.create(
            project=other_project,
            vendor=other_vendor,
            gps_lat=-29.21,
            gps_lng=27.58,
            serial_number="SERIAL-MAP-2",
            beneficiary_id="BEN-MAP-2",
            beneficiary_name="John Molefe",
            household_type="standard",
            installation_date="2025-01-16",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )
        VerificationTask.objects.create(
            report=own_report,
            vendor_lat=own_report.gps_lat,
            vendor_lng=own_report.gps_lng,
            status=VerificationStatus.VERIFIED,
        )
        self.client.force_authenticate(vendor)

        response = self.client.get("/api/map/installations")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["summary"]["total"], 1)
        self.assertEqual(len(response.data["data"]["installations"]), 1)
        self.assertEqual(response.data["data"]["installations"][0]["vendor_name"], vendor.username)
        self.assertNotIn("beneficiary_id", response.data["data"]["installations"][0])
        self.assertNotIn("receipt_file", response.data["data"]["installations"][0])

    def test_installations_map_data_endpoint_returns_requested_shape(self):
        User = get_user_model()
        officer = User.objects.create_user(
            username="field_map_user",
            password="securePass123",
            role="Field Verifier",
            status="Active",
            verification_zone="Maseru",
        )
        project = Project.objects.create(
            vendor_id="V-001",
            vendor_name="SunPower Ltd",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=98,
            gender_impact=0,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=officer,
            gps_lat=-29.3142,
            gps_lng=27.4869,
            serial_number="SERIAL-MAP-3",
            beneficiary_id="BEN-MAP-3",
            beneficiary_name="Jane Mokoena",
            household_type="female_headed",
            installation_date="2025-01-15",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )
        VerificationTask.objects.create(
            report=report,
            assigned_verifier=officer,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(officer)
        response = self.client.get("/api/installations/map-data")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        item = response.data["data"]["installations"][0]
        self.assertEqual(item["latitude"], -29.3142)
        self.assertEqual(item["longitude"], 27.4869)
        self.assertEqual(item["beneficiary_name"], "Jane Mokoena")
        self.assertEqual(item["verification_status"], "Pending")
        self.assertEqual(item["district"], "Maseru")

    def test_map_installations_endpoint_scopes_field_verifier_using_comma_separated_zone(self):
        User = get_user_model()
        verifier = User.objects.create_user(
            username="field_map_multi_zone",
            password="securePass123",
            role="Field Verifier",
            status="Active",
            verification_zone="Maseru, Berea",
        )
        project_maseru = Project.objects.create(
            vendor_id="V-100",
            vendor_name="Vendor A",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=90,
            gender_impact=0,
        )
        project_berea = Project.objects.create(
            vendor_id="V-101",
            vendor_name="Vendor B",
            tech_type="ICS",
            region="Berea",
            district="Berea",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=90,
            gender_impact=0,
        )
        project_other = Project.objects.create(
            vendor_id="V-102",
            vendor_name="Vendor C",
            tech_type="SHS",
            region="Butha-Buthe",
            district="Butha-Buthe",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=90,
            gender_impact=0,
        )
        InstallationReport.objects.create(
            project=project_maseru,
            vendor=verifier,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-MULTI-1",
            beneficiary_id="BEN-MULTI-1",
            status=InstallationStatus.SUBMITTED,
        )
        InstallationReport.objects.create(
            project=project_berea,
            vendor=verifier,
            gps_lat=-29.21,
            gps_lng=27.58,
            serial_number="SERIAL-MULTI-2",
            beneficiary_id="BEN-MULTI-2",
            status=InstallationStatus.SUBMITTED,
        )
        InstallationReport.objects.create(
            project=project_other,
            vendor=verifier,
            gps_lat=-28.76,
            gps_lng=28.24,
            serial_number="SERIAL-MULTI-3",
            beneficiary_id="BEN-MULTI-3",
            status=InstallationStatus.SUBMITTED,
        )

        self.client.force_authenticate(verifier)
        response = self.client.get("/api/map/installations")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        districts = {item["district"] for item in response.data["data"]["installations"]}
        self.assertIn("Maseru", districts)
        self.assertIn("Berea", districts)
        self.assertNotIn("Butha-Buthe", districts)

    def test_map_vendor_name_uses_project_vendor_not_report_creator(self):
        User = get_user_model()
        admin_user = User.objects.create_user(
            username="map_admin_creator",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        project_vendor = User.objects.create_user(
            username="actual_project_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(project_vendor.id),
            vendor_name="SunPower Ltd",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=98,
            gender_impact=0,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=admin_user,
            gps_lat=-29.3142,
            gps_lng=27.4869,
            serial_number="SERIAL-MAP-VENDOR",
            beneficiary_id="BEN-MAP-VENDOR",
            beneficiary_name="Jane Mokoena",
            household_type="female_headed",
            installation_date="2025-01-15",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )
        VerificationTask.objects.create(
            report=report,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(admin_user)
        response = self.client.get("/api/installations/map-data")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["installations"][0]["vendor_name"], "SunPower Ltd")

    def test_map_vendor_name_resolves_from_vendor_account_when_project_name_is_stale(self):
        User = get_user_model()
        admin_user = User.objects.create_user(
            username="map_admin_stale_vendor",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        project_vendor = User.objects.create_user(
            username="different_vendor_user",
            password="securePass123",
            role="Vendor",
            status="Active",
            organization_name="Different Vendor Ltd",
            full_name="Vendor Contact Person",
        )
        project = Project.objects.create(
            vendor_id=str(project_vendor.id),
            vendor_name="ABC Corp",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=98,
            gender_impact=0,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=admin_user,
            gps_lat=-29.3142,
            gps_lng=27.4869,
            serial_number="SERIAL-MAP-STALE-VENDOR",
            beneficiary_id="BEN-MAP-STALE-VENDOR",
            beneficiary_name="Jane Mokoena",
            household_type="female_headed",
            installation_date="2025-01-15",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )
        VerificationTask.objects.create(
            report=report,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(admin_user)
        response = self.client.get("/api/installations/map-data")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["installations"][0]["vendor_name"], "Different Vendor Ltd")

    def test_doe_officer_map_scope_is_not_region_limited(self):
        User = get_user_model()
        doe_user = User.objects.create_user(
            username="doe_map_user",
            password="securePass123",
            role="DoE Officer",
            status="Active",
            region="Maseru",
        )
        vendor = User.objects.create_user(
            username="doe_map_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=98,
            gender_impact=0,
        )
        other_project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="ICS",
            region="Berea",
            district="Berea",
            status=ProjectStatus.INSTALLATION,
            progress=0,
            energy_output=0,
            uptime=95,
            gender_impact=0,
        )
        InstallationReport.objects.create(
            project=other_project,
            vendor=vendor,
            gps_lat=-29.21,
            gps_lng=27.58,
            serial_number="SERIAL-MAP-DOE",
            beneficiary_id="BEN-MAP-DOE",
            beneficiary_name="John Molefe",
            household_type="standard",
            installation_date="2025-01-16",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )

        self.client.force_authenticate(doe_user)
        response = self.client.get("/api/installations/map-data")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["summary"]["total"], 1)

    def test_blacklisted_vendor_claim_exposes_payment_lock_and_cannot_be_paid(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="locked_claim_vendor",
            password="securePass123",
            role="Vendor",
            status="Blacklisted",
            is_active=True,
        )
        approver = User.objects.create_user(
            username="payment_lock_admin",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )

        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.DISBURSEMENT,
            progress=90,
            energy_output=100,
            uptime=97,
            gender_impact=50,
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="5000.00",
            status=PaymentClaimStatus.PSC_APPROVED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(approver)
        detail_response = self.client.get(f"/api/projects/claims/{claim.id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertTrue(detail_response.data["payment_locked"])
        self.assertIn("blacklisted vendor", detail_response.data["payment_lock_reason"].lower())

        pay_response = self.client.post(f"/api/projects/claims/{claim.id}/pay/", {}, format="json")
        self.assertEqual(pay_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("frozen", str(pay_response.data).lower())

    def test_project_steering_committee_can_approve_claims_and_flag_project_issues(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="psc_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        psc_user = User.objects.create_user(
            username="psc_user",
            password="securePass123",
            role="Project Steering Committee",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.DISBURSEMENT,
            progress=90,
            energy_output=100,
            uptime=97,
            gender_impact=50,
            project_reference="PRJ-PSC-001",
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="7000.00",
            status=PaymentClaimStatus.TAC_ENDORSED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(psc_user)
        approve_response = self.client.post(
            f"/api/projects/claims/{claim.id}/approve/",
            {},
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], "PSC Approved")

        audit_logs = self.client.get("/api/projects/audit-logs/")
        self.assertEqual(audit_logs.status_code, status.HTTP_200_OK)

        export_csv = self.client.get("/api/projects/audit-logs/export-csv/?module=paymentclaim")
        self.assertEqual(export_csv.status_code, status.HTTP_200_OK)
        self.assertEqual(export_csv["Content-Type"], "text/csv")
        self.assertIn("Action", export_csv.content.decode("utf-8"))

        with patch("rbf.tenders.pba_pdf._render_pdf") as mock_render:
            def _fake_render(_html, output_path, _ref):
                output_path.write_bytes(b"%PDF-1.4\n%fake\n")

            mock_render.side_effect = _fake_render
            export_pdf = self.client.get("/api/projects/audit-logs/export-pdf/?module=paymentclaim")
        self.assertEqual(export_pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(export_pdf["Content-Type"], "application/pdf")

        flag_response = self.client.post(
            f"/api/projects/{project.id}/flag_issue/",
            {"category": "payment_delay", "details": "PSC flagged delayed payment clearance for review."},
            format="json",
        )
        self.assertEqual(flag_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ProjectUpdate.objects.filter(
                project=project,
                title="Payment Delay Flagged",
            ).exists()
        )

    def test_paused_or_terminated_verification_tasks_cannot_be_verified(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="verification_vendor",
            password="securePass123",
            role="Vendor",
            status="Suspended",
            is_active=True,
        )
        verifier = User.objects.create_user(
            username="verification_guard",
            password="securePass123",
            role="Field Verifier",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            status=ProjectStatus.VERIFICATION,
            progress=80,
            energy_output=88,
            uptime=96,
            gender_impact=50,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-VERIFY-1",
            beneficiary_id="BEN-VERIFY-1",
            status=InstallationStatus.PAUSED,
        )
        paused_task = VerificationTask.objects.create(
            report=report,
            assigned_verifier=verifier,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PAUSED,
        )

        self.client.force_authenticate(verifier)
        paused_response = self.client.post(
            f"/api/projects/verification-tasks/{paused_task.id}/verify/",
            {"verifier_lat": -29.31, "verifier_lng": 27.48},
            format="json",
        )
        self.assertEqual(paused_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paused", str(paused_response.data).lower())

        vendor.status = "Blacklisted"
        vendor.save(update_fields=["status"])
        report.status = InstallationStatus.TERMINATED
        report.save(update_fields=["status"])
        paused_task.status = VerificationStatus.TERMINATED
        paused_task.save(update_fields=["status"])

        terminated_response = self.client.post(
            f"/api/projects/verification-tasks/{paused_task.id}/verify/",
            {"verifier_lat": -29.31, "verifier_lng": 27.48},
            format="json",
        )
        self.assertEqual(terminated_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("terminated", str(terminated_response.data).lower())

    @patch("rbf.projects.views.queue_installation_sync")
    def test_verification_repushes_installation_only(self, queue_installation):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="verification_vendor_ok",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        verifier = User.objects.create_user(
            username="verification_guard_ok",
            password="securePass123",
            role="Field Verifier",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.VERIFICATION,
            progress=80,
            energy_output=88,
            uptime=96,
            gender_impact=50,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-VERIFY-2",
            beneficiary_id="BEN-VERIFY-2",
            status=InstallationStatus.SUBMITTED,
        )
        task = VerificationTask.objects.create(
            report=report,
            assigned_verifier=verifier,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(verifier)
        response = self.client.post(
            f"/api/projects/verification-tasks/{task.id}/verify/",
            {"verifier_lat": -29.31, "verifier_lng": 27.48, "verification_status": "verified"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        queue_installation.assert_called_once_with(str(report.id), include_customer=False, include_installation=True)

    def test_field_verifier_can_access_and_verify_any_task_in_assigned_district(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="district_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        verifier = User.objects.create_user(
            username="district_verifier",
            password="securePass123",
            role="Field Verifier",
            status="Active",
            verification_zone="Maseru",
        )
        other_verifier = User.objects.create_user(
            username="district_verifier_other",
            password="securePass123",
            role="Field Verifier",
            status="Active",
            verification_zone="Maseru",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.VERIFICATION,
            progress=20,
            energy_output=10,
            uptime=96,
            gender_impact=50,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-DISTRICT-1",
            beneficiary_id="BEN-DISTRICT-1",
            status=InstallationStatus.SUBMITTED,
        )
        task = VerificationTask.objects.create(
            report=report,
            assigned_verifier=other_verifier,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(verifier)
        list_response = self.client.get("/api/projects/verification-tasks/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)

        verify_response = self.client.post(
            f"/api/projects/verification-tasks/{task.id}/verify/",
            {
                "verifier_lat": -29.31,
                "verifier_lng": 27.48,
                "verification_status": "verified",
            },
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, VerificationStatus.VERIFIED)

    @patch("rbf.projects.views.SyncToProspectJob.dispatch_async")
    def test_prospect_sync_panel_refresh_queues_read_endpoints_on_demand(self, dispatch_async):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            "/api/projects/prospect-sync-logs/refresh-panel/",
            {"project_id": 42, "size": 25},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(dispatch_async.call_count, 2)
        first_call = dispatch_async.call_args_list[0]
        second_call = dispatch_async.call_args_list[1]
        self.assertEqual(first_call.args[0], "getInstallations")
        self.assertEqual(second_call.args[0], "getTargets")
        self.assertEqual(first_call.args[1]["reporting_phase"], "PRJ-42")
        self.assertEqual(first_call.args[1]["size"], 25)
        self.assertEqual(first_call.kwargs["record_type"], "sync_panel")

class ProjectKpiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.rbf_user = User.objects.create_user(
            username="kpi_rbf",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
        )
        self.vendor = User.objects.create_user(
            username="kpi_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
        )
        self.other_vendor = User.objects.create_user(
            username="kpi_vendor_other",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Butha-Buthe",
        )
        self.doe = User.objects.create_user(
            username="kpi_doe",
            password="securePass123",
            role="DoE Officer",
            status="Active",
            region="Maseru",
        )
        tender = Tender.objects.create(
            reference_number="TND-KPI-001",
            name="KPI Tender",
            department="Dept",
            category="Solar",
            status="Awarded",
            deadline=timezone.now() + timedelta(days=30),
        )
        self.project = Project.objects.create(
            tender=tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
            start_date=timezone.localdate() - timedelta(days=45),
            end_date=timezone.localdate() + timedelta(days=45),
            target_installations=10,
            target_female_pct=50,
            target_vulnerable_pct=30,
            target_low_income_pct=20,
            deployment_team_roster="Team A",
            deployment_equipment_plan="Plan A",
            deployment_site_status="Sites ready",
            deployment_work_schedule="Week 1 to 8",
            deployment_permits_status="Permits approved",
            device_brand="SolarCo",
            device_model="SHS-200",
            device_tech_tier="Tier 2",
            verification_method_confirmed=True,
            setup_completed_at=timezone.now(),
            energy_output=200,
            uptime=99,
            progress=30,
        )
        TenderContract.objects.create(
            tender=tender,
            vendor_id=str(self.vendor.id),
            vendor_name=self.vendor.username,
            reference_number="CTR-KPI-001",
            status="Approved",
            project_id=str(self.project.id),
        )
        milestone1 = self.project.milestones.create(name="Mobilization", milestone_number=1, disbursement_pct=20, percentage=20, amount=1000)
        milestone2 = self.project.milestones.create(name="Installation", milestone_number=2, disbursement_pct=50, percentage=50, amount=2000)
        self.project.milestones.create(name="Commissioning", milestone_number=3, disbursement_pct=30, percentage=30, amount=1000)
        PaymentClaim.objects.create(
            project=self.project,
            vendor=self.vendor,
            milestone=milestone1,
            claim_amount="1000.00",
            status=PaymentClaimStatus.COMPLETED,
            declaration_accepted=True,
        )
        self.verified_1 = InstallationReport.objects.create(
            project=self.project,
            vendor=self.vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SER-KPI-1",
            beneficiary_id="BEN-KPI-1",
            household_type="female_headed",
            meter_id="MTR-001",
            status=InstallationStatus.VERIFIED,
        )
        self.verified_2 = InstallationReport.objects.create(
            project=self.project,
            vendor=self.vendor,
            gps_lat=-29.32,
            gps_lng=27.49,
            serial_number="SER-KPI-2",
            beneficiary_id="BEN-KPI-2",
            household_type="vulnerable",
            meter_id="MTR-002",
            status=InstallationStatus.VERIFIED,
        )
        InstallationReport.objects.create(
            project=self.project,
            vendor=self.vendor,
            gps_lat=-29.33,
            gps_lng=27.50,
            serial_number="SER-KPI-3",
            beneficiary_id="BEN-KPI-3",
            household_type="standard",
            status=InstallationStatus.SUBMITTED,
        )
        SmartMeterReading.objects.create(
            project=self.project,
            installation=self.verified_1,
            meter_id="MTR-001",
            kwh=180,
            uptime_pct=99.5,
            recorded_at=timezone.now() - timedelta(days=5),
        )
        SmartMeterReading.objects.create(
            project=self.project,
            installation=self.verified_2,
            meter_id="MTR-002",
            kwh=150,
            uptime_pct=97.5,
            recorded_at=timezone.now() - timedelta(days=4),
        )
        self.project_refresh = lambda: Project.objects.get(id=self.project.id)
        cache.clear()

    def test_kpi_service_returns_summary_and_marks_milestone_one_claimable(self):
        summary = KpiService.for_project(str(self.project.id)).getFullKpiSummary()

        self.assertEqual(summary["installation_progress"]["verified"], 2)
        self.assertEqual(summary["installation_progress"]["target"], 10)
        self.assertEqual(summary["gender_kpi"]["female_headed"]["count"], 1)
        self.assertEqual(len(summary["energy_kpi"]["monthly_data"]), 1)
        self.assertEqual(summary["uptime_kpi"]["total_devices_monitored"], 2)
        self.assertTrue(summary["milestone_eligibility"]["milestone_1"]["eligible"])
        milestone1 = self.project_refresh().milestones.order_by("created_at", "id").first()
        self.assertEqual(milestone1.status, "claimable")

    def test_kpi_summary_syncs_project_snapshot_fields(self):
        summary = KpiService.for_project(str(self.project.id)).getFullKpiSummary()

        self.project.refresh_from_db()

        self.assertEqual(self.project.progress, round(summary["installation_progress"]["progress_pct"]))
        self.assertEqual(float(self.project.gender_impact), float(summary["gender_kpi"]["female_headed"]["percentage"]))
        self.assertEqual(float(self.project.uptime), float(summary["uptime_kpi"]["average_uptime_pct"]))
        self.assertEqual(float(self.project.energy_output), float(summary["energy_kpi"]["current_month_kwh"]))

    def test_milestone_two_becomes_claimable_with_80_percent_verified_and_non_blocking_flags(self):
        for index in range(3, 9):
            InstallationReport.objects.create(
                project=self.project,
                vendor=self.vendor,
                gps_lat=-29.30 - (index * 0.01),
                gps_lng=27.40 + (index * 0.01),
                serial_number=f"SER-KPI-{index}",
                beneficiary_id=f"BEN-KPI-{index}",
                household_type="female_headed" if index % 2 == 0 else "standard",
                meter_id=f"MTR-00{index}",
                status=InstallationStatus.VERIFIED,
            )

        AnomalyFlag.objects.create(
            installation=self.verified_1,
            project=self.project,
            flag_type="duplicate_gps",
            description="Duplicate GPS warning",
        )
        AnomalyFlag.objects.create(
            installation=self.verified_2,
            project=self.project,
            flag_type="location_mismatch",
            description="Location mismatch warning",
        )

        summary = KpiService.for_project(str(self.project.id)).getFullKpiSummary()

        self.assertTrue(summary["milestone_eligibility"]["milestone_2"]["eligible"])
        self.assertTrue(summary["milestone_eligibility"]["milestone_2"]["conditions"]["no_blocking_anomaly_flags"])
        milestone2 = self.project_refresh().milestones.get(milestone_number=2)
        self.assertEqual(milestone2.status, "claimable")

    def test_milestone_two_stays_claimable_after_later_kpi_drop(self):
        milestone2 = self.project.milestones.get(milestone_number=2)
        milestone2.status = "claimable"
        milestone2.save(update_fields=["status", "updated_at"])

        for index in range(3, 11):
            InstallationReport.objects.create(
                project=self.project,
                vendor=self.vendor,
                gps_lat=-29.10 - (index * 0.01),
                gps_lng=27.10 + (index * 0.01),
                serial_number=f"SER-DROP-{index}",
                beneficiary_id=f"BEN-DROP-{index}",
                household_type="standard",
                meter_id=f"MTR-DROP-{index}",
                status=InstallationStatus.VERIFIED,
            )

        summary = KpiService.for_project(str(self.project.id)).getFullKpiSummary()

        self.assertFalse(summary["milestone_eligibility"]["milestone_2"]["eligible"])
        self.assertEqual(summary["milestone_eligibility"]["milestone_2"]["status"], "CLAIMABLE")
        milestone2.refresh_from_db()
        self.assertEqual(milestone2.status, "claimable")

    def test_milestone_three_requires_milestone_two_paid_and_zero_open_flags(self):
        milestone2 = self.project.milestones.get(milestone_number=2)
        milestone2.status = "paid"
        milestone2.save(update_fields=["status", "updated_at"])
        PaymentClaim.objects.create(
            project=self.project,
            vendor=self.vendor,
            milestone=milestone2,
            claim_amount="2000.00",
            status=PaymentClaimStatus.COMPLETED,
            declaration_accepted=True,
        )
        for index in range(3, 11):
            InstallationReport.objects.create(
                project=self.project,
                vendor=self.vendor,
                gps_lat=-29.50 - (index * 0.01),
                gps_lng=27.60 + (index * 0.01),
                serial_number=f"SER-M3-{index}",
                beneficiary_id=f"BEN-M3-{index}",
                household_type="standard",
                meter_id=f"MTR-M3-{index}",
                status=InstallationStatus.VERIFIED,
            )
        AnomalyFlag.objects.create(
            installation=self.verified_1,
            project=self.project,
            flag_type="zero_uptime",
            description="Blocking flag",
        )

        summary = KpiService.for_project(str(self.project.id)).getFullKpiSummary()

        self.assertFalse(summary["milestone_eligibility"]["milestone_3"]["eligible"])
        self.assertTrue(summary["milestone_eligibility"]["milestone_3"]["conditions"]["milestone_2_paid"])
        self.assertFalse(summary["milestone_eligibility"]["milestone_3"]["conditions"]["all_anomaly_flags_resolved"])

    def test_project_kpi_endpoint_respects_vendor_and_region_access(self):
        self.client.force_authenticate(self.vendor)
        own_response = self.client.get(f"/api/kpi/project/{self.project.id}")
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)

        other_project = Project.objects.create(
            vendor_id=str(self.other_vendor.id),
            vendor_name=self.other_vendor.username,
            tech_type="ICS",
            region="Butha-Buthe",
            district="Butha-Buthe",
            status=ProjectStatus.INSTALLATION,
            target_installations=5,
            energy_output=20,
            uptime=95,
            progress=0,
        )
        forbidden_response = self.client.get(f"/api/kpi/project/{other_project.id}")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.doe)
        doe_response = self.client.get(f"/api/kpi/project/{self.project.id}")
        self.assertEqual(doe_response.status_code, status.HTTP_200_OK)
        doe_forbidden = self.client.get(f"/api/kpi/project/{other_project.id}")
        self.assertEqual(doe_forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_portfolio_endpoint_available_to_rbf_only(self):
        self.client.force_authenticate(self.rbf_user)
        response = self.client.get("/api/kpi/portfolio")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_projects", response.data)
        self.assertIn("scope_label", response.data)

        self.client.force_authenticate(self.vendor)
        forbidden = self.client.get("/api/kpi/portfolio")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_portfolio_endpoint_scopes_doe_to_their_region(self):
        other_project = Project.objects.create(
            vendor_id=str(self.other_vendor.id),
            vendor_name=self.other_vendor.username,
            tech_type="ICS",
            region="Butha-Buthe",
            district="Butha-Buthe",
            status=ProjectStatus.INSTALLATION,
            target_installations=5,
            energy_output=20,
            uptime=95,
            progress=0,
        )

        self.client.force_authenticate(self.doe)
        response = self.client.get("/api/kpi/portfolio")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["scope_label"], "Regional Portfolio - Maseru")
        self.assertEqual(response.data["total_projects"], 1)
        self.assertEqual(response.data["projects"][0]["project_id"], str(self.project.id))
        self.assertNotEqual(response.data["projects"][0]["project_id"], str(other_project.id))

    def test_doe_map_endpoint_is_scoped_to_region(self):
        other_project = Project.objects.create(
            vendor_id=str(self.other_vendor.id),
            vendor_name=self.other_vendor.username,
            tech_type="ICS",
            region="Butha-Buthe",
            district="Butha-Buthe",
            status=ProjectStatus.INSTALLATION,
            target_installations=5,
            energy_output=20,
            uptime=95,
            progress=0,
        )
        other_report = InstallationReport.objects.create(
            project=other_project,
            vendor=self.other_vendor,
            gps_lat=-28.766,
            gps_lng=28.249,
            serial_number="SER-OTHER-1",
            beneficiary_id="BEN-OTHER-1",
            beneficiary_name="Outside Region",
            household_type="standard",
            installation_date="2025-01-18",
            status=InstallationStatus.SUBMITTED,
            gis_status="yellow",
        )
        VerificationTask.objects.create(
            report=other_report,
            vendor_lat=other_report.gps_lat,
            vendor_lng=other_report.gps_lng,
            status=VerificationStatus.PENDING,
        )

        self.client.force_authenticate(self.doe)
        response = self.client.get("/api/map/installations")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["data"]["summary"]["total"], 1)
        districts = {item["district"] for item in response.data["data"]["installations"]}
        project_ids = {item["project_id"] for item in response.data["data"]["installations"]}
        self.assertIn("Maseru", districts)
        self.assertNotIn("Butha-Buthe", districts)
        self.assertIn(self.project.id, project_ids)
        self.assertNotIn(other_project.id, project_ids)


class ProjectProspectTargetSyncTests(APITestCase):
    @patch("rbf.projects.integrations.SyncToProspectJob.dispatch_async")
    def test_queue_project_targets_sync_uses_assignment_metrics_and_values(self, dispatch_async):
        project = Project.objects.create(
            vendor_id="vendor-1",
            vendor_name="Vendor",
            tech_type="SHS",
            technology_type="SHS",
            region="Maseru",
            district="Maseru",
            district_zone="Maseru",
            status=ProjectStatus.INSTALLATION,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=365),
            target_installations=500,
            installation_target=500,
            target_female_pct=50,
            female_target_pct=50,
            target_low_income_pct=60,
            low_income_target_pct=60,
            energy_output=20000,
            energy_output_target_kwh=20000,
        )

        queue_project_targets_sync(str(project.id))

        dispatch_async.assert_called_once()
        method_name, payload = dispatch_async.call_args[0]
        self.assertEqual(method_name, "pushTarget")
        self.assertEqual(payload[0]["metric"], "installation_target")
        self.assertEqual(payload[0]["target_value"], 500)
        self.assertEqual(payload[0]["country"], "LS")
        self.assertEqual(payload[0]["effective_date"], project.start_date.isoformat())
        self.assertEqual(payload[0]["program_end_date"], project.end_date.isoformat())
        self.assertNotIn("external_id", payload[0])
        self.assertEqual(payload[1]["metric"], "female_beneficiary_target")
        self.assertEqual(payload[1]["target_value"], 50)
        self.assertEqual(payload[1]["effective_date"], project.start_date.isoformat())
        self.assertEqual(payload[1]["program_end_date"], project.end_date.isoformat())
        self.assertEqual(payload[2]["metric"], "monthly_energy_output_kwh")
        self.assertEqual(payload[2]["target_value"], 20000)
        self.assertEqual(payload[2]["effective_date"], project.start_date.isoformat())
        self.assertEqual(payload[2]["program_end_date"], project.end_date.isoformat())

    @patch.object(ProspectService, "_post_records")
    def test_push_agent_accepts_raw_record_array(self, post_records):
        service = ProspectService(
            base_url="http://prospect.test/api",
            write_token="write-token",
            write_tokens={"pushAgent": "agents-write-token"},
            read_token="read-token",
            timeout=5,
            batch_size=100,
        )

        service.pushAgent(
            [{
                "external_id": "9",
                "agent_type": "sales_agent",
                "gender": "Male",
                "location_area_1": "Maseru",
            }]
        )

        post_records.assert_called_once()
        method_name, endpoint, records = post_records.call_args[0]
        self.assertEqual(method_name, "pushAgent")
        self.assertEqual(endpoint, "/v1/in/agents")
        self.assertEqual(records[0]["gender"], "Male")

    def test_prospect_service_uses_method_specific_write_tokens(self):
        service = ProspectService(
            base_url="http://prospect.test/api",
            write_token="fallback-write-token",
            write_tokens={
                "pushAgent": "agents-write-token",
                "pushCustomer": "customers-write-token",
                "pushInstallation": "installations-write-token",
                "pushInstallationTimeSeries": "installations-ts-write-token",
                "pushTarget": "targets-write-token",
                "pushReport": "reports-write-token",
            },
            read_token="read-token",
            timeout=5,
            batch_size=100,
        )

        self.assertEqual(service._token_for_write("pushAgent"), "agents-write-token")
        self.assertEqual(service._token_for_write("pushCustomer"), "customers-write-token")
        self.assertEqual(service._token_for_write("pushInstallation"), "installations-write-token")
        self.assertEqual(service._token_for_write("pushInstallationTimeSeries"), "installations-ts-write-token")
        self.assertEqual(service._token_for_write("pushTarget"), "targets-write-token")
        self.assertEqual(service._token_for_write("pushReport"), "reports-write-token")

    def test_normalize_prospect_gender_maps_expected_values(self):
        from .integrations import normalize_prospect_gender

        self.assertEqual(normalize_prospect_gender("Male"), "M")
        self.assertEqual(normalize_prospect_gender("Female"), "F")
        self.assertEqual(normalize_prospect_gender("Other"), "O")
        self.assertEqual(normalize_prospect_gender("non-binary"), "O")

    def test_derive_installation_gender_maps_expected_values(self):
        from .integrations import derive_installation_gender

        self.assertEqual(derive_installation_gender("female_headed"), "F")
        self.assertEqual(derive_installation_gender("standard"), "M")
        self.assertEqual(derive_installation_gender(""), "M")

    @patch("rbf.projects.integrations.SyncToProspectJob.dispatch_async")
    def test_queue_project_agent_sync_prefers_vendor_location_fields(self, dispatch_async):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="agent_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            gender="Female",
            region="Maseru",
            verification_zone="Maseru Urban",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            technology_type="SHS",
            region="Fallback Region",
            district="Fallback District",
            district_zone="Fallback Zone",
            status=ProjectStatus.ACTIVE,
        )

        from .integrations import queue_project_agent_sync
        queue_project_agent_sync(str(project.id))

        dispatch_async.assert_called_once()
        method_name, payload = dispatch_async.call_args[0]
        self.assertEqual(method_name, "pushAgent")
        self.assertEqual(payload["data"][0]["external_id"], str(vendor.id))
        self.assertEqual(payload["data"][0]["gender"], "F")
        self.assertEqual(payload["data"][0]["location_area_1"], "Maseru Urban")
        self.assertEqual(dispatch_async.call_args.kwargs["record_id"], vendor.id)
        self.assertEqual(dispatch_async.call_args.kwargs["record_type"], "user")

    @patch("rbf.projects.integrations.SyncToProspectJob.dispatch_async")
    def test_queue_project_targets_sync_uses_prospect_required_dates_without_external_id(self, dispatch_async):
        project = Project.objects.create(
            vendor_id="vendor-2",
            vendor_name="Vendor",
            tech_type="SHS",
            technology_type="SHS",
            region="Maseru",
            district="Maseru",
            district_zone="Maseru",
            status=ProjectStatus.ACTIVE,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=365),
            target_installations=100,
            installation_target=100,
            target_female_pct=50,
            female_target_pct=50,
            energy_output=5000,
            energy_output_target_kwh=5000,
        )

        queue_project_targets_sync(str(project.id))

        _, payload = dispatch_async.call_args[0]
        self.assertEqual(payload[0]["unit_of_measurement"], "number")
        self.assertEqual(payload[0]["effective_date"], project.start_date.isoformat())
        self.assertEqual(payload[0]["program_end_date"], project.end_date.isoformat())
        self.assertNotIn("external_id", payload[0])

    @patch("rbf.projects.integrations.SyncToProspectJob.dispatch_async")
    def test_queue_installation_sync_uses_project_setup_device_details(self, dispatch_async):
        from .integrations import _hash_value

        User = get_user_model()
        vendor = User.objects.create_user(
            username="prospect_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.ACTIVE,
        )
        ProjectSetup.objects.create(
            project=project,
            vendor=vendor,
            device_brand="Toshiba",
            device_model="TN-001",
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.1511,
            gps_lng=27.7425,
            serial_number="001",
            beneficiary_id="BEN-001",
            household_type="female_headed",
        )

        queue_installation_sync(str(report.id))

        self.assertEqual(dispatch_async.call_count, 2)
        first_call = dispatch_async.call_args_list[0].args
        second_call = dispatch_async.call_args_list[1].args
        self.assertEqual(first_call[0], "pushCustomer")
        self.assertEqual(first_call[1]["data"][0]["gender"], "F")
        self.assertEqual(first_call[1]["data"][0]["identification_number"], _hash_value("BEN-001"))
        self.assertEqual(first_call[1]["data"][0]["phone"], "")
        self.assertEqual(second_call[0], "pushInstallation")
        self.assertEqual(second_call[1]["data"][0]["manufacturer"], "Toshiba")
        self.assertEqual(second_call[1]["data"][0]["model"], "TN-001")
        self.assertEqual(second_call[1]["data"][0]["device_category"], "solar_home_system")
        self.assertEqual(second_call[1]["data"][0]["usage_category"], "household")

    @patch("rbf.projects.integrations.SyncToProspectJob.dispatch_async")
    def test_queue_installation_sync_normalizes_legacy_project_technology_for_device_category(self, dispatch_async):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="legacy_tech_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name=vendor.username,
            tech_type="Mini-grid",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.ACTIVE,
        )
        report = InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.1511,
            gps_lng=27.7425,
            serial_number="MG-001",
            beneficiary_id="BEN-LEGACY-001",
            household_type="standard",
        )

        queue_installation_sync(str(report.id), include_customer=False, include_installation=True)

        dispatch_async.assert_called_once()
        method_name, payload = dispatch_async.call_args[0]
        self.assertEqual(method_name, "pushInstallation")
        self.assertEqual(payload["data"][0]["device_category"], "meter")


class ProspectSyncLogViewSetTests(SimpleTestCase):
    @override_settings(
        PROSPECT_BASE_URL="https://prospect.example.test/api",
        PROSPECT_READ_TOKEN="read-token",
        PROSPECT_WRITE_TOKEN="write-token",
    )
    def test_check_connection_returns_configured_status(self):
        from rbf.projects.views import ProspectSyncLogViewSet
        from rbf.users.models import UserRole

        request = APIRequestFactory().post("/api/projects/prospect-sync-logs/check-connection/", {}, format="json")
        user = SimpleNamespace(role=UserRole.ADMIN, is_active=True, is_authenticated=True)
        force_authenticate(request, user=user)

        response = ProspectSyncLogViewSet.as_view({"post": "check_connection"})(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "read_token_ok": True,
                "write_token_ok": True,
                "base_url": "https://prospect.example.test/api",
            },
        )

    @override_settings(
        PROSPECT_BASE_URL="https://prospect.example.test/api",
        PROSPECT_API_SECRET="shared-read-secret",
        PROSPECT_READ_TOKEN="",
        PROSPECT_WRITE_TOKEN="",
        PROSPECT_TOKEN_IN_AGENTS="agents-secret",
        PROSPECT_TOKEN_IN_TARGETS="targets-secret",
        PROSPECT_TOKEN_IN_CUSTOMERS="customers-secret",
        PROSPECT_TOKEN_IN_INSTALLATIONS="installations-secret",
        PROSPECT_TOKEN_IN_INSTALLATIONS_TS="installations-ts-secret",
        PROSPECT_TOKEN_IN_REPORTS="reports-secret",
        PROSPECT_TOKEN_OUT_INSTALLATIONS="shared-read-secret",
        PROSPECT_TOKEN_OUT_TARGETS="shared-read-secret",
    )
    def test_check_connection_accepts_per_endpoint_write_tokens_and_shared_read_secret(self):
        from rbf.projects.views import ProspectSyncLogViewSet
        from rbf.users.models import UserRole

        request = APIRequestFactory().post("/api/projects/prospect-sync-logs/check-connection/", {}, format="json")
        user = SimpleNamespace(role=UserRole.ADMIN, is_active=True, is_authenticated=True)
        force_authenticate(request, user=user)

        response = ProspectSyncLogViewSet.as_view({"post": "check_connection"})(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["read_token_ok"], True)
        self.assertEqual(response.data["write_token_ok"], True)


class ProspectServiceConfigurationTests(SimpleTestCase):
    def test_prospect_service_uses_method_specific_read_tokens(self):
        service = ProspectService(
            base_url="http://prospect.test/api",
            write_token="",
            write_tokens={},
            read_token="fallback-read-token",
            read_tokens={
                "getInstallations": "installations-read-token",
                "getTargets": "targets-read-token",
            },
            timeout=5,
            batch_size=100,
        )

        self.assertEqual(service._token_for_read("getInstallations"), "installations-read-token")
        self.assertEqual(service._token_for_read("getTargets"), "targets-read-token")
