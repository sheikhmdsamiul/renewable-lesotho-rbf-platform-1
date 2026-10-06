"""DoE officer portal: what a DoE officer may read, create and change."""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.users.models import (
    BlacklistRecommendation,
    BlacklistRecommendationStatus,
    User,
    VendorBlacklistCase,
)
from .models import KpiReview, Project, ProjectDocument, ProjectUpdate, SiteMonitoringVisit

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class DoeOfficerPortalTests(APITestCase):
    def setUp(self):
        self.doe = User.objects.create_user(
            username="doe_portal", password="securePass123", role="DoE Officer", status="Active", region="Maseru",
        )
        self.other_doe = User.objects.create_user(
            username="doe_portal_other", password="securePass123", role="DoE Officer", status="Active", region="Maseru",
        )
        self.rmt = User.objects.create_user(
            username="rmt_portal", password="securePass123", role="RBF Management Team", status="Active",
        )
        self.vendor = User.objects.create_user(
            username="vendor_portal", password="securePass123", role="Vendor", status="Active", region="Maseru",
        )
        self.far_vendor = User.objects.create_user(
            username="vendor_far", password="securePass123", role="Vendor", status="Active", region="Mokhotlong",
        )
        self.project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name=self.vendor.username, tech_type="SHS",
            region="Maseru", district="Maseru", project_reference="PRJ-DOE-1",
        )
        self.far_project = Project.objects.create(
            vendor_id=str(self.far_vendor.id), vendor_name=self.far_vendor.username, tech_type="SHS",
            region="Mokhotlong", district="Mokhotlong", project_reference="PRJ-DOE-2",
        )

    # --- Regional Projects: read + limited update -------------------------------------------

    def test_doe_cannot_edit_projects_or_milestones(self):
        self.client.force_authenticate(self.doe)
        response = self.client.patch(f"/api/projects/{self.project.id}/", {"progress": 90}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(
            "/api/projects/milestones/", {"project": self.project.id, "name": "M9", "percentage": 10}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doe_notes_are_region_scoped_and_owner_edited(self):
        self.client.force_authenticate(self.doe)
        created = self.client.post(
            "/api/projects/updates/", {"project": self.project.id, "title": "Regional note", "body": "Site access road flooded."},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        outside = self.client.post(
            "/api/projects/updates/", {"project": self.far_project.id, "body": "Not my region."}, format="json",
        )
        self.assertEqual(outside.status_code, status.HTTP_403_FORBIDDEN)

        ProjectUpdate.objects.create(project=self.far_project, author=self.rmt, body="Elsewhere")
        listed = self.client.get("/api/projects/updates/")
        self.assertEqual({row["project"] for row in listed.data["results"]}, {self.project.id})

        rmt_note = ProjectUpdate.objects.create(project=self.project, author=self.rmt, body="RMT note")
        self.assertEqual(
            self.client.patch(f"/api/projects/updates/{rmt_note.id}/", {"body": "edited"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(f"/api/projects/updates/{rmt_note.id}/").status_code, status.HTTP_403_FORBIDDEN)
        own_id = created.data["id"]
        self.assertEqual(
            self.client.patch(f"/api/projects/updates/{own_id}/", {"body": "Road now passable."}, format="json").status_code,
            status.HTTP_200_OK,
        )

    def test_doe_can_upload_regional_documents_only(self):
        self.client.force_authenticate(self.doe)
        upload = SimpleUploadedFile("site.png", PNG_BYTES, content_type="image/png")
        response = self.client.post(
            "/api/projects/documents/", {"project": self.project.id, "title": "Site visit photo", "file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ProjectDocument.objects.filter(project=self.project, uploaded_by=self.doe).exists())
        upload = SimpleUploadedFile("site.png", PNG_BYTES, content_type="image/png")
        response = self.client.post(
            "/api/projects/documents/", {"project": self.far_project.id, "file": upload}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doe_project_kpis_are_region_scoped(self):
        self.client.force_authenticate(self.doe)
        self.assertEqual(self.client.get(f"/api/kpi/project/{self.far_project.id}").status_code, status.HTTP_403_FORBIDDEN)

    # --- Regional Monitoring: create / read / update ---------------------------------------

    def test_site_monitoring_visit_lifecycle(self):
        self.client.force_authenticate(self.doe)
        response = self.client.post(
            "/api/projects/monitoring-visits/",
            {
                "project": self.project.id,
                "visit_date": "2026-09-15",
                "system_working": "true",
                "observations": "Panels installed and charging; household using lights.",
                "follow_up_status": "open",
                "follow_up_action": "Vendor to replace cracked controller casing.",
                "photos": [SimpleUploadedFile("p.png", PNG_BYTES, content_type="image/png")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data["photos"]), 1)
        visit_id = response.data["id"]

        updated = self.client.patch(
            f"/api/projects/monitoring-visits/{visit_id}/", {"follow_up_status": "closed"}, format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["follow_up_status"], "closed")
        self.assertEqual(
            self.client.delete(f"/api/projects/monitoring-visits/{visit_id}/").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

        outside = self.client.post(
            "/api/projects/monitoring-visits/",
            {"project": self.far_project.id, "visit_date": "2026-09-15", "observations": "Outside my region entirely."},
            format="json",
        )
        self.assertEqual(outside.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.other_doe)
        self.assertEqual(
            self.client.patch(f"/api/projects/monitoring-visits/{visit_id}/", {"follow_up_status": "open"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(self.rmt)
        self.assertEqual(self.client.get("/api/projects/monitoring-visits/").data["count"], 1)
        self.assertEqual(
            self.client.post(
                "/api/projects/monitoring-visits/",
                {"project": self.project.id, "visit_date": "2026-09-15", "observations": "RMT cannot log DoE visits."},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # --- KPI Review: read / create review / update review ----------------------------------

    def test_kpi_review_create_update_and_one_per_month(self):
        self.client.force_authenticate(self.doe)
        payload = {"project": self.project.id, "review_period": "2026-09", "rating": "needs_attention",
                   "summary": "Uptime dipped below 95% in two villages."}
        created = self.client.post("/api/projects/kpi-reviews/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        duplicate = self.client.post("/api/projects/kpi-reviews/", payload, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        updated = self.client.patch(
            f"/api/projects/kpi-reviews/{created.data['id']}/", {"rating": "on_track"}, format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(KpiReview.objects.get().rating, "on_track")
        bad_period = self.client.post("/api/projects/kpi-reviews/", {**payload, "review_period": "Sept"}, format="json")
        self.assertEqual(bad_period.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Blacklisting: read + recommend, no direct changes ---------------------------------

    def test_doe_recommends_and_rmt_accepts_into_a_case(self):
        self.client.force_authenticate(self.doe)
        far = self.client.post(
            "/api/users/blacklisting-recommendations/",
            {"vendor": self.far_vendor.id, "reason": "Integrity Breach", "justification": "x" * 40},
            format="multipart",
        )
        self.assertEqual(far.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(
            "/api/users/blacklisting-recommendations/",
            {
                "vendor": self.vendor.id,
                "project": self.project.id,
                "reason": "Fraudulent Reporting",
                "justification": "Installations reported as complete were not found on site during visits.",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        rec_id = response.data["id"]
        self.assertEqual(
            self.client.post(f"/api/users/blacklisting-recommendations/{rec_id}/accept/", {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(self.rmt)
        accepted = self.client.post(
            f"/api/users/blacklisting-recommendations/{rec_id}/accept/", {"response_notes": "Opening a case."}, format="json",
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        rec = BlacklistRecommendation.objects.get(id=rec_id)
        self.assertEqual(rec.status, BlacklistRecommendationStatus.ACCEPTED)
        self.assertEqual(rec.linked_case.vendor, self.vendor)
        self.assertEqual(rec.linked_case.initiated_by, self.rmt)

    def test_doe_has_no_case_powers_and_cases_cannot_be_edited_directly(self):
        case = VendorBlacklistCase.objects.create(vendor=self.vendor, reason="Integrity Breach", initiated_by=self.rmt)
        self.client.force_authenticate(self.doe)
        self.assertEqual(self.client.get(f"/api/users/blacklisting-cases/{case.id}/").status_code, status.HTTP_200_OK)
        for action in ("review", "confirm", "reject", "reinstate"):
            response = self.client.post(f"/api/users/blacklisting-cases/{case.id}/{action}/", {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, action)
        self.assertEqual(
            self.client.delete(f"/api/users/blacklisting-cases/{case.id}/").status_code, status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(f"/api/users/blacklisting-cases/{case.id}/", {"status": "Rejected"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_vendors_running_regional_projects_count_as_regional(self):
        travelling_vendor = User.objects.create_user(
            username="vendor_travelling", password="securePass123", role="Vendor", status="Active", region="Leribe",
        )
        Project.objects.create(
            vendor_id=str(travelling_vendor.id), vendor_name="Travelling Solar", tech_type="SHS",
            region="Leribe", district="Maseru", project_reference="PRJ-DOE-3",
        )
        self.client.force_authenticate(self.doe)
        directory = self.client.get("/api/users/vendor_directory/")
        usernames = {row["username"] for row in directory.data["results"]}
        self.assertIn("vendor_travelling", usernames)
        self.assertNotIn("vendor_far", usernames)
        response = self.client.post(
            "/api/users/blacklisting-recommendations/",
            {"vendor": travelling_vendor.id, "reason": "Integrity Breach", "justification": "y" * 40},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
