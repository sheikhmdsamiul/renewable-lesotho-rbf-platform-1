from django.db import models
from django.conf import settings
from django.utils import timezone


class TenderStatus(models.TextChoices):
    DRAFT = 'Draft'
    PUBLISHED = 'Published'
    EVALUATION = 'Evaluation'
    AWARDED = 'Awarded'
    CLOSED = 'Closed'


class BidStatus(models.TextChoices):
    DRAFT = 'Draft'
    SUBMITTED = 'Submitted'
    UNDER_REVIEW = 'Under Review'
    REVISION_REQUIRED = 'Revision Required'
    AWARDED = 'Awarded'
    ACCEPTED = 'Accepted'
    REJECTED = 'Rejected'
    WITHDRAWN = 'Withdrawn'


class BidStage1Status(models.TextChoices):
    DRAFT = 'Draft'
    SUBMITTED = 'Submitted'
    SHORTLISTED = 'Shortlisted'
    REJECTED = 'Rejected'


class BidStage2Status(models.TextChoices):
    DRAFT = 'Draft'
    SUBMITTED = 'Submitted'
    EVALUATED = 'Evaluated'
    AWARDED = 'Awarded'
    NOT_AWARDED = 'Not Awarded'


class Tender(models.Model):
    reference_number = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=255)
    category = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=TenderStatus.choices, default=TenderStatus.DRAFT)
    deadline = models.DateTimeField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    application_type = models.CharField(max_length=64, blank=True)
    stage_type = models.CharField(max_length=64, blank=True)
    procurement_method = models.CharField(max_length=64, blank=True)
    address_for_document = models.CharField(max_length=255, blank=True)
    address_for_security = models.CharField(max_length=255, blank=True)
    place_for_opening = models.CharField(max_length=255, blank=True)
    bidders_eligibility = models.TextField(blank=True)
    time_for_completion = models.CharField(max_length=128, blank=True)
    invited_by = models.CharField(max_length=255, blank=True)
    bidding_currency = models.CharField(max_length=64, blank=True)
    instruction = models.TextField(blank=True)
    last_date_security = models.DateTimeField(null=True, blank=True)
    last_date_submission = models.DateTimeField(null=True, blank=True)
    date_opening = models.DateTimeField(null=True, blank=True)
    pre_tender_meeting_info = models.TextField(blank=True)
    bidders_schedule_purchase = models.BooleanField(default=False)
    tender_security_required = models.BooleanField(default=False)
    contact_details = models.CharField(max_length=255, blank=True)
    technology_types = models.JSONField(default=list, blank=True)
    target_districts = models.JSONField(default=list, blank=True)
    target_site_type = models.CharField(max_length=64, blank=True)
    schedule_file = models.FileField(upload_to='tender_schedules/', blank=True)
    rfp_documents_file = models.FileField(upload_to='tender_documents/', blank=True)
    milestone_payment_schedule_file = models.FileField(upload_to='tender_documents/', blank=True)
    trading_license_file = models.FileField(upload_to='tender_documents/', blank=True)
    tax_clearance_file = models.FileField(upload_to='tender_documents/', blank=True)
    company_registration_file = models.FileField(upload_to='tender_documents/', blank=True)
    experience_portfolio_file = models.FileField(upload_to='tender_documents/', blank=True)
    is_verified = models.BooleanField(default=False)
    funding_source = models.CharField(max_length=128, blank=True)
    technical_weight = models.PositiveIntegerField(default=70)
    financial_weight = models.PositiveIntegerField(default=30)
    technical_threshold = models.PositiveIntegerField(default=70)
    cooling_off_days = models.PositiveIntegerField(default=7)
    awarded_vendor_id = models.CharField(max_length=64, blank=True)
    awarded_vendor_name = models.CharField(max_length=255, blank=True)
    intent_to_award_bid = models.ForeignKey(
        'TenderBid',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='intent_awards',
    )
    intent_to_award_at = models.DateTimeField(null=True, blank=True)
    cooling_off_until = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Security verification fields
    security_deposit_verified = models.BooleanField(default=False)
    security_deposit_verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['deadline']),
            models.Index(fields=['department']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"{self.reference_number} - {self.name}"


class TenderBid(models.Model):
    """Track vendor bids/submissions for tenders"""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='bids')
    vendor_id = models.CharField(max_length=64)
    vendor_name = models.CharField(max_length=255)
    vendor_email = models.EmailField(blank=True)
    
    # Bid content
    bid_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    subsidy_requested = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    proposal_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    stage = models.CharField(max_length=64, blank=True)  # e.g., "Pre-Qualification", "Site-Specific"
    concept_note = models.TextField(blank=True)  # For Stage 1
    technical_proposal = models.TextField(blank=True)  # For Stage 2
    financial_proposal = models.TextField(blank=True)  # For Stage 2
    system_configuration = models.JSONField(default=dict, blank=True)
    boq_items = models.JSONField(default=list, blank=True)
    boq_details = models.JSONField(default=list, blank=True)
    device_brand_model = models.CharField(max_length=255, blank=True)
    tech_tier = models.CharField(max_length=16, blank=True)
    energy_target_kwh_month = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    technical_proposal_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    financial_proposal_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    boq_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    gender_action_plan_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    implementation_plan_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    om_plan_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    reporting_templates_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    distribution_map_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    female_target_pct = models.PositiveIntegerField(default=50)
    vulnerable_target_pct = models.PositiveIntegerField(default=30)
    low_income_target_pct = models.PositiveIntegerField(default=60)
    inclusion_commitment_confirmed = models.BooleanField(default=False)
    om_strategy_summary = models.TextField(blank=True)
    local_technicians_to_be_trained = models.PositiveIntegerField(null=True, blank=True)
    warranty_period_months = models.PositiveIntegerField(null=True, blank=True)
    offer_paygo = models.BooleanField(default=False)
    paygo_platform = models.CharField(max_length=255, blank=True)
    daily_payment_amount_lsl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    collection_method = models.CharField(max_length=64, blank=True)
    preferred_district = models.CharField(max_length=128, blank=True)
    technology_types = models.JSONField(default=list, blank=True)
    
    # Metadata
    version_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=BidStatus.choices, default=BidStatus.DRAFT)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=255, blank=True)
    rejection_reason = models.TextField(blank=True)
    stage_two_unlocked = models.BooleanField(default=False)
    stage_two_unlocked_at = models.DateTimeField(null=True, blank=True)
    stage_two_source_bid = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='stage_two_drafts',
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = ('tender', 'vendor_id', 'version_number')
        constraints = [
            models.UniqueConstraint(
                fields=['tender', 'vendor_id'],
                condition=~models.Q(status__in=[BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN, BidStatus.ACCEPTED]),
                name='uniq_tender_vendor_final_bid',
            ),
        ]
        indexes = [
            models.Index(fields=['tender', 'status']),
            models.Index(fields=['vendor_id']),
            models.Index(fields=['status']),
            models.Index(fields=['tender', 'vendor_id', 'version_number']),
        ]

    def __str__(self):
        return f"Bid from {self.vendor_name} for {self.tender.reference_number}"


class EvaluationStatus(models.TextChoices):
    PENDING = 'Pending'
    SCORED = 'Scored'


class TenderBidEvaluation(models.Model):
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=16, choices=EvaluationStatus.choices, default=EvaluationStatus.PENDING)
    technical_score = models.PositiveIntegerField(default=0)
    financial_score = models.PositiveIntegerField(default=0)
    feasibility_score = models.PositiveIntegerField(default=0)
    kpi_score = models.PositiveIntegerField(default=0)
    gender_score = models.PositiveIntegerField(default=0)
    environmental_score = models.PositiveIntegerField(default=0)
    om_score = models.PositiveIntegerField(default=0)
    inclusivity_score = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['bid']),
        ]

    def __str__(self):
        return f"Evaluation for bid {self.bid_id} ({self.status})"


class ContractStatus(models.TextChoices):
    GENERATED = 'Generated'
    SUBMITTED = 'Submitted'
    SIGNED = 'Signed'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'


class ContractSignatureStatus(models.TextChoices):
    AWAITING = 'awaiting'
    UPLOADED = 'uploaded'
    APPROVED = 'approved'


class TenderContract(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='contracts')
    bid = models.ForeignKey(TenderBid, null=True, blank=True, on_delete=models.SET_NULL, related_name='contracts')
    vendor_id = models.CharField(max_length=64)
    vendor_name = models.CharField(max_length=255)
    vendor_email = models.EmailField(blank=True)
    reference_number = models.CharField(max_length=64, unique=True)
    template_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=ContractStatus.choices, default=ContractStatus.GENERATED)
    signature_status = models.CharField(
        max_length=16,
        choices=ContractSignatureStatus.choices,
        default=ContractSignatureStatus.AWAITING,
    )
    generated_file = models.FileField(upload_to='tender_contracts/generated/', null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signed_file = models.FileField(upload_to='tender_contracts/', null=True, blank=True)
    annex_a_file = models.FileField(upload_to='tender_contracts/annexes/', null=True, blank=True)
    annex_b_file = models.FileField(upload_to='tender_contracts/annexes/', null=True, blank=True)
    annex_c_file = models.FileField(upload_to='tender_contracts/annexes/', null=True, blank=True)
    annex_d_file = models.FileField(upload_to='tender_contracts/annexes/', null=True, blank=True)
    annex_e_file = models.FileField(upload_to='tender_contracts/annexes/', null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=255, blank=True)
    rejection_reason = models.TextField(blank=True)
    milestone_plan_id = models.CharField(max_length=64, blank=True)
    project_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['tender', 'vendor_id']),
        ]

    def __str__(self):
        return f"Contract {self.reference_number} ({self.status})"


class TenderBidSite(models.Model):
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='sites')
    site_name = models.CharField(max_length=255)
    district = models.CharField(max_length=128, blank=True)
    village_sub_district = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    system_configuration = models.JSONField(default=dict, blank=True)
    boq_items = models.JSONField(default=list, blank=True)
    number_of_households = models.PositiveIntegerField(default=0)
    target_beneficiary_type = models.CharField(max_length=32, blank=True)
    estimated_energy_demand_kwh_month = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    road_access_available = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['bid']),
        ]

    def __str__(self):
        return f"{self.site_name} ({self.bid.tender.reference_number})"
