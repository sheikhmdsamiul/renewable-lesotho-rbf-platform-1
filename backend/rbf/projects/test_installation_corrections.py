import shutil
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.notifications.models import Notification

from .gis import GpsValidator
from .models import (
    INSTALLATION_MAX_RESUBMISSIONS,
    FieldVerification,
    InstallationReport,
    InstallationStatus,
    Project,
    ProjectSetup,
    ProjectStatus,
    VerificationStatus,
)

LESOTHO_SQUARE = """
{"type": "Feature", "properties": {"ISO_A2": "LS"},
 "geometry": {"type": "Polygon", "coordinates": [[[27.0, -30.5], [29.5, -30.5], [29.5, -28.0], [27.0, -28.0], [27.0, -30.5]]]}}
"""


class InstallationCorrectionTests(APITestCase):
    """Duplicate device / household blocking at submission, and the vendor correction loop
    for flagged installations."""

    def setUp(self):
        User = get_user_model()
        self.geojson_root = settings.BASE_DIR / "tmp_test_geojson" / str(uuid.uuid4())
        (self.geojson_root / "geojson").mkdir(parents=True, exist_ok=True)
        path = self.geojson_root / "geojson" / "lesotho.geojson"
        path.write_text(LESOTHO_SQUARE.strip(), encoding="utf-8")
        self.settings_override = override_settings(LESOTHO_BOUNDARY_PATH=str(path.relative_to(settings.BASE_DIR)))
        self.settings_override.enable()
        GpsValidator._feature_cache = None

        self.vendor = User.objects.create_user(username="ic_vendor", password="securePass123", role="Vendor", status="Active")
        self.other_vendor = User.objects.create_user(username="ic_vendor2", password="securePass123", role="Vendor", status="Active")
        self.verifier = User.objects.create_user(
            username="ic_verifier", password="securePass123", role="Field Verifier", status="Active", verification_zone="Maseru",
        )
        self.project = self._project(self.vendor, "PRJ-IC-1")
        self.other_project = self._project(self.other_vendor, "PRJ-IC-2")
        cache.clear()

    def tearDown(self):
        GpsValidator._feature_cache = None
        self.settings_override.disable()
        shutil.rmtree(self.geojson_root, ignore_errors=True)
        super().tearDown()

    def _project(self, vendor, reference):
        project = Project.objects.create(
            vendor_id=str(vendor.id), vendor_name=vendor.username, tech_type="SHS", region="Maseru",
            district="Maseru", status=ProjectStatus.ACTIVE, project_reference=reference, target_installations=10,
        )
        ProjectSetup.objects.create(
            project=project, vendor=vendor, site_status="ready",
            work_schedule_start=timezone.now().date(), work_schedule_end=timezone.now().date() + timedelta(days=10),
            device_brand="SolarCo", device_model="SHS-100", tech_tier=2, manual_verification_confirmed=True,
            setup_completed_at=timezone.now(),
        )
        return project

    def _submit(self, vendor, project, serial, beneficiary, lat=-29.31, lng=27.48):
        self.client.force_authenticate(vendor)
        return self.client.post(
            "/api/projects/installations/",
            {"project": project.id, "gps_lat": lat, "gps_lng": lng, "serial_number": serial, "beneficiary_id": beneficiary},
        )

    def _flag(self, report_id, reason="Serial plate on the panel does not match the report."):
        task = InstallationReport.objects.get(id=report_id).verification_task
        self.client.force_authenticate(self.verifier)
        response = self.client.post(
            f"/api/projects/verification-tasks/{task.id}/verify/",
            {
                "verifier_lat": -29.31, "verifier_lng": 27.48, "verification_status": "flagged", "flag_reason": reason,
                "beneficiary_present": "true", "system_working": "true", "observation_notes": "Checked on site.",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return task

    def test_duplicate_serial_or_beneficiary_is_rejected_across_projects(self):
        self.assertEqual(self._submit(self.vendor, self.project, "SN-001", "BEN-001").status_code, status.HTTP_201_CREATED)

        response = self._submit(self.other_vendor, self.other_project, "sn-001 ", "BEN-999", lat=-29.40)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("serial_number", response.data["errors"])

        response = self._submit(self.vendor, self.project, "SN-002", "ben-001", lat=-29.40)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("beneficiary_id", response.data["errors"])
        self.assertEqual(InstallationReport.objects.count(), 1)

        # A terminated installation no longer reserves its serial number.
        InstallationReport.objects.update(status=InstallationStatus.TERMINATED)
        self.assertEqual(self._submit(self.vendor, self.project, "SN-001", "BEN-001").status_code, status.HTTP_201_CREATED)

    def test_vendor_edit_cannot_take_another_installations_serial(self):
        self._submit(self.vendor, self.project, "SN-A", "BEN-A")
        report_id = self._submit(self.vendor, self.project, "SN-B", "BEN-B", lat=-29.40).data["data"]["id"]
        response = self.client.patch(f"/api/projects/installations/{report_id}/", {"serial_number": "SN-A"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(InstallationReport.objects.get(id=report_id).serial_number, "SN-B")

    def test_flagged_installation_can_be_corrected_and_resubmitted(self):
        report_id = self._submit(self.vendor, self.project, "SN-WRONG", "BEN-1").data["data"]["id"]
        task = self._flag(report_id)

        notice = Notification.objects.get(recipient_id=str(self.vendor.id), event="installation_verification_vendor")
        self.assertIn("Serial plate on the panel does not match", notice.body)
        self.assertIn("resubmission(s) left", notice.body)

        self.client.force_authenticate(self.vendor)
        data = self.client.get(f"/api/projects/installations/{report_id}/").data
        self.assertEqual(data["status"], InstallationStatus.FLAGGED)
        self.assertTrue(data["can_resubmit"])
        self.assertIn("Serial plate", data["latest_flag_reason"])

        url = f"/api/projects/installations/{report_id}/resubmit/"
        self.assertEqual(self.client.post(url, {"correction_note": "short"}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.post(url, {"correction_note": "Corrected the serial.", "gps_lat": -10, "gps_lng": 10}).status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
        response = self.client.post(url, {"correction_note": "Corrected the serial to match the plate.", "serial_number": "SN-RIGHT"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["data"]["status"], InstallationStatus.SUBMITTED)
        self.assertEqual(response.data["data"]["serial_number"], "SN-RIGHT")
        self.assertEqual(response.data["data"]["resubmission_count"], 1)

        task.refresh_from_db()
        self.assertEqual(task.status, VerificationStatus.REVERIFICATION_REQUIRED)
        self.assertEqual(task.verification_round, 2)
        self.assertIn("Corrected the serial", task.reverification_reason)
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.verifier.id), event="installation_resubmitted").exists())
        # Round 1 stays on record.
        self.assertEqual(FieldVerification.objects.filter(installation_id=report_id, verification_round=1).count(), 1)

        # Not flagged any more, so it cannot be resubmitted again until the next round flags it.
        self.assertEqual(self.client.post(url, {"correction_note": "Another correction here."}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_resubmission_limit_and_ownership(self):
        report_id = self._submit(self.vendor, self.project, "SN-L", "BEN-L").data["data"]["id"]
        self._flag(report_id)
        url = f"/api/projects/installations/{report_id}/resubmit/"

        self.client.force_authenticate(self.other_vendor)
        self.assertEqual(self.client.post(url, {"correction_note": "Not my installation."}).status_code, status.HTTP_404_NOT_FOUND)

        InstallationReport.objects.filter(id=report_id).update(resubmission_count=INSTALLATION_MAX_RESUBMISSIONS)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(url, {"correction_note": "Trying once more after fixes."})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Contact the RBF Management Team", response.data["detail"])
        self.assertFalse(self.client.get(f"/api/projects/installations/{report_id}/").data["can_resubmit"])

    def test_resubmit_cannot_reuse_another_installations_identity(self):
        self._submit(self.vendor, self.project, "SN-TAKEN", "BEN-TAKEN")
        report_id = self._submit(self.vendor, self.project, "SN-X", "BEN-X", lat=-29.40).data["data"]["id"]
        self._flag(report_id)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(
            f"/api/projects/installations/{report_id}/resubmit/",
            {"correction_note": "Using the other serial number.", "serial_number": "SN-TAKEN"},
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(InstallationReport.objects.get(id=report_id).status, InstallationStatus.FLAGGED)
