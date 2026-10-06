"""Inclusion targets (female-headed, vulnerable, low-income) come from Platform Configuration and
only the Super Admin can set them."""

from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from rbf.tenders.serializers import ProjectAssignmentSerializer, default_inclusion_targets, inclusion_target_errors
from rbf.users.models import PlatformConfiguration, User, inclusion_targets
from .kpi import KpiService
from .models import InstallationReport, InstallationStatus, Project
from .report_engine import ReportContext, build_gender_impact


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, password="securePass123", role=role, status="Active", **extra)


class InclusionTargetTests(APITestCase):
    def setUp(self):
        self.admin = make_user("it_admin", "Platform Administrator (Super Admin)")
        self.rmt = make_user("it_rmt", "RBF Management Team")
        self.vendor = make_user("it_vendor", "Vendor")
        PlatformConfiguration.objects.create(female_target_minimum=55, vulnerable_target_minimum=35, low_income_target_minimum=65)
        self.project = Project.objects.create(vendor_id=str(self.vendor.id), vendor_name="Sun Co", tech_type="SHS", region="Maseru",
                                              district="Maseru", project_reference="PRJ-IT-1", status="active",
                                              female_target_pct=0, target_female_pct=0, vulnerable_target_pct=0, target_vulnerable_pct=0,
                                              low_income_target_pct=0, target_low_income_pct=0)

    def configure(self, user, **values):
        self.client.force_authenticate(user)
        return self.client.patch("/api/users/platform-configuration/", values, format="json")

    def test_only_the_super_admin_changes_the_targets_and_everyone_reads_them(self):
        self.assertEqual(self.configure(self.rmt, female_target_minimum=10).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.configure(self.admin, female_target_minimum=101).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.configure(self.admin, female_target_minimum=60, low_income_target_minimum=70).status_code, status.HTTP_200_OK)
        self.client.force_authenticate(None)
        data = self.client.get("/api/users/platform-configuration/inclusion-targets/").data
        self.assertEqual((data["female_target_minimum"], data["vulnerable_target_minimum"], data["low_income_target_minimum"]), (60, 35, 70))

    def test_bids_and_new_projects_follow_the_configured_minimums(self):
        errors = inclusion_target_errors({"female_target_pct": 54, "vulnerable_target_pct": 35, "low_income_target_pct": 65})
        self.assertEqual(errors, {"female_target_pct": "Female-headed household target must be at least 55%."})
        self.assertEqual(default_inclusion_targets(), {"female_target_pct": 55, "vulnerable_target_pct": 35, "low_income_target_pct": 65})

    def assignment(self, user, **targets):
        data = {"project_duration_months": 12, "installation_target": 10, "technology_type": "SHS", "energy_output_target_kwh": "100.00",
                "district_zones": ["Maseru"], "verification_method": "manual", **targets}
        serializer = ProjectAssignmentSerializer(data=data, context={"user": user})
        with mock.patch.object(ProjectAssignmentSerializer, "validate_technology_type", lambda self, v: v):
            return serializer.is_valid(), serializer

    def test_contract_assignment_targets_are_set_by_the_super_admin_only(self):
        ok, serializer = self.assignment(self.rmt)
        self.assertTrue(ok, serializer.errors)
        self.assertEqual(serializer.validated_data["female_target_pct"], 55)
        ok, serializer = self.assignment(self.rmt, female_target_pct=70)
        self.assertFalse(ok)
        self.assertIn("female_target_pct", serializer.errors)
        ok, serializer = self.assignment(self.admin, female_target_pct=70)
        self.assertTrue(ok, serializer.errors)
        ok, serializer = self.assignment(self.admin, female_target_pct=40)
        self.assertFalse(ok)

    def test_project_targets_can_only_be_edited_by_the_super_admin(self):
        self.client.force_authenticate(self.rmt)
        response = self.client.patch(f"/api/projects/{self.project.id}/", {"female_target_pct": 80}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/projects/{self.project.id}/", {"female_target_pct": 80, "target_female_pct": 80}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_kpis_and_reports_measure_against_the_configured_targets(self):
        self.assertEqual(KpiService.for_project(str(self.project.id))._gender_targets()["female_headed"], 55)
        InstallationReport.objects.create(project=self.project, vendor=self.vendor, gps_lat=-29.3, gps_lng=27.4, serial_number="SN-IT-1",
                                          beneficiary_id="B1", status=InstallationStatus.VERIFIED, household_type="female_headed")
        summary = dict(build_gender_impact(ReportContext(self.admin, {})).summary)
        self.assertIn("(target 55%)", summary["Female-headed"])
        self.assertEqual(inclusion_targets(), {"female": 55, "vulnerable": 35, "low_income": 65})
