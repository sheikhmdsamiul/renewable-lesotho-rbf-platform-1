from rest_framework import status
from rest_framework.test import APITestCase

from .models import Notification, NotificationChannel, NotificationStatus


class NotificationApiTests(APITestCase):
    def test_notifications_list_endpoint(self):
        Notification.objects.create(
            recipient_id="USR-001",
            recipient_name="Admin User",
            type=NotificationChannel.IN_APP,
            event="TenderPublished",
            title="Tender published",
            body="A new tender is now live.",
            status=NotificationStatus.SENT,
        )

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["recipient_id"], "USR-001")

    def test_create_notification_with_sms_channel(self):
        payload = {
            "recipient_id": "USR-002",
            "recipient_name": "Field Verifier",
            "type": "SMS",
            "event": "MilestoneFlagged",
            "title": "Action required",
            "body": "A milestone needs your review.",
            "status": "Sent",
            "linked_entity_id": "PRJ-001",
        }

        response = self.client.post("/api/notifications/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "SMS")
