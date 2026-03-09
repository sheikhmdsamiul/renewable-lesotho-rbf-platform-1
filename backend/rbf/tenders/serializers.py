from rest_framework import serializers
from django.utils import timezone
from .models import Tender


class TenderSerializer(serializers.ModelSerializer):
    OPTIONAL_TEXT_FIELDS = (
        'application_type',
        'stage_type',
        'procurement_method',
        'address_for_document',
        'address_for_security',
        'place_for_opening',
        'bidders_eligibility',
        'time_for_completion',
        'invited_by',
        'bidding_currency',
        'instruction',
        'pre_tender_meeting_info',
        'contact_details',
        'target_site_type',
        'funding_source',
        'awarded_vendor_id',
        'awarded_vendor_name',
    )
    OPTIONAL_DATE_FIELDS = (
        'last_date_security',
        'last_date_submission',
        'date_opening',
        'verified_at',
        'published_at',
        'awarded_at',
    )
    OPTIONAL_BOOLEAN_FIELDS = (
        'bidders_schedule_purchase',
        'tender_security_required',
        'is_verified',
    )

    def to_internal_value(self, data):
        payload = data.copy() if hasattr(data, 'copy') else dict(data)

        for field in self.OPTIONAL_TEXT_FIELDS:
            if payload.get(field) is None:
                payload[field] = ''

        for field in self.OPTIONAL_DATE_FIELDS:
            if payload.get(field) in ('', None):
                payload[field] = None

        for field in self.OPTIONAL_BOOLEAN_FIELDS:
            if payload.get(field) is None:
                payload[field] = False

        if payload.get('deadline') in ('', None):
            payload['deadline'] = timezone.now().isoformat()

        if payload.get('technology_types') is None:
            payload['technology_types'] = []

        return super().to_internal_value(payload)

    class Meta:
        model = Tender
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
