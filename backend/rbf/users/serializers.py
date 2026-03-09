from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, UserRole, VendorPrequalification, PrequalificationStatus


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'gender', 'role', 'region',
            'organization_name', 'organization_type', 'technology_types', 'status',
            'must_change_password', 'password'
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'This field is required.'})

        request = self.context.get('request')
        if self.instance is None and request is not None and not request.user.is_authenticated:
            # Public endpoint is for vendor self-registration only.
            requested_role = attrs.get('role', UserRole.VENDOR)
            if requested_role != UserRole.VENDOR:
                raise serializers.ValidationError({'role': 'Only vendor registration is allowed.'})
            attrs['status'] = 'Pending'

        if self.instance is None:
            role = attrs.get('role', UserRole.VENDOR)
            if role == UserRole.VENDOR and not attrs.get('status'):
                attrs['status'] = 'Pending'

        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        if (self.user.status or '').lower() != 'active':
            raise AuthenticationFailed('Your account is pending approval.')

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
            'tech_tier',
            'years_experience',
            'prior_projects',
            'annual_revenue',
            'districts_covered',
            'female_beneficiary_target',
            'vulnerable_group_target',
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
        request = self.context.get('request')
        if request and request.method == 'POST':
            if request.user.role != UserRole.VENDOR:
                raise serializers.ValidationError('Only vendors can submit pre-qualification forms.')
            attrs['status'] = PrequalificationStatus.PENDING
        return attrs
