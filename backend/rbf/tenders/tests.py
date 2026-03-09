from django.test import override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Tender, TenderStatus


class TenderApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            username="tender_admin",
            password="securePass123",
            role="Digital Admin",
            status="Active",
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

    def test_tender_lifecycle_verify_publish_award(self):
        self.client.force_authenticate(self.admin_user)
        tender = Tender.objects.create(
            reference_number="REF-100200",
            name="Lifecycle Tender",
            department="DoE",
            category="SHS",
            status=TenderStatus.DRAFT,
            deadline=timezone.now(),
            is_verified=False,
        )

        verify_response = self.client.post(f"/api/tenders/{tender.id}/verify/", {}, format="json")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.data["is_verified"])

        publish_response = self.client.post(f"/api/tenders/{tender.id}/publish/", {}, format="json")
        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(publish_response.data["status"], TenderStatus.PUBLISHED)

        award_response = self.client.post(
            f"/api/tenders/{tender.id}/award/",
            {"awarded_vendor_id": "vendor_approved", "awarded_vendor_name": "Approved Vendor"},
            format="json",
        )
        self.assertEqual(award_response.status_code, status.HTTP_200_OK)
        self.assertEqual(award_response.data["status"], TenderStatus.AWARDED)
