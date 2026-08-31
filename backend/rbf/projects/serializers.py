from rest_framework import serializers
from django.db.models import Q, Sum
from .models import (
    Project,
    ProjectSetup,
    ProjectSetupReviewStatus,
    Milestone,
    ProjectUpdate,
    ProjectDocument,
    InstallationReport,
    FieldVerification,
    VerificationTask,
    SmartMeterReading,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    AuditLog,
    ProspectSyncLog,
    AnomalyFlag,
    AnomalyReviewEvent,
    AnomalyEvidenceFile,
    Concern,
    ConcernResponse,
    AuditFinding,
)
from rbf.tenders.models import TenderContract
from django.conf import settings
from rbf.users.models import UserRole
from .bank_details import get_vendor_bank_snapshot


class MilestoneSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id']


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
        elif role in {UserRole.DOE_OFFICER, UserRole.UNDP_DONOR}:
            data['beneficiary_id'] = ''
            data['beneficiary_name'] = None

        return data

    class Meta:
        model = InstallationReport
        fields = '__all__'
        read_only_fields = ['id', 'vendor', 'vendor_username', 'submitted_at', 'status', 'gis_status', 'receipt_file_url']


class VerificationTaskSerializer(serializers.ModelSerializer):
    assigned_verifier_username = serializers.CharField(source='assigned_verifier.username', read_only=True)
    field_verification = serializers.SerializerMethodField()

    class Meta:
        model = VerificationTask
        fields = '__all__'
        read_only_fields = [
            'id',
            'assigned_verifier',
            'assigned_verifier_username',
            'distance_meters',
            'anomaly_flag',
            'created_at',
            'updated_at',
        ]

    def get_field_verification(self, obj):
        field_verification = obj.report.field_verifications.first()
        if field_verification is None:
            return None
        return FieldVerificationSerializer(field_verification, context=self.context).data


class FieldVerificationSerializer(serializers.ModelSerializer):
    field_officer_username = serializers.CharField(source='field_officer.username', read_only=True)

    class Meta:
        model = FieldVerification
        fields = '__all__'
        read_only_fields = ['id', 'field_officer_username', 'verified_at']


class SmartMeterReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmartMeterReading
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


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


class ConcernResponseSerializer(serializers.ModelSerializer):
    responded_by_username = serializers.CharField(source='responded_by.username', read_only=True)

    class Meta:
        model = ConcernResponse
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'responded_by_username']


class ConcernSerializer(serializers.ModelSerializer):
    raised_by_username = serializers.CharField(source='raised_by.username', read_only=True)
    raised_by_role = serializers.CharField(source='raised_by.get_role_display', read_only=True)
    raised_by_region = serializers.CharField(source='raised_by.region', read_only=True)
    linked_project_ref = serializers.CharField(source='linked_project.project_reference', read_only=True, allow_null=True)
    linked_project_vendor = serializers.CharField(source='linked_project.vendor.name', read_only=True, allow_null=True)
    linked_project_district = serializers.CharField(source='linked_project.district', read_only=True, allow_null=True)
    responses = ConcernResponseSerializer(many=True, read_only=True)

    class Meta:
        model = Concern
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'raised_by', 'raised_by_username', 'raised_by_role', 'raised_by_region', 'linked_project_ref', 'linked_project_vendor', 'linked_project_district']


class AuditFindingSerializer(serializers.ModelSerializer):
    raised_by_username = serializers.CharField(source='raised_by.username', read_only=True)
    raised_by_role = serializers.CharField(source='raised_by.get_role_display', read_only=True)
    raised_by_region = serializers.CharField(source='raised_by.region', read_only=True)
    linked_project_ref = serializers.CharField(source='linked_project.project_reference', read_only=True, allow_null=True)
    linked_project_vendor = serializers.CharField(source='linked_project.vendor.name', read_only=True, allow_null=True)
    linked_project_district = serializers.CharField(source='linked_project.district', read_only=True, allow_null=True)

    class Meta:
        model = AuditFinding
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'raised_by', 'raised_by_username', 'raised_by_role', 'raised_by_region', 'linked_project_ref', 'linked_project_vendor', 'linked_project_district']
