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
    CLOSED = 'closed', 'Closed'
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
    # Set only for lot-wise tenders. A vendor can win several lots under one bid, so the
    # project must remember WHICH lot it delivers — it drives the lot-aware project
    # reference and distinguishes otherwise identical projects from the same vendor.
    lot = models.ForeignKey('tenders.TenderLot', related_name='projects', on_delete=models.SET_NULL, null=True, blank=True)
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
    # Set when the project completes. An archived project and every record under it
    # (milestones, installations, verifications, claims, meter data...) is read-only and
    # leaves the operational lists; see rbf.projects.archive.
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='archived_projects', on_delete=models.SET_NULL, null=True, blank=True,
    )
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
    CANCELLED = 'cancelled', 'Cancelled'
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
    # Checklist threshold set on the Milestone Assignment form: share (%) of the
    # project's installation target that must be verified before this milestone
    # becomes claimable. 0 = no installation requirement (e.g. M1).
    required_installation_pct = models.PositiveIntegerField(default=0)
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


class MilestoneReviewStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Verification'
    DECIDED = 'decided', 'Decided'


class MilestoneReviewDecision(models.TextChoices):
    PROCEED = 'proceed', 'Proceed to Next Milestone'
    CLOSE = 'close', 'Close Project'
    TRANSFER = 'transfer', 'Transfer to Another Vendor'
    COMPLETE = 'complete', 'Complete Project'


class MilestoneCompletionReview(models.Model):
    """RBF / Super Admin verification opened when a milestone is paid. The next
    milestone cannot unlock until the decision is 'proceed' (or 'transfer', which
    hands the remaining milestones to a new vendor)."""

    milestone = models.OneToOneField(Milestone, related_name='completion_review', on_delete=models.CASCADE)
    project = models.ForeignKey(Project, related_name='milestone_reviews', on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=MilestoneReviewStatus.choices, default=MilestoneReviewStatus.PENDING)
    decision = models.CharField(max_length=16, choices=MilestoneReviewDecision.choices, blank=True, default='')
    verification_notes = models.TextField(blank=True)
    vendor_id = models.CharField(max_length=64, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    transferred_to_vendor_id = models.CharField(max_length=64, blank=True)
    transferred_to_vendor_name = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='milestone_completion_reviews',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for milestone {self.milestone_id} ({self.status})"


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
    # Contact number for the beneficiary household. Optional (many installations are
    # recorded without one) and treated as PII: masked for TAC/Auditor and withheld from
    # DOE Officer / UNDP Donor in InstallationReportSerializer.to_representation. The
    # prospect sync hashes it rather than sending it in clear (see integrations.py).
    beneficiary_phone = models.CharField(max_length=32, blank=True)
    # District the installation was captured in: one of the project's districts, which
    # for a lot-wise project can differ from the project's primary `district`.
    district = models.CharField(max_length=128, blank=True, default='')
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
    REVERIFICATION_REQUIRED = 'Reverification Required'


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
    status = models.CharField(max_length=32, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    # Each re-verification starts a new round; earlier FieldVerification records are kept untouched.
    verification_round = models.PositiveIntegerField(default=1)
    reverification_reason = models.TextField(blank=True)
    reverification_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='requested_reverifications',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reverification_requested_at = models.DateTimeField(null=True, blank=True)
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
    verification_round = models.PositiveIntegerField(default=1)
    verified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-verified_at', '-id']
        indexes = [
            models.Index(fields=['installation', 'verification_status']),
            models.Index(fields=['field_officer', 'verified_at']),
        ]

    def __str__(self):
        return f"Field verification {self.id} - installation {self.installation_id}"


class MeterDataBatchStatus(models.TextChoices):
    # Clean upload awaiting an RBF / Super Admin look; its readings count meanwhile.
    PENDING_REVIEW = 'pending_review', 'Pending Review'
    # Automated integrity checks found high-severity problems; blocks milestone claims
    # until an RBF Official / Super Admin verifies or rejects it.
    FLAGGED = 'flagged', 'Flagged'
    VERIFIED = 'verified', 'Verified'
    REJECTED = 'rejected', 'Rejected'
    # Readings excluded and milestone claims blocked until the vendor uploads again.
    CORRECTION_REQUESTED = 'correction_requested', 'Correction Requested'
    # A correction was requested and the vendor has since uploaded a new batch.
    SUPERSEDED = 'superseded', 'Superseded'


# Batch states that keep the project's milestones from becoming claimable.
MILESTONE_BLOCKING_BATCH_STATUSES = (MeterDataBatchStatus.FLAGGED, MeterDataBatchStatus.CORRECTION_REQUESTED)


class MeterDataBatch(models.Model):
    """One vendor meter-data upload, so every reading can be traced to who submitted it
    and when, reviewed as a unit, and rejected if it is not genuine."""

    project = models.ForeignKey(Project, related_name='meter_data_batches', on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='meter_data_batches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source_document = models.ForeignKey(
        ProjectDocument,
        related_name='meter_data_batches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    file_name = models.CharField(max_length=255, blank=True)
    rows_ingested = models.PositiveIntegerField(default=0)
    rows_rejected_on_upload = models.PositiveIntegerField(default=0)
    # [{row, meter_id, errors}] kept so the vendor and reviewer can see why a row was
    # dropped after the upload response is gone. Capped at REJECTED_ROWS_STORED.
    rejected_rows = models.JSONField(default=list, blank=True)
    # [{code, severity, message, meter_id, reading_ids}] from integrity checks at upload.
    integrity_findings = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=MeterDataBatchStatus.choices, default=MeterDataBatchStatus.PENDING_REVIEW)
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='reviewed_meter_data_batches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    correction_due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', 'status'])]

    def __str__(self):
        return f"Meter batch {self.id} - project {self.project_id} ({self.status})"


class SmartMeterReadingSource(models.TextChoices):
    CSV_UPLOAD = 'csv_upload', 'CSV Upload'
    INSTALLATION_REPORT = 'installation_report', 'Installation Report'
    API = 'api', 'API'
    LEGACY = 'legacy', 'Legacy (before provenance tracking)'


class SmartMeterReadingReviewStatus(models.TextChoices):
    ACCEPTED = 'accepted', 'Accepted'
    # Excluded from KPIs and milestone eligibility.
    REJECTED = 'rejected', 'Rejected'


class SmartMeterReading(models.Model):
    project = models.ForeignKey(Project, related_name='smart_meter_readings', on_delete=models.CASCADE)
    installation = models.ForeignKey(
        InstallationReport,
        related_name='smart_meter_readings',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    batch = models.ForeignKey(
        MeterDataBatch,
        related_name='readings',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=32, choices=SmartMeterReadingSource.choices, default=SmartMeterReadingSource.LEGACY)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='submitted_meter_readings',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    meter_id = models.CharField(max_length=64)
    kwh = models.FloatField(default=0)
    uptime_pct = models.FloatField(default=0)
    output_power_w = models.FloatField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Integrity check codes this reading tripped at upload (see meter_integrity.py).
    integrity_flags = models.JSONField(default=list, blank=True)
    review_status = models.CharField(
        max_length=16,
        choices=SmartMeterReadingReviewStatus.choices,
        default=SmartMeterReadingReviewStatus.ACCEPTED,
    )
    rejection_reason = models.TextField(blank=True)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [models.Index(fields=['project', 'meter_id', 'recorded_at'])]

    def __str__(self):
        return f"{self.meter_id} - {self.kwh} kWh"


class AnomalyFlagStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    UNDER_INVESTIGATION = 'under_investigation', 'Under Investigation'
    CORRECTION_REQUESTED = 'correction_requested', 'Correction Requested'
    AWAITING_EVIDENCE = 'awaiting_evidence', 'Awaiting Evidence'
    RESOLVED = 'resolved', 'Resolved'
    FALSE_POSITIVE = 'false_positive', 'False Positive'
    ESCALATED = 'escalated', 'Escalated'
    REOPENED = 'reopened', 'Reopened'


class AnomalyFlag(models.Model):
    installation = models.ForeignKey(InstallationReport, related_name='anomaly_flags', on_delete=models.CASCADE)
    project = models.ForeignKey(Project, related_name='anomaly_flags', on_delete=models.CASCADE)
    flag_type = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=AnomalyFlagStatus.choices, default=AnomalyFlagStatus.OPEN)
    severity = models.CharField(max_length=16, choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='assigned_anomaly_flags', on_delete=models.SET_NULL, null=True, blank=True)
    investigation_notes = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    resolution_reason = models.TextField(blank=True)
    evidence_reference = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
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


class AnomalyReviewEvent(models.Model):
    flag = models.ForeignKey(AnomalyFlag, related_name='review_events', on_delete=models.CASCADE)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='anomaly_review_events',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor_role = models.CharField(max_length=64, blank=True)
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    investigation_notes = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    resolution_reason = models.TextField(blank=True)
    evidence_reference = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review event for flag {self.flag_id}: {self.from_status or '—'} → {self.to_status}"


class AnomalyEvidenceFile(models.Model):
    flag = models.ForeignKey(AnomalyFlag, related_name='evidence_files', on_delete=models.CASCADE)
    file = models.CharField(max_length=512)
    original_name = models.CharField(max_length=256, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='anomaly_evidence_files',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"Evidence {self.original_name} for flag {self.flag_id}"


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
        GEOJSON = "geojson", "GeoJSON"
        XML = "xml", "IATI XML"
        ZIP = "zip", "ZIP package"

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
    file = models.FileField(upload_to="generated-reports/%Y/%m/%d/", null=True, blank=True)

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Generating"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    # Reports are generated in the background (see report_queue); the row is the job.
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    title = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    row_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Approval(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        RETURNED = "returned", "Returned for correction"

    # Formal reports (results, PSC packs, verification) are reviewed and approved before they are
    # distributed; the file never changes, so a correction is a new version that supersedes this one.
    approval_status = models.CharField(max_length=16, choices=Approval.choices, default=Approval.NOT_REQUIRED)
    version = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey("self", related_name="superseded_by", on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    schedule = models.ForeignKey("ReportSchedule", related_name="runs", on_delete=models.SET_NULL, null=True, blank=True)
    distributed_at = models.DateTimeField(null=True, blank=True)
    distributed_to = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="received_reports", blank=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["report_type", "generated_at"]),
            models.Index(fields=["generated_by", "generated_at"]),
            models.Index(fields=["status", "generated_at"]),
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


class SiteVisitFollowUpStatus(models.TextChoices):
    NONE = 'none', 'No Follow-up Needed'
    OPEN = 'open', 'Open'
    IN_PROGRESS = 'in_progress', 'In Progress'
    CLOSED = 'closed', 'Closed'


class SiteMonitoringVisit(models.Model):
    """A DoE officer's record of a regional site monitoring visit."""

    project = models.ForeignKey(Project, related_name='monitoring_visits', on_delete=models.CASCADE)
    installation = models.ForeignKey(
        InstallationReport,
        related_name='monitoring_visits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    visited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='monitoring_visits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    visit_date = models.DateField()
    system_working = models.BooleanField(null=True, blank=True)
    beneficiary_present = models.BooleanField(null=True, blank=True)
    observations = models.TextField()
    follow_up_action = models.TextField(blank=True)
    follow_up_status = models.CharField(
        max_length=16,
        choices=SiteVisitFollowUpStatus.choices,
        default=SiteVisitFollowUpStatus.NONE,
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']
        indexes = [models.Index(fields=['project', 'visit_date'])]

    def __str__(self):
        return f"Visit {self.id} to {self.project_id} on {self.visit_date}"


class SiteMonitoringPhoto(models.Model):
    visit = models.ForeignKey(SiteMonitoringVisit, related_name='photos', on_delete=models.CASCADE)
    file = models.FileField(upload_to='monitoring_visits/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']


class KpiReviewRating(models.TextChoices):
    ON_TRACK = 'on_track', 'On Track'
    NEEDS_ATTENTION = 'needs_attention', 'Needs Attention'
    AT_RISK = 'at_risk', 'At Risk'


class KpiReview(models.Model):
    """A DoE officer's periodic review of a project's KPI performance."""

    project = models.ForeignKey(Project, related_name='kpi_reviews', on_delete=models.CASCADE)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='kpi_reviews',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    review_period = models.CharField(max_length=7, help_text='Reporting month, YYYY-MM.')
    rating = models.CharField(max_length=24, choices=KpiReviewRating.choices)
    uptime_comment = models.TextField(blank=True)
    beneficiary_comment = models.TextField(blank=True)
    gender_inclusion_comment = models.TextField(blank=True)
    summary = models.TextField()
    recommendations = models.TextField(blank=True)
    kpi_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-review_period', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'reviewer', 'review_period'],
                name='unique_kpi_review_per_reviewer_period',
            ),
        ]

    def __str__(self):
        return f"KPI review {self.project_id} {self.review_period} ({self.rating})"


class OversightSubject(models.TextChoices):
    PROJECT = 'project', 'Project'
    VERIFICATION = 'verification', 'Verification'
    KPI = 'kpi', 'KPI'
    VENDOR = 'vendor', 'Vendor Performance'
    DISBURSEMENT = 'disbursement', 'Disbursement'
    MONITORING = 'monitoring', 'Monitoring'


class OversightReviewStatus(models.TextChoices):
    COMPLIANT = 'compliant', 'Compliant'
    DELAYED = 'delayed', 'Delayed'
    FLAGGED = 'flagged', 'Flagged'
    COMMENT = 'comment', 'Comment'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    REVERIFICATION_REQUESTED = 'reverification_requested', 'Re-verification Requested'


class OversightFollowUpStatus(models.TextChoices):
    NONE = 'none', 'No Follow-up'
    OPEN = 'open', 'Open'
    IN_PROGRESS = 'in_progress', 'In Progress'
    RESOLVED = 'resolved', 'Resolved'


class OversightReview(models.Model):
    """One shared record for oversight reviews, flags and comments on existing project data.

    DoE, PSC and RMT all write here, about the same underlying project, verification, KPI,
    vendor and disbursement records; the role of the reviewer is stored, the data is not copied.
    """

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True,
    )
    reviewer_role = models.CharField(max_length=64, blank=True)
    subject_type = models.CharField(max_length=16, choices=OversightSubject.choices)
    review_status = models.CharField(max_length=32, choices=OversightReviewStatus.choices)
    project = models.ForeignKey(Project, related_name='oversight_reviews', on_delete=models.CASCADE, null=True, blank=True)
    milestone = models.ForeignKey(Milestone, related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True)
    verification_task = models.ForeignKey(
        VerificationTask, related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True,
    )
    verification_round = models.PositiveIntegerField(null=True, blank=True)
    payment_claim = models.ForeignKey(PaymentClaim, related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='vendor_oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True,
    )
    kpi_review = models.ForeignKey('KpiReview', related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True)
    monitoring_visit = models.ForeignKey(
        'SiteMonitoringVisit', related_name='oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True,
    )
    comment = models.TextField()
    issue_category = models.CharField(max_length=64, blank=True)
    action_required = models.TextField(blank=True)
    follow_up_status = models.CharField(
        max_length=16, choices=OversightFollowUpStatus.choices, default=OversightFollowUpStatus.NONE,
    )
    follow_up_date = models.DateField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='resolved_oversight_reviews', on_delete=models.SET_NULL, null=True, blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subject_type', 'review_status']),
            models.Index(fields=['follow_up_status']),
            models.Index(fields=['reviewer_role']),
        ]

    def __str__(self):
        return f"{self.get_review_status_display()} {self.subject_type} review {self.id}"



class AuditArea(models.TextChoices):
    PROCUREMENT = 'procurement', 'Procurement'
    VENDOR = 'vendor', 'Vendor'
    CONTRACT = 'contract', 'Contract'
    VERIFICATION = 'verification', 'Verification / GPS Evidence'
    KPI = 'kpi', 'KPI'
    DISBURSEMENT = 'disbursement', 'Disbursement'
    SYSTEM_ACCESS = 'system_access', 'System Access'
    OTHER = 'other', 'Other'


class AuditCaseType(models.TextChoices):
    AUDIT = 'audit', 'Audit Case'
    COMPLIANCE_REVIEW = 'compliance_review', 'Compliance Review'


class AuditCaseStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    UNDER_REVIEW = 'under_review', 'Under Review'
    EVIDENCE_COLLECTED = 'evidence_collected', 'Evidence Collected'
    FINDING_RECORDED = 'finding_recorded', 'Finding Recorded'
    MANAGEMENT_RESPONSE = 'management_response', 'Management Response'
    FINALIZED = 'finalized', 'Audit Finalized'
    CLOSED = 'closed', 'Closed'


class AuditFindingType(models.TextChoices):
    COMPLIANT = 'compliant', 'No Exception (Compliant)'
    OBSERVATION = 'observation', 'Observation'
    EXCEPTION = 'exception', 'Exception'
    NON_COMPLIANCE = 'non_compliance', 'Non-compliance'


class AuditRiskLevel(models.TextChoices):
    OBSERVATION = 'observation', 'Observation'
    MINOR = 'minor', 'Minor'
    MAJOR = 'major', 'Major'
    CRITICAL = 'critical', 'Critical'


class CorrectiveActionStatus(models.TextChoices):
    NOT_REQUIRED = 'not_required', 'Not Required'
    OPEN = 'open', 'Open'
    IN_PROGRESS = 'in_progress', 'In Progress'
    IMPLEMENTED = 'implemented', 'Implemented'
    VERIFIED = 'verified', 'Verified by Auditor'


class AuditCase(models.Model):
    """An independent audit (or compliance review) over existing source records.

    The case links to the records it examines; it never copies or changes them. Only the
    Auditor moves a case through its workflow; the RBF Management Team supplies the
    management response and corrective-action progress.
    """

    reference = models.CharField(max_length=32, unique=True)
    case_type = models.CharField(max_length=24, choices=AuditCaseType.choices, default=AuditCaseType.AUDIT)
    audit_area = models.CharField(max_length=24, choices=AuditArea.choices)
    title = models.CharField(max_length=255)
    scope = models.TextField()
    status = models.CharField(max_length=24, choices=AuditCaseStatus.choices, default=AuditCaseStatus.DRAFT)
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True,
    )

    project = models.ForeignKey(Project, related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='vendor_audit_cases', on_delete=models.SET_NULL, null=True, blank=True,
    )
    tender = models.ForeignKey('tenders.Tender', related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True)
    contract = models.ForeignKey(
        'tenders.TenderContract', related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True,
    )
    payment_claim = models.ForeignKey(PaymentClaim, related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True)
    verification_task = models.ForeignKey(
        VerificationTask, related_name='audit_cases', on_delete=models.SET_NULL, null=True, blank=True,
    )

    criteria = models.TextField(blank=True, help_text='Rule, policy or SRS requirement the records were tested against.')
    finding_type = models.CharField(max_length=24, choices=AuditFindingType.choices, blank=True)
    risk_level = models.CharField(max_length=16, choices=AuditRiskLevel.choices, blank=True)
    finding = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    finding_recorded_at = models.DateTimeField(null=True, blank=True)

    response_requested_at = models.DateTimeField(null=True, blank=True)
    management_response = models.TextField(blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='audit_case_responses', on_delete=models.SET_NULL, null=True, blank=True,
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    corrective_action = models.TextField(blank=True)
    corrective_action_owner = models.CharField(max_length=255, blank=True)
    corrective_action_due = models.DateField(null=True, blank=True)
    corrective_action_status = models.CharField(
        max_length=16, choices=CorrectiveActionStatus.choices, default=CorrectiveActionStatus.NOT_REQUIRED,
    )

    conclusion = models.TextField(blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['audit_area', 'status']),
            models.Index(fields=['case_type']),
        ]

    def __str__(self):
        return f"{self.reference} ({self.get_status_display()})"


class AuditEvidenceKind(models.TextChoices):
    FILE = 'file', 'File'
    RECORD = 'record', 'Source Record Reference'
    NOTE = 'note', 'Working Note'


class AuditEvidence(models.Model):
    """Append-only evidence on an audit case: a file, a pointer to a source record, or a note."""

    case = models.ForeignKey(AuditCase, related_name='evidence', on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, choices=AuditEvidenceKind.choices)
    description = models.TextField()
    file = models.FileField(upload_to='audit_evidence/', null=True, blank=True)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='audit_evidence', on_delete=models.SET_NULL, null=True, blank=True,
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['added_at', 'id']


class ProjectArchive(models.Model):
    """The archived record of a project's whole lifecycle, from tender creation to completion
    and contract closure.

    Written once when the project is archived and never changed. If the Super Admin restores
    the project, this record is kept (marked superseded) and a new one is written when the
    project is archived again.
    """

    project = models.ForeignKey(Project, related_name='archives', on_delete=models.PROTECT)
    tender = models.ForeignKey('tenders.Tender', related_name='project_archives', on_delete=models.SET_NULL, null=True, blank=True)
    contract = models.ForeignKey(
        'tenders.TenderContract', related_name='project_archives', on_delete=models.SET_NULL, null=True, blank=True,
    )
    archived_at = models.DateTimeField(auto_now_add=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='project_archive_records', on_delete=models.SET_NULL, null=True, blank=True,
    )
    reason = models.CharField(max_length=255, blank=True)
    lifecycle_started_at = models.DateTimeField(null=True, blank=True, help_text='Tender creation.')
    lifecycle_ended_at = models.DateTimeField(null=True, blank=True, help_text='Project completion and contract closure.')
    timeline = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    dossier = models.FileField(upload_to='project_archives/', null=True, blank=True)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-archived_at']

    def __str__(self):
        return f"Archive of project {self.project_id} ({self.archived_at:%Y-%m-%d})"


class ResultsMeasure(models.TextChoices):
    VERIFIED_INSTALLATIONS = 'verified_installations', 'Verified installations (connections)'
    FEMALE_HEADED_SHARE = 'female_headed_share', 'Female-headed households (% of verified)'
    VULNERABLE_SHARE = 'vulnerable_share', 'Vulnerable households (% of verified)'
    LOW_INCOME_SHARE = 'low_income_share', 'Low-income households (% of verified)'
    BENEFICIARIES = 'beneficiaries', 'Beneficiaries reported in paid claims'
    FEMALE_BENEFICIARIES = 'female_beneficiaries', 'Female beneficiaries reported in paid claims'
    ENERGY_KWH = 'energy_kwh', 'Energy delivered (kWh, meter readings)'
    AVERAGE_UPTIME = 'average_uptime', 'Average system uptime (%)'
    AMOUNT_DISBURSED = 'amount_disbursed', 'Amount disbursed (LSL, paid claims)'
    PROJECTS_COMPLETED = 'projects_completed', 'Projects completed'
    MANUAL = 'manual', 'Entered manually (not measured by the platform)'


class ResultsIndicator(models.Model):
    """One line of the programme results framework (logframe): baseline, target and how the
    actual value is obtained. Maintained by the Super Admin; read by the Results report."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=32, blank=True)
    measure = models.CharField(max_length=32, choices=ResultsMeasure.choices)
    technology = models.CharField(max_length=64, blank=True, help_text='Limit the measure to one technology (optional).')
    baseline = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    target = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    manual_actual = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    manual_actual_as_of = models.DateField(null=True, blank=True)
    source_note = models.TextField(blank=True, help_text='Where the target comes from (e.g. EU Action Document).')
    position = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'code']

    def __str__(self):
        return f'{self.code} {self.name}'


class ReportSchedule(models.Model):
    """A report generated automatically every month or quarter and sent to a distribution list.

    The report is prepared with the role and data scope of `prepared_by`. Formal reports go to
    review and are distributed once approved; others are distributed as soon as they are ready.
    """

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly (previous month)"
        QUARTERLY = "quarterly", "Quarterly (previous quarter)"

    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=64)
    format = models.CharField(max_length=16, choices=GeneratedReport.Format.choices, default=GeneratedReport.Format.PDF)
    frequency = models.CharField(max_length=16, choices=Frequency.choices)
    run_day = models.PositiveSmallIntegerField(default=5, help_text="Day of the month the report runs (1-28).")
    filters = models.JSONField(default=dict, blank=True)
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="prepared_report_schedules", on_delete=models.PROTECT)
    recipient_roles = models.JSONField(default=list, blank=True)
    recipient_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="report_subscriptions", blank=True)
    active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.frequency})"
