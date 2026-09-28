from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone


class TenderStatus(models.TextChoices):
    DRAFT = 'Draft'
    PENDING_PUBLISH_APPROVAL = 'Pending Publish Approval'
    PUBLISHED = 'Published'
    EVALUATION = 'Evaluation'
    STANDSTILL = 'Standstill'
    DISPUTED = 'Disputed'
    AWARDED = 'Awarded'
    CLOSED = 'Closed'


class PublishApprovalStatus(models.TextChoices):
    NOT_REQUESTED = 'not_requested', 'Not Requested'
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'


class IntentAwardRequestStatus(models.TextChoices):
    """Lifecycle of a single "issue intent to award" request awaiting Super Admin sign-off.

    PENDING is the only state in which the tender/lot is *not* yet in standstill:
    the request carries the proposed winner but nothing on the tender has moved yet,
    so bidders are never notified until a Super Admin approves."""
    PENDING = 'pending', 'Pending Super Admin Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
    WITHDRAWN = 'withdrawn', 'Withdrawn'


class BidStatus(models.TextChoices):
    DRAFT = 'Draft'
    SUBMITTED = 'Submitted'
    UNDER_REVIEW = 'Under Review'
    REVISION_REQUIRED = 'Revision Required'
    AWARDED = 'Awarded'
    ACCEPTED = 'Accepted'
    REJECTED = 'Rejected'
    WITHDRAWN = 'Withdrawn'
    NOT_AWARDED = 'Not Awarded'


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


class ProcurementWorkflow(models.TextChoices):
    """How the Technical and Financial stages are handled."""
    # EOI -> Combined: an Expression of Interest stage first; willing vendors submit an
    # EOI, the RBF shortlists, and the shortlisted vendors are invited to bid in a single
    # Combined (Technical + Financial) stage. Auto-locks the procurement method to
    # Restricted Tendering.
    EOI_COMBINED = 'eoi_combined', 'EOI → Combined'
    COMBINED = 'combined', 'Combined'          # Direct single-stage Combined (Tech + Fin together); no EOI required. Evaluated tech-then-fin such that financial is sealed until technical clearance.
    # SEQUENTIAL is retained as a legacy value so historical tenders (EOI -> Technical ->
    # Financial) keep working; it is no longer offered in the tender-creation UI.
    SEQUENTIAL = 'sequential', 'Sequential'    # Tech submission -> Tech eval -> if cleared -> Fin submission -> Fin eval


class BidStage(models.TextChoices):
    """Which stage a TenderBid record represents within a tender."""
    EOI = 'eoi', 'EOI'
    TECHNICAL = 'technical', 'Technical'
    FINANCIAL = 'financial', 'Financial'
    COMBINED = 'combined', 'Combined'


class ProcurementMethod(models.TextChoices):
    """Values use the existing long display strings as both value and label —
    matches what tenders already had stored before this field gained choices=,
    so no backfill/migration of existing data is needed."""
    OPEN = 'Open Tendering', 'Open Tendering'
    RESTRICTED = 'Restricted Tendering', 'Restricted Tendering'


class BudgetDisclosure(models.TextChoices):
    CONFIDENTIAL = 'confidential', 'Confidential'
    PUBLISHED = 'published', 'Published'


class SubmissionMethod(models.TextChoices):
    ONLINE_ONLY = 'online_only', 'Online Only'
    HYBRID = 'hybrid', 'Hybrid (Online + Physical)'


class Tender(models.Model):
    reference_number = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=255)
    category = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=TenderStatus.choices, default=TenderStatus.DRAFT)
    deadline = models.DateTimeField()
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Three-stage procurement configuration
    procurement_workflow = models.CharField(
        max_length=16,
        choices=ProcurementWorkflow.choices,
        default=ProcurementWorkflow.SEQUENTIAL,
    )
    eoi_deadline = models.DateTimeField(null=True, blank=True)
    technical_deadline = models.DateTimeField(null=True, blank=True)
    financial_deadline = models.DateTimeField(null=True, blank=True)

    application_type = models.CharField(max_length=64, blank=True)
    stage_type = models.CharField(max_length=64, blank=True)
    # Free text, not choices=ProcurementMethod.choices — existing tenders/tests already
    # store other values here (e.g. "National") beyond the frontend's two options, so a
    # hard DB-level constraint would reject legitimate existing data. ProcurementMethod
    # is only used for comparisons (== ProcurementMethod.RESTRICTED) in views.py.
    procurement_method = models.CharField(max_length=64, blank=True)
    # A tender that exists solely to run an EOI stage and shortlist vendors — it never
    # itself collects a Combined bid. Workflow is forced to eoi_combined and its own
    # technical_deadline is not required (see TenderSerializer.validate). Mutually
    # exclusive with linked_eoi_tender below (enforced in the serializer, not the DB).
    is_eoi_invite_only = models.BooleanField(default=False)
    # When set, this tender's own vendor bids skip the EOI stage entirely and open
    # directly at Combined (see _bid_stage_spec); the invited-vendor roster is copied
    # from linked_eoi_tender (see TenderSerializer._sync_linked_eoi_vendors), and name
    # is kept forced equal to linked_eoi_tender.name.
    linked_eoi_tender = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='linked_tenders',
    )
    address_for_document = models.CharField(max_length=255, blank=True)
    address_for_security = models.CharField(max_length=255, blank=True)
    place_for_opening = models.CharField(max_length=255, blank=True)
    bidders_eligibility = models.TextField(blank=True)
    time_for_completion = models.CharField(max_length=128, blank=True)
    invited_by = models.CharField(max_length=255, blank=True)
    bidding_currency = models.CharField(max_length=64, blank=True)
    # Additional currencies this tender accepts beyond its base (bidding_currency), each
    # mapped to a fixed exchange rate INTO the base currency, e.g. {"USD": "19.50"} means
    # 1 USD = 19.50 units of bidding_currency. Empty (default) = single-currency tender,
    # identical to legacy behavior. Set once at tender creation and never changes.
    currency_rates = models.JSONField(default=dict, blank=True)
    instruction = models.TextField(blank=True)
    pre_tender_meeting_info = models.TextField(blank=True)
    bidders_schedule_purchase = models.BooleanField(default=False)
    document_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    document_fee_type = models.CharField(max_length=32, blank=True)
    document_fee_refundable = models.BooleanField(default=False)
    tender_security_required = models.BooleanField(default=False)
    # The following are informational/display-only procurement metadata — nothing in the
    # bidding, evaluation, or award engines reads them (deliberately, per scope: these
    # record real-world procurement detail without changing any enforcement logic).
    language_of_bid_submission = models.CharField(max_length=64, blank=True)
    budget_disclosure = models.CharField(max_length=16, choices=BudgetDisclosure.choices, blank=True)
    clarification_deadline = models.DateTimeField(null=True, blank=True)
    site_visit_date = models.DateTimeField(null=True, blank=True)
    bid_validity_period_days = models.PositiveIntegerField(null=True, blank=True)
    # Distinct from TenderBid.warranty_period_months (the vendor's own offered warranty on
    # their bid) — this is the RFP's minimum required floor, set by the RBF.
    minimum_warranty_period_months = models.PositiveIntegerField(null=True, blank=True)
    submission_method = models.CharField(max_length=16, choices=SubmissionMethod.choices, default=SubmissionMethod.ONLINE_ONLY)
    digital_signature_required = models.BooleanField(default=True)
    # EOI Invite-only concepts. Advisory: never enforced against the actual number of
    # vendors shortlisted during EOI Review.
    max_vendors_to_shortlist = models.PositiveIntegerField(null=True, blank=True)
    advertisement_channels = models.JSONField(default=list, blank=True)
    contact_details = models.CharField(max_length=255, blank=True)
    governing_documents = models.JSONField(default=list, blank=True)
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
    minimum_service_tier = models.CharField(max_length=64, blank=True)
    approximate_installation_target = models.PositiveIntegerField(null=True, blank=True)
    # Lot-wise tendering: a tender with no TenderLot rows behaves exactly as a normal
    # single-award tender. One with lots lets bidders price any subset of lots (subject
    # to this optional cap) and lets RMT award each lot to a different vendor.
    max_lots_per_bidder = models.PositiveIntegerField(null=True, blank=True)
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
    dispute_started_at = models.DateTimeField(null=True, blank=True)

    # RBF Official's comment, written only once the committee's evaluation for the
    # tender is complete (quorum technical scores + finalized financial scores). Filled
    # through the /evaluation_comment/ action on TenderViewSet, which enforces the gate.
    evaluation_comment = models.TextField(blank=True)
    evaluation_comment_author = models.CharField(max_length=255, blank=True)
    evaluation_comment_updated_at = models.DateTimeField(null=True, blank=True)

    verified_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Security verification fields
    security_deposit_verified = models.BooleanField(default=False)
    security_deposit_verified_at = models.DateTimeField(null=True, blank=True)

    # Publish approval workflow (RBF requests, Super Admin approves, then RBF publishes)
    publish_approval_status = models.CharField(
        max_length=32,
        choices=PublishApprovalStatus.choices,
        default=PublishApprovalStatus.NOT_REQUESTED,
    )
    publish_approval_requested_at = models.DateTimeField(null=True, blank=True)
    publish_approval_reviewed_at = models.DateTimeField(null=True, blank=True)
    publish_approval_reviewed_by = models.CharField(max_length=255, blank=True)
    publish_approval_notes = models.TextField(blank=True)

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

    def currency_rate_to_base(self, currency):
        """Exchange rate to convert `currency` INTO this tender's base currency
        (bidding_currency). A blank currency, or one matching the base currency, is
        already in base terms (rate 1). Falls back safely to 1 if a rate is somehow
        missing for a currency this tender should have one for — never raises."""
        if not currency or currency == self.bidding_currency:
            return Decimal("1")
        rate = (self.currency_rates or {}).get(currency)
        try:
            return Decimal(str(rate)) if rate else Decimal("1")
        except Exception:
            return Decimal("1")

    def master_deadline(self):
        """The overall tender deadline, derived from the staged deadlines."""
        candidates = [
            v for v in (self.eoi_deadline, self.technical_deadline, self.financial_deadline) if v
        ]
        return max(candidates) if candidates else None

    def save(self, *args, **kwargs):
        # Keep the legacy single "deadline" column (used by exports, filters, and
        # auto-close checks) always in sync with the staged deadlines an admin actually
        # configures, rather than trusting a client-supplied value that can drift out of
        # sync with them.
        computed_deadline = self.master_deadline()
        if computed_deadline:
            self.deadline = computed_deadline
        super().save(*args, **kwargs)


class TenderLot(models.Model):
    """A separately-awardable package within a lot-wise tender.

    A tender with no lots is awarded as a single whole (unchanged legacy behavior,
    using the award fields on Tender itself). A tender with one or more TenderLot rows
    switches into lot-wise mode: bidders price whichever lots they choose (see
    TenderBidLotOffer), and RMT selects a winner independently for each lot, each with
    its own standstill/cooling-off window starting from when THAT lot's intent was
    issued (only the dispute/challenge timeline is still shared at the tender level).
    """
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='lots')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    technology_types = models.JSONField(default=list, blank=True)
    target_districts = models.JSONField(default=list, blank=True)
    estimated_installation_target = models.PositiveIntegerField(null=True, blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    position = models.PositiveIntegerField(default=0)

    # Award state — independent per lot, unlike the shared dispute/challenge timing.
    # awarded_vendor_id/name are set only once this lot's award is CONFIRMED (alongside
    # awarded_at, in confirm_award) — not at intent-to-award time. Use
    # intent_to_award_bid/_at to detect "intent issued, pending confirmation".
    awarded_vendor_id = models.CharField(max_length=64, blank=True)
    awarded_vendor_name = models.CharField(max_length=255, blank=True)
    intent_to_award_bid = models.ForeignKey(
        'TenderBid', null=True, blank=True, on_delete=models.SET_NULL, related_name='lot_intent_awards',
    )
    intent_to_award_at = models.DateTimeField(null=True, blank=True)
    # This lot's own standstill/cooling-off deadline, started when ITS intent was
    # issued — independent of other lots and of Tender.cooling_off_until.
    cooling_off_until = models.DateTimeField(null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'Tender Lot'
        verbose_name_plural = 'Tender Lots'

    def __str__(self):
        return f"{self.name} ({self.tender.reference_number})"


class TenderBoqItem(models.Model):
    """One line of the Bill of Quantities the RBF Official designs while creating the
    tender — description, unit, and quantity are fixed by the RMT; a bidder only ever
    supplies a unit price against each line (see TenderBid.boq_items /
    TenderBidLotOffer.boq_items, which are built server-side from this template plus
    the vendor's submitted prices, never from vendor-supplied descriptions).

    For a non-lot-wise tender, items have lot=None and belong to the tender directly.
    For a lot-wise tender, each lot gets its own independent item list (lot is set,
    tender is left in sync with lot.tender). A tender with no TenderBoqItem rows at all
    falls back to the legacy behavior: the vendor freely authors their own BOQ.
    """
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='boq_template_items')
    lot = models.ForeignKey(
        TenderLot, null=True, blank=True, on_delete=models.CASCADE, related_name='boq_template_items',
        help_text="Set for a lot-wise tender's per-lot BOQ; blank for a non-lot-wise tender's single BOQ.",
    )
    description = models.CharField(max_length=255)
    unit = models.CharField(max_length=64, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    position = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'Tender BOQ Item'
        verbose_name_plural = 'Tender BOQ Items'

    def __str__(self):
        return f"{self.description} ({self.tender.reference_number})"


class TenderEvaluationCommitteeMember(models.Model):
    """A user (holding UserRole.EVALUATION_COMMITTEE) assigned by Super Admin to
    evaluate this specific tender's bids. Membership is per-tender, not platform-wide —
    an Evaluation Committee member may sit on several tenders' committees but only ones
    they've actually been assigned to. A tender's roster must have 3-5 members (enforced
    where it's written, not here) before evaluation can begin on that tender."""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='evaluation_committee_members')
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evaluation_committee_assignments')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    assigned_at = models.DateTimeField(auto_now_add=True)
    # Blanket conflict-of-interest attestation: the member confirms they have no (or
    # only already-declared) conflicts of interest with any bidder on this tender.
    # Required before the member can score any bid — enforced in the evaluation viewset.
    coi_attested = models.BooleanField(default=False)
    coi_attested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('tender', 'member')
        ordering = ['assigned_at', 'id']
        verbose_name = 'Tender Evaluation Committee Member'
        verbose_name_plural = 'Tender Evaluation Committee Members'

    def __str__(self):
        return f"{self.member_id} on {self.tender.reference_number}"


class TenderInvitedVendor(models.Model):
    """A vendor specifically invited to bid on a Restricted Tendering tender.
    Only meaningful when Tender.procurement_method == ProcurementMethod.RESTRICTED —
    for an Open Tendering tender this list is simply unused (any pre-qualified vendor
    can bid). Enforced in TenderViewSet._assert_vendor_submission_access and in
    TenderViewSet.get_queryset (a non-invited vendor never sees a Restricted tender)."""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='invited_vendors')
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tender_invitations')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tender', 'vendor')
        ordering = ['invited_at', 'id']
        verbose_name = 'Tender Invited Vendor'
        verbose_name_plural = 'Tender Invited Vendors'

    def __str__(self):
        return f"{self.vendor_id} invited to {self.tender.reference_number}"


class TenderViewLog(models.Model):
    """Record the first time an authenticated vendor opens a published tender."""

    tender = models.ForeignKey(
        Tender,
        on_delete=models.CASCADE,
        related_name='view_logs',
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tender_view_logs',
    )
    vendor_name = models.CharField(max_length=255)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-viewed_at']
        constraints = [
            models.UniqueConstraint(
                fields=['tender', 'vendor'],
                name='unique_tender_vendor_view',
            ),
        ]
        indexes = [
            models.Index(fields=['tender', 'viewed_at']),
        ]

    def __str__(self):
        return f"{self.vendor_name} viewed {self.tender.reference_number}"


class TenderBid(models.Model):
    """Track vendor bids/submissions for tenders"""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='bids')
    vendor_id = models.CharField(max_length=64)
    vendor_name = models.CharField(max_length=255)
    vendor_email = models.EmailField(blank=True)
    
    # Bid content
    bid_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    subsidy_requested = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Blank means "the tender's base currency" (bidding_currency) — backward-compatible
    # default for every bid submitted before multi-currency tenders existed.
    bid_currency = models.CharField(max_length=64, blank=True)
    proposal_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    stage = models.CharField(max_length=64, blank=True)  # e.g., "Pre-Qualification", "Site-Specific"
    bid_stage = models.CharField(
        max_length=16,
        choices=BidStage.choices,
        default=BidStage.EOI,
        help_text="Which procurement stage this bid record represents.",
    )
    concept_note = models.TextField(blank=True)  # For Stage 1

    # EOI stage content (company credentials, financial standing, technical experience, track record)
    eoi_narrative = models.TextField(blank=True)
    company_credentials_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    financial_standing_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    technical_experience_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    track_record_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
    financial_standing_summary = models.TextField(blank=True)
    technical_experience_summary = models.TextField(blank=True)
    track_record_summary = models.TextField(blank=True)

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
    tender_security_file = models.FileField(upload_to='tender_bids/', null=True, blank=True)
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
    custom_documents = models.JSONField(default=list, blank=True, help_text="Uploaded custom required bid documents: [{name, expected_type, file_name, file_url}]")
    declared_lots = models.JSONField(
        default=list,
        blank=True,
        help_text="Lot IDs (as strings) the vendor declared intent to bid on at EOI stage, for lot-wise tenders. Scopes which lots may be tagged to sites and priced in later stages.",
    )
    
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

    # Stage gating between EOI -> Technical -> Financial
    technical_stage_unlocked = models.BooleanField(default=False)
    technical_stage_unlocked_at = models.DateTimeField(null=True, blank=True)
    technical_stage_source_bid = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='technical_stage_drafts',
    )
    financial_stage_unlocked = models.BooleanField(default=False)
    financial_stage_unlocked_at = models.DateTimeField(null=True, blank=True)
    financial_stage_source_bid = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='financial_stage_drafts',
    )
    # Financial bids are sealed until the technical evaluation clears the threshold.
    financial_sealed = models.BooleanField(default=True)
    financial_unsealed_at = models.DateTimeField(null=True, blank=True)


    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = ('tender', 'vendor_id', 'version_number')
        constraints = [
            # Scoped per bid_stage (not just tender+vendor) because the EOI -> Technical
            # -> Financial workflow deliberately keeps one persistent row per stage, each
            # living out its own status independently — a Technical bid stays "Under
            # Review" forever (there's no explicit accept action for it), so a plain
            # tender+vendor uniqueness would make it permanently impossible to also have
            # a "Submitted" Financial row for the same vendor once Technical has been
            # submitted. Per-stage scoping still prevents two live rows within the same
            # stage (a genuine duplicate submission).
            models.UniqueConstraint(
                fields=['tender', 'vendor_id', 'bid_stage'],
                condition=~models.Q(status__in=[BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN, BidStatus.ACCEPTED]),
                name='uniq_tender_vendor_stage_final_bid',
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


class EvaluationStage(models.TextChoices):
    """Which pass of the evaluation this row represents. Explicit rather than inferred
    from the evaluator's role, since a single Evaluation Committee member now submits
    both a technical and (later) a financial row for the same bid."""
    TECHNICAL = 'technical', 'Technical'
    FINANCIAL = 'financial', 'Financial'


class EvaluationSubmissionStatus(models.TextChoices):
    """Whether an evaluator's row is still a working draft or has been formally
    submitted (locked). Production e-tendering practice: an evaluator may iterate on a
    DRAFT freely, but once SUBMITTED the marks are sealed — only a Super Admin can
    reopen them, and every change is recorded as a TenderBidEvaluationRevision."""
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted'


class EvaluationRevisionAction(models.TextChoices):
    DRAFT_SAVED = 'draft_saved', 'Draft Saved'
    SUBMITTED = 'submitted', 'Submitted'
    REOPENED = 'reopened', 'Reopened by Super Admin'


class TenderBidEvaluation(models.Model):
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    stage = models.CharField(max_length=16, choices=EvaluationStage.choices, default=EvaluationStage.TECHNICAL)
    lot = models.ForeignKey(
        TenderLot, null=True, blank=True, on_delete=models.CASCADE, related_name='bid_evaluations',
        help_text="Scopes an evaluation to a single lot. Lot-wise tenders keep one evaluation per lot per evaluator for BOTH technical and financial stages (a bid covering several lots is scored separately for each). Non-lot-wise tenders leave this NULL.",
    )
    financial_score_auto_calculated = models.BooleanField(
        default=False,
        help_text="True when financial_score was computed from the price formula (100 x lowest bid / this bid) rather than manually typed.",
    )
    status = models.CharField(max_length=16, choices=EvaluationStatus.choices, default=EvaluationStatus.PENDING)
    submission_status = models.CharField(
        max_length=16,
        choices=EvaluationSubmissionStatus.choices,
        default=EvaluationSubmissionStatus.DRAFT,
        help_text="Draft = working marks, freely editable; Submitted = sealed, requires a Super Admin unlock to change.",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    justifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-criterion rationale keyed by the technical rubric key (e.g. {'technical': '...', 'feasibility': '...'}). Required for every scored criterion before a technical evaluation can be submitted.",
    )
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
            models.Index(fields=['evaluator', 'stage', 'status']),
        ]
        constraints = [
            # One technical row per (bid, evaluator) — lot is always NULL for technical.
            models.UniqueConstraint(
                fields=['bid', 'evaluator', 'stage', 'lot'],
                condition=~models.Q(lot__isnull=True),
                name='uniq_bid_evaluator_stage_lot',
            ),
            models.UniqueConstraint(
                fields=['bid', 'evaluator', 'stage'],
                condition=models.Q(lot__isnull=True),
                name='uniq_bid_evaluator_stage_no_lot',
            ),
        ]

    def __str__(self):
        return f"Evaluation for bid {self.bid_id} ({self.status})"


class TenderAwardRecommendation(models.Model):
    """An assigned Evaluation Committee member's suggested winner for a tender. On a
    lot-wise tender the suggestion is per lot — a different vendor can be suggested for
    each lot; on a non-lot-wise tender `lot` stays NULL. The committee's verdict for a
    decision unit is the bid that EVERY assigned member's latest suggestion points to.
    The RBF may then issue intent to award to that agreed bid, or — with a recorded
    `ec_override_reason` — step in when the members disagree or reach no verdict."""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='award_recommendations')
    lot = models.ForeignKey(
        TenderLot, null=True, blank=True, on_delete=models.CASCADE, related_name='award_recommendations',
        help_text='NULL on a non-lot-wise tender (one verdict for the whole tender); set per lot on a lot-wise tender.',
    )
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='award_recommendations')
    suggested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='award_recommendations')
    rationale = models.TextField(blank=True, help_text="Optional note explaining this member's choice.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # One suggestion per member per tender (lot-wise: per lot).
            models.UniqueConstraint(
                fields=['tender', 'lot', 'suggested_by'],
                condition=~models.Q(lot__isnull=True),
                name='uniq_recommendation_tender_lot_member',
            ),
            models.UniqueConstraint(
                fields=['tender', 'suggested_by'],
                condition=models.Q(lot__isnull=True),
                name='uniq_recommendation_tender_member',
            ),
        ]
        indexes = [
            models.Index(fields=['tender', 'lot']),
            models.Index(fields=['tender', 'suggested_by']),
        ]

    def __str__(self):
        unit = f"lot {self.lot_id}" if self.lot_id else "whole tender"
        return f"Award recommendation ({unit}) by {self.suggested_by_id} -> bid {self.bid_id}"


class IntentToAwardRequest(models.Model):
    """The RBF's proposal to issue an intent to award, held for Super Admin approval.

    The RBF selecting a winner and the intent to award actually taking effect are two
    separate acts. This row is the hand-off between them: the RBF's `award` /
    `award_lot` call (or a challenge upheld re-issue) writes a PENDING request and
    nothing else — the tender keeps its current status, no standstill/cooling-off
    clock starts, and bidders are not notified. Only `approve_intent_award`, which a
    Super Admin alone may call, mutates the tender/lot and sends the notices.

    One row per decision unit: `lot` is NULL for a whole-tender award and set per lot
    on a lot-wise tender, so each lot is queued, reviewed and approved independently.
    The Evaluation Committee verdict that justified the choice is snapshotted onto
    the request (`ec_agreed_bid_id`, `ec_consensus`, `ec_override_reason`) so the
    Super Admin reviews the same evidence the RBF saw, even if committee suggestions
    change before the decision is made.
    """
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='intent_award_requests')
    lot = models.ForeignKey(
        TenderLot, null=True, blank=True, on_delete=models.CASCADE, related_name='intent_award_requests',
        help_text='NULL on a non-lot-wise tender (one approval for the whole award); set per lot on a lot-wise tender.',
    )
    bid = models.ForeignKey(
        TenderBid, on_delete=models.CASCADE, related_name='intent_award_requests',
        help_text='The bid proposed to receive the intent to award.',
    )
    proposed_vendor_id = models.CharField(max_length=64, blank=True)
    proposed_vendor_name = models.CharField(max_length=255, blank=True)

    # Snapshot of the committee's verdict + any override reason supplied by the RBF.
    ec_agreed_bid_id = models.CharField(max_length=64, blank=True)
    ec_consensus = models.BooleanField(null=True, blank=True)
    ec_override_reason = models.TextField(blank=True)
    # The RBF's "notify bidders by email" choice, captured at request time and honoured
    # when the Super Admin approves — the notices can only be sent at approval.
    send_email = models.BooleanField(default=True)

    status = models.CharField(
        max_length=32,
        choices=IntentAwardRequestStatus.choices,
        default=IntentAwardRequestStatus.PENDING,
    )
    notes = models.TextField(blank=True, help_text="Super Admin's decision notes.")

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    requested_by_name = models.CharField(max_length=255, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    # True when the request was raised by an upheld challenge rather than by the RBF
    # picking a winner in the Award panel.
    from_challenge = models.BooleanField(default=False)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    reviewed_by_name = models.CharField(max_length=255, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
        constraints = [
            # At most one live request per decision unit, so a tender can never sit in
            # the Super Admin queue twice for the same lot (or whole-tender award).
            models.UniqueConstraint(
                fields=['tender', 'lot'],
                condition=models.Q(status='pending'),
                name='uniq_pending_intent_award_request_per_lot',
            ),
            models.UniqueConstraint(
                fields=['tender'],
                condition=models.Q(status='pending', lot__isnull=True),
                name='uniq_pending_intent_award_request_whole_tender',
            ),
        ]
        indexes = [
            models.Index(fields=['status', '-requested_at']),
            models.Index(fields=['tender', 'lot']),
        ]

    def __str__(self):
        unit = f"lot {self.lot_id}" if self.lot_id else "whole tender"
        return f"Intent to award request ({unit}) for {self.tender.reference_number} -> {self.proposed_vendor_name or self.bid_id}"


class TenderBidEvaluationRevision(models.Model):
    """Immutable before/after snapshot of a TenderBidEvaluation, written whenever a
    draft is saved, submitted, or reopened by a Super Admin. This is the audit trail
    that proves who marked what, when, and how the marks evolved."""
    evaluation = models.ForeignKey(TenderBidEvaluation, on_delete=models.CASCADE, related_name='revisions')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=16, choices=EvaluationRevisionAction.choices, default=EvaluationRevisionAction.DRAFT_SAVED)
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['evaluation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} for evaluation {self.evaluation_id} by {self.changed_by_id}"


class ConflictOfInterestRelationship(models.TextChoices):
    FAMILY = 'family', 'Family member of bidder'
    BUSINESS = 'business', 'Business relationship with bidder'
    FORMER_EMPLOYER = 'former_employer', 'Former employee of bidder'
    HOLDING = 'holding', 'Holdings / financial interest in bidder'
    OTHER = 'other', 'Other'


class EvaluationConflictOfInterest(models.Model):
    """A declared or administered conflict of interest between an Evaluation Committee
    member and a specific bidder on a tender. An unresolved declaration blocks that
    member from scoring the bidder's bids. Every committee member must also complete a
    blanket attestation (TenderEvaluationCommitteeMember.coi_attested) before scoring
    anything on the tender."""
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='declared_conflicts')
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='conflict_of_interests')
    vendor_id = models.CharField(max_length=64, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    relationship = models.CharField(max_length=32, choices=ConflictOfInterestRelationship.choices, default=ConflictOfInterestRelationship.OTHER)
    details = models.TextField(blank=True)
    declared_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='resolved_conflicts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-declared_at']
        indexes = [
            models.Index(fields=['evaluator', 'tender', 'resolved']),
        ]

    def __str__(self):
        return f"COI: {self.evaluator_id} vs {self.vendor_name or self.vendor_id} on {self.tender_id}"


class ChallengeCategory(models.TextChoices):
    PROCEDURAL = 'procedural', 'Procedural Irregularity'
    EVALUATION = 'evaluation', 'Evaluation Error'
    DISCRIMINATION = 'discrimination', 'Discrimination / Bias'
    CONFLICT_OF_INTEREST = 'conflict_of_interest', 'Conflict of Interest'
    TECHNICAL_SPECIFICATION = 'technical_spec', 'Technical Specification Issue'
    FINANCIAL_EVALUATION = 'financial_eval', 'Financial Evaluation Error'
    ELIGIBILITY = 'eligibility', 'Eligibility / Qualification Error'
    CORRUPTION = 'corruption', 'Corruption / Fraud Allegation'
    OTHER = 'other', 'Other Grounds'


class ChallengeStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    ADDITIONAL_INFO_REQUESTED = 'additional_info', 'Additional Information Requested'
    HEARING_SCHEDULED = 'hearing_scheduled', 'Hearing Scheduled'
    UPHELD = 'upheld', 'Upheld'
    PARTIALLY_UPHELD = 'partially_upheld', 'Partially Upheld'
    DISMISSED = 'dismissed', 'Dismissed'
    WITHDRAWN = 'withdrawn', 'Withdrawn'
    SETTLED = 'settled', 'Settled'


class TenderChallenge(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='challenges')
    filed_by_vendor_id = models.CharField(max_length=64)
    filed_by_vendor_name = models.CharField(max_length=255)
    challenger_bid = models.ForeignKey(
        TenderBid, null=True, blank=True, on_delete=models.SET_NULL, related_name='challenges'
    )

    # Structured challenge details
    category = models.CharField(max_length=30, choices=ChallengeCategory.choices, default=ChallengeCategory.OTHER)
    grounds = models.TextField()
    legal_basis = models.TextField(blank=True, help_text="Specific legal/regulatory provisions cited")
    requested_relief = models.TextField(blank=True, help_text="What the challenger wants as remedy")

    # Status and workflow
    status = models.CharField(max_length=25, choices=ChallengeStatus.choices, default=ChallengeStatus.DRAFT)
    priority = models.CharField(max_length=10, choices=[('normal', 'Normal'), ('urgent', 'Urgent')], default='normal')

    # Deadlines
    challenge_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline to file challenge (standstill end)")
    response_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline for RMT to respond")
    hearing_date = models.DateTimeField(null=True, blank=True)

    # Review assignment
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_challenges'
    )
    review_committee = models.JSONField(default=list, blank=True, help_text="List of reviewer user IDs")

    # Timestamps
    filed_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_challenges'
    )
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)

    # Consolidation
    parent_challenge = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='consolidated_challenges')
    is_consolidated = models.BooleanField(default=False)

    class Meta:
        ordering = ['-filed_at']
        indexes = [
            models.Index(fields=['tender', 'status']),
            models.Index(fields=['filed_by_vendor_id', 'status']),
            models.Index(fields=['challenge_deadline']),
        ]

    def __str__(self):
        return f"Challenge by {self.filed_by_vendor_name} on {self.tender.reference_number} [{self.get_status_display()}]"

    def is_within_filing_deadline(self):
        """Check if challenge was filed within standstill period."""
        if self.challenge_deadline:
            return self.filed_at and self.filed_at <= self.challenge_deadline
        return True  # No deadline set = allowed

    def days_until_deadline(self):
        """Days remaining until challenge filing deadline."""
        if self.challenge_deadline:
            delta = self.challenge_deadline - timezone.now()
            return max(0, delta.days)
        return None

    def can_withdraw(self):
        """Challenge can be withdrawn before resolution."""
        return self.status in [ChallengeStatus.DRAFT, ChallengeStatus.SUBMITTED, ChallengeStatus.UNDER_REVIEW,
                               ChallengeStatus.ADDITIONAL_INFO_REQUESTED, ChallengeStatus.HEARING_SCHEDULED]


class ChallengeDocument(models.Model):
    """Supporting documents for challenges."""
    challenge = models.ForeignKey(TenderChallenge, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='challenge_documents/')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    document_type = models.CharField(
        max_length=30,
        choices=[
            ('evidence', 'Evidence'),
            ('legal_argument', 'Legal Argument'),
            ('correspondence', 'Correspondence'),
            ('expert_report', 'Expert Report'),
            ('other', 'Other'),
        ],
        default='evidence'
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_confidential = models.BooleanField(default=False)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} ({self.challenge_id})"


class ChallengeEvent(models.Model):
    """Audit trail / timeline events for challenge."""
    challenge = models.ForeignKey(TenderChallenge, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50)
    description = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_role = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.event_type} - {self.challenge_id}"


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
    # Set only for lot-wise tenders — a vendor can win several lots with the same bid,
    # so (tender, bid) alone is no longer enough to tell contracts apart.
    lot = models.ForeignKey('TenderLot', null=True, blank=True, on_delete=models.SET_NULL, related_name='contracts')
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

    def resolved_award_value(self) -> Decimal:
        """The actual awarded price for this contract, converted into the tender's base
        currency (what the RBF actually tracks/disburses in) — the specific lot's
        winning bid amount for a lot-wise award, otherwise the bid's own bid_amount."""
        bid_currency = self.bid.bid_currency if self.bid_id else ''
        if self.lot_id and self.bid_id:
            offer = TenderBidLotOffer.objects.filter(bid_id=self.bid_id, lot_id=self.lot_id).first()
            if offer and offer.bid_amount:
                return Decimal(str(offer.bid_amount)) * self.tender.currency_rate_to_base(bid_currency)
        if self.bid_id and self.bid.bid_amount:
            return Decimal(str(self.bid.bid_amount)) * self.tender.currency_rate_to_base(bid_currency)
        if self.lot_id and self.lot.budget:
            return Decimal(str(self.lot.budget))
        if self.tender_id and self.tender.budget:
            return Decimal(str(self.tender.budget))
        return Decimal('0.00')


class TenderBidSite(models.Model):
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='sites')
    lot = models.ForeignKey(
        TenderLot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bid_sites',
        help_text="Which lot this site belongs to, for lot-wise tenders. Blank for non-lot-wise tenders.",
    )
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


class TenderBidLotOffer(models.Model):
    """A vendor's price for one lot of a lot-wise tender, within their single bid.

    A vendor may offer on any subset of a tender's lots (one, several, or all),
    subject to Tender.max_lots_per_bidder if the RBF Admin set a cap.
    """
    bid = models.ForeignKey(TenderBid, on_delete=models.CASCADE, related_name='lot_offers')
    lot = models.ForeignKey(TenderLot, on_delete=models.CASCADE, related_name='bid_offers')
    bid_amount = models.DecimalField(max_digits=14, decimal_places=2)
    subsidy_requested = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Populated (server-side, from the lot's TenderBoqItem template + this vendor's unit
    # prices) only when the lot actually has a designed BOQ — see
    # TenderBidSerializer.validate(). When present, bid_amount is derived from this
    # rather than trusted from the client. Blank list for a lot with no BOQ template,
    # where bid_amount is still just a plain vendor-typed number (legacy behavior).
    boq_items = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['lot__position', 'lot_id']
        constraints = [
            models.UniqueConstraint(fields=['bid', 'lot'], name='uniq_bid_lot_offer'),
        ]

    def __str__(self):
        return f"{self.bid.vendor_name} — {self.lot.name}: {self.bid_amount}"


class NoticeCategory(models.TextChoices):
    TENDER = "tender", "Tender"
    DEADLINE = "deadline", "Deadline"
    AWARD = "award", "Award"
    CLARIFICATION = "clarification", "Clarification"
    TRAINING = "training", "Training"
    GENERAL = "general", "General"


class NoticeStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class Notice(models.Model):
    notice_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=NoticeCategory.choices, default=NoticeCategory.GENERAL)
    summary = models.TextField(blank=True, default="")
    content = models.TextField(blank=True, default="")
    linked_tender = models.ForeignKey(Tender, on_delete=models.SET_NULL, null=True, blank=True, related_name="notices")
    is_pinned = models.BooleanField(default=False)
    show_countdown = models.BooleanField(default=False)
    countdown_date = models.DateTimeField(null=True, blank=True)
    send_email_notification = models.BooleanField(default=False)
    attachments = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=NoticeStatus.choices, default=NoticeStatus.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at", "-created_at"]

    def __str__(self):
        return f"{self.notice_id} - {self.title}"


class RequiredDocumentFieldKey(models.TextChoices):
    """Canonical TenderBid file fields a configured required-document row can bind to.

    When a TenderRequiredDocument specifies one of these, the vendor wizard uploads
    directly into that structured field on TenderBid (so BOQ line-items, contract-annex
    generation, and evaluator screens that reference these fields by name keep working).
    A blank field_key means the document is fully custom, stored in TenderBid.custom_documents.
    """
    COMPANY_CREDENTIALS = 'company_credentials_file', 'Company Credentials'
    FINANCIAL_STANDING = 'financial_standing_file', 'Financial Standing'
    TECHNICAL_EXPERIENCE = 'technical_experience_file', 'Technical Experience'
    TRACK_RECORD = 'track_record_file', 'Track Record'
    TECHNICAL_PROPOSAL = 'technical_proposal_file', 'Technical Proposal'
    BOQ = 'boq_file', 'Bill of Quantities'
    GENDER_ACTION_PLAN = 'gender_action_plan_file', 'Gender Action Plan'
    IMPLEMENTATION_PLAN = 'implementation_plan_file', 'Implementation Plan'
    OM_PLAN = 'om_plan_file', 'O&M Plan'
    REPORTING_TEMPLATES = 'reporting_templates_file', 'Reporting Templates'
    DISTRIBUTION_MAP = 'distribution_map_file', 'Distribution Map'
    FINANCIAL_PROPOSAL = 'financial_proposal_file', 'Financial Proposal'
    TENDER_SECURITY = 'tender_security_file', 'Tender Security'


class TenderRequiredDocument(models.Model):
    """A supporting document the RBF requires from bidders, configurable per tender and bid stage."""
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="required_documents")
    name = models.CharField(max_length=255)
    expected_type = models.CharField(max_length=64, blank=True, default='')
    bid_stage = models.CharField(max_length=32, choices=BidStage.choices, default=BidStage.EOI)
    field_key = models.CharField(max_length=64, blank=True, default='', choices=RequiredDocumentFieldKey.choices)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'Required Bid Document'
        verbose_name_plural = 'Required Bid Documents'

    def __str__(self):
        return f"{self.name} ({self.get_bid_stage_display()})"
