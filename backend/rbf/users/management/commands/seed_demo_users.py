from django.core.management.base import BaseCommand

from rbf.users.models import User, UserRole


DEMO_USERS = [
    {
        'username': 'vendor_approved',
        'password': 'Vendor@1234',
        'email': 'vendor.approved@rbf.ls',
        'full_name': 'Approved Vendor',
        'role': UserRole.VENDOR,
        'status': 'Active',
        'gender': 'Female',
        'organization_name': 'Lesotho Solar Solutions',
        'organization_type': 'Private',
        'technology_types': ['SHS', 'Mini-Grid'],
        'region': 'Maseru',
    },
    {
        'username': 'admin_user',
        'password': 'Admin@1234',
        'email': 'admin@rbf.ls',
        'full_name': 'Platform Administrator',
        'role': UserRole.ADMIN,
        'status': 'Active',
        'gender': 'Male',
        'region': 'All',
    },
    {
        'username': 'rbf_official',
        'password': 'Rbf@1234',
        'email': 'official@rbf.ls',
        'full_name': 'RBF Official User',
        'role': UserRole.RBF_OFFICIAL,
        'status': 'Active',
        'gender': 'Male',
        'region': 'Maseru',
    },
    {
        'username': 'tac_member',
        'password': 'Tac@1234',
        'email': 'tac@rbf.ls',
        'full_name': 'TAC Member User',
        'role': UserRole.TAC,
        'status': 'Active',
        'gender': 'Female',
        'region': 'Leribe',
    },
    {
        'username': 'doe_officer',
        'password': 'Doe@1234',
        'email': 'doe@rbf.ls',
        'full_name': 'DoE Officer User',
        'role': UserRole.DOE_OFFICER,
        'status': 'Active',
        'gender': 'Male',
        'region': 'Berea',
    },
    {
        'username': 'field_verifier',
        'password': 'Field@1234',
        'email': 'field@rbf.ls',
        'full_name': 'Field Verifier User',
        'role': UserRole.FIELD_VERIFIER,
        'status': 'Active',
        'gender': 'Female',
        'region': 'Mokhotlong',
    },
    {
        'username': 'donor_user',
        'password': 'Donor@1234',
        'email': 'donor@rbf.ls',
        'full_name': 'Donor User',
        'role': UserRole.UNDP_DONOR,
        'status': 'Active',
        'gender': 'Other',
        'region': 'All',
    },
    {
        'username': 'auditor_user',
        'password': 'Auditor@1234',
        'email': 'auditor@rbf.ls',
        'full_name': 'Auditor User',
        'role': UserRole.AUDITOR,
        'status': 'Active',
        'gender': 'Male',
        'region': 'Quthing',
    },
]


class Command(BaseCommand):
    help = 'Create or update demo users for role-based testing.'

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for spec in DEMO_USERS:
            user, was_created = User.objects.get_or_create(username=spec['username'])
            field_defaults = {
                'email': '',
                'full_name': '',
                'gender': '',
                'role': UserRole.VENDOR,
                'region': '',
                'organization_name': '',
                'organization_type': '',
                'technology_types': [],
                'status': 'Active',
            }
            for field, fallback in field_defaults.items():
                setattr(user, field, spec.get(field, fallback))

            user.is_active = True
            user.must_change_password = False
            user.set_password(spec['password'])
            user.save()

            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Demo users ready: created={created}, updated={updated}, total={len(DEMO_USERS)}'
            )
        )
