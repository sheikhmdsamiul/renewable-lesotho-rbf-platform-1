from rest_framework import status
from rest_framework.test import APITestCase

from rbf.users.models import User, UserRole

from .models import Notification, NotificationChannel, NotificationStatus
from .services import NotificationService


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.rmt_user = User.objects.create_user(
            username="rmt_notify",
            password="testpass",
            email="rmt-notify@example.com",
            full_name="RMT Official",
            role=UserRole.RBF_OFFICIAL,
        )
        self.vendor = User.objects.create_user(
            username="vendor_notify",
            password="testpass",
            email="vendor-notify@example.com",
            full_name="Vendor One",
            role=UserRole.VENDOR,
        )

    def _create(self, recipient, title="Tender published", status=NotificationStatus.SENT, **kwargs):
        return Notification.objects.create(
            recipient_id=str(recipient.id),
            recipient_name=recipient.full_name,
            type=NotificationChannel.IN_APP,
            event="TenderPublished",
            title=title,
            body="A new tender is now live.",
            status=status,
            **kwargs,
        )

    def test_unauthenticated_access_is_denied(self):
        response = self.client.get("/api/notifications/")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_list_is_scoped_to_own_notifications(self):
        self._create(self.vendor, title="Vendor notice")
        self._create(self.rmt_user, title="RMT notice")
        self._create(self.rmt_user, title="RMT notice two")

        self.client.force_authenticate(self.vendor)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "Vendor notice")

    def test_staff_can_see_all_notifications(self):
        self._create(self.vendor)
        self._create(self.rmt_user)

        self.client.force_authenticate(self.rmt_user)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_non_staff_cannot_create_notifications(self):
        self.client.force_authenticate(self.vendor)
        payload = {
            "recipient_id": str(self.vendor.id),
            "recipient_name": "Vendor One",
            "type": "SMS",
            "event": "MilestoneFlagged",
            "title": "Action required",
            "body": "A milestone needs your review.",
            "status": "Sent",
        }
        response = self.client.post("/api/notifications/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_notification(self):
        self.client.force_authenticate(self.rmt_user)
        payload = {
            "recipient_id": str(self.vendor.id),
            "recipient_name": "Vendor One",
            "type": "In-App",
            "event": "TenderPublished",
            "title": "Tender published",
            "body": "A new tender is now live.",
            "status": "Sent",
        }
        response = self.client.post("/api/notifications/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "In-App")

    def test_non_staff_cannot_modify_notifications(self):
        note = self._create(self.vendor)
        self.client.force_authenticate(self.vendor)
        response = self.client.patch(f"/api/notifications/{note.id}/", {"title": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unread_count(self):
        self._create(self.vendor)
        self._create(self.vendor, title="Already read", status=NotificationStatus.READ)

        self.client.force_authenticate(self.vendor)
        response = self.client.get("/api/notifications/unread_count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_mark_read_own_notification(self):
        note = self._create(self.vendor)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(f"/api/notifications/{note.id}/mark_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], NotificationStatus.READ)
        note.refresh_from_db()
        self.assertEqual(note.status, NotificationStatus.READ)

    def test_mark_read_other_users_notification_is_hidden(self):
        note = self._create(self.rmt_user)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(f"/api/notifications/{note.id}/mark_read/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_all_read(self):
        self._create(self.vendor)
        self._create(self.vendor, title="Second unread")
        self._create(self.rmt_user, title="Other user unread")

        self.client.force_authenticate(self.vendor)
        response = self.client.post("/api/notifications/mark_all_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 2)

    def test_duplicate_event_for_same_entity_does_not_crash(self):
        first = NotificationService.send(
            recipient_id=str(self.rmt_user.id),
            title="New Bid Submitted",
            body="Bid resubmission duplicate check",
            module="tenders",
            record_id=42,
        )
        self.assertIsNotNone(first)
        second = NotificationService.send(
            recipient_id=str(self.rmt_user.id),
            title="New Bid Submitted",
            body="Bid resubmission duplicate check",
            module="tenders",
            record_id=42,
        )
        self.assertIsNone(second)
        self.assertEqual(
            Notification.objects.filter(
                recipient_id=str(self.rmt_user.id),
                event="tenders_info",
                linked_entity_id="42",
            ).count(),
            1,
            "Re-notifying the same entity must not create a duplicate row or raise.",
        )
