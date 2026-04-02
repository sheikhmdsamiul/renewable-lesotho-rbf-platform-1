from rest_framework import serializers
from .models import (
    Tender,
    TenderBid,
    TenderBidSite,
    BidStatus,
    TenderBidEvaluation,
    EvaluationStatus,
    TenderContract,
    ContractStatus,
)
from rbf.users.models import UserRole


class TenderBidSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenderBidSite
        fields = [
            'id',
            'site_name',
            'district',
            'latitude',
            'longitude',
            'system_configuration',
            'boq_items',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class TenderBidSerializer(serializers.ModelSerializer):
    """Serializer for vendor bid submissions and tracking"""
    sites = TenderBidSiteSerializer(many=True, required=False)
    tender_reference = serializers.CharField(source='tender.reference_number', read_only=True)
    tender_name = serializers.CharField(source='tender.name', read_only=True)
    
    class Meta:
        model = TenderBid
        fields = [
            'id', 'tender', 'vendor_id', 'vendor_name', 'vendor_email',
            'tender_reference', 'tender_name',
            'bid_amount', 'proposal_file', 'stage', 'concept_note',
            'technical_proposal', 'financial_proposal',
            'technical_proposal_file', 'financial_proposal_file', 'boq_file',
            'gender_action_plan_file', 'implementation_plan_file', 'reporting_templates_file',
            'status', 'version_number',
            'submitted_at', 'reviewed_at', 'reviewed_by', 'rejection_reason',
            'created_at', 'updated_at', 'sites'
        ]
        read_only_fields = ['id', 'submitted_at', 'created_at', 'updated_at']

    def to_internal_value(self, data):
        payload = data.copy() if hasattr(data, 'copy') else dict(data)
        sites = payload.get('sites')
        if isinstance(sites, str):
            try:
                import json
                payload['sites'] = json.loads(sites)
            except Exception:
                pass
        return super().to_internal_value(payload)

    def validate(self, attrs):
        errors = {}
        def validate_file(field_name, max_size_mb=15, allowed_ext=None):
            file_obj = attrs.get(field_name)
            if not file_obj:
                return
            if file_obj.size > max_size_mb * 1024 * 1024:
                errors[field_name] = f'File too large (max {max_size_mb}MB).'
                return
            valid_ext = allowed_ext or {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}
            import os
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                errors[field_name] = 'Invalid file type. Allowed: PDF, DOC, DOCX, XLS, XLSX.'

        validate_file('proposal_file')
        validate_file('technical_proposal_file')
        validate_file('financial_proposal_file')
        validate_file('boq_file')
        validate_file('gender_action_plan_file')
        validate_file('implementation_plan_file')
        validate_file('reporting_templates_file')

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        sites_data = validated_data.pop('sites', [])
        bid = super().create(validated_data)
        if sites_data:
            TenderBidSite.objects.bulk_create(
                [TenderBidSite(bid=bid, **site) for site in sites_data]
            )
        return bid

    def update(self, instance, validated_data):
        sites_data = validated_data.pop('sites', None)
        bid = super().update(instance, validated_data)
        if sites_data is not None:
            bid.sites.all().delete()
            if sites_data:
                TenderBidSite.objects.bulk_create(
                    [TenderBidSite(bid=bid, **site) for site in sites_data]
                )
        return bid

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            file_fields = [
                'proposal_file',
                'technical_proposal_file',
                'financial_proposal_file',
                'boq_file',
                'gender_action_plan_file',
                'implementation_plan_file',
                'reporting_templates_file',
            ]
            for field in file_fields:
                if data.get(field):
                    data[field] = request.build_absolute_uri(data[field])
        return data


class TenderBidEvaluationSerializer(serializers.ModelSerializer):
    evaluator_username = serializers.CharField(source='evaluator.username', read_only=True)

    class Meta:
        model = TenderBidEvaluation
        fields = [
            'id',
            'bid',
            'evaluator',
            'evaluator_username',
            'status',
            'technical_score',
            'financial_score',
            'feasibility_score',
            'kpi_score',
            'gender_score',
            'environmental_score',
            'om_score',
            'inclusivity_score',
            'total_score',
            'comments',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'total_score', 'created_at', 'updated_at', 'evaluator_username']

    def validate(self, attrs):
        scores = [
            attrs.get('technical_score', 0),
            attrs.get('financial_score', 0),
            attrs.get('feasibility_score', 0),
            attrs.get('kpi_score', 0),
            attrs.get('gender_score', 0),
            attrs.get('environmental_score', 0),
            attrs.get('om_score', 0),
            attrs.get('inclusivity_score', 0),
        ]
        for score in scores:
            if score is None:
                continue
            if score < 0 or score > 100:
                raise serializers.ValidationError('Scores must be between 0 and 100.')
        return attrs

    def _compute_total(self, instance, attrs):
        values = [
            attrs.get('technical_score', instance.technical_score if instance else 0),
            attrs.get('financial_score', instance.financial_score if instance else 0),
            attrs.get('feasibility_score', instance.feasibility_score if instance else 0),
            attrs.get('kpi_score', instance.kpi_score if instance else 0),
            attrs.get('gender_score', instance.gender_score if instance else 0),
            attrs.get('environmental_score', instance.environmental_score if instance else 0),
            attrs.get('om_score', instance.om_score if instance else 0),
            attrs.get('inclusivity_score', instance.inclusivity_score if instance else 0),
        ]
        total = round(sum(values) / max(1, len(values)))
        return total

    def create(self, validated_data):
        validated_data['total_score'] = self._compute_total(None, validated_data)
        validated_data['status'] = EvaluationStatus.SCORED
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['total_score'] = self._compute_total(instance, validated_data)
        validated_data['status'] = EvaluationStatus.SCORED
        return super().update(instance, validated_data)


class TenderContractSerializer(serializers.ModelSerializer):
    ANNEX_SOURCE_FIELDS = {
        'annex_a_file': ('gender_action_plan_file',),
        'annex_b_file': ('implementation_plan_file',),
        'annex_c_file': ('financial_proposal_file', 'boq_file'),
        'annex_d_file': ('reporting_templates_file', 'milestone_payment_schedule_file', 'schedule_file'),
        'annex_e_file': ('technical_proposal_file',),
    }

    class Meta:
        model = TenderContract
        fields = '__all__'
        read_only_fields = [
            'id',
            'reference_number',
            'generated_at',
            'signed_at',
            'approved_at',
            'approved_by',
            'milestone_plan_id',
            'project_id',
        ]

    def _resolve_bid(self, instance):
        if instance.bid_id:
            return instance.bid
        return (
            TenderBid.objects.filter(tender=instance.tender, vendor_id=instance.vendor_id)
            .order_by('-version_number', '-submitted_at')
            .first()
        )

    def _resolve_annex_value(self, instance, annex_field):
        current_value = getattr(instance, annex_field, None)
        if current_value:
            return getattr(current_value, 'url', None) or str(current_value)
        bid = self._resolve_bid(instance)
        for source_field in self.ANNEX_SOURCE_FIELDS.get(annex_field, ()):
            source = bid if bid is not None and hasattr(bid, source_field) else instance.tender
            file_obj = getattr(source, source_field, None)
            if file_obj:
                return getattr(file_obj, 'url', None) or str(file_obj)
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and data.get('signed_file'):
            data['signed_file'] = request.build_absolute_uri(data['signed_file'])
        if request and data.get('generated_file'):
            data['generated_file'] = request.build_absolute_uri(data['generated_file'])
        for annex_field in ('annex_a_file', 'annex_b_file', 'annex_c_file', 'annex_d_file', 'annex_e_file'):
            resolved_value = self._resolve_annex_value(instance, annex_field)
            if request and resolved_value:
                data[annex_field] = request.build_absolute_uri(resolved_value)
            else:
                data[annex_field] = resolved_value
        return data


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
        instance = getattr(self, 'instance', None)
        for field in self.REQUIRED_FIELDS:
            value = attrs.get(field)
            if value is None and instance is not None:
                value = getattr(instance, field, None)
            if value in (None, '', []):
                errors[field] = 'This field is required.'

        technology_types = attrs.get('technology_types', instance.technology_types if instance else [])
        if not technology_types:
            errors['technology_types'] = 'Select at least one technology type.'

        def validate_file(field_name, max_size_mb=10, allowed_ext=None):
            file_obj = attrs.get(field_name)
            if not file_obj:
                return
            if file_obj.size > max_size_mb * 1024 * 1024:
                errors[field_name] = f'File too large (max {max_size_mb}MB).'
                return
            valid_ext = allowed_ext or {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}
            import os
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                errors[field_name] = 'Invalid file type. Allowed: PDF, DOC, DOCX, XLS, XLSX.'

        validate_file('schedule_file')
        validate_file('rfp_documents_file')
        validate_file('milestone_payment_schedule_file')

        technical_weight = attrs.get('technical_weight', instance.technical_weight if instance else 70)
        financial_weight = attrs.get('financial_weight', instance.financial_weight if instance else 30)
        technical_threshold = attrs.get('technical_threshold', instance.technical_threshold if instance else 70)
        cooling_off_days = attrs.get('cooling_off_days', instance.cooling_off_days if instance else 7)

        if technical_weight + financial_weight != 100:
            errors['technical_weight'] = 'Technical and financial weights must add up to 100.'
        if technical_threshold < 0 or technical_threshold > 100:
            errors['technical_threshold'] = 'Technical threshold must be between 0 and 100.'
        if cooling_off_days < 0 or cooling_off_days > 14:
            errors['cooling_off_days'] = 'Cooling-off period must be between 0 and 14 days.'

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            file_fields = [
                'schedule_file',
                'rfp_documents_file',
                'milestone_payment_schedule_file',
                'trading_license_file',
                'tax_clearance_file',
                'company_registration_file',
                'experience_portfolio_file',
            ]
            for field in file_fields:
                if data.get(field):
                    data[field] = request.build_absolute_uri(data[field])
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            role = getattr(request.user, 'role', None)
            if role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
                raise serializers.ValidationError('Only the RBF Management Team or Platform Administrators can create tenders.')
        # Auto-generate reference number if missing
        if not validated_data.get('reference_number'):
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
            'rfp_documents_file': {'required': False, 'allow_null': True},
            'milestone_payment_schedule_file': {'required': False, 'allow_null': True},
            'trading_license_file': {'required': False, 'allow_null': True},
            'tax_clearance_file': {'required': False, 'allow_null': True},
            'company_registration_file': {'required': False, 'allow_null': True},
            'experience_portfolio_file': {'required': False, 'allow_null': True},
        }
