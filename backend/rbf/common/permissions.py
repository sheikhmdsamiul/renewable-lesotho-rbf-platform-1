from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS


def has_module_permission(user, module, action='view'):
    """Return the effective role permission, with an immutable Super Admin bypass."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'role', None) == 'Platform Administrator (Super Admin)':
        return True
    from rbf.users.models import RolePermission
    record = RolePermission.objects.filter(role=user.role, module=module).first()
    if record is None:
        # Preserve legacy role behavior until this role/module is explicitly configured.
        return True
    return action in (record.actions or [])


def require_module_permission(user, module, action='view'):
    if not has_module_permission(user, module, action):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied(f'Permission required: {module}.{action}')


class RequireAuthForUnsafeMethodsInProd(BasePermission):
    """
    In production mode, require authentication for write operations.
    In development mode, allow all requests to keep local workflows simple.
    """

    def has_permission(self, request, view):
        if not getattr(settings, 'API_REQUIRE_AUTH', False):
            return True
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


class RequireAuthInProd(BasePermission):
    """
    In production mode, require authentication for all requests.
    In development mode, allow all requests.
    """

    def has_permission(self, request, view):
        if not getattr(settings, 'API_REQUIRE_AUTH', False):
            return True
        return bool(request.user and request.user.is_authenticated)
