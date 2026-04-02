from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from .models import (
    InstallationReport,
    InstallationStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
    ProjectUpdate,
    VerificationStatus,
    VerificationTask,
)


class ProjectApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="project_admin",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )

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

    def test_projects_list_endpoint(self):
        Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["vendor_id"], "V-001")

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

    def test_project_planning_update_creates_project_update_entry(self):
        project = Project.objects.create(**self._project_payload())
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"deployment_team_roster": "Team A, Team B"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ProjectUpdate.objects.filter(
                project=project,
                title="Deployment Plan Updated",
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
            username="field_verifier_user",
            password="securePass123",
            role="Field Verifier",
            status="Active",
        )
        approver = User.objects.create_user(
            username="rbf_approver",
            password="securePass123",
            role="RBF Management Team",
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
        self.assertEqual(create_response.data["status"], "Pending")

        self.client.force_authenticate(verifier)
        verify_response = self.client.post(f"/api/projects/claims/{claim_id}/verify/", {}, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["status"], "Verified")

        self.client.force_authenticate(approver)
        approve_response = self.client.post(f"/api/projects/claims/{claim_id}/approve/", {}, format="json")
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], "Approved")

        pay_response = self.client.post(
            f"/api/projects/claims/{claim_id}/pay/",
            {"payment_reference": "PMT-TEST-001"},
            format="json",
        )
        self.assertEqual(pay_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pay_response.data["status"], "Paid")
        self.assertEqual(pay_response.data["payment_reference"], "PMT-TEST-001")
        self.assertFalse(pay_response.data["payment_locked"])

        disbursement_list = self.client.get("/api/projects/disbursements/")
        self.assertEqual(disbursement_list.status_code, status.HTTP_200_OK)
        self.assertEqual(disbursement_list.data["count"], 1)

        audit_logs = self.client.get("/api/projects/audit-logs/")
        self.assertEqual(audit_logs.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(audit_logs.data["count"], 3)

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
            status=PaymentClaimStatus.APPROVED,
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

    def test_project_steering_committee_can_pay_claims_and_flag_project_issues(self):
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
            status=PaymentClaimStatus.APPROVED,
            declaration_accepted=True,
        )

        self.client.force_authenticate(psc_user)
        pay_response = self.client.post(
            f"/api/projects/claims/{claim.id}/pay/",
            {"payment_reference": "PMT-PSC-001"},
            format="json",
        )
        self.assertEqual(pay_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pay_response.data["status"], "Paid")

        audit_logs = self.client.get("/api/projects/audit-logs/")
        self.assertEqual(audit_logs.status_code, status.HTTP_200_OK)

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
