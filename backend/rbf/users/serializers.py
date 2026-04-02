import re

from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .blacklisting import get_active_blacklist_case, normalize_identifier
from .models import (
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
            'tier_assignment', 'verification_zone',
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


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
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
            if self.instance.status != PrequalificationStatus.CLARIFICATION_REQUESTED:
                raise serializers.ValidationError('Only submissions marked Partial (Resubmit) can be edited by vendors.')

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
