from rest_framework import status
from rest_framework.test import APITestCase

from rbf.projects.models import Project, ProjectStatus
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
        self.admin = User.objects.create_user(
            username="admin_notify", password="testpass", full_name="Admin", role=UserRole.ADMIN,
        )
        self.vendor = User.objects.create_user(
            username="vendor_notify",
            password="testpass",
            email="vendor-notify@example.com",
            full_name="Vendor One",
            role=UserRole.VENDOR,
        )

    def _create(self, recipient, title="Tender published", status=NotificationStatus.SENT, event="TenderPublished", **kwargs):
        return Notification.objects.create(
            recipient_id=str(recipient.id),
            recipient_name=recipient.full_name,
            type=NotificationChannel.IN_APP,
            event=event,
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

    def test_staff_inbox_and_counts_are_their_own(self):
        """The RMT used to see (and mark read) every user's notifications."""
        self._create(self.vendor)
        self._create(self.rmt_user)

        self.client.force_authenticate(self.rmt_user)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 1)
        self.assertEqual(self.client.get("/api/notifications/unread_count/").data["count"], 1)
        self.client.post("/api/notifications/mark_all_read/")
        self.assertEqual(Notification.objects.get(recipient_id=str(self.vendor.id)).status, NotificationStatus.SENT)
        # Only the administrator may open the all-users delivery log.
        self.assertEqual(self.client.get("/api/notifications/?scope=all").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/notifications/?scope=all").data["count"], 2)

    def test_notifications_cannot_be_created_or_edited_through_the_api(self):
        note = self._create(self.vendor)
        payload = {"recipient_id": str(self.vendor.id), "type": "In-App", "event": "x", "title": "t", "body": "b"}
        for user in (self.vendor, self.rmt_user):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post("/api/notifications/", payload, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.vendor)
        response = self.client.patch(f"/api/notifications/{note.id}/", {"title": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unread_count(self):
        self._create(self.vendor)
        self._create(self.vendor, title="Already read", status=NotificationStatus.READ)
        self._create(self.vendor, title="Urgent", event="payment_claim_returned")

        self.client.force_authenticate(self.vendor)
        response = self.client.get("/api/notifications/unread_count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["high_priority"], 1)

    def test_mark_read_and_unread_own_notification(self):
        note = self._create(self.vendor)
        self.client.force_authenticate(self.vendor)
        response = self.client.post(f"/api/notifications/{note.id}/mark_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])
        self.assertIsNotNone(response.data["read_at"])
        response = self.client.post(f"/api/notifications/{note.id}/mark_unread/")
        self.assertFalse(response.data["is_read"])
        note.refresh_from_db()
        self.assertEqual(note.status, NotificationStatus.SENT)

    def test_other_users_notification_is_hidden(self):
        note = self._create(self.rmt_user)
        self.client.force_authenticate(self.vendor)
        for url in (f"/api/notifications/{note.id}/", f"/api/notifications/{note.id}/mark_read/"):
            method = self.client.get if url.endswith(f"{note.id}/") else self.client.post
            self.assertEqual(method(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(f"/api/notifications/{note.id}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_all_read(self):
        self._create(self.vendor)
        self._create(self.vendor, title="Second unread")
        self._create(self.rmt_user, title="Other user unread")

        self.client.force_authenticate(self.vendor)
        response = self.client.post("/api/notifications/mark_all_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 2)

    def test_archive_filters_and_delete(self):
        keep = self._create(self.vendor, title="Keep")
        old = self._create(self.vendor, title="Old")
        self.client.force_authenticate(self.vendor)
        response = self.client.post(f"/api/notifications/{old.id}/archive/")
        self.assertIsNotNone(response.data["archived_at"])
        self.assertTrue(response.data["is_read"])
        self.assertEqual([n["title"] for n in self.client.get("/api/notifications/").data["results"]], ["Keep"])
        self.assertEqual([n["title"] for n in self.client.get("/api/notifications/?archived=1").data["results"]], ["Old"])
        self.client.post(f"/api/notifications/{old.id}/unarchive/")
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 2)
        self.assertEqual(self.client.delete(f"/api/notifications/{keep.id}/").status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(id=keep.id).exists())

    def test_bulk_actions_only_touch_own_rows(self):
        mine = [self._create(self.vendor, title=f"n{i}") for i in range(3)]
        theirs = self._create(self.rmt_user)
        self.client.force_authenticate(self.vendor)
        ids = [n.id for n in mine] + [theirs.id]
        response = self.client.post("/api/notifications/bulk/", {"ids": ids, "action": "read"}, format="json")
        self.assertEqual(response.data["updated"], 3)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, NotificationStatus.SENT)
        self.assertEqual(self.client.post("/api/notifications/bulk/", {"ids": ids, "action": "explode"}, format="json").status_code, 400)
        response = self.client.post("/api/notifications/bulk/", {"ids": ids, "action": "delete"}, format="json")
        self.assertEqual(response.data["updated"], 3)
        self.assertTrue(Notification.objects.filter(id=theirs.id).exists())

    def test_category_priority_and_related_project(self):
        project = Project.objects.create(
            vendor_id=str(self.vendor.id), vendor_name="Vendor One", tech_type="SHS", region="Maseru",
            district="Maseru", status=ProjectStatus.ACTIVE, project_reference="PRJ-NOTE-1",
        )
        self._create(self.vendor, title="Claim returned", event="payment_claim_returned", linked_entity_id=str(project.id))
        self._create(self.vendor, title="Tender out", event="tender_published", linked_entity_id="999999")
        self._create(self.vendor, title="Flag", event="project_oversight_flag", linked_entity_id=str(project.id))

        self.client.force_authenticate(self.vendor)
        rows = {n["title"]: n for n in self.client.get("/api/notifications/").data["results"]}
        claim = rows["Claim returned"]
        self.assertEqual(claim["category"], "payments")
        self.assertEqual(claim["priority"], "high")
        self.assertEqual(claim["related"]["project_id"], str(project.id))
        self.assertEqual(claim["related"]["project_label"], "PRJ-NOTE-1")
        self.assertEqual(rows["Tender out"]["category"], "procurement")
        self.assertEqual(rows["Tender out"]["related"]["tender_id"], "")  # tender no longer exists

        titles = lambda q: sorted(n["title"] for n in self.client.get(f"/api/notifications/?{q}").data["results"])
        self.assertEqual(titles("category=payments"), ["Claim returned"])
        self.assertEqual(titles("category=projects"), [])  # project_oversight_flag belongs to oversight
        self.assertEqual(titles("category=oversight"), ["Flag"])
        self.assertEqual(titles("priority=high"), ["Claim returned", "Flag"])

    def test_repeated_events_are_all_kept(self):
        """A second bid submission (or a second claim on a project) is a new notification."""
        for _ in range(2):
            NotificationService.send(
                recipient_id=str(self.rmt_user.id),
                title="New Bid Submitted",
                body="Bid resubmission",
                module="tenders",
                record_id=42,
            )
        self.assertEqual(Notification.objects.filter(recipient_id=str(self.rmt_user.id), event="tenders_info").count(), 2)

    def test_dedupe_key_notifies_once(self):
        first = NotificationService.notify_user(recipient=self.vendor, title="t", body="b", event="e", dedupe_key="once:1")
        second = NotificationService.notify_user(recipient=self.vendor, title="t", body="b", event="e", dedupe_key="once:1")
        self.assertEqual(first.id, second.id)
        self.assertEqual(Notification.objects.filter(dedupe_key="once:1").count(), 1)

    def test_inactive_users_are_not_notified(self):
        self.rmt_user.is_active = False
        self.rmt_user.save(update_fields=["is_active"])
        NotificationService.notify_roles(roles={UserRole.RBF_OFFICIAL, UserRole.ADMIN}, title="t", body="b", event="e")
        self.assertFalse(Notification.objects.filter(recipient_id=str(self.rmt_user.id)).exists())
        self.assertTrue(Notification.objects.filter(recipient_id=str(self.admin.id)).exists())
