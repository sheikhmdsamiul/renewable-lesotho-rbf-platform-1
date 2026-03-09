from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile', {'fields': (
            'full_name', 'gender', 'role', 'region', 'organization_name',
            'organization_type', 'technology_types', 'status', 'must_change_password'
        )}),
    )
