from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    RBF_OFFICIAL = 'RBF Management Team', 'RBF Management Team'
    TAC = 'TAC Member', 'TAC Member'
    DOE_OFFICER = 'DoE Officer', 'DoE Officer'
    FIELD_VERIFIER = 'Field Verifier', 'Field Verifier'
    VENDOR = 'Vendor', 'Vendor'
    ADMIN = 'Platform Administrator (Super Admin)', 'Platform Administrator (Super Admin)'
    UNDP_DONOR = 'Project Steering Committee', 'Project Steering Committee'
    AUDITOR = 'Auditor', 'Auditor'


class UserStatus(models.TextChoices):
    ACTIVE = 'Active'
    PENDING = 'Pending'
    INACTIVE = 'Inactive'
    REGISTERED = 'Registered'
    SUSPENDED = 'Suspended'
    BLACKLISTED = 'Blacklisted'


class User(AbstractUser):
    full_name = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=16, blank=True)
    role = models.CharField(max_length=64, choices=UserRole.choices, default=UserRole.VENDOR)
    region = models.CharField(max_length=128, blank=True)
    mobile_number = models.CharField(max_length=20, blank=True)
    national_id = models.CharField(max_length=64, blank=True)
    address = models.CharField(max_length=255, blank=True)
    organization_name = models.CharField(max_length=255, blank=True)
    organization_type = models.CharField(max_length=64, blank=True)
    associated_entities = models.JSONField(default=list, blank=True)
    technology_types = models.JSONField(default=list, blank=True)
    registration_certificate_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    tier_assignment = models.CharField(max_length=64, blank=True)
    verification_zone = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=UserStatus.choices, default=UserStatus.ACTIVE)
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return self.username or self.email or str(self.pk)


class PrequalificationStatus(models.TextChoices):
    PENDING = 'Pending', 'Pending'
    UNDER_REVIEW = 'Under Review', 'Under Review'
    APPROVED = 'Approved', 'Approved'
    CLARIFICATION_REQUESTED = 'Partial (Resubmit)', 'Partial (Resubmit)'
    REJECTED = 'Rejected', 'Rejected'


class VendorPrequalification(models.Model):
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    TIER_CHOICES = [
        ('Level 1', 'Level 1'),
        ('Level 2', 'Level 2'),
        ('Level 3', 'Level 3'),
        ('Level 4', 'Level 4'),
        ('Level 5', 'Level 5'),
    ]

    vendor = models.ForeignKey(User, related_name='prequalifications', on_delete=models.CASCADE)
    company_name = models.CharField(max_length=255)
    organization_type = models.CharField(max_length=64, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    hq_address = models.CharField(max_length=255, blank=True)
    
    # File uploads
    trading_license = models.FileField(upload_to='prequalification/certificates/', blank=True, null=True)
    registration_certificate = models.FileField(upload_to='prequalification/certificates/', blank=True, null=True)
    tax_compliance_certificate = models.FileField(upload_to='prequalification/certificates/', blank=True, null=True)
    authorized_signatory_id = models.FileField(upload_to='prequalification/signatures/', blank=True, null=True)
    experience_financial_proof = models.FileField(upload_to='prequalification/experience/', blank=True, null=True)
    
    # Technology and tier info
    technology_types = models.JSONField(default=list, blank=True)
    registration_certificate_name = models.CharField(max_length=255, blank=True)
    tech_tier = models.CharField(max_length=32, choices=TIER_CHOICES, blank=True)
    
    # Financial and experience info
    years_experience = models.PositiveIntegerField(default=0)
    prior_projects = models.PositiveIntegerField(default=0)
    annual_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    districts_covered = models.PositiveIntegerField(default=0)
    
    # Inclusive targets
    female_beneficiary_target = models.PositiveIntegerField(default=50)
    vulnerable_group_target = models.PositiveIntegerField(default=30)
    
    # Bank and contact details
    bank_account_name = models.CharField(max_length=255, blank=True)
    bank_account_number = models.CharField(max_length=32, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    bank_branch = models.CharField(max_length=255, blank=True)
    bank_swift_code = models.CharField(max_length=64, blank=True)
    bank_sort_code = models.CharField(max_length=64, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    gender_of_focal_person = models.CharField(max_length=16, choices=GENDER_CHOICES, blank=True)
    
    # Status and review
    declaration_accepted = models.BooleanField(default=False)
    reviewer_comments = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=PrequalificationStatus.choices,
        default=PrequalificationStatus.PENDING,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_prequalifications',
    )

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.vendor.username} - {self.company_name} ({self.status})"


class BlacklistReason(models.TextChoices):
    FRAUDULENT_REPORTING = 'Fraudulent Reporting', 'Fraudulent Reporting'
    INTEGRITY_BREACH = 'Integrity Breach', 'Integrity Breach'
    PERSISTENT_NON_PERFORMANCE = 'Persistent Non-Performance', 'Persistent Non-Performance'
    EXTERNAL_LEGAL_ACTION = 'External Legal Action', 'External Legal Action'


class BlacklistCaseStatus(models.TextChoices):
    INITIATED = 'Initiated'
    UNDER_REVIEW = 'Under Review'
    BLACKLISTED = 'Blacklisted'
    REJECTED = 'Rejected'
    EXPIRED = 'Expired'
    REINSTATED = 'Reinstated'


class BlacklistAppealStatus(models.TextChoices):
    SUBMITTED = 'Submitted'
    UNDER_REVIEW = 'Under Review'
    RESOLVED = 'Resolved'


class VendorBlacklistCase(models.Model):
    vendor = models.ForeignKey(User, related_name='blacklist_cases', on_delete=models.CASCADE)
    reason = models.CharField(max_length=64, choices=BlacklistReason.choices)
    description = models.TextField(blank=True)
    justification_document = models.FileField(upload_to='blacklisting/justifications/', blank=True, null=True)
    status = models.CharField(max_length=24, choices=BlacklistCaseStatus.choices, default=BlacklistCaseStatus.INITIATED)
    initiated_by = models.ForeignKey(
        User,
        related_name='initiated_blacklist_cases',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    initiated_at = models.DateTimeField(auto_now_add=True)
    notice_sent_at = models.DateTimeField(null=True, blank=True)
    cooling_off_until = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        related_name='reviewed_blacklist_cases',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        User,
        related_name='confirmed_blacklist_cases',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    final_decision_notes = models.TextField(blank=True)
    is_permanent = models.BooleanField(default=False)
    expiry_date = models.DateField(null=True, blank=True)
    reinstated_at = models.DateTimeField(null=True, blank=True)
    reinstated_by = models.ForeignKey(
        User,
        related_name='reinstated_blacklist_cases',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-initiated_at']

    def __str__(self):
        return f"{self.vendor} - {self.reason} ({self.status})"


class BlacklistedIdentifier(models.Model):
    case = models.ForeignKey(VendorBlacklistCase, related_name='identifiers', on_delete=models.CASCADE)
    vendor = models.ForeignKey(User, related_name='blacklisted_identifiers', on_delete=models.CASCADE)
    organization_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    national_id = models.CharField(max_length=64, blank=True)
    associated_entities = models.JSONField(default=list, blank=True)
    normalized_organization_name = models.CharField(max_length=255, blank=True, db_index=True)
    normalized_tax_id = models.CharField(max_length=64, blank=True, db_index=True)
    normalized_national_id = models.CharField(max_length=64, blank=True, db_index=True)
    normalized_associated_entities = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_blacklistidentifier'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization_name or self.vendor} / {self.tax_id or 'no-tax-id'}"


class BlacklistAppeal(models.Model):
    case = models.ForeignKey(VendorBlacklistCase, related_name='appeals', on_delete=models.CASCADE)
    vendor = models.ForeignKey(User, related_name='blacklist_appeals', on_delete=models.CASCADE)
    rebuttal_text = models.TextField(blank=True)
    rebuttal_document = models.FileField(upload_to='blacklisting/appeals/', blank=True, null=True)
    status = models.CharField(max_length=24, choices=BlacklistAppealStatus.choices, default=BlacklistAppealStatus.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User,
        related_name='reviewed_blacklist_appeals',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Appeal {self.id} - {self.vendor} ({self.status})"


class OrganizationType(models.TextChoices):
    GOVERNMENT = 'Government', 'Government'
    INTERNATIONAL = 'International', 'International'
    NGO = 'NGO', 'NGO'


class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=32, choices=OrganizationType.choices)
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PlatformConfiguration(models.Model):
    platform_name = models.CharField(max_length=255, default='Renewable Lesotho RBF PLATFORM')
    country_code = models.CharField(max_length=8, default='LS')
    country_name = models.CharField(max_length=64, default='Lesotho')
    default_currency = models.CharField(max_length=8, default='LSL')
    timezone = models.CharField(max_length=64, default='Africa/Maseru')
    female_target_minimum = models.PositiveIntegerField(default=50)
    vulnerable_target_minimum = models.PositiveIntegerField(default=30)
    low_income_target_minimum = models.PositiveIntegerField(default=60)
    uptime_target = models.PositiveIntegerField(default=99)
    anomaly_deviation_threshold = models.PositiveIntegerField(default=5)
    gps_duplicate_radius_m = models.PositiveIntegerField(default=10)
    gps_verification_max_distance_m = models.PositiveIntegerField(default=50)
    m2_verification_required_pct = models.PositiveIntegerField(default=80)
    m3_verification_required_pct = models.PositiveIntegerField(default=100)
    email_notifications_enabled = models.BooleanField(default=True)
    sms_notifications_enabled = models.BooleanField(default=False)
    max_file_size_mb = models.PositiveIntegerField(default=10)
    allowed_file_types = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Platform Configuration'
        verbose_name_plural = 'Platform Configuration'

    def __str__(self):
        return self.platform_name
