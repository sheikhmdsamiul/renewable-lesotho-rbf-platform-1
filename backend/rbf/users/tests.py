import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase


class UserApiTests(APITestCase):
    def test_create_and_list_user(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="platform_admin",
            password="securePass123",
            role="Digital Admin",
            status="Active",
        )
        self.client.force_authenticate(admin)

        payload = {
            "username": "rbf_admin",
            "password": "securePass123",
            "email": "admin@rbf.ls",
            "full_name": "Admin User",
            "gender": "Female",
            "role": "Digital Admin",
            "region": "Maseru",
            "organization_name": "RBF Office",
            "organization_type": "Government",
            "technology_types": ["SHS"],
            "status": "Active",
            "must_change_password": False,
        }

        create_response = self.client.post("/api/users/", payload, format="json")
        list_response = self.client.get("/api/users/")

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", create_response.data)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        usernames = [item["username"] for item in list_response.data["results"]]
        self.assertIn("rbf_admin", usernames)

    def test_login_and_current_user_endpoint(self):
        user = get_user_model().objects.create_user(
            username="auth_user",
            password="securePass123",
            email="auth@example.com",
        )

        login_response = self.client.post(
            "/api/users/auth/token/",
            {"username": "auth_user", "password": "securePass123"},
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)
        self.assertEqual(login_response.data["user"]["id"], user.id)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
        me_response = self.client.get("/api/users/auth/me/")

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["username"], "auth_user")

    def test_user_created_via_api_can_login(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="creator_admin",
            password="securePass123",
            role="Digital Admin",
            status="Active",
        )
        self.client.force_authenticate(admin)

        create_response = self.client.post(
            "/api/users/",
            {
                "username": "api_created_user",
                "password": "securePass123",
                "email": "api@example.com",
                "role": "Digital Admin",
                "status": "Active",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(user=None)

        login_response = self.client.post(
            "/api/users/auth/token/",
            {"username": "api_created_user", "password": "securePass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)

    def test_pending_vendor_cannot_login(self):
        self.client.post(
            "/api/users/",
            {
                "username": "pending_vendor",
                "password": "securePass123",
                "email": "pending@example.com",
                "role": "Vendor",
                "status": "Pending",
            },
            format="json",
        )

        response = self.client.post(
            "/api/users/auth/token/",
            {"username": "pending_vendor", "password": "securePass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            "/api/users/auth/token/",
            {"username": "unknown_user", "password": "wrong-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_vendor_defaults_to_pending_on_registration(self):
        create_response = self.client.post(
            "/api/users/",
            {
                "username": "new_vendor_default_pending",
                "password": "securePass123",
                "email": "new_vendor_default_pending@example.com",
                "role": "Vendor",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["status"], "Pending")

        login_response = self.client.post(
            "/api/users/auth/token/",
            {"username": "new_vendor_default_pending", "password": "securePass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_seed_demo_users_command_creates_expected_accounts(self):
        call_command("seed_demo_users")
        User = get_user_model()

        self.assertTrue(User.objects.filter(username="vendor_approved").exists())
        self.assertTrue(User.objects.filter(username="admin_user").exists())
        self.assertEqual(User.objects.filter(is_active=True).count(), 8)

    def test_seed_demo_users_can_login_and_access_me(self):
        call_command("seed_demo_users")
        credentials = [
            ("vendor_approved", "Vendor@1234"),
            ("admin_user", "Admin@1234"),
            ("rbf_official", "Rbf@1234"),
            ("tac_member", "Tac@1234"),
            ("doe_officer", "Doe@1234"),
            ("field_verifier", "Field@1234"),
            ("donor_user", "Donor@1234"),
            ("auditor_user", "Auditor@1234"),
        ]

        for username, password in credentials:
            login_response = self.client.post(
                "/api/users/auth/token/",
                {"username": username, "password": password},
                format="json",
            )
            self.assertEqual(login_response.status_code, status.HTTP_200_OK)
            self.assertIn("access", login_response.data)

            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
            me_response = self.client.get("/api/users/auth/me/")
            self.assertEqual(me_response.status_code, status.HTTP_200_OK)
            self.assertEqual(me_response.data["username"], username)
            self.client.credentials()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="secret",
        DEFAULT_FROM_EMAIL="sender@example.com",
        OTP_LENGTH=6,
        OTP_EXPIRY_SECONDS=300,
    )
    def test_registration_otp_request_and_verify(self):
        request_response = self.client.post(
            "/api/users/auth/request-otp/",
            {"email": "otp.user@example.com"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body
        otp_match = re.search(r"(\d{6})", body)
        self.assertIsNotNone(otp_match)
        otp = otp_match.group(1)

        verify_response = self.client.post(
            "/api/users/auth/verify-otp/",
            {"email": "otp.user@example.com", "otp": otp},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="secret",
        DEFAULT_FROM_EMAIL="sender@example.com",
    )
    def test_registration_otp_invalid_code_rejected(self):
        self.client.post(
            "/api/users/auth/request-otp/",
            {"email": "otp.invalid@example.com"},
            format="json",
        )
        verify_response = self.client.post(
            "/api/users/auth/verify-otp/",
            {"email": "otp.invalid@example.com", "otp": "111111"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(
        DEBUG=True,
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
    )
    def test_registration_otp_returns_debug_code_when_email_not_configured(self):
        response = self.client.post(
            "/api/users/auth/request-otp/",
            {"email": "otp.noemail@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("debug_otp", response.data)

    @override_settings(DEBUG=True)
    def test_bootstrap_demo_users_endpoint(self):
        User = get_user_model()
        User.objects.all().delete()

        response = self.client.post("/api/users/auth/bootstrap-demo-users/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.filter(username="admin_user").exists())

    @override_settings(DEBUG=True)
    def test_demo_login_autoseeds_when_users_missing(self):
        User = get_user_model()
        User.objects.all().delete()

        response = self.client.post(
            "/api/users/auth/token/",
            {"username": "admin_user", "password": "Admin@1234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertEqual(User.objects.filter(username="admin_user").count(), 1)

    @override_settings(API_REQUIRE_AUTH=True)
    def test_user_write_requires_auth_when_production_auth_enabled(self):
        payload = {
            "username": "unauth_user",
            "password": "securePass123",
            "email": "unauth@example.com",
            "role": "Digital Admin",
        }

        response = self.client.post("/api/users/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_admin_can_approve_vendor(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="approver_admin",
            password="securePass123",
            role="Digital Admin",
            status="Active",
        )
        vendor = User.objects.create_user(
            username="pending_vendor_to_approve",
            password="securePass123",
            role="Vendor",
            status="Pending",
            is_active=True,
        )

        self.client.force_authenticate(admin)
        response = self.client.patch(f"/api/users/{vendor.id}/approve/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vendor.refresh_from_db()
        self.assertEqual(vendor.status, "Active")

    def test_public_registration_cannot_create_privileged_role(self):
        response = self.client.post(
            "/api/users/",
            {
                "username": "public_admin_attempt",
                "password": "securePass123",
                "email": "public-admin@example.com",
                "role": "Digital Admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_vendor_prequalification_submission_and_review_workflow(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="prequal_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
        )
        reviewer = User.objects.create_user(
            username="prequal_reviewer",
            password="securePass123",
            role="RBF Official",
            status="Active",
        )

        self.client.force_authenticate(vendor)
        submit_response = self.client.post(
            "/api/users/prequalifications/",
            {
                "company_name": "Solar Vendor Ltd",
                "organization_type": "Private",
                "tax_id": "TIN-123",
                "hq_address": "Maseru HQ",
                "technology_types": ["SHS", "Mini-grid"],
                "declaration_accepted": True,
            },
            format="json",
        )
        self.assertEqual(submit_response.status_code, status.HTTP_201_CREATED)
        preq_id = submit_response.data["id"]
        self.assertEqual(submit_response.data["status"], "Pending")

        self.client.force_authenticate(reviewer)
        review_response = self.client.post(
            f"/api/users/prequalifications/{preq_id}/start_review/",
            {"reviewer_comments": "Review started"},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        self.assertEqual(review_response.data["status"], "Under Review")

        approve_response = self.client.post(
            f"/api/users/prequalifications/{preq_id}/approve/",
            {"reviewer_comments": "Approved for EVL"},
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], "Approved")
