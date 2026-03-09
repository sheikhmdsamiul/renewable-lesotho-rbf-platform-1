from django.db import models


class TenderStatus(models.TextChoices):
    DRAFT = 'Draft'
    PUBLISHED = 'Published'
    EVALUATION = 'Evaluation'
    AWARDED = 'Awarded'
    CLOSED = 'Closed'


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
    target_site_type = models.CharField(max_length=64, blank=True)
    is_verified = models.BooleanField(default=False)
    funding_source = models.CharField(max_length=128, blank=True)
    awarded_vendor_id = models.CharField(max_length=64, blank=True)
    awarded_vendor_name = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.reference_number} - {self.name}"
