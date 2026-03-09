from django.db import models
from django.conf import settings


class ProjectStatus(models.TextChoices):
    PRE_QUALIFICATION = 'Pre-Qualification'
    SITE_SPECIFIC = 'Site-Specific Proposal'
    CONTRACTING = 'Contracting'
    INSTALLATION = 'Installation'
    VERIFICATION = 'Field Verification'
    DISBURSEMENT = 'Disbursement'
    COMPLETED = 'Completed'


class Project(models.Model):
    vendor_id = models.CharField(max_length=64)
    vendor_name = models.CharField(max_length=255)
    tech_type = models.CharField(max_length=64)
    region = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=ProjectStatus.choices)
    progress = models.PositiveIntegerField(default=0)
    energy_output = models.FloatField(default=0)  # kWh
    uptime = models.FloatField(default=0)  # %
    gender_impact = models.FloatField(default=0)  # % female beneficiaries

    def __str__(self):
        return f"{self.vendor_name} - {self.tech_type}"


class MilestoneStatus(models.TextChoices):
    PENDING = 'Pending'
    SUBMITTED = 'Submitted'
    VERIFIED = 'Verified'
    PAID = 'Paid'


class Milestone(models.Model):
    project = models.ForeignKey(Project, related_name='milestones', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    percentage = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=MilestoneStatus.choices, default=MilestoneStatus.PENDING)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project_id} - {self.name} ({self.percentage}%)"


class PaymentClaimStatus(models.TextChoices):
    PENDING = 'Pending'
    VERIFIED = 'Verified'
    APPROVED = 'Approved'
    PAID = 'Paid'
    REJECTED = 'Rejected'


class PaymentClaim(models.Model):
    project = models.ForeignKey(Project, related_name='payment_claims', on_delete=models.CASCADE)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='payment_claims', on_delete=models.CASCADE)
    milestone = models.ForeignKey(Milestone, related_name='payment_claims', on_delete=models.SET_NULL, null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    claim_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_beneficiaries = models.PositiveIntegerField(default=0)
    actual_female_beneficiaries = models.PositiveIntegerField(default=0)
    implementation_notes = models.TextField(blank=True)
    evidence_files = models.JSONField(default=list, blank=True)
    declaration_accepted = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=PaymentClaimStatus.choices, default=PaymentClaimStatus.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=64, blank=True)
    remarks = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='reviewed_claims',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Claim {self.id} - {self.vendor} - {self.status}"


class DisbursementStatus(models.TextChoices):
    INITIATED = 'Initiated'
    COMPLETED = 'Completed'
    FAILED = 'Failed'


class Disbursement(models.Model):
    claim = models.OneToOneField(PaymentClaim, related_name='disbursement', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=16, choices=DisbursementStatus.choices, default=DisbursementStatus.INITIATED)
    reference = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='processed_disbursements',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-processed_at']

    def __str__(self):
        return f"Disbursement {self.id} - Claim {self.claim_id} - {self.status}"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='audit_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=128)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"
