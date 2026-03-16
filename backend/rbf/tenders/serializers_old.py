from rest_framework import serializers
from .models import Tender, TenderBid, BidStatus
from rbf.users.models import UserRole


class TenderBidSerializer(serializers.ModelSerializer):
    """Serializer for vendor bid submissions and tracking"""
    
    class Meta:
        model = TenderBid
        fields = [
            'id', 'tender', 'vendor_id', 'vendor_name', 'vendor_email',
            'bid_amount', 'proposal_file', 'stage', 'concept_note',
            'technical_proposal', 'financial_proposal', 'status',
            'submitted_at', 'reviewed_at', 'reviewed_by', 'rejection_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'submitted_at', 'created_at', 'updated_at']


class TenderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tender list views"""
    bid_count = serializers.SerializerMethodField()
    
    def get_bid_count(self, obj):
        return obj.bids.count()
    
    class Meta:
        model = Tender
        fields = [
            'id', 'reference_number', 'name', 'department', 'category',
            'status', 'deadline', 'budget', 'published_at', 'is_verified',
            'awarded_vendor_name', 'bid_count', 'created_at'
        ]


class TenderSerializer(serializers.ModelSerializer):
    reference_number = serializers.CharField(required=False, allow_blank=True, default='')
    bid_count = serializers.SerializerMethodField()
    
    def get_bid_count(self, obj):
        return obj.bids.count()
    
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
        'closed_at',
        'security_deposit_verified_at',
    )
    OPTIONAL_BOOLEAN_FIELDS = (
        'bidders_schedule_purchase',
        'tender_security_required',
        'is_verified',
        'security_deposit_verified',
    )

    REQUIRED_FIELDS = [
        'name',
        'department',
        'category',
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
        'contact_details',
        'target_site_type',
        'deadline',
        'last_date_security',
        'last_date_submission',
        'date_opening',
    ]

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

        if payload.get('technology_types') is None:
            payload['technology_types'] = []

        return super().to_internal_value(payload)

    def validate(self, attrs):
        errors = {}
        for field in self.REQUIRED_FIELDS:
            value = attrs.get(field)
            if value in (None, '', []):
                errors[field] = 'This field is required.'

        if not attrs.get('technology_types'):
            errors['technology_types'] = 'Select at least one technology type.'

        file_obj = attrs.get('schedule_file')
        if file_obj:
            if file_obj.size > 10 * 1024 * 1024:
                errors['schedule_file'] = 'File too large (max 10MB).'
            valid_ext = {'.pdf', '.doc', '.docx'}
            import os
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                errors['schedule_file'] = 'Invalid file type. Allowed: PDF, DOC, DOCX.'

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) != UserRole.RBF_OFFICIAL:
            raise serializers.ValidationError('Only RBF Officials can create tenders.')
        # Auto-generate reference number if missing
        if not validated_data.get('reference_number'):
            # Simple sequential tag; in production consider DB sequence or UUID
            last_id = Tender.objects.order_by('-id').values_list('id', flat=True).first() or 0
            validated_data['reference_number'] = f"TND-{last_id + 1:06d}"
        return super().create(validated_data)

    class Meta:
        model = Tender
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'verified_at', 'published_at', 'awarded_at', 'closed_at', 'security_deposit_verified_at', 'bid_count']
        extra_kwargs = {
            'reference_number': {'required': False, 'allow_blank': True},
            'schedule_file': {'required': False, 'allow_null': True},
        }
            if ext not in valid_ext:
                errors['schedule_file'] = 'Invalid file type. Allowed: PDF, DOC, DOCX.'

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) != UserRole.RBF_OFFICIAL:
            raise serializers.ValidationError('Only RBF Officials can create tenders.')
        # Auto-generate reference number if missing
        if not validated_data.get('reference_number'):
            # Simple sequential tag; in production consider DB sequence or UUID
            last_id = Tender.objects.order_by('-id').values_list('id', flat=True).first() or 0
            validated_data['reference_number'] = f"TND-{last_id + 1:06d}"
        return super().create(validated_data)

    class Meta:
        model = Tender
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'reference_number': {'required': False, 'allow_blank': True},
            'schedule_file': {'required': False, 'allow_null': True},
        }
