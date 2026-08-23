from django.conf import settings
from django.core import signing
from django.db import models
from django.utils import timezone
import uuid


class ProspectSyncStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'


class ProjectStatus(models.TextChoices):
    SETUP_PENDING = 'setup_pending', 'Setup Pending'
    SETUP_UNDER_REVIEW = 'setup_under_review', 'Setup Under Review'
    SETUP_CHANGES_REQUESTED = 'setup_changes_requested', 'Setup Changes Requested'
    SETUP_REJECTED = 'setup_rejected', 'Setup Rejected'
    ACTIVE = 'active', 'Active'
    PRE_QUALIFICATION = 'Pre-Qualification', 'Pre-Qualification'
    SITE_SPECIFIC = 'Site-Specific Proposal', 'Site-Specific Proposal'
    CONTRACTING = 'Contracting', 'Contracting'
    INSTALLATION = 'Installation', 'Installation'
    VERIFICATION = 'Field Verification', 'Field Verification'
    DISBURSEMENT = 'Disbursement', 'Disbursement'
    HALTED = 'Halted', 'Halted'
    COMPLETED = 'completed', 'Completed'
    LEGACY_COMPLETED = 'Completed', 'Completed (Legacy)'


class TechnologyType(models.TextChoices):
    SHS = 'SHS', 'SHS'
    ICS = 'ICS', 'ICS'
    GMG = 'GMG', 'GMG'
    SWP = 'SWP', 'SWP'
    PUE = 'PUE', 'PUE'


class VerificationMethod(models.TextChoices):
    IOT = 'iot', 'IoT'
    MANUAL = 'manual', 'Manual'


class Project(models.Model):
    tender = models.ForeignKey('tenders.Tender', related_name='projects', on_delete=models.SET_NULL, null=True, blank=True)
    contract = models.ForeignKey('tenders.TenderContract', related_name='projects', on_delete=models.SET_NULL, null=True, blank=True)
    project_title = models.CharField(max_length=255, blank=True)
    project_reference = models.CharField(max_length=64, blank=True)
    milestone_plan_id = models.CharField(max_length=64, blank=True)
    vendor_id = models.CharField(max_length=64)
    vendor_name = models.CharField(max_length=255)
    tech_type = models.CharField(max_length=64)
    region = models.CharField(max_length=64)
    district = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=ProjectStatus.choices)
    contract_file = models.FileField(upload_to='project_contracts/', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_projects', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    progress = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    target_installations = models.PositiveIntegerField(default=0)
    installation_target = models.PositiveIntegerField(default=0)
    target_female_pct = models.PositiveIntegerField(default=50)
    female_target_pct = models.PositiveIntegerField(default=50)
    target_vulnerable_pct = models.PositiveIntegerField(default=30)
    vulnerable_target_pct = models.PositiveIntegerField(default=30)
    target_low_income_pct = models.PositiveIntegerField(default=0)
    low_income_target_pct = models.PositiveIntegerField(default=60)
    target_beneficiaries = models.PositiveIntegerField(default=0)
    deployment_team_roster = models.TextField(blank=True)
    deployment_equipment_plan = models.TextField(blank=True)
    deployment_site_status = models.TextField(blank=True)
    deployment_work_schedule = models.TextField(blank=True)
    deployment_permits_status = models.TextField(blank=True)
    device_brand = models.CharField(max_length=255, blank=True, default='')
    device_model = models.CharField(max_length=255, blank=True, default='')
    device_tech_tier = models.CharField(max_length=64, blank=True, default='')
    verification_method_confirmed = models.BooleanField(default=False)
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    installation_target_summary = models.CharField(max_length=255, blank=True, default='')
    project_duration_months = models.PositiveIntegerField(default=0)
    verification_method = models.CharField(
        max_length=16,
        choices=VerificationMethod.choices,
        default=VerificationMethod.MANUAL,
    )
    prospect_sync_status = models.CharField(max_length=16, choices=ProspectSyncStatus.choices, default=ProspectSyncStatus.PENDING)
    prospect_sync_error = models.TextField(blank=True)
    prospect_synced_at = models.DateTimeField(null=True, blank=True)
    energy_output = models.FloatField(default=0)  # kWh
    energy_output_target_kwh = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    uptime = models.FloatField(default=0)  # %
    gender_impact = models.FloatField(default=0)  # % female beneficiaries
    technology_type = models.CharField(max_length=8, choices=TechnologyType.choices, blank=True, default='')
    district_zone = models.TextField(blank=True)

    def __str__(self):
        return f"{self.vendor_name} - {self.technology_type or self.tech_type}"

    def save(self, *args, **kwargs):
        if self.installation_target and not self.target_installations:
            self.target_installations = self.installation_target
        elif self.target_installations and not self.installation_target:
            self.installation_target = self.target_installations

        if self.female_target_pct and not self.target_female_pct:
            self.target_female_pct = self.female_target_pct
        elif self.target_female_pct and not self.female_target_pct:
            self.female_target_pct = self.target_female_pct

        if self.vulnerable_target_pct and not self.target_vulnerable_pct:
            self.target_vulnerable_pct = self.vulnerable_target_pct
        elif self.target_vulnerable_pct and not self.vulnerable_target_pct:
            self.vulnerable_target_pct = self.target_vulnerable_pct

        if self.low_income_target_pct and not self.target_low_income_pct:
            self.target_low_income_pct = self.low_income_target_pct
        elif self.target_low_income_pct and not self.low_income_target_pct:
            self.low_income_target_pct = self.target_low_income_pct

        if self.energy_output_target_kwh and not self.energy_output:
            self.energy_output = float(self.energy_output_target_kwh)
        elif self.energy_output and not self.energy_output_target_kwh:
            self.energy_output_target_kwh = self.energy_output

        if self.technology_type and not self.tech_type:
            self.tech_type = self.technology_type
        elif self.tech_type and not self.technology_type:
            self.technology_type = self.tech_type

        if self.district_zone and not self.district:
            self.district = self.district_zone
        elif self.district and not self.district_zone:
            self.district_zone = self.district

        super().save(*args, **kwargs)


class ProjectSetupSiteStatus(models.TextChoices):
    READY = 'ready', 'Ready'
    IN_PROGRESS = 'in_progress', 'In Progress'
    NOT_STARTED = 'not_started', 'Not Started'


class ProjectSetupReviewStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted (Awaiting RMT Review)'
    UNDER_REVIEW = 'under_review', 'Under RMT Review'
    APPROVED = 'approved', 'Approved'
    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
    REJECTED = 'rejected', 'Rejected'


class ProjectSetup(models.Model):
    project = models.OneToOneField(Project, related_name='project_setup', on_delete=models.CASCADE)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='project_setups', on_delete=models.CASCADE)
    team_roster_file = models.FileField(upload_to='project_setup/team_rosters/', null=True, blank=True)
    equipment_plan_file = models.FileField(upload_to='project_setup/equipment_plans/', null=True, blank=True)
    site_status = models.CharField(
        max_length=24,
        choices=ProjectSetupSiteStatus.choices,
        default=ProjectSetupSiteStatus.NOT_STARTED,
    )
    work_schedule_start = models.DateField(null=True, blank=True)
    work_schedule_end = models.DateField(null=True, blank=True)
    compliance_docs_file = models.FileField(upload_to='project_setup/compliance_docs/', null=True, blank=True)
    insurance_certificate_file = models.FileField(upload_to='project_setup/insurance/', null=True, blank=True)
    device_model = models.CharField(max_length=255, blank=True)
    device_brand = models.CharField(max_length=255, blank=True)
    tech_tier = models.PositiveSmallIntegerField(null=True, blank=True)
    meter_api_endpoint = models.URLField(blank=True)
    meter_api_token_encrypted = models.TextField(blank=True)
    manual_verification_confirmed = models.BooleanField(default=False)
    checklist_team_ready = models.BooleanField(default=False)
    checklist_equipment_ready = models.BooleanField(default=False)
    checklist_site_ready = models.BooleanField(default=False)
    checklist_safety_ready = models.BooleanField(default=False)
    checklist_logistics_ready = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=32,
        choices=ProjectSetupReviewStatus.choices,
        default=ProjectSetupReviewStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='reviewed_project_setups',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    previous_review_notes = models.TextField(blank=True)
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Setup for project {self.project_id}"

    def set_meter_api_token(self, raw_token: str):
        token = str(raw_token or '').strip()
        if not token:
            self.meter_api_token_encrypted = ''
            return
        self.meter_api_token_encrypted = signing.dumps({'token': token}, compress=True)

    def get_meter_api_token(self) -> str:
        if not self.meter_api_token_encrypted:
            return ''
        try:
            payload = signing.loads(self.meter_api_token_encrypted)
        except signing.BadSignature:
            return ''
        return str(payload.get('token') or '')

    @property
    def has_meter_api_token(self) -> bool:
        return bool(self.get_meter_api_token())


class MilestoneStatus(models.TextChoices):
    LOCKED = 'locked', 'Locked'
    CLAIMABLE = 'claimable', 'Claimable'
    CLAIMED = 'claimed', 'Claimed'
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    LEGACY_PENDING = 'Pending', 'Pending (Legacy)'
    LEGACY_SUBMITTED = 'Submitted', 'Submitted (Legacy)'
    LEGACY_VERIFIED = 'Verified', 'Verified (Legacy)'
    LEGACY_PAID = 'Paid', 'Paid (Legacy)'


class Milestone(models.Model):
    project = models.ForeignKey(Project, related_name='milestones', on_delete=models.CASCADE)
    milestone_number = models.PositiveIntegerField(default=1)
    disbursement_pct = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    percentage = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=MilestoneStatus.choices, default=MilestoneStatus.PENDING)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount_lsl = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    progress_percentage = models.PositiveIntegerField(default=0)
    target_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project_id} - {self.name} ({self.percentage}%)"

    def save(self, *args, **kwargs):
        if self.disbursement_pct and not self.percentage:
            self.percentage = self.disbursement_pct
        elif self.percentage and not self.disbursement_pct:
            self.disbursement_pct = self.percentage
        if self.amount_lsl and not self.amount:
            self.amount = self.amount_lsl
        elif self.amount and not self.amount_lsl:
            self.amount_lsl = self.amount
        super().save(*args, **kwargs)


class ProjectUpdate(models.Model):
    project = models.ForeignKey(Project, related_name='updates', on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='project_updates',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.title:
            return f"{self.project_id} - {self.title}"
        return f"{self.project_id} update {self.id}"


class ProjectDocument(models.Model):
    project = models.ForeignKey(Project, related_name='documents', on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='project_documents',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='project_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        if self.title:
            return f"{self.project_id} - {self.title}"
        return f"{self.project_id} document {self.id}"


class PaymentClaimStatus(models.TextChoices):
    SUBMITTED = 'Submitted', 'Submitted'
    RMT_APPROVED = 'RMT Approved', 'RMT Approved'
    TAC_ENDORSED = 'TAC Endorsed', 'TAC Endorsed'
    PSC_APPROVED = 'PSC Approved', 'PSC Approved'
    COMPLETED = 'Completed', 'Completed'
    HELD_AUDIT = 'Held/Audit', 'Held/Audit'
    REJECTED = 'Rejected', 'Rejected'
    LEGACY_PENDING = 'Pending', 'Pending (Legacy)'
    LEGACY_VERIFIED = 'Verified', 'Verified (Legacy)'
    LEGACY_APPROVED = 'Approved', 'Approved (Legacy)'
    LEGACY_PAID = 'Paid', 'Paid (Legacy)'


class InstallationStatus(models.TextChoices):
    SUBMITTED = 'Submitted'
    PAUSED = 'Paused'
    VERIFIED = 'Verified'
    FLAGGED = 'Flagged'
    TERMINATED = 'Terminated'


class GisStatus(models.TextChoices):
    GREEN = 'green'
    YELLOW = 'yellow'
    RED = 'red'


class PaymentClaim(models.Model):
    project = models.ForeignKey(Project, related_name='payment_claims', on_delete=models.CASCADE)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='payment_claims', on_delete=models.CASCADE)
    milestone = models.ForeignKey(Milestone, related_name='payment_claims', on_delete=models.SET_NULL, null=True, blank=True)
    district = models.CharField(max_length=64, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    claim_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_beneficiaries = models.PositiveIntegerField(default=0)
    actual_female_beneficiaries = models.PositiveIntegerField(default=0)
    implementation_notes = models.TextField(blank=True)
    evidence_files = models.JSONField(default=list, blank=True)
    declaration_accepted = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=PaymentClaimStatus.choices, default=PaymentClaimStatus.SUBMITTED)
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
    INITIATED = 'Initiated', 'Initiated'
    HELD_AUDIT = 'Held/Audit', 'Held/Audit'
    COMPLETED = 'Completed', 'Completed'
    FAILED = 'Failed', 'Failed'


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


class InstallationReport(models.Model):
    project = models.ForeignKey(Project, related_name='installation_reports', on_delete=models.CASCADE)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='installation_reports', on_delete=models.CASCADE)
    milestone = models.ForeignKey(Milestone, related_name='installation_reports', on_delete=models.SET_NULL, null=True, blank=True)
    gps_lat = models.DecimalField(max_digits=9, decimal_places=6)
    gps_lng = models.DecimalField(max_digits=9, decimal_places=6)
    serial_number = models.CharField(max_length=128)
    beneficiary_id = models.CharField(max_length=128)
    beneficiary_name = models.CharField(max_length=255, blank=True)
    household_type = models.CharField(max_length=64, blank=True)
    installation_date = models.DateField(null=True, blank=True)
    receipt_file = models.FileField(upload_to='installation_receipts/', null=True, blank=True)
    photo_files = models.JSONField(default=list, blank=True)
    meter_id = models.CharField(max_length=64, blank=True)
    kwh_reading = models.FloatField(default=0)
    status = models.CharField(max_length=16, choices=InstallationStatus.choices, default=InstallationStatus.SUBMITTED)
    gis_status = models.CharField(max_length=16, choices=GisStatus.choices, default=GisStatus.YELLOW)
    prospect_sync_status = models.CharField(max_length=16, choices=ProspectSyncStatus.choices, default=ProspectSyncStatus.PENDING)
    prospect_sync_error = models.TextField(blank=True)
    prospect_synced_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['gps_lat', 'gps_lng']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['gis_status']),
            models.Index(fields=['vendor', 'project']),
        ]

    def __str__(self):
        return f"Installation {self.id} - Project {self.project_id}"

    def recompute_gis_status(self, *, save: bool = False):
        has_blocking_anomaly = self.anomaly_flags.filter(is_resolved=False).exclude(flag_type='duplicate_gps').exists()
        if has_blocking_anomaly:
            self.gis_status = GisStatus.RED
        elif self.status == InstallationStatus.VERIFIED:
            self.gis_status = GisStatus.GREEN
        elif self.status == InstallationStatus.FLAGGED:
            self.gis_status = GisStatus.RED
        else:
            self.gis_status = GisStatus.YELLOW
        if save:
            self.save(update_fields=['gis_status'])
        return self.gis_status


class VerificationStatus(models.TextChoices):
    PENDING = 'Pending'
    PAUSED = 'Paused'
    PARTIAL = 'Partial'
    VERIFIED = 'Verified'
    FLAGGED = 'Flagged'
    TERMINATED = 'Terminated'


class VerificationTask(models.Model):
    report = models.OneToOneField(InstallationReport, related_name='verification_task', on_delete=models.CASCADE)
    assigned_verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='verification_tasks',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    vendor_lat = models.DecimalField(max_digits=9, decimal_places=6)
    vendor_lng = models.DecimalField(max_digits=9, decimal_places=6)
    verifier_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    verifier_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distance_meters = models.FloatField(null=True, blank=True)
    anomaly_flag = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Verification {self.id} - Report {self.report_id}"


class FieldVerificationStatus(models.TextChoices):
    VERIFIED = 'verified', 'Verified'
    FLAGGED = 'flagged', 'Flagged'
    PARTIAL = 'partial', 'Partial'


class BeneficiaryGender(models.TextChoices):
    MALE = 'male', 'Male'
    FEMALE = 'female', 'Female'
    OTHER = 'other', 'Other'
    UNKNOWN = 'unknown', 'Unknown'


class FieldVerification(models.Model):
    installation = models.ForeignKey(InstallationReport, related_name='field_verifications', on_delete=models.CASCADE)
    field_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='field_verifications',
        on_delete=models.CASCADE,
    )
    beneficiary_present = models.BooleanField(default=False)
    beneficiary_gender = models.CharField(
        max_length=16,
        choices=BeneficiaryGender.choices,
        default=BeneficiaryGender.UNKNOWN,
    )
    system_working = models.BooleanField(default=False)
    officer_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    officer_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_match = models.BooleanField(default=False)
    location_distance_meters = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    site_photos = models.JSONField(default=list, blank=True)
    serial_visible = models.BooleanField(default=False)
    observation_notes = models.CharField(max_length=500, blank=True)
    verification_status = models.CharField(
        max_length=16,
        choices=FieldVerificationStatus.choices,
        default=FieldVerificationStatus.VERIFIED,
    )
    flag_reason = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-verified_at', '-id']
        indexes = [
            models.Index(fields=['installation', 'verification_status']),
            models.Index(fields=['field_officer', 'verified_at']),
        ]

    def __str__(self):
        return f"Field verification {self.id} - installation {self.installation_id}"


class SmartMeterReading(models.Model):
    project = models.ForeignKey(Project, related_name='smart_meter_readings', on_delete=models.CASCADE)
    installation = models.ForeignKey(
        InstallationReport,
        related_name='smart_meter_readings',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    meter_id = models.CharField(max_length=64)
    kwh = models.FloatField(default=0)
    uptime_pct = models.FloatField(default=0)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.meter_id} - {self.kwh} kWh"


class AnomalyFlag(models.Model):
    installation = models.ForeignKey(InstallationReport, related_name='anomaly_flags', on_delete=models.CASCADE)
    project = models.ForeignKey(Project, related_name='anomaly_flags', on_delete=models.CASCADE)
    flag_type = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['installation', 'is_resolved']),
            models.Index(fields=['project', 'flag_type']),
        ]

    def __str__(self):
        return f"{self.flag_type} for installation {self.installation_id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.installation.recompute_gis_status(save=True)


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='audit_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor_role = models.CharField(max_length=128, blank=True)
    action = models.CharField(max_length=128)
    module = models.CharField(max_length=128, blank=True)
    entity_type = models.CharField(max_length=64, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    record_id = models.IntegerField(null=True, blank=True)
    record_type = models.CharField(max_length=64, blank=True)
    old_status = models.CharField(max_length=128, blank=True)
    new_status = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"


class GeneratedReport(models.Model):
    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        PDF = "pdf", "PDF"
        EXCEL = "excel", "Excel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=128)
    format = models.CharField(max_length=16, choices=Format.choices)
    filters = models.JSONField(default=dict, blank=True)
    scope_label = models.CharField(max_length=255, blank=True)

    project = models.ForeignKey(
        "Project",
        related_name="generated_reports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="generated_reports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to="generated-reports/%Y/%m/%d/")

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["report_type", "generated_at"]),
            models.Index(fields=["generated_by", "generated_at"]),
        ]

    def __str__(self):
        return f"{self.report_type} ({self.format}) {self.id}"


class ProspectSyncLog(models.Model):
    method_name = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)
    record_id = models.IntegerField(null=True, blank=True)
    record_type = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=ProspectSyncStatus.choices, default=ProspectSyncStatus.PENDING)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['method_name']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.method_name} ({self.status})"


class ConcernType(models.TextChoices):
    KPI_ISSUE = 'kpi_issue', 'KPI Issue'
    GPS_ISSUE = 'gps_issue', 'GPS / Location Issue'
    VERIFICATION_ISSUE = 'verification_issue', 'Field Verification Issue'
    VENDOR_BEHAVIOUR = 'vendor_behaviour', 'Vendor Behaviour'
    INSTALLATION_QUALITY = 'installation_quality', 'Installation Quality'
    DATA_DISCREPANCY = 'data_discrepancy', 'Data Discrepancy'
    OTHER = 'other', 'Other'


class ConcernSeverity(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class ConcernStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    UNDER_INVESTIGATION = 'under_investigation', 'Under Investigation'
    RESOLVED = 'resolved', 'Resolved'
    DISMISSED = 'dismissed', 'Dismissed'
    ESCALATED_TO_PSC = 'escalated_to_psc', 'Escalated to PSC'


class Concern(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    raised_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='raised_concerns')
    concern_type = models.CharField(max_length=32, choices=ConcernType.choices)
    severity = models.CharField(max_length=16, choices=ConcernSeverity.choices)
    linked_project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='concerns', null=True, blank=True
    )
    linked_installation = models.ForeignKey(
        'InstallationReport', on_delete=models.CASCADE,
        related_name='concerns', null=True, blank=True
    )
    description = models.TextField()
    evidence_files = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=24, choices=ConcernStatus.choices,
        default=ConcernStatus.OPEN
    )
    notify_rmt = models.BooleanField(default=True)
    notify_psc = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['raised_by']),
            models.Index(fields=['status']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"{self.id} - {self.concern_type} ({self.severity})"

    def save(self, *args, **kwargs):
        if not self.id:
            last_concern = Concern.objects.order_by('-created_at').first()
            next_num = 1 if not last_concern else int(last_concern.id.split('-')[1]) + 1
            self.id = f"CNC-{next_num:03d}"
        super().save(*args, **kwargs)


class ConcernResponse(models.Model):
    concern = models.ForeignKey(
        Concern, on_delete=models.CASCADE,
        related_name='responses'
    )
    responded_by = models.ForeignKey('users.User', on_delete=models.CASCADE)
    response_text = models.TextField()
    action_taken = models.CharField(max_length=32, blank=True)
    evidence_files = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Response to {self.concern_id}"


class FindingCategory(models.TextChoices):
    PAYMENT_COMPLIANCE = 'payment_compliance', 'Payment Compliance'
    APPROVAL_CHAIN_VIOLATION = 'approval_chain_violation', 'Approval Chain Violation'
    DATA_INTEGRITY = 'data_integrity', 'Data Integrity'
    GPS_FRAUD = 'gps_fraud', 'GPS / Location Fraud'
    KPI_MANIPULATION = 'kpi_manipulation', 'KPI Manipulation'
    DOCUMENT_IRREGULARITY = 'document_irregularity', 'Document Irregularity'
    PROCESS_VIOLATION = 'process_violation', 'Process Violation'
    CONFLICT_OF_INTEREST = 'conflict_of_interest', 'Conflict of Interest'
    OTHER = 'other', 'Other Compliance Issue'


class FindingRiskLevel(models.TextChoices):
    OBSERVATION = 'observation', 'Observation'
    MINOR = 'minor', 'Minor Finding'
    MAJOR = 'major', 'Major Finding'
    CRITICAL = 'critical', 'Critical'


class AuditFinding(models.Model):
    id = models.CharField(max_length=24, primary_key=True)
    raised_by = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='raised_findings'
    )
    finding_category = models.CharField(
        max_length=32, choices=FindingCategory.choices
    )
    risk_level = models.CharField(
        max_length=16, choices=FindingRiskLevel.choices
    )
    linked_project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='audit_findings', null=True, blank=True
    )
    linked_claim = models.ForeignKey(
        'PaymentClaim', on_delete=models.CASCADE,
        related_name='audit_findings', null=True, blank=True
    )
    linked_installation = models.ForeignKey(
        'InstallationReport', on_delete=models.CASCADE,
        related_name='audit_findings', null=True, blank=True
    )
    description = models.TextField()
    recommended_action = models.TextField(blank=True)
    evidence_files = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=24, choices=ConcernStatus.choices,
        default=ConcernStatus.OPEN
    )
    rised_to_rmt = models.BooleanField(default=True)
    rised_to_psc = models.BooleanField(default=True)
    rised_to_super_admin = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    rmt_response = models.TextField(blank=True, default="")
    rmt_response_action = models.CharField(max_length=32, blank=True, default="")
    rmt_responded_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='audit_finding_responses', null=True, blank=True
    )
    rmt_responded_at = models.DateTimeField(null=True, blank=True)
    psc_comment = models.TextField(blank=True, default="")
    psc_commented_at = models.DateTimeField(null=True, blank=True)
    psc_commented_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='audit_finding_psc_comments', null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['raised_by']),
            models.Index(fields=['status']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f"{self.id} - {self.finding_category} ({self.risk_level})"

    def save(self, *args, **kwargs):
        if not self.id:
            year = timezone.now().year
            last_finding = AuditFinding.objects.filter(
                id__startswith=f'AUD-FND-{year}'
            ).order_by('-created_at').first()
            next_num = 1 if not last_finding else int(last_finding.id.split('-')[-1]) + 1
            self.id = f"AUD-FND-{year}-{next_num:03d}"
        super().save(*args, **kwargs)
