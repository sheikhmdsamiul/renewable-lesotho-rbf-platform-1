from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile', {'fields': (
            'full_name', 'gender', 'role', 'region', 'mobile_number', 'national_id', 'address',
            'organization_name', 'organization_type', 'technology_types',
            'registration_certificate_name', 'tax_id', 'device_id',
            'tier_assignment', 'verification_zone',
            'status', 'must_change_password'
        )}),
    )
