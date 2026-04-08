import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from rbf.projects.models import (
    AuditLog,
    Disbursement,
    DisbursementStatus,
    InstallationReport,
    InstallationStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
    VerificationStatus,
    VerificationTask,
)
from rbf.users.models import BlacklistedIdentifier, BlacklistCaseStatus, VendorBlacklistCase


class UserApiTests(APITestCase):
    @patch("rbf.users.views.SyncToProspectJob.dispatch_async")
    def test_super_admin_can_create_non_vendor_user_and_queue_prospect_agent(self, dispatch_async):
        User = get_user_model()
        admin = User.objects.create_user(
            username="super_admin_create",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
            email="super-admin@example.com",
        )
        self.client.force_authenticate(admin)

        response = self.client.post(
            "/api/users/",
            {
                "email": "field.officer@example.com",
                "full_name": "Field Officer One",
                "gender": "Female",
                "role": "Field Officer",
                "region": "Maseru",
                "verification_zone": "Maseru Urban",
                "status": "Active",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="field.officer@example.com")
        self.assertTrue(created_user.must_change_password)
        self.assertEqual(created_user.role, "Field Verifier")
        self.assertTrue(AuditLog.objects.filter(action="user_created", record_id=created_user.id, record_type="user").exists())
        dispatch_async.assert_called_once()
        self.assertEqual(dispatch_async.call_args.args[0], "pushAgent")
        self.assertEqual(dispatch_async.call_args.args[1][0]["gender"], "F")
        self.assertEqual(dispatch_async.call_args.kwargs["record_id"], created_user.id)
        self.assertEqual(dispatch_async.call_args.kwargs["record_type"], "user")

    def test_super_admin_user_list_excludes_vendors_and_supports_filters(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="super_admin_list",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        User.objects.create_user(
            username="vendor_hidden",
            password="securePass123",
            role="Vendor",
            status="Active",
            region="Maseru",
            email="vendor-hidden@example.com",
            gender="Male",
            mobile_number="26655555555",
        )
        User.objects.create_user(
            username="doe_visible",
            password="securePass123",
            role="DoE Officer",
            status="Active",
            region="Maseru",
            email="doe-visible@example.com",
            gender="Female",
            mobile_number="26655555556",
        )
        self.client.force_authenticate(admin)

        response = self.client.get("/api/users/?role=DoE Officer&district=Maseru&status=active")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["role"], "DoE Officer")

    def test_super_admin_can_deactivate_user(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="super_admin_deactivate",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        managed = User.objects.create_user(
            username="auditor_user",
            password="securePass123",
            role="Auditor",
            status="Active",
            is_active=True,
            email="auditor@example.com",
            gender="Male",
            region="Maseru",
            mobile_number="26655555557",
        )
        self.client.force_authenticate(admin)

        response = self.client.post(f"/api/users/{managed.id}/deactivate/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        managed.refresh_from_db()
        self.assertFalse(managed.is_active)
        self.assertEqual(managed.status, "Inactive")
        self.assertTrue(AuditLog.objects.filter(action="user_deactivated", record_id=managed.id).exists())

    def test_change_password_clears_must_change_password(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="must_change_user",
            password="TempPass123!",
            email="must-change@example.com",
            role="Auditor",
            status="Active",
            must_change_password=True,
            gender="Female",
            region="Maseru",
            mobile_number="26655555558",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            "/api/users/auth/change-password/",
            {"new_password": "ChangedPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "Auditor")
        self.assertFalse(response.data["must_change_password"])
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("ChangedPass123!"))

    def test_create_and_list_user(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="platform_admin",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        self.client.force_authenticate(admin)

        payload = {
            "username": "rbf_admin",
            "password": "securePass123",
            "email": "admin@rbf.ls",
            "full_name": "Admin User",
            "gender": "Female",
            "role": "Platform Administrator (Super Admin)",
            "region": "Maseru",
            "mobile_number": "26655555555",
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
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        self.client.force_authenticate(admin)

        create_response = self.client.post(
            "/api/users/",
            {
                "username": "api_created_user",
                "password": "securePass123",
                "email": "api@example.com",
                "role": "Platform Administrator (Super Admin)",
                "status": "Active",
                "gender": "Male",
                "region": "Maseru",
                "mobile_number": "26655555555",
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

    @override_settings(DEBUG=True)
    def test_user_created_via_api_can_login_with_email_and_temp_password(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="creator_admin_email_login",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
        )
        self.client.force_authenticate(admin)

        create_response = self.client.post(
            "/api/users/",
            {
                "email": "temp.login@example.com",
                "full_name": "Temp Login User",
                "role": "Field Officer",
                "status": "Active",
                "gender": "Female",
                "region": "Maseru",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertIn("initial_password", create_response.data)
        self.assertEqual(create_response.data["username"], "temp_login")

        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/users/auth/token/",
            {"username": "temp.login@example.com", "password": create_response.data["initial_password"]},
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)
        self.assertEqual(login_response.data["user"]["username"], "temp_login")

    def test_pending_vendor_can_login(self):
        cache.set("registration_otp_verified:pending@example.com", True, timeout=300)
        self.client.post(
            "/api/users/",
            {
                "username": "pending_vendor",
                "password": "securePass123",
                "email": "pending@example.com",
                "role": "Vendor",
                "status": "Pending",
                "full_name": "Pending Vendor",
                "gender": "Female",
                "region": "Maseru",
                "mobile_number": "26655555555",
                "national_id": "ID-123",
                "address": "Maseru HQ",
                "organization_name": "Pending Vendor Ltd",
                "organization_type": "Private",
                "technology_types": ["SHS"],
                "registration_certificate_name": "reg.pdf",
                "tax_id": "TIN-123",
            },
            format="json",
        )

        response = self.client.post(
            "/api/users/auth/token/",
            {"username": "pending_vendor", "password": "securePass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            "/api/users/auth/token/",
            {"username": "unknown_user", "password": "wrong-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_vendor_defaults_to_pending_on_registration(self):
        cache.set("registration_otp_verified:new_vendor_default_pending@example.com", True, timeout=300)
        create_response = self.client.post(
            "/api/users/",
            {
                "username": "new_vendor_default_pending",
                "password": "securePass123",
                "email": "new_vendor_default_pending@example.com",
                "role": "Vendor",
                "full_name": "New Vendor",
                "gender": "Male",
                "region": "Maseru",
                "mobile_number": "26655555555",
                "national_id": "ID-234",
                "address": "Maseru HQ",
                "organization_name": "New Vendor Ltd",
                "organization_type": "Private",
                "technology_types": ["SHS"],
                "registration_certificate_name": "reg.pdf",
                "tax_id": "TIN-234",
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

    def test_vendor_registration_is_blocked_for_blacklisted_associated_entity(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="blacklisted_source_vendor",
            password="securePass123",
            role="Vendor",
            status="Blacklisted",
            is_active=True,
            gender="Male",
            region="Maseru",
            mobile_number="26655555555",
            national_id="ID-BL-1",
            address="Maseru HQ",
            organization_name="Blocked Vendor Ltd",
            organization_type="Private",
            associated_entities=["Jane Director", "John Partner"],
            technology_types=["SHS"],
            registration_certificate_name="reg.pdf",
            tax_id="TIN-BL-1",
        )
        case = VendorBlacklistCase.objects.create(
            vendor=vendor,
            reason="Fraudulent Reporting",
            status=BlacklistCaseStatus.BLACKLISTED,
        )
        BlacklistedIdentifier.objects.create(
            case=case,
            vendor=vendor,
            organization_name=vendor.organization_name,
            tax_id=vendor.tax_id,
            national_id=vendor.national_id,
            associated_entities=vendor.associated_entities,
            normalized_organization_name="blockedvendorltd",
            normalized_tax_id="tinbl1",
            normalized_national_id="idbl1",
            normalized_associated_entities=["janedirector", "johnpartner"],
            active=True,
        )

        cache.set("registration_otp_verified:associated@example.com", True, timeout=300)
        response = self.client.post(
            "/api/users/",
            {
                "username": "associated_match_vendor",
                "password": "securePass123",
                "email": "associated@example.com",
                "role": "Vendor",
                "full_name": "Associated Match",
                "gender": "Female",
                "region": "Maseru",
                "mobile_number": "26655555555",
                "national_id": "ID-NEW-1",
                "address": "Maseru HQ",
                "organization_name": "Fresh Entity Ltd",
                "organization_type": "Private",
                "associated_entities": ["Jane Director"],
                "technology_types": ["SHS"],
                "registration_certificate_name": "reg.pdf",
                "tax_id": "TIN-NEW-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("associated_entities", response.data)

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
        OTP_EXPIRY_SECONDS=600,
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
            "role": "Platform Administrator (Super Admin)",
            "gender": "Male",
            "region": "Maseru",
            "mobile_number": "26655555555",
        }

        response = self.client.post("/api/users/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_admin_can_approve_vendor(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="approver_admin",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
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
                "role": "Platform Administrator (Super Admin)",
                "gender": "Male",
                "region": "Maseru",
                "mobile_number": "26655555555",
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
            gender="Male",
            region="Maseru",
            mobile_number="26655555555",
        )
        reviewer = User.objects.create_user(
            username="prequal_reviewer",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
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

    def test_vendor_can_resubmit_partial_prequalification(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="prequal_resubmit_vendor",
            password="securePass123",
            role="Vendor",
            status="Active",
            gender="Male",
            region="Maseru",
            mobile_number="26655555555",
        )
        reviewer = User.objects.create_user(
            username="prequal_resubmit_reviewer",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )
        preq = vendor.prequalifications.create(
            company_name="Original Vendor Ltd",
            organization_type="Private",
            tax_id="TIN-123",
            hq_address="Maseru HQ",
            technology_types=["SHS"],
            declaration_accepted=True,
            contact_number="26655555555",
            email="vendor@example.com",
            status="Partial (Resubmit)",
            reviewer_comments="Please correct your application.",
            reviewed_by=reviewer,
            reviewed_at=timezone.now(),
        )

        self.client.force_authenticate(vendor)
        response = self.client.patch(
            f"/api/users/prequalifications/{preq.id}/",
            {
                "company_name": "Updated Vendor Ltd",
                "technology_types": ["SHS", "Mini-grid"],
                "declaration_accepted": True,
                "contact_number": "26655555555",
                "email": "vendor@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        preq.refresh_from_db()
        self.assertEqual(preq.company_name, "Updated Vendor Ltd")
        self.assertEqual(preq.technology_types, ["SHS", "Mini-grid"])
        self.assertEqual(preq.status, "Pending")
        self.assertIsNone(preq.reviewed_by)
        self.assertIsNone(preq.reviewed_at)

    def test_blacklisting_case_detail_is_visible_to_official_roles(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="blacklist_vendor_detail",
            password="securePass123",
            role="Vendor",
            status="Suspended",
            is_active=True,
            gender="Male",
            region="Maseru",
            mobile_number="26655555555",
            national_id="ID-DETAIL-1",
            address="Maseru HQ",
            organization_name="Detail Vendor Ltd",
            organization_type="Private",
            technology_types=["SHS"],
            registration_certificate_name="reg.pdf",
            tax_id="TIN-DETAIL-1",
        )
        initiator = User.objects.create_user(
            username="detail_rbf",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )
        case = vendor.blacklist_cases.create(
            reason="Fraudulent Reporting",
            description="Testing detail retrieval for officials.",
            status="Initiated",
            initiated_by=initiator,
            notice_sent_at=timezone.now(),
            cooling_off_until=timezone.now(),
        )
        roles = [
            ("detail_admin", "Platform Administrator (Super Admin)"),
            ("detail_rbf_official_2", "RBF Management Team"),
            ("detail_tac", "TAC Member"),
            ("detail_doe", "DoE Officer"),
            ("detail_auditor", "Auditor"),
        ]

        for username, role in roles:
            official = User.objects.create_user(
                username=username,
                password="securePass123",
                role=role,
                status="Active",
                gender="Female",
                region="Maseru",
                mobile_number="26655555555",
            )
            self.client.force_authenticate(official)
            response = self.client.get(f"/api/users/blacklisting-cases/{case.id}/")
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=f"{role} should be able to open blacklist cases")

        self.client.force_authenticate(vendor)
        vendor_response = self.client.get(f"/api/users/blacklisting-cases/{case.id}/")
        self.assertEqual(vendor_response.status_code, status.HTTP_200_OK)

    def test_blacklisting_workflow_updates_vendor_projects_claims_and_appeals(self):
        User = get_user_model()
        vendor = User.objects.create_user(
            username="blacklist_vendor_flow",
            password="securePass123",
            role="Vendor",
            status="Active",
            is_active=True,
            gender="Male",
            region="Maseru",
            mobile_number="26655555555",
            national_id="ID-FLOW-1",
            address="Maseru HQ",
            organization_name="Workflow Vendor Ltd",
            organization_type="Private",
            technology_types=["SHS"],
            registration_certificate_name="reg.pdf",
            tax_id="TIN-FLOW-1",
        )
        initiator = User.objects.create_user(
            username="blacklist_initiator",
            password="securePass123",
            role="RBF Management Team",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )
        reviewer = User.objects.create_user(
            username="blacklist_reviewer",
            password="securePass123",
            role="TAC Member",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )
        confirmer = User.objects.create_user(
            username="blacklist_confirmer",
            password="securePass123",
            role="Platform Administrator (Super Admin)",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )
        appeal_reviewer = User.objects.create_user(
            username="blacklist_appeal_reviewer",
            password="securePass123",
            role="Auditor",
            status="Active",
            gender="Female",
            region="Maseru",
            mobile_number="26655555555",
        )

        project = Project.objects.create(
            vendor_id=str(vendor.id),
            vendor_name="Workflow Vendor Ltd",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
        )
        related_vendor = User.objects.create_user(
            username="related_vendor_flow",
            password="securePass123",
            role="Vendor",
            status="Active",
            is_active=True,
            gender="Female",
            region="Maseru",
            mobile_number="26655555556",
            national_id="ID-REL-1",
            address="Maseru Branch",
            organization_name="Related Vendor Ltd",
            organization_type="Private",
            technology_types=["SHS"],
            registration_certificate_name="reg.pdf",
            tax_id="TIN-REL-1",
        )
        related_project = Project.objects.create(
            vendor_id=str(related_vendor.id),
            vendor_name="Related Vendor Ltd",
            tech_type="SHS",
            region="Maseru",
            district="Maseru",
            status=ProjectStatus.INSTALLATION,
        )
        claim = PaymentClaim.objects.create(
            project=project,
            vendor=vendor,
            claim_amount="1000.00",
            status=PaymentClaimStatus.APPROVED,
            declaration_accepted=True,
        )
        disbursement = Disbursement.objects.create(
            claim=claim,
            amount="1000.00",
            status=DisbursementStatus.INITIATED,
        )
        related_claim = PaymentClaim.objects.create(
            project=related_project,
            vendor=related_vendor,
            claim_amount="1200.00",
            status=PaymentClaimStatus.APPROVED,
            declaration_accepted=True,
        )
        InstallationReport.objects.create(
            project=project,
            vendor=vendor,
            gps_lat=-29.31,
            gps_lng=27.48,
            serial_number="SERIAL-DUP-1",
            beneficiary_id="BEN-100",
        )
        related_report = InstallationReport.objects.create(
            project=related_project,
            vendor=related_vendor,
            gps_lat=-29.32,
            gps_lng=27.49,
            serial_number="SERIAL-DUP-1",
            beneficiary_id="BEN-200",
        )
        related_task = VerificationTask.objects.create(
            report=related_report,
            vendor_lat=related_report.gps_lat,
            vendor_lng=related_report.gps_lng,
            status="Pending",
        )

        self.client.force_authenticate(initiator)
        initiate_response = self.client.post(
            f"/api/users/{vendor.id}/initiate_blacklisting/",
            {
                "reason": "Fraudulent Reporting",
                "description": "Evidence package attached.",
                "cooling_off_days": 3,
            },
            format="multipart",
        )
        self.assertEqual(initiate_response.status_code, status.HTTP_201_CREATED)
        case_id = initiate_response.data["id"]
        vendor.refresh_from_db()
        own_report = InstallationReport.objects.get(project=project, vendor=vendor)
        own_task = VerificationTask.objects.get(report=own_report)
        own_report.refresh_from_db()
        own_task.refresh_from_db()
        self.assertEqual(vendor.status, "Suspended")
        self.assertEqual(initiate_response.data["status"], "Initiated")
        self.assertEqual(own_report.status, InstallationStatus.PAUSED)
        self.assertEqual(own_task.status, VerificationStatus.PAUSED)

        self.client.force_authenticate(vendor)
        vendor_cases = self.client.get("/api/users/blacklisting-cases/")
        self.assertEqual(vendor_cases.status_code, status.HTTP_200_OK)
        self.assertEqual(vendor_cases.data["results"][0]["id"], case_id)

        appeal_response = self.client.post(
            f"/api/users/blacklisting-cases/{case_id}/appeal/",
            {
                "rebuttal_text": "We dispute the allegation and request review.",
            },
            format="multipart",
        )
        self.assertEqual(appeal_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(appeal_response.data["status"], "Submitted")
        appeal_id = appeal_response.data["id"]

        self.client.force_authenticate(reviewer)
        review_response = self.client.post(
            f"/api/users/blacklisting-cases/{case_id}/review/",
            {"review_notes": "Escalating for formal review."},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        self.assertEqual(review_response.data["status"], "Under Review")

        self.client.force_authenticate(confirmer)
        early_confirm = self.client.post(
            f"/api/users/blacklisting-cases/{case_id}/confirm/",
            {"final_decision_notes": "Too early to confirm."},
            format="json",
        )
        self.assertEqual(early_confirm.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cooling-off period is still active.", str(early_confirm.data))

        case = vendor.blacklist_cases.get(id=case_id)
        case.cooling_off_until = timezone.now() - timedelta(days=1)
        case.save(update_fields=["cooling_off_until"])

        confirm_response = self.client.post(
            f"/api/users/blacklisting-cases/{case_id}/confirm/",
            {"final_decision_notes": "Confirmed after cooling-off."},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.data["status"], "Blacklisted")
        vendor.refresh_from_db()
        project.refresh_from_db()
        related_project.refresh_from_db()
        claim.refresh_from_db()
        related_claim.refresh_from_db()
        disbursement.refresh_from_db()
        related_report.refresh_from_db()
        related_task.refresh_from_db()
        own_report.refresh_from_db()
        own_task.refresh_from_db()
        self.assertEqual(vendor.status, "Blacklisted")
        self.assertTrue(vendor.is_active)
        self.assertEqual(project.status, ProjectStatus.HALTED)
        self.assertEqual(related_project.status, ProjectStatus.HALTED)
        self.assertEqual(claim.status, PaymentClaimStatus.HELD_AUDIT)
        self.assertEqual(related_claim.status, PaymentClaimStatus.HELD_AUDIT)
        self.assertEqual(disbursement.status, DisbursementStatus.HELD_AUDIT)
        self.assertEqual(own_report.status, InstallationStatus.TERMINATED)
        self.assertEqual(own_task.status, VerificationStatus.TERMINATED)
        self.assertEqual(related_report.status, "Flagged")
        self.assertEqual(related_task.status, "Flagged")
        self.assertTrue(related_task.anomaly_flag)
        self.assertTrue(BlacklistedIdentifier.objects.filter(case_id=case_id, vendor=vendor, active=True).exists())

        self.client.force_authenticate(appeal_reviewer)
        resolve_appeal = self.client.post(
            f"/api/users/blacklisting-appeals/{appeal_id}/review/",
            {"resolution_notes": "Appeal reviewed and closed."},
            format="json",
        )
        self.assertEqual(resolve_appeal.status_code, status.HTTP_200_OK)
        self.assertEqual(resolve_appeal.data["status"], "Resolved")

        self.client.force_authenticate(confirmer)
        reinstate_response = self.client.post(
            f"/api/users/blacklisting-cases/{case_id}/reinstate/",
            {},
            format="json",
        )
        self.assertEqual(reinstate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reinstate_response.data["status"], "Reinstated")
        vendor.refresh_from_db()
        self.assertEqual(vendor.status, "Registered")
        self.assertFalse(BlacklistedIdentifier.objects.filter(case_id=case_id, vendor=vendor, active=True).exists())
