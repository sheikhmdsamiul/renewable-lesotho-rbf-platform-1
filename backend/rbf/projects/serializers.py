from rest_framework import serializers
from django.db.models import Q, Sum
from .models import (
    ResultsIndicator,
    AuditCase,
    AuditEvidence,
    OversightReview,
    KpiReview,
    SiteMonitoringPhoto,
    SiteMonitoringVisit,
    Project,
    ProjectSetup,
    ProjectSetupReviewStatus,
    Milestone,
    MilestoneCompletionReview,
    ProjectUpdate,
    ProjectDocument,
    InstallationReport,
    FieldVerification,
    VerificationTask,
    MeterDataBatch,
    SmartMeterReading,
    SmartMeterReadingReviewStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    AuditLog,
    ProspectSyncLog,
    AnomalyFlag,
    AnomalyReviewEvent,
    AnomalyEvidenceFile,
)
from rbf.tenders.models import TenderContract
from django.conf import settings
from rbf.users.models import UserRole
from rbf.common.uploads import validate_document_upload
from django.core.files.storage import default_storage
from .bank_details import get_vendor_bank_snapshot


class MilestoneReviewDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['proceed', 'close', 'transfer', 'complete'])
    verification_notes = serializers.CharField(allow_blank=False, trim_whitespace=True)
    new_vendor_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['decision'] == 'transfer' and not str(attrs.get('new_vendor_id') or '').strip():
            raise serializers.ValidationError({'new_vendor_id': 'Select the vendor the project will be transferred to.'})
        return attrs


class MilestoneCompletionReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.SerializerMethodField()

    def get_reviewed_by_name(self, obj):
        user = obj.reviewed_by
        if not user:
            return ''
        return user.full_name or user.username

    class Meta:
        model = MilestoneCompletionReview
        fields = [
            'id', 'milestone', 'project', 'status', 'decision', 'verification_notes',
            'vendor_id', 'vendor_name', 'transferred_to_vendor_id', 'transferred_to_vendor_name',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at',
        ]
        read_only_fields = fields


class MilestoneSerializer(serializers.ModelSerializer):
    completion_review = serializers.SerializerMethodField()
    target_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'],
    )
    completed_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'],
    )

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        progress = attrs.get('progress_percentage')
        completed_date = attrs.get('completed_date')

        if instance is not None:
            if progress is None:
                progress = instance.progress_percentage
            if 'completed_date' not in attrs:
                completed_date = instance.completed_date

        if completed_date:
            attrs['progress_percentage'] = 100
            progress = 100

        progress = 0 if progress is None else progress
        if progress < 0 or progress > 100:
            raise serializers.ValidationError({'progress_percentage': 'Progress must be between 0 and 100.'})

        return attrs

    def get_completion_review(self, obj):
        # Reverse one-to-one raises RelatedObjectDoesNotExist (an AttributeError) when absent.
        review = getattr(obj, 'completion_review', None)
        return MilestoneCompletionReviewSerializer(review).data if review else None

    class Meta:
        model = Milestone
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProjectSerializer(serializers.ModelSerializer):
    milestones = MilestoneSerializer(many=True, read_only=True)
    project_setup = serializers.SerializerMethodField()
    tender_reference_number = serializers.CharField(source='tender.reference_number', read_only=True)
    tender_name = serializers.CharField(source='tender.name', read_only=True)
    tender_budget = serializers.DecimalField(source='tender.budget', max_digits=14, decimal_places=2, read_only=True)
    tender_deadline = serializers.DateTimeField(source='tender.deadline', read_only=True)
    tender_awarded_at = serializers.DateTimeField(source='tender.awarded_at', read_only=True)
    tender_status = serializers.CharField(source='tender.status', read_only=True)
    contract_reference = serializers.SerializerMethodField()
    contract_status = serializers.SerializerMethodField()
    contract_signed_file = serializers.SerializerMethodField()
    milestone_total_amount = serializers.SerializerMethodField()
    archived_by_name = serializers.SerializerMethodField()
    milestone_count = serializers.SerializerMethodField()
    assigned_district = serializers.SerializerMethodField()
    setup_status = serializers.SerializerMethodField()
    setup_status_banner = serializers.SerializerMethodField()
    installation_submission_enabled = serializers.SerializerMethodField()
    installation_submission_disabled = serializers.SerializerMethodField()
    milestone_plan = serializers.SerializerMethodField()
    vendor_dashboard_widget = serializers.SerializerMethodField()
    claim_count = serializers.SerializerMethodField()
    unresolved_flag_count = serializers.SerializerMethodField()
    latest_audit_entry = serializers.SerializerMethodField()
    contract_value = serializers.SerializerMethodField()
    awarded_bid_device_info = serializers.SerializerMethodField()
    # For a lot-wise award the project is scoped to a single lot, so its name needs to be
    # visible wherever the project is (the assignment screen, project lists, details).
    lot_name = serializers.SerializerMethodField()

    def _get_contract(self, obj: Project):
        if not hasattr(self, '_contract_cache'):
            self._contract_cache = {}
        cached = self._contract_cache.get(obj.id)
        if cached is not None:
            return cached
        contract = TenderContract.objects.filter(project_id=str(obj.id)).only(
            'reference_number', 'status', 'signed_file'
        ).first()
        self._contract_cache[obj.id] = contract
        return contract

    def get_archived_by_name(self, obj: Project):
        return (obj.archived_by.full_name or obj.archived_by.username) if obj.archived_by_id else None

    def get_contract_reference(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.reference_number if contract else None

    def get_contract_status(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.status if contract else None

    def get_contract_signed_file(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.signed_file.url if contract and contract.signed_file else None

    def get_milestone_total_amount(self, obj: Project):
        milestones = list(obj.milestones.all())
        return sum(m.amount for m in milestones) if milestones else 0

    def get_milestone_count(self, obj: Project):
        return obj.milestones.count()

    def get_project_setup(self, obj: Project):
        setup = getattr(obj, 'project_setup', None)
        if not setup:
            return None
        return ProjectSetupSerializer(setup, context=self.context).data

    def _setup_complete(self, obj: Project) -> bool:
        setup = getattr(obj, 'project_setup', None)
        return bool((setup and setup.setup_completed_at) or obj.setup_completed_at)

    def get_assigned_district(self, obj: Project):
        return obj.district_zone or obj.district or obj.region or ''

    def get_setup_status(self, obj: Project):
        return 'COMPLETE' if self._setup_complete(obj) else 'INCOMPLETE'

    def get_setup_status_banner(self, obj: Project):
        setup = getattr(obj, 'project_setup', None)
        is_complete = self._setup_complete(obj)
        review_status = getattr(setup, 'review_status', None) or (
            ProjectSetupReviewStatus.APPROVED if is_complete else ProjectSetupReviewStatus.DRAFT
        )
        reviewed_by = getattr(setup, 'reviewed_by', None)
        tone_map = {
            ProjectSetupReviewStatus.DRAFT: ('INCOMPLETE', 'red', 'Project setup is incomplete. Complete setup before submitting installations.'),
            ProjectSetupReviewStatus.SUBMITTED: ('PENDING', 'blue', 'Project setup has been submitted and is awaiting RMT review.'),
            ProjectSetupReviewStatus.UNDER_REVIEW: ('PENDING', 'indigo', 'RMT is currently reviewing the project setup.'),
            ProjectSetupReviewStatus.APPROVED: ('COMPLETE', 'green', 'Project setup is approved. Installation submission is unlocked.'),
            ProjectSetupReviewStatus.CHANGES_REQUESTED: ('CHANGES_REQUESTED', 'amber', 'RMT requested changes. Update the setup and resubmit.'),
            ProjectSetupReviewStatus.REJECTED: ('REJECTED', 'red', 'Project setup was rejected. Contact RMT for next steps.'),
        }
        status, tone, message = tone_map.get(review_status, ('INCOMPLETE', 'red', 'Project setup is incomplete.'))
        return {
            'status': status,
            'tone': tone,
            'message': message,
            'review_status': review_status,
            'review_notes': getattr(setup, 'review_notes', '') or '',
            'previous_review_notes': getattr(setup, 'previous_review_notes', '') or '',
            'reviewed_at': setup.reviewed_at if setup else None,
            'reviewed_by_username': getattr(reviewed_by, 'username', None) if reviewed_by else None,
            'submitted_at': getattr(setup, 'submitted_at', None),
        }

    def get_installation_submission_enabled(self, obj: Project):
        return self._setup_complete(obj)

    def get_installation_submission_disabled(self, obj: Project):
        return not self.get_installation_submission_enabled(obj)

    def get_milestone_plan(self, obj: Project):
        milestones = list(obj.milestones.all().order_by('milestone_number', 'id'))
        return [
            {
                'milestone_number': milestone.milestone_number,
                'name': milestone.name,
                'disbursement_pct': milestone.disbursement_pct,
                'required_installation_pct': milestone.required_installation_pct,
                'status': milestone.status,
            }
            for milestone in milestones
        ]

    def get_vendor_dashboard_widget(self, obj: Project):
        return {
            'project_id': obj.id,
            'technology_type': obj.technology_type or obj.tech_type,
            'assigned_district': self.get_assigned_district(obj),
            'installation_target': obj.installation_target or obj.target_installations,
            'project_duration_months': obj.project_duration_months,
            'milestone_plan': self.get_milestone_plan(obj),
            'setup_status': self.get_setup_status(obj),
            'setup_status_banner': self.get_setup_status_banner(obj),
            'submit_installation_disabled': self.get_installation_submission_disabled(obj),
            'submit_installation_enabled': self.get_installation_submission_enabled(obj),
        }

    def get_claim_count(self, obj: Project):
        return obj.payment_claims.count() if hasattr(obj, 'payment_claims') else 0

    def get_unresolved_flag_count(self, obj: Project):
        return obj.anomaly_flags.filter(is_resolved=False).count() if hasattr(obj, 'anomaly_flags') else 0

    def get_latest_audit_entry(self, obj: Project):
        audit = AuditLog.objects.filter(
            Q(record_type='project', record_id=obj.id)
            | Q(details__project_id=str(obj.id))
            | Q(entity_type='Project', entity_id=str(obj.id))
        ).select_related('actor').order_by('-created_at').first()
        if not audit:
            return None
        return AuditLogSerializer(audit, context=self.context).data

    def get_lot_name(self, obj: Project):
        return obj.lot.name if obj.lot_id else None

    def get_contract_value(self, obj: Project):
        total = obj.milestones.aggregate(total=Sum('amount_lsl'))['total']
        if total is None:
            total = obj.milestones.aggregate(total=Sum('amount'))['total']
        if total is not None:
            return total
        if obj.budget is not None:
            return obj.budget
        if obj.tender and obj.tender.budget is not None:
            return obj.tender.budget
        return None

    def get_awarded_bid_device_info(self, obj: Project):
        tender = getattr(obj, 'tender', None)
        if not tender:
            return None
        try:
            contract = TenderContract.objects.filter(tender=tender, project_id=str(obj.id)).first()
            if contract and contract.bid_id:
                bid = contract.bid
                if bid and bid.status == 'Awarded':
                    sys_config = bid.system_configuration or {}
                    return {
                        'device_brand': sys_config.get('device_brand', ''),
                        'device_model': sys_config.get('device_model', ''),
                    }
        except Exception:
            pass
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        role = getattr(user, 'role', None)

        if role == UserRole.UNDP_DONOR:
            for field_name in ('vendor_name', 'vendor_id'):
                data.pop(field_name, None)
            for field_name in ('budget', 'contract_value', 'tender_budget', 'milestone_total_amount'):
                data[field_name] = None

        if role in {UserRole.TAC, UserRole.DOE_OFFICER, UserRole.UNDP_DONOR}:
            for field_name in ('budget', 'contract_value', 'tender_budget', 'milestone_total_amount'):
                data[field_name] = None

        return data

    INCLUSION_TARGET_FIELDS = {
        'female': ('female_target_pct', 'target_female_pct'),
        'vulnerable': ('vulnerable_target_pct', 'target_vulnerable_pct'),
        'low_income': ('low_income_target_pct', 'target_low_income_pct'),
    }

    def validate(self, attrs):
        """Inclusion targets are configured by the Super Admin only. Anyone else creating a project
        gets the programme minimums from Platform Configuration and cannot change them later."""
        from rbf.users.models import inclusion_targets

        attrs = super().validate(attrs)
        request = self.context.get('request')
        if getattr(getattr(request, 'user', None), 'role', None) == UserRole.ADMIN:
            return attrs
        fields = [f for pair in self.INCLUSION_TARGET_FIELDS.values() for f in pair]
        if self.instance is None:
            minimums = inclusion_targets()
            for key, pair in self.INCLUSION_TARGET_FIELDS.items():
                for field in pair:
                    attrs[field] = minimums[key]
            return attrs
        changed = [f for f in fields if f in attrs and attrs[f] != getattr(self.instance, f)]
        if changed:
            raise serializers.ValidationError({f: 'Only the Super Admin can change inclusion targets.' for f in changed})
        return attrs

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id', 'archived_at', 'archived_by']


class ProjectSetupSerializer(serializers.ModelSerializer):
    team_roster_file_url = serializers.SerializerMethodField()
    equipment_plan_file_url = serializers.SerializerMethodField()
    compliance_docs_file_url = serializers.SerializerMethodField()
    insurance_certificate_file_url = serializers.SerializerMethodField()
    meter_api_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_meter_api_token = serializers.SerializerMethodField()
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True, default=None)

    def _file_url(self, file_field):
        if file_field:
            request = self.context.get('request')
            url = file_field.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_team_roster_file_url(self, obj: ProjectSetup):
        return self._file_url(obj.team_roster_file)

    def get_equipment_plan_file_url(self, obj: ProjectSetup):
        return self._file_url(obj.equipment_plan_file)

    def get_compliance_docs_file_url(self, obj: ProjectSetup):
        return self._file_url(obj.compliance_docs_file)

    def get_insurance_certificate_file_url(self, obj: ProjectSetup):
        return self._file_url(obj.insurance_certificate_file)

    def get_has_meter_api_token(self, obj: ProjectSetup):
        return obj.has_meter_api_token

    def validate_team_roster_file(self, value):
        self._validate_supporting_file(value, {'pdf', 'docx'})
        return value

    def validate_equipment_plan_file(self, value):
        self._validate_supporting_file(value, {'pdf', 'docx'})
        return value

    def validate_compliance_docs_file(self, value):
        self._validate_supporting_file(value, {'pdf', 'docx'})
        return value

    def validate_insurance_certificate_file(self, value):
        self._validate_supporting_file(value, {'pdf', 'docx'})
        return value

    def _validate_supporting_file(self, value, allowed_extensions: set[str]):
        if not value:
            return
        extension = str(value.name).rsplit('.', 1)[-1].lower() if '.' in str(value.name) else ''
        if extension not in allowed_extensions:
            raise serializers.ValidationError(f"Supported file types: {', '.join(sorted(allowed_extensions))}.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('File size must be 5MB or less.')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, 'instance', None)
        project = self.context.get('project') or getattr(instance, 'project', None)
        is_submit = bool(self.context.get('submit'))

        def current(field_name, default=''):
            if field_name in attrs:
                return attrs.get(field_name)
            if instance is not None:
                return getattr(instance, field_name)
            return default

        start = current('work_schedule_start', None)
        end = current('work_schedule_end', None)
        if start and end and end < start:
            raise serializers.ValidationError({'work_schedule_end': 'Work schedule end must be on or after the start date.'})

        tech_tier = current('tech_tier', None)
        if tech_tier is not None and tech_tier not in {1, 2, 3, 4, 5}:
            raise serializers.ValidationError({'tech_tier': 'Technology tier must be between 1 and 5.'})

        if project is not None:
            tender = getattr(project, 'tender', None)
            if tender:
                try:
                    contract = TenderContract.objects.filter(tender=tender, project_id=str(project.id)).first()
                    if contract and contract.bid_id:
                        bid = contract.bid
                        if bid and bid.status == 'Awarded':
                            bid_device_brand = str(bid.system_configuration.get('device_brand', '') or '').strip().lower()
                            bid_device_model = str(bid.system_configuration.get('device_model', '') or '').strip().lower()
                            setup_device_brand = str(current('device_brand', '') or '').strip().lower()
                            setup_device_model = str(current('device_model', '') or '').strip().lower()
                            if bid_device_brand and setup_device_brand and bid_device_brand != setup_device_brand:
                                raise serializers.ValidationError({
                                    'device_brand': f"Device brand must match the awarded bid's device brand: '{bid.system_configuration.get('device_brand', '')}'"
                                })
                            if bid_device_model and setup_device_model and bid_device_model != setup_device_model:
                                raise serializers.ValidationError({
                                    'device_model': f"Device model must match the awarded bid's device model: '{bid.system_configuration.get('device_model', '')}'"
                                })
                except Exception:
                    pass

        if not is_submit or project is None:
            return attrs

        required_fields = {
            'team_roster_file': 'team_roster_file',
            'equipment_plan_file': 'equipment_plan_file',
            'site_status': 'site_status',
            'work_schedule_start': 'work_schedule_start',
            'work_schedule_end': 'work_schedule_end',
            'compliance_docs_file': 'compliance_docs_file',
            'insurance_certificate_file': 'insurance_certificate_file',
            'device_model': 'device_model',
            'device_brand': 'device_brand',
            'tech_tier': 'tech_tier',
        }
        errors = {}
        for field_name, error_key in required_fields.items():
            value = current(field_name, None)
            if value in {None, ''}:
                errors[error_key] = 'This field is required before submitting setup.'

        checklist_fields = [
            'checklist_team_ready',
            'checklist_equipment_ready',
            'checklist_site_ready',
            'checklist_safety_ready',
            'checklist_logistics_ready',
        ]
        for field_name in checklist_fields:
            if not bool(current(field_name, False)):
                errors[field_name] = 'All pre-deployment checklist items must be completed.'

        verification_method = str(getattr(project, 'verification_method', '') or '').strip().lower()
        if verification_method == 'iot':
            if not str(current('meter_api_endpoint', '') or '').strip():
                errors['meter_api_endpoint'] = 'Meter API endpoint is required for IoT verification.'
            if not (str(attrs.get('meter_api_token') or '').strip() or (instance and instance.has_meter_api_token)):
                errors['meter_api_token'] = 'Meter API token is required for IoT verification.'
        elif not bool(current('manual_verification_confirmed', False)):
            errors['manual_verification_confirmed'] = 'Please confirm the manual verification method before submitting.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        raw_token = validated_data.pop('meter_api_token', None)
        setup = super().create(validated_data)
        if raw_token is not None:
            setup.set_meter_api_token(raw_token)
            setup.save(update_fields=['meter_api_token_encrypted'])
        return setup

    def update(self, instance, validated_data):
        raw_token = validated_data.pop('meter_api_token', None)
        setup = super().update(instance, validated_data)
        if raw_token is not None:
            setup.set_meter_api_token(raw_token)
            setup.save(update_fields=['meter_api_token_encrypted'])
        return setup

    class Meta:
        model = ProjectSetup
        fields = [
            'id',
            'project',
            'vendor',
            'team_roster_file',
            'team_roster_file_url',
            'equipment_plan_file',
            'equipment_plan_file_url',
            'site_status',
            'work_schedule_start',
            'work_schedule_end',
            'compliance_docs_file',
            'compliance_docs_file_url',
            'insurance_certificate_file',
            'insurance_certificate_file_url',
            'device_model',
            'device_brand',
            'tech_tier',
            'meter_api_endpoint',
            'meter_api_token',
            'has_meter_api_token',
            'manual_verification_confirmed',
            'checklist_team_ready',
            'checklist_equipment_ready',
            'checklist_site_ready',
            'checklist_safety_ready',
            'checklist_logistics_ready',
            'review_status',
            'submitted_at',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
            'review_notes',
            'previous_review_notes',
            'setup_completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'project',
            'vendor',
            'review_status',
            'submitted_at',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
            'review_notes',
            'previous_review_notes',
            'setup_completed_at',
            'created_at',
            'updated_at',
        ]


class ProjectUpdateSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = ProjectUpdate
        fields = '__all__'
        read_only_fields = ['id', 'author', 'author_username', 'created_at']


class ProjectDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = ProjectDocument
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_by', 'uploaded_by_username', 'uploaded_at']


class DisbursementSerializer(serializers.ModelSerializer):
    processed_by_username = serializers.CharField(source='processed_by.username', read_only=True)

    class Meta:
        model = Disbursement
        fields = '__all__'
        read_only_fields = ['id', 'processed_at', 'processed_by', 'processed_by_username']


class PaymentClaimSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    vendor_legal_name = serializers.SerializerMethodField()
    vendor_bank_name = serializers.SerializerMethodField()
    vendor_bank_branch = serializers.SerializerMethodField()
    vendor_bank_swift_code = serializers.SerializerMethodField()
    vendor_bank_sort_code = serializers.SerializerMethodField()
    vendor_account_holder_name = serializers.SerializerMethodField()
    vendor_account_number = serializers.SerializerMethodField()
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)
    disbursement = DisbursementSerializer(read_only=True)
    payment_locked = serializers.SerializerMethodField()
    payment_lock_reason = serializers.SerializerMethodField()
    milestone_details = MilestoneSerializer(source='milestone', read_only=True)

    def get_vendor_legal_name(self, obj: PaymentClaim):
        if obj.vendor.organization_name:
            return obj.vendor.organization_name
        if obj.vendor.full_name:
            return obj.vendor.full_name
        return obj.vendor.username

    def _has_partial_bank_visibility(self, obj: PaymentClaim):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return (
            user is not None
            and user.role == UserRole.UNDP_DONOR
            and obj.status in {PaymentClaimStatus.TAC_ENDORSED, PaymentClaimStatus.PSC_APPROVED}
        )

    def get_vendor_bank_name(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        if self._has_partial_bank_visibility(obj):
            return snapshot['bank_name']
        return None

    def get_vendor_bank_branch(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        if self._has_partial_bank_visibility(obj):
            return snapshot['bank_branch']
        return None

    def get_vendor_bank_swift_code(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        if self._has_partial_bank_visibility(obj):
            return snapshot['bank_swift_code']
        return None

    def get_vendor_bank_sort_code(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        if self._has_partial_bank_visibility(obj):
            return snapshot['bank_sort_code']
        return None

    def get_vendor_account_holder_name(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        if self._has_partial_bank_visibility(obj):
            return snapshot['bank_account_name']
        return None

    def get_vendor_account_number(self, obj: PaymentClaim):
        snapshot = get_vendor_bank_snapshot(obj.vendor)
        account_number = snapshot['bank_account_number']
        if self._has_partial_bank_visibility(obj):
            if len(account_number) <= 4:
                return '****'
            return '*' * max(0, len(account_number) - 4) + account_number[-4:]
        return None

    def get_payment_locked(self, obj: PaymentClaim):
        return bool(obj.vendor and obj.vendor.role == 'Vendor' and obj.vendor.status in {'Suspended', 'Blacklisted'})

    def get_payment_lock_reason(self, obj: PaymentClaim):
        if self.get_payment_locked(obj):
            return 'Payment is locked because this transaction is linked to a suspended or blacklisted vendor.'
        return None

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        declaration_accepted = attrs.get('declaration_accepted', getattr(instance, 'declaration_accepted', False))
        if not declaration_accepted:
            raise serializers.ValidationError({'declaration_accepted': 'You must accept the declaration before submitting a claim.'})
        return attrs

    class Meta:
        model = PaymentClaim
        fields = '__all__'
        read_only_fields = [
            'id',
            'submitted_at',
            'verified_at',
            'approved_at',
            'paid_at',
            'reviewed_by',
            'reviewed_by_username',
                'vendor_username',
            'vendor_legal_name',
            'vendor_bank_name',
            'vendor_bank_branch',
            'vendor_bank_swift_code',
            'vendor_bank_sort_code',
            'vendor_account_holder_name',
            'vendor_account_number',
            'disbursement',
            'payment_locked',
            'payment_lock_reason',
            'milestone_details',
        ]


class InstallationReportSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    receipt_file_url = serializers.SerializerMethodField()

    def get_receipt_file_url(self, obj: InstallationReport):
        if obj.receipt_file:
            return obj.receipt_file.url
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        role = getattr(user, 'role', None)

        if role in {UserRole.TAC, UserRole.AUDITOR}:
            beneficiary_id = str(data.get('beneficiary_id') or '')
            if beneficiary_id:
                data['beneficiary_id'] = f"{'*' * max(0, len(beneficiary_id) - 4)}{beneficiary_id[-4:]}"
            # A contact number is PII of comparable sensitivity to the national ID, so it
            # gets the same treatment rather than being exposed in full to these roles.
            beneficiary_phone = str(data.get('beneficiary_phone') or '')
            if beneficiary_phone:
                data['beneficiary_phone'] = f"{'*' * max(0, len(beneficiary_phone) - 4)}{beneficiary_phone[-4:]}"
        elif role in {UserRole.DOE_OFFICER, UserRole.UNDP_DONOR}:
            data['beneficiary_id'] = ''
            data['beneficiary_name'] = None
            data['beneficiary_phone'] = ''

        return data

    class Meta:
        model = InstallationReport
        fields = '__all__'
        read_only_fields = ['id', 'vendor', 'vendor_username', 'submitted_at', 'status', 'gis_status', 'receipt_file_url', 'district']


def _storage_urls(paths):
    urls = []
    for path in paths or []:
        try:
            urls.append(default_storage.url(path))
        except Exception:
            continue
    return urls


class FieldVerificationSerializer(serializers.ModelSerializer):
    field_officer_username = serializers.CharField(source='field_officer.username', read_only=True)
    field_officer_name = serializers.CharField(source='field_officer.full_name', read_only=True)
    site_photo_urls = serializers.SerializerMethodField()

    class Meta:
        model = FieldVerification
        fields = '__all__'
        read_only_fields = [field.name for field in FieldVerification._meta.fields] + [
            'field_officer_username', 'field_officer_name', 'site_photo_urls',
        ]

    def get_site_photo_urls(self, obj):
        return _storage_urls(obj.site_photos)


class VerificationTaskSerializer(serializers.ModelSerializer):
    """Verification tasks are workflow records: every field is read-only and changes go through actions."""

    assigned_verifier_username = serializers.CharField(source='assigned_verifier.username', read_only=True)
    reverification_requested_by_username = serializers.CharField(source='reverification_requested_by.username', read_only=True, default=None)
    field_verification = serializers.SerializerMethodField()
    field_verifications = serializers.SerializerMethodField()
    installation = serializers.SerializerMethodField()

    class Meta:
        model = VerificationTask
        fields = '__all__'
        read_only_fields = [field.name for field in VerificationTask._meta.fields] + [
            'assigned_verifier_username', 'reverification_requested_by_username',
        ]

    def _history(self, obj):
        cached = getattr(obj, '_field_verification_history', None)
        if cached is None:
            cached = list(obj.report.field_verifications.select_related('field_officer').all())
            obj._field_verification_history = cached
        return cached

    def get_field_verification(self, obj):
        history = self._history(obj)
        if not history:
            return None
        return FieldVerificationSerializer(history[0], context=self.context).data

    def get_field_verifications(self, obj):
        return FieldVerificationSerializer(self._history(obj), many=True, context=self.context).data

    def get_installation(self, obj):
        report = obj.report
        project = report.project
        return {
            'id': report.id,
            'project_id': project.id,
            'project_reference': project.project_reference,
            'project_title': project.project_title,
            'vendor_name': project.vendor_name,
            'serial_number': report.serial_number,
            'district': report.district or project.district or project.region,
            'household_type': report.household_type,
            'gps_lat': report.gps_lat,
            'gps_lng': report.gps_lng,
            'status': report.status,
            'gis_status': report.gis_status,
            'submitted_at': report.submitted_at,
            'photo_urls': _storage_urls(report.photo_files),
        }


class SmartMeterReadingSerializer(serializers.ModelSerializer):
    submitted_by_username = serializers.CharField(source='submitted_by.username', read_only=True, default=None)
    batch_status = serializers.CharField(source='batch.status', read_only=True, default=None)

    class Meta:
        model = SmartMeterReading
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'batch', 'source', 'submitted_by', 'integrity_flags',
            'review_status', 'rejection_reason',
        ]


class MeterDataBatchSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True, default=None)
    uploaded_by_name = serializers.SerializerMethodField()
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True, default=None)
    source_file_url = serializers.SerializerMethodField()
    project_reference = serializers.CharField(source='project.project_reference', read_only=True)
    vendor_id = serializers.CharField(source='project.vendor_id', read_only=True)
    vendor_name = serializers.CharField(source='project.vendor_name', read_only=True)
    readings_rejected = serializers.SerializerMethodField()
    total_kwh = serializers.SerializerMethodField()

    def get_uploaded_by_name(self, obj: MeterDataBatch):
        user = obj.uploaded_by
        if not user:
            return None
        return user.organization_name or user.full_name or user.username

    def get_source_file_url(self, obj: MeterDataBatch):
        document = obj.source_document
        if document and document.file:
            return document.file.url
        return None

    def get_readings_rejected(self, obj: MeterDataBatch):
        return sum(1 for reading in obj.readings.all() if reading.review_status == SmartMeterReadingReviewStatus.REJECTED)

    def get_total_kwh(self, obj: MeterDataBatch):
        return round(sum(float(reading.kwh or 0) for reading in obj.readings.all()), 3)

    class Meta:
        model = MeterDataBatch
        fields = '__all__'
        read_only_fields = [field.name for field in MeterDataBatch._meta.fields]


class MeterDataBatchDetailSerializer(MeterDataBatchSerializer):
    readings = SmartMeterReadingSerializer(many=True, read_only=True)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)
    actor_full_name = serializers.CharField(source='actor.full_name', read_only=True)

    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'actor_username', 'actor_full_name']


class ProspectSyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProspectSyncLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class AnomalyReviewEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = AnomalyReviewEvent
        fields = [
            'id', 'flag', 'actor', 'actor_username', 'actor_role',
            'from_status', 'to_status', 'investigation_notes', 'corrective_action',
            'resolution_reason', 'evidence_reference', 'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'actor_username']


class AnomalyEvidenceFileSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = AnomalyEvidenceFile
        fields = [
            'id', 'flag', 'file', 'original_name', 'uploaded_by', 'uploaded_by_username', 'uploaded_at',
        ]
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by_username']


class AnomalyFlagSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    review_events = AnomalyReviewEventSerializer(many=True, read_only=True)
    evidence_files = AnomalyEvidenceFileSerializer(many=True, read_only=True)

    class Meta:
        model = AnomalyFlag
        fields = [
            'id', 'installation', 'project', 'flag_type', 'description', 'is_resolved',
            'status', 'severity', 'assigned_to', 'assigned_to_username',
            'investigation_notes', 'corrective_action', 'resolution_reason',
            'evidence_reference', 'due_date', 'created_at', 'resolved_at',
            'review_events', 'evidence_files',
        ]
        read_only_fields = ['id', 'created_at', 'resolved_at', 'is_resolved', 'assigned_to_username']


class SiteMonitoringPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteMonitoringPhoto
        fields = ['id', 'file', 'uploaded_at']
        read_only_fields = fields


class SiteMonitoringVisitSerializer(serializers.ModelSerializer):
    visited_by_username = serializers.CharField(source='visited_by.username', read_only=True)
    visited_by_name = serializers.CharField(source='visited_by.full_name', read_only=True)
    project_reference = serializers.CharField(source='project.project_reference', read_only=True)
    project_title = serializers.CharField(source='project.project_title', read_only=True)
    project_district = serializers.CharField(source='project.district', read_only=True)
    installation_serial = serializers.CharField(source='installation.serial_number', read_only=True, allow_null=True)
    photos = SiteMonitoringPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = SiteMonitoringVisit
        fields = [
            'id', 'project', 'project_reference', 'project_title', 'project_district',
            'installation', 'installation_serial', 'visited_by', 'visited_by_username', 'visited_by_name',
            'visit_date', 'system_working', 'beneficiary_present', 'observations',
            'follow_up_action', 'follow_up_status', 'latitude', 'longitude', 'photos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'visited_by', 'created_at', 'updated_at']

    def validate_observations(self, value):
        if len((value or '').strip()) < 10:
            raise serializers.ValidationError('Describe what you observed (at least 10 characters).')
        return value.strip()

    def validate(self, attrs):
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        installation = attrs.get('installation')
        if installation and project and installation.project_id != project.id:
            raise serializers.ValidationError({'installation': 'The installation does not belong to this project.'})
        if self.instance and 'project' in attrs and attrs['project'].id != self.instance.project_id:
            raise serializers.ValidationError({'project': 'The project of a visit cannot be changed.'})
        return attrs

    @staticmethod
    def validate_photo(upload):
        return validate_document_upload(upload, label='Site photo', allowed=('jpg', 'jpeg', 'png'))


class KpiReviewSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.full_name', read_only=True)
    project_reference = serializers.CharField(source='project.project_reference', read_only=True)
    project_title = serializers.CharField(source='project.project_title', read_only=True)

    class Meta:
        model = KpiReview
        fields = [
            'id', 'project', 'project_reference', 'project_title', 'reviewer', 'reviewer_username', 'reviewer_name',
            'review_period', 'rating', 'uptime_comment', 'beneficiary_comment', 'gender_inclusion_comment',
            'summary', 'recommendations', 'kpi_snapshot', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'reviewer', 'created_at', 'updated_at']
        # Uniqueness per reviewer/period is enforced in the view, where the reviewer is known.
        validators = []

    def validate_review_period(self, value):
        import re
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value or ''):
            raise serializers.ValidationError('Use the YYYY-MM format.')
        return value

    def validate_summary(self, value):
        if len((value or '').strip()) < 10:
            raise serializers.ValidationError('Write a short summary of the review (at least 10 characters).')
        return value.strip()

    def validate(self, attrs):
        if self.instance and 'project' in attrs and attrs['project'].id != self.instance.project_id:
            raise serializers.ValidationError({'project': 'The project of a review cannot be changed.'})
        return attrs


class OversightReviewSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True, default=None)
    reviewer_name = serializers.CharField(source='reviewer.full_name', read_only=True, default=None)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True, default=None)
    project_reference = serializers.CharField(source='project.project_reference', read_only=True, default=None)
    project_title = serializers.CharField(source='project.project_title', read_only=True, default=None)
    project_district = serializers.CharField(source='project.district', read_only=True, default=None)
    vendor_display = serializers.SerializerMethodField()
    installation_serial = serializers.CharField(source='verification_task.report.serial_number', read_only=True, default=None)
    claim_status = serializers.CharField(source='payment_claim.status', read_only=True, default=None)

    class Meta:
        model = OversightReview
        fields = '__all__'
        read_only_fields = [
            'id', 'reviewer', 'reviewer_role', 'verification_round', 'resolved_by', 'resolved_at',
            'resolution_note', 'created_at', 'updated_at',
        ]

    def get_vendor_display(self, obj):
        if obj.vendor_id:
            vendor = obj.vendor
            return vendor.organization_name or vendor.full_name or vendor.username
        if obj.project_id:
            return obj.project.vendor_name or None
        return None

    def validate_comment(self, value):
        if len((value or '').strip()) < 5:
            raise serializers.ValidationError('Write a comment (at least 5 characters).')
        return value.strip()



class AuditEvidenceSerializer(serializers.ModelSerializer):
    added_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvidence
        fields = '__all__'
        read_only_fields = ['id', 'case', 'added_by', 'added_at']

    def get_added_by_name(self, obj):
        return (obj.added_by.full_name or obj.added_by.username) if obj.added_by_id else None

    def get_file_url(self, obj):
        return obj.file.url if obj.file else None


class AuditCaseSerializer(serializers.ModelSerializer):
    """Descriptive fields are writable by the Auditor; workflow fields change only through actions."""

    auditor_name = serializers.SerializerMethodField()
    responded_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    audit_area_display = serializers.CharField(source='get_audit_area_display', read_only=True)
    project_reference = serializers.CharField(source='project.project_reference', read_only=True, default=None)
    project_title = serializers.CharField(source='project.project_title', read_only=True, default=None)
    vendor_display = serializers.SerializerMethodField()
    tender_reference = serializers.CharField(source='tender.reference_number', read_only=True, default=None)
    contract_reference = serializers.CharField(source='contract.reference_number', read_only=True, default=None)
    claim_status = serializers.CharField(source='payment_claim.status', read_only=True, default=None)
    installation_serial = serializers.CharField(source='verification_task.report.serial_number', read_only=True, default=None)
    evidence = AuditEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = AuditCase
        fields = '__all__'
        read_only_fields = [
            'reference', 'status', 'auditor', 'finding_recorded_at', 'response_requested_at', 'management_response',
            'responded_by', 'responded_at', 'finalized_at', 'closed_at', 'created_at', 'updated_at',
        ]

    def get_auditor_name(self, obj):
        return (obj.auditor.full_name or obj.auditor.username) if obj.auditor_id else None

    def get_responded_by_name(self, obj):
        return (obj.responded_by.full_name or obj.responded_by.username) if obj.responded_by_id else None

    def get_vendor_display(self, obj):
        if obj.vendor_id:
            return obj.vendor.organization_name or obj.vendor.full_name or obj.vendor.username
        if obj.project_id:
            return obj.project.vendor_name or None
        return None

    def validate_title(self, value):
        if len((value or '').strip()) < 5:
            raise serializers.ValidationError('Give the case a title (at least 5 characters).')
        return value.strip()

    def validate_scope(self, value):
        if len((value or '').strip()) < 10:
            raise serializers.ValidationError('Describe the audit scope (at least 10 characters).')
        return value.strip()


class ResultsIndicatorSerializer(serializers.ModelSerializer):
    measure_display = serializers.CharField(source='get_measure_display', read_only=True)
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ResultsIndicator
        fields = '__all__'
        read_only_fields = ['id', 'updated_by', 'updated_at']

    def get_updated_by_name(self, obj):
        return (obj.updated_by.full_name or obj.updated_by.username) if obj.updated_by_id else None

    def validate_code(self, value):
        value = (value or '').strip().upper()
        if not value:
            raise serializers.ValidationError('Give the indicator a short code, such as "OUT1.1".')
        return value

    def validate(self, attrs):
        measure = attrs.get('measure', getattr(self.instance, 'measure', None))
        if measure != 'manual' and (attrs.get('manual_actual') is not None):
            raise serializers.ValidationError({'manual_actual': 'Only manual indicators take an entered actual value.'})
        return attrs
