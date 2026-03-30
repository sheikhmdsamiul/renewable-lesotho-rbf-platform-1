from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from .models import Project, ProjectStatus, ProjectUpdate


class ProjectApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="project_admin",
            password="securePass123",
            role="Digital Admin",
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
            role="RBF Official",
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

        disbursement_list = self.client.get("/api/projects/disbursements/")
        self.assertEqual(disbursement_list.status_code, status.HTTP_200_OK)
        self.assertEqual(disbursement_list.data["count"], 1)

        audit_logs = self.client.get("/api/projects/audit-logs/")
        self.assertEqual(audit_logs.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(audit_logs.data["count"], 3)
