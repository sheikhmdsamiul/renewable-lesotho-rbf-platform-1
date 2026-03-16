from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    RBF_OFFICIAL = 'RBF Official'
    TAC = 'TAC Member'
    DOE_OFFICER = 'DoE Officer'
    FIELD_VERIFIER = 'Field Verifier'
    VENDOR = 'Vendor'
    ADMIN = 'Digital Admin'
    UNDP_DONOR = 'UNDP & Donors'
    AUDITOR = 'Auditor'


class User(AbstractUser):
    full_name = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=16, blank=True)
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.VENDOR)
    region = models.CharField(max_length=128, blank=True)
    mobile_number = models.CharField(max_length=20, blank=True)
    national_id = models.CharField(max_length=64, blank=True)
    address = models.CharField(max_length=255, blank=True)
    organization_name = models.CharField(max_length=255, blank=True)
    organization_type = models.CharField(max_length=64, blank=True)
    technology_types = models.JSONField(default=list, blank=True)
    registration_certificate_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    tier_assignment = models.CharField(max_length=64, blank=True)
    verification_zone = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, default='Active')
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return self.username or self.email or str(self.pk)


class PrequalificationStatus(models.TextChoices):
    PENDING = 'Pending'
    UNDER_REVIEW = 'Under Review'
    APPROVED = 'Approved'
    CLARIFICATION_REQUESTED = 'Clarification Requested'
    REJECTED = 'Rejected'


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
