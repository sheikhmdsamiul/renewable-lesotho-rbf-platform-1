from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from .models import Notification
from .serializers import NotificationSerializer
from rbf.users.models import UserRole


class IsAdminOrReadOnly(BasePermission):
    """
    Allows only Admin to perform write actions; allows read for all (including public).
    """

    def has_permission(self, request, view):
        # Allow public (unauthenticated) read access for GET requests
        if request.method in SAFE_METHODS:
            return True  # Allow both authenticated and unauthenticated read access
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
        )


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-timestamp')
    serializer_class = NotificationSerializer
    permission_classes = [IsAdminOrReadOnly]  # Removed IsAuthenticated to allow public read access
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'status', 'recipient_id']
    search_fields = ['title', 'body', 'event']
    ordering_fields = ['timestamp']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = Notification.objects.all().order_by('-timestamp')
        user = self.request.user
        # Allow unauthenticated users to see notifications (frontend will filter for public relevant ones)
        if not user.is_authenticated:
            return qs
        if user.role == UserRole.VENDOR:
            return qs.filter(recipient_id=str(user.id))
        return qs

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('Only RBF Management Team or Platform Administrator (Super Admin) can modify notifications.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)
