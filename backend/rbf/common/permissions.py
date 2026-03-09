from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS


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
