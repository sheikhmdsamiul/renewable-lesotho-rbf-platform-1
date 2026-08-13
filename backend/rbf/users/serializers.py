import re
from secrets import choice as secret_choice

from django.contrib.auth.password_validation import validate_password
from django.db import models
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .blacklisting import get_active_blacklist_case, normalize_identifier
from .models import (
    Organization,
    OrganizationType,
    PasswordResetRequest,
    PasswordResetRequestStatus,
    PlatformConfiguration,
    BlacklistedIdentifier,
    BlacklistAppeal,
    BlacklistAppealStatus,
    BlacklistCaseStatus,
    BlacklistReason,
    User,
    UserRole,
    UserStatus,
    VendorBlacklistCase,
    VendorPrequalification,
    PrequalificationStatus,
)
from rbf.projects.models import AuditLog, ProspectSyncLog


ADMIN_CREATE_ROLE_ALIASES = {
    'RMT': UserRole.RBF_OFFICIAL,
    'RBF Management Team': UserRole.RBF_OFFICIAL,
    'TAC': UserRole.TAC,
    'TAC Member': UserRole.TAC,
    'DoE': UserRole.DOE_OFFICER,
    'DoE Officer': UserRole.DOE_OFFICER,
    'Field Officer': UserRole.FIELD_VERIFIER,
    'Field Verifier': UserRole.FIELD_VERIFIER,
    'PSC': UserRole.UNDP_DONOR,
    'Project Steering Committee': UserRole.UNDP_DONOR,
    'UNDP': UserRole.UNDP_DONOR,
    'Auditor': UserRole.AUDITOR,
}


def generate_temporary_password(length: int = 12) -> str:
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%'
    return ''.join(secret_choice(alphabet) for _ in range(length))


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    vendor_tag = serializers.SerializerMethodField(read_only=True)
    blacklist_summary = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'gender', 'role', 'region',
            'mobile_number', 'national_id', 'address',
            'organization_name', 'organization_type', 'technology_types',
            'registration_certificate_name', 'tax_id', 'device_id', 'associated_entities',
            'bank_name', 'bank_branch', 'bank_swift_code', 'bank_sort_code',
            'tier_assignment', 'verification_zone', 'districts',
            'status', 'must_change_password', 'password', 'vendor_tag', 'blacklist_summary'
        ]
        read_only_fields = ['id']

    def validate_associated_entities(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            items = re.split(r'[\n,;]+', value)
        elif isinstance(value, list):
            items = value
        else:
            raise serializers.ValidationError('Associated entities must be a list of names.')

        cleaned = []
        seen = set()
        for item in items:
            text = str(item).strip()
            key = normalize_identifier(text)
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned

    def validate(self, attrs):
        request = self.context.get('request')
        if self.instance is None and request is not None and not request.user.is_authenticated:
            # Public endpoint is for vendor self-registration only.
            requested_role = attrs.get('role', UserRole.VENDOR)
            if requested_role != UserRole.VENDOR:
                raise serializers.ValidationError({'role': 'Only vendor registration is allowed.'})
            attrs['status'] = 'Pending'
            email = (attrs.get('email') or '').strip().lower()
            cache_key = f'registration_otp_verified:{email}'
            cache = self.context.get('cache')
            if not cache or not cache.get(cache_key):
                raise serializers.ValidationError({'email': 'OTP verification is required before registration.'})

        if self.instance is None and request is not None and request.user.is_authenticated:
            if request.user.role != UserRole.ADMIN:
                raise serializers.ValidationError({'role': 'Only Platform Administrator (Super Admin) can create accounts.'})

        if self.instance is None:
            role = attrs.get('role', UserRole.VENDOR)
            if role == UserRole.VENDOR and not attrs.get('status'):
                attrs['status'] = 'Pending'

        # Common required fields
        gender = attrs.get('gender') or getattr(self.instance, 'gender', None)
        email = attrs.get('email') or getattr(self.instance, 'email', None)
        mobile_value = attrs.get('mobile_number') or getattr(self.instance, 'mobile_number', None)
        region_value = attrs.get('region') or getattr(self.instance, 'region', None)
        if not gender:
            raise serializers.ValidationError({'gender': 'Gender is required.'})
        if not email:
            raise serializers.ValidationError({'email': 'Email is required.'})
        if not mobile_value:
            raise serializers.ValidationError({'mobile_number': 'Mobile number is required.'})
        mobile = str(mobile_value or '').strip()
        if mobile and not re.fullmatch(r'\d{8,15}', mobile):
            raise serializers.ValidationError({'mobile_number': 'Mobile number must be 8-15 digits.'})
        if not region_value:
            raise serializers.ValidationError({'region': 'Region is required.'})

        role = attrs.get('role', getattr(self.instance, 'role', None))
        if role == UserRole.VENDOR:
            missing = {}
            national_id = attrs.get('national_id') or getattr(self.instance, 'national_id', None)
            address = attrs.get('address') or getattr(self.instance, 'address', None)
            org_name = attrs.get('organization_name') or getattr(self.instance, 'organization_name', None)
            org_type = attrs.get('organization_type') or getattr(self.instance, 'organization_type', None)
            tech_types = attrs.get('technology_types') or getattr(self.instance, 'technology_types', None) or []
            reg_cert = attrs.get('registration_certificate_name') or getattr(self.instance, 'registration_certificate_name', None)
            tax_id = attrs.get('tax_id') or getattr(self.instance, 'tax_id', None)
            associated_entities = attrs.get('associated_entities', getattr(self.instance, 'associated_entities', [])) or []
            if not national_id:
                missing['national_id'] = 'National ID or Passport is required for vendors.'
            if not address:
                missing['address'] = 'Address is required for vendors.'
            if not org_name:
                missing['organization_name'] = 'Organization name is required for vendors.'
            if not org_type:
                missing['organization_type'] = 'Organization type is required for vendors.'
            if not tech_types:
                missing['technology_types'] = 'At least one technology type is required for vendors.'
            if not reg_cert:
                missing['registration_certificate_name'] = 'Registration certificate is required for vendors.'
            if not tax_id:
                missing['tax_id'] = 'Tax ID is required for vendors.'
            if missing:
                raise serializers.ValidationError(missing)
            normalized_org = normalize_identifier(org_name)
            normalized_tax = normalize_identifier(tax_id)
            normalized_national_id = normalize_identifier(national_id)
            normalized_entities = {normalize_identifier(item) for item in associated_entities if normalize_identifier(item)}
            identifier_filter = Q()
            if normalized_org:
                identifier_filter |= Q(normalized_organization_name=normalized_org)
            if normalized_tax:
                identifier_filter |= Q(normalized_tax_id=normalized_tax)
            if normalized_national_id:
                identifier_filter |= Q(normalized_national_id=normalized_national_id)
            identifier_qs = BlacklistedIdentifier.objects.filter(active=True).filter(identifier_filter) if identifier_filter else BlacklistedIdentifier.objects.none()
            if self.instance is not None:
                identifier_qs = identifier_qs.exclude(vendor=self.instance)
            associated_match = False
            if normalized_entities:
                for identifier in BlacklistedIdentifier.objects.filter(active=True):
                    if self.instance is not None and identifier.vendor_id == self.instance.id:
                        continue
                    if normalized_entities.intersection(identifier.normalized_associated_entities or []):
                        associated_match = True
                        break
            if identifier_qs.exists() or associated_match:
                raise serializers.ValidationError({
                    'organization_name': 'This vendor identity is blacklisted and cannot be re-registered.',
                    'tax_id': 'This vendor identity is blacklisted and cannot be re-registered.',
                    'national_id': 'This vendor identity is blacklisted and cannot be re-registered.',
                    'associated_entities': 'A director or partner linked to a blacklisted company appears in this application.',
                })
        else:
            verification_zone = attrs.get('verification_zone') or getattr(self.instance, 'verification_zone', None)
            if role == UserRole.FIELD_VERIFIER and not verification_zone:
                raise serializers.ValidationError({'verification_zone': 'Verification zone is required for field verifiers.'})

        password = attrs.get('password')
        if self.instance is None and role == UserRole.VENDOR and not password:
            raise serializers.ValidationError({'password': 'This field is required.'})
        if password:
            validate_password(password)

        reg_name = str(attrs.get('registration_certificate_name') or '').strip().lower()
        if reg_name and not reg_name.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
            raise serializers.ValidationError({'registration_certificate_name': 'Certificate must be a PDF or JPG/PNG file.'})

        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        role = validated_data.get('role', UserRole.VENDOR)
        if role != UserRole.VENDOR:
            validated_data.setdefault('status', 'Active')
        else:
            validated_data.setdefault('status', 'Pending')
        user = User(**validated_data)
        if role != UserRole.VENDOR:
            user.must_change_password = True
        if not password and role != UserRole.VENDOR:
            password = User.objects.make_random_password(length=12)
            self.generated_password = password
        if password:
            user.set_password(password)
        user.save()
        if role == UserRole.VENDOR:
            email = (user.email or '').strip().lower()
            cache_key = f'registration_otp_verified:{email}'
            cache = self.context.get('cache')
            if cache:
                cache.delete(cache_key)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
            instance.must_change_password = False
        instance.save()
        return instance

    def get_vendor_tag(self, obj):
        if obj.role != UserRole.VENDOR:
            return None
        tech = obj.technology_types[0] if obj.technology_types else 'GEN'
        org = (obj.organization_type or 'Type').replace(' ', '')
        return f"Vendor_{org}_{tech}"

    def get_blacklist_summary(self, obj):
        if obj.role != UserRole.VENDOR:
            return None
        case = get_active_blacklist_case(obj)
        if not case:
            return None
        return {
            'case_id': str(case.id),
            'status': case.status,
            'reason': case.reason,
            'expiry_date': case.expiry_date.isoformat() if case.expiry_date else None,
            'cooling_off_until': case.cooling_off_until.isoformat() if case.cooling_off_until else None,
            'is_permanent': case.is_permanent,
            'banner': (
                'This account has been blacklisted. Access to new features is restricted.'
                if obj.status == UserStatus.BLACKLISTED
                else 'This account is suspended pending blacklisting review. Access to new features is restricted.'
            ),
            'appeal_allowed': case.status in {
                BlacklistCaseStatus.INITIATED,
                BlacklistCaseStatus.UNDER_REVIEW,
                BlacklistCaseStatus.BLACKLISTED,
            },
        }


class AdminManagedUserSerializer(serializers.ModelSerializer):
    role = serializers.CharField()
    district = serializers.SerializerMethodField(read_only=True)
    districts = serializers.JSONField(required=False, default=list)
    role_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'full_name',
            'gender',
            'role',
            'role_label',
            'region',
            'verification_zone',
            'districts',
            'district',
            'status',
            'is_active',
            'must_change_password',
            'last_login',
        ]
        read_only_fields = ['id', 'username', 'must_change_password', 'last_login']
        extra_kwargs = {
            'username': {'required': False, 'allow_blank': True},
            'email': {'required': True},
        }

    def get_district(self, obj):
        if obj.districts and isinstance(obj.districts, list) and len(obj.districts) > 0:
            return ', '.join(obj.districts)
        return obj.verification_zone or obj.region or ''

    def get_role_label(self, obj):
        if obj.role == UserRole.UNDP_DONOR:
            return 'PSC/UNDP'
        if obj.role == UserRole.RBF_OFFICIAL:
            return 'RMT'
        if obj.role == UserRole.DOE_OFFICER:
            return 'DoE'
        if obj.role == UserRole.FIELD_VERIFIER:
            return 'Field Officer'
        return obj.role

    def validate_role(self, value):
        normalized = ADMIN_CREATE_ROLE_ALIASES.get(str(value).strip(), value)
        if normalized in {UserRole.VENDOR, UserRole.ADMIN}:
            raise serializers.ValidationError('Role cannot be Vendor or Super Admin for admin-created users.')
        if normalized not in {UserRole.RBF_OFFICIAL, UserRole.TAC, UserRole.DOE_OFFICER, UserRole.FIELD_VERIFIER, UserRole.UNDP_DONOR, UserRole.AUDITOR}:
            raise serializers.ValidationError('Unsupported admin-managed role.')
        return normalized

    def validate(self, attrs):
        role = attrs.get('role', getattr(self.instance, 'role', None))
        full_name = str(attrs.get('full_name', getattr(self.instance, 'full_name', '')) or '').strip()
        email = str(attrs.get('email', getattr(self.instance, 'email', '')) or '').strip().lower()
        gender = str(attrs.get('gender', getattr(self.instance, 'gender', '')) or '').strip()
        region = str(attrs.get('region', getattr(self.instance, 'region', '')) or '').strip()
        verification_zone = str(attrs.get('verification_zone', getattr(self.instance, 'verification_zone', '')) or '').strip()
        districts = attrs.get('districts', getattr(self.instance, 'districts', None))

        errors = {}
        if not full_name:
            errors['full_name'] = 'Full name is required.'
        if not email:
            errors['email'] = 'Email is required.'
        if not gender:
            errors['gender'] = 'Gender is required.'
        if role in {UserRole.FIELD_VERIFIER, UserRole.DOE_OFFICER}:
            has_districts = districts and isinstance(districts, list) and len(districts) > 0
            if not has_districts and not verification_zone and not region:
                errors['districts'] = 'At least one district is required for Field Officer and DoE users.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        email = str(validated_data['email']).strip().lower()
        validated_data['email'] = email
        if not validated_data.get('username'):
            base = re.sub(r'[^a-z0-9]+', '_', email.split('@')[0].lower()).strip('_') or 'user'
            username = base
            suffix = 1
            while User.objects.filter(username=username).exists():
                suffix += 1
                username = f'{base}_{suffix}'
            validated_data['username'] = username

        temporary_password = generate_temporary_password(12)
        user = User(**validated_data)
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.must_change_password = True
        user.set_password(temporary_password)
        user.save()
        self.generated_password = temporary_password
        return user

    def update(self, instance, validated_data):
        old_active = instance.is_active
        districts = validated_data.get('districts')
        if districts and isinstance(districts, list) and len(districts) > 0:
            validated_data['verification_zone'] = districts[0]
            validated_data['region'] = districts[0]
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        status_value = str(validated_data.get('status', instance.status) or instance.status)
        instance.is_active = status_value == UserStatus.ACTIVE and bool(validated_data.get('is_active', instance.is_active))
        instance.save()
        self.was_deactivated = old_active and not instance.is_active
        return instance


class AdminManagedUserDetailSerializer(AdminManagedUserSerializer):
    recent_audit_logs = serializers.SerializerMethodField()
    prospect_sync_status = serializers.SerializerMethodField()

    class Meta(AdminManagedUserSerializer.Meta):
        fields = AdminManagedUserSerializer.Meta.fields + ['recent_audit_logs', 'prospect_sync_status']

    def get_recent_audit_logs(self, obj):
        logs = AuditLog.objects.filter(actor=obj).order_by('-created_at')[:10]
        return [
            {
                'id': log.id,
                'action': log.action,
                'module': log.module,
                'record_id': log.record_id,
                'record_type': log.record_type,
                'created_at': log.created_at,
            }
            for log in logs
        ]

    def get_prospect_sync_status(self, obj):
        logs = ProspectSyncLog.objects.filter(record_id=obj.id, record_type='user').order_by('-created_at')[:10]
        return [
            {
                'id': log.id,
                'method_name': log.method_name,
                'status': log.status,
                'attempts': log.attempts,
                'error_message': log.error_message,
                'created_at': log.created_at,
            }
            for log in logs
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlatformConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformConfiguration
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_allowed_file_types(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split('/') if item.strip()]
        return [str(item).strip().upper() for item in value if str(item).strip()]

    def validate_national_main_program_budget(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError('National/Main Program Budget cannot be negative.')
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        login_identifier = str(attrs.get('username', '') or '').strip()
        if login_identifier and '@' in login_identifier:
            matched_user = User.objects.filter(email__iexact=login_identifier).only('username').first()
            if matched_user:
                attrs = {**attrs, 'username': matched_user.username}
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class VendorPrequalificationSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)

    class Meta:
        model = VendorPrequalification
        fields = [
            'id',
            'vendor',
            'vendor_username',
            'company_name',
            'organization_type',
            'tax_id',
            'hq_address',
            'technology_types',
            'registration_certificate_name',
            'trading_license',
            'registration_certificate',
            'tax_compliance_certificate',
            'authorized_signatory_id',
            'experience_financial_proof',
            'tech_tier',
            'years_experience',
            'prior_projects',
            'annual_revenue',
            'districts_covered',
            'female_beneficiary_target',
            'vulnerable_group_target',
            'bank_name',
            'bank_branch',
            'bank_swift_code',
            'bank_sort_code',
            'bank_account_name',
            'bank_account_number',
            'contact_number',
            'email',
            'gender_of_focal_person',
            'declaration_accepted',
            'reviewer_comments',
            'status',
            'submitted_at',
            'reviewed_at',
            'reviewed_by',
            'reviewed_by_username',
        ]
        read_only_fields = [
            'id',
            'vendor',
            'submitted_at',
            'reviewed_at',
            'reviewed_by',
            'reviewed_by_username',
            'vendor_username',
        ]

    def validate(self, attrs):
        """Validate pre-qualification submission"""
        request = self.context.get('request')
        if self.instance is not None and request and request.user.role == UserRole.VENDOR:
            if self.instance.vendor_id != request.user.id:
                raise serializers.ValidationError('You can only edit your own pre-qualification submission.')
            if self.instance.status not in (PrequalificationStatus.CLARIFICATION_REQUESTED, PrequalificationStatus.REJECTED):
                raise serializers.ValidationError('Only submissions marked Partial (Resubmit) or Rejected can be edited by vendors.')

        if request and request.method == 'POST':
            if request.user.role != UserRole.VENDOR:
                raise serializers.ValidationError('Only vendors can submit pre-qualification forms.')
            attrs['status'] = PrequalificationStatus.PENDING
            attrs['vendor'] = request.user
        
        # Validate percentages
        female_target = attrs.get('female_beneficiary_target', 50)
        if female_target < 50:
            raise serializers.ValidationError({
                'female_beneficiary_target': 'Female beneficiary target must be at least 50%.'
            })
        
        vulnerable_target = attrs.get('vulnerable_group_target', 30)
        if vulnerable_target < 30:
            raise serializers.ValidationError({
                'vulnerable_group_target': 'Vulnerable group inclusion target must be at least 30%.'
            })
        
        # Validate contact number length
        contact = attrs.get('contact_number', '')
        if contact and (len(contact) < 10 or len(contact) > 15):
            raise serializers.ValidationError({
                'contact_number': 'Contact number must be between 10-15 digits.'
            })
        
        # Validate technology types
        tech_types = attrs.get('technology_types', [])
        if not tech_types:
            raise serializers.ValidationError({
                'technology_types': 'Select at least one technology type.'
            })

        def validate_file(field_name, max_size_mb=5, allowed_ext=None):
            file_obj = attrs.get(field_name)
            if not file_obj:
                return
            if file_obj.size > max_size_mb * 1024 * 1024:
                raise serializers.ValidationError({
                    field_name: f'File too large (max {max_size_mb}MB).'
                })
            valid_ext = allowed_ext or {'.pdf', '.doc', '.docx'}
            import os
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                raise serializers.ValidationError({
                    field_name: 'Invalid file type. Allowed: PDF, DOC, DOCX.'
                })

        validate_file('trading_license')
        validate_file('registration_certificate')
        validate_file('tax_compliance_certificate')
        validate_file('authorized_signatory_id')
        validate_file('experience_financial_proof')
        
        return attrs

    def update(self, instance, validated_data):
        request = self.context.get('request')
        is_vendor_resubmission = bool(
            request
            and request.user.role == UserRole.VENDOR
            and instance.vendor_id == request.user.id
        )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if is_vendor_resubmission:
            instance.status = PrequalificationStatus.PENDING
            instance.reviewed_by = None
            instance.reviewed_at = None

        instance.save()
        return instance


class VendorBlacklistCaseSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    initiated_by_username = serializers.CharField(source='initiated_by.username', read_only=True)
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)
    confirmed_by_username = serializers.CharField(source='confirmed_by.username', read_only=True)
    reinstated_by_username = serializers.CharField(source='reinstated_by.username', read_only=True)

    class Meta:
        model = VendorBlacklistCase
        fields = [
            'id',
            'vendor',
            'vendor_username',
            'reason',
            'description',
            'justification_document',
            'status',
            'initiated_by',
            'initiated_by_username',
            'initiated_at',
            'notice_sent_at',
            'cooling_off_until',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
            'review_notes',
            'confirmed_by',
            'confirmed_by_username',
            'confirmed_at',
            'final_decision_notes',
            'is_permanent',
            'expiry_date',
            'reinstated_at',
            'reinstated_by',
            'reinstated_by_username',
        ]
        read_only_fields = [
            'id',
            'status',
            'initiated_by',
            'initiated_by_username',
            'initiated_at',
            'notice_sent_at',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
            'confirmed_by',
            'confirmed_by_username',
            'confirmed_at',
            'reinstated_at',
            'reinstated_by',
            'reinstated_by_username',
        ]


class BlacklistAppealSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)

    class Meta:
        model = BlacklistAppeal
        fields = [
            'id',
            'case',
            'vendor',
            'vendor_username',
            'rebuttal_text',
            'rebuttal_document',
            'status',
            'submitted_at',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
            'resolution_notes',
        ]
        read_only_fields = [
            'id',
            'vendor',
            'vendor_username',
            'status',
            'submitted_at',
            'reviewed_by',
            'reviewed_by_username',
            'reviewed_at',
        ]


class VendorProfileSerializer(serializers.ModelSerializer):
    """Detailed vendor profile for profile page"""
    prequalification = serializers.SerializerMethodField()
    blacklist_status = serializers.SerializerMethodField()
    bid_count = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()
    total_contract_value = serializers.SerializerMethodField()
    bank_account_name = serializers.SerializerMethodField()
    bank_account_number = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    bids_data = serializers.SerializerMethodField()
    projects_data = serializers.SerializerMethodField()
    performance_data = serializers.SerializerMethodField()
    payments_data = serializers.SerializerMethodField()
    audit_trail = serializers.SerializerMethodField()
    prospect_sync_logs = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    operational_standing = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'gender', 'role',
            'mobile_number', 'national_id', 'address',
            'organization_name', 'organization_type', 'technology_types',
            'registration_certificate_name', 'tax_id',
            'bank_name', 'bank_branch', 'bank_swift_code', 'bank_sort_code', 'bank_account_name', 'bank_account_number',
            'tier_assignment', 'verification_zone', 'region', 'status', 'operational_standing',
            'date_joined', 'last_login',
            'prequalification', 'blacklist_status', 'bid_count', 'project_count', 'total_contract_value',
            'documents', 'bids_data', 'projects_data', 'performance_data', 'payments_data', 'audit_trail', 'prospect_sync_logs',
        ]

    def _request(self):
        return self.context.get('request')

    def _viewer(self):
        request = self._request()
        return getattr(request, 'user', None)

    def _viewer_role(self):
        viewer = self._viewer()
        return getattr(viewer, 'role', None)

    def _build_absolute_uri(self, value):
        if not value:
            return None
        request = self._request()
        if hasattr(value, 'url'):
            value = value.url
        if request:
            return request.build_absolute_uri(str(value))
        return str(value)

    def _latest_prequalification(self, obj):
        cached = getattr(obj, '_latest_prequalification_profile', None)
        if cached is not None:
            return cached
        latest = VendorPrequalification.objects.filter(vendor=obj).order_by('-submitted_at').first()
        obj._latest_prequalification_profile = latest
        return latest

    def _latest_blacklist_case(self, obj):
        cached = getattr(obj, '_latest_blacklist_case_profile', None)
        if cached is not None:
            return cached
        latest = VendorBlacklistCase.objects.filter(vendor=obj).order_by('-initiated_at').first()
        obj._latest_blacklist_case_profile = latest
        return latest

    def _project_queryset(self, obj):
        from rbf.projects.models import Project
        return (
            Project.objects.filter(vendor_id=str(obj.id))
            .prefetch_related('milestones', 'payment_claims', 'anomaly_flags', 'documents', 'updates')
            .select_related('tender')
            .order_by('-created_at', '-id')
        )

    def _can_view_bids(self):
        return self._viewer_role() in {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.TAC, UserRole.AUDITOR, UserRole.ADMIN}

    def _can_view_performance(self):
        return self._viewer_role() in {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.TAC, UserRole.DOE_OFFICER, UserRole.AUDITOR, UserRole.ADMIN}

    def _can_view_payments(self):
        return self._viewer_role() in {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.UNDP_DONOR, UserRole.AUDITOR, UserRole.ADMIN}

    def _can_view_audit(self):
        return self._viewer_role() in {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.ADMIN}

    def _can_view_financial_details(self):
        return self._viewer_role() in {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.UNDP_DONOR, UserRole.AUDITOR, UserRole.ADMIN}

    def _can_view_prospect_sync(self):
        return self._viewer_role() in {UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.ADMIN}

    def get_prequalification(self, obj):
        prequal = self._latest_prequalification(obj)
        if prequal:
            return {
                'status': prequal.status,
                'approved_at': prequal.reviewed_at,
                'submitted_at': prequal.submitted_at,
                'company_name': prequal.company_name,
                'organization_type': prequal.organization_type,
                'tax_id': prequal.tax_id,
                'hq_address': prequal.hq_address,
                'tech_tier': prequal.tech_tier,
                'technology_types': prequal.technology_types or [],
                'female_beneficiary_target': prequal.female_beneficiary_target,
                'vulnerable_group_target': prequal.vulnerable_group_target,
                'years_experience': prequal.years_experience,
                'prior_projects': prequal.prior_projects,
                'annual_revenue': float(prequal.annual_revenue) if prequal.annual_revenue else None,
                'districts_covered': prequal.districts_covered,
                'contact_number': prequal.contact_number,
                'email': prequal.email,
                'gender_of_focal_person': prequal.gender_of_focal_person,
                'bank_name': prequal.bank_name,
                'bank_branch': prequal.bank_branch,
                'bank_swift_code': prequal.bank_swift_code,
                'bank_sort_code': prequal.bank_sort_code,
                'bank_account_name': prequal.bank_account_name,
                'bank_account_number': prequal.bank_account_number,
                'trading_license': self._build_absolute_uri(prequal.trading_license),
                'registration_certificate': self._build_absolute_uri(prequal.registration_certificate),
                'tax_compliance_certificate': self._build_absolute_uri(prequal.tax_compliance_certificate),
                'authorized_signatory_id': self._build_absolute_uri(prequal.authorized_signatory_id),
                'experience_financial_proof': self._build_absolute_uri(prequal.experience_financial_proof),
            }
        return None

    def get_blacklist_status(self, obj):
        case = self._latest_blacklist_case(obj)
        if case:
            return {
                'status': case.status,
                'reason': case.reason,
                'description': case.description,
                'expiry_date': case.expiry_date,
                'is_permanent': case.is_permanent,
                'initiated_at': case.initiated_at,
                'reviewed_at': case.reviewed_at,
                'confirmed_at': case.confirmed_at,
                'reinstated_at': case.reinstated_at,
            }
        return {'status': 'Clear'}

    def get_status(self, obj):
        """Return computed status based on prequalification and blacklist status"""
        return obj.computed_status

    def get_operational_standing(self, obj):
        from rbf.users.models import BlacklistCaseStatus, PrequalificationStatus
        latest_prequalification = VendorPrequalification.objects.filter(vendor=obj).order_by('-submitted_at').first()
        latest_blacklist_case = obj.blacklist_cases.order_by('-initiated_at').first()

        if latest_blacklist_case:
            if latest_blacklist_case.status == BlacklistCaseStatus.BLACKLISTED:
                return 'Blacklisted'
            if latest_blacklist_case.status in {BlacklistCaseStatus.INITIATED, BlacklistCaseStatus.UNDER_REVIEW}:
                return 'Suspended'
            if latest_blacklist_case.status == BlacklistCaseStatus.REINSTATED:
                return 'Reinstated'

        if latest_prequalification is None:
            return 'Not Pre-Qualified'

        if latest_prequalification.status == PrequalificationStatus.APPROVED:
            return 'Active'

        if latest_prequalification.status in {
            PrequalificationStatus.PENDING,
            PrequalificationStatus.UNDER_REVIEW,
            PrequalificationStatus.CLARIFICATION_REQUESTED,
        }:
            return 'Pre-Qualification Under Review'

        return 'Not Pre-Qualified'

    def get_bid_count(self, obj):
        from rbf.tenders.models import TenderBid
        return TenderBid.objects.filter(vendor_id=str(obj.id)).count()

    def get_project_count(self, obj):
        from rbf.projects.models import Project
        return Project.objects.filter(vendor_id=str(obj.id)).count()

    def get_total_contract_value(self, obj):
        from rbf.projects.models import Project
        total = Project.objects.filter(vendor_id=str(obj.id)).aggregate(total=models.Sum('budget'))
        return float(total['total'] or 0)

    def get_bank_account_name(self, obj):
        prequal = VendorPrequalification.objects.filter(vendor_id=str(obj.id)).order_by('-submitted_at').first()
        return prequal.bank_account_name if prequal and prequal.bank_account_name else None

    def get_bank_account_number(self, obj):
        prequal = self._latest_prequalification(obj)
        return prequal.bank_account_number if prequal and prequal.bank_account_number else None

    def get_documents(self, obj):
        project_documents = []
        contract_documents = []
        prequalification_documents = []

        prequal = self._latest_prequalification(obj)
        if prequal:
            for label, file_field, category in [
                ('Trading License', prequal.trading_license, 'Pre-Qualification'),
                ('Registration Certificate', prequal.registration_certificate, 'Pre-Qualification'),
                ('Tax Compliance Certificate', prequal.tax_compliance_certificate, 'Pre-Qualification'),
                ('Authorized Signatory ID', prequal.authorized_signatory_id, 'Pre-Qualification'),
                ('Experience / Financial Proof', prequal.experience_financial_proof, 'Pre-Qualification'),
            ]:
                if file_field:
                    prequalification_documents.append({
                        'label': label,
                        'category': category,
                        'url': self._build_absolute_uri(file_field),
                        'uploaded_at': prequal.submitted_at,
                    })

        from rbf.projects.models import ProjectDocument
        from rbf.tenders.models import TenderContract
        project_ids = list(self._project_queryset(obj).values_list('id', flat=True))
        for doc in ProjectDocument.objects.filter(project_id__in=project_ids).select_related('project', 'uploaded_by').order_by('-uploaded_at'):
            project_documents.append({
                'id': str(doc.id),
                'project_id': str(doc.project_id),
                'project_reference': doc.project.project_reference or doc.project.project_title or str(doc.project_id),
                'title': doc.title or doc.file.name.split('/')[-1],
                'url': self._build_absolute_uri(doc.file),
                'uploaded_at': doc.uploaded_at,
                'uploaded_by': doc.uploaded_by.full_name if doc.uploaded_by and doc.uploaded_by.full_name else getattr(doc.uploaded_by, 'username', None),
            })

        for contract in TenderContract.objects.filter(vendor_id=str(obj.id)).select_related('tender').order_by('-generated_at'):
            for label, value in [
                ('Generated Contract', contract.generated_file),
                ('Signed Contract', contract.signed_file),
                ('Annex A', contract.annex_a_file),
                ('Annex B', contract.annex_b_file),
                ('Annex C', contract.annex_c_file),
                ('Annex D', contract.annex_d_file),
                ('Annex E', contract.annex_e_file),
            ]:
                if value:
                    contract_documents.append({
                        'contract_id': str(contract.id),
                        'reference_number': contract.reference_number,
                        'title': label,
                        'url': self._build_absolute_uri(value),
                        'uploaded_at': contract.generated_at,
                    })

        return {
            'prequalification_documents': prequalification_documents,
            'project_documents': project_documents,
            'contract_documents': contract_documents,
        }

    def get_bids_data(self, obj):
        if not self._can_view_bids():
            return None
        from rbf.tenders.models import TenderBid, TenderBidEvaluation, TenderContract, BidStatus
        from rbf.tenders.serializers import TenderBidSerializer, TenderBidEvaluationSerializer, TenderContractSerializer

        bids = TenderBid.objects.filter(vendor_id=str(obj.id)).select_related('tender').prefetch_related('sites').order_by('-submitted_at', '-updated_at')
        
        bid_rows = []
        for bid in bids:
            bid_data = TenderBidSerializer(bid, context=self.context).data
            bid_data['tender_name'] = bid.tender.name if bid.tender else None
            bid_data['tender_reference'] = bid.tender.reference_number if bid.tender else None
            bid_rows.append(bid_data)
        
        evaluations = TenderBidEvaluation.objects.filter(bid__vendor_id=str(obj.id)).select_related('bid', 'evaluator').order_by('-created_at')
        if self._viewer_role() == UserRole.TAC:
            evaluations = evaluations.filter(evaluator__role__in={UserRole.TAC, UserRole.ADMIN})
        contracts = TenderContract.objects.filter(vendor_id=str(obj.id)).select_related('tender', 'bid').order_by('-generated_at')

        evaluation_rows = TenderBidEvaluationSerializer(evaluations, many=True, context=self.context).data
        contract_rows = TenderContractSerializer(contracts, many=True, context=self.context).data

        summary = {
            'total_bids': bids.count(),
            'awarded': bids.filter(status=BidStatus.AWARDED).count(),
            'accepted': bids.filter(status=BidStatus.ACCEPTED).count(),
            'rejected': bids.filter(status=BidStatus.REJECTED).count(),
            'pending': bids.filter(status__in={BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.REVISION_REQUIRED, BidStatus.DRAFT}).count(),
        }
        resolved_awards = summary['awarded'] + summary['accepted']
        summary['win_rate_pct'] = round((resolved_awards / summary['total_bids']) * 100, 1) if summary['total_bids'] else 0.0

        return {
            'summary': summary,
            'bids': bid_rows,
            'evaluations': evaluation_rows,
            'contracts': contract_rows,
        }

    def get_projects_data(self, obj):
        from rbf.projects.models import ProjectDocument, ProjectUpdate
        from rbf.projects.serializers import ProjectSerializer

        projects = list(self._project_queryset(obj))
        project_ids = [project.id for project in projects]
        updates = list(
            ProjectUpdate.objects.filter(project_id__in=project_ids)
            .select_related('project', 'author')
            .order_by('-created_at')[:25]
        )
        documents = list(
            ProjectDocument.objects.filter(project_id__in=project_ids)
            .select_related('project', 'uploaded_by')
            .order_by('-uploaded_at')[:25]
        )

        return {
            'projects': ProjectSerializer(projects, many=True, context=self.context).data,
            'recent_updates': [
                {
                    'id': str(update.id),
                    'project_id': str(update.project_id),
                    'project_reference': update.project.project_reference or update.project.project_title or str(update.project_id),
                    'title': update.title,
                    'body': update.body,
                    'created_at': update.created_at,
                    'author_name': update.author.full_name if update.author and update.author.full_name else getattr(update.author, 'username', None),
                }
                for update in updates
            ],
            'recent_documents': [
                {
                    'id': str(document.id),
                    'project_id': str(document.project_id),
                    'project_reference': document.project.project_reference or document.project.project_title or str(document.project_id),
                    'title': document.title or document.file.name.split('/')[-1],
                    'url': self._build_absolute_uri(document.file),
                    'uploaded_at': document.uploaded_at,
                }
                for document in documents
            ],
        }

    def get_performance_data(self, obj):
        if not self._can_view_performance():
            return None
        from django.db.models import Avg, Count, Q, Sum
        from rbf.projects.models import InstallationReport, InstallationStatus, AnomalyFlag, SmartMeterReading, ProjectUpdate

        projects = list(self._project_queryset(obj))
        project_ids = [project.id for project in projects]
        installations = InstallationReport.objects.filter(project_id__in=project_ids, vendor=obj)
        anomalies = AnomalyFlag.objects.filter(project_id__in=project_ids)
        readings = SmartMeterReading.objects.filter(project_id__in=project_ids)

        installation_summary = installations.aggregate(
            total_submitted=Count('id'),
            total_verified=Count('id', filter=Q(status=InstallationStatus.VERIFIED)),
            total_flagged=Count('id', filter=Q(status=InstallationStatus.FLAGGED)),
            total_paused=Count('id', filter=Q(status=InstallationStatus.PAUSED)),
            total_terminated=Count('id', filter=Q(status=InstallationStatus.TERMINATED)),
            female_count=Count('id', filter=Q(household_type__iexact='female_headed')),
            vulnerable_count=Count('id', filter=Q(household_type__iexact='vulnerable')),
            low_income_count=Count('id', filter=Q(household_type__iexact='low_income')),
        )
        total_submitted = int(installation_summary['total_submitted'] or 0)
        total_verified = int(installation_summary['total_verified'] or 0)
        total_flagged = int(installation_summary['total_flagged'] or 0)
        unresolved = anomalies.filter(is_resolved=False)
        target_energy = sum(float(project.energy_output_target_kwh or project.energy_output or 0) for project in projects)
        total_energy = float(readings.aggregate(total=Sum('kwh'))['total'] or 0)
        average_uptime = float(readings.aggregate(avg=Avg('uptime_pct'))['avg'] or 0)
        verification_rate = round((total_verified / total_submitted) * 100, 1) if total_submitted else 0.0
        total_claimable_target = max(total_verified, 1)

        def pct(value):
            return round((int(value or 0) / total_claimable_target) * 100, 1) if total_claimable_target else 0.0

        prequal = self._latest_prequalification(obj)
        notes = list(
            ProjectUpdate.objects.filter(project_id__in=project_ids, author__role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN})
            .select_related('author')
            .order_by('-created_at')[:5]
        )

        return {
            'kpi_rows': [
                {'label': 'Female-headed HH', 'target': f">={prequal.female_beneficiary_target if prequal else 50}%", 'achieved': f"{pct(installation_summary['female_count'])}%", 'status': 'Met' if pct(installation_summary['female_count']) >= float(prequal.female_beneficiary_target if prequal else 50) else 'Below'},
                {'label': 'Vulnerable groups', 'target': f">={prequal.vulnerable_group_target if prequal else 30}%", 'achieved': f"{pct(installation_summary['vulnerable_count'])}%", 'status': 'Met' if pct(installation_summary['vulnerable_count']) >= float(prequal.vulnerable_group_target if prequal else 30) else 'Below'},
                {'label': 'Low-income HH', 'target': '>=60%', 'achieved': f"{pct(installation_summary['low_income_count'])}%", 'status': 'Met' if pct(installation_summary['low_income_count']) >= 60.0 else 'Below'},
                {'label': 'System uptime', 'target': '>=99%', 'achieved': f"{round(average_uptime, 1)}%", 'status': 'Met' if average_uptime >= 99.0 else 'Below'},
                {'label': 'Energy output', 'target': f"{round(target_energy, 1)} kWh", 'achieved': f"{round(total_energy, 1)} kWh", 'status': 'Met' if target_energy <= 0 or total_energy >= target_energy else 'Below'},
                {'label': 'Verification rate', 'target': '100%', 'achieved': f"{verification_rate}%", 'status': 'Met' if verification_rate >= 100.0 else 'Below'},
            ],
            'installation_summary': {
                'submitted': total_submitted,
                'verified': total_verified,
                'flagged': total_flagged,
                'paused': int(installation_summary['total_paused'] or 0),
                'terminated': int(installation_summary['total_terminated'] or 0),
                'verification_rate_pct': verification_rate,
            },
            'anomaly_summary': {
                'total': anomalies.count(),
                'resolved': anomalies.filter(is_resolved=True).count(),
                'unresolved': unresolved.count(),
                'by_type': [
                    {
                        'flag_type': row['flag_type'],
                        'count': row['count'],
                        'resolved': anomalies.filter(flag_type=row['flag_type'], is_resolved=True).count(),
                        'unresolved': anomalies.filter(flag_type=row['flag_type'], is_resolved=False).count(),
                    }
                    for row in anomalies.values('flag_type').annotate(count=Count('id')).order_by('-count', 'flag_type')
                ],
            },
            'meter_summary': {
                'average_uptime_pct': round(average_uptime, 1),
                'total_energy_kwh': round(total_energy, 1),
                'target_energy_kwh': round(target_energy, 1),
                'reading_count': readings.count(),
            },
            'performance_notes': [
                {
                    'id': str(note.id),
                    'created_at': note.created_at,
                    'author_name': note.author.full_name if note.author and note.author.full_name else getattr(note.author, 'username', None),
                    'author_role': note.author.role if note.author else None,
                    'title': note.title,
                    'body': note.body,
                }
                for note in notes
            ],
        }

    def get_payments_data(self, obj):
        if not self._can_view_payments():
            return None
        from django.db.models import Sum
        from rbf.projects.models import PaymentClaim, PaymentClaimStatus
        from rbf.projects.serializers import PaymentClaimSerializer

        claims = PaymentClaim.objects.filter(vendor=obj).select_related('project', 'vendor', 'milestone', 'reviewed_by', 'disbursement').order_by('-submitted_at')
        claim_rows = PaymentClaimSerializer(claims, many=True, context=self.context).data
        total_disbursed = claims.filter(status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID}).aggregate(total=Sum('claim_amount'))['total'] or 0
        total_pending = claims.exclude(status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID, PaymentClaimStatus.REJECTED}).aggregate(total=Sum('claim_amount'))['total'] or 0

        return {
            'summary': {
                'total_contracted_value': self.get_total_contract_value(obj),
                'total_disbursed': float(total_disbursed or 0),
                'total_pending': float(total_pending or 0),
            },
            'claims': claim_rows,
        }

    def get_audit_trail(self, obj):
        if not self._can_view_audit():
            return None
        from django.db.models import Q
        from rbf.projects.models import PaymentClaim
        from rbf.projects.serializers import AuditLogSerializer

        project_ids = [str(pid) for pid in self._project_queryset(obj).values_list('id', flat=True)]
        claim_ids = [str(cid) for cid in PaymentClaim.objects.filter(vendor=obj).values_list('id', flat=True)]
        queryset = AuditLog.objects.select_related('actor')
        if self._viewer_role() == UserRole.VENDOR:
            queryset = queryset.filter(actor=obj)
        else:
            queryset = queryset.filter(
                Q(actor=obj)
                | Q(details__vendor_id=str(obj.id))
                | Q(entity_type='PaymentClaim', entity_id__in=claim_ids)
                | Q(entity_type='Project', entity_id__in=project_ids)
                | Q(record_type='project', record_id__in=project_ids)
                | Q(details__project_id__in=project_ids)
            ).distinct()
        rows = AuditLogSerializer(queryset.order_by('-created_at')[:100], many=True, context=self.context).data
        if self._viewer_role() == UserRole.VENDOR:
            for row in rows:
                row['ip_address'] = ''
        return {
            'limited': self._viewer_role() == UserRole.VENDOR,
            'entries': rows,
        }

    def get_prospect_sync_logs(self, obj):
        if not self._can_view_prospect_sync():
            return []
        logs = ProspectSyncLog.objects.filter(record_id=obj.id, record_type='user').order_by('-created_at')[:10]
        return [
            {
                'id': str(log.id),
                'method_name': log.method_name,
                'status': log.status,
                'attempts': log.attempts,
                'error_message': log.error_message,
                'created_at': log.created_at,
                'updated_at': log.updated_at,
            }
            for log in logs
        ]


class VendorDirectorySerializer(serializers.ModelSerializer):
    vendor_tag = serializers.SerializerMethodField()
    prequalification_status = serializers.SerializerMethodField()
    prequalification_approved_at = serializers.SerializerMethodField()
    blacklist_status = serializers.SerializerMethodField()
    operational_standing = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()
    bid_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    has_pending_password_reset = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'full_name',
            'email',
            'organization_name',
            'organization_type',
            'technology_types',
            'region',
            'status',
            'vendor_tag',
            'last_login',
            'prequalification_status',
            'prequalification_approved_at',
            'blacklist_status',
            'operational_standing',
            'project_count',
            'bid_count',
            'has_pending_password_reset',
        ]

    def get_has_pending_password_reset(self, obj):
        return PasswordResetRequest.objects.filter(
            user=obj,
            status=PasswordResetRequestStatus.PENDING,
        ).exists()

    def get_vendor_tag(self, obj):
        if obj.role != UserRole.VENDOR:
            return None
        tech = obj.technology_types[0] if obj.technology_types else 'GEN'
        org = (obj.organization_type or 'Type').replace(' ', '')
        return f"Vendor_{org}_{tech}"

    def get_prequalification_status(self, obj):
        latest = getattr(obj, '_latest_prequalification', None)
        if latest is not None:
            return latest.status
        latest = obj.prequalifications.order_by('-submitted_at').first()
        return latest.status if latest else None

    def get_prequalification_approved_at(self, obj):
        latest = getattr(obj, '_latest_prequalification', None)
        if latest is not None:
            return latest.reviewed_at
        latest = obj.prequalifications.order_by('-submitted_at').first()
        return latest.reviewed_at if latest else None

    def get_blacklist_status(self, obj):
        case = get_active_blacklist_case(obj)
        return case.status if case else 'Clear'

    def get_operational_standing(self, obj):
        latest_prequalification = getattr(obj, '_latest_prequalification', None)
        if latest_prequalification is None:
            latest_prequalification = obj.prequalifications.order_by('-submitted_at').first()

        latest_blacklist_case = obj.blacklist_cases.order_by('-initiated_at').first()

        if latest_blacklist_case:
            if latest_blacklist_case.status == BlacklistCaseStatus.BLACKLISTED:
                return 'Blacklisted'
            if latest_blacklist_case.status in {BlacklistCaseStatus.INITIATED, BlacklistCaseStatus.UNDER_REVIEW}:
                return 'Suspended'
            if latest_blacklist_case.status == BlacklistCaseStatus.REINSTATED:
                return 'Reinstated'

        if latest_prequalification is None:
            return 'Not Pre-Qualified'

        if latest_prequalification.status == PrequalificationStatus.APPROVED:
            return 'Active'

        if latest_prequalification.status in {
            PrequalificationStatus.PENDING,
            PrequalificationStatus.UNDER_REVIEW,
            PrequalificationStatus.CLARIFICATION_REQUESTED,
        }:
            return 'Pre-Qualification Under Review'

        return 'Not Pre-Qualified'

    def get_project_count(self, obj):
        from rbf.projects.models import Project
        return Project.objects.filter(vendor_id=str(obj.id)).count()

    def get_bid_count(self, obj):
        from rbf.tenders.models import TenderBid
        return TenderBid.objects.filter(vendor_id=str(obj.id)).count()

    def get_status(self, obj):
        """Return computed status based on prequalification and blacklist status"""
        return obj.computed_status
